"""
This module defines the ConfigDialog class, a PyQt5 QDialog subclass.

The ConfigDialog provides a graphical user interface for users to change
application settings. It includes checkboxes for different settings and a save button
to apply changes. The class interacts with a SettingsManager to persist these settings.
"""

from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QSpinBox,
    QGroupBox,
    QFormLayout,
    QDialog,
)

from settingsmanager import SettingsManager


def init_clipboard_group(layout):
    """TODO Static for now"""
    clipboard_group = QGroupBox("Clipboard behavior:")
    clipboard_layout = QFormLayout()
    clipboard_group.setLayout(clipboard_layout)
    copy_to_clipboard = QCheckBox("Always copy to clipboard")
    copy_to_clipboard.setDisabled(True)
    clipboard_layout.addRow(copy_to_clipboard)
    layout.addWidget(clipboard_group)


def init_password_generation_group(layout):
    """TODO Static for now"""
    password_group = QGroupBox("Password Generation:")
    password_layout = QFormLayout()
    password_group.setLayout(password_layout)
    spin_password_length = QSpinBox()
    spin_password_length.setValue(8)
    spin_password_length.setDisabled(True)
    spin_password_length.setReadOnly(True)
    password_layout.addRow("Password Length:", spin_password_length)
    layout.addWidget(password_group)


def init_git_group(layout):
    """TODO Static for now"""
    git_group = QGroupBox("Git:")
    git_layout = QFormLayout()
    git_group.setLayout(git_layout)
    use_git = QCheckBox("Use Git")
    use_git.setDisabled(True)
    git_layout.addRow(use_git)
    layout.addWidget(git_group)


def init_content_panel_group(layout):
    """TODO Static for now"""
    content_panel_group = QGroupBox("Content panel behavior:")
    content_panel_layout = QFormLayout()
    content_panel_group.setLayout(content_panel_layout)
    hide_content = QCheckBox("Hide content")
    hide_content.setDisabled(True)
    content_panel_layout.addRow(hide_content)
    layout.addWidget(content_panel_group)


class ConfigDialog(QDialog):
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
        self.start_minimized = None
        self.always_on_top = None
        self.use_tray_icon = None
        self.select_is_open = None
        self.close_is_hide = None
        self.settings_manager = SettingsManager()
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """
        Sets up the user interface for the configuration dialog.
        """
        self.setWindowTitle("Configuration")
        self.resize(500, 400)
        layout = QVBoxLayout()
        self.init_treeview_group(layout)
        init_clipboard_group(layout)
        init_content_panel_group(layout)
        init_password_generation_group(layout)
        init_git_group(layout)
        self.init_system_group(layout)
        self.init_buttons(layout)
        self.setLayout(layout)

    def init_treeview_group(self, layout):
        """Setup treeview group"""
        treeview_group = QGroupBox("Tree view behavior:")
        treeview_layout = QFormLayout()
        treeview_group.setLayout(treeview_layout)
        self.select_is_open = QCheckBox("Select is open")
        treeview_layout.addRow(self.select_is_open)
        layout.addWidget(treeview_group)

    def init_system_group(self, layout):
        """Setup system group"""
        system_group = QGroupBox("System:")
        system_layout = QHBoxLayout()
        system_group.setLayout(system_layout)
        self.use_tray_icon = QCheckBox("Use Tray icon")
        self.start_minimized = QCheckBox("Start minimized")
        self.close_is_hide = QCheckBox("Hide on close")
        self.always_on_top = QCheckBox("Always on top")
        system_layout.addWidget(self.use_tray_icon)
        system_layout.addWidget(self.start_minimized)
        system_layout.addWidget(self.close_is_hide)
        system_layout.addWidget(self.always_on_top)
        layout.addWidget(system_group)

    def init_buttons(self, layout):
        """OK and Cancel buttons"""
        buttons_layout = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.save_settings)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.close)
        buttons_layout.addWidget(btn_ok)
        buttons_layout.addWidget(btn_cancel)
        layout.addLayout(buttons_layout)

    def load_settings(self):
        """
        Load settings.
        """
        for key in self.settings_manager.options:
            widget = getattr(self, key, None)
            if widget:
                if isinstance(widget, QCheckBox):
                    widget.setChecked(self.settings_manager.get(key))
                else:
                    widget.setValue(self.settings_manager.get(key))

    def save_settings(self):
        """
        Saves the settings based on the user's input.

        This method is connected to the OK button's clicked signal and updates the
        application settings to reflect the state of the checkboxes when the button is pressed.
        """
        for key in self.settings_manager.options:
            widget = getattr(self, key, None)
            if widget:
                if isinstance(widget, QCheckBox):
                    self.settings_manager.set(key, widget.isChecked())
                else:
                    self.settings_manager.set(key, widget.getValue())
        self.settings_manager.save()
        self.close()
