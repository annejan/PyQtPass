"""Tests of the main window actions that change the password store."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument,import-outside-toplevel,too-few-public-methods

import pytest
from PyQt6.QtWidgets import QDialog, QMenu, QMessageBox

from conftest import find_index, wait_for_tasks
from pyqtpass.password_store import CommitError

YES = QMessageBox.StandardButton.Yes
NO = QMessageBox.StandardButton.No


@pytest.fixture
def answers(monkeypatch):
    """
    Scripted answers for the input dialogs and message boxes, and a record
    of the messages shown.
    """

    class Answers:
        """What the user types and clicks, and what they are shown."""

        text = ("", False)
        question = NO
        warnings = []
        criticals = []

    def get_text(_parent, _title, _label, text=""):
        Answers.prompted = text
        return Answers.text

    Answers.warnings, Answers.criticals = [], []
    monkeypatch.setattr("pyqtpass.store_actions.QInputDialog.getText", get_text)
    monkeypatch.setattr(
        "pyqtpass.store_actions.QMessageBox.question",
        lambda *_args: Answers.question,
    )
    monkeypatch.setattr(
        "pyqtpass.store_actions.QMessageBox.warning",
        lambda _parent, title, text: Answers.warnings.append((title, text)),
    )
    monkeypatch.setattr(
        "pyqtpass.store_actions.QMessageBox.critical",
        lambda _parent, title, text: Answers.criticals.append((title, text)),
    )
    return Answers


def status(window):
    return window.statusBar().currentMessage()


def test_rename_entry(qapp, window, store, answers):
    answers.text = ("  /renamed/ ", True)
    window.rename_item(find_index(window, "other"))
    wait_for_tasks(qapp)
    assert answers.prompted == "other"
    assert store.is_entry("renamed") and not store.is_entry("other")
    assert find_index(window, "renamed") is not None
    assert status(window) == "Renamed other to renamed"


def test_rename_folder(qapp, window, store, answers):
    answers.text = ("sites", True)
    window.rename_item(find_index(window, "web"))
    wait_for_tasks(qapp)
    assert store.is_entry("sites/site") and not store.is_folder("web")


@pytest.mark.parametrize("text", [("x", False), ("", True), ("other", True)])
def test_rename_cancelled_or_unchanged(qapp, window, store, answers, text):
    answers.text = text
    window.rename_item(find_index(window, "other"))
    wait_for_tasks(qapp)
    assert store.list_dir("") == (["web"], ["other"])


def test_rename_without_selection(qapp, window, answers):
    window.rename_item()
    window.delete_item()
    assert status(window) == "No password selected"


def test_rename_onto_an_existing_entry_fails(qapp, window, store, answers):
    answers.text = ("web/site", True)
    window.rename_item(find_index(window, "other"))
    wait_for_tasks(qapp)
    assert [title for title, _ in answers.warnings] == ["Rename failed"]
    assert store.get_key("other") == "pw2\nnote: findme\n"
    assert status(window) == ""


def test_change_that_is_not_committed_still_refreshes(
    qapp, window, store, answers, monkeypatch
):
    def uncommitted(old, new):
        store.set_key(new, "moved")
        raise CommitError("commit failed")

    monkeypatch.setattr(window.store, "move_path", uncommitted)
    answers.text = ("moved", True)
    window.rename_item(find_index(window, "other"))
    wait_for_tasks(qapp)
    assert answers.warnings == [("Not committed", "commit failed")]
    assert find_index(window, "moved") is not None
    assert status(window) == "Renamed other to moved"


def test_duplicate_entry(qapp, window, store, answers):
    answers.text = ("copy", True)
    window.duplicate_item(find_index(window, "web/site"))
    wait_for_tasks(qapp)
    assert answers.prompted == "web/site-copy"
    assert store.get_key("copy") == store.get_key("web/site")
    assert store.is_entry("web/site")


def test_duplicate_needs_an_entry_and_a_new_name(qapp, window, store, answers):
    window.duplicate_item(find_index(window, "web"))
    answers.text = ("other", True)
    window.duplicate_item(find_index(window, "other"))
    wait_for_tasks(qapp)
    assert store.list_dir("") == (["web"], ["other"])


def test_delete_entry_asks_first(qapp, window, store, answers):
    window.ui.tree_view.setCurrentIndex(find_index(window, "other"))
    answers.question = NO
    window.delete_item()
    wait_for_tasks(qapp)
    assert store.is_entry("other")
    answers.question = YES
    window.delete_item()
    wait_for_tasks(qapp)
    assert not store.is_entry("other")
    assert find_index(window, "other") is None
    assert status(window) == "Deleted other"


def test_delete_folder_removes_its_contents(qapp, window, store, answers):
    answers.question = YES
    window.delete_item(find_index(window, "web"))
    wait_for_tasks(qapp)
    assert not store.is_folder("web") and not store.is_entry("web/site")


def test_add_folder_in_the_selected_folder(qapp, window, store, answers):
    answers.text = (" /new/ ", True)
    window.add_folder(find_index(window, "web/site"))
    wait_for_tasks(qapp)
    assert store.is_folder("web/new")
    assert status(window) == "Added folder web/new"


def test_add_folder_cancelled(qapp, window, store, answers):
    answers.text = ("new", False)
    window.add_folder()
    answers.text = (" / ", True)
    window.add_folder()
    wait_for_tasks(qapp)
    assert store.list_dir("") == (["web"], ["other"])


class FakeDialog:
    """Stands in for a modal dialog: accepted, with given attributes."""

    calls = []

    def __init__(self, *args, **kwargs):
        FakeDialog.calls.append((args, kwargs))
        self.path = "web/added"
        self.saved = True
        self.selected_ids = []

    def exec(self):
        return QDialog.DialogCode.Accepted


def test_add_item_reports_the_new_entry(qapp, window, monkeypatch):
    FakeDialog.calls = []
    monkeypatch.setattr("pyqtpass.store_actions.EditPasswordDialog", FakeDialog)
    window.add_item(find_index(window, "web"))
    assert len(FakeDialog.calls) == 1
    args, kwargs = FakeDialog.calls[0]
    assert args[1:] == ("web", "") and kwargs["create"]
    assert status(window) == "Added password web/added"


def test_edit_item_opens_the_decrypted_entry(qapp, window, monkeypatch):
    FakeDialog.calls = []
    monkeypatch.setattr("pyqtpass.store_actions.EditPasswordDialog", FakeDialog)
    window.edit_item(find_index(window, "other"))
    wait_for_tasks(qapp)
    assert len(FakeDialog.calls) == 1
    args, kwargs = FakeDialog.calls[0]
    assert args[1:] == ("other", "other")
    assert kwargs["data"] == "pw2\nnote: findme\n"
    assert status(window) == "Saved password other"


def test_edit_item_reports_errors(qapp, window, store, answers, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "open_edit_dialog", lambda *args: opened.append(args))
    index = find_index(window, "other")
    store.remove_path("other")
    window.edit_item(index)
    wait_for_tasks(qapp)
    assert not answers.warnings

    def broken(_path):
        raise ValueError("bad data")

    monkeypatch.setattr(window.store, "get_key", broken)
    window.edit_item(find_index(window, "web/site"))
    wait_for_tasks(qapp)
    assert answers.warnings == [("Could not decrypt this password entry", "bad data")]
    assert not opened
    window.edit_item(find_index(window, "web"))
    assert status(window) == "No password selected"


def test_users_dialog_reencrypts_the_folder(qapp, window, store, key_id, monkeypatch):
    calls = []

    class Users(FakeDialog):
        """Accepts with the test key ticked."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.selected_ids = [key_id]

    monkeypatch.setattr("pyqtpass.store_actions.UsersDialog", Users)
    monkeypatch.setattr(
        window.store, "init", lambda keys, folder, **_kw: calls.append((keys, folder))
    )
    window.open_users_dialog(find_index(window, "web/site"))
    wait_for_tasks(qapp)
    assert calls == [([key_id], "web")]
    assert status(window) == "Re-encrypted passwords in web"


