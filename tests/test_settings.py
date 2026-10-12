"""Tests for profiles, profile overrides and the profiles editor."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument

from profiles_editor import ProfilesEditor
from settings_manager import profile_options
from test_gui import (
    settings,
)  # noqa: F401  pylint: disable=unused-import,wrong-import-order

FINGERPRINT = "A" * 40


def test_profile_options_reads_old_and_new_format():
    assert profile_options("/old")["path"] == "/old"
    assert profile_options("/old")["use_git"] is None
    options = profile_options({"path": "/new", "use_git": "false"})
    assert options["use_git"] is False and options["signing_key"] == ""


def test_effective_settings(settings):
    settings.set("use_git", True)
    settings.set("pass_signing_key", FINGERPRINT)
    settings.set(
        "profiles",
        {"work": {"path": "/work", "use_git": False, "signing_key": "B" * 40}},
    )
    assert settings.effective("use_git") is True
    assert settings.signing_keys() == [FINGERPRINT]
    settings.set("current_profile", "work")
    assert settings.store_dir() == "/work"
    assert settings.effective("use_git") is False
    assert settings.effective("auto_push") == settings.get("auto_push")
    assert settings.signing_keys() == ["B" * 40]


def test_profiles_editor(qapp):
    editor = ProfilesEditor()
    editor.set_profiles({"home": "/home/store", "work": {"path": "/work"}})
    assert editor.validation_error() == ""
    editor.profile_list.setCurrentRow(1)
    editor.signing_edit.setText("not-a-fingerprint")
    assert "fingerprint" in editor.validation_error()
    editor.signing_edit.setText(FINGERPRINT)
    editor.override_boxes["auto_push"].setCurrentIndex(2)
    editor.name_edit.setText("home")
    assert "two profiles" in editor.validation_error()
    editor.name_edit.setText("office")
    profiles = editor.profiles()
    assert profiles["office"]["signing_key"] == FINGERPRINT
    assert profiles["office"]["auto_push"] is False
    assert profiles["home"]["path"] == "/home/store"
