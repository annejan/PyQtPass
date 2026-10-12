"""
The content panel on the right of the main window.

Like the QtPass password display panel it shows the password and every
field of an entry in its own row with a copy button, a live one-time
password with its countdown, an 'open in browser' button for web
addresses, an optional QR code and the remaining text below.
"""

import shutil

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QStyle,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import executor
from tasks import run_task
import otp
from utilities import format_key_html, is_web_url


def find_qrencode(configured=""):
    """
    :param configured: A configured qrencode executable, may be ''.
    :return: The qrencode executable or '' when it is not installed.
    """
    return configured or shutil.which("qrencode") or ""


class PasswordPanel(QWidget):
    """
    Shows a decrypted entry as rows of fields plus free text.
    """

    # pylint: disable=too-many-instance-attributes

    copy_requested = pyqtSignal(str, str)
    edit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.qrencode = ""
        self.otp_settings = None
        self.otp_code_edit = None
        self.otp_progress = None
        self.otp_timer = QTimer(self)
        self.otp_timer.timeout.connect(self.update_otp)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.fields_widget = QWidget(self)
        self.fields_layout = QFormLayout(self.fields_widget)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.fields_widget)

        self.text_browser = QTextBrowser(self)
        self.text_browser.setReadOnly(True)
        self.text_browser.setOpenLinks(False)
        self.text_browser.anchorClicked.connect(open_web_url)
        layout.addWidget(self.text_browser, 1)

    def clear(self):
        """Remove the shown entry."""
        self.otp_timer.stop()
        self.otp_settings = None
        self.otp_code_edit = None
        self.otp_progress = None
        while self.fields_layout.rowCount():
            self.fields_layout.removeRow(0)
        self.fields_widget.hide()
        self.text_browser.clear()

    def show_message(self, html, font=None):
        """
        Show a message, like the welcome text, instead of an entry.

        :param html: The HTML to show.
        :param font: Optional font for the message.
        """
        self.clear()
        if font is not None:
            self.text_browser.setFont(font)
        self.text_browser.setHtml(html)

    def show_entry(self, content, settings):
        """
        Show a parsed entry.

        :param content: An EntryContent.
        :param settings: The SettingsManager.
        """
        self.clear()
        self.qrencode = (
            find_qrencode(settings.get("qrencode_executable"))
            if settings.get("use_qrencode")
            else ""
        )
        password = content.password_for_display
        if password:
            self.add_row(
                self.tr("Password"),
                password,
                hidden=bool(settings.get("hide_password")),
                is_password=True,
            )
        if settings.get("use_otp") and content.otp:
            self.add_otp_row(content.otp)
        font = QFont("monospace") if settings.get("use_monospace") else QFont()
        font.setStyleHint(
            QFont.StyleHint.Monospace
            if settings.get("use_monospace")
            else QFont.StyleHint.AnyStyle
        )
        self.text_browser.setFont(font)
        self.text_browser.setLineWrapMode(
            QTextBrowser.LineWrapMode.NoWrap
            if settings.get("no_line_wrapping")
            else QTextBrowser.LineWrapMode.WidgetWidth
        )
        if settings.get("hide_content"):
            self.fields_widget.setVisible(self.fields_layout.rowCount() > 0)
            self.text_browser.setHtml(f"<i>{self.tr('Content hidden')}</i>")
            return
        for name, value in content.fields:
            if otp.is_otp_field_name(name) or otp.is_otp_uri(value):
                continue
            self.add_row(name, value)
        self.fields_widget.setVisible(self.fields_layout.rowCount() > 0)
        if settings.get("display_as_is"):
            self.text_browser.setPlainText(content.remaining_display)
        else:
            self.text_browser.setHtml(format_key_html(content.remaining_display))

    def tool_button(self, theme, fallback, tooltip, slot):
        """
        :return: A QToolButton with a themed icon.
        """
        button = QToolButton(self.fields_widget)
        icon = QIcon.fromTheme(theme)
        if icon.isNull():
            icon = self.style().standardIcon(fallback)
        button.setIcon(icon)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.clicked.connect(slot)
        return button

    def add_row(self, name, value, hidden=False, is_password=False):
        """
        Add a field row with a read-only value and action buttons.

        :param name: The field name.
        :param value: The field value.
        :param hidden: Show the value as dots until revealed.
        :param is_password: Whether this row is the password.
        """
        row = QHBoxLayout()
        edit = QLineEdit(value, self.fields_widget)
        edit.setReadOnly(True)
        edit.setAccessibleName(name)
        edit.setCursorPosition(0)
        if hidden:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        row.addWidget(edit, 1)
        if hidden:
            row.addWidget(
                self.tool_button(
                    "view-visible",
                    QStyle.StandardPixmap.SP_DialogYesButton,
                    self.tr("Show password"),
                    lambda: edit.setEchoMode(
                        QLineEdit.EchoMode.Normal
                        if edit.echoMode() == QLineEdit.EchoMode.Password
                        else QLineEdit.EchoMode.Password
                    ),
                )
            )
        what = self.tr("Password") if is_password else name
        row.addWidget(
            self.tool_button(
                "edit-copy",
                QStyle.StandardPixmap.SP_FileDialogContentsView,
                self.tr("Copy {} to clipboard").format(what),
                lambda: self.copy_requested.emit(value, what),
            )
        )
        if not is_password and is_web_url(value):
            row.addWidget(
                self.tool_button(
                    "internet-web-browser",
                    QStyle.StandardPixmap.SP_DirLinkIcon,
                    self.tr("Open {} in browser").format(value),
                    lambda: open_web_url(QUrl(value)),
                )
            )
        if self.qrencode:
            row.addWidget(
                self.tool_button(
                    "view-barcode-qr",
                    QStyle.StandardPixmap.SP_FileDialogDetailedView,
                    self.tr("Show {} as QR code").format(what),
                    lambda: self.show_qr_code(value, what),
                )
            )
        label = QLabel(name, self.fields_widget)
        label.setBuddy(edit)
        self.fields_layout.addRow(label, row)

    def add_otp_row(self, config):
        """
        Add a row with the live one-time password.

        :param config: The otpauth:// URI or base32 secret.
        """
        self.otp_settings = otp.parse(config)
        row = QHBoxLayout()
        if self.otp_settings is None:
            row.addWidget(
                QLabel(self.tr("No valid OTP configuration found"), self.fields_widget)
            )
            self.fields_layout.addRow(self.tr("OTP code"), row)
            return
        self.otp_code_edit = QLineEdit(self.fields_widget)
        self.otp_code_edit.setReadOnly(True)
        self.otp_code_edit.setAccessibleName(self.tr("OTP code"))
        row.addWidget(self.otp_code_edit, 1)
        self.otp_progress = QProgressBar(self.fields_widget)
        self.otp_progress.setRange(0, self.otp_settings.period)
        self.otp_progress.setFormat("%vs")
        self.otp_progress.setMaximumWidth(80)
        row.addWidget(self.otp_progress)
        row.addWidget(
            self.tool_button(
                "edit-copy",
                QStyle.StandardPixmap.SP_FileDialogContentsView,
                self.tr("Copy OTP code to clipboard"),
                lambda: self.copy_requested.emit(
                    self.current_otp_code(), self.tr("OTP code")
                ),
            )
        )
        self.fields_layout.addRow(self.tr("OTP code"), row)
        self.update_otp()
        self.otp_timer.start(1000)

    def current_otp_code(self):
        """
        :return: The current one-time password or '' when none is shown.
        """
        if self.otp_settings is None:
            return ""
        return otp.generate(self.otp_settings)

    def update_otp(self):
        """Refresh the one-time password and its countdown."""
        if self.otp_settings is None or self.otp_code_edit is None:
            self.otp_timer.stop()
            return
        self.otp_code_edit.setText(otp.generate(self.otp_settings))
        self.otp_progress.setValue(otp.seconds_remaining(self.otp_settings))

    def show_qr_code(self, value, what):
        """
        Show a value as QR code, rendered by the qrencode program.

        :param value: The text to encode.
        :param what: Name of the value for the window title.
        """
        qrencode = self.qrencode
        run_task(
            lambda _progress, _cancelled: executor.run(
                [qrencode, "-o", "-", "-t", "PNG", "-s", "8", "-m", "2"],
                input_data=value.encode("utf-8"),
                timeout=30,
            ),
            lambda result, error: self.show_qr_result(what, result, error),
        )

    def show_qr_result(self, what, result, error):
        """
        Show the QR code qrencode rendered on a worker thread.

        :param what: Name of the value for the window title.
        :param result: Tuple of (returncode, stdout, stderr) from qrencode.
        :param error: An exception, if running it failed.
        """
        returncode, stdout, stderr = result if error is None else (-1, b"", b"")
        if error is not None:
            stderr = str(error).encode()
        pixmap = QPixmap()
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("QR code for {}").format(what))
        layout = QVBoxLayout(dialog)
        label = QLabel(dialog)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if returncode == 0 and pixmap.loadFromData(stdout, "PNG"):
            label.setPixmap(pixmap)
        else:
            label.setText(
                self.tr("qrencode failed: {}").format(
                    stderr.decode(errors="replace").strip()
                )
            )
        layout.addWidget(label)
        dialog.exec()

    def mouseDoubleClickEvent(self, event):  # pylint: disable=invalid-name
        """Double-clicking the panel opens the entry for editing."""
        self.edit_requested.emit()
        super().mouseDoubleClickEvent(event)


def open_web_url(url):
    """
    Open a URL in the browser, but only web addresses.

    :param url: The QUrl to open.
    """
    if url.scheme() in ("http", "https"):
        QDesktopServices.openUrl(url)
