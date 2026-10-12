"""
Copying passwords and one-time codes to the clipboard, and clearing it again.

Like the other main window mixins, the strings are translated in the
context of the main window class.
"""

from PyQt6.QtCore import QByteArray, QCoreApplication, QMimeData
from PyQt6.QtGui import QClipboard
from PyQt6.QtWidgets import QApplication

from pyqtpass import otp
from pyqtpass.entry import parse_entry
from pyqtpass.tasks import run_task

# Clipboard formats that ask clipboard managers not to keep a copy.
SECRET_CLIPBOARD_HINTS = {
    "x-kde-passwordManagerHint": b"secret",
    "ExcludeClipboardContentFromMonitorProcessing": b"1",
    "org.nspasteboard.ConcealedType": b"",
}


class ClipboardActionsMixin:
    """
    The clipboard actions of QtPassGUI.
    """

    def copy_text_to_clipboard(self, text, what=None):
        """
        Copy text to the clipboard, marked as secret for clipboard managers,
        and start the autoclear timer.

        :param text: The text to copy.
        :param what: Optional name of what was copied, for the status bar.
        """
        clipboard = QApplication.clipboard()
        modes = [QClipboard.Mode.Clipboard]
        if self.settings.get("use_selection") and clipboard.supportsSelection():
            modes.append(QClipboard.Mode.Selection)
        for mode in modes:
            mime = QMimeData()
            mime.setText(text)
            for hint, value in SECRET_CLIPBOARD_HINTS.items():
                mime.setData(hint, QByteArray(value))
            clipboard.setMimeData(mime, mode)
        self.copied_text = text
        what = what or QCoreApplication.translate("QtPassGUI", "Password")
        if self.settings.get("autoclear_clipboard"):
            timeout = int(self.settings.get("clipboard_timeout"))
            self.clipboard_timer.start(timeout * 1000)
            self.show_status(
                QCoreApplication.translate(
                    "QtPassGUI", "{} copied to clipboard, clearing in {} seconds"
                ).format(what, timeout)
            )
        else:
            self.show_status(
                QCoreApplication.translate(
                    "QtPassGUI", "{} copied to clipboard"
                ).format(what)
            )

    def clear_clipboard(self):
        """
        Clear the clipboard if it still holds the text we copied.
        """
        clipboard = QApplication.clipboard()
        cleared = False
        for mode in (QClipboard.Mode.Clipboard, QClipboard.Mode.Selection):
            if mode == QClipboard.Mode.Selection and not clipboard.supportsSelection():
                continue
            if self.copied_text and clipboard.text(mode) == self.copied_text:
                clipboard.clear(mode)
                cleared = True
        if cleared:
            self.show_status(
                QCoreApplication.translate("QtPassGUI", "Clipboard cleared")
            )
        self.copied_text = ""

    def with_decrypted(self, path, callback):
        """
        Decrypt an entry on a worker thread, then hand it to callback on the
        GUI thread; a slow gpg (smartcard, pinentry) never freezes the window.

        :param path: The entry path.
        :param callback: Called with the parsed EntryContent.
        """
        store = self.store

        def done(data, error):
            if error is not None:
                self.show_status(
                    QCoreApplication.translate(
                        "QtPassGUI", "Could not decrypt {}: {}"
                    ).format(path, error)
                )
                return
            callback(parse_entry(data))

        run_task(lambda _progress, _cancelled: store.get_key(path), done)

    def copy_password(self, index=None):
        """
        Copy the password (first line) of the item at index to the clipboard.

        :param index: The index in the proxy model, or None for the selection.
        """
        path = self.required_entry_path(index)
        if path is None:
            return

        def copy(content):
            if not content.password_for_display:
                self.show_status(
                    QCoreApplication.translate(
                        "QtPassGUI", "This entry holds an OTP secret, not a password"
                    )
                )
                return
            self.copy_text_to_clipboard(content.password)

        self.with_decrypted(path, copy)

    def copy_otp(self, index=None):
        """
        Copy the current one-time password of the item at index.

        :param index: The index in the proxy model, or None for the selection.
        """
        path = self.required_entry_path(
            index,
            QCoreApplication.translate(
                "QtPassGUI", "No password selected for OTP generation"
            ),
        )
        if path is None:
            return

        def copy(content):
            settings = otp.parse(content.otp)
            if settings is None:
                self.show_status(
                    QCoreApplication.translate(
                        "QtPassGUI", "No OTP code found in this password entry"
                    )
                )
                return
            self.copy_text_to_clipboard(
                otp.generate(settings),
                QCoreApplication.translate("QtPassGUI", "OTP code"),
            )

        self.with_decrypted(path, copy)
