"""
Signed recipient lists (.gpg-id files) with rollback detection.

With a signing key configured, like PASSWORD_STORE_SIGNING_KEY in pass
1.7.4, every .gpg-id has a detached signature in .gpg-id.sig, and a list
whose signature does not verify with one of the signing keys is not used:
nothing is encrypted to it.

A signature proves a list authentic, not current or placed. Like QtPass 2.0
a list written here therefore starts with two comment lines (ignored by pass
and covered by the signature):

    # QtPass-GpgId-Generation: N
    # QtPass-GpgId-Folder: <folder, '.' for the root>

and this device remembers, per list, the highest generation it accepted or
wrote together with a SHA-256 of its bytes. An older generation, a list
written for another folder, or other bytes under a remembered generation are
refused with a message saying how a signing-key holder gets through: saving
the recipients again in the Users dialog.
"""

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time

import executor
from fs_utils import atomic_write, is_link

OUR_COMMENT = "# QtPass-GpgId-"
GENERATION_PREFIX = "# QtPass-GpgId-Generation: "
FOLDER_PREFIX = "# QtPass-GpgId-Folder: "
MAX_GENERATION = 999999999999999999
LOCK_TIMEOUT = 10

VALIDSIG = re.compile(
    r"^\[GNUPG:\] VALIDSIG ([A-F0-9]{40}(?:[A-F0-9]{24})?) .* "
    r"([A-F0-9]{40}(?:[A-F0-9]{24})?)\r?$",
    re.MULTILINE,
)
FINGERPRINT = re.compile(r"^(?:[A-F0-9]{40}|[A-F0-9]{64})$")


class TrustError(Exception):
    """A recipient list that must not be used, with the reason."""


def is_fingerprint(value):
    """
    :param value: A key specification.
    :return: True for a full v4 (40) or v5/v6 (64 hex digits) fingerprint.
    """
    return bool(FINGERPRINT.match(value.strip().upper()))


def parse_header(text):
    """
    Read the generation header of a recipient list.

    :param text: The contents of the .gpg-id file.
    :return: Tuple of (generation, folder); (0, None) without a header.
    :raises TrustError: when the header is malformed.
    """
    generation = None
    folder = None
    for line in text.splitlines():
        if not line.startswith(OUR_COMMENT):
            continue
        if line.startswith(GENERATION_PREFIX):
            if generation is not None:
                raise TrustError("The list carries more than one generation line.")
            digits = line[len(GENERATION_PREFIX) :]
            if not digits.isdigit() or not digits.isascii() or len(digits) > 18:
                raise TrustError(f"The generation line is malformed: {line}")
            generation = int(digits)
        elif line.startswith(FOLDER_PREFIX):
            if folder is not None:
                raise TrustError("The list carries more than one folder line.")
            folder = line[len(FOLDER_PREFIX) :]
            if not folder:
                raise TrustError(f"The folder line is malformed: {line}")
        else:
            raise TrustError(f"The header line is malformed: {line}")
    if generation is not None and folder is None:
        raise TrustError("The list carries a generation line but no folder line.")
    return generation or 0, folder


def folder_label(folder):
    """
    :param folder: Folder relative to the store root, '' for the root.
    :return: The folder as written in the header.
    """
    return folder.strip("/") or "."


def with_header(generation, folder, gpg_ids):
    """
    :param generation: The generation number.
    :param folder: Folder relative to the store root.
    :param gpg_ids: The recipients.
    :return: The contents of a recipient list with header.
    """
    return (
        f"{GENERATION_PREFIX}{generation}\n"
        f"{FOLDER_PREFIX}{folder_label(folder)}\n" + "\n".join(gpg_ids) + "\n"
    )


def list_key(gpg_id_file):
    """
    :param gpg_id_file: Path of a .gpg-id file.
    :return: The key of the list in the generation record.
    """
    folder = os.path.realpath(os.path.dirname(os.path.abspath(gpg_id_file)))
    canonical = os.path.join(folder, os.path.basename(gpg_id_file))
    canonical = canonical.replace(os.sep, "/")
    if os.name == "nt":
        canonical = canonical.lower()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def digest(contents):
    """
    :param contents: The bytes of a recipient list.
    :return: Their SHA-256 as hex.
    """
    return hashlib.sha256(contents).hexdigest()


