"""Offscreen smoke tests of the main window and dialogs."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument

import time

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QLineEdit

from settings_manager import SettingsManager

OTP_URI = "otpauth://totp/Test?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def wait_until(app, condition, timeout=10):
    deadline = time.time() + timeout
    while not condition():
        app.processEvents()
        if time.time() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


@pytest.fixture
def settings(tmp_path, qapp):
    QSettings.setPath(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    SettingsManager._instance = None  # pylint: disable=protected-access
    manager = SettingsManager()
    yield manager
    SettingsManager._instance = None  # pylint: disable=protected-access


@pytest.fixture
def window(qapp, settings, store):
    from pyqtpass import QtPassGUI  # pylint: disable=import-outside-toplevel

    settings.set("pass_store", store.store_dir)
    settings.set("use_template", True)
    settings.set("use_tray_icon", False)
    store.set_key("web/site", f"secret\nlogin: me\nurl: https://example.org\n{OTP_URI}")
    store.set_key("other", "pw2\nnote: findme")
    gui = QtPassGUI()
    yield gui
    gui.close()


def find_index(gui, path):
    from utilities import PATH_ROLE  # pylint: disable=import-outside-toplevel

    model = gui.ui.proxy_model
    pending = [model.index(row, 0) for row in range(model.rowCount())]
    while pending:
        index = pending.pop()
        if index.data(PATH_ROLE) == path:
            return index
        pending += [model.index(row, 0, index) for row in range(model.rowCount(index))]
    return None


def test_open_entry_shows_fields_and_otp(qapp, window):
    index = find_index(window, "web/site")
    assert index is not None
    window.ui.tree_view.setCurrentIndex(index)
    panel = window.ui.panel
    wait_until(qapp, lambda: panel.fields_layout.rowCount() >= 4)
    values = [edit.text() for edit in panel.fields_widget.findChildren(QLineEdit)]
    assert "secret" in values and "me" in values and "https://example.org" in values
    code = panel.current_otp_code()
    assert len(code) == 6 and code in values
    assert OTP_URI not in panel.text_browser.toPlainText()


def test_clipboard_is_marked_secret_and_cleared(qapp, window):
    window.copy_text_to_clipboard("topsecret")
    mime = QApplication.clipboard().mimeData()
    assert mime.text() == "topsecret"
    assert bytes(mime.data("x-kde-passwordManagerHint")) == b"secret"
    window.clear_clipboard()
    assert QApplication.clipboard().text() != "topsecret"


def test_filter_and_content_search(qapp, window):
    window.ui.filter_text_box.setText("web si")
    assert find_index(window, "web/site") is not None
    assert find_index(window, "other") is None
    window.settings.set("use_grep_search", True)
    window.ui.filter_text_box.setText("findme")
    window.on_search_return()
    wait_until(qapp, lambda: window.search_task is None)
    assert find_index(window, "other") is not None
    assert find_index(window, "web/site") is None


def test_move_folder_and_delete(qapp, window, store, monkeypatch):
    window.store.create_folder("archive")
    window.on_move_requested("other", "archive", False)
    assert store.list_dir("archive") == ([], ["other"])
    assert find_index(window, "archive/other") is not None
    window.on_move_requested("archive/other", "", True)
    assert store.is_entry("other") and store.is_entry("archive/other")


def test_dialogs_construct(qapp, window, store):
    # pylint: disable=import-outside-toplevel
    from config_dialog import ConfigDialog
    from edit_password_window import EditPasswordDialog
    from first_run_wizard import FirstRunWizard
    from keygen_dialog import ExportPublicKeyDialog, KeyGenDialog
    from users_dialog import UsersDialog

    ConfigDialog(window).save_settings()
    edit = EditPasswordDialog(store, "web/site", "site", parent=window)
    assert [name for name, _ in edit.field_edits] == ["login", "url"]
    assert "login: me" in edit.entry_data()
    assert OTP_URI in edit.entry_data()
    add = EditPasswordDialog(store, "web", "", create=True, parent=window)
    assert add.folder_combo.currentText() == "/web"
    assert add.password_edit.text()
    users = UsersDialog(store.store_dir, "", window)
    assert users.selected_key_ids()
    keygen = KeyGenDialog(window, "A", "a@example.org")
    assert not keygen.status.text() == ""
    keygen.no_passphrase.setChecked(True)
    assert keygen.status.text() == ""
    assert "PUBLIC KEY" in ExportPublicKeyDialog(window).key_text.toPlainText()
    FirstRunWizard(store.store_dir, window)


def test_users_dialog_reencrypts(qapp, window, store, key_id):
    store.create_folder("team")
    store.set_key("team/x", "pw")
    window.ui.tree_view.clearSelection()
    window.run_with_progress(
        "test",
        lambda progress, _cancelled: store.init([key_id], "team", progress=progress),
        "done",
        "failed",
    )
    wait_until(qapp, lambda: store.recipients("team") == [key_id])
    assert store.get_key("team/x") == "pw\n"
