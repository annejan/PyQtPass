"""
A native implementation of the 'pass' password store.

Like QtPass's ImitatePass backend this talks to gpg and git directly, so no
Python password store library is needed. The on-disk format is the one pass
uses: one gpg encrypted file per entry, a .gpg-id file per (sub)store naming
the recipients and, optionally, a git repository tracking every change.

Writes are atomic (encrypted to memory, written to a temporary file and
renamed into place), so a failing gpg never leaves a truncated entry behind.
A symbolic link inside the store is not part of it: listing and search skip
links and every operation refuses a path that is, or lies behind, one.
"""

import os
import re
import shutil

from pyqtpass import executor
from pyqtpass import git_utils
from pyqtpass.i18n import translate
from pyqtpass.gpg_utils import parse_gpg_id_lines, which_gpg
from pyqtpass.gpgid_trust import (
    GpgIdSigner,
    TrustError,
    list_key,
    parse_header,
    with_header,
)
from pyqtpass.fs_utils import atomic_write, is_link

# Re-exported: other modules import these from here.
from pyqtpass.store_base import (  # pylint: disable=unused-import
    GPG_EXT,
    GPG_ID,
    STAGING_PREFIX,
    CommitError,
    PullConflictError,
    StoreError,
    locked,
    store_lock,
)
from pyqtpass.store_transfer import TransferMixin


