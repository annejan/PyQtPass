"""
A password store backend that runs the pass script itself, like QtPass's
"Use pass" option, for setups that rely on pass extensions, hooks or its
environment variables.

Listing and content search stay native (pass grep would follow links out
of the store), and every path is checked against links and traversal
before pass is asked anything.
"""

import os
import shutil

from pyqtpass import executor
from pyqtpass.fs_utils import is_link
from pyqtpass.password_store import GPG_EXT, PasswordStore, StoreError, locked


def find_pass(configured=""):
    """
    :param configured: A configured pass executable, may be ''.
    :return: The pass executable, or '' when it is not installed.
    """
    return configured or shutil.which("pass") or ""


class RealPassStore(PasswordStore):
    """
    A PasswordStore whose changes are made by the pass script.
    """

    # pylint: disable=too-many-public-methods

    def __init__(self, store_dir, pass_bin, **kwargs):
        super().__init__(store_dir, **kwargs)
        self.pass_bin = pass_bin

    def run_pass(self, *args, input_data=None):
        """
        Run pass on this store.

        :param args: The pass command and its arguments.
        :param input_data: Optional bytes for standard input.
        :return: The standard output as text.
        :raises StoreError: when pass fails.
        """
        env = {"PASSWORD_STORE_DIR": self.store_dir}
        if self.signer.enabled:
            env["PASSWORD_STORE_SIGNING_KEY"] = " ".join(self.signer.keys)
        if self.gpg_bin:
            env["PASSWORD_STORE_GPG"] = self.gpg_bin
        returncode, stdout, stderr = executor.run(
            [self.pass_bin, *args], input_data=input_data, timeout=300, env=env
        )
        if returncode != 0:
            raise StoreError(
                stderr.decode(errors="replace").strip() or f"pass {args[0]} failed"
            )
        return stdout.decode("utf-8", errors="replace")

    def get_key(self, path):
        clean = self.clean_path(path)
        if not os.path.isfile(self.entry_file(clean)):
            raise FileNotFoundError(f"{path} is not in the password store")
        if self.signer.enabled:
            # Refuse an untrusted recipient list here too, like the native
            # backend does before encrypting anything.
            self.recipients(self._folder_of(clean))
        return self.run_pass("show", "--", clean)

    @locked
    def set_key(self, path, key_data, force=False):
        clean = self.clean_path(path)
        absolute = self.entry_file(clean)
        if os.path.exists(absolute) and not force:
            raise FileExistsError(f"{clean} already exists")
        self.recipients(self._folder_of(clean))
        self.absolute(self._folder_of(clean))
        if not key_data.endswith("\n"):
            key_data += "\n"
        self.run_pass("insert", "-m", "-f", "--", clean, input_data=key_data.encode())

    @locked
    def remove_path(self, path, recursive=False):
        clean = self.clean_path(path)
        parent = self.absolute(self._folder_of(clean))
        name = clean.rsplit("/", 1)[-1]
        folder = os.path.join(parent, name)
        entry = folder + GPG_EXT
        if is_link(folder) or is_link(entry):
            # pass rm -rf would empty what the link points to.
            super().remove_path(clean, recursive)
            return
        if os.path.isdir(folder):
            if not recursive and os.listdir(folder):
                raise StoreError(f"{clean} is not empty")
        elif not os.path.isfile(entry):
            raise FileNotFoundError(f"{clean} is not in the password store")
        self.run_pass("rm", "-r", "-f", "--", clean)

    def _pass_copy_move(self, command, old_path, new_path, force):
        old_clean, new_clean, _, _, _ = self._source_and_target(
            old_path, new_path, force
        )
        self.run_pass(command, "-f", "--", old_clean, new_clean)
        return new_clean

    @locked
    def move_path(self, old_path, new_path, force=False):
        return self._pass_copy_move("mv", old_path, new_path, force)

    @locked
    def copy_path(self, old_path, new_path, force=False):
        return self._pass_copy_move("cp", old_path, new_path, force)

    @locked
    def init(self, gpg_ids, folder="", progress=None):
        if not gpg_ids:
            raise StoreError("At least one key is needed")
        clean = self.clean_path(folder)
        absolute = self.absolute(clean)
        for name in (".gpg-id", ".gpg-id.sig"):
            if is_link(os.path.join(absolute, name)):
                raise StoreError(f"{name} in {clean or '/'} is a symbolic link")
        args = ["init"]
        if clean:
            args += ["-p", clean]
        self.run_pass(*args, "--", *gpg_ids)

    @locked
    def reencrypt(self, folder="", progress=None, cancelled=None, commit=True):
        clean = self.clean_path(folder)
        ids, list_folder = self.recipient_list(clean)
        if list_folder != clean:
            # pass init would give the folder a list of its own.
            return super().reencrypt(clean, progress, cancelled, commit)
        count = len(list(self.iter_entries(clean)))
        self.init(ids, clean)
        return count

    def git_commit(self, paths, message):
        """pass commits its own changes."""

    @locked
    def init_git(self):
        self.run_pass("git", "init")
