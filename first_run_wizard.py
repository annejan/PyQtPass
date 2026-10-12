"""
The first-run wizard, shown when the password store is not set up yet,
like the QtPass 2.0 onboarding: pick or generate a key, pick the store
folder and optionally put it under Git.
"""

import os
import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

import git_utils
from gpg_utils import key_problem, list_gpg_keys, which_gpg
from keygen_dialog import KeyGenDialog
from password_store import PasswordStore, StoreError


class IntroPage(QWizardPage):  # pylint: disable=too-few-public-methods
    """Explains what is going to happen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle(self.tr("Welcome to PyQtPass"))
        layout = QVBoxLayout(self)
        text = QLabel(
            self.tr(
                "PyQtPass is a graphical front-end for <i>pass</i>, the standard "
                "Unix password manager. Every password is a file encrypted with "
                "GnuPG.<br><br>This wizard sets up a password store: it needs a "
                "GnuPG key to encrypt to and a folder to keep the passwords in."
            ),
            self,
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        if not shutil.which(which_gpg()):
            warning = QLabel(
                self.tr(
                    "<b>GnuPG was not found.</b> Install it (gpg or gpg2) and "
                    "start PyQtPass again."
                ),
                self,
            )
            warning.setWordWrap(True)
            layout.addWidget(warning)


class KeyPage(QWizardPage):
    """Pick the keys to encrypt to, or generate one."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle(self.tr("Your key"))
        self.setSubTitle(
            self.tr(
                "Passwords are encrypted to GnuPG keys. Tick the keys that "
                "should be able to read them."
            )
        )
        self.key_list = QListWidget(self)
        self.key_list.itemChanged.connect(lambda _item: self.completeChanged.emit())
        self.empty_label = QLabel(
            self.tr("GnuPG has no secret key yet. Generate one here."), self
        )
        generate = QPushButton(self.tr("Generate a new key pair..."), self)
        generate.clicked.connect(self.generate)
        layout = QVBoxLayout(self)
        layout.addWidget(self.key_list)
        layout.addWidget(self.empty_label)
        layout.addWidget(generate, 0, Qt.AlignmentFlag.AlignLeft)
        self.populate()

    def populate(self, check_fingerprint=None):
        """
        List the usable secret keys.

        :param check_fingerprint: A fingerprint to tick, e.g. a new key.
        """
        checked = set(self.selected_keys())
        if check_fingerprint:
            checked.add(check_fingerprint)
        self.key_list.blockSignals(True)
        self.key_list.clear()
        keys = [key for key in list_gpg_keys(secret=True) if not key_problem(key)]
        for key in keys:
            uid = key["uids"][0] if key["uids"] else key["fingerprint"]
            item = QListWidgetItem(f"{uid} ({key['id']})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            fingerprint = key["fingerprint"] or key["id"]
            item.setData(Qt.ItemDataRole.UserRole, fingerprint)
            tick = fingerprint in checked or len(keys) == 1
            item.setCheckState(
                Qt.CheckState.Checked if tick else Qt.CheckState.Unchecked
            )
            self.key_list.addItem(item)
        self.key_list.blockSignals(False)
        self.empty_label.setVisible(not keys)
        self.completeChanged.emit()

    def selected_keys(self):
        """:return: The fingerprints of the ticked keys."""
        return [
            self.key_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.key_list.count())
            if self.key_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def generate(self):
        """Generate a key pair and tick it."""
        before = {key["fingerprint"] for key in list_gpg_keys(secret=True)}
        if KeyGenDialog(self).exec():
            new = [
                key["fingerprint"]
                for key in list_gpg_keys(secret=True)
                if key["fingerprint"] not in before
            ]
            self.populate(new[0] if new else None)

    def isComplete(self):  # pylint: disable=invalid-name
        """At least one key has to be ticked."""
        return bool(self.selected_keys())


class StorePage(QWizardPage):
    """Pick the store folder and set it up."""

    def __init__(self, store_dir, key_page, parent=None, store_factory=None):
        super().__init__(parent)
        self.key_page = key_page
        self.store_factory = store_factory or (
            lambda path: PasswordStore(path, use_git=False)
        )
        self.setTitle(self.tr("Password store"))
        self.setSubTitle(
            self.tr(
                "The folder your passwords live in. An existing store is "
                "used as it is."
            )
        )
        self.path_edit = QLineEdit(os.path.expanduser(store_dir), self)
        self.path_edit.textChanged.connect(self.describe)
        browse = QToolButton(self)
        browse.setText("...")
        browse.setToolTip(self.tr("Browse"))
        browse.clicked.connect(self.browse)
        self.use_git = QCheckBox(self.tr("Keep the store under Git"), self)
        self.use_git.setEnabled(shutil.which(git_utils.git_executable()) is not None)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse)
        layout = QVBoxLayout(self)
        layout.addLayout(path_row)
        layout.addWidget(self.use_git)
        layout.addWidget(self.status)
        layout.addStretch(1)
        self.describe()

    def store_dir(self):
        """:return: The chosen store folder."""
        return os.path.abspath(os.path.expanduser(self.path_edit.text().strip()))

    def browse(self):
        """Pick the folder with a file dialog."""
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Choose the password store folder"), self.store_dir()
        )
        if path:
            self.path_edit.setText(path)

    def describe(self):
        """Say what will happen to the chosen folder."""
        path = self.store_dir()
        store = PasswordStore(path, use_git=False)
        if not self.path_edit.text().strip():
            text = self.tr("Enter a folder.")
        elif store.is_initialised():
            text = self.tr("An existing password store; it is used as it is.")
        elif os.path.isdir(path) and store.has_entries():
            text = self.tr(
                "This folder holds passwords but no .gpg-id; they will be "
                "re-encrypted for the ticked keys."
            )
        elif os.path.isdir(path):
            text = self.tr("The folder will be set up as a password store.")
        else:
            text = self.tr("The folder does not exist yet; it will be created.")
        if git_utils.is_git_repo(path):
            self.use_git.setChecked(True)
        self.status.setText(text)
        self.completeChanged.emit()

    def isComplete(self):  # pylint: disable=invalid-name
        """A folder has to be entered."""
        return bool(self.path_edit.text().strip())

    def validatePage(self):  # pylint: disable=invalid-name
        """Set the store up; stay on the page when that fails."""
        store = self.store_factory(self.store_dir())
        store.use_git = self.use_git.isChecked()
        try:
            os.makedirs(store.store_dir, exist_ok=True)
            if self.use_git.isChecked() and not git_utils.is_git_repo(store.store_dir):
                success, output = git_utils.git_init(store.store_dir)
                if not success:
                    raise StoreError(output)
            if not store.is_initialised():
                store.init(self.key_page.selected_keys())
        except (OSError, StoreError) as error:
            QMessageBox.critical(
                self,
                self.tr("Password store not initialised"),
                self.tr("Failed to set up the password store at {}:\n{}").format(
                    store.store_dir, error
                ),
            )
            return False
        return True


class FirstRunWizard(QWizard):
    """The wizard tying the pages together."""

    def __init__(self, store_dir, parent=None, store_factory=None):
        """
        :param store_dir: The suggested store folder.
        :param parent: The parent widget.
        :param store_factory: Callable(path) opening a store with the
                              configured backend and signing keys.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Welcome to PyQtPass"))
        self.addPage(IntroPage(self))
        self.key_page = KeyPage(self)
        self.addPage(self.key_page)
        self.store_page = StorePage(store_dir, self.key_page, self, store_factory)
        self.addPage(self.store_page)
        self.resize(600, 450)

    def store_dir(self):
        """:return: The folder that was set up."""
        return self.store_page.store_dir()

    def use_git(self):
        """:return: Whether the store should be used with Git."""
        return self.store_page.use_git.isChecked()
