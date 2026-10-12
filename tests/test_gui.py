"""Offscreen smoke tests of the main window and dialogs."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument,import-outside-toplevel

import os

from PyQt6.QtWidgets import QApplication, QLineEdit

from conftest import OTP_URI, find_index, wait_for_tasks, wait_until


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


def test_search_for_fills_the_search_box_and_selects(qapp, window):
    window.search_for("site")
    assert window.ui.filter_text_box.text() == "site"
    assert window.ui.tree_view.currentIndex().isValid()
    assert find_index(window, "other") is None


def test_clipboard_modes(qapp, window, settings):
    from PyQt6.QtWidgets import QToolButton

    from pyqtpass.settings_manager import CLIPBOARD_ALWAYS, CLIPBOARD_NEVER

    def copy_buttons():
        return [
            button
            for button in window.ui.panel.fields_widget.findChildren(QToolButton)
            if "clipboard" in button.toolTip()
        ]

    QApplication.clipboard().clear()
    settings.set("clipboard_mode", CLIPBOARD_NEVER)
    window.ui.tree_view.setCurrentIndex(find_index(window, "other"))
    wait_until(qapp, lambda: window.ui.panel.fields_layout.rowCount() >= 1)
    assert not copy_buttons()
    assert QApplication.clipboard().text() != "pw2"
    settings.set("clipboard_mode", CLIPBOARD_ALWAYS)
    window.ui.tree_view.setCurrentIndex(find_index(window, "web/site"))
    wait_until(qapp, lambda: QApplication.clipboard().text() == "secret")
    assert copy_buttons()


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


def test_edit_pulls_first_and_stops_on_a_conflict(qapp, window, monkeypatch):
    from pyqtpass.password_store import (
        PullConflictError,
    )  # pylint: disable=import-outside-toplevel

    pulls, warnings, opened = [], [], []

    def conflicted():
        pulls.append(True)
        raise PullConflictError("unmerged")

    monkeypatch.setattr(window, "git_enabled", lambda: True)
    monkeypatch.setattr(window.store, "pull_before_change", conflicted)
    monkeypatch.setattr(window, "open_edit_dialog", lambda *args: opened.append(args))
    monkeypatch.setattr(
        "pyqtpass.store_actions.QMessageBox.warning",
        lambda _parent, title, _text: warnings.append(title),
    )
    window.settings.set("git_pull_on_start", False)
    window.edit_item(find_index(window, "other"))
    wait_for_tasks(qapp)
    assert not pulls and len(opened) == 1
    window.settings.set("git_pull_on_start", True)
    window.edit_item(find_index(window, "other"))
    wait_for_tasks(qapp)
    assert pulls and len(opened) == 1
    assert warnings == ["Git pull failed"]


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
