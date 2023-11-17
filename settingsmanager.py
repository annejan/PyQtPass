"""
This module provides a SettingsManager class to manage application settings
using the QSettings interface from the PyQt5.QtCore module. It allows for storing
and retrieving various settings such as window geometry, splitter sizes, and
boolean flags for application behavior.
"""

from PyQt5.QtCore import QSettings, QByteArray


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
        self.settings = QSettings("IJHack", "PyQtPass")
        self.options = {
            "select_is_open": True,
            "close_is_hide": False,
            "splitter_sizes": [200, 400],
            "window_geometry": QByteArray,
            "always_on_top": False,
            "use_tray_icon": True,
            "start_minimized": False,
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
        """Load settings"""
        for key, value in self.options.items():
            settings_value = self.settings.value(key)
            if not settings_value:
                continue
            if isinstance(value, bool) and not isinstance(settings_value, bool):
                self.options[key] = settings_value.lower() in ("true", "1")
            else:
                self.options[key] = settings_value

    def save(self):
        """Save settings"""
        for key, value in self.options.items():
            self.settings.setValue(key, value)
