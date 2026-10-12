"""
The profiles page of the configuration dialog: a list of profiles with a
form for the selected one, like QtPass 2.0. A profile has its own store
folder and can have its own signing key and Git behaviour.
"""

from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pyqtpass.gpgid_trust import is_fingerprint
from pyqtpass.settings_manager import PROFILE_OVERRIDES, profile_options


class ProfilesEditor(QWidget):
    """
    Edits the profiles: name to options (path, signing key, git overrides).
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.loading = False
        self.profile_list = QListWidget(self)
        self.name_edit = QLineEdit(self)
        self.path_edit = QLineEdit(self)
        self.signing_edit = QLineEdit(self)
        self.signing_edit.setPlaceholderText(self.tr("As configured in System"))
        self.signing_edit.setToolTip(
            self.tr(
                "Full fingerprints of the keys that sign the .gpg-id files of "
                "this store, separated by spaces"
            )
        )
        self.override_boxes = {}
        self.problem = QLabel(self)
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #c0392b")

        add_button = QPushButton(self.tr("Add"), self)
        add_button.clicked.connect(self.add_profile)
        remove_button = QPushButton(self.tr("Remove"), self)
        remove_button.clicked.connect(self.remove_profile)
        list_buttons = QHBoxLayout()
        list_buttons.addWidget(add_button)
        list_buttons.addWidget(remove_button)
        left = QVBoxLayout()
        left.addWidget(self.profile_list)
        left.addLayout(list_buttons)

        browse = QToolButton(self)
        browse.setText("...")
        browse.setToolTip(self.tr("Browse"))
        browse.clicked.connect(self.browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse)

        self.form = QFormLayout()
        self.form.addRow(self.tr("Name:"), self.name_edit)
        self.form.addRow(self.tr("Folder:"), path_row)
        self.form.addRow(self.tr("Signing key:"), self.signing_edit)
        self.add_override_rows()
        right = QVBoxLayout()
        right.addLayout(self.form)
        right.addWidget(self.problem)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

        for edit in (self.name_edit, self.path_edit, self.signing_edit):
            edit.textChanged.connect(self.store_form)
        self.profile_list.currentRowChanged.connect(self.show_form)
        self.show_form(-1)

    def add_override_rows(self):
        """Add a Yes/No/As configured choice per overridable setting."""
        labels = {
            "use_git": self.tr("Use Git:"),
            "auto_push": self.tr("Automatically push:"),
            "git_pull_on_start": self.tr("Pull on startup:"),
        }
        for key in PROFILE_OVERRIDES:
            box = QComboBox(self)
            box.addItems([self.tr("As configured"), self.tr("Yes"), self.tr("No")])
            box.currentIndexChanged.connect(self.store_form)
            self.override_boxes[key] = box
            self.form.addRow(labels[key], box)

    def set_profiles(self, profiles):
        """
        :param profiles: Dict of name to stored profile.
        """
        self.data = [
            {"name": name, **profile_options(value)}
            for name, value in sorted(profiles.items())
        ]
        self.profile_list.clear()
        self.profile_list.addItems([entry["name"] for entry in self.data])
        if self.data:
            self.profile_list.setCurrentRow(0)

    def profiles(self):
        """
        :return: Dict of name to profile options; nameless or pathless
                 profiles are left out.
        """
        result = {}
        for entry in self.data:
            name = entry["name"].strip()
            if name and entry["path"].strip():
                options = {key: value for key, value in entry.items() if key != "name"}
                options["path"] = options["path"].strip()
                options["signing_key"] = " ".join(options["signing_key"].split())
                result[name] = options
        return result

    def validation_error(self):
        """
        :return: Why the profiles cannot be saved, or ''.
        """
        names = [entry["name"].strip() for entry in self.data]
        for entry in self.data:
            name = entry["name"].strip() or self.tr("(unnamed)")
            if not entry["name"].strip():
                return self.tr("Every profile needs a name.")
            if names.count(entry["name"].strip()) > 1:
                return self.tr("There are two profiles named {}.").format(name)
            if not entry["path"].strip():
                return self.tr("Profile {} needs a folder.").format(name)
            if not all(is_fingerprint(key) for key in entry["signing_key"].split()):
                return self.tr(
                    "The signing key of profile {} must be full fingerprints "
                    "(40 or 64 hexadecimal digits)."
                ).format(name)
        return ""

    def show_form(self, row):
        """
        Show the selected profile in the form.

        :param row: The selected row, -1 for none.
        """
        self.loading = True
        enabled = 0 <= row < len(self.data)
        entry = self.data[row] if enabled else profile_options("")
        self.name_edit.setText(entry.get("name", ""))
        self.path_edit.setText(entry["path"])
        self.signing_edit.setText(entry["signing_key"])
        for key, box in self.override_boxes.items():
            value = entry.get(key)
            box.setCurrentIndex(0 if value is None else (1 if value else 2))
        for row_index in range(self.form.rowCount()):
            for role in (
                QFormLayout.ItemRole.LabelRole,
                QFormLayout.ItemRole.FieldRole,
            ):
                item = self.form.itemAt(row_index, role)
                if item is not None and item.widget() is not None:
                    item.widget().setEnabled(enabled)
        self.path_edit.setEnabled(enabled)
        self.loading = False
        self.problem.setText(self.validation_error())

    def store_form(self):
        """Copy the form into the selected profile."""
        row = self.profile_list.currentRow()
        if self.loading or not 0 <= row < len(self.data):
            return
        entry = self.data[row]
        entry["name"] = self.name_edit.text()
        entry["path"] = self.path_edit.text()
        entry["signing_key"] = self.signing_edit.text()
        for key, box in self.override_boxes.items():
            entry[key] = [None, True, False][box.currentIndex()]
        self.profile_list.item(row).setText(entry["name"])
        self.problem.setText(self.validation_error())

    def add_profile(self):
        """Add a profile and pick its folder."""
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select password store directory")
        )
        if not path:
            return
        names = {entry["name"] for entry in self.data}
        number = len(self.data) + 1
        while self.tr("Profile {}").format(number) in names:
            number += 1
        name = self.tr("Profile {}").format(number)
        self.data.append({"name": name, **profile_options(path)})
        self.profile_list.addItem(name)
        self.profile_list.setCurrentRow(len(self.data) - 1)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def remove_profile(self):
        """Remove the selected profile."""
        row = self.profile_list.currentRow()
        if 0 <= row < len(self.data):
            del self.data[row]
            self.profile_list.takeItem(row)
            self.show_form(self.profile_list.currentRow())

    def browse(self):
        """Pick the folder of the selected profile."""
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select password store directory"), self.path_edit.text()
        )
        if path:
            self.path_edit.setText(path)
