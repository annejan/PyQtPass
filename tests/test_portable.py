"""Tests for portable mode: a pyqtpass.ini next to the program."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument

import os
import sys

from PyQt6.QtCore import QSettings

from pyqtpass import settings_manager
from pyqtpass.settings_manager import SettingsManager


def test_program_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "pyqtpass")])
    assert settings_manager.program_dir() == str(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "PyQtPass.exe"))
    assert settings_manager.program_dir() == str(tmp_path / "bin")


def test_no_portable_ini(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(settings_manager, "program_dir", lambda: str(tmp_path))
    assert settings_manager.portable_ini() is None
    assert settings.settings.organizationName() == "IJHack"


def test_portable_ini_holds_the_settings(qapp, monkeypatch, tmp_path):
    program = tmp_path / "program"
    program.mkdir()
    ini = program / settings_manager.PORTABLE_INI
    ini.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings_manager, "program_dir", lambda: str(program))
    SettingsManager._instance = None  # pylint: disable=protected-access
    try:
        manager = SettingsManager()
        assert manager.settings.fileName() == str(ini)
        manager.set("password_length", 42)
        manager.set("use_git", False)
        manager.set("profiles", {"work": {"path": "/work", "use_git": False}})
        manager.save()
        assert manager.generation_record_path() == os.path.join(
            str(program), "PyQtPass-gpgid-generations.json"
        )

        stored = QSettings(str(ini), QSettings.Format.IniFormat)
        assert int(stored.value("password_length")) == 42

        SettingsManager._instance = None  # pylint: disable=protected-access
        reloaded = SettingsManager()
        assert reloaded.get("password_length") == 42
        assert reloaded.get("use_git") is False
        assert reloaded.get("profiles")["work"]["path"] == "/work"
    finally:
        SettingsManager._instance = None  # pylint: disable=protected-access
