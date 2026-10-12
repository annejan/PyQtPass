"""
GPG helper functions for PyQtPass.

Used to detect the gpg binary, list, generate, import and export keys and
read the .gpg-id files that determine which keys a password (sub)store is
encrypted for.
"""

import os
import re
import shutil

from pyqtpass import executor

_gpg_binary = {"path": ""}

# Validity letters gpg uses for keys that cannot be encrypted to.
UNUSABLE_VALIDITY = {"e": "expired", "r": "revoked", "i": "invalid", "d": "disabled"}


def set_gpg_executable(path):
    """
    Configure the gpg executable, '' to look it up on the PATH.

    :param path: Path or name of the gpg executable.
    """
    _gpg_binary["path"] = path or ""


def which_gpg():
    """
    Find the gpg binary, preferring a configured one and then gpg2 like
    pass itself does.

    :return: Name or path of the gpg binary.
    """
    if _gpg_binary["path"]:
        return _gpg_binary["path"]
    for name in ("gpg2", "gpg"):
        if shutil.which(name):
            return name
    if os.name == "nt":
        # Gpg4win does not always end up on the PATH.
        for base in ("ProgramFiles(x86)", "ProgramFiles"):
            candidate = os.path.join(
                os.environ.get(base, ""), "GnuPG", "bin", "gpg.exe"
            )
            if os.path.isfile(candidate):
                return candidate
    return "gpg"


def unescape_colon_field(value):
    """
    Undo the \\xNN escaping gpg applies to fields in --with-colons output.

    :param value: The escaped field.
    :return: The unescaped string.
    """
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), value)


def list_gpg_keys(secret=False):
    """
    List the GPG keys available in the user's keyring.

    :param secret: When True list secret (private) keys instead of public ones.
    :return: List of dicts as returned by parse_gpg_colons.
    """
    command = "--list-secret-keys" if secret else "--list-keys"
    returncode, stdout, _ = executor.run(
        [which_gpg(), "--batch", command, "--with-colons", "--fixed-list-mode"],
        timeout=30,
    )
    if returncode != 0:
        return []
    return parse_gpg_colons(stdout.decode(errors="replace"))


def parse_gpg_colons(output):
    """
    Parse the colon-delimited output of gpg --list-keys.

    :param output: The raw gpg output.
    :return: List of dicts with 'id', 'fingerprint', 'uids' and 'validity'
             keys; 'validity' is the gpg validity letter of the primary key.
    """
    keys = []
    current = None
    in_subkey = False
    for line in output.splitlines():
        fields = line.split(":")
        record = fields[0]
        if record in ("pub", "sec"):
            current = {
                "id": fields[4],
                "fingerprint": "",
                "uids": [],
                "validity": fields[1] if len(fields) > 1 else "",
            }
            keys.append(current)
            in_subkey = False
        elif current is None:
            continue
        elif record in ("sub", "ssb"):
            in_subkey = True
        elif record == "fpr" and not in_subkey and not current["fingerprint"]:
            current["fingerprint"] = fields[9]
        elif record == "uid":
            current["uids"].append(unescape_colon_field(fields[9]))
    return keys


def key_problem(key):
    """
    :param key: Dict as returned by list_gpg_keys.
    :return: Why the key cannot be used ('expired', 'revoked', ...) or ''.
    """
    return UNUSABLE_VALIDITY.get(key.get("validity", ""), "")


def parse_gpg_id_lines(text):
    """
    Parse the contents of a .gpg-id file like pass 1.7.4 does: everything
    after a '#' is a comment and blank lines are ignored.

    :param text: The contents of the file.
    :return: List of gpg ids.
    """
    ids = []
    for line in text.splitlines():
        gpg_id = line.split("#", 1)[0].strip()
        if gpg_id:
            ids.append(gpg_id)
    return ids


def key_matches_id(key, gpg_id):
    """
    Check whether a parsed gpg key matches an id from a .gpg-id file.

    The id can be a key id, a fingerprint, an e-mail address or a full uid.

    :param key: Dict as returned by list_gpg_keys.
    :param gpg_id: The id string to match against.
    :return: True when the key matches the id.
    """
    gpg_id = gpg_id.strip()
    if gpg_id.startswith("0x"):
        gpg_id = gpg_id[2:]
    upper_id = gpg_id.upper()
    if upper_id in (key["id"].upper(), key["fingerprint"].upper()):
        return True
    if len(gpg_id) >= 8 and (
        key["fingerprint"].upper().endswith(upper_id)
        or key["id"].upper().endswith(upper_id)
    ):
        return True
    for uid in key["uids"]:
        if gpg_id == uid or f"<{gpg_id}>" in uid:
            return True
    return False


