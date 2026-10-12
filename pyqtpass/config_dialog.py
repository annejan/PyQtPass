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
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pyqtpass.edit_password_window import CUSTOM_CHARSET, charset_names
from pyqtpass.gpgid_trust import is_fingerprint
from pyqtpass.profiles_editor import ProfilesEditor
from pyqtpass.settings_manager import SettingsManager


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
        self.profiles_editor = ProfilesEditor(self)
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
        layout.addWidget(self.create_pwgen_group(tab))
        layout.addStretch(1)
        return tab

    def create_pwgen_group(self, parent):
        """
        :param parent: The tab the group goes on.
        :return: The group with the pwgen settings.
        """
        group = QGroupBox(self.tr("Use pwgen"), parent)
        group.setCheckable(True)
        self.add_field("use_pwgen", group)
        group_layout = QFormLayout(group)
        group_layout.addRow(self.tr("pwgen:"), self.path_row("pwgen_executable"))
        for key, text in (
            ("avoid_capitals", self.tr("Avoid capital letters")),
            ("avoid_numbers", self.tr("Avoid numbers")),
            ("use_symbols", self.tr("Include special symbols")),
            ("less_random", self.tr("Generate easy to memorize but less secure")),
        ):
            group_layout.addRow(self.add_field(key, QCheckBox(text)))
        return group

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
                "add_gpg_id", QCheckBox(self.tr("Automatically add .gpg-id files"))
            )
        )
        git_layout.addRow(
            self.add_field(
                "auto_push", QCheckBox(self.tr("Automatically push local changes"))
            )
        )
        auto_pull = QCheckBox(self.tr("Automatically pull"))
        auto_pull.setToolTip(
            self.tr(
                "Pull on startup, before editing a password and before " "re-encrypting"
            )
        )
        git_layout.addRow(self.add_field("git_pull_on_start", auto_pull))
        layout.addWidget(git_group)
        layout.addStretch(1)
        return tab

    def create_profiles_tab(self):
        """Create the tab for managing password store profiles."""
        return self.profiles_editor

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
        signing_edit = self.add_field("pass_signing_key", QLineEdit(self))
        signing_edit.setPlaceholderText(self.tr("No signing"))
        signing_edit.setToolTip(
            self.tr(
                "Full fingerprints of the keys that sign .gpg-id files, like "
                "PASSWORD_STORE_SIGNING_KEY; nothing is encrypted to a list "
                "whose signature does not verify"
            )
        )
        programs_layout.addRow(self.tr("Signing key:"), signing_edit)
        programs_layout.addRow(self.tr("GnuPG:"), self.path_row("gpg_executable"))
        programs_layout.addRow(
            self.tr("GnuPG home:"), self.path_row("gpg_home", directory=True)
        )
        self.fields["gpg_home"].setPlaceholderText(self.tr("Default"))
        programs_layout.addRow(
            self.tr("SSH agent socket:"), self.path_row("ssh_auth_sock")
        )
        self.fields["ssh_auth_sock"].setToolTip(
            self.tr(
                "Used for Git over SSH when the session has no SSH_AUTH_SOCK; "
                "when empty, the ssh socket of a running gpg-agent is used"
            )
        )
        programs_layout.addRow(self.tr("Git:"), self.path_row("git_executable"))
        programs_layout.addRow(
            self.tr("qrencode:"), self.path_row("qrencode_executable")
        )
        use_pass = QCheckBox(self.tr("Use the pass command-line tool"))
        use_pass.setToolTip(
            self.tr(
                "Run the pass script for every change instead of gpg and git "
                "directly, for pass extensions and hooks"
            )
        )
        programs_layout.addRow(self.add_field("use_pass", use_pass))
        programs_layout.addRow(self.tr("pass:"), self.path_row("pass_executable"))
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

    def signing_problem(self):
        """
        :return: Why the configured signing key is not usable, or ''.
        """
        keys = self.fields["pass_signing_key"].text().split()
        if all(is_fingerprint(key) for key in keys):
            return ""
        return self.tr(
            "The signing key must be full fingerprints (40 or 64 hexadecimal "
            "digits), separated by spaces."
        )

    def load_settings(self):
        """
        Load settings into the widgets.
        """
        for key, widget in self.fields.items():
            value = self.settings_manager.get(key)
            if isinstance(widget, (QCheckBox, QGroupBox)):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(int(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value or ""))
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(str(value or ""))
        self.profiles_editor.set_profiles(self.settings_manager.get("profiles") or {})

    def save_settings(self):
        """
        Saves the settings based on the user's input.

        This method is connected to the OK button's clicked signal and updates
        the application settings to reflect the state of the widgets when the
        button is pressed.
        """
        problem = self.profiles_editor.validation_error() or self.signing_problem()
        if problem:
            QMessageBox.warning(self, self.tr("Configuration"), problem)
            return
        for key, widget in self.fields.items():
            if isinstance(widget, (QCheckBox, QGroupBox)):
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
        profiles = self.profiles_editor.profiles()
        self.settings_manager.set("profiles", profiles)
        if self.settings_manager.get("current_profile") not in profiles:
            self.settings_manager.set("current_profile", "")
        self.settings_manager.save()
        self.accept()
