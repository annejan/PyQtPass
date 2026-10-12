"""
Tests of setting a password store up: the first-run wizard, opening the
configured store at start, switching profiles and quitting with work left.
"""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument,import-outside-toplevel,too-few-public-methods

import os
import pathlib
import threading

import pytest
from PyQt6.QtWidgets import QDialog, QLabel

from conftest import find_index, wait_until
from pyqtpass import first_run_wizard, git_utils, gpg_utils
from pyqtpass.first_run_wizard import FirstRunWizard, IntroPage, KeyPage, StorePage
from pyqtpass.password_store import PasswordStore


def git_config(monkeypatch, tmp_path, *pairs):
    """Run git with only the given configuration, ignoring the user's."""
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    pairs = (("user.useConfigOnly", "true"),) + pairs
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(pairs)))
    for number, (key, value) in enumerate(pairs):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{number}", key)
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{number}", value)


@pytest.fixture
def git_identity(monkeypatch, tmp_path):
    git_config(
        monkeypatch,
        tmp_path,
        ("user.name", "Test"),
        ("user.email", "t@example.org"),
        ("commit.gpgsign", "false"),
    )


@pytest.fixture
def criticals(monkeypatch):
    shown = []
    monkeypatch.setattr(
        "pyqtpass.first_run_wizard.QMessageBox.critical",
        lambda _parent, _title, text: shown.append(text),
    )
    return shown


@pytest.fixture
def key_page(qapp, key_id):
    page = KeyPage()
    page.populate(key_id)
    return page


# The first-run wizard


def test_intro_warns_without_gnupg(qapp, monkeypatch):
    def texts(page):
        return " ".join(label.text() for label in page.findChildren(QLabel))

    assert "GnuPG was not found" not in texts(IntroPage())
    monkeypatch.setattr(first_run_wizard, "program_exists", lambda _program: False)
    assert "GnuPG was not found" in texts(IntroPage())


def test_key_page_needs_a_ticked_key(qapp, key_page, key_id):
    assert key_id in key_page.selected_keys()
    assert key_page.isComplete()
    for row in range(key_page.key_list.count()):
        key_page.key_list.item(row).setCheckState(
            first_run_wizard.Qt.CheckState.Unchecked
        )
    assert not key_page.selected_keys()
    assert not key_page.isComplete()


def test_key_page_ticks_a_generated_key(qapp, key_page, monkeypatch):
    real = gpg_utils.list_gpg_keys(secret=True)
    generated = {**real[0], "fingerprint": "F" * 40, "id": "F" * 16, "uids": []}
    keys = list(real)

    class Generated:
        """A key generation dialog that adds a key."""

        def __init__(self, _parent):
            pass

        def exec(self):
            keys.append(generated)
            return True

    monkeypatch.setattr(first_run_wizard, "list_gpg_keys", lambda secret: keys)
    monkeypatch.setattr(first_run_wizard, "KeyGenDialog", Generated)
    before = key_page.selected_keys()
    key_page.generate()
    assert key_page.selected_keys() == before + ["F" * 40]
    assert key_page.key_list.item(key_page.key_list.count() - 1).text() == (
        f"{'F' * 40} ({'F' * 16})"
    )


def test_store_page_describes_the_folder(qapp, key_page, store, tmp_path):
    page = StorePage(store.store_dir, key_page)
    assert page.status.text().startswith("An existing password store")
    assert not page.use_git.isChecked()
    page.path_edit.setText(str(tmp_path / "missing"))
    assert page.status.text().startswith("The folder does not exist yet")
    page.path_edit.setText(str(tmp_path))
    assert page.status.text().startswith("The folder will be set up")
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "old.gpg").write_bytes(b"")
    page.path_edit.setText(str(loose))
    assert page.status.text().startswith("This folder holds passwords")
    page.path_edit.setText("  ")
    assert page.status.text() == "Enter a folder."
    assert not page.isComplete()
    git_utils.run_git(str(tmp_path), "init")
    page.path_edit.setText(str(tmp_path))
    assert page.use_git.isChecked()


def test_store_page_browses_for_a_folder(qapp, key_page, tmp_path, monkeypatch):
    answers = [str(tmp_path / "chosen"), ""]
    monkeypatch.setattr(
        "pyqtpass.first_run_wizard.QFileDialog.getExistingDirectory",
        lambda *_args: answers.pop(0),
    )
    page = StorePage(str(tmp_path / "start"), key_page)
    page.browse()
    assert page.store_dir() == str(tmp_path / "chosen")
    page.browse()
    assert page.store_dir() == str(tmp_path / "chosen")


def test_store_page_sets_up_a_new_store(qapp, key_page, key_id, tmp_path, criticals):
    path = str(tmp_path / "new" / "store")
    page = StorePage(path, key_page)
    assert page.validatePage()
    store = PasswordStore(path)
    assert store.is_initialised()
    assert key_id in store.recipients()
    assert not git_utils.is_git_repo(path)
    assert not criticals


def test_store_page_sets_up_a_git_store(
    qapp, key_page, tmp_path, git_identity, criticals
):
    path = str(tmp_path / "store")
    page = StorePage(path, key_page)
    page.use_git.setChecked(True)
    assert page.validatePage()
    assert git_utils.is_git_repo(path)
    assert "Set GPG id to" in git_utils.run_git(path, "log", "--format=%s")[1]
    assert not criticals


