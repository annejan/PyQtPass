"""
File system helpers for the password store.

A symbolic link (or, on Windows, an NTFS junction) inside the store is not
part of it: a shared repository can carry one pointing anywhere. Files are
written atomically, so a failure never leaves a half written file behind.
"""

import os
import tempfile


def is_link(path):
    """
    :param path: A file system path.
    :return: True when path is a symbolic link or an NTFS junction.
    """
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)  # Python 3.12+
    if isjunction is not None:
        return isjunction(path)
    if os.name == "nt":  # pragma: no cover - Windows before Python 3.12
        try:
            return bool(os.lstat(path).st_reparse_tag)
        except (OSError, AttributeError):
            return False
    return False


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
