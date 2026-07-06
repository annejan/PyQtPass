"""
Git helper functions for PyQtPass.

These wrap the git command line client, the same way QtPass does, so that
the password store can be synchronised with a remote repository.
"""

import os
import subprocess


def is_git_repo(path):
    """
    Check whether the given directory is a git repository.

    :param path: Directory to check, may contain '~'.
    :return: True when path contains a .git directory.
    """
    return os.path.isdir(os.path.join(os.path.expanduser(path), ".git"))


def run_git(path, *args):
    """
    Run a git command inside the given directory.

    :param path: Directory to run git in, may contain '~'.
    :param args: The git subcommand and its arguments.
    :return: Tuple of (success, combined output).
    """
    try:
        result = subprocess.run(
            ["git", "-C", os.path.expanduser(path)] + list(args),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


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
