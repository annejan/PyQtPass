"""
Shared pytest fixtures: an isolated GnuPG home with a test key, a fresh
password store and an offscreen QApplication.
"""

import base64
import os
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# pylint: disable=wrong-import-position
from pyqtpass import gpg_utils  # noqa: E402
from pyqtpass.password_store import PasswordStore  # noqa: E402

TEST_UID = "PyQtPass Test <test@example.org>"

# The RFC 6238 test seed in base32, built at run time so secret scanners do
# not mistake the well-known test vector for a leaked credential.
TEST_OTP_SEED = base64.b32encode(b"12345678901234567890").decode()

OTP_URI = f"otpauth://totp/Test?secret={TEST_OTP_SEED}"


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
    from pyqtpass import executor  # pylint: disable=import-outside-toplevel

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

    from pyqtpass.settings_manager import SettingsManager

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


def wait_until(app, condition, timeout=10):
    """Process events until condition() holds, failing after timeout seconds."""
    deadline = time.time() + timeout
    while not condition():
        app.processEvents()
        if time.time() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


@pytest.fixture
def window(qapp, settings, store):  # pylint: disable=redefined-outer-name
    """A main window on the test store, holding two entries."""
    # pylint: disable=import-outside-toplevel
    from pyqtpass.main_window import QtPassGUI

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
    """:return: The proxy model index of path in the tree, or None."""
    from pyqtpass.utilities import PATH_ROLE  # pylint: disable=import-outside-toplevel

    model = gui.ui.proxy_model
    pending = [model.index(row, 0) for row in range(model.rowCount())]
    while pending:
        index = pending.pop()
        if index.data(PATH_ROLE) == path:
            return index
        pending += [model.index(row, 0, index) for row in range(model.rowCount(index))]
    return None


def wait_for_tasks(app):
    """Process events until no background task runs."""
    from pyqtpass import tasks  # pylint: disable=import-outside-toplevel

    wait_until(app, lambda: not tasks.running())