class GenerationRecord:  # pylint: disable=too-few-public-methods
    """
    The per-device memory of accepted and written list generations: a JSON
    file read afresh and locked against other processes for every
    transaction.
    """

    def __init__(self, path):
        self.path = path

    @contextlib.contextmanager
    def transaction(self):
        """
        Lock the record and yield its entries; changes are written back.

        :raises TrustError: when the record cannot be locked, read or written.
        """
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        lock_path = self.path + ".lock"
        deadline = time.time() + LOCK_TIMEOUT
        while True:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError as error:
                if time.time() > deadline:
                    raise TrustError(
                        f"The generation record {self.path} is locked by "
                        f"another process (remove {lock_path} if none runs)."
                    ) from error
                time.sleep(0.05)
            except OSError as error:
                raise TrustError(
                    f"The generation record {self.path} cannot be locked: {error}"
                ) from error
        try:
            os.close(descriptor)
            entries = self._read()
            before = json.dumps(entries, sort_keys=True)
            yield entries
            if json.dumps(entries, sort_keys=True) != before:
                self._write(entries)
        finally:
            with contextlib.suppress(OSError):
                os.remove(lock_path)

    def _read(self):
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as record_file:
                data = json.load(record_file)
        except (OSError, ValueError) as error:
            raise TrustError(
                f"The generation record {self.path} cannot be read: {error}"
            ) from error
        if not isinstance(data, dict):
            raise TrustError(f"The generation record {self.path} is malformed.")
        return data

    def _write(self, entries):
        directory = os.path.dirname(self.path) or "."
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".record-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(entries, handle, indent=1, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            with contextlib.suppress(OSError):
                os.remove(temporary)
            raise TrustError(
                f"The generation record {self.path} cannot be written: {error}"
            ) from error


def _way_through(last, record_path):
    return (
        "A holder of the signing key gets through by opening Users on the "
        f"folder and saving the recipients, which writes generation {last + 1}. "
        f"Removing {record_path} forgets what this device accepted before."
    )


