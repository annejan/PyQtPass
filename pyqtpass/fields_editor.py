"""
The fields of a password entry in the password dialog, like QtPass 2.0:
template fields have a fixed name, every other field has an editable name
and a button to remove it, and fields can be added.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def field_rows(template_fields, fields):
    """
    Decide which field inputs the dialog shows: one per template field,
    filled from the entry when it has that field, then one for every other
    field of the entry. Repeated fields each keep their own input.

    :param template_fields: The template field names.
    :param fields: List of (name, value) tuples parsed from the entry.
    :return: List of (name, value, is_template) tuples.
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
        rows.append((name, value, True))
    return rows + [(name, value, False) for name, value in remaining]


class FieldsEditor(QWidget):
    """
    Edits the 'name: value' fields of an entry.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.form = QFormLayout()
        self.form.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.form)
        add_button = QPushButton(self.tr("Add field"), self)
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.clicked.connect(lambda: self.add_field(focus=True))
        buttons = QHBoxLayout()
        buttons.addWidget(add_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def set_fields(self, template_fields, fields):
        """
        Show the fields of an entry for a template.

        :param template_fields: The template field names.
        :param fields: List of (name, value) tuples.
        """
        while self.form.rowCount():
            self.form.removeRow(0)
        self.rows = []
        for name, value, is_template in field_rows(template_fields, fields):
            if is_template:
                self.add_template_field(name, value)
            else:
                self.add_field(name, value)

    def add_template_field(self, name, value=""):
        """
        Add a field whose name the template fixes.

        :param name: The field name.
        :param value: The field value.
        """
        edit = QLineEdit(value, self)
        edit.setAccessibleName(name)
        edit.textChanged.connect(self.changed.emit)
        self.form.addRow(QLabel(f"{name}:", self), edit)
        self.rows.append({"name": name, "name_edit": None, "value_edit": edit})

    def add_field(self, name="", value="", focus=False):
        """
        Add a field with an editable name and a remove button.

        :param name: The field name.
        :param value: The field value.
        :param focus: Put the cursor in the name.
        """
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        name_edit = QLineEdit(name, row)
        name_edit.setPlaceholderText(self.tr("Name"))
        name_edit.setAccessibleName(self.tr("Field name"))
        name_edit.setMaximumWidth(160)
        value_edit = QLineEdit(value, row)
        value_edit.setPlaceholderText(self.tr("Value"))
        value_edit.setAccessibleName(name or self.tr("Field value"))
        remove = QToolButton(row)
        icon = QIcon.fromTheme("list-remove")
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton)
        remove.setIcon(icon)
        remove.setToolTip(self.tr("Remove this field"))
        remove.setAccessibleName(self.tr("Remove this field"))
        layout.addWidget(name_edit)
        layout.addWidget(value_edit, 1)
        layout.addWidget(remove)
        entry = {"name": None, "name_edit": name_edit, "value_edit": value_edit}
        remove.clicked.connect(lambda: self.remove_field(row, entry))
        name_edit.textChanged.connect(self.changed.emit)
        value_edit.textChanged.connect(self.changed.emit)
        self.form.addRow(row)
        self.rows.append(entry)
        if focus:
            name_edit.setFocus()

    def remove_field(self, row, entry):
        """
        Remove a field.

        :param row: The row widget.
        :param entry: The row's entry in self.rows.
        """
        self.rows.remove(entry)
        self.form.removeRow(row)
        self.changed.emit()

    @staticmethod
    def field_name(entry):
        """
        :param entry: A row of self.rows.
        :return: The field name the row has now.
        """
        if entry["name_edit"] is None:
            return entry["name"]
        return entry["name_edit"].text().strip()

    def problem(self):
        """
        :return: Why the fields cannot be saved as 'name: value' lines, or ''.
        """
        for entry in self.rows:
            name = self.field_name(entry)
            if ":" in name:
                return self.tr("A field name cannot contain ':' ({}).").format(name)
            if not name and entry["value_edit"].text().strip():
                return self.tr("A field with a value needs a name.")
        return ""

    def fields(self):
        """
        :return: List of (name, value) tuples; rows without a name and value
                 are left out.
        """
        return [
            (self.field_name(entry), entry["value_edit"].text().strip())
            for entry in self.rows
            if self.field_name(entry)
        ]

    def template_names(self):
        """:return: The names of the fixed (template) fields, in order."""
        return [entry["name"] for entry in self.rows if entry["name_edit"] is None]
