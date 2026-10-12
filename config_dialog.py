"""
This module defines the ConfigDialog class, a PyQt6 QDialog subclass.

The ConfigDialog provides a graphical user interface for users to change
application settings, grouped in tabs like the QtPass configuration dialog.
It interacts with a SettingsManager to persist these settings.
"""

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from edit_password_window import CUSTOM_CHARSET, charset_names
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
        tabs.addTab(self.create_template_tab(), self.tr("Templates"))
        tabs.addTab(self.create_git_tab(), self.tr("Git"))
        tabs.addTab(self.create_profiles_tab(), self.tr("Profiles"))
        tabs.addTab(self.create_system_tab(), self.tr("System"))
        layout.addWidget(tabs)
        self.init_buttons(layout)
        self.setLayout(layout)
        self.resize(560, 480)

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
        search_box = QCheckBox(self.tr("Search the content of passwords too"))
        search_box.setToolTip(
            self.tr(
                "Pressing Enter in the search box decrypts every entry and shows "
                "the ones whose content matches the regular expression"
            )
        )
        treeview_layout.addRow(self.add_field("use_grep_search", search_box))
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
            self.add_field("use_monospace", QCheckBox(self.tr("Use monospace font")))
        )
        panel_layout.addRow(
            self.add_field("display_as_is", QCheckBox(self.tr("Display content as is")))
        )
        panel_layout.addRow(
            self.add_field("no_line_wrapping", QCheckBox(self.tr("No line wrapping")))
        )
        panel_layout.addRow(
            self.add_field(
                "use_otp", QCheckBox(self.tr("Show one-time passwords (TOTP)"))
            )
        )
        panel_layout.addRow(
            self.add_field(
                "use_qrencode",
                QCheckBox(self.tr("Offer QR codes (needs qrencode)")),
            )
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
                "use_selection",
                QCheckBox(self.tr("Also copy to the selection (middle click)")),
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
        charset_combo_box.addItems(charset_names(self))
        password_layout.addRow(
            self.tr("Characters:"),
            self.add_field("password_charset", charset_combo_box),
        )
        custom_edit = QLineEdit(self)
        custom_edit.setEnabled(False)
        charset_combo_box.currentIndexChanged.connect(
            lambda index: custom_edit.setEnabled(index == CUSTOM_CHARSET)
        )
        password_layout.addRow(
            self.tr("Custom characters:"), self.add_field("custom_chars", custom_edit)
        )
        layout.addWidget(password_group)
        layout.addStretch(1)
        return tab

    def create_template_tab(self):
        """Create the tab with the field template settings."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.addWidget(
            self.add_field("use_template", QCheckBox(self.tr("Use a template")))
        )
        explanation = QLabel(
            self.tr(
                "Field names, one per line. Template fields get their own "
                "input in the password dialog and their own row, with a copy "
                "button, in the content panel."
            ),
            tab,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        layout.addWidget(self.add_field("pass_template", QPlainTextEdit(tab)))
        layout.addWidget(
            self.add_field(
                "template_all_fields",
                QCheckBox(self.tr("Show all 'name: value' lines as fields")),
            )
        )
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

        programs_group = QGroupBox(self.tr("Locations:"), tab)
        programs_layout = QFormLayout(programs_group)
        programs_layout.addRow(
            self.tr("Password store:"),
            self.path_row("pass_store", directory=True),
        )
        programs_layout.addRow(self.tr("GnuPG:"), self.path_row("gpg_executable"))
        programs_layout.addRow(self.tr("Git:"), self.path_row("git_executable"))
        programs_layout.addRow(
            self.tr("qrencode:"), self.path_row("qrencode_executable")
        )
        layout.addWidget(programs_group)
        layout.addStretch(1)
        return tab

    def path_row(self, key, directory=False):
        """
        A line edit for a path setting with a browse button.

        :param key: The settings key.
        :param directory: Browse for a directory instead of a file.
        :return: The layout holding both.
        """
        edit = self.add_field(key, QLineEdit(self))
        if not directory:
            edit.setPlaceholderText(self.tr("Found automatically"))
        browse = QToolButton(self)
        browse.setText("...")
        browse.setToolTip(self.tr("Browse"))

        def pick():
            if directory:
                path = QFileDialog.getExistingDirectory(self, self.tr("Select folder"))
            else:
                path, _ = QFileDialog.getOpenFileName(
                    self, self.tr("Select executable")
                )
            if path:
                edit.setText(path)

        browse.clicked.connect(pick)
        row = QHBoxLayout()
        row.addWidget(edit)
        row.addWidget(browse)
        return row

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
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value or ""))
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(str(value or ""))
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
            elif isinstance(widget, QLineEdit):
                self.settings_manager.set(key, widget.text().strip())
            elif isinstance(widget, QPlainTextEdit):
                self.settings_manager.set(key, widget.toPlainText().strip())
        if not self.settings_manager.get("pass_store"):
            self.settings_manager.set("pass_store", "~/.password-store")
        profiles = self.get_profiles()
        self.settings_manager.set("profiles", profiles)
        if self.settings_manager.get("current_profile") not in profiles:
            self.settings_manager.set("current_profile", "")
        self.settings_manager.save()
        self.accept()
