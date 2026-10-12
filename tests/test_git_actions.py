"""Tests of pulling and pushing from the main window against a real remote."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument,import-outside-toplevel

import pytest

from conftest import find_index, wait_for_tasks, wait_until
from test_password_store import clone_store, make_repo
from pyqtpass import git_utils
from pyqtpass.password_store import PasswordStore


@pytest.fixture
def remote(tmp_path, key_id):
    """A bare remote holding an initialised store with one entry."""
    seed = str(tmp_path / "seed")
    make_repo(seed)
    PasswordStore(seed).init([key_id])
    PasswordStore(seed).set_key("first", "pw")
    bare = str(tmp_path / "remote.git")
    git_utils.run_git(str(tmp_path), "clone", "--bare", seed, bare)
    return bare


@pytest.fixture
def git_window(qapp, settings, remote, tmp_path, monkeypatch):
    """A main window on a clone of the remote, with auto push and no auto pull."""
    from pyqtpass.main_window import QtPassGUI

    local = clone_store(remote, str(tmp_path / "local"))
    settings.set("pass_store", local.store_dir)
    settings.set("use_git", True)
    settings.set("auto_push", True)
    settings.set("git_pull_on_start", False)
    settings.set("use_tray_icon", False)
    warnings = []
    monkeypatch.setattr(
        "pyqtpass.git_actions.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )
    gui = QtPassGUI()
    gui.warnings = warnings
    yield gui
    wait_for_tasks(qapp)
    gui.close()
    gui.deleteLater()
    qapp.processEvents()


def remote_log(remote):
    return git_utils.run_git(remote, "log", "--format=%s")[1].splitlines()


def other_clone(remote, tmp_path):
    return clone_store(remote, str(tmp_path / "other"))


def wait_for_git(qapp, window):
    wait_until(qapp, lambda: window.git_task is None and not window.push_pending)
    wait_for_tasks(qapp)


def test_git_actions_show_for_a_git_store(qapp, git_window):
    for name in ("git_pull", "git_push"):
        assert git_window.actions[name].isVisible()
        assert git_window.actions[name].isEnabled()


def test_pull_brings_in_remote_changes(qapp, git_window, remote, tmp_path):
    other = other_clone(remote, tmp_path)
    other.set_key("from/elsewhere", "pw")
    assert git_utils.git_push(other.store_dir)[0]
    assert find_index(git_window, "from/elsewhere") is None
    git_window.on_git_pull()
    assert not git_window.actions["git_pull"].isEnabled()
    wait_for_git(qapp, git_window)
    assert git_window.actions["git_pull"].isEnabled()
    assert find_index(git_window, "from/elsewhere") is not None
    assert git_window.statusBar().currentMessage() == "Password store updated"
    assert not git_window.warnings


def test_pull_on_start(qapp, settings, git_window, remote, tmp_path):
    from pyqtpass.main_window import QtPassGUI

    other = other_clone(remote, tmp_path)
    other.set_key("new", "pw")
    assert git_utils.git_push(other.store_dir)[0]
    settings.set("git_pull_on_start", True)
    gui = QtPassGUI()
    try:
        wait_until(qapp, lambda: find_index(gui, "new") is not None)
    finally:
        wait_for_git(qapp, gui)
        gui.close()
        gui.deleteLater()


def test_push_sends_local_commits(qapp, git_window, remote):
    git_window.store.set_key("local", "pw")
    git_window.on_git_push()
    wait_for_git(qapp, git_window)
    assert remote_log(remote)[0] == "Add given password for local to store."
    assert git_window.statusBar().currentMessage() == "Password store pushed"


def test_store_change_is_pushed_automatically(qapp, git_window, remote, monkeypatch):
    monkeypatch.setattr(
        "pyqtpass.store_actions.QInputDialog.getText",
        lambda *_args, **_kwargs: ("renamed", True),
    )
    git_window.rename_item(find_index(git_window, "first"))
    wait_for_git(qapp, git_window)
    wait_until(qapp, lambda: remote_log(remote)[0] == "Rename first to renamed.")
    assert not git_window.warnings


def test_auto_push_waits_for_a_running_git_task(qapp, git_window, remote):
    git_window.store.set_key("queued", "pw")
    git_window.on_git_pull()
    git_window.auto_push()
    assert git_window.push_pending
    wait_for_git(qapp, git_window)
    wait_until(qapp, lambda: "queued" in remote_log(remote)[0])
    assert not git_window.warnings


def test_auto_push_can_be_turned_off(qapp, git_window, remote):
    before = remote_log(remote)
    git_window.settings.set("auto_push", False)
    git_window.store.set_key("kept", "pw")
    git_window.auto_push()
    assert git_window.git_task is None
    assert remote_log(remote) == before


def test_failed_push_is_reported(qapp, git_window, tmp_path):
    store_dir = git_window.store.store_dir
    git_utils.run_git(store_dir, "remote", "set-url", "origin", str(tmp_path / "gone"))
    git_window.on_git_push()
    wait_for_git(qapp, git_window)
    assert [title for title, _ in git_window.warnings] == ["Git push failed"]


def test_git_needs_a_git_store(qapp, window):
    window.on_git_pull()
    assert window.git_task is None
    assert window.statusBar().currentMessage() == "Git is not available for this store"
    assert not window.actions["git_pull"].isVisible()
    window.auto_push()
    assert window.git_task is None


def test_second_git_task_is_ignored_while_one_runs(qapp, git_window):
    git_window.on_git_pull()
    task = git_window.git_task
    git_window.on_git_push()
    assert git_window.git_task is task
    wait_for_git(qapp, git_window)
    assert git_window.statusBar().currentMessage() == "Password store updated"
