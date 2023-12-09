"""
This module defines the EditPasswordDialog class, a PyQt5 QDialog subclass.

This is the main window for password generation, changes etc.
"""

import secrets
import string

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
)

from settings_manager import SettingsManager


class EditPasswordDialog(QDialog):
    """
    A EditPasswordDialog dialog class that inherits from QDialog.

    This dialog allows users to edit and create passwords.
    """

    def __init__(self, store, path, name):
        super().__init__()
        self.info_text_edit = None
        self.length_edit = None
        self.charset_combo_box = None
        self.password_edit = None
        self.show_password_checkbox = None
        self.store = store
        self.path = path
        self.setWindowTitle(self.tr("Password {}").format(name))
        self.init_ui()

    def init_ui(self):
        """
        Sets up the user interface for the password dialog.
        """
        layout = QVBoxLayout(self)

        data = self.store.get_key(self.path)
        lines = data.splitlines(True)  # 'True' keeps the newline characters
        password = lines[0].rstrip("\n")  # Remove the newline character
        information = "".join(lines[1:])

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
            [self.tr("All characters"), self.tr("Letters only"), self.tr("Numbers only")]
        )
        length_label = QLabel(self.tr("Length:"), self)
        self.length_edit = QSpinBox(self)
        self.length_edit.setRange(8, 4096)
        settings = SettingsManager()
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
        cancel_button.clicked.connect(self.close)
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
        if state == self.show_password_checkbox.isChecked():
            self.password_edit.setEchoMode(QLineEdit.Password)
        else:
            self.password_edit.setEchoMode(QLineEdit.Normal)

    def generate_password(self):
        """Generate a password"""
        if self.charset_combo_box.currentIndex() == 1:
            characters = string.ascii_letters
        elif self.charset_combo_box.currentIndex() == 2:
            characters = string.digits
        else:
            characters = string.ascii_letters + string.digits + string.punctuation
        password = "".join(
            secrets.choice(characters) for i in range(self.length_edit.value())
        )
        self.password_edit.setText(password)

    def save(self):
        """Save the password"""
        self.store.set_key(
            self.path,
            self.password_edit.text() + "\n" + self.info_text_edit.toPlainText(),
            True,
        )
        self.close()
