"""Tests of the dialog that picks the keys a folder is encrypted for."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument,import-outside-toplevel,too-few-public-methods

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from pyqtpass import gpg_utils
from pyqtpass.password_store import StoreError
from pyqtpass.users_dialog import UsersDialog

MISSING = "0123456789ABCDEF0123456789ABCDEF01234567"


@pytest.fixture
def boxes(monkeypatch):
    """Record the message boxes, answering questions with No."""

    class Boxes:
        """What was shown, and how questions are answered."""

        shown = []
        answer = QMessageBox.StandardButton.No

    def record(kind):
        def show(_parent, title, _text):
            Boxes.shown.append((kind, title))
            return Boxes.answer

        return show

    for kind in ("information", "warning", "question"):
        monkeypatch.setattr(f"pyqtpass.users_dialog.QMessageBox.{kind}", record(kind))
    return Boxes


def labels(dialog):
    return " ".join(label.text() for label in dialog.findChildren(QLabel))


def items(dialog):
    return {
        dialog.key_list.item(row).data(Qt.ItemDataRole.UserRole): dialog.key_list.item(
            row
        )
        for row in range(dialog.key_list.count())
    }


def with_recipients(store, *ids):
    with open(store.absolute(".gpg-id"), "w", encoding="utf-8") as gpg_id:
        gpg_id.write("\n".join(ids) + "\n")


def test_current_recipients_are_ticked(qapp, store, key_id):
    dialog = UsersDialog(store, "")
    assert dialog.windowTitle() == "Users for /"
    assert dialog.selected_key_ids() == [key_id]
    assert "[your key]" in items(dialog)[key_id].text()


def test_recipient_without_a_key_is_kept(qapp, store, key_id):
    with_recipients(store, key_id, MISSING)
    dialog = UsersDialog(store, "")
    assert set(dialog.selected_key_ids()) == {key_id, MISSING}
    assert items(dialog)[MISSING].text().endswith("[key not in keyring]")


def test_subfolder_shows_where_its_keys_come_from(qapp, store):
    store.create_folder("team")
    dialog = UsersDialog(store, "team")
    assert "This folder now uses the keys of /" in labels(dialog)


def test_untrusted_list_preselects_nothing(qapp, store, monkeypatch):
    def untrusted(_folder):
        raise StoreError("bad signature")

    monkeypatch.setattr(store, "recipient_list", untrusted)
    dialog = UsersDialog(store, "")
    assert "The current recipient list is not used: bad signature" in labels(dialog)
    assert not dialog.selected_key_ids()


def test_filter_hides_other_keys(qapp, store, key_id):
    dialog = UsersDialog(store, "")
    dialog.filter_edit.setText("PYQTPASS TEST")
    assert not items(dialog)[key_id].isHidden()
    dialog.filter_edit.setText("nobody")
    assert all(item.isHidden() for item in items(dialog).values())


def test_ticks_survive_showing_all_keys(qapp, store, key_id):
    dialog = UsersDialog(store, "")
    items(dialog)[key_id].setCheckState(Qt.CheckState.Unchecked)
    dialog.show_all.setChecked(True)
    assert not dialog.selected_key_ids()


def test_save_needs_a_key(qapp, store, key_id, boxes):
    dialog = UsersDialog(store, "")
    items(dialog)[key_id].setCheckState(Qt.CheckState.Unchecked)
    dialog.save()
    assert boxes.shown == [("warning", "No keys selected")]
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_save_warns_when_none_of_your_keys_is_ticked(qapp, store, key_id, boxes):
    with_recipients(store, key_id, MISSING)
    dialog = UsersDialog(store, "")
    items(dialog)[key_id].setCheckState(Qt.CheckState.Unchecked)
    dialog.save()
    assert boxes.shown == [("question", "None of your keys selected")]
    assert not dialog.selected_ids
    boxes.answer = QMessageBox.StandardButton.Yes
    dialog.save()
    assert dialog.selected_ids == [MISSING]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_save_with_your_key(qapp, store, key_id, boxes):
    dialog = UsersDialog(store, "")
    dialog.save()
    assert not boxes.shown
    assert dialog.selected_ids == [key_id]


def test_import_from_clipboard(qapp, store, key_id, boxes):
    dialog = UsersDialog(store, "")
    QApplication.clipboard().setText("not a key")
    dialog.import_from_clipboard()
    assert boxes.shown == [("warning", "Import failed")]
    ok, armored = gpg_utils.export_public_key(key_id)
    assert ok
    QApplication.clipboard().setText(armored)
    dialog.import_from_clipboard()
    assert boxes.shown[-1] == ("information", "Keys imported")
    assert dialog.selected_key_ids() == [key_id]


def test_import_from_file(qapp, store, boxes, tmp_path, monkeypatch):
    broken = tmp_path / "broken.asc"
    broken.write_text(
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\ngarbage\n"
        "-----END PGP PUBLIC KEY BLOCK-----\n"
    )
    answers = [(str(broken), ""), ("", "")]
    monkeypatch.setattr(
        "pyqtpass.users_dialog.QFileDialog.getOpenFileName",
        lambda *_args: answers.pop(0),
    )
    dialog = UsersDialog(store, "")
    dialog.import_from_file()
    assert boxes.shown == [("warning", "Import failed")]
    dialog.import_from_file()
    assert len(boxes.shown) == 1


def test_generated_key_is_listed(qapp, store, monkeypatch):
    shown = []

    class Generated:
        """A key generation dialog that is accepted."""

        def __init__(self, _parent):
            pass

        def exec(self):
            shown.append(True)
            return QDialog.DialogCode.Accepted

    dialog = UsersDialog(store, "")
    monkeypatch.setattr("pyqtpass.users_dialog.KeyGenDialog", Generated)
    populated = []
    monkeypatch.setattr(dialog, "populate_keys", lambda: populated.append(True))
    dialog.generate_key()
    assert shown and populated
