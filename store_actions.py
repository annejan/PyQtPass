"""
The actions of the main window that change the password store: adding,
editing, renaming, moving, duplicating and deleting entries and folders,
managing the recipients of a folder and sharing it.

They live in a mixin to keep the main window module readable; the strings
are translated in the context of the main window class.
"""

from PyQt6.QtCore import QCoreApplication, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QProgressDialog,
)

from edit_password_window import EditPasswordDialog
from keygen_dialog import ExportPublicKeyDialog
from password_store import CommitError
from tasks import run_task
from users_dialog import UsersDialog
from utilities import get_item_full_path, is_folder_item


class StoreActionsMixin:
    """
    Store changing actions of QtPassGUI.
    """

    def open_users_dialog(self, index=None):
        """
        Open the users dialog to select the GPG keys for a folder, then
        write .gpg-id and re-encrypt the folder.

        :param index: The index in the proxy model, or None for the selection.
        """
        folder = self.selected_folder(index)
        dialog = UsersDialog(self.store, folder, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        keys = dialog.selected_ids
        store = self.store
        self.run_with_progress(
            QCoreApplication.translate("QtPassGUI", "Re-encrypting passwords..."),
            lambda progress, _cancelled: store.init(keys, folder, progress=progress),
            QCoreApplication.translate(
                "QtPassGUI", "Re-encrypted passwords in {}"
            ).format(folder or "/"),
            QCoreApplication.translate("QtPassGUI", "Re-encryption failed"),
        )

    def reencrypt_folder(self, index=None):
        """
        Re-encrypt all passwords in a folder for its current recipients.

        :param index: The index in the proxy model, or None for the selection.
        """
        folder = self.selected_folder(index)
        answer = QMessageBox.question(
            self,
            QCoreApplication.translate("QtPassGUI", "Re-encrypt passwords"),
            QCoreApplication.translate(
                "QtPassGUI",
                "Re-encrypt all passwords in {} for its current recipients?",
            ).format(folder or "/"),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        store = self.store
        self.run_with_progress(
            QCoreApplication.translate("QtPassGUI", "Re-encrypting passwords..."),
            lambda progress, cancelled: store.reencrypt(folder, progress, cancelled),
            QCoreApplication.translate(
                "QtPassGUI", "Re-encrypted passwords in {}"
            ).format(folder or "/"),
            QCoreApplication.translate("QtPassGUI", "Re-encryption failed"),
        )

    def run_with_progress(self, label, function, done_message, failed_title):
        """
        Run a store operation on a worker thread with a progress dialog.

        :param label: Text of the progress dialog.
        :param function: Callable(progress, cancelled).
        :param done_message: Status message on success.
        :param failed_title: Title of the error message on failure.
        """
        dialog = QProgressDialog(
            label, QCoreApplication.translate("QtPassGUI", "Cancel"), 0, 0, self
        )
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(500)

        def progress(done, total):
            dialog.setMaximum(total)
            dialog.setValue(done)

        def finished(_result, error):
            dialog.reset()
            dialog.deleteLater()
            self.refresh_tree()
            if error is not None:
                QMessageBox.critical(self, failed_title, str(error))
                return
            self.show_status(done_message)
            self.auto_push()

        task = run_task(function, finished, progress, critical=True)
        dialog.canceled.connect(task.cancel)

    def export_public_key(self):
        """Show the export public key dialog."""
        ExportPublicKeyDialog(self).exec()

    def show_share_help(self):
        """Explain how sharing a store works."""
        QMessageBox.information(
            self,
            QCoreApplication.translate("QtPassGUI", "Sharing passwords with GPG"),
            QCoreApplication.translate(
                "QtPassGUI",
                "<h3>Sharing passwords with GPG</h3>"
                "<p>Every folder is encrypted for the keys in its <i>.gpg-id</i> "
                "file. To share a folder:</p><ol>"
                "<li>Ask the other person for their public key (they can use "
                "<i>Export my public key</i>) and import it in the Users dialog.</li>"
                "<li>Tick their key in <i>Users</i> for the folder; its passwords "
                "are re-encrypted so both of you can read them.</li>"
                "<li>Share the store, for example through a Git remote.</li></ol>",
            ),
        )

    def open_store_folder(self, index=None):
        """
        Open a folder of the store in the file manager.

        :param index: The index in the proxy model, or None for the selection.
        """
        folder = self.selected_folder(index)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.store.absolute(folder)))

    # Context menu

    def show_context_menu(self, position):
        """Create context menu"""
        context_menu = QMenu(self.ui.tree_view)
        index = self.ui.tree_view.indexAt(position)
        item = self.item_from_index(index) if index.isValid() else None
        if item is None:
            index = None

        if item is not None and not is_folder_item(item):
            context_menu.addAction(
                QCoreApplication.translate("QtPassGUI", "Copy password"),
                lambda: self.copy_password(index),
            )
            if self.settings.get("use_otp"):
                context_menu.addAction(
                    QCoreApplication.translate("QtPassGUI", "Copy OTP code"),
                    lambda: self.copy_otp(index),
                )
            context_menu.addAction(
                QCoreApplication.translate("QtPassGUI", "Open"),
                lambda: self.open_item(index),
            )
            context_menu.addAction(
                QCoreApplication.translate("QtPassGUI", "Edit"),
                lambda: self.edit_item(index),
            )
            context_menu.addAction(
                QCoreApplication.translate("QtPassGUI", "Rename password"),
                lambda: self.rename_item(index),
            )
            context_menu.addAction(
                QCoreApplication.translate("QtPassGUI", "Duplicate"),
                lambda: self.duplicate_item(index),
            )
            context_menu.addAction(
                QCoreApplication.translate("QtPassGUI", "Delete"),
                lambda: self.delete_item(index),
            )
            context_menu.exec(self.ui.tree_view.mapToGlobal(position))
            return

        context_menu.addAction(
            QCoreApplication.translate("QtPassGUI", "Add password"),
            lambda: self.add_item(index),
        )
        context_menu.addAction(
            QCoreApplication.translate("QtPassGUI", "Add folder"),
            lambda: self.add_folder(index),
        )
        if item is not None:
            context_menu.addAction(
                QCoreApplication.translate("QtPassGUI", "Rename folder"),
                lambda: self.rename_item(index),
            )
            context_menu.addAction(
                QCoreApplication.translate("QtPassGUI", "Delete"),
                lambda: self.delete_item(index),
            )
        context_menu.addSeparator()
        context_menu.addAction(
            QCoreApplication.translate("QtPassGUI", "Users"),
            lambda: self.open_users_dialog(index),
        )
        share_menu = context_menu.addMenu(
            QCoreApplication.translate("QtPassGUI", "Share")
        )
        share_menu.addAction(
            QCoreApplication.translate("QtPassGUI", "Re-encrypt all passwords"),
            lambda: self.reencrypt_folder(index),
        )
        share_menu.addAction(
            QCoreApplication.translate("QtPassGUI", "Export my public key..."),
            self.export_public_key,
        )
        share_menu.addAction(
            QCoreApplication.translate("QtPassGUI", "Add recipient..."),
            lambda: self.open_users_dialog(index),
        )
        share_menu.addSeparator()
        share_menu.addAction(
            QCoreApplication.translate("QtPassGUI", "What is this?"),
            self.show_share_help,
        )
        context_menu.addAction(
            QCoreApplication.translate("QtPassGUI", "Open folder with file manager"),
            lambda: self.open_store_folder(index),
        )
        context_menu.exec(self.ui.tree_view.mapToGlobal(position))

    # Store changes

    def after_change(self, message):
        """
        Refresh the tree, report a change and push it when configured.

        :param message: The status message.
        """
        self.refresh_tree()
        self.show_status(message)
        self.auto_push()

    def store_error(self, title, error):
        """
        Report a failed store operation.

        :param title: The title of the message box.
        :param error: The exception.
        """
        QMessageBox.warning(self, title, str(error))

    def run_store_change(self, function, done_message, failed_title, on_done=None):
        """
        Change the store on a worker thread: gpg and git can take long (a
        smartcard, a pinentry, a hook), and the store's lock makes a change
        wait for a running pull instead of racing it.

        :param function: Callable doing the change.
        :param done_message: Status message on success.
        :param failed_title: Title of the warning on failure.
        :param on_done: Optional callable run on the GUI thread on success.
        """
        self.show_status(QCoreApplication.translate("QtPassGUI", "Working..."), 0)

        def done(_result, error):
            if isinstance(error, CommitError):
                # The change is on disk; only the commit failed.
                self.store_error(
                    QCoreApplication.translate("QtPassGUI", "Not committed"), error
                )
            elif error is not None:
                self.store_error(failed_title, error)
                self.statusBar().clearMessage()
                return
            if on_done is not None:
                on_done()
            self.after_change(done_message)

        run_task(lambda _progress, _cancelled: function(), done, critical=True)

    def add_item(self, index=None):
        """Add a password in the folder of index or the selection."""
        dialog = EditPasswordDialog(
            self.store, self.selected_folder(index), "", create=True, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.after_change(
                QCoreApplication.translate("QtPassGUI", "Added password {}").format(
                    dialog.path
                )
            )

    def add_folder(self, index=None):
        """Add a folder in the folder of index or the selection."""
        parent = self.selected_folder(index)
        name, ok = QInputDialog.getText(
            self,
            QCoreApplication.translate("QtPassGUI", "New folder"),
            QCoreApplication.translate(
                "QtPassGUI", "New folder:\n(will be placed in {})"
            ).format("/" + parent),
        )
        name = name.strip().strip("/")
        if not ok or not name:
            return
        path = f"{parent}/{name}" if parent else name
        store = self.store
        # Waits for the store's lock like any change, so not on this thread.
        self.run_store_change(
            lambda: store.create_folder(path),
            QCoreApplication.translate("QtPassGUI", "Added folder {}").format(path),
            QCoreApplication.translate("QtPassGUI", "Failed to create folder"),
        )

    def edit_item(self, index=None):
        """Decrypt an entry in the background, then open it for editing."""
        path = self.selected_entry_path(index)
        if path is None:
            self.show_status(
                QCoreApplication.translate("QtPassGUI", "No password selected")
            )
            return
        store = self.store
        self.show_status(
            QCoreApplication.translate("QtPassGUI", "Decrypting {}").format(path), 0
        )

        def decrypted(data, error):
            self.statusBar().clearMessage()
            if isinstance(error, FileNotFoundError):
                self.verbose_print(f"Cannot retrieve a non-existent key: {path}")
                return
            if error is not None:
                self.store_error(
                    QCoreApplication.translate(
                        "QtPassGUI", "Could not decrypt this password entry"
                    ),
                    error,
                )
                return
            self.open_edit_dialog(store, path, data)

        run_task(lambda _progress, _cancelled: store.get_key(path), decrypted)

    def open_edit_dialog(self, store, path, data):
        """
        Show the password dialog for a decrypted entry.

        :param store: The store the entry was read from.
        :param path: The entry path.
        :param data: The decrypted contents.
        """
        dialog = EditPasswordDialog(
            store, path, path.rsplit("/", 1)[-1], parent=self, data=data
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.saved:
            return
        if self.settings.get("select_is_open") and path == self.selected_entry_path():
            self.open_item(self.current_index())
        self.show_status(
            QCoreApplication.translate("QtPassGUI", "Saved password {}").format(path)
        )
        self.auto_push()

    def rename_item(self, index=None):
        """Rename an entry or folder."""
        if index is None:
            index = self.current_index()
        if index is None:
            self.show_status(
                QCoreApplication.translate("QtPassGUI", "No password selected")
            )
            return
        item = self.item_from_index(index)
        path = get_item_full_path(item)
        if is_folder_item(item):
            title = QCoreApplication.translate("QtPassGUI", "Rename folder")
            label = QCoreApplication.translate("QtPassGUI", "Rename folder to:")
        else:
            title = QCoreApplication.translate("QtPassGUI", "Rename password")
            label = QCoreApplication.translate("QtPassGUI", "Rename password to:")
        new_path, ok = QInputDialog.getText(self, title, label, text=path)
        new_path = new_path.strip().strip("/")
        if not ok or not new_path or new_path == path:
            self.verbose_print("Rename cancelled")
            return
        store = self.store
        self.run_store_change(
            lambda: store.move_path(path, new_path),
            QCoreApplication.translate("QtPassGUI", "Renamed {} to {}").format(
                path, new_path
            ),
            QCoreApplication.translate("QtPassGUI", "Rename failed"),
        )

    def duplicate_item(self, index=None):
        """Copy an entry to a new name."""
        path = self.selected_entry_path(index)
        if path is None:
            return
        new_path, ok = QInputDialog.getText(
            self,
            QCoreApplication.translate("QtPassGUI", "Duplicate password"),
            QCoreApplication.translate("QtPassGUI", "Copy password to:"),
            text=path + "-copy",
        )
        new_path = new_path.strip().strip("/")
        if not ok or not new_path or new_path == path:
            return
        store = self.store
        self.run_store_change(
            lambda: store.copy_path(path, new_path),
            QCoreApplication.translate("QtPassGUI", "Copied {} to {}").format(
                path, new_path
            ),
            QCoreApplication.translate("QtPassGUI", "Copy failed"),
        )

    def on_move_requested(self, source, folder, copy):
        """
        Move (or copy) an entry or folder dropped onto a folder.

        :param source: The dragged path.
        :param folder: The target folder, '' for the root.
        :param copy: Copy instead of move.
        """
        name = source.rsplit("/", 1)[-1]
        target = f"{folder}/{name}" if folder else name
        if target == source:
            return
        store = self.store
        if copy:
            self.run_store_change(
                lambda: store.copy_path(source, target),
                QCoreApplication.translate("QtPassGUI", "Copied {} to {}").format(
                    source, target
                ),
                QCoreApplication.translate("QtPassGUI", "Copy failed"),
            )
        else:
            self.run_store_change(
                lambda: store.move_path(source, target),
                QCoreApplication.translate("QtPassGUI", "Moved {} to {}").format(
                    source, target
                ),
                QCoreApplication.translate("QtPassGUI", "Move failed"),
            )

    def delete_item(self, index=None):
        """Delete an entry or folder."""
        if index is None:
            index = self.current_index()
        if index is None:
            self.show_status(
                QCoreApplication.translate("QtPassGUI", "No password selected")
            )
            return
        item = self.item_from_index(index)
        path = get_item_full_path(item)
        if is_folder_item(item):
            question = QCoreApplication.translate(
                "QtPassGUI", "Are you sure you want to delete {} and the whole content?"
            ).format(path)
        else:
            question = QCoreApplication.translate(
                "QtPassGUI", "Are you sure you want to delete {}?"
            ).format(path)
        reply = QMessageBox.question(
            self,
            QCoreApplication.translate("QtPassGUI", "Confirm Delete"),
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.verbose_print("Deletion cancelled")
            return
        self.verbose_print(f"Deleting {path}")
        store = self.store
        self.run_store_change(
            lambda: store.remove_path(path, recursive=True),
            QCoreApplication.translate("QtPassGUI", "Deleted {}").format(path),
            QCoreApplication.translate("QtPassGUI", "Delete failed"),
            on_done=self.ui.panel.clear,
        )
