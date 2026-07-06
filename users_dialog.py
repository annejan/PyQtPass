"""
This module defines the UsersDialog class, a PyQt6 QDialog subclass.

The UsersDialog shows the GPG keys in the user's keyring and lets them
select which keys the password store (or a folder inside it) should be
encrypted for, like the users dialog in QtPass. Applying the selection
rewrites the .gpg-id file and re-encrypts the affected passwords.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from gpg_utils import key_matches_id, list_gpg_keys, read_gpg_ids, reencrypt_store


class UsersDialog(QDialog):
    """
    A dialog to select the GPG keys a (sub)store is encrypted for.
    """

    def __init__(self, store, folder="", parent=None):
        super().__init__(parent)
        self.store = store
        self.folder = folder
        self.key_list = QListWidget(self)
        self.setWindowTitle(self.tr("Users for {}").format(folder or "/"))
        self.init_ui()

    def init_ui(self):
        """
        Sets up the user interface for the users dialog.
        """
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                self.tr("Select the keys to encrypt passwords in {} with:").format(
                    self.folder or self.tr("the password store")
                )
            )
        )
        layout.addWidget(self.key_list)
        self.populate_keys()

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)
        ok_button = QPushButton(self.tr("OK"), self)
        ok_button.clicked.connect(self.save)
        cancel_button = QPushButton(self.tr("Cancel"), self)
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(ok_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)
        self.setLayout(layout)
        self.resize(500, 400)

    def populate_keys(self):
        """
        Fill the list widget with the available GPG keys, checking the
        ones currently in use for this folder.
        """
        current_ids, _ = read_gpg_ids(self.store.store_dir, self.folder)
        secret_ids = {key["id"] for key in list_gpg_keys(secret=True)}
        for key in list_gpg_keys():
            uid = key["uids"][0] if key["uids"] else key["fingerprint"]
            label = f"{uid} ({key['id']})"
            if key["id"] not in secret_ids:
                label += self.tr(" [no private key]")
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = any(key_matches_id(key, gpg_id) for gpg_id in current_ids)
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, key["id"])
            self.key_list.addItem(item)

    def selected_key_ids(self):
        """
        :return: List of the key ids of all checked keys.
        """
        return [
            self.key_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.key_list.count())
            if self.key_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def save(self):
        """
        Write the selected keys to .gpg-id and re-encrypt the passwords.
        """
        key_ids = self.selected_key_ids()
        if not key_ids:
            QMessageBox.warning(
                self,
                self.tr("No keys selected"),
                self.tr("Select at least one key to encrypt the passwords with."),
            )
            return
        try:
            reencrypt_store(self.store, self.folder, key_ids)
        except (OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                self.tr("Re-encryption failed"),
                self.tr("Could not update the store keys: {}").format(error),
            )
            return
        self.accept()