def test_reencrypt_folder_asks_first(qapp, window, store, answers, monkeypatch):
    calls = []
    monkeypatch.setattr(
        window.store, "reencrypt", lambda folder, *_args: calls.append(folder)
    )
    answers.question = NO
    window.reencrypt_folder()
    wait_for_tasks(qapp)
    assert not calls
    answers.question = YES
    window.reencrypt_folder()
    wait_for_tasks(qapp)
    assert calls == [""]
    assert status(window) == "Re-encrypted passwords in /"


def test_failed_reencryption_is_reported(qapp, window, answers):
    def failing(_progress, _cancelled):
        raise RuntimeError("no secret key")

    window.run_with_progress("busy", failing, "done", "Re-encryption failed")
    wait_for_tasks(qapp)
    assert answers.criticals == [("Re-encryption failed", "no secret key")]


def test_a_failed_pull_does_not_stop_the_change(qapp, window, monkeypatch):
    printed = []
    monkeypatch.setattr(window, "git_enabled", lambda: True)
    monkeypatch.setattr(window, "verbose_print", printed.append)
    monkeypatch.setattr(window.store, "pull_before_change", lambda: (False, "offline"))
    window.settings.set("git_pull_on_start", True)
    pulled = window.pulling_first(lambda progress, cancelled: (progress, cancelled))
    assert pulled(1, 2) == (1, 2)
    assert printed == ["offline"]
    window.settings.set("git_pull_on_start", False)
    plain = window.pulling_first(len)
    assert plain is len


