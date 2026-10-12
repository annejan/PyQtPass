"""
This module defines the UsersDialog class, a PyQt6 QDialog subclass.

The UsersDialog shows the GPG keys in the user's keyring and lets them
select which keys the password store (or a folder inside it) should be
encrypted for, like the users dialog in QtPass. Keys can be imported from a
file or the clipboard, and a new key pair can be generated, without leaving
the dialog. The caller applies the selection with PasswordStore.init.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from gpg_utils import (
    import_keys,
    key_matches_id,
    key_problem,
    list_gpg_keys,
    read_gpg_ids,
)
from keygen_dialog import KeyGenDialog


class UsersDialog(QDialog):
    """
    A dialog to select the GPG keys a (sub)store is encrypted for.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, store_dir, folder="", parent=None):
        """
        :param store_dir: Root directory of the password store.
        :param folder: Folder relative to the store root, '' for the root.
        :param parent: The parent widget.
        """
        super().__init__(parent)
        self.store_dir = store_dir
        self.folder = folder
        self.selected_ids = []
        self.key_list = QListWidget(self)
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText(self.tr("Search keys"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.apply_filter)
        self.show_all = QCheckBox(self.tr("Show keys that cannot be used"), self)
        self.show_all.toggled.connect(self.populate_keys)
        self.current_ids, self.ids_folder = read_gpg_ids(store_dir, folder)
        self.setWindowTitle(self.tr("Users for {}").format(folder or "/"))
        self.init_ui()

    def init_ui(self):
        """
        Sets up the user interface for the users dialog.
        """
        layout = QVBoxLayout(self)
        intro = self.tr("Select the keys to encrypt passwords in {} with:").format(
            self.folder or self.tr("the password store")
        )
        if self.current_ids and self.ids_folder != self.folder.strip("/"):
            intro += "\n" + self.tr(
                "This folder now uses the keys of {}; OK gives it its own list."
            ).format("/" + self.ids_folder)
        label = QLabel(intro, self)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.key_list)
        layout.addWidget(self.show_all)
        self.populate_keys()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        import_button = QPushButton(self.tr("Import keys"), self)
        import_menu = QMenu(import_button)
        import_menu.addAction(self.tr("From file..."), self.import_from_file)
        import_menu.addAction(self.tr("From clipboard"), self.import_from_clipboard)
        import_button.setMenu(import_menu)
        generate_button = QPushButton(self.tr("Generate key pair..."), self)
        generate_button.clicked.connect(self.generate_key)
        buttons.addButton(import_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(generate_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 420)

    def checked_ids(self):
        """
        :return: Set of the key ids currently checked in the list.
        """
        return {
            self.key_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.key_list.count())
            if self.key_list.item(row).checkState() == Qt.CheckState.Checked
        }

    def populate_keys(self):
        """
        Fill the list widget with the available GPG keys, checking the
        ones currently in use for this folder. Recipients whose key is not
        in the keyring are listed too, so they are not dropped silently.
        """
        previously_checked = self.checked_ids() if self.key_list.count() else None
        self.key_list.clear()
        secret_ids = {key["id"] for key in list_gpg_keys(secret=True)}
        matched_ids = set()
        for key in list_gpg_keys():
            matches = [i for i in self.current_ids if key_matches_id(key, i)]
            matched_ids.update(matches)
            problem = key_problem(key)
            if problem and not matches and not self.show_all.isChecked():
                continue
            uid = key["uids"][0] if key["uids"] else key["fingerprint"]
            label = f"{uid} ({key['id']})"
            if key["id"] in secret_ids:
                label += self.tr(" [your key]")
            if problem:
                label += f" [{problem}]"
            key_id = key["fingerprint"] or key["id"]
            if previously_checked is None:
                checked = bool(matches)
            else:
                checked = key_id in previously_checked
            self.add_item(label, key_id, checked, bool(problem))
        for missing in self.current_ids:
            if missing not in matched_ids:
                checked = previously_checked is None or missing in previously_checked
                self.add_item(
                    missing + self.tr(" [key not in keyring]"), missing, checked, True
                )
        self.apply_filter(self.filter_edit.text())

    def add_item(self, label, key_id, checked, warning):
        """Add one checkable key to the list."""
        item = QListWidgetItem(label)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        item.setData(Qt.ItemDataRole.UserRole, key_id)
        if warning:
            item.setForeground(QBrush(Qt.GlobalColor.darkRed))
        self.key_list.addItem(item)

    def apply_filter(self, text):
        """
        Hide the keys that do not match the search text.

        :param text: The search text.
        """
        text = text.lower()
        for row in range(self.key_list.count()):
            item = self.key_list.item(row)
            item.setHidden(bool(text) and text not in item.text().lower())

    def selected_key_ids(self):
        """
        :return: List of the key ids of all checked keys, in list order.
        """
        return [
            self.key_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.key_list.count())
            if self.key_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def import_data(self, data):
        """
        Import key material and refresh the list.

        :param data: The key material as bytes.
        """
        success, output = import_keys(data)
        if success:
            QMessageBox.information(
                self,
                self.tr("Keys imported"),
                self.tr(
                    "The key is now in your keyring. Tick it to make it a "
                    "recipient of this folder.\n\n{}"
                ).format(output),
            )
            self.populate_keys()
        else:
            QMessageBox.warning(self, self.tr("Import failed"), output)

    def import_from_file(self):
        """Import keys from a file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import keys"),
            "",
            self.tr("Keys (*.asc *.gpg *.pgp *.key);;All files (*)"),
        )
        if path:
            with open(path, "rb") as key_file:
                self.import_data(key_file.read())

    def import_from_clipboard(self):
        """Import an armored key from the clipboard."""
        text = QApplication.clipboard().text()
        if "BEGIN PGP PUBLIC KEY BLOCK" not in text:
            QMessageBox.warning(
                self,
                self.tr("Import failed"),
                self.tr("The clipboard does not hold an armored public key."),
            )
            return
        self.import_data(text.encode())

    def generate_key(self):
        """Generate a new key pair and refresh the list."""
        if KeyGenDialog(self).exec() == QDialog.DialogCode.Accepted:
            self.populate_keys()

    def save(self):
        """
        Check the selection and close; the caller writes .gpg-id and
        re-encrypts the passwords.
        """
        key_ids = self.selected_key_ids()
        if not key_ids:
            QMessageBox.warning(
                self,
                self.tr("No keys selected"),
                self.tr("Select at least one key to encrypt the passwords with."),
            )
            return
        secret_keys = list_gpg_keys(secret=True)
        if not any(
            key_matches_id(key, key_id) for key in secret_keys for key_id in key_ids
        ):
            answer = QMessageBox.question(
                self,
                self.tr("None of your keys selected"),
                self.tr(
                    "None of the selected keys is yours, so you will not be "
                    "able to read these passwords any more. Continue?"
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.selected_ids = key_ids
        self.accept()
