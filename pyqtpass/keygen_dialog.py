"""
Dialogs for GPG key management: generating a key pair and exporting your
public key to share with the people a store is shared with.
"""

from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from pyqtpass.gpg_utils import (
    DEFAULT_KEY_TEMPLATE,
    export_public_key,
    generate_key,
    generate_key_batch,
    list_gpg_keys,
    set_batch_parameter,
)
from pyqtpass.tasks import run_task


class KeyGenDialog(QDialog):
    """
    Generate a new GPG key pair. A passphrase has to be typed twice, or
    'No passphrase' ticked on purpose, before OK is enabled.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, parent=None, name="", email=""):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Generate GnuPG key pair"))
        self.task = None
        self.name_edit = QLineEdit(name, self)
        self.email_edit = QLineEdit(email, self)
        self.passphrase_edit = QLineEdit(self)
        self.passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit = QLineEdit(self)
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.no_passphrase = QCheckBox(self.tr("No passphrase"), self)
        self.no_passphrase.setToolTip(
            self.tr("Anyone with access to the key file can then use it")
        )
        self.expert = QCheckBox(self.tr("Expert"), self)
        self.template_edit = QPlainTextEdit(self)
        self.template_edit.setPlainText(DEFAULT_KEY_TEMPLATE)
        self.expert_info = QLabel(
            self.tr(
                # pylint: disable-next=line-too-long
                'For expert options check out the <a href="https://www.gnupg.org/documentation/manuals/gnupg/Unattended-GPG-key-generation.html">GnuPG manual</a>'
            ),
            self,
        )
        self.expert_info.setOpenExternalLinks(True)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.busy = QProgressBar(self)
        self.busy.setRange(0, 0)
        self.busy.hide()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.buttons.accepted.connect(self.generate)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow(self.tr("Name:"), self.name_edit)
        form.addRow(self.tr("E-mail:"), self.email_edit)
        form.addRow(self.tr("Passphrase:"), self.passphrase_edit)
        form.addRow(self.tr("Repeat passphrase:"), self.confirm_edit)
        form.addRow(self.no_passphrase)
        layout.addLayout(form)
        layout.addWidget(self.expert)
        layout.addWidget(self.template_edit)
        layout.addWidget(self.expert_info)
        layout.addWidget(self.status)
        layout.addWidget(self.busy)
        layout.addWidget(self.buttons)
        for widget in (
            self.name_edit,
            self.email_edit,
            self.passphrase_edit,
            self.confirm_edit,
        ):
            widget.textChanged.connect(self.validate)
        self.no_passphrase.toggled.connect(self.validate)
        self.name_edit.textChanged.connect(
            lambda text: self.set_parameter("Name-Real", text)
        )
        self.email_edit.textChanged.connect(
            lambda text: self.set_parameter("Name-Email", text)
        )
        self.expert.toggled.connect(self.set_expert_mode)
        self.set_parameter("Name-Real", name)
        self.set_parameter("Name-Email", email)
        self.set_expert_mode(False)
        self.validate()

    def set_expert_mode(self, checked):
        """
        Show the key generation parameters to edit, like QtPass's expert
        mode. The passphrase is never shown in them: it is added when the
        key is generated.

        :param checked: Whether expert mode is on.
        """
        self.template_edit.setVisible(checked)
        self.expert_info.setVisible(checked)

    def set_parameter(self, key, value):
        """
        Keep the name and e-mail in the parameters in step with the fields.

        :param key: The parameter name.
        :param value: Its value.
        """
        self.template_edit.setPlainText(
            set_batch_parameter(self.template_edit.toPlainText(), key, value.strip())
        )

    def validate(self):
        """Enable OK only when the input is complete."""
        no_passphrase = self.no_passphrase.isChecked()
        self.passphrase_edit.setEnabled(not no_passphrase)
        self.confirm_edit.setEnabled(not no_passphrase)
        message = ""
        if not self.name_edit.text().strip():
            message = self.tr("Enter a name.")
        elif "@" not in self.email_edit.text():
            message = self.tr("Enter an e-mail address.")
        elif not no_passphrase and not self.passphrase_edit.text():
            message = self.tr("Type a passphrase twice, or tick 'No passphrase'.")
        elif not no_passphrase and (
            self.passphrase_edit.text() != self.confirm_edit.text()
        ):
            message = self.tr("The passphrases differ.")
        elif not no_passphrase and any(
            char in self.passphrase_edit.text() for char in "\r\n"
        ):
            message = self.tr("The passphrase cannot contain a line break.")
        self.status.setText(message)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not message)

    def generate(self):
        """Generate the key on a worker thread."""
        name = self.name_edit.text().strip()
        email = self.email_edit.text().strip()
        passphrase = (
            "" if self.no_passphrase.isChecked() else self.passphrase_edit.text()
        )
        self.buttons.setEnabled(False)
        self.expert.setEnabled(False)
        self.template_edit.setReadOnly(True)
        self.busy.show()
        self.status.setText(self.tr("Generating key pair, this can take a while..."))
        batch = self.template_edit.toPlainText() if self.expert.isChecked() else ""
        self.task = run_task(
            lambda _progress, _cancelled: (
                generate_key_batch(batch, passphrase)
                if batch
                else generate_key(name, email, passphrase)
            ),
            self.generated,
        )

    def generated(self, result, error):
        """
        Called when key generation finished.

        :param result: Tuple of (success, output) from generate_key.
        :param error: An exception, if one was raised.
        """
        self.task = None
        self.busy.hide()
        self.buttons.setEnabled(True)
        self.expert.setEnabled(True)
        self.template_edit.setReadOnly(False)
        if error is None and result[0]:
            self.accept()
            return
        QMessageBox.critical(
            self,
            self.tr("Key generation failed"),
            str(error) if error else result[1],
        )
        self.validate()

    def reject(self):
        """Do not close while gpg is still running."""
        if self.task is None:
            super().reject()


class ExportPublicKeyDialog(QDialog):
    """
    Shows the armored public key of one of your secret keys, to send to the
    people who should add you as a recipient.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export public key"))
        self.key_combo = QComboBox(self)
        self.key_text = QPlainTextEdit(self)
        self.key_text.setReadOnly(True)
        for key in list_gpg_keys(secret=True):
            uid = key["uids"][0] if key["uids"] else key["fingerprint"]
            self.key_combo.addItem(uid, key["fingerprint"] or key["id"])
        self.key_combo.currentIndexChanged.connect(self.show_key)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                self.tr(
                    "Send this public key to the people you share a store with, "
                    "so they can add you as a recipient. It does not contain "
                    "anything secret."
                ),
                self,
            )
        )
        layout.addWidget(self.key_combo)
        layout.addWidget(self.key_text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        copy_button = QPushButton(self.tr("Copy to clipboard"), self)
        copy_button.clicked.connect(self.copy_key)
        save_button = QPushButton(self.tr("Save..."), self)
        save_button.clicked.connect(self.save_key)
        buttons.addButton(copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(save_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(600, 450)
        if self.key_combo.count():
            self.show_key()
        else:
            self.key_text.setPlainText(self.tr("You have no secret key yet."))
            copy_button.setEnabled(False)
            save_button.setEnabled(False)

    def show_key(self):
        """Show the armored public key of the selected key."""
        success, text = export_public_key(self.key_combo.currentData())
        if not success:
            text = self.tr("Could not export the public key: {}").format(text)
        self.key_text.setPlainText(text)

    def copy_key(self):
        """Copy the public key to the clipboard."""
        QApplication.clipboard().setText(self.key_text.toPlainText())

    def save_key(self):
        """Save the public key to a file."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save public key"),
            "public-key.asc",
            self.tr("ASCII armored keys (*.asc);;All files (*)"),
        )
        if path:
            with open(path, "w", encoding="utf-8") as key_file:
                key_file.write(self.key_text.toPlainText())