def test_store_page_needs_a_git_identity(
    qapp, key_page, tmp_path, monkeypatch, criticals
):
    git_config(monkeypatch, tmp_path)
    path = str(tmp_path / "store")
    page = StorePage(path, key_page)
    page.use_git.setChecked(True)
    assert not page.validatePage()
    assert "Git does not know who you are" in criticals[0]
    assert not PasswordStore(path).is_initialised()
    assert not git_utils.is_git_repo(path)


def test_store_page_reports_a_folder_it_cannot_make(
    qapp, key_page, tmp_path, criticals
):
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    page = StorePage(str(blocker / "store"), key_page)
    assert not page.validatePage()
    assert "Failed to set up the password store" in criticals[0]


def test_store_page_keeps_an_existing_store(qapp, key_page, store, criticals):
    gpg_id = pathlib.Path(store.store_dir, ".gpg-id")
    before = gpg_id.read_text(encoding="utf-8")
    page = StorePage(store.store_dir, key_page)
    assert page.validatePage()
    assert gpg_id.read_text(encoding="utf-8") == before


def test_wizard_reports_the_choices(qapp, key_id, tmp_path):
    wizard = FirstRunWizard(str(tmp_path / "store"))
    wizard.store_page.use_git.setChecked(True)
    assert wizard.store_dir() == str(tmp_path / "store")
    assert wizard.use_git()


# Opening the configured store at start


class FakeWizard:
    """A first-run wizard that sets up a store without being shown."""

    result = QDialog.DialogCode.Accepted
    made = []

    def __init__(self, store_dir, store_factory):
        self.directory = store_dir + "-chosen"
        FakeWizard.made.append(store_factory(self.directory))

    def exec(self):
        return FakeWizard.result

    def store_dir(self):
        return self.directory

    def use_git(self):
        return True


@pytest.fixture
def fake_wizard(monkeypatch):
    FakeWizard.result = QDialog.DialogCode.Accepted
    FakeWizard.made = []
    monkeypatch.setattr("pyqtpass.store_setup.FirstRunWizard", FakeWizard)
    return FakeWizard


def test_ensure_store_skips_the_wizard_for_a_store(settings, store, fake_wizard):
    from pyqtpass.store_setup import ensure_store

    settings.set("pass_store", store.store_dir)
    assert ensure_store(settings)
    assert not fake_wizard.made


def test_ensure_store_saves_the_wizard_choices(settings, tmp_path, fake_wizard):
    from pyqtpass.store_setup import ensure_store

    settings.set("pass_store", str(tmp_path / "store"))
    settings.set("use_git", False)
    assert ensure_store(settings)
    assert settings.get("pass_store") == str(tmp_path / "store-chosen")
    assert settings.get("use_git")
    assert fake_wizard.made[0].store_dir == str(tmp_path / "store-chosen")


def test_ensure_store_updates_the_current_profile(settings, tmp_path, fake_wizard):
    from pyqtpass.store_setup import ensure_store

    work = str(tmp_path / "work")
    settings.set("pass_store", str(tmp_path / "default"))
    settings.set("profiles", {"work": {"path": work, "signing_key": "ABC"}})
    settings.set("current_profile", "work")
    assert ensure_store(settings)
    profile = settings.get("profiles")["work"]
    assert profile["path"] == work + "-chosen"
    assert profile["signing_key"] == "ABC"
    assert settings.get("pass_store") == str(tmp_path / "default")


def test_ensure_store_stops_when_the_wizard_is_cancelled(
    settings, tmp_path, fake_wizard
):
    from pyqtpass.store_setup import ensure_store

    settings.set("pass_store", str(tmp_path / "store"))
    fake_wizard.result = QDialog.DialogCode.Rejected
    assert not ensure_store(settings)
    assert settings.get("pass_store") == str(tmp_path / "store")


# Profiles


def test_switching_profiles_opens_the_other_store(
    window, settings, key_id, tmp_path, monkeypatch
):
    warnings = []
    monkeypatch.setattr(
        "pyqtpass.main_window.QMessageBox.warning",
        lambda _parent, title, _text: warnings.append(title),
    )
    work = PasswordStore(str(tmp_path / "work"), use_git=False)
    work.init([key_id])
    work.set_key("work-only", "pw")
    empty = str(tmp_path / "empty")
    settings.set("profiles", {"work": work.store_dir, "empty": empty})
    window.update_profile_combo()
    assert window.actions["profile"].isVisible()
    assert [
        window.profile_combo.itemText(row)
        for row in range(window.profile_combo.count())
    ] == ["empty", "work"]

    window.on_profile_changed("work")
    assert window.store.store_dir == work.store_dir
    assert find_index(window, "work-only") is not None
    assert find_index(window, "other") is None
    assert not warnings

    window.on_profile_changed("empty")
    assert warnings == ["Store not initialised"]
    assert os.path.isdir(empty)
    assert find_index(window, "work-only") is None


# Quitting


def test_quitting_waits_for_a_running_change(qapp, monkeypatch):
    from pyqtpass import main_window, tasks

    release = threading.Event()
    finished = []

    def change(_progress, _cancelled):
        release.wait(5)
        finished.append(True)

    tasks.run_task(change, lambda *_args: None, critical=True)
    threading.Timer(0.2, release.set).start()
    main_window.finish_tasks_on_quit()
    assert finished == [True]
    wait_until(qapp, lambda: not tasks.running())
    main_window.finish_tasks_on_quit()