class GpgIdSigner:
    """
    Signs and verifies recipient lists and keeps their generations.
    """

    def __init__(self, signing_keys, gpg_bin, record):
        """
        :param signing_keys: Full fingerprints of the signing keys.
        :param gpg_bin: The gpg executable.
        :param record: A GenerationRecord.
        """
        self.keys = [key.strip().upper() for key in signing_keys if key.strip()]
        self.gpg_bin = gpg_bin
        self.record = record

    @property
    def enabled(self):
        """:return: True when a signing key is configured."""
        return bool(self.keys)

    def sign(self, gpg_id_file, contents):
        """
        Write a detached signature of contents to gpg_id_file + '.sig'.

        :param gpg_id_file: Path of the .gpg-id file.
        :param contents: The bytes that were written to it.
        :raises TrustError: when gpg fails.
        """
        returncode, stdout, stderr = executor.run(
            [
                self.gpg_bin,
                "--batch",
                "--yes",
                "--default-key",
                self.keys[0],
                "--detach-sign",
                "--output",
                "-",
                "-",
            ],
            input_data=contents,
            timeout=300,
        )
        if returncode != 0 or not stdout:
            raise TrustError(
                "Signing the recipient list failed: "
                + (stderr.decode(errors="replace").strip() or "gpg wrote nothing")
            )
        signature = gpg_id_file + ".sig"
        if is_link(signature):
            raise TrustError(f"{signature} is a symbolic link")
        atomic_write(signature, stdout)

    def verify(self, gpg_id_file, contents):
        """
        Check the detached signature of a recipient list.

        :param gpg_id_file: Path of the .gpg-id file.
        :param contents: The bytes read from it; these are what is verified.
        :raises TrustError: when the signature is missing or not valid.
        """
        signature = gpg_id_file + ".sig"
        if is_link(signature) or not os.path.isfile(signature):
            raise TrustError(
                f"The recipient list {gpg_id_file} has no signature, while a "
                "signing key is configured."
            )
        returncode, stdout, _ = executor.run(
            [
                self.gpg_bin,
                "--batch",
                "--verify",
                "--status-fd=1",
                "--",
                signature,
                "-",
            ],
            input_data=contents,
            timeout=60,
        )
        fingerprints = []
        for match in VALIDSIG.finditer(stdout.decode(errors="replace")):
            fingerprints += [match.group(1), match.group(2)]
        if returncode != 0 or not any(key in fingerprints for key in self.keys):
            raise TrustError(
                f"The signature of the recipient list {gpg_id_file} does not "
                "verify with the signing key."
            )

    def accept(self, gpg_id_file, contents, folder):
        """
        Verify a recipient list and check it is current and in its place.

        :param gpg_id_file: Path of the .gpg-id file.
        :param contents: Its bytes.
        :param folder: Folder of the list relative to the store root.
        :raises TrustError: when the list must not be used.
        """
        self.verify(gpg_id_file, contents)
        try:
            generation, written_for = parse_header(contents.decode("utf-8"))
        except (TrustError, UnicodeDecodeError) as error:
            raise TrustError(
                f"The signed recipient list {gpg_id_file} is not one to trust: "
                f"{error}"
            ) from error
        if written_for is not None and written_for != folder_label(folder):
            raise TrustError(
                f"The signed recipient list {gpg_id_file} was written for the "
                f'folder "{written_for}", not for "{folder_label(folder)}", and '
                "is not used. If the folder was moved or renamed, a holder of "
                "the signing key saves the recipients in Users again."
            )
        key = list_key(gpg_id_file)
        with self.record.transaction() as entries:
            entry = entries.get(key, {})
            last = int(entry.get("generation", "0"))
            known = entry.get("digest")
            if generation < last:
                if written_for is None:
                    raise TrustError(
                        f"The signed recipient list {gpg_id_file} carries no "
                        f"generation line, while generation {last} was accepted "
                        "here before. " + _way_through(last, self.record.path)
                    )
                raise TrustError(
                    f"The signed recipient list {gpg_id_file} is generation "
                    f"{generation}, older than generation {last}, the last one "
                    "accepted here. It may have been put back by someone else. "
                    + _way_through(last, self.record.path)
                )
            if generation == 0:
                return
            this_digest = digest(contents)
            if generation == last and known and known != this_digest:
                raise TrustError(
                    f"The signed recipient list {gpg_id_file} is generation "
                    f"{generation}, like a different list this device accepted "
                    "before: two devices saved recipients at the same time, or "
                    "an authentic list was swapped in. "
                    + _way_through(last, self.record.path)
                )
            entries[key] = {"generation": str(generation), "digest": this_digest}

    def reserve_next(self, gpg_id_file, on_disk_generation=0):
        """
        :param gpg_id_file: Path of the .gpg-id file about to be written.
        :param on_disk_generation: Generation of the verified list there now.
        :return: The generation to write.
        """
        key = list_key(gpg_id_file)
        with self.record.transaction() as entries:
            last = int(entries.get(key, {}).get("generation", "0"))
            base = max(last, on_disk_generation)
            if base >= MAX_GENERATION:
                raise TrustError(
                    f"The recipient list {gpg_id_file} has reached the highest "
                    "generation; it cannot be written."
                )
            entries[key] = {"generation": str(base + 1), "digest": ""}
            return base + 1

    def record_written(self, gpg_id_file, contents):
        """
        Remember the bytes of a list this device just wrote.

        :param gpg_id_file: Path of the .gpg-id file.
        :param contents: The bytes written.
        """
        generation, _ = parse_header(contents.decode("utf-8"))
        key = list_key(gpg_id_file)
        with self.record.transaction() as entries:
            entries[key] = {"generation": str(generation), "digest": digest(contents)}
