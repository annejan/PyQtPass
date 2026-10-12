"""GnuPG home, ssh agent, WSL wrapping and pwgen."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument,protected-access,import-outside-toplevel

import os
import socket
import stat

import pytest

from pyqtpass import environment, executor, pwgen


@pytest.fixture
def clean_environment(monkeypatch):
    """Forget what earlier tests set up, and put it back afterwards."""
    monkeypatch.setattr(environment, "_replaced", {})
    monkeypatch.setattr(environment, "_probed", {})
    for name in ("GNUPGHOME", "SSH_AUTH_SOCK"):
        monkeypatch.setenv(name, "unused")
        monkeypatch.delenv(name)


def test_gnupg_home_is_set_and_restored(tmp_path, clean_environment, monkeypatch):
    monkeypatch.setenv("GNUPGHOME", "/session/home")
    assert environment.apply_gnupg_home(str(tmp_path)) == ""
    assert os.environ["GNUPGHOME"] == str(tmp_path)
    assert environment.apply_gnupg_home(str(tmp_path / "missing"))
    assert os.environ["GNUPGHOME"] == "/session/home"
    environment.apply_gnupg_home(str(tmp_path))
    environment.apply_gnupg_home("")
    assert os.environ["GNUPGHOME"] == "/session/home"


def test_session_ssh_agent_wins(clean_environment, monkeypatch):
    monkeypatch.setenv("SSH_AUTH_SOCK", "/session/agent")
    assert environment.apply_ssh_auth_sock("/configured") == "/session/agent"
    assert os.environ["SSH_AUTH_SOCK"] == "/session/agent"


def test_configured_ssh_agent(clean_environment):
    assert environment.apply_ssh_auth_sock("/configured") == "/configured"
    assert os.environ["SSH_AUTH_SOCK"] == "/configured"
    # Still ours, so a changed setting replaces it.
    assert environment.apply_ssh_auth_sock("/other") == "/other"


def test_found_ssh_agent_is_probed_once(clean_environment, monkeypatch):
    calls = []

    def probe():
        calls.append(1)
        return "/run/gpg/S.gpg-agent.ssh"

    monkeypatch.setattr(environment, "gpg_agent_ssh_socket", probe)
    assert environment.apply_ssh_auth_sock("") == "/run/gpg/S.gpg-agent.ssh"
    assert environment.apply_ssh_auth_sock("") == "/run/gpg/S.gpg-agent.ssh"
    assert len(calls) == 1
    monkeypatch.setattr(environment, "_probed", {"found": ""})
    monkeypatch.setattr(environment, "launchd_ssh_socket", lambda: "")
    assert environment.apply_ssh_auth_sock("") == ""
    assert "SSH_AUTH_SOCK" not in os.environ


def test_is_socket(tmp_path):
    path = str(tmp_path / "s")
    server = socket.socket(socket.AF_UNIX)
    try:
        server.bind(path)
        assert stat.S_ISSOCK(os.stat(path).st_mode)
        assert environment.is_socket(path)
    finally:
        server.close()
    assert not environment.is_socket(str(tmp_path))
    assert not environment.is_socket(str(tmp_path / "none"))


def test_wsl_command(monkeypatch):
    args = ["wsl gpg2", "-d", "--", "C:\\Users\\me\\store\\a.gpg", "-r", "KEY"]
    monkeypatch.setattr(environment, "WSL_ENABLED", False)
    assert environment.wsl_command(args) == args
    monkeypatch.setattr(environment, "WSL_ENABLED", True)
    assert environment.wsl_command(args) == [
        "wsl",
        "--exec",
        "gpg2",
        "-d",
        "--",
        "/mnt/c/Users/me/store/a.gpg",
        "-r",
        "KEY",
    ]
    assert environment.wsl_command(["gpg", "C:/x"]) == ["gpg", "C:/x"]
    assert environment.wsl_path("d:/data") == "/mnt/d/data"
    assert environment.wsl_path("--homedir=C:/x") == "--homedir=C:/x"


def test_executor_runs_wsl_command(monkeypatch):
    started = []

    def fake_popen(args, **_kwargs):
        started.append(args)
        raise OSError("not here")

    monkeypatch.setattr(environment, "WSL_ENABLED", True)
    monkeypatch.setattr(executor.subprocess, "Popen", fake_popen)
    executor.run(["wsl git", "-C", "C:\\store", "status"])
    assert started == [["wsl", "--exec", "git", "-C", "/mnt/c/store", "status"]]


class Options:  # pylint: disable=too-few-public-methods
    """A stand-in for the SettingsManager."""

    def __init__(self, **options):
        self.options = options

    def get(self, key):
        return self.options.get(key)


def test_pwgen_args():
    assert pwgen.pwgen_args(Options(), 20) == [
        "-1",
        "--secure",
        "--capitalize",
        "--numerals",
        "20",
    ]
    options = Options(
        less_random=True, avoid_capitals=True, avoid_numbers=True, use_symbols=True
    )
    assert pwgen.pwgen_args(options, 8) == [
        "-1",
        "--no-capitalize",
        "--no-numerals",
        "--symbols",
        "8",
    ]


def test_pwgen_password(tmp_path):
    script = tmp_path / "pwgen"
    script.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\necho abcdefgh\n')
    script.chmod(0o755)
    options = Options(use_pwgen=True, pwgen_executable=str(script))
    assert pwgen.pwgen_password(options, 8) == "abcdefgh"
    assert (tmp_path / "pwgen.args").read_text().split() == pwgen.pwgen_args(options, 8)
    # A password of another length means pwgen did not do what was asked.
    assert pwgen.pwgen_password(options, 9) == ""
    assert pwgen.pwgen_password(Options(pwgen_executable=str(script)), 8) == ""
    missing = Options(use_pwgen=True, pwgen_executable=str(tmp_path / "none"))
    assert pwgen.pwgen_password(missing, 8) == ""


def test_dialog_generates_with_pwgen(qapp, settings, store, tmp_path):
    from pyqtpass.config_dialog import (
        ConfigDialog,
    )
    from pyqtpass.edit_password_window import (
        EditPasswordDialog,
    )

    script = tmp_path / "pwgen"
    script.write_text(
        '#!/bin/sh\nfor n; do :; done\nhead -c "$n" /dev/zero | tr "\\0" x; echo\n'
    )
    script.chmod(0o755)
    settings.set("use_pwgen", True)
    settings.set("pwgen_executable", str(script))
    settings.save()
    config = ConfigDialog()
    assert config.fields["use_pwgen"].isChecked()
    config.fields["avoid_numbers"].setChecked(True)
    config.fields["use_pwgen"].setChecked(False)
    config.save_settings()
    assert not ConfigDialog().fields["use_pwgen"].isChecked()
    settings.load()
    assert settings.get("avoid_numbers") and not settings.get("use_pwgen")
    settings.set("use_pwgen", True)
    settings.save()
    dialog = EditPasswordDialog(store, "", "", create=True)
    dialog.length_edit.setValue(12)
    dialog.generate_password()
    assert dialog.password_edit.text() == "x" * 12
    dialog.settings.set("pwgen_executable", str(tmp_path / "none"))
    dialog.generate_password()
    assert len(dialog.password_edit.text()) == 12
    assert dialog.password_edit.text() != "x" * 12
