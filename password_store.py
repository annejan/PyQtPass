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
import tempfile

import executor
import git_utils
from gpg_utils import parse_gpg_id_lines, which_gpg

GPG_EXT = ".gpg"
GPG_ID = ".gpg-id"


class StoreError(Exception):
    """Raised when a password store operation fails."""


class PasswordStore:
    """
    A pass compatible password store rooted at store_dir.
    """

    # pylint: disable=too-many-public-methods

    def __init__(self, store_dir, gpg_bin=None, use_git=True):
        self.store_dir = os.path.abspath(os.path.expanduser(store_dir))
        self.gpg_bin = gpg_bin or which_gpg()
        self.use_git = use_git

    # Paths

    def is_initialised(self):
        """
        :return: True when the store root has a .gpg-id file.
        """
        root_id = os.path.join(self.store_dir, GPG_ID)
        return os.path.isfile(root_id) and not os.path.islink(root_id)

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
            if os.path.islink(current):
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
        return os.path.isdir(absolute) and not os.path.islink(absolute)

    def is_entry(self, path):
        """
        :param path: Path relative to the store root.
        :return: True when path is an entry of the store.
        """
        try:
            absolute = self.entry_file(path)
        except StoreError:
            return False
        return os.path.isfile(absolute) and not os.path.islink(absolute)

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
            if os.path.islink(full):
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
                    and not os.path.islink(os.path.join(current, name))
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
                    and not os.path.islink(full)
                ):
                    yield self.relative(full)[: -len(GPG_EXT)]

    def list_folders(self):
        """
        :return: All folders of the store relative to the root, '' included.
        """
        return [self.relative(current) for current, _, _ in self._walk()]

    # Recipients

    def recipients(self, folder=""):
        """
        Find the gpg ids for a folder from the nearest .gpg-id file.

        :param folder: Folder relative to the store root.
        :return: List of gpg ids.
        :raises StoreError: when no .gpg-id applies to the folder.
        """
        parts = [part for part in self.clean_path(folder).split("/") if part]
        while True:
            candidate = os.path.join(self.store_dir, *parts, GPG_ID)
            if os.path.isfile(candidate) and not os.path.islink(candidate):
                with open(candidate, "r", encoding="utf-8") as gpg_id_file:
                    ids = parse_gpg_id_lines(gpg_id_file.read())
                if ids:
                    return ids
            if not parts:
                raise StoreError(
                    "You must initialise the password store first "
                    "(no .gpg-id file found)"
                )
            parts.pop()

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
        return stdout.decode("utf-8", errors="replace")

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

    def create_folder(self, path):
        """
        Create a folder; it inherits the recipients of its parent.

        :param path: Folder path relative to the store root.
        """
        absolute = self.absolute(path)
        if os.path.exists(absolute):
            raise FileExistsError(f"{path} already exists")
        os.makedirs(absolute)

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
        if os.path.islink(folder) or os.path.islink(entry):
            link = folder if os.path.islink(folder) else entry
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
        if os.path.lexists(target) and not force:
            raise FileExistsError(f"{new_clean} already exists")
        self.absolute(self._folder_of(new_clean))
        return old_clean, new_clean, source, target, relative_target

    def _recipients_or_none(self, path, is_folder):
        try:
            return self.recipients(path if is_folder else self._folder_of(path))
        except StoreError:
            return None

    def _reencrypt_if_needed(self, old_recipients, new_clean, target):
        new_recipients = self._recipients_or_none(new_clean, os.path.isdir(target))
        if old_recipients is None or old_recipients != new_recipients:
            if os.path.isdir(target):
                self.reencrypt(new_clean, commit=False)
            else:
                self.reencrypt_entry(new_clean)

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
        old_clean, new_clean, source, target, relative_target = self._source_and_target(
            old_path, new_path, force
        )
        old_recipients = self._recipients_or_none(old_clean, os.path.isdir(source))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.replace(source, target)
        self._reencrypt_if_needed(old_recipients, new_clean, target)
        relative_source = self.relative(source)
        self.git_commit(
            [relative_source, relative_target],
            f"Rename {old_clean} to {new_clean}.",
        )
        return new_clean

    def copy_path(self, old_path, new_path, force=False):
        """
        Copy an entry or folder, re-encrypting it when the destination has
        other recipients, like 'pass cp'.

        :param old_path: Source path relative to the store root.
        :param new_path: Destination path, see move_path.
        :param force: Overwrite an existing destination entry.
        :return: The destination path relative to the store root.
        """
        old_clean, new_clean, source, target, relative_target = self._source_and_target(
            old_path, new_path, force
        )
        old_recipients = self._recipients_or_none(old_clean, os.path.isdir(source))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.isdir(source):
            shutil.copytree(
                source,
                target,
                symlinks=True,
                ignore=lambda folder, names: [
                    name for name in names if os.path.islink(os.path.join(folder, name))
                ],
            )
        else:
            shutil.copyfile(source, target)
        self._reencrypt_if_needed(old_recipients, new_clean, target)
        self.git_commit([relative_target], f"Copy {old_clean} to {new_clean}.")
        return new_clean

    # Recipients management

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
        os.makedirs(absolute, exist_ok=True)
        gpg_id_path = os.path.join(absolute, GPG_ID)
        if os.path.islink(gpg_id_path):
            raise StoreError(f"{gpg_id_path} is a symbolic link")
        atomic_write(gpg_id_path, ("\n".join(gpg_ids) + "\n").encode("utf-8"))
        relative_id = f"{clean}/{GPG_ID}" if clean else GPG_ID
        joined = ", ".join(gpg_ids)
        self.git_commit([relative_id], f"Set GPG id to {joined}.")
        if next(self.iter_entries(clean), None) is not None:
            self.reencrypt(clean, progress=progress, commit=False)
            self.git_commit(
                [clean or "."],
                f"Reencrypt password store using new GPG id {joined}.",
            )

    def reencrypt_entry(self, path):
        """
        Re-encrypt one entry for the recipients of its folder.

        :param path: Entry path relative to the store root.
        """
        clean = self.clean_path(path)
        absolute = self.entry_file(clean)
        data = self.decrypt_file(absolute)
        self.encrypt_to_file(absolute, data, self.recipients(self._folder_of(clean)))

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
        for entry in entries:
            if cancelled and cancelled():
                break
            self.reencrypt_entry(entry)
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
            raise StoreError(f"git commit failed: {output}")

    def init_git(self):
        """
        Put the store under git and commit its current contents.
        """
        success, output = git_utils.git_init(self.store_dir)
        if not success:
            raise StoreError(f"git init failed: {output}")
        self.git_commit(["."], "Add current contents of password store.")


def atomic_write(path, data, mode=0o600):
    """
    Write bytes to a file atomically: a temporary file next to it is
    written, flushed and renamed over the target.

    :param path: The file to write.
    :param data: The bytes to write.
    :param mode: Permission bits for the new file.
    """
    directory = os.path.dirname(path)
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".pyqtpass-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise
