"""
This module defines the EditPasswordDialog class, a PyQt6 QDialog subclass.

Like the QtPass 2.0 password dialog it is one dialog for adding and
editing entries: when adding, the folder is picked from the store and the
name typed in the dialog itself. Template fields ('login', 'url', ...) get
their own line edits and the password can be generated.
"""

import secrets
import string

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from entry import build_entry, parse_entry
from password_store import CommitError
from tasks import run_task
from settings_manager import SettingsManager

CHARACTER_SETS = [
    string.ascii_letters + string.digits + string.punctuation,
    string.ascii_letters + string.digits,
    string.ascii_letters,
    string.digits,
]
CUSTOM_CHARSET = len(CHARACTER_SETS)


def charset_names(widget):
    """
    :param widget: A QObject used for translating.
    :return: The names of the character sets, in index order.
    """
    return [
        widget.tr("All characters"),
        widget.tr("Letters and numbers"),
        widget.tr("Letters only"),
        widget.tr("Numbers only"),
        widget.tr("Custom"),
    ]


def random_password(charset_index, length, custom_chars=""):
    """
    Generate a random password.

    :param charset_index: Index into CHARACTER_SETS, or CUSTOM_CHARSET.
    :param length: Number of characters to generate.
    :param custom_chars: The characters to use for CUSTOM_CHARSET.
    :return: The generated password string.
    """
    if charset_index == CUSTOM_CHARSET and custom_chars:
        characters = "".join(dict.fromkeys(custom_chars))
    elif 0 <= charset_index < len(CHARACTER_SETS):
        characters = CHARACTER_SETS[charset_index]
    else:
        characters = CHARACTER_SETS[0]
    return "".join(secrets.choice(characters) for _ in range(length))


def field_rows(template_fields, fields):
    """
    Decide which field inputs the dialog shows: one per template field,
    filled from the entry when it has that field, then one for every other
    field of the entry. Repeated fields each keep their own input.

    :param template_fields: The template field names.
    :param fields: List of (name, value) tuples parsed from the entry.
    :return: List of (name, value) tuples.
    """
    remaining = list(fields)
    rows = []
    for name in template_fields:
        value = ""
        for position, (field_name, field_value) in enumerate(remaining):
            if field_name == name:
                value = field_value
                del remaining[position]
                break
        rows.append((name, value))
    return rows + remaining


class EditPasswordDialog(QDialog):
    """
    A EditPasswordDialog dialog class that inherits from QDialog.

    This dialog allows users to edit and create passwords.
    """

    # pylint: disable=too-many-instance-attributes,too-many-arguments
    # pylint: disable=too-many-positional-arguments

    def __init__(
        self, store, path, name, create=False, parent=None, data=None
    ):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """
        :param store: The PasswordStore.
        :param path: The entry path, or the initial folder when creating.
        :param name: The entry name for the window title.
        :param create: Whether a new entry is added.
        :param parent: The parent widget.
        :param data: The decrypted entry, read from the store when None.
        :raises FileNotFoundError, StoreError: when the entry cannot be read.
        """
        super().__init__(parent)
        self.settings = SettingsManager()
        self.store = store
        self.path = path
        self.create = create
        self.folder_combo = None
        self.name_edit = None
        self.field_edits = []
        self.password_edit = QLineEdit(self)
        self.show_password_checkbox = QCheckBox(self.tr("Show password"), self)
        self.charset_combo_box = QComboBox(self)
        self.length_edit = QSpinBox(self)
        self.info_text_edit = QTextEdit(self)
        self.buttons = None
        self.task = None
        self.dirty = create
        self.saved = False
        content = None
        if not create:
            content = parse_entry(
                data if data is not None else store.get_key(path),
                self.settings.template_fields(),
                self.settings.get("use_template")
                and self.settings.get("template_all_fields"),
            )
        if create:
            self.setWindowTitle(self.tr("Add password"))
        else:
            self.setWindowTitle(self.tr("Edit {}").format(name))
        self.init_ui(content)
        for edit in [self.password_edit] + [edit for _, edit in self.field_edits]:
            edit.textChanged.connect(self.mark_dirty)
        self.info_text_edit.textChanged.connect(self.mark_dirty)

    def mark_dirty(self):
        """Remember that something was changed, so OK has to save."""
        self.dirty = True

    def init_ui(self, content):
        """
        Sets up the user interface for the password dialog.

        :param content: The parsed entry, or None when creating.
        """
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        if self.create:
            self.init_location_rows(form)
        self.init_password_rows(form)
        if content is not None:
            self.password_edit.setText(content.password)
            self.info_text_edit.setPlainText(content.remaining)
        for name, value in field_rows(
            self.settings.template_fields(), content.fields if content else []
        ):
            edit = QLineEdit(value, self)
            edit.setAccessibleName(name)
            form.addRow(f"{name}:", edit)
            self.field_edits.append((name, edit))
        self.info_text_edit.setAcceptRichText(False)
        layout.addWidget(self.info_text_edit)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        if self.create:
            self.generate_password()
        (self.name_edit or self.password_edit).setFocus()
        self.resize(500, 400)

    def init_location_rows(self, form):
        """
        Add the folder and name inputs for a new entry.

        :param form: The QFormLayout to add to.
        """
        self.folder_combo = QComboBox(self)
        folders = self.store.list_folders()
        self.folder_combo.addItems(["/" + folder for folder in folders])
        initial = self.path.strip("/")
        if initial in folders:
            self.folder_combo.setCurrentIndex(folders.index(initial))
        form.addRow(self.tr("Folder:"), self.folder_combo)
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText(self.tr("Name of the new password"))
        form.addRow(self.tr("Name:"), self.name_edit)

    def init_password_rows(self, form):
        """
        Add the password input and the generator settings.

        :param form: The QFormLayout to add to.
        """
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setAccessibleName(self.tr("Password"))
        generate_button = QPushButton(self.tr("Generate"), self)
        generate_button.clicked.connect(self.generate_password)
        password_layout = QHBoxLayout()
        password_layout.addWidget(self.password_edit)
        password_layout.addWidget(generate_button)
        form.addRow(self.tr("Password:"), password_layout)

        self.charset_combo_box.addItems(charset_names(self))
        charset = int(self.settings.get("password_charset"))
        if not 0 <= charset <= CUSTOM_CHARSET:
            charset = 0
        self.charset_combo_box.setCurrentIndex(charset)
        self.length_edit.setRange(1, 4096)
        self.length_edit.setValue(int(self.settings.get("password_length")))
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(self.show_password_checkbox)
        settings_layout.addStretch(1)
        settings_layout.addWidget(self.charset_combo_box)
        settings_layout.addWidget(QLabel(self.tr("Length:"), self))
        settings_layout.addWidget(self.length_edit)
        form.addRow(settings_layout)
        self.show_password_checkbox.toggled.connect(self.toggle_password_visibility)

    def toggle_password_visibility(self, _state=None):
        """Show or hide password"""
        if self.show_password_checkbox.isChecked():
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def generate_password(self):
        """Generate a password"""
        password = random_password(
            self.charset_combo_box.currentIndex(),
            self.length_edit.value(),
            self.settings.get("custom_chars"),
        )
        self.password_edit.setText(password)

    def target_path(self):
        """
        :return: The entry path the dialog saves to.
        """
        if not self.create:
            return self.path
        folder = self.folder_combo.currentText().strip("/")
        name = self.name_edit.text().strip().strip("/")
        return f"{folder}/{name}" if folder else name

    def entry_data(self):
        """
        :return: The entry contents assembled from the dialog.
        """
        fields = [(name, edit.text().strip()) for name, edit in self.field_edits]
        return build_entry(
            self.password_edit.text(), fields, self.info_text_edit.toPlainText()
        )

    def save(self):
        """
        Save the password on a worker thread; an unchanged entry is not
        written again (that would re-encrypt and commit it for nothing).
        """
        if self.create and not self.name_edit.text().strip().strip("/"):
            QMessageBox.warning(
                self, self.tr("No name"), self.tr("Enter a name for the password.")
            )
            return
        if not self.dirty:
            self.accept()
            return
        path = self.target_path()
        data = self.entry_data()
        store = self.store
        force = not self.create
        self.setEnabled(False)
        self.task = run_task(
            lambda _progress, _cancelled: store.set_key(path, data, force=force),
            lambda _result, error: self.saved_or_failed(path, error),
        )

    def saved_or_failed(self, path, error):
        """
        Close the dialog when the entry was saved, or say why it was not.

        :param path: The entry path.
        :param error: The exception, or None.
        """
        self.task = None
        self.setEnabled(True)
        if isinstance(error, FileExistsError):
            QMessageBox.warning(
                self,
                self.tr("Password exists"),
                self.tr("Password already exists at: {}").format(path),
            )
            return
        if isinstance(error, CommitError):
            # Saved: retrying would only make a second commit.
            QMessageBox.warning(
                self,
                self.tr("Saved, but not committed"),
                self.tr("{} was saved, but committing it to git failed:\n{}").format(
                    path, error
                ),
            )
        elif error is not None:
            QMessageBox.critical(
                self,
                self.tr("Could not save password"),
                self.tr("Saving {} failed, nothing was changed:\n{}").format(
                    path, error
                ),
            )
            return
        self.path = path
        self.saved = True
        self.accept()

    def reject(self):
        """Do not close while the entry is being saved."""
        if self.task is None:
            super().reject()
