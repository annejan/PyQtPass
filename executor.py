"""
Runs the external programs PyQtPass depends on (gpg, git, qrencode).

Every command goes through run() so that the process output panel can show
what was executed and what it said, like the QtPass process output panel.
Listeners are plain callables so this module does not depend on Qt and can
be used from worker threads; the GUI marshals the calls to its own thread.
"""

import subprocess

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


def run(args, input_data=None, timeout=None, cwd=None, log_stdout=False):
    """
    Run a command and report it to the listeners.

    Standard output is only passed to the listeners when log_stdout is True,
    so decrypted passwords never end up in the process output panel.

    :param args: The command and its arguments.
    :param input_data: Optional bytes to write to standard input.
    :param timeout: Optional timeout in seconds.
    :param cwd: Optional working directory.
    :param log_stdout: Whether standard output may be shown to listeners.
    :return: Tuple of (returncode, stdout bytes, stderr bytes); returncode is
             -1 when the program could not be started or timed out.
    """
    try:
        result = subprocess.run(
            list(args),
            input=input_data,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        _notify(args, -1, str(error))
        return -1, b"", str(error).encode()
    shown = result.stderr
    if log_stdout:
        shown = result.stdout + result.stderr
    _notify(args, result.returncode, shown.decode(errors="replace").rstrip())
    return result.returncode, result.stdout, result.stderr