class PasswordStore(TransferMixin):
    """
    A pass compatible password store rooted at store_dir.
    """

    # pylint: disable=too-many-public-methods

    def __init__(
        self,
        store_dir,
        gpg_bin=None,
        use_git=True,
        signing_keys=(),
        record=None,
        add_gpg_id=True,
    ):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """
        :param store_dir: Root directory of the store, may contain '~'.
        :param gpg_bin: The gpg executable, found automatically when None.
        :param use_git: Commit changes when the store is a git repository.
        :param signing_keys: Fingerprints that sign the .gpg-id files, like
                             PASSWORD_STORE_SIGNING_KEY; empty to not sign.
        :param record: The GenerationRecord used with signing keys.
        :param add_gpg_id: Commit the .gpg-id files init writes, like
                           QtPass's addGPGId; when False they are left out
                           of git and only the re-encrypted entries are
                           committed.
        """
        self.store_dir = os.path.abspath(os.path.expanduser(store_dir))
        self.gpg_bin = gpg_bin or which_gpg()
        self.use_git = use_git
        self.add_gpg_id = add_gpg_id
        self.signer = GpgIdSigner(signing_keys, self.gpg_bin, record)
        if self.signer.enabled and record is None:
            raise ValueError("Signing keys need a generation record")

    @property
    def lock(self):
        """:return: The lock of this store's folder, see store_lock."""
        return store_lock(self.store_dir)

    # Paths

    def is_initialised(self):
        """
        :return: True when the store root has a .gpg-id file.
        """
        root_id = os.path.join(self.store_dir, GPG_ID)
        return os.path.isfile(root_id) and not is_link(root_id)

    def has_entries(self):
        """
        :return: True when the store directory contains any entry.
        """
        return next(self.iter_entries(), None) is not None

    @staticmethod
    def clean_path(path):
        """
        Normalise a store relative path and refuse ones leaving the store.

        :param path: Path relative to the store root, '/' separated.
        :return: The normalised path without leading or trailing '/'.
        :raises StoreError: when the path is absolute or escapes the store.
        """
        parts = []
        for part in path.replace("\\", "/").split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                raise StoreError(
                    translate(
                        "PasswordStore", "{} would resolve outside the password store"
                    ).format(path)
                )
            parts.append(part)
        return "/".join(parts)

    def absolute(self, path):
        """
        :param path: Path relative to the store root.
        :return: The absolute file system path, after checking it stays in the
                 store and does not pass through a symbolic link.
        """
        clean = self.clean_path(path)
        current = self.store_dir
        for part in clean.split("/") if clean else []:
            current = os.path.join(current, part)
            if is_link(current):
                raise StoreError(
                    translate(
                        "PasswordStore",
                        "{} is, or lies behind, a symbolic link; "
                        "links inside the password store are not followed",
                    ).format(clean)
                )
        return current

    def entry_file(self, path):
        """
        :param path: Entry path relative to the store root, without .gpg.
        :return: Absolute path of the encrypted file of the entry.
        """
        clean = self.clean_path(path)
        if not clean:
            raise StoreError(translate("PasswordStore", "An entry needs a name"))
        absolute = self.absolute(clean + GPG_EXT)
        return absolute

    def relative(self, absolute):
        """
        :param absolute: An absolute path inside the store.
        :return: The path relative to the store root, '/' separated.
        """
        relative = os.path.relpath(absolute, self.store_dir)
        return "" if relative == "." else relative.replace(os.sep, "/")

    def is_folder(self, path):
        """
        :param path: Path relative to the store root.
        :return: True when path is a real folder of the store.
        """
        try:
            absolute = self.absolute(path)
        except StoreError:
            return False
        return os.path.isdir(absolute) and not is_link(absolute)

    def is_entry(self, path):
        """
        :param path: Path relative to the store root.
        :return: True when path is an entry of the store.
        """
        try:
            absolute = self.entry_file(path)
        except StoreError:
            return False
        return os.path.isfile(absolute) and not is_link(absolute)

    # Listing

    def list_dir(self, path=""):
        """
        List the folders and entries directly inside a folder.

        Hidden files and symbolic links are skipped.

        :param path: Folder relative to the store root.
        :return: Tuple of (folder names, entry names), each sorted.
        """
        absolute = self.absolute(path)
        directories, entries = [], []
        for name in os.listdir(absolute):
            if name.startswith("."):
                continue
            full = os.path.join(absolute, name)
            if is_link(full):
                continue
            if os.path.isdir(full):
                directories.append(name)
            elif os.path.isfile(full) and name.endswith(GPG_EXT):
                entries.append(name[: -len(GPG_EXT)])
        return sorted(directories, key=str.lower), sorted(entries, key=str.lower)

    def _walk(self, path=""):
        root = self.absolute(path)
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(
                (
                    name
                    for name in dirs
                    if not name.startswith(".")
                    and not is_link(os.path.join(current, name))
                ),
                key=str.lower,
            )
            yield current, dirs, sorted(files, key=str.lower)

    def iter_entries(self, path=""):
        """
        Iterate over all entries in a folder and its subfolders.

        :param path: Folder relative to the store root.
        :return: Generator of entry paths relative to the store root.
        """
        for current, _, files in self._walk(path):
            for name in files:
                full = os.path.join(current, name)
                if (
                    name.endswith(GPG_EXT)
                    and not name.startswith(".")
                    and os.path.isfile(full)
                    and not is_link(full)
                ):
                    yield self.relative(full)[: -len(GPG_EXT)]

    def list_folders(self):
        """
        :return: All folders of the store relative to the root, '' included.
        """
        return [self.relative(current) for current, _, _ in self._walk()]

    # Recipients

    def list_at(self, folder):
        """
        Read the recipient list stored in exactly this folder.

        :param folder: Folder relative to the store root.
        :return: The gpg ids, or None when the folder has no list of its own
                 and its parent's applies.
        :raises StoreError: when the list there must not be used, or the
                            parent's must not stand in for it.
        """
        clean = self.clean_path(folder)
        candidate = os.path.join(self.absolute(clean), GPG_ID)
        label = "/" + clean
        if os.path.lexists(candidate):
            if is_link(candidate) or not os.path.isfile(candidate):
                if not self.signer.enabled:
                    # A link is not the folder's list: the parent's applies.
                    return None
                raise StoreError(
                    translate(
                        "PasswordStore",
                        "The recipient list of {} is a link or not a file. "
                        "While a signing key is configured the folder does not "
                        "fall back to its parent's list; a holder of the signing "
                        "key saves the recipients in Users again.",
                    ).format(label)
                )
            with open(candidate, "rb") as gpg_id_file:
                contents = gpg_id_file.read()
            if self.signer.enabled:
                try:
                    self.signer.accept(candidate, contents, clean)
                except TrustError as error:
                    raise StoreError(str(error)) from error
            ids = parse_gpg_id_lines(contents.decode("utf-8", errors="replace"))
            if not ids:
                # pass refuses such a folder too ("No user ID").
                raise StoreError(
                    translate(
                        "PasswordStore", "The recipient list of {} names no key."
                    ).format(label)
                )
            return ids
        if self.signer.enabled:
            try:
                remembered = self.signer.remembers(candidate)
            except TrustError as error:
                raise StoreError(str(error)) from error
            if remembered:
                raise StoreError(
                    translate(
                        "PasswordStore",
                        "The signed recipient list of {} was removed; its "
                        "passwords are not encrypted to the parent folder's keys "
                        "instead. A holder of the signing key saves the "
                        "recipients in Users again.",
                    ).format(label)
                )
        return None

    def recipient_list(self, folder=""):
        """
        Find the recipient list that applies to a folder: the nearest
        .gpg-id file, verified when signing keys are configured.

        :param folder: Folder relative to the store root.
        :return: Tuple of (gpg ids, folder of the .gpg-id file).
        :raises StoreError: when no list applies or the list is not trusted.
        """
        parts = [part for part in self.clean_path(folder).split("/") if part]
        while True:
            list_folder = "/".join(parts)
            ids = self.list_at(list_folder)
            if ids is not None:
                return ids, list_folder
            if not parts:
                raise StoreError(
                    translate(
                        "PasswordStore",
                        "You must initialise the password store first "
                        "(no .gpg-id file found)",
                    )
                )
            parts.pop()

    def recipients(self, folder=""):
        """
        Find the gpg ids for a folder from the nearest .gpg-id file.

        :param folder: Folder relative to the store root.
        :return: List of gpg ids.
        :raises StoreError: when no .gpg-id applies to the folder, or it is
                            not trusted.
        """
        return self.recipient_list(folder)[0]

    def _folder_of(self, entry_path):
        clean = self.clean_path(entry_path)
        return clean.rsplit("/", 1)[0] if "/" in clean else ""

    # Encryption

    def decrypt_file(self, absolute):
        """
        Decrypt a file with gpg.

        :param absolute: Absolute path of the encrypted file.
        :return: The decrypted text.
        :raises StoreError: when gpg fails.
        """
        return self.decrypt_bytes(absolute).decode("utf-8", errors="replace")

    def decrypt_bytes(self, absolute):
        """
        Decrypt a file with gpg, keeping its exact bytes; re-encryption uses
        this so entries that are not UTF-8 survive unchanged.

        :param absolute: Absolute path of the encrypted file.
        :return: The decrypted bytes.
        :raises StoreError: when gpg fails.
        """
        returncode, stdout, stderr = executor.run(
            [
                self.gpg_bin,
                "-d",
                "--quiet",
                "--yes",
                "--batch",
                "--no-encrypt-to",
                "--",
                absolute,
            ],
            timeout=300,
        )
        if returncode != 0:
            raise StoreError(
                stderr.decode(errors="replace").strip()
                or translate("PasswordStore", "gpg failed to decrypt")
            )
        return stdout

    def encrypt_to_file(self, absolute, data, recipients):
        """
        Encrypt data for the recipients and atomically write it to a file.

        :param absolute: Absolute path of the file to write.
        :param data: The text or bytes to encrypt.
        :param recipients: List of gpg ids to encrypt for.
        :raises StoreError: when gpg fails; the file is left untouched.
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        args = [
            self.gpg_bin,
            "-e",
            "--quiet",
            "--yes",
            "--batch",
            "--no-encrypt-to",
            "--compress-algo=none",
            "--output",
            "-",
        ]
        for recipient in recipients:
            args += ["-r", recipient]
        returncode, stdout, stderr = executor.run(args, input_data=data, timeout=300)
        if returncode != 0 or not stdout:
            raise StoreError(
                stderr.decode(errors="replace").strip()
                or translate("PasswordStore", "gpg failed to encrypt")
            )
        atomic_write(absolute, stdout)

    # Entries

    def get_key(self, path):
        """
        Decrypt an entry.

        :param path: Entry path relative to the store root.
        :return: The decrypted contents.
        :raises FileNotFoundError: when there is no such entry.
        :raises StoreError: when the path is refused or gpg fails.
        """
        absolute = self.entry_file(path)
        if not os.path.isfile(absolute):
            raise FileNotFoundError(
                translate("PasswordStore", "{} is not in the password store").format(
                    path
                )
            )
        return self.decrypt_file(absolute)

    @locked
    def set_key(self, path, key_data, force=False):
        """
        Encrypt and store an entry.

        :param path: Entry path relative to the store root.
        :param key_data: The contents to store.
        :param force: Overwrite an existing entry.
        :raises FileExistsError: when the entry exists and force is False.
        :raises StoreError: when the path is refused or gpg fails.
        """
        clean = self.clean_path(path)
        absolute = self.entry_file(clean)
        exists = os.path.exists(absolute)
        if exists and not force:
            raise FileExistsError(
                translate("PasswordStore", "{} already exists").format(clean)
            )
        if not key_data.endswith("\n"):
            key_data += "\n"
        recipients = self.recipients(self._folder_of(clean))
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        self.encrypt_to_file(absolute, key_data, recipients)
        if exists:
            message = f"Edit password for {clean} using PyQtPass."
        else:
            message = f"Add given password for {clean} to store."
        self.git_commit([clean + GPG_EXT], message)

    @locked
    def create_folder(self, path):
        """
        Create a folder; it inherits the recipients of its parent.

        :param path: Folder path relative to the store root.
        """
        absolute = self.absolute(path)
        if os.path.exists(absolute):
            raise FileExistsError(
                translate("PasswordStore", "{} already exists").format(path)
            )
        os.makedirs(absolute)

    def _own_lists(self, folder_abs):
        """
        :param folder_abs: An absolute folder of the store.
        :return: The subfolders (relative to it, '' for itself) that hold a
                 recipient list or signature of their own; links are not
                 entered.
        """
        found = []
        for current, dirs, _ in os.walk(folder_abs):
            dirs[:] = [
                name for name in dirs if not is_link(os.path.join(current, name))
            ]
            if any(
                os.path.lexists(os.path.join(current, name))
                for name in (GPG_ID, GPG_ID + ".sig")
            ):
                relative = os.path.relpath(current, folder_abs)
                found.append("" if relative == "." else relative.replace(os.sep, "/"))
        return found

    @staticmethod
    def _join(folder, sub):
        return f"{folder}/{sub}" if folder and sub else folder or sub

    def _list_keys(self, folder_abs, subs):
        """:return: The generation record keys of the lists in subs."""
        return [list_key(os.path.join(folder_abs, sub, GPG_ID)) for sub in subs]

    @locked
    def remove_path(self, path, recursive=False):
        """
        Remove an entry or a folder. A link is removed, not what it points to.
        The record forgets the signed lists of a removed folder, so a new
        folder of that name is not refused as one whose list was removed.

        :param path: Path relative to the store root.
        :param recursive: Allow removing a folder with its contents.
        :raises FileNotFoundError: when there is nothing at path.
        """
        clean = self.clean_path(path)
        parent = self.absolute(self._folder_of(clean)) if clean else self.store_dir
        name = clean.rsplit("/", 1)[-1]
        folder = os.path.join(parent, name)
        entry = os.path.join(parent, name + GPG_EXT)
        if is_link(folder) or is_link(entry):
            link = folder if is_link(folder) else entry
            staged = clean if link == folder else clean + GPG_EXT
            os.unlink(link)
        elif os.path.isdir(folder) and clean:
            if not recursive and os.listdir(folder):
                raise StoreError(
                    translate("PasswordStore", "{} is not empty").format(clean)
                )
            keys = []
            if self.signer.enabled:
                keys = self._list_keys(folder, self._own_lists(folder))
            shutil.rmtree(folder)
            self._forget(keys)
            staged = clean
        elif os.path.isfile(entry):
            os.remove(entry)
            staged = clean + GPG_EXT
        else:
            raise FileNotFoundError(
                translate("PasswordStore", "{} is not in the password store").format(
                    clean
                )
            )
        self.git_commit([staged], f"Remove {clean} from store.")

    def _forget(self, keys):
        if keys:
            try:
                self.signer.forget_keys(keys)
            except TrustError as error:
                raise StoreError(str(error)) from error

    # Recipients management

    def check_sub_lists(self, folder):
        """
        Check the recipient lists of the subfolders before a folder gets new
        recipients, so re-encryption does not stop halfway on one of them.

        :param folder: Folder relative to the store root.
        :raises StoreError: naming the first list that cannot be used.
        """
        clean = self.clean_path(folder)
        for current, _, _ in self._walk(clean):
            relative = self.relative(current)
            if relative != clean:
                self.list_at(relative)

    @locked
    def init(self, gpg_ids, folder="", progress=None, cancelled=None):
        """
        Set the recipients of a (sub)store and re-encrypt its entries, like
        'pass init'. The list and the re-encrypted entries are committed
        together, after re-encryption, so a failed commit never hides
        entries that still use the old keys.

        :param gpg_ids: List of gpg ids to encrypt for.
        :param folder: Folder relative to the store root, '' for the root.
        :param progress: Optional callable(done, total) for re-encryption.
        :param cancelled: Optional callable returning True to stop
                          re-encrypting; what was done is committed.
        """
        if not gpg_ids:
            raise StoreError(translate("PasswordStore", "At least one key is needed"))
        clean = self.clean_path(folder)
        absolute = self.absolute(clean)
        gpg_id_path = os.path.join(absolute, GPG_ID)
        relative_id = f"{clean}/{GPG_ID}" if clean else GPG_ID
        for path in (gpg_id_path, gpg_id_path + ".sig"):
            if is_link(path):
                raise StoreError(
                    translate("PasswordStore", "{} is a symbolic link").format(path)
                )
        has_entries = (
            os.path.isdir(absolute) and next(self.iter_entries(clean), None) is not None
        )
        if has_entries:
            self.check_sub_lists(clean)
        os.makedirs(absolute, exist_ok=True)
        try:
            self.write_gpg_id(gpg_id_path, clean, gpg_ids)
        except TrustError as error:
            raise StoreError(str(error)) from error
        changed = [relative_id, relative_id + ".sig"] if self.add_gpg_id else []
        failure = None
        if has_entries:
            try:
                if not self._reencrypt_entries(clean, changed, progress, cancelled):
                    failure = StoreError(translate("PasswordStore", "it was cancelled"))
            except (OSError, StoreError) as error:
                failure = error
        joined = ", ".join(gpg_ids)
        try:
            self.git_commit(changed, f"Set GPG id to {joined}.")
        except CommitError as error:
            if failure is not None:
                raise StoreError(
                    translate(
                        "PasswordStore",
                        "The recipients were changed, but re-encrypting stopped: "
                        "{0}. Committing what was done failed too: {1}",
                    ).format(failure, error.output)
                ) from failure
            raise CommitError(
                translate(
                    "PasswordStore",
                    "The recipients were changed and every password was "
                    "re-encrypted for them, but git commit failed: {}",
                ).format(error.output),
                error.output,
            ) from error
        if failure is not None:
            raise StoreError(
                translate(
                    "PasswordStore",
                    "The recipients were changed, but re-encrypting stopped: "
                    "{}. Some passwords still use the old keys; use "
                    "Re-encrypt once this is fixed.",
                ).format(failure)
            ) from failure

    def write_gpg_id(self, gpg_id_path, folder, gpg_ids, record_path=None):
        """
        Write a recipient list: signed and with a generation header when
        signing keys are configured, a plain list like pass writes otherwise.

        :param gpg_id_path: Path of the .gpg-id file.
        :param folder: Its folder relative to the store root.
        :param gpg_ids: The recipients.
        :param record_path: Where the list will end up when it is written to a
                            staging copy first; the record is kept for that
                            path.
        """
        signature = gpg_id_path + ".sig"
        if not self.signer.enabled:
            if os.path.lexists(signature):
                raise StoreError(
                    translate(
                        "PasswordStore",
                        "The recipient list of /{} is signed. Configure the "
                        "signing key (Settings, the profile, or "
                        "PASSWORD_STORE_SIGNING_KEY) to change its recipients; "
                        "an unsigned list would break the folder for everyone "
                        "who verifies it.",
                    ).format(folder)
                )
            atomic_write(gpg_id_path, ("\n".join(gpg_ids) + "\n").encode("utf-8"))
            return
        on_disk = 0
        if os.path.isfile(gpg_id_path) and not is_link(gpg_id_path):
            with open(gpg_id_path, "rb") as gpg_id_file:
                current = gpg_id_file.read()
            try:
                self.signer.verify(gpg_id_path, current)
                on_disk = parse_header(current.decode("utf-8"))[0]
            except (TrustError, UnicodeDecodeError):
                on_disk = 0
        record_path = record_path or gpg_id_path
        generation = self.signer.next_generation(record_path, on_disk)
        contents = with_header(generation, folder, gpg_ids).encode("utf-8")
        signed = self.signer.sign(contents)

        def write():
            atomic_write(gpg_id_path, contents)
            atomic_write(signature, signed)

        self.signer.store_written(record_path, contents, generation, write)

    def reencrypt_entry(self, path, cache=None):
        """
        Re-encrypt one entry for the recipients of its folder.

        :param path: Entry path relative to the store root.
        :param cache: Optional dict of folder to recipients, so a list is
                      read (and verified) once per re-encryption run.
        """
        clean = self.clean_path(path)
        absolute = self.entry_file(clean)
        folder = self._folder_of(clean)
        if cache is None:
            recipients = self.recipients(folder)
        else:
            if folder not in cache:
                cache[folder] = self.recipients(folder)
            recipients = cache[folder]
        data = self.decrypt_bytes(absolute)
        self.encrypt_to_file(absolute, data, recipients)

    def _reencrypt_entries(self, folder, changed, progress=None, cancelled=None):
        """
        Re-encrypt the entries of a folder, adding each one's file to changed
        as soon as it is done, so a failure still commits what was done.

        :return: False when it was cancelled before the end.
        """
        entries = list(self.iter_entries(folder))
        cache = {}
        for done, entry in enumerate(entries, 1):
            if cancelled and cancelled():
                return False
            self.reencrypt_entry(entry, cache)
            changed.append(entry + GPG_EXT)
            if progress:
                progress(done, len(entries))
        return True

    @locked
    def reencrypt(self, folder="", progress=None, cancelled=None, commit=True):
        """
        Re-encrypt every entry in a folder for its current recipients.

        :param folder: Folder relative to the store root.
        :param progress: Optional callable(done, total).
        :param cancelled: Optional callable returning True to stop early.
        :param commit: Commit the result to git.
        :return: Number of re-encrypted entries.
        """
        changed = []
        try:
            self._reencrypt_entries(folder, changed, progress, cancelled)
        finally:
            if commit and changed:
                self.git_commit(
                    changed,
                    f"Reencrypt {self.clean_path(folder) or 'password store'}.",
                )
        return len(changed)

    # Search

    def search(
        self, pattern, folder="", progress=None, cancelled=None, match_case=False
    ):
        """
        Search the decrypted contents of all entries, like 'pass grep'.

        :param pattern: A regular expression (Python syntax).
        :param folder: Folder to search in.
        :param progress: Optional callable(done, total).
        :param cancelled: Optional callable returning True to stop early.
        :param match_case: Match upper and lower case exactly.
        :return: Dict of entry path to a list of (line number, line) of the
                 matching lines; line 1 is the password.
        :raises re.error: when the pattern is invalid.
        """
        regex = re.compile(pattern, 0 if match_case else re.IGNORECASE)
        entries = list(self.iter_entries(folder))
        results = {}
        for done, entry in enumerate(entries, 1):
            if cancelled and cancelled():
                break
            try:
                content = self.get_key(entry)
            except (OSError, StoreError):
                continue
            matches = [
                (number, line)
                for number, line in enumerate(content.splitlines(), 1)
                if regex.search(line)
            ]
            if matches:
                results[entry] = matches
            if progress:
                progress(done, len(entries))
        return results

    # Git

    def git_enabled(self):
        """
        :return: True when git is used and the store is a git repository.
        """
        return self.use_git and git_utils.is_git_repo(self.store_dir)

    def git_commit(self, paths, message):
        """
        Commit changed paths when the store is under git.

        :param paths: Paths relative to the store root.
        :param message: The commit message.
        """
        if not self.git_enabled():
            return
        success, output = git_utils.git_commit_paths(self.store_dir, paths, message)
        if not success:
            raise CommitError(
                translate(
                    "PasswordStore", "The change was made, but git commit failed: {}"
                ).format(output),
                output,
            )

    @locked
    def pull(self):
        """
        Pull from the remote, never while the store is being changed.

        :return: Tuple of (success, output).
        """
        return git_utils.git_pull(self.store_dir)

    @locked
    def pull_before_change(self):
        """
        Pull before a change that should start from the latest state of the
        remote, like QtPass before an edit or a re-encrypt. A pull that
        cannot reach the remote leaves the store as it was, and the change
        goes on; one that stops in a merge leaves conflicts, and the change
        must not be made on top of them.

        :return: Tuple of (success, output); (True, '') without a remote.
        :raises PullConflictError: When the store has unmerged files.
        """
        if not git_utils.has_remote(self.store_dir):
            return True, ""
        success, output = git_utils.git_pull(self.store_dir)
        if not success and git_utils.has_unmerged_files(self.store_dir):
            raise PullConflictError(
                translate(
                    "PasswordStore",
                    "The pull left the store with unmerged files. Resolve the "
                    "conflict with git first.",
                )
            )
        return success, output

    @locked
    def push(self, only_with_remote=False):
        """
        Push to the remote, never while the store is being changed.

        :param only_with_remote: Do nothing when no remote is configured.
        :return: Tuple of (success, output); (True, '') when skipped.
        """
        if only_with_remote and not git_utils.has_remote(self.store_dir):
            return True, ""
        return git_utils.git_push(self.store_dir)

    @locked
    def init_git(self):
        """
        Put the store under git and commit its current contents.
        """
        success, output = git_utils.git_init(self.store_dir)
        if not success:
            raise StoreError(
                translate("PasswordStore", "git init failed: {}").format(output)
            )
        self.git_commit(["."], "Add current contents of password store.")
