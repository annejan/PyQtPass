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
    :return: True when path holds a .git directory, or the .git file of a
             worktree or submodule.
    """
    return os.path.exists(os.path.join(os.path.expanduser(path), ".git"))


# The app's own git calls run without hooks or an fsmonitor command from the
# repository's configuration: whoever can write the store's .git/config could
# otherwise make every save run a program. Pull and push keep the user's
# setup, since those are what hooks there are usually for.
NO_HOOKS = ["-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false"]


def run_git(path, *args, timeout=120, hooks=True):
    """
    Run a git command inside the given directory.

    :param path: Directory to run git in, may contain '~'.
    :param args: The git subcommand and its arguments.
    :param timeout: Seconds before the command is given up on.
    :param hooks: Allow repository hooks and fsmonitor; False for the
                  app's own bookkeeping.
    :return: Tuple of (success, combined output).
    """
    prefix = [] if hooks else NO_HOOKS
    returncode, stdout, stderr = executor.run(
        [git_executable(), *prefix, "-C", os.path.expanduser(path)] + list(args),
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
    return run_git(path, "init", hooks=False)


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
        or run_git(path, "ls-files", "--", name, hooks=False)[1]
    ]
    if not paths:
        return True, ""
    success, output = run_git(path, "add", "-A", "--", *paths, hooks=False)
    if not success:
        return success, output
    unchanged, _ = run_git(
        path, "diff", "--cached", "--quiet", "--", *paths, hooks=False
    )
    if unchanged:
        return True, ""
    # Only these paths: whatever else the user staged stays staged.
    return run_git(path, "commit", "-m", message, "--", *paths, hooks=False)


def has_identity(path):
    """
    Check that git knows who commits, before anything is written that
    would then fail to be committed.

    :param path: A directory inside (or for) the repository.
    :return: Tuple of (success, git's complaint).
    """
    return run_git(path, "var", "GIT_AUTHOR_IDENT", hooks=False)


def has_unmerged_files(path):
    """
    Check whether a pull left files with merge conflicts behind.

    :param path: Directory of the git repository.
    :return: True when unmerged files exist or the check itself failed.
    """
    success, output = run_git(path, "ls-files", "--unmerged")
    return not success or output != ""