class RecordingMenu(QMenu):
    """A context menu that records its actions instead of showing."""

    shown = []

    def exec(self, *_args):  # pylint: disable=arguments-differ
        RecordingMenu.shown.append(self.texts(self))

    @staticmethod
    def texts(menu):
        result = []
        for action in menu.actions():
            if action.menu() is not None:
                result.append(RecordingMenu.texts(action.menu()))
            elif not action.isSeparator():
                result.append(action.text())
        return result


def show_menu_at(window, monkeypatch, path):
    RecordingMenu.shown = []
    monkeypatch.setattr("pyqtpass.store_actions.QMenu", RecordingMenu)
    if path is None:
        position = window.ui.tree_view.viewport().rect().bottomRight()
    else:
        position = window.ui.tree_view.visualRect(find_index(window, path)).center()
    window.show_context_menu(position)
    return RecordingMenu.shown[0]


def test_context_menu_of_an_entry(qapp, window, monkeypatch):
    window.show()
    window.settings.set("use_otp", True)
    window.ui.tree_view.expandAll()
    texts = show_menu_at(window, monkeypatch, "other")
    assert texts == [
        "Copy password",
        "Copy OTP code",
        "Open",
        "Edit",
        "Rename password",
        "Duplicate",
        "Delete",
    ]


def test_context_menu_of_a_folder_and_the_root(qapp, window, monkeypatch):
    window.show()
    share = [
        "Re-encrypt all passwords",
        "Export my public key...",
        "Add recipient...",
        "What is this?",
    ]
    assert show_menu_at(window, monkeypatch, "web") == [
        "Add password",
        "Add folder",
        "Rename folder",
        "Delete",
        "Users",
        share,
        "Open folder with file manager",
    ]
    assert show_menu_at(window, monkeypatch, None) == [
        "Add password",
        "Add folder",
        "Users",
        share,
        "Open folder with file manager",
    ]


def test_sharing_helpers(qapp, window, store, monkeypatch):
    opened, shown = [], []
    monkeypatch.setattr(
        "pyqtpass.store_actions.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()),
    )
    monkeypatch.setattr(
        "pyqtpass.store_actions.QMessageBox.information",
        lambda _parent, title, _text: shown.append(title),
    )
    monkeypatch.setattr(
        "pyqtpass.store_actions.ExportPublicKeyDialog.exec",
        lambda dialog: shown.append(dialog.windowTitle()),
    )
    window.open_store_folder(find_index(window, "web"))
    assert opened == [store.absolute("web")]
    window.show_share_help()
    window.export_public_key()
    assert shown[0] == "Sharing passwords with GPG" and len(shown) == 2
