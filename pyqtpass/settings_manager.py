"""
This module provides a SettingsManager class to manage application settings
using the QSettings interface from the PyQt6.QtCore module. It allows for storing
and retrieving various settings such as window geometry, splitter sizes, and
boolean flags for application behavior.
"""

import os
import string
import sys

from PyQt6.QtCore import QSettings, QByteArray

DEFAULT_CUSTOM_CHARS = string.ascii_letters + string.digits + string.punctuation
DEFAULT_STORE_DIR = "~/.password-store"

# Portable mode, like QtPass's qtpass.ini: this file next to the program
# holds the settings instead of the platform's settings store.
PORTABLE_INI = "pyqtpass.ini"

# When to copy the password, QtPass's ClipBoardType: never (no copy buttons),
# always when an entry is shown, or on demand with the copy buttons.
CLIPBOARD_NEVER, CLIPBOARD_ALWAYS, CLIPBOARD_ON_DEMAND = range(3)

# Settings a profile can override; None in a profile means "as configured".
PROFILE_OVERRIDES = ("use_git", "auto_push", "git_pull_on_start")


def profile_options(value):
    """
    Normalise a stored profile: older versions stored only its path.

    :param value: The stored profile, a path or a dict.
    :return: Dict with 'path', 'signing_key' and the PROFILE_OVERRIDES.
    """
    if isinstance(value, dict):
        options = {
            "path": str(value.get("path") or ""),
            "signing_key": str(value.get("signing_key") or ""),
        }
        for key in PROFILE_OVERRIDES:
            override = value.get(key)
            if isinstance(override, str):
                override = {"true": True, "false": False}.get(override.lower())
            options[key] = override if isinstance(override, bool) else None
        return options
    options = {"path": str(value or ""), "signing_key": ""}
    options.update({key: None for key in PROFILE_OVERRIDES})
    return options


