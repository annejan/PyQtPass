"""
Password generation with pwgen, like QtPass offers it. The built-in
generator is used when pwgen is turned off, missing or fails.
"""

import shutil

from pyqtpass import executor


def find_pwgen(configured=""):
    """
    :param configured: The configured pwgen executable, '' to search.
    :return: The pwgen executable, or '' when it is not found.
    """
    return configured or shutil.which("pwgen") or ""


def pwgen_args(settings, length):
    """
    The pwgen command line QtPass uses: one password of the given length.

    :param settings: The SettingsManager.
    :param length: The password length.
    :return: The arguments after the program name.
    """
    args = ["-1"]
    if not settings.get("less_random"):
        args.append("--secure")
    args.append("--no-capitalize" if settings.get("avoid_capitals") else "--capitalize")
    args.append("--no-numerals" if settings.get("avoid_numbers") else "--numerals")
    if settings.get("use_symbols"):
        args.append("--symbols")
    args.append(str(int(length)))
    return args


def pwgen_password(settings, length):
    """
    :param settings: The SettingsManager.
    :param length: The password length.
    :return: A password from pwgen, or '' when pwgen is not used or fails.
    """
    if not settings.get("use_pwgen"):
        return ""
    program = find_pwgen(settings.get("pwgen_executable"))
    if not program:
        return ""
    returncode, stdout, _ = executor.run(
        [program, *pwgen_args(settings, length)], timeout=30
    )
    lines = stdout.decode(errors="replace").splitlines()
    if returncode != 0 or not lines or len(lines[0]) != int(length):
        return ""
    return lines[0]
