"""
Shared pytest fixtures: an isolated GnuPG home with a test key, a fresh
password store and an offscreen QApplication.
"""

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


@pytest.fixture
def store(tmp_path, key_id):  # pylint: disable=redefined-outer-name
    """An initialised, git-less password store."""
    password_store = PasswordStore(str(tmp_path / "store"), use_git=False)
    password_store.init([key_id])
    return password_store


@pytest.fixture(scope="session")
def qapp():
    """The QApplication for widget tests."""
    from PyQt6.QtWidgets import QApplication  # pylint: disable=import-outside-toplevel

    app = QApplication.instance() or QApplication([])
    yield app
