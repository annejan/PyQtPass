"""Tests for the backend that runs the pass script."""

# pylint: disable=missing-function-docstring,redefined-outer-name

import os
import shutil

import pytest

from pyqtpass.password_store import StoreError
from pyqtpass.real_pass import RealPassStore, find_pass


@pytest.fixture
def pass_store(tmp_path, key_id):
    if not find_pass():
        pytest.skip("pass is not installed")
    store = RealPassStore(str(tmp_path / "passstore"), find_pass(), use_git=False)
    store.init([key_id])
    return store


def test_round_trip(pass_store):
    pass_store.set_key("web/site", "pw\nlogin: me")
    assert pass_store.get_key("web/site") == "pw\nlogin: me\n"
    with pytest.raises(FileExistsError):
        pass_store.set_key("web/site", "x")
    pass_store.set_key("web/site", "new", force=True)
    assert pass_store.get_key("web/site") == "new\n"


def test_move_copy_remove(pass_store):
    pass_store.set_key("a/one", "1")
    pass_store.copy_path("a/one", "b/one")
    pass_store.move_path("a", "c")
    assert pass_store.list_dir("") == (["b", "c"], [])
    assert pass_store.get_key("c/one") == "1\n"
    pass_store.remove_path("c", recursive=True)
    assert pass_store.list_dir("") == (["b"], [])


def test_links_never_reach_pass(pass_store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.gpg").write_bytes(b"x")
    os.symlink(outside, os.path.join(pass_store.store_dir, "linked"))
    with pytest.raises(StoreError):
        pass_store.set_key("linked/entry", "x")
    pass_store.remove_path("linked")
    assert (outside / "keep.gpg").exists()


def test_subfolder_init(pass_store, key_id):
    pass_store.set_key("team/x", "pw")
    pass_store.init([key_id], "team")
    assert os.path.isfile(os.path.join(pass_store.store_dir, "team", ".gpg-id"))
    assert pass_store.reencrypt("team") == 1
    assert pass_store.get_key("team/x") == "pw\n"


def test_missing_pass_is_reported(tmp_path, key_id):
    store = RealPassStore(str(tmp_path / "s"), "/nonexistent/pass", use_git=False)
    with pytest.raises(StoreError):
        store.init([key_id])
    assert shutil.which("true")
