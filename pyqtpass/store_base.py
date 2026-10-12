"""
What the password store modules share: their errors, names, and the lock
that keeps changes to one store from running at the same time.
"""

import functools
import os
import threading

GPG_EXT = ".gpg"
GPG_ID = ".gpg-id"
# Folders a move or copy is put together in before taking its place.
STAGING_PREFIX = ".pyqtpass-move-"


class StoreError(Exception):
    """Raised when a password store operation fails."""


class CommitError(StoreError):
    """
    The change itself was made, but committing it to git failed; the
    message says so, and the change is not to be retried.
    """

    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output or message


_locks_by_path = {}
_locks_by_folder = {}
_locks_guard = threading.Lock()


def store_lock(store_dir):
    """
    The lock shared by every PasswordStore for a directory, so a store
    reopened with new settings still waits for a pull running on the old
    one. It is looked up each time, by the folder itself once it exists
    (device and inode), so two spellings of it on a case-insensitive volume,
    or a link to it made later, share the lock; before that, by its path.

    :param store_dir: A store directory.
    :return: The lock.
    """
    path_key = os.path.normcase(os.path.realpath(store_dir))
    try:
        status = os.stat(store_dir)
        folder_key = (status.st_dev, status.st_ino)
    except OSError:
        folder_key = None
    with _locks_guard:
        lock = _locks_by_folder.get(folder_key) if folder_key else None
        if lock is None:
            lock = _locks_by_path.setdefault(path_key, threading.RLock())
            if folder_key:
                _locks_by_folder[folder_key] = lock
        return lock


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
