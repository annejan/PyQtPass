"""
GPG helper functions for PyQtPass.

Used to detect the gpg binary, list the available keys and read the
.gpg-id files that determine which keys a password (sub)store is
encrypted for.
"""

import os
import shutil
import subprocess

from passpy.git import git_add_path
from passpy.gpg import reencrypt_path


def which_gpg():
    """
    Find the gpg binary, preferring gpg2 like pass itself does.

    :return: Name of the gpg binary ('gpg2' or 'gpg').
    """
    return "gpg2" if shutil.which("gpg2") else "gpg"


def list_gpg_keys(secret=False):
    """
    List the GPG keys available in the user's keyring.

    :param secret: When True list secret (private) keys instead of public ones.
    :return: List of dicts with 'id', 'fingerprint' and 'uids' keys.
    """
    command = "--list-secret-keys" if secret else "--list-keys"
    try:
        result = subprocess.run(
            [which_gpg(), command, "--with-colons"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return parse_gpg_colons(result.stdout)


def parse_gpg_colons(output):
    """
    Parse the colon-delimited output of gpg --list-keys.

    :param output: The raw gpg output.
    :return: List of dicts with 'id', 'fingerprint' and 'uids' keys.
    """
    keys = []
    current = None
    for line in output.splitlines():
        fields = line.split(":")
        record = fields[0]
        if record in ("pub", "sec"):
            current = {"id": fields[4], "fingerprint": "", "uids": []}
            keys.append(current)
        elif current is not None:
            if record == "fpr" and not current["fingerprint"]:
                current["fingerprint"] = fields[9]
            elif record == "uid":
                current["uids"].append(fields[9])
    return keys


def read_gpg_ids(store_dir, folder=""):
    """
    Read the GPG ids that apply to a folder in the password store.

    Walks up from the given folder to the store root looking for the
    nearest .gpg-id file, the same way pass resolves keys.

    :param store_dir: Root directory of the password store.
    :param folder: Folder relative to the store root, '' for the root.
    :return: Tuple of (list of gpg ids, folder the .gpg-id file was found in).
    """
    store_dir = os.path.expanduser(store_dir)
    parts = [part for part in folder.split("/") if part]
    while True:
        candidate = os.path.join(store_dir, *parts, ".gpg-id")
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as gpg_id_file:
                ids = [line.strip() for line in gpg_id_file if line.strip()]
            return ids, "/".join(parts)
        if not parts:
            return [], ""
        parts.pop()


def reencrypt_store(store, folder, gpg_ids):
    """
    Set the GPG ids for a (sub)store and re-encrypt its passwords.

    This is what 'pass init' does. It is implemented here because
    passpy's own init_store cannot handle an already existing store
    directory.

    :param store: The passpy Store instance.
    :param folder: Folder relative to the store root, '' for the root.
    :param gpg_ids: List of GPG ids to encrypt with.
    """
    path = store.store_dir
    if folder:
        path = os.path.normpath(os.path.join(path, folder))
    os.makedirs(path, exist_ok=True)
    gpg_id_path = os.path.join(path, ".gpg-id")
    with open(gpg_id_path, "w", encoding="utf-8") as gpg_id_file:
        gpg_id_file.write("\n".join(gpg_ids))
        gpg_id_file.write("\n")
    joined_ids = ", ".join(gpg_ids)
    git_add_path(store.repo, gpg_id_path, f"Set GPG id to {joined_ids}.")
    reencrypt_path(path, gpg_bin=store.gpg_bin, gpg_opts=store.gpg_opts)
    git_add_path(
        store.repo,
        path,
        f"Reencrypt password store using new GPG id {joined_ids}.",
    )


def key_matches_id(key, gpg_id):
    """
    Check whether a parsed gpg key matches an id from a .gpg-id file.

    The id can be a key id, a fingerprint, an e-mail address or a full uid.

    :param key: Dict as returned by list_gpg_keys.
    :param gpg_id: The id string to match against.
    :return: True when the key matches the id.
    """
    if gpg_id in (key["id"], key["fingerprint"]):
        return True
    if key["fingerprint"].endswith(gpg_id) or key["id"].endswith(gpg_id):
        return True
    for uid in key["uids"]:
        if gpg_id == uid or f"<{gpg_id}>" in uid:
            return True
    return False