def program_dir():
    """
    :return: The folder holding the program: the executable of a frozen
             build, else the script that started PyQtPass.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(sys.argv[0] or sys.executable))


def portable_ini():
    """
    :return: The path of the portable settings file when it exists, else None.
    """
    path = os.path.join(program_dir(), PORTABLE_INI)
    return path if os.path.isfile(path) else None


def open_settings():
    """
    :return: QSettings on the portable settings file when there is one, else
             on the platform's settings store.
    """
    path = portable_ini()
    if path:
        return QSettings(path, QSettings.Format.IniFormat)
    return QSettings("IJHack", "PyQtPass")


class SettingsManager:
    """
    The SettingsManager class encapsulates methods for saving and retrieving
    application settings. It uses QSettings for persistent storage.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "initialized", False):
            return
        self.initialized = True
        self.settings = open_settings()
        self.options = {
            "select_is_open": True,
            "close_is_hide": False,
            "splitter_sizes": [200, 400],
            "window_geometry": QByteArray,
            "window_state": QByteArray,
            "config_dialog_geometry": QByteArray,
            "always_on_top": False,
            "use_tray_icon": True,
            "start_minimized": False,
            "clipboard_mode": CLIPBOARD_ON_DEMAND,
            "autoclear_clipboard": True,
            "clipboard_timeout": 45,
            "hide_password": False,
            "hide_content": False,
            "autoclear_panel": False,
            "panel_timeout": 10,
            "password_length": 16,
            "password_charset": 0,
            "use_pwgen": False,
            "pwgen_executable": "",
            "avoid_capitals": False,
            "avoid_numbers": False,
            "less_random": False,
            "use_symbols": False,
            "use_git": True,
            "auto_push": True,
            "add_gpg_id": True,
            "git_pull_on_start": False,
            "profiles": {},
            "current_profile": "",
            "pass_store": "~/.password-store",
            "pass_signing_key": "",
            "use_pass": False,
            "pass_executable": "",
            "show_menu_bar": True,
            "use_selection": False,
            "use_monospace": True,
            "display_as_is": False,
            "no_line_wrapping": False,
            "use_otp": True,
            "use_qrencode": True,
            "use_template": False,
            "pass_template": "login\nurl",
            "template_all_fields": False,
            "custom_chars": DEFAULT_CUSTOM_CHARS,
            "use_grep_search": False,
            "show_process_output": False,
            "gpg_executable": "",
            "gpg_home": "",
            "ssh_auth_sock": "",
            "git_executable": "",
            "qrencode_executable": "",
        }
        self.load()

    def set(self, key, value):
        """
        Set that value
        """
        self.options[key] = value

    def get(self, key):
        """
        Get the option from settings
        """
        if key == "splitter_sizes":
            return self.get_splitter_sizes()

        return self.options.get(key)

    def get_splitter_sizes(self):
        """
        Retrieves the sizes of the splitters as a list of integers.

        Returns:
            list: The sizes of the splitters.
        """
        return [
            int(item)
            for item in self.settings.value("splitter_sizes", [200, 400], type=list)
        ]

    def load(self):
        """Load settings, coercing stored values back to their default types."""
        for key, default in self.options.items():
            value = self.settings.value(key)
            if value is None:
                continue
            if isinstance(default, bool):
                if isinstance(value, bool):
                    self.options[key] = value
                else:
                    self.options[key] = str(value).lower() in ("true", "1")
            elif isinstance(default, int):
                try:
                    self.options[key] = int(value)
                except (TypeError, ValueError):
                    pass
            elif isinstance(default, dict):
                if isinstance(value, dict):
                    self.options[key] = value
            else:
                self.options[key] = value
        self.load_clipboard_mode()

    def load_clipboard_mode(self):
        """
        Check the clipboard mode, or take it from the on/off setting that
        older versions stored: on is Always, off is On demand.
        """
        if self.settings.value("clipboard_mode") is None:
            always = self.settings.value("always_copy_to_clipboard")
            if always is not None:
                self.options["clipboard_mode"] = (
                    CLIPBOARD_ALWAYS
                    if str(always).lower() in ("true", "1")
                    else CLIPBOARD_ON_DEMAND
                )
        if self.options["clipboard_mode"] not in range(3):
            self.options["clipboard_mode"] = CLIPBOARD_ON_DEMAND

    def template_fields(self):
        """
        :return: The template field names when templates are in use.
        """
        if not self.get("use_template"):
            return []
        return [
            name.strip()
            for name in str(self.get("pass_template")).splitlines()
            if name.strip()
        ]

    def current_profile(self):
        """
        :return: The options of the selected profile, or None.
        """
        profiles = self.get("profiles") or {}
        current = self.get("current_profile")
        if current and current in profiles:
            return profile_options(profiles[current])
        return None

    def store_dir(self):
        """
        :return: The store of the selected profile, or the configured store.
        """
        profile = self.current_profile()
        if profile and profile["path"]:
            return profile["path"]
        return self.get("pass_store") or DEFAULT_STORE_DIR

    def effective(self, key):
        """
        :param key: A setting a profile can override.
        :return: The profile's value when it sets one, else the global one.
        """
        profile = self.current_profile()
        if profile is not None and profile.get(key) is not None:
            return profile[key]
        return self.get(key)

    def signing_keys(self):
        """
        :return: The fingerprints that sign .gpg-id files for the current
                 store: the profile's, the configured ones, or those in
                 PASSWORD_STORE_SIGNING_KEY.
        """
        profile = self.current_profile()
        keys = profile["signing_key"] if profile and profile["signing_key"] else ""
        keys = keys or str(self.get("pass_signing_key") or "")
        # Like pass, PASSWORD_STORE_SIGNING_KEY applies when nothing is set.
        keys = keys or os.environ.get("PASSWORD_STORE_SIGNING_KEY", "")
        return keys.split()

    def generation_record_path(self):
        """
        :return: Where the generations of signed recipient lists are kept,
                 next to the settings.
        """
        return os.path.join(
            os.path.dirname(self.settings.fileName()),
            "PyQtPass-gpgid-generations.json",
        )

    def save(self):
        """Save settings"""
        for key, value in self.options.items():
            if isinstance(value, type):
                continue  # placeholder default, nothing stored yet
            self.settings.setValue(key, value)
        self.settings.sync()
