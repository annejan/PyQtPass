"""Tests for the native password store backend."""

# pylint: disable=missing-function-docstring,import-outside-toplevel

import os
import re

import pytest

from pyqtpass import git_utils
from pyqtpass import gpg_utils
from pyqtpass.password_store import PasswordStore, StoreError


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


def test_reencrypt_folder(store, key_id):
    store.set_key("team/a", "1")
    store.set_key("team/b", "2")
    store.init([key_id], "team")
    assert store.reencrypt("team") == 2
    assert store.get_key("team/b") == "2\n"


def test_reencrypt_keeps_bytes_that_are_not_utf8(store, key_id):
    raw = b"caf\xe9 \xff\xfe\n"
    store.encrypt_to_file(store.entry_file("latin1"), raw, [key_id])
    store.init([key_id])
    assert store.decrypt_bytes(store.entry_file("latin1")) == raw
    store.set_key("team/keep", "x")
    store.init([key_id], "team")
    store.move_path("latin1", "team/latin1")
    assert store.decrypt_bytes(store.entry_file("team/latin1")) == raw


def test_empty_list_does_not_fall_back(store, key_id):
    os.makedirs(os.path.join(store.store_dir, "empty"))
    with open(
        os.path.join(store.store_dir, "empty", ".gpg-id"), "w", encoding="utf-8"
    ) as f:
        f.write("# nobody yet\n")
    with pytest.raises(StoreError, match="names no key"):
        store.set_key("empty/x", "pw")
    assert store.recipients("") == [key_id]


def test_folder_move_reencrypts_before_replacing(store, key_id):
    store.set_key("a/one", "1")
    store.set_key("a/sub/two", "2")
    store.init([key_id], "b")
    store.move_path("a", "b/a")
    assert store.get_key("b/a/sub/two") == "2\n"
    assert not store.is_folder("a")
    assert not [
        n
        for n in os.listdir(os.path.join(store.store_dir, "b"))
        if n.startswith(".pyqtpass")
    ]


def make_repo(path):
    os.makedirs(path)
    for args in (
        ("init",),
        ("config", "user.email", "t@example.org"),
        ("config", "user.name", "Test"),
        ("config", "commit.gpgsign", "false"),
    ):
        git_utils.run_git(path, *args)


def test_commit_leaves_other_staged_changes(tmp_path, key_id):
    repo = str(tmp_path / "repo")
    make_repo(repo)
    git_store = PasswordStore(repo)
    git_store.init([key_id])
    with open(os.path.join(repo, "notes.txt"), "w", encoding="utf-8") as f:
        f.write("mine")
    git_utils.run_git(repo, "add", "notes.txt")
    git_store.set_key("entry", "pw")
    ok, files = git_utils.run_git(repo, "show", "--name-only", "--format=")
    assert ok and files == "entry.gpg"
    ok, staged = git_utils.run_git(repo, "diff", "--cached", "--name-only")
    assert staged == "notes.txt"


