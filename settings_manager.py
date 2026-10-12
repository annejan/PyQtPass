"""
This module provides a SettingsManager class to manage application settings
using the QSettings interface from the PyQt6.QtCore module. It allows for storing
and retrieving various settings such as window geometry, splitter sizes, and
boolean flags for application behavior.
"""

import string

from PyQt6.QtCore import QSettings, QByteArray

DEFAULT_CUSTOM_CHARS = string.ascii_letters + string.digits + string.punctuation


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
        self.settings = QSettings("IJHack", "PyQtPass")
        self.options = {
            "select_is_open": True,
            "close_is_hide": False,
            "splitter_sizes": [200, 400],
            "window_geometry": QByteArray,
            "window_state": QByteArray,
            "always_on_top": False,
            "use_tray_icon": True,
            "start_minimized": False,
            "always_copy_to_clipboard": False,
            "autoclear_clipboard": True,
            "clipboard_timeout": 45,
            "hide_password": False,
            "hide_content": False,
            "autoclear_panel": False,
            "panel_timeout": 10,
            "password_length": 16,
            "password_charset": 0,
            "use_git": True,
            "auto_push": True,
            "git_pull_on_start": False,
            "profiles": {},
            "current_profile": "",
            "pass_store": "~/.password-store",
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

    def save(self):
        """Save settings"""
        for key, value in self.options.items():
            if isinstance(value, type):
                continue  # placeholder default, nothing stored yet
            self.settings.setValue(key, value)
        self.settings.sync()
