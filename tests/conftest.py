"""
Shared pytest fixtures: an isolated GnuPG home with a test key, a fresh
password store and an offscreen QApplication.
"""

import base64
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# pylint: disable=wrong-import-position
import gpg_utils  # noqa: E402
from password_store import PasswordStore  # noqa: E402

TEST_UID = "PyQtPass Test <test@example.org>"

# The RFC 6238 test seed in base32, built at run time so secret scanners do
# not mistake the well-known test vector for a leaked credential.
TEST_OTP_SEED = base64.b32encode(b"12345678901234567890").decode()


def has_gpg():
    """:return: True when a gpg binary is available."""
    return shutil.which("gpg") is not None or shutil.which("gpg2") is not None


@pytest.fixture(scope="session")
def gnupg_home(tmp_path_factory):
    """An isolated GNUPGHOME holding one unprotected test key."""
    if not has_gpg():
        pytest.skip("gpg is not installed")
    home = tmp_path_factory.mktemp("gnupg")
    os.chmod(home, 0o700)
    previous = os.environ.get("GNUPGHOME")
    os.environ["GNUPGHOME"] = str(home)
    ok, output = gpg_utils.generate_key("PyQtPass Test", "test@example.org")
    assert ok, output
    yield home
    subprocess.run(["gpgconf", "--kill", "gpg-agent"], check=False, capture_output=True)
    if previous is None:
        del os.environ["GNUPGHOME"]
    else:
        os.environ["GNUPGHOME"] = previous


@pytest.fixture
def key_id(gnupg_home):  # pylint: disable=redefined-outer-name,unused-argument
    """The fingerprint of the test key."""
    keys = gpg_utils.list_gpg_keys(secret=True)
    assert keys
    return keys[0]["fingerprint"]


@pytest.fixture(scope="session")
def second_key(gnupg_home):  # pylint: disable=redefined-outer-name,unused-argument
    """
    A second key whose primary key only certifies and which signs with a
    subkey, a common layout.
    """
    import executor  # pylint: disable=import-outside-toplevel

    gpg = gpg_utils.which_gpg()
    uid = "Second Key <second@example.org>"
    base = [gpg, "--batch", "--pinentry-mode", "loopback", "--passphrase", ""]
    returncode, _, stderr = executor.run(
        base + ["--quick-generate-key", uid, "ed25519", "cert", "never"], timeout=120
    )
    assert returncode == 0, stderr
    key = next(k for k in gpg_utils.list_gpg_keys(secret=True) if uid in k["uids"])
    for usage, algorithm in (("sign", "ed25519"), ("encr", "cv25519")):
        returncode, _, stderr = executor.run(
            base + ["--quick-add-key", key["fingerprint"], algorithm, usage, "never"],
            timeout=120,
        )
        assert returncode == 0, stderr
    return key["fingerprint"]


@pytest.fixture
def store(tmp_path, key_id):  # pylint: disable=redefined-outer-name
    """An initialised, git-less password store."""
    new_store = PasswordStore(str(tmp_path / "store"), use_git=False)
    new_store.init([key_id])
    return new_store


@pytest.fixture(scope="session")
def qapp():
    """The QApplication for widget tests."""
    from PyQt6.QtWidgets import QApplication  # pylint: disable=import-outside-toplevel

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def settings(
    tmp_path, qapp, monkeypatch
):  # pylint: disable=redefined-outer-name,unused-argument
    """A SettingsManager writing to a temporary directory."""
    # pylint: disable=import-outside-toplevel
    from PyQt6.QtCore import QSettings

    from settings_manager import SettingsManager

    QSettings.setPath(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    monkeypatch.delenv("PASSWORD_STORE_SIGNING_KEY", raising=False)
    SettingsManager._instance = None  # pylint: disable=protected-access
    manager = SettingsManager()
    yield manager
    SettingsManager._instance = None  # pylint: disable=protected-access
