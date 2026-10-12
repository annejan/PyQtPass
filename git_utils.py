"""
Git helper functions for PyQtPass.

These wrap the git command line client, the same way QtPass does, so that
the password store can be versioned and synchronised with a remote repository.
"""

import os
import shutil

import executor

_git_binary = {"path": ""}


def set_git_executable(path):
    """
    Configure the git executable, '' to look it up on the PATH.

    :param path: Path or name of the git executable.
    """
    _git_binary["path"] = path or ""


def git_executable():
    """
    :return: The configured git executable or 'git' from the PATH.
    """
    return _git_binary["path"] or shutil.which("git") or "git"


def is_git_repo(path):
    """
    Check whether the given directory is a git repository.

    :param path: Directory to check, may contain '~'.
    :return: True when path contains a .git directory.
    """
    return os.path.isdir(os.path.join(os.path.expanduser(path), ".git"))


def run_git(path, *args, timeout=120):
    """
    Run a git command inside the given directory.

    :param path: Directory to run git in, may contain '~'.
    :param args: The git subcommand and its arguments.
    :param timeout: Seconds before the command is given up on.
    :return: Tuple of (success, combined output).
    """
    returncode, stdout, stderr = executor.run(
        [git_executable(), "-C", os.path.expanduser(path)] + list(args),
        timeout=timeout,
        log_stdout=True,
    )
    output = (stdout + stderr).decode(errors="replace").strip()
    return returncode == 0, output


def has_remote(path):
    """
    Check whether the git repository at path has a remote configured.

    :param path: Directory of the git repository.
    :return: True when at least one remote is configured.
    """
    success, output = run_git(path, "remote")
    return success and output != ""


def git_pull(path):
    """
    Pull the latest changes from the default remote.

    :param path: Directory of the git repository.
    :return: Tuple of (success, combined output).
    """
    return run_git(path, "pull")


def git_push(path):
    """
    Push local changes to the default remote.

    :param path: Directory of the git repository.
    :return: Tuple of (success, combined output).
    """
    return run_git(path, "push")


def git_init(path):
    """
    Turn a directory into a git repository.

    :param path: Directory to initialise.
    :return: Tuple of (success, combined output).
    """
    return run_git(path, "init")


def git_commit_paths(path, paths, message):
    """
    Stage the given paths (additions, changes and removals) and commit them.

    Paths that neither exist nor are tracked are skipped, and nothing is
    committed when staging did not change anything.

    :param path: Directory of the git repository.
    :param paths: Paths relative to the repository to stage.
    :param message: The commit message.
    :return: Tuple of (success, combined output).
    """
    root = os.path.expanduser(path)
    paths = [
        name
        for name in paths
        if os.path.lexists(os.path.join(root, name))
        or run_git(path, "ls-files", "--", name)[1]
    ]
    if not paths:
        return True, ""
    success, output = run_git(path, "add", "-A", "--", *paths)
    if not success:
        return success, output
    unchanged, _ = run_git(path, "diff", "--cached", "--quiet")
    if unchanged:
        return True, ""
    return run_git(path, "commit", "-m", message)


def has_unmerged_files(path):
    """
    Check whether a pull left files with merge conflicts behind.

    :param path: Directory of the git repository.
    :return: True when unmerged files exist or the check itself failed.
    """
    success, output = run_git(path, "ls-files", "--unmerged")
    return not success or output != ""
