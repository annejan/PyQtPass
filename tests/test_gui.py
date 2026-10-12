"""Offscreen smoke tests of the main window and dialogs."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument,import-outside-toplevel

import os
import time

import pytest
from PyQt6.QtWidgets import QApplication, QLineEdit

from conftest import TEST_OTP_SEED

OTP_URI = f"otpauth://totp/Test?secret={TEST_OTP_SEED}"


def wait_until(app, condition, timeout=10):
    deadline = time.time() + timeout
    while not condition():
        app.processEvents()
        if time.time() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


@pytest.fixture
def window(qapp, settings, store):
    from pyqtpass.main_window import (
        QtPassGUI,
    )  # pylint: disable=import-outside-toplevel

    settings.set("pass_store", store.store_dir)
    settings.set("use_template", True)
    settings.set("use_tray_icon", False)
    store.set_key("web/site", f"secret\nlogin: me\nurl: https://example.org\n{OTP_URI}")
    store.set_key("other", "pw2\nnote: findme")
    gui = QtPassGUI()
    yield gui
    gui.close()
    gui.deleteLater()
    qapp.processEvents()


def find_index(gui, path):
    from pyqtpass.utilities import PATH_ROLE  # pylint: disable=import-outside-toplevel

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
    assert {"secret", "me", "https://example.org"} <= set(values)
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


def test_clipboard_is_cleared_on_quit(qapp, window):
    # aboutToQuit is a private signal, so the test cannot emit it;
    # disconnecting raises TypeError when clear_clipboard is not connected.
    qapp.aboutToQuit.disconnect(window.clear_clipboard)


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


def wait_for_tasks(app):
    from pyqtpass import tasks  # pylint: disable=import-outside-toplevel

    wait_until(app, lambda: not tasks.running())


def test_move_folder_and_delete(qapp, window, store, monkeypatch):
    window.store.create_folder("archive")
    window.on_move_requested("other", "archive", False)
    wait_for_tasks(qapp)
    assert store.list_dir("archive") == ([], ["other"])
    assert find_index(window, "archive/other") is not None
    window.on_move_requested("archive/other", "", True)
    wait_for_tasks(qapp)
    assert store.is_entry("other") and store.is_entry("archive/other")


def test_dialogs_construct(qapp, window, store):
    # pylint: disable=import-outside-toplevel
    from pyqtpass.config_dialog import ConfigDialog
    from pyqtpass.edit_password_window import EditPasswordDialog
    from pyqtpass.first_run_wizard import FirstRunWizard
    from pyqtpass.keygen_dialog import ExportPublicKeyDialog, KeyGenDialog
    from pyqtpass.users_dialog import UsersDialog

    ConfigDialog(window).save_settings()
    edit = EditPasswordDialog(store, "web/site", "site", parent=window)
    assert [name for name, _ in edit.field_edits] == ["login", "url"]
    assert "login: me" in edit.entry_data()
    assert OTP_URI in edit.entry_data()
    add = EditPasswordDialog(store, "web", "", create=True, parent=window)
    assert add.folder_combo.currentText() == "/web"
    assert add.password_edit.text()
    users = UsersDialog(store, "", window)
    assert users.selected_key_ids()
    keygen = KeyGenDialog(window, "A", "a@example.org")
    assert not keygen.status.text() == ""
    keygen.no_passphrase.setChecked(True)
    assert keygen.status.text() == ""
    assert "PUBLIC KEY" in ExportPublicKeyDialog(window).key_text.toPlainText()
    FirstRunWizard(store.store_dir, window)


def test_reencrypt_in_background(qapp, window, store, key_id, monkeypatch):
    from pyqtpass import tasks  # pylint: disable=import-outside-toplevel

    failures = []
    monkeypatch.setattr(
        "pyqtpass.store_actions.QMessageBox.critical",
        lambda _parent, _title, text: failures.append(text),
    )
    store.create_folder("team")
    store.set_key("team/x", "pw")
    window.run_with_progress(
        "test",
        lambda progress, _cancelled: store.init([key_id], "team", progress=progress),
        "done",
        "failed",
    )
    wait_until(qapp, lambda: not tasks._running)  # pylint: disable=protected-access
    assert not failures
    assert os.path.isfile(os.path.join(store.store_dir, "team", ".gpg-id"))
    assert store.get_key("team/x") == "pw\n"


def test_menu_bar_toggle_and_peek(qapp, window):
    window.actions["show_menu_bar"].setChecked(False)
    assert not window.settings.get("show_menu_bar")
    assert window.menuBar().isHidden()
    window.peek_menu_bar()
    assert not window.menuBar().isHidden() and window.menu_peek
    window.menuBar().setActiveAction(None)
    window.end_menu_peek()
    assert window.menuBar().isHidden()
    window.actions["show_menu_bar"].setChecked(True)
    assert not window.menuBar().isHidden()


def test_signed_profile_store(qapp, window, settings, key_id):
    from pyqtpass.store_setup import (
        make_store,
    )  # pylint: disable=import-outside-toplevel

    settings.set("pass_signing_key", key_id)
    store = make_store(settings)
    assert store.signer.enabled
    store.init([key_id])
    assert os.path.isfile(os.path.join(store.store_dir, ".gpg-id.sig"))
    store.set_key("signed", "pw")
    window.apply_settings()
    assert window.store.signer.enabled
    assert window.store.get_key("signed") == "pw\n"


def test_unchanged_edit_is_not_saved(qapp, window, store):
    from pyqtpass.edit_password_window import (  # pylint: disable=import-outside-toplevel
        EditPasswordDialog,
    )

    before = os.path.getmtime(store.entry_file("other"))
    dialog = EditPasswordDialog(store, "other", "other", parent=window)
    dialog.save()
    assert dialog.result() == 1 and not dialog.saved
    assert os.path.getmtime(store.entry_file("other")) == before
    dialog = EditPasswordDialog(store, "other", "other", parent=window)
    dialog.info_text_edit.setPlainText("changed")
    dialog.save()
    wait_for_tasks(qapp)
    assert dialog.saved
    assert "changed" in store.get_key("other")


def test_copy_password_runs_in_background(qapp, window):
    window.ui.tree_view.setCurrentIndex(find_index(window, "web/site"))
    window.copy_password()
    wait_until(qapp, lambda: QApplication.clipboard().text() == "secret")
