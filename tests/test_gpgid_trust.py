"""Tests for signed recipient lists and rollback detection."""

# pylint: disable=missing-function-docstring,redefined-outer-name

import os
import shutil

import pytest

from gpgid_trust import GenerationRecord, TrustError, parse_header, with_header
from password_store import PasswordStore, StoreError


@pytest.fixture
def signed_store(tmp_path, key_id):
    record = GenerationRecord(str(tmp_path / "record" / "generations.json"))
    store = PasswordStore(
        str(tmp_path / "signed"), use_git=False, signing_keys=[key_id], record=record
    )
    store.init([key_id])
    return store


def read(path):
    with open(path, "rb") as handle:
        return handle.read()


def test_header_round_trip():
    text = with_header(3, "team/a", ["ABC"])
    assert parse_header(text) == (3, "team/a")
    assert parse_header("ABC\n") == (0, None)
    with pytest.raises(TrustError):
        parse_header("# QtPass-GpgId-Generation: 1\nABC\n")
    with pytest.raises(TrustError):
        parse_header("# QtPass-GpgId-Generation: x\n# QtPass-GpgId-Folder: .\n")


def test_signed_list_is_written_and_verified(signed_store, key_id):
    gpg_id = os.path.join(signed_store.store_dir, ".gpg-id")
    assert os.path.isfile(gpg_id + ".sig")
    assert read(gpg_id).startswith(b"# QtPass-GpgId-Generation: 1\n")
    signed_store.set_key("entry", "pw")
    assert signed_store.get_key("entry") == "pw\n"
    assert signed_store.recipients() == [key_id]


def test_tampered_list_is_refused(signed_store, key_id):
    gpg_id = os.path.join(signed_store.store_dir, ".gpg-id")
    with open(gpg_id, "ab") as handle:
        handle.write(b"intruder@example.org\n")
    with pytest.raises(StoreError):
        signed_store.set_key("entry", "pw")
    assert not signed_store.is_entry("entry")
    signed_store.init([key_id])
    signed_store.set_key("entry", "pw")


def test_rollback_is_refused(signed_store, key_id, tmp_path):
    gpg_id = os.path.join(signed_store.store_dir, ".gpg-id")
    shutil.copy(gpg_id, tmp_path / "old")
    shutil.copy(gpg_id + ".sig", tmp_path / "old.sig")
    signed_store.init([key_id])
    assert read(gpg_id).startswith(b"# QtPass-GpgId-Generation: 2\n")
    shutil.copy(tmp_path / "old", gpg_id)
    shutil.copy(tmp_path / "old.sig", gpg_id + ".sig")
    with pytest.raises(StoreError, match="older than generation 2"):
        signed_store.recipients()


def test_list_copied_to_other_folder_is_refused(signed_store, key_id):
    root_id = os.path.join(signed_store.store_dir, ".gpg-id")
    os.makedirs(os.path.join(signed_store.store_dir, "team"))
    team_id = os.path.join(signed_store.store_dir, "team", ".gpg-id")
    shutil.copy(root_id, team_id)
    shutil.copy(root_id + ".sig", team_id + ".sig")
    with pytest.raises(StoreError, match="written for the folder"):
        signed_store.recipients("team")
    signed_store.init([key_id], "team")
    assert signed_store.recipients("team") == [key_id]


def test_unsigned_store_does_not_drop_a_signature(signed_store, key_id):
    plain = PasswordStore(signed_store.store_dir, use_git=False)
    gpg_id = os.path.join(plain.store_dir, ".gpg-id")
    before = read(gpg_id)
    with pytest.raises(StoreError, match="is signed"):
        plain.init([key_id])
    assert read(gpg_id) == before
    assert os.path.isfile(gpg_id + ".sig")


def test_removed_sub_list_does_not_fall_back(signed_store, key_id):
    signed_store.init([key_id], "secret")
    signed_store.set_key("secret/x", "pw")
    team_id = os.path.join(signed_store.store_dir, "secret", ".gpg-id")
    os.remove(team_id)
    os.remove(team_id + ".sig")
    with pytest.raises(StoreError, match="was removed"):
        signed_store.recipients("secret")
    with pytest.raises(StoreError):
        signed_store.set_key("secret/x", "changed", force=True)
    signed_store.init([key_id], "secret")
    assert signed_store.recipients("secret") == [key_id]


def test_linked_or_odd_sub_list_does_not_fall_back(signed_store, tmp_path):
    os.makedirs(os.path.join(signed_store.store_dir, "linked"))
    os.symlink(
        tmp_path / "elsewhere",
        os.path.join(signed_store.store_dir, "linked", ".gpg-id"),
    )
    with pytest.raises(StoreError, match="link or not a file"):
        signed_store.recipients("linked")
    os.makedirs(os.path.join(signed_store.store_dir, "odd", ".gpg-id"))
    with pytest.raises(StoreError, match="link or not a file"):
        signed_store.recipients("odd")


def test_missing_signing_key_writes_nothing(tmp_path, key_id):
    record = GenerationRecord(str(tmp_path / "record.json"))
    store = PasswordStore(
        str(tmp_path / "nokey"),
        use_git=False,
        signing_keys=["0123456789ABCDEF0123456789ABCDEF01234567"],
        record=record,
    )
    with pytest.raises(StoreError, match="did not sign|failed"):
        store.init([key_id])
    assert not os.path.exists(os.path.join(store.store_dir, ".gpg-id"))
    with record.transaction() as entries:
        assert not entries


def test_store_written_refuses_a_record_that_moved_on(signed_store):
    gpg_id = os.path.join(signed_store.store_dir, ".gpg-id")
    signer = signed_store.signer
    generation = signer.next_generation(gpg_id, 1)
    signer.store_written(gpg_id, b"x", generation + 1, lambda: None)
    written = []
    with pytest.raises(TrustError, match="moved on"):
        signer.store_written(gpg_id, b"y", generation, lambda: written.append(1))
    assert not written


def test_enabling_signing_checks_sub_lists_first(tmp_path, key_id):
    plain = PasswordStore(str(tmp_path / "mixed"), use_git=False)
    plain.init([key_id])
    plain.init([key_id], "team")
    plain.set_key("personal/m", "pw")
    plain.set_key("team/t", "pw")
    gpg_id = os.path.join(plain.store_dir, ".gpg-id")
    before = read(gpg_id)
    record = GenerationRecord(str(tmp_path / "record.json"))
    signed = PasswordStore(
        plain.store_dir, use_git=False, signing_keys=[key_id], record=record
    )
    with pytest.raises(StoreError, match="no signature"):
        signed.init([key_id])
    assert read(gpg_id) == before


def test_failed_move_leaves_the_source(signed_store, key_id):
    signed_store.set_key("entry", "pw")
    signed_store.init([key_id], "team")
    team_id = os.path.join(signed_store.store_dir, "team", ".gpg-id")
    with open(team_id, "ab") as handle:
        handle.write(b"intruder@example.org\n")
    with pytest.raises(StoreError):
        signed_store.move_path("entry", "team/entry")
    assert signed_store.get_key("entry") == "pw\n"
    assert not signed_store.is_entry("team/entry")


def test_stale_lock_is_taken_over(tmp_path):
    record = GenerationRecord(str(tmp_path / "record.json"))
    lock = tmp_path / "record.json.lock"
    lock.write_text("")
    os.utime(lock, (0, 0))
    with record.transaction() as entries:
        entries["k"] = {"generation": "1", "digest": ""}
    assert not lock.exists()
