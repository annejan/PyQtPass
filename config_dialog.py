"""
This module defines the ConfigDialog class, a PyQt5 QDialog subclass.

The ConfigDialog provides a graphical user interface for users to change
application settings, grouped in tabs like the QtPass configuration dialog.
It interacts with a SettingsManager to persist these settings.
"""

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from settings_manager import SettingsManager


class ConfigDialog(QDialog):
    """
    A configuration dialog class that inherits from QDialog.

    This dialog allows users to modify application settings using a graphical
    interface. The settings are grouped in tabs and stored through the
    SettingsManager when the OK button is pressed.
    """

    def __init__(self, parent=None):
        """
        Initializes the configuration dialog, setting up the UI components and
        settings manager.
        """
        super().__init__(parent)
        self.settings_manager = SettingsManager()
        self.fields = {}
        self.profiles_table = QTableWidget(0, 2, self)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """
        Sets up the user interface for the configuration dialog.
        """
        self.setWindowTitle(self.tr("Configuration"))
        layout = QVBoxLayout()
        tabs = QTabWidget(self)
        tabs.addTab(self.create_behaviour_tab(), self.tr("Behaviour"))
        tabs.addTab(self.create_password_tab(), self.tr("Password Generation"))
        tabs.addTab(self.create_git_tab(), self.tr("Git"))
        tabs.addTab(self.create_profiles_tab(), self.tr("Profiles"))
        tabs.addTab(self.create_system_tab(), self.tr("System"))
        layout.addWidget(tabs)
        self.init_buttons(layout)
        self.setLayout(layout)
        self.resize(500, 400)

    def add_field(self, key, widget):
        """
        Register a widget as the editor for a settings key.

        :param key: The settings key.
        :param widget: The widget editing that key.
        :return: The widget, for convenience.
        """
        self.fields[key] = widget
        return widget

    def create_behaviour_tab(self):
        """Create the tab with tree view, content panel and clipboard settings."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        treeview_group = QGroupBox(self.tr("Tree view behavior:"), tab)
        treeview_layout = QFormLayout(treeview_group)
        treeview_layout.addRow(
            self.add_field("select_is_open", QCheckBox(self.tr("Select is open")))
        )
        layout.addWidget(treeview_group)

        panel_group = QGroupBox(self.tr("Content panel behavior:"), tab)
        panel_layout = QFormLayout(panel_group)
        panel_layout.addRow(
            self.add_field("hide_content", QCheckBox(self.tr("Hide content")))
        )
        panel_layout.addRow(
            self.add_field("hide_password", QCheckBox(self.tr("Hide password")))
        )
        panel_layout.addRow(
            self.add_field(
                "autoclear_panel", QCheckBox(self.tr("Autoclear panel after:"))
            ),
            self.add_field("panel_timeout", self.seconds_spin_box()),
        )
        layout.addWidget(panel_group)

        clipboard_group = QGroupBox(self.tr("Clipboard behavior:"), tab)
        clipboard_layout = QFormLayout(clipboard_group)
        clipboard_layout.addRow(
            self.add_field(
                "always_copy_to_clipboard",
                QCheckBox(self.tr("Always copy to clipboard")),
            )
        )
        clipboard_layout.addRow(
            self.add_field(
                "autoclear_clipboard", QCheckBox(self.tr("Autoclear clipboard after:"))
            ),
            self.add_field("clipboard_timeout", self.seconds_spin_box()),
        )
        layout.addWidget(clipboard_group)
        layout.addStretch(1)
        return tab

    def seconds_spin_box(self):
        """
        :return: A QSpinBox suitable for second timeouts.
        """
        spin_box = QSpinBox(self)
        spin_box.setRange(1, 3600)
        spin_box.setSuffix(self.tr(" seconds"))
        return spin_box

    def create_password_tab(self):
        """Create the tab with password generation settings."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        password_group = QGroupBox(self.tr("Password Generation:"), tab)
        password_layout = QFormLayout(password_group)
        length_spin_box = QSpinBox(self)
        length_spin_box.setRange(1, 4096)
        password_layout.addRow(
            self.tr("Password Length:"),
            self.add_field("password_length", length_spin_box),
        )
        charset_combo_box = QComboBox(self)
        charset_combo_box.addItems(
            [
                self.tr("All characters"),
                self.tr("Letters and numbers"),
                self.tr("Letters only"),
                self.tr("Numbers only"),
            ]
        )
        password_layout.addRow(
            self.tr("Characters:"),
            self.add_field("password_charset", charset_combo_box),
        )
        layout.addWidget(password_group)
        layout.addStretch(1)
        return tab

    def create_git_tab(self):
        """Create the tab with git settings."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        git_group = QGroupBox(self.tr("Git:"), tab)
        git_layout = QFormLayout(git_group)
        git_layout.addRow(self.add_field("use_git", QCheckBox(self.tr("Use Git"))))
        git_layout.addRow(
            self.add_field(
                "auto_push", QCheckBox(self.tr("Automatically push local changes"))
            )
        )
        git_layout.addRow(
            self.add_field(
                "git_pull_on_start", QCheckBox(self.tr("Update (git pull) on startup"))
            )
        )
        layout.addWidget(git_group)
        layout.addStretch(1)
        return tab

    def create_profiles_tab(self):
        """Create the tab for managing password store profiles."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        self.profiles_table.setHorizontalHeaderLabels(
            [self.tr("Name"), self.tr("Path")]
        )
        self.profiles_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.profiles_table)

        buttons_layout = QHBoxLayout()
        add_button = QPushButton(self.tr("Add"), self)
        add_button.clicked.connect(self.add_profile)
        remove_button = QPushButton(self.tr("Remove"), self)
        remove_button.clicked.connect(self.remove_profile)
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch(1)
        layout.addLayout(buttons_layout)
        return tab

    def create_system_tab(self):
        """Create the tab with system settings."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        system_group = QGroupBox(self.tr("System:"), tab)
        system_layout = QFormLayout(system_group)
        system_layout.addRow(
            self.add_field("use_tray_icon", QCheckBox(self.tr("Use Tray icon")))
        )
        system_layout.addRow(
            self.add_field("start_minimized", QCheckBox(self.tr("Start minimized")))
        )
        system_layout.addRow(
            self.add_field("close_is_hide", QCheckBox(self.tr("Hide on close")))
        )
        system_layout.addRow(
            self.add_field("always_on_top", QCheckBox(self.tr("Always on top")))
        )
        layout.addWidget(system_group)
        layout.addStretch(1)
        return tab

    def init_buttons(self, layout):
        """OK and Cancel buttons"""
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)
        btn_ok = QPushButton(self.tr("OK"))
        btn_ok.clicked.connect(self.save_settings)
        btn_cancel = QPushButton(self.tr("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        buttons_layout.addWidget(btn_ok)
        buttons_layout.addWidget(btn_cancel)
        layout.addLayout(buttons_layout)

    def add_profile(self):
        """Ask for a profile name and store directory and add it to the table."""
        name, ok = QInputDialog.getText(
            self, self.tr("Profile Name"), self.tr("Enter profile name:")
        )
        if not ok or not name:
            return
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select password store directory")
        )
        if not path:
            return
        row = self.profiles_table.rowCount()
        self.profiles_table.insertRow(row)
        self.profiles_table.setItem(row, 0, QTableWidgetItem(name))
        self.profiles_table.setItem(row, 1, QTableWidgetItem(path))

    def remove_profile(self):
        """Remove the selected profile from the table."""
        row = self.profiles_table.currentRow()
        if row >= 0:
            self.profiles_table.removeRow(row)

    def get_profiles(self):
        """
        :return: Dict of profile name to store path from the profiles table.
        """
        profiles = {}
        for row in range(self.profiles_table.rowCount()):
            name = self.profiles_table.item(row, 0)
            path = self.profiles_table.item(row, 1)
            if name and path and name.text() and path.text():
                profiles[name.text()] = path.text()
        return profiles

    def load_settings(self):
        """
        Load settings into the widgets.
        """
        for key, widget in self.fields.items():
            value = self.settings_manager.get(key)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(int(value))
        profiles = self.settings_manager.get("profiles") or {}
        for name, path in profiles.items():
            row = self.profiles_table.rowCount()
            self.profiles_table.insertRow(row)
            self.profiles_table.setItem(row, 0, QTableWidgetItem(name))
            self.profiles_table.setItem(row, 1, QTableWidgetItem(path))

    def save_settings(self):
        """
        Saves the settings based on the user's input.

        This method is connected to the OK button's clicked signal and updates
        the application settings to reflect the state of the widgets when the
        button is pressed.
        """
        for key, widget in self.fields.items():
            if isinstance(widget, QCheckBox):
                self.settings_manager.set(key, widget.isChecked())
            elif isinstance(widget, QSpinBox):
                self.settings_manager.set(key, widget.value())
            elif isinstance(widget, QComboBox):
                self.settings_manager.set(key, widget.currentIndex())
        profiles = self.get_profiles()
        self.settings_manager.set("profiles", profiles)
        if self.settings_manager.get("current_profile") not in profiles:
            self.settings_manager.set("current_profile", "")
        self.settings_manager.save()
        self.accept()
