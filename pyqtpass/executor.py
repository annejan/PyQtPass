"""
Runs the external programs PyQtPass depends on (gpg, git, qrencode).

Every command goes through run() so that the process output panel can show
what was executed and what it said, like the QtPass process output panel.
Listeners are plain callables so this module does not depend on Qt and can
be used from worker threads; the GUI marshals the calls to its own thread.
"""

import os
import signal
import subprocess
import threading
import time

from pyqtpass import environment

_listeners = []

# Options whose value must never be shown in the process output panel.
SECRET_OPTIONS = ("--passphrase",)


def add_listener(listener):
    """
    Register a callable that receives (label, returncode, output) for every
    command that is run.

    :param listener: The callable to register.
    """
    if listener not in _listeners:
        _listeners.append(listener)


def remove_listener(listener):
    """
    Unregister a listener added with add_listener.

    :param listener: The callable to unregister.
    """
    if listener in _listeners:
        _listeners.remove(listener)


def command_label(args):
    """
    Build a printable label for a command, hiding secret option values.

    :param args: The command and its arguments.
    :return: The command line as a string.
    """
    shown = []
    hide_next = False
    for arg in args:
        if hide_next:
            shown.append("***")
            hide_next = False
            continue
        if arg in SECRET_OPTIONS:
            hide_next = True
        elif any(arg.startswith(option + "=") for option in SECRET_OPTIONS):
            arg = arg.split("=", 1)[0] + "=***"
        shown.append(arg)
    return " ".join(shown)


def _notify(args, returncode, output):
    label = command_label(args)
    for listener in list(_listeners):
        try:
            listener(label, returncode, output)
        except Exception:  # pylint: disable=broad-exception-caught
            # A broken listener must never break the command itself.
            pass


_running = set()
_running_lock = threading.Lock()
# Set by terminate_all: a command a worker starts after that is refused,
# so nothing new runs once quitting has ended the running ones.
_refusing = threading.Event()

# On POSIX every command gets a session of its own: it has no controlling
# terminal to ask on (git and ssh fail instead of waiting on a hidden tty),
# and on timeout or quit the whole group, an ssh grandchild included, ends.
_NEW_SESSION = os.name == "posix"


def _end(process, sig=signal.SIGTERM):
    """Stop a process and, on POSIX, the rest of its group."""
    try:
        if _NEW_SESSION:
            os.killpg(process.pid, sig)
        elif sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def terminate_all(grace=2.0):
    """
    Stop every running command, used when quitting while work is running.

    :param grace: Seconds to wait after SIGTERM before killing.
    """
    with _running_lock:
        _refusing.set()
        processes = list(_running)
    for process in processes:
        _end(process)
    deadline = time.monotonic() + grace
    for process in processes:
        try:
            process.wait(max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _end(process, getattr(signal, "SIGKILL", signal.SIGTERM))


def allow_commands():
    """Start running commands again after terminate_all (for tests)."""
    _refusing.clear()


def run(
    args, input_data=None, timeout=None, cwd=None, log_stdout=False, env=None
):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """
    Run a command and report it to the listeners.

    Standard output is only passed to the listeners when log_stdout is True,
    so decrypted passwords never end up in the process output panel.

    :param args: The command and its arguments.
    :param input_data: Optional bytes to write to standard input; without it
                       standard input is empty.
    :param timeout: Optional timeout in seconds.
    :param cwd: Optional working directory.
    :param log_stdout: Whether standard output may be shown to listeners.
    :param env: Optional extra environment variables.
    :return: Tuple of (returncode, stdout bytes, stderr bytes); returncode is
             -1 when the program could not be started or timed out.
    """
    try:
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            environment.wsl_command(args),
            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env={**os.environ, **env} if env else None,
            start_new_session=_NEW_SESSION,
        )
    except OSError as error:
        _notify(args, -1, str(error))
        return -1, b"", str(error).encode()
    with _running_lock:
        if _refusing.is_set():
            _end(process, getattr(signal, "SIGKILL", signal.SIGTERM))
        _running.add(process)
    try:
        stdout, stderr = process.communicate(input_data, timeout=timeout)
    except subprocess.TimeoutExpired:
        _end(process, getattr(signal, "SIGKILL", signal.SIGTERM))
        try:
            # A descendant that left the group can keep the pipes open.
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
        message = f"{args[0]} did not finish within {timeout} seconds"
        _notify(args, -1, message)
        return -1, b"", message.encode()
    finally:
        with _running_lock:
            _running.discard(process)
    shown = stderr
    if log_stdout:
        shown = stdout + stderr
    _notify(args, process.returncode, shown.decode(errors="replace").rstrip())
    return process.returncode, stdout, stderr