def test_hooks_do_not_run_for_own_commits(tmp_path, key_id):
    repo = str(tmp_path / "hooked")
    make_repo(repo)
    hook = os.path.join(repo, ".git", "hooks", "pre-commit")
    with open(hook, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\ntouch ran-hook\nexit 1\n")
    os.chmod(hook, 0o755)
    git_store = PasswordStore(repo)
    git_store.init([key_id])
    git_store.set_key("entry", "pw")
    assert not os.path.exists(os.path.join(repo, "ran-hook"))


def test_worktree_store_is_a_git_store(tmp_path):
    repo = str(tmp_path / "main")
    make_repo(repo)
    git_utils.run_git(repo, "commit", "--allow-empty", "-m", "start")
    worktree = str(tmp_path / "wt")
    ok, output = git_utils.run_git(repo, "worktree", "add", worktree)
    assert ok, output
    assert PasswordStore(worktree).git_enabled()


def test_identity_check(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "EMAIL", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(name, raising=False)
    known, _ = git_utils.has_identity(str(tmp_path))
    assert not known


def test_passphrase_with_line_break_is_refused():
    with pytest.raises(ValueError):
        gpg_utils.generate_key("A", "a@example.org", "two\nlines")


def test_move_is_undone_when_encryption_fails(store):
    store.set_key("entry", "pw")
    store.set_key("folder/inner", "pw")
    os.makedirs(os.path.join(store.store_dir, "team"))
    with open(
        os.path.join(store.store_dir, "team", ".gpg-id"), "w", encoding="utf-8"
    ) as f:
        f.write("nobody@invalid.example\n")
    with pytest.raises(StoreError):
        store.move_path("entry", "team/entry")
    with pytest.raises(StoreError):
        store.move_path("folder", "team/folder")
    assert store.get_key("entry") == "pw\n"
    assert store.get_key("folder/inner") == "pw\n"
    assert os.listdir(os.path.join(store.store_dir, "team")) == [".gpg-id"]


def test_failed_commit_is_a_commit_error(tmp_path, key_id):
    from pyqtpass.password_store import (
        CommitError,
    )  # pylint: disable=import-outside-toplevel

    repo = str(tmp_path / "locked")
    make_repo(repo)
    git_store = PasswordStore(repo)
    git_store.init([key_id])
    with open(os.path.join(repo, ".git", "index.lock"), "w", encoding="utf-8"):
        pass
    with pytest.raises(CommitError, match="change was made"):
        git_store.set_key("entry", "pw")
    assert git_store.get_key("entry") == "pw\n"


def test_store_lock_is_shared_per_folder(store):
    import threading  # pylint: disable=import-outside-toplevel

    again = PasswordStore(store.store_dir, use_git=False)
    assert again.lock is store.lock
    with store.lock:
        seen = []
        other = threading.Thread(
            target=lambda: seen.append(again.lock.acquire(blocking=False))
        )
        other.start()
        other.join()
        assert seen == [False]


def test_staged_folder_move_keeps_links(store, key_id, tmp_path):
    store.set_key("a/one", "1")
    os.symlink(tmp_path, os.path.join(store.store_dir, "a", "link"))
    store.init([key_id], "b")
    os.makedirs(os.path.join(store.store_dir, "c"))
    with open(
        os.path.join(store.store_dir, "c", ".gpg-id"), "w", encoding="utf-8"
    ) as f:
        f.write(key_id + "\n# other list\n")
    store.move_path("a", "c/a")
    assert os.path.islink(os.path.join(store.store_dir, "c", "a", "link"))
    assert store.get_key("c/a/one") == "1\n"


def recipients_of(path):
    _, stdout, _ = gpg_run(["--batch", "--list-packets", path])
    return set(re.findall(r"keyid ([0-9A-F]{16})", stdout.decode()))


def gpg_run(args):
    from pyqtpass import executor  # pylint: disable=import-outside-toplevel

    return executor.run([gpg_utils.which_gpg(), *args], timeout=60)


def test_init_with_failing_commit_still_reencrypts(tmp_path, key_id, second_key):
    from pyqtpass.password_store import (
        CommitError,
    )  # pylint: disable=import-outside-toplevel

    repo = str(tmp_path / "lockinit")
    make_repo(repo)
    git_store = PasswordStore(repo)
    git_store.init([key_id])
    git_store.set_key("a", "pw")
    old_recipients = recipients_of(git_store.entry_file("a"))
    with open(os.path.join(repo, ".git", "index.lock"), "w", encoding="utf-8"):
        pass
    with pytest.raises(CommitError, match="re-encrypted"):
        git_store.init([second_key])
    # Encrypted to the new key's encryption subkey only, not the old key.
    new_recipients = recipients_of(git_store.entry_file("a"))
    assert new_recipients and not new_recipients & old_recipients


def test_leftover_staging_folder_is_not_committed(tmp_path, key_id):
    repo = str(tmp_path / "staging")
    make_repo(repo)
    git_store = PasswordStore(repo)
    git_store.init([key_id])
    git_store.set_key("a", "pw")
    leftover = os.path.join(repo, ".pyqtpass-move-crash")
    os.makedirs(leftover)
    with open(os.path.join(leftover, "x.gpg"), "wb") as f:
        f.write(b"junk")
    git_store.init([key_id])
    git_store.reencrypt()
    ok, files = git_utils.run_git(repo, "ls-files")
    assert ok and ".pyqtpass-move-crash" not in files
