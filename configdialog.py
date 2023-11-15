"""
This module defines the ConfigDialog class, a PyQt5 QDialog subclass.

The ConfigDialog provides a graphical user interface for users to change
application settings. It includes checkboxes for different settings and a save button
to apply changes. The class interacts with a SettingsManager to persist these settings.
"""

from PyQt5 import QtWidgets
from settingsmanager import SettingsManager


class ConfigDialog(QtWidgets.QDialog):
    """
    A configuration dialog class that inherits from QDialog.

    This dialog allows users to modify application settings using a graphical interface.
    It includes checkboxes for various settings and a save button to apply the changes.
    """

    def __init__(self):
        """
        Initializes the configuration dialog, setting up the UI components and settings manager.
        """
        super().__init__()
        self.save_button = None
        self.close_is_hide_checkbox = None
        self.select_is_open_checkbox = None
        self.settings_manager = SettingsManager()
        self.init_ui()

    def init_ui(self):
        """
        Sets up the user interface for the configuration dialog.

        This method creates and arranges the checkboxes and the save button in the dialog,
        and sets the initial states of these components based on the current settings.
        """
        self.setWindowTitle("Configuration")

        self.select_is_open_checkbox = QtWidgets.QCheckBox("Select Is Open", self)
        self.select_is_open_checkbox.setChecked(
            self.settings_manager.get_select_is_open()
        )

        self.close_is_hide_checkbox = QtWidgets.QCheckBox("Close Is Hide", self)
        self.close_is_hide_checkbox.setChecked(
            self.settings_manager.get_close_is_hide()
        )

        self.save_button = QtWidgets.QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_settings)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.select_is_open_checkbox)
        layout.addWidget(self.close_is_hide_checkbox)
        layout.addWidget(self.save_button)
        self.setLayout(layout)

    def save_settings(self):
        """
        Saves the settings based on the user's input.

        This method is connected to the save button's clicked signal and updates the
        application settings to reflect the state of the checkboxes when the button is pressed.
        """
        self.settings_manager.set_select_is_open(
            self.select_is_open_checkbox.isChecked()
        )
        self.settings_manager.set_close_is_hide(self.close_is_hide_checkbox.isChecked())
        self.close()
