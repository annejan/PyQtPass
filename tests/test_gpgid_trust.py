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


def test_unsigned_list_drops_stale_signature(signed_store, key_id):
    plain = PasswordStore(signed_store.store_dir, use_git=False)
    plain.init([key_id])
    assert not os.path.exists(os.path.join(plain.store_dir, ".gpg-id.sig"))
