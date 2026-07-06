"""
This module defines the EditPasswordDialog class, a PyQt5 QDialog subclass.

This is the main window for password generation, changes etc.
"""

import secrets
import string

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QTextEdit,
    QCheckBox,
    QComboBox,
    QSpinBox,
    QMessageBox,
)

from settings_manager import SettingsManager

CHARACTER_SETS = [
    string.ascii_letters + string.digits + string.punctuation,
    string.ascii_letters + string.digits,
    string.ascii_letters,
    string.digits,
]


def random_password(charset_index, length):
    """
    Generate a random password.

    :param charset_index: Index into CHARACTER_SETS.
    :param length: Number of characters to generate.
    :return: The generated password string.
    """
    if 0 <= charset_index < len(CHARACTER_SETS):
        characters = CHARACTER_SETS[charset_index]
    else:
        characters = CHARACTER_SETS[0]
    return "".join(secrets.choice(characters) for _ in range(length))


class EditPasswordDialog(QDialog):
    """
    A EditPasswordDialog dialog class that inherits from QDialog.

    This dialog allows users to edit and create passwords.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, store, path, name, create=False, parent=None):
        super().__init__(parent)
        self.info_text_edit = None
        self.length_edit = None
        self.charset_combo_box = None
        self.password_edit = None
        self.show_password_checkbox = None
        self.store = store
        self.path = path
        self.create = create
        if create:
            self.setWindowTitle(self.tr("New password {}").format(name))
        else:
            self.setWindowTitle(self.tr("Password {}").format(name))
        self.init_ui()

    def init_ui(self):
        """
        Sets up the user interface for the password dialog.
        """
        layout = QVBoxLayout(self)

        password = ""
        information = ""
        if not self.create:
            data = self.store.get_key(self.path)
            lines = data.splitlines(True)  # 'True' keeps the newline characters
            if lines:
                password = lines[0].rstrip("\n")
                information = "".join(lines[1:])

        settings = SettingsManager()

        self.password_edit = QLineEdit(self)
        self.password_edit.setText(password)
        self.password_edit.setEchoMode(QLineEdit.Password)  # Hides the password
        generate_button = QPushButton(self.tr("Generate"), self)
        password_layout = QHBoxLayout()
        password_layout.addWidget(self.password_edit)
        password_layout.addWidget(generate_button)
        layout.addLayout(password_layout)

        self.show_password_checkbox = QCheckBox(self.tr("Show password"), self)
        self.charset_combo_box = QComboBox(self)
        self.charset_combo_box.addItems(
            [
                self.tr("All characters"),
                self.tr("Letters and numbers"),
                self.tr("Letters only"),
                self.tr("Numbers only"),
            ]
        )
        self.charset_combo_box.setCurrentIndex(int(settings.get("password_charset")))
        length_label = QLabel(self.tr("Length:"), self)
        self.length_edit = QSpinBox(self)
        self.length_edit.setRange(1, 4096)
        self.length_edit.setValue(int(settings.get("password_length")))
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(self.show_password_checkbox)
        settings_layout.addStretch(1)
        settings_layout.addWidget(self.charset_combo_box)
        settings_layout.addWidget(length_label)
        settings_layout.addWidget(self.length_edit)
        layout.addLayout(settings_layout)

        self.info_text_edit = QTextEdit(self)
        self.info_text_edit.setText(information)
        layout.addWidget(self.info_text_edit)

        ok_button = QPushButton(self.tr("OK"), self)
        ok_button.clicked.connect(self.save)
        cancel_button = QPushButton(self.tr("Cancel"))
        cancel_button.clicked.connect(self.reject)
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(ok_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)

        # Connect signals and slots
        self.show_password_checkbox.stateChanged.connect(
            self.toggle_password_visibility
        )
        generate_button.clicked.connect(self.generate_password)

        self.setLayout(layout)

    def toggle_password_visibility(self, state):
        """Show or hide password"""
        if state == Qt.Checked:
            self.password_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)

    def generate_password(self):
        """Generate a password"""
        password = random_password(
            self.charset_combo_box.currentIndex(), self.length_edit.value()
        )
        self.password_edit.setText(password)

    def save(self):
        """Save the password"""
        data = self.password_edit.text() + "\n" + self.info_text_edit.toPlainText()
        try:
            self.store.set_key(self.path, data, force=not self.create)
        except FileExistsError:
            QMessageBox.warning(
                self,
                self.tr("Password exists"),
                self.tr("Password already exists at: {}").format(self.path),
            )
            return
        self.accept()
