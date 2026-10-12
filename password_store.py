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

import functools
import os
import re
import threading
import shutil
import tempfile

import executor
import git_utils
from gpg_utils import parse_gpg_id_lines, which_gpg
from gpgid_trust import GpgIdSigner, TrustError, parse_header, with_header
from fs_utils import atomic_write, is_link

GPG_EXT = ".gpg"
GPG_ID = ".gpg-id"


class StoreError(Exception):
    """Raised when a password store operation fails."""


class CommitError(StoreError):
    """
    The change itself was made, but committing it to git failed; the
    message says so, and the change is not to be retried.
    """


def locked(method):
    """
    Run a store method under the store's lock, so changes and git pull or
    push never run at the same time.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)

    return wrapper


class PasswordStore:
    """
    A pass compatible password store rooted at store_dir.
    """

    # pylint: disable=too-many-public-methods

    def __init__(
        self, store_dir, gpg_bin=None, use_git=True, signing_keys=(), record=None
    ):
        """
        :param store_dir: Root directory of the store, may contain '~'.
        :param gpg_bin: The gpg executable, found automatically when None.
        :param use_git: Commit changes when the store is a git repository.
        :param signing_keys: Fingerprints that sign the .gpg-id files, like
                             PASSWORD_STORE_SIGNING_KEY; empty to not sign.
        :param record: The GenerationRecord used with signing keys.
        """
        self.store_dir = os.path.abspath(os.path.expanduser(store_dir))
        self.gpg_bin = gpg_bin or which_gpg()
        self.use_git = use_git
        self.signer = GpgIdSigner(signing_keys, self.gpg_bin, record)
        self.lock = threading.RLock()
        if self.signer.enabled and record is None:
            raise ValueError("Signing keys need a generation record")

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
                raise StoreError(f"{path} would resolve outside the password store")
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
                    f"{clean} is, or lies behind, a symbolic link; "
                    "links inside the password store are not followed"
                )
        return current

    def entry_file(self, path):
        """
        :param path: Entry path relative to the store root, without .gpg.
        :return: Absolute path of the encrypted file of the entry.
        """
        clean = self.clean_path(path)
        if not clean:
            raise StoreError("An entry needs a name")
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
                    f"The recipient list of {label} is a link or not a file. "
                    "While a signing key is configured the folder does not "
                    "fall back to its parent's list; a holder of the signing "
                    "key saves the recipients in Users again."
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
                raise StoreError(f"The recipient list of {label} names no key.")
            return ids
        if self.signer.enabled:
            try:
                remembered = self.signer.remembers(candidate)
            except TrustError as error:
                raise StoreError(str(error)) from error
            if remembered:
                raise StoreError(
                    f"The signed recipient list of {label} was removed; its "
                    "passwords are not encrypted to the parent folder's keys "
                    "instead. A holder of the signing key saves the "
                    "recipients in Users again."
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
                    "You must initialise the password store first "
                    "(no .gpg-id file found)"
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
                stderr.decode(errors="replace").strip() or "gpg failed to decrypt"
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
                stderr.decode(errors="replace").strip() or "gpg failed to encrypt"
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
            raise FileNotFoundError(f"{path} is not in the password store")
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
            raise FileExistsError(f"{clean} already exists")
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
            raise FileExistsError(f"{path} already exists")
        os.makedirs(absolute)

    @locked
    def remove_path(self, path, recursive=False):
        """
        Remove an entry or a folder. A link is removed, not what it points to.

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
                raise StoreError(f"{clean} is not empty")
            shutil.rmtree(folder)
            staged = clean
        elif os.path.isfile(entry):
            os.remove(entry)
            staged = clean + GPG_EXT
        else:
            raise FileNotFoundError(f"{clean} is not in the password store")
        self.git_commit([staged], f"Remove {clean} from store.")

    def _source_and_target(self, old_path, new_path, force):
        old_clean = self.clean_path(old_path)
        new_clean = self.clean_path(new_path)
        if not old_clean or not new_clean:
            raise StoreError("Cannot move or copy the store root")
        if self.is_folder(old_clean):
            source = self.absolute(old_clean)
            if self.is_folder(new_clean) or new_path.endswith("/"):
                new_clean = f"{new_clean}/{old_clean.rsplit('/', 1)[-1]}"
            target = self.absolute(new_clean)
            if target == source or target.startswith(source + os.sep):
                raise StoreError(f"Cannot move {old_clean} into itself")
            relative_target = new_clean
        else:
            source = self.entry_file(old_clean)
            if not os.path.isfile(source):
                raise FileNotFoundError(f"{old_clean} is not in the password store")
            if self.is_folder(new_clean) or new_path.endswith("/"):
                new_clean = f"{new_clean}/{old_clean.rsplit('/', 1)[-1]}"
            target = self.entry_file(new_clean)
            relative_target = new_clean + GPG_EXT
        if os.path.lexists(target) and (not force or os.path.isdir(source)):
            raise FileExistsError(f"{new_clean} already exists")
        self.absolute(self._folder_of(new_clean))
        return old_clean, new_clean, source, target, relative_target

    def _needs_reencrypt(self, old_clean, new_clean, source):
        """
        :return: True when what moves from old_clean to new_clean would be
                 governed by other recipients there, like pass mv/cp decide.
        """
        if os.path.isdir(source):
            if os.path.lexists(os.path.join(source, GPG_ID)):
                return False  # its own list travels with it
            old_folder = self._folder_of(old_clean)
            new_folder = self._folder_of(new_clean)
        else:
            old_folder = self._folder_of(old_clean)
            new_folder = self._folder_of(new_clean)
        try:
            old = self.recipients(old_folder)
        except StoreError:
            return True
        return old != self.recipients(new_folder)

    def _transfer(self, old_path, new_path, force, keep_source):
        """
        Move or copy an entry or folder. When the destination has other
        recipients the copy is re-encrypted before it takes its place, so a
        failure leaves the store as it was.

        :return: Tuple of (old path, new path, git paths to commit).
        """
        # pylint: disable=too-many-locals
        old_clean, new_clean, source, target, relative_target = self._source_and_target(
            old_path, new_path, force
        )
        needs_reencrypt = self._needs_reencrypt(old_clean, new_clean, source)
        parent = os.path.dirname(target)
        os.makedirs(parent, exist_ok=True)
        if os.path.isdir(source):
            if not needs_reencrypt and not keep_source:
                os.replace(source, target)
            else:
                staging = tempfile.mkdtemp(dir=parent, prefix=".pyqtpass-")
                os.rmdir(staging)
                try:
                    shutil.copytree(
                        source,
                        staging,
                        symlinks=True,
                        ignore=lambda folder, names: [
                            name
                            for name in names
                            if is_link(os.path.join(folder, name))
                        ],
                    )
                    if needs_reencrypt:
                        cache = {}
                        for entry in list(self.iter_entries(self.relative(staging))):
                            self.reencrypt_entry(entry, cache)
                    os.replace(staging, target)
                except BaseException:
                    shutil.rmtree(staging, ignore_errors=True)
                    raise
                if not keep_source:
                    shutil.rmtree(source)
        else:
            if needs_reencrypt:
                data = self.decrypt_bytes(source)
                self.encrypt_to_file(
                    target, data, self.recipients(self._folder_of(new_clean))
                )
                if not keep_source:
                    os.remove(source)
            elif keep_source:
                with open(source, "rb") as handle:
                    atomic_write(target, handle.read())
            else:
                os.replace(source, target)
        paths = [relative_target]
        if not keep_source:
            paths.insert(0, self.relative(source))
        return old_clean, new_clean, paths

    @locked
    def move_path(self, old_path, new_path, force=False):
        """
        Move or rename an entry or folder, re-encrypting it when the
        destination has other recipients, like 'pass mv'.

        :param old_path: Source path relative to the store root.
        :param new_path: Destination path; an existing folder or a path
                         ending in '/' moves the source into it.
        :param force: Overwrite an existing destination entry.
        :return: The destination path relative to the store root.
        """
        old_clean, new_clean, paths = self._transfer(
            old_path, new_path, force, keep_source=False
        )
        self.git_commit(paths, f"Rename {old_clean} to {new_clean}.")
        return new_clean

    @locked
    def copy_path(self, old_path, new_path, force=False):
        """
        Copy an entry or folder, re-encrypting it when the destination has
        other recipients, like 'pass cp'.

        :param old_path: Source path relative to the store root.
        :param new_path: Destination path, see move_path.
        :param force: Overwrite an existing destination entry.
        :return: The destination path relative to the store root.
        """
        old_clean, new_clean, paths = self._transfer(
            old_path, new_path, force, keep_source=True
        )
        self.git_commit(paths, f"Copy {old_clean} to {new_clean}.")
        return new_clean

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
    def init(self, gpg_ids, folder="", progress=None):
        """
        Set the recipients of a (sub)store and re-encrypt its entries, like
        'pass init'.

        :param gpg_ids: List of gpg ids to encrypt for.
        :param folder: Folder relative to the store root, '' for the root.
        :param progress: Optional callable(done, total) for re-encryption.
        """
        if not gpg_ids:
            raise StoreError("At least one key is needed")
        clean = self.clean_path(folder)
        absolute = self.absolute(clean)
        gpg_id_path = os.path.join(absolute, GPG_ID)
        relative_id = f"{clean}/{GPG_ID}" if clean else GPG_ID
        for path in (gpg_id_path, gpg_id_path + ".sig"):
            if is_link(path):
                raise StoreError(f"{path} is a symbolic link")
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
        joined = ", ".join(gpg_ids)
        self.git_commit([relative_id, relative_id + ".sig"], f"Set GPG id to {joined}.")
        if not has_entries:
            return
        failure = None
        try:
            self.reencrypt(clean, progress=progress, commit=False)
        except (OSError, StoreError) as error:
            failure = error
        # Commit what was re-encrypted, also when a later entry failed, so
        # the store and its history agree.
        self.git_commit(
            [clean or "."], f"Reencrypt password store using new GPG id {joined}."
        )
        if failure is not None:
            raise failure

    def write_gpg_id(self, gpg_id_path, folder, gpg_ids):
        """
        Write a recipient list: signed and with a generation header when
        signing keys are configured, a plain list like pass writes otherwise.

        :param gpg_id_path: Path of the .gpg-id file.
        :param folder: Its folder relative to the store root.
        :param gpg_ids: The recipients.
        """
        signature = gpg_id_path + ".sig"
        if not self.signer.enabled:
            if os.path.lexists(signature):
                raise StoreError(
                    f"The recipient list of /{folder} is signed. Configure the "
                    "signing key (Settings, the profile, or "
                    "PASSWORD_STORE_SIGNING_KEY) to change its recipients; "
                    "an unsigned list would break the folder for everyone "
                    "who verifies it."
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
        generation = self.signer.next_generation(gpg_id_path, on_disk)
        contents = with_header(generation, folder, gpg_ids).encode("utf-8")
        signed = self.signer.sign(contents)

        def write():
            atomic_write(gpg_id_path, contents)
            atomic_write(signature, signed)

        self.signer.store_written(gpg_id_path, contents, generation, write)

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
        entries = list(self.iter_entries(folder))
        done = 0
        cache = {}
        for entry in entries:
            if cancelled and cancelled():
                break
            self.reencrypt_entry(entry, cache)
            done += 1
            if progress:
                progress(done, len(entries))
        if commit and done:
            self.git_commit(
                [self.clean_path(folder) or "."],
                f"Reencrypt {self.clean_path(folder) or 'password store'}.",
            )
        return done

    # Search

    def search(self, pattern, folder="", progress=None, cancelled=None):
        """
        Search the decrypted contents of all entries, like 'pass grep'.

        :param pattern: A regular expression (Python syntax).
        :param folder: Folder to search in.
        :param progress: Optional callable(done, total).
        :param cancelled: Optional callable returning True to stop early.
        :return: Dict of entry path to list of matching lines.
        :raises re.error: when the pattern is invalid.
        """
        regex = re.compile(pattern, re.IGNORECASE)
        entries = list(self.iter_entries(folder))
        results = {}
        for done, entry in enumerate(entries, 1):
            if cancelled and cancelled():
                break
            try:
                content = self.get_key(entry)
            except (OSError, StoreError):
                continue
            matches = [line for line in content.splitlines() if regex.search(line)]
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
            raise CommitError(f"The change was made, but git commit failed: {output}")

    def busy(self):
        """
        :return: True while another thread is changing the store or running
                 git pull or push on it.
        """
        if not self.lock.acquire(blocking=False):  # pylint: disable=consider-using-with
            return True
        self.lock.release()
        return False

    @locked
    def pull(self):
        """
        Pull from the remote, never while the store is being changed.

        :return: Tuple of (success, output).
        """
        return git_utils.git_pull(self.store_dir)

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
            raise StoreError(f"git init failed: {output}")
        self.git_commit(["."], "Add current contents of password store.")
