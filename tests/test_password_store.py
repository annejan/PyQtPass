"""Tests for the native password store backend."""

# pylint: disable=missing-function-docstring

import os

import pytest

import git_utils
from password_store import PasswordStore, StoreError


def test_set_and_get(store):
    store.set_key("web/example", "secret\nlogin: me")
    assert store.get_key("web/example") == "secret\nlogin: me\n"
    assert store.list_dir("") == (["web"], [])
    assert store.list_dir("web") == ([], ["example"])


def test_set_existing_requires_force(store):
    store.set_key("entry", "one")
    with pytest.raises(FileExistsError):
        store.set_key("entry", "two")
    store.set_key("entry", "two", force=True)
    assert store.get_key("entry") == "two\n"


def test_failed_encrypt_keeps_entry(store):
    store.set_key("entry", "original")
    with open(store.entry_file("entry"), "rb") as f:
        before = f.read()
    with open(os.path.join(store.store_dir, ".gpg-id"), "w", encoding="utf-8") as f:
        f.write("nobody@invalid.example\n")
    with pytest.raises(StoreError):
        store.set_key("entry", "changed", force=True)
    with open(store.entry_file("entry"), "rb") as f:
        assert f.read() == before
    assert store.get_key("entry") == "original\n"


def test_missing_entry(store):
    with pytest.raises(FileNotFoundError):
        store.get_key("does/not/exist")


def test_path_traversal_refused(store):
    with pytest.raises(StoreError):
        store.set_key("../outside", "x")
    with pytest.raises(StoreError):
        store.get_key("a/../../b")


def test_symlinks_skipped_and_refused(store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, os.path.join(store.store_dir, "linked"))
    assert store.list_dir("") == ([], [])
    with pytest.raises(StoreError):
        store.set_key("linked/entry", "x")
    store.remove_path("linked")
    assert outside.exists()
    assert not os.path.lexists(os.path.join(store.store_dir, "linked"))


def test_move_copy_remove(store):
    store.set_key("a/one", "1")
    store.copy_path("a/one", "b/")
    assert store.get_key("b/one") == "1\n"
    store.move_path("a/one", "a/two")
    assert store.list_dir("a") == ([], ["two"])
    store.move_path("a", "c")
    assert store.list_dir("") == (["b", "c"], [])
    with pytest.raises(StoreError):
        store.move_path("c", "c/inner")
    store.remove_path("b/one")
    with pytest.raises(StoreError):
        store.remove_path("c")
    store.remove_path("c", recursive=True)
    assert store.list_dir("") == (["b"], [])


def test_search_and_folders(store):
    store.set_key("x/one", "pw\nurl: https://example.org")
    store.set_key("two", "pw\nnote: nothing")
    assert store.search("example") == {"x/one": ["url: https://example.org"]}
    assert store.list_folders() == ["", "x"]
    assert sorted(store.iter_entries()) == ["two", "x/one"]


def test_recipients_comments(store, key_id):
    path = os.path.join(store.store_dir, "sub")
    os.makedirs(path)
    with open(os.path.join(path, ".gpg-id"), "w", encoding="utf-8") as f:
        f.write(f"# team\n{key_id}  # me\n\n")
    assert store.recipients("sub") == [key_id]
    assert store.recipients("sub/deeper") == [key_id]


def test_uninitialised(tmp_path):
    empty = PasswordStore(str(tmp_path / "empty"), use_git=False)
    assert not empty.is_initialised()
    os.makedirs(empty.store_dir)
    with pytest.raises(StoreError):
        empty.set_key("x", "y")


def test_git_commits(tmp_path, key_id):
    git_store = PasswordStore(str(tmp_path / "gitstore"))
    os.makedirs(git_store.store_dir)
    git_utils.run_git(git_store.store_dir, "init")
    git_utils.run_git(git_store.store_dir, "config", "user.email", "t@example.org")
    git_utils.run_git(git_store.store_dir, "config", "user.name", "Test")
    git_utils.run_git(git_store.store_dir, "config", "commit.gpgsign", "false")
    git_store.init([key_id])
    git_store.set_key("entry", "pw")
    git_store.move_path("entry", "renamed")
    git_store.remove_path("renamed")
    ok, log = git_utils.run_git(git_store.store_dir, "log", "--format=%s")
    assert ok
    assert log.splitlines() == [
        "Remove renamed from store.",
        "Rename entry to renamed.",
        "Add given password for entry to store.",
        "Set GPG id to " + key_id + ".",
    ]
    ok, status = git_utils.run_git(git_store.store_dir, "status", "--porcelain")
    assert ok and status == ""
