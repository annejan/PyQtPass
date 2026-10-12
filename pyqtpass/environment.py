"""
The environment the external programs run in, like QtPass sets it up:

- a GnuPG home other than the default one (GNUPGHOME);
- an ssh agent for git over ssh when the desktop session did not provide
  one (SSH_AUTH_SOCK): the configured socket, else the gpg-agent's ssh
  socket when that agent answers, else on macOS the launchd one;
- programs inside the Windows Subsystem for Linux: a program configured as
  'wsl gpg2' runs as 'wsl --exec gpg2 ...', with Windows paths in its
  arguments translated to /mnt/<drive>/... paths.
"""

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys

from pyqtpass.i18n import translate

# The values variables had before this module set them, so that clearing a
# setting restores them instead of keeping the last configured one.
_replaced = {}
_probed = {}

WSL_PREFIX = "wsl "
# Wrapping only makes sense where wsl.exe exists; tests switch it on.
WSL_ENABLED = os.name == "nt"
_WINDOWS_PATH = re.compile(r"^([A-Za-z]):[\\/](.*)$", re.DOTALL)


def _set(name, value):
    if name not in _replaced:
        _replaced[name] = os.environ.get(name)
    os.environ[name] = value


def _restore(name):
    if name not in _replaced:
        return
    previous = _replaced.pop(name)
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


def apply_gnupg_home(path):
    """
    Use another GnuPG home for every gpg run, or the session's own.

    :param path: The GnuPG home folder, '' for the default.
    :return: A problem to tell the user about, or ''.
    """
    path = os.path.expanduser(path or "")
    if not path:
        _restore("GNUPGHOME")
        return ""
    if not os.path.isdir(path):
        _restore("GNUPGHOME")
        return translate(
            "Environment",
            "The GnuPG home folder {} does not exist; using the default one.",
        ).format(path)
    _set("GNUPGHOME", path)
    return ""


def is_socket(path):
    """:return: True when path is a Unix socket."""
    try:
        return stat.S_ISSOCK(os.stat(path).st_mode)
    except (OSError, ValueError):
        return False


def _output(args, env=None):
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=5,
            check=False,
            env={**os.environ, **env} if env else None,
        )
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return result.returncode, result.stdout.decode(errors="replace").strip()


def gpg_agent_ssh_socket():
    """
    :return: The gpg-agent's ssh socket when an agent answers on it, or ''.
    """
    gpgconf = shutil.which("gpgconf")
    if not gpgconf:
        return ""
    returncode, socket = _output([gpgconf, "--list-dirs", "agent-ssh-socket"])
    if returncode != 0 or not is_socket(socket):
        return ""
    ssh_add = shutil.which("ssh-add")
    if ssh_add:
        # 0: keys listed, 1: an agent without keys; anything else: no agent.
        returncode, _ = _output([ssh_add, "-l"], env={"SSH_AUTH_SOCK": socket})
        if returncode not in (0, 1):
            return ""
    return socket


def launchd_ssh_socket():
    """:return: The ssh agent socket launchd provides on macOS, or ''."""
    if sys.platform != "darwin":
        return ""
    returncode, socket = _output(["launchctl", "getenv", "SSH_AUTH_SOCK"])
    return socket if returncode == 0 and is_socket(socket) else ""


def apply_ssh_auth_sock(configured):
    """
    Give git an ssh agent when the session has none.

    :param configured: The socket from the settings, '' to find one.
    :return: The socket in use, or ''.
    """
    if "SSH_AUTH_SOCK" not in _replaced and os.environ.get("SSH_AUTH_SOCK"):
        # The session's own agent wins, like in QtPass.
        return os.environ["SSH_AUTH_SOCK"]
    socket = os.path.expanduser(configured or "")
    if not socket:
        if "found" not in _probed:
            _probed["found"] = gpg_agent_ssh_socket() or launchd_ssh_socket()
        socket = _probed["found"]
    if socket:
        _set("SSH_AUTH_SOCK", socket)
    else:
        _restore("SSH_AUTH_SOCK")
    return socket


def wsl_path(arg):
    """
    :param arg: A command-line argument.
    :return: The argument, a Windows path in it turned into a WSL path.
    """
    match = _WINDOWS_PATH.match(arg)
    if not match:
        return arg
    rest = match.group(2).replace("\\", "/")
    return f"/mnt/{match.group(1).lower()}/{rest}"


def wsl_command(args):
    """
    :param args: A command whose program may be configured as 'wsl <program>'.
    :return: The command to start, run through wsl --exec when needed.
    """
    args = list(args)
    if not (WSL_ENABLED and args and args[0].lower().startswith(WSL_PREFIX)):
        return args
    program = shlex.split(args[0][len(WSL_PREFIX) :])
    return ["wsl", "--exec", *program, *(wsl_path(arg) for arg in args[1:])]


def program_exists(program):
    """
    :param program: A program name or path, possibly 'wsl <program>'.
    :return: True when it can be started.
    """
    if WSL_ENABLED and program.lower().startswith(WSL_PREFIX):
        return shutil.which("wsl") is not None
    return shutil.which(program) is not None


def apply(settings):
    """
    Set up the environment from the settings.

    :param settings: The SettingsManager.
    :return: Problems to tell the user about.
    """
    problems = []
    problem = apply_gnupg_home(settings.get("gpg_home"))
    if problem:
        problems.append(problem)
    apply_ssh_auth_sock(settings.get("ssh_auth_sock"))
    return problems
