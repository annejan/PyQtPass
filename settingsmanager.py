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

    def __init__(self):
        self.settings = QSettings("IJHack", "PyQtPass")

    def get_select_is_open(self):
        """
        Retrieves the boolean value indicating if 'select' is open.

        Returns:
            bool: True if 'select' is open, False otherwise.
        """
        return self.settings.value("select_is_open", True, type=bool)

    def set_select_is_open(self, value):
        """
        Sets the boolean value for the 'select_is_open' setting.

        Args:
            value (bool): The value to set for the 'select_is_open' setting.
        """
        self.settings.setValue("select_is_open", value)

    def get_close_is_hide(self):
        """
        Retrieves the boolean value indicating if 'close' action should hide the application.

        Returns:
            bool: True if 'close' should hide the application, False otherwise.
        """
        return self.settings.value("close_is_hide", True, type=bool)

    def set_close_is_hide(self, value):
        """
        Sets the boolean value for the 'close_is_hide' setting.

        Args:
            value (bool): The value to set for the 'close_is_hide' setting.
        """
        self.settings.setValue("close_is_hide", value)

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

    def set_splitter_sizes(self, sizes):
        """
        Sets the sizes of the splitters.

        Args:
            sizes (list): A list of integers representing the sizes of the splitters.
        """
        self.settings.setValue("splitter_sizes", [int(item) for item in sizes])

    def get_window_geometry(self):
        """
        Retrieves the window geometry.

        Returns:
            QByteArray: The geometry of the window.
        """
        return self.settings.value("window_geometry", QByteArray())

    def set_window_geometry(self, geometry):
        """
        Sets the window geometry.

        Args:
            geometry (QByteArray): The geometry to set for the window.
        """
        self.settings.setValue("window_geometry", geometry)