def generate_key(name, email, passphrase=None, comment=""):
    """
    Generate a new GPG key pair.

    :param name: Real name for the user id.
    :param email: E-mail address for the user id.
    :param passphrase: The passphrase, or None/'' for an unprotected key.
    :param comment: Optional user id comment.
    :return: Tuple of (success, gpg output).
    """
    if passphrase and ("\n" in passphrase or "\r" in passphrase):
        raise ValueError("A passphrase cannot contain a line break")
    uid = name
    if comment:
        uid += f" ({comment})"
    if email:
        uid += f" <{email}>"
    output = ""
    for algorithm in ("future-default", "default"):
        returncode, _, stderr = executor.run(
            [
                which_gpg(),
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase-fd",
                "0",
                "--quick-generate-key",
                uid,
                algorithm,
                "default",
                "never",
            ],
            input_data=((passphrase or "") + "\n").encode(),
            timeout=300,
        )
        output = stderr.decode(errors="replace").strip()
        if returncode == 0:
            return True, output
    return False, output


# The parameters QtPass's expert mode starts from; gpg's unattended key
# generation reads them (see the GnuPG manual).
DEFAULT_KEY_TEMPLATE = """%echo Generating a default key
Key-Type: EdDSA
Key-Curve: Ed25519
Subkey-Type: ECDH
Subkey-Curve: Curve25519
Name-Real:
Name-Comment: PyQtPass
Name-Email:
Expire-Date: 0
%no-protection
%commit
%echo done"""


def set_batch_parameter(batch, key, value):
    """
    :param batch: Unattended key generation parameters.
    :param key: A parameter name, like 'Name-Real'.
    :param value: Its new value.
    :return: The parameters with every 'key:' line set to value.
    """
    lines = []
    for line in batch.splitlines():
        if line.strip().lower().startswith(key.lower() + ":"):
            line = f"{key}: {value}"
        lines.append(line)
    return "\n".join(lines)


def _is_control(line, control):
    word = line.strip().split(maxsplit=1)
    return bool(word) and word[0].lower() == control


def apply_passphrase(batch, passphrase):
    """
    Put the passphrase into unattended key generation parameters, like
    QtPass: it replaces any %no-protection or Passphrase: line (gpg would
    make an unprotected key while %no-protection is left), and goes before
    %commit when there is none.

    :param batch: The parameters.
    :param passphrase: The passphrase, '' for an unprotected key.
    :return: The parameters to give gpg.
    """
    protection = f"Passphrase: {passphrase}" if passphrase else "%no-protection"
    lines = []
    spliced = False
    for line in batch.splitlines():
        if not line.strip():
            continue
        if _is_control(line, "%no-protection") or line.strip().lower().startswith(
            "passphrase:"
        ):
            if not spliced:
                lines.append(protection)
                spliced = True
            continue
        lines.append(line)
    if not spliced and passphrase:
        position = next(
            (n for n, line in enumerate(lines) if _is_control(line, "%commit")),
            len(lines),
        )
        lines.insert(position, protection)
    return "\n".join(lines) + "\n"


def generate_key_batch(batch, passphrase=None):
    """
    Generate a key pair from unattended key generation parameters, for
    QtPass's expert mode.

    :param batch: The parameters (see DEFAULT_KEY_TEMPLATE).
    :param passphrase: The passphrase, or None/'' for an unprotected key.
    :return: Tuple of (success, gpg output).
    """
    if passphrase and ("\n" in passphrase or "\r" in passphrase):
        raise ValueError("A passphrase cannot contain a line break")
    returncode, _, stderr = executor.run(
        [which_gpg(), "--batch", "--pinentry-mode", "loopback", "--generate-key"],
        input_data=apply_passphrase(batch, passphrase or "").encode(),
        timeout=300,
    )
    return returncode == 0, stderr.decode(errors="replace").strip()


def export_public_key(key_id):
    """
    Export a public key in ASCII armor.

    :param key_id: Key id or fingerprint to export.
    :return: Tuple of (success, armored key or error output).
    """
    returncode, stdout, stderr = executor.run(
        [which_gpg(), "--batch", "--armor", "--export", "--", key_id], timeout=30
    )
    armored = stdout.decode(errors="replace")
    if returncode != 0 or not armored.strip():
        return False, stderr.decode(errors="replace").strip()
    return True, armored


def import_keys(data):
    """
    Import keys into the keyring.

    :param data: The key material, armored or binary, as bytes.
    :return: Tuple of (success, gpg output).
    """
    returncode, _, stderr = executor.run(
        [which_gpg(), "--batch", "--import"], input_data=data, timeout=60
    )
    return returncode == 0, stderr.decode(errors="replace").strip()
