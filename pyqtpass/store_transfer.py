"""
Moving and copying entries and folders in the password store, like
'pass mv' and 'pass cp': entries are re-encrypted when their new place has
other recipients, signed recipient lists are signed again for their new
folder, and a failure leaves the store as it was.
"""

import contextlib
import os
import shutil
import tempfile

from pyqtpass.fs_utils import atomic_write, is_link
from pyqtpass.i18n import translate
from pyqtpass.gpgid_trust import TrustError, list_key
from pyqtpass.store_base import GPG_EXT, GPG_ID, STAGING_PREFIX, StoreError, locked


class TransferMixin:
    """
    The move and copy operations of PasswordStore.
    """

    def _source_and_target(self, old_path, new_path, force):
        old_clean = self.clean_path(old_path)
        new_clean = self.clean_path(new_path)
        if not old_clean or not new_clean:
            raise StoreError(
                translate("PasswordStore", "Cannot move or copy the store root")
            )
        if self.is_folder(old_clean):
            source = self.absolute(old_clean)
            if self.is_folder(new_clean) or new_path.endswith("/"):
                new_clean = f"{new_clean}/{old_clean.rsplit('/', 1)[-1]}"
            target = self.absolute(new_clean)
            if target == source or target.startswith(source + os.sep):
                raise StoreError(
                    translate("PasswordStore", "Cannot move {} into itself").format(
                        old_clean
                    )
                )
            relative_target = new_clean
        else:
            source = self.entry_file(old_clean)
            if not os.path.isfile(source):
                raise FileNotFoundError(
                    translate(
                        "PasswordStore", "{} is not in the password store"
                    ).format(old_clean)
                )
            if self.is_folder(new_clean) or new_path.endswith("/"):
                new_clean = f"{new_clean}/{old_clean.rsplit('/', 1)[-1]}"
            target = self.entry_file(new_clean)
            relative_target = new_clean + GPG_EXT
        if os.path.lexists(target) and (not force or os.path.isdir(source)):
            raise FileExistsError(
                translate("PasswordStore", "{} already exists").format(new_clean)
            )
        self.absolute(self._folder_of(new_clean))
        return old_clean, new_clean, source, target, relative_target

    def _inherited_change(self, old_clean, new_clean):
        """
        :return: The recipients at the destination's parent when they differ
                 from those at the source's parent, else None.
        """
        new = self.recipients(self._folder_of(new_clean))
        try:
            old = self.recipients(self._folder_of(old_clean))
        except StoreError:
            return new
        return None if old == new else new

    def _transfer_entry(self, old_clean, new_clean, source, target, keep_source):
        new_recipients = self._inherited_change(old_clean, new_clean)
        if new_recipients is not None:
            data = self.decrypt_bytes(source)
            self.encrypt_to_file(target, data, new_recipients)
            if not keep_source:
                os.remove(source)
        elif keep_source:
            with open(source, "rb") as handle:
                atomic_write(target, handle.read())
        else:
            os.replace(source, target)

    def _transfer_folder(self, old_clean, new_clean, source, target, keep_source):
        """
        Move or copy a folder. Its own recipient lists go with it; with a
        signing key they are signed again for their new place. Entries that
        inherit their recipients are re-encrypted when the new parent has
        other ones. All of that happens in a staging copy, which only takes
        its place when everything succeeded.
        """
        # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        own_ids = {}
        for sub in self._own_lists(source):
            if os.path.lexists(os.path.join(source, sub, GPG_ID + ".sig")) and (
                not self.signer.enabled
            ):
                raise StoreError(
                    translate(
                        "PasswordStore",
                        "/{} has a signed recipient list. "
                        "Configure the signing key, so it can be signed again for "
                        "its new place, before moving or copying it.",
                    ).format(self._join(old_clean, sub))
                )
            ids = self.list_at(self._join(old_clean, sub))
            if ids is not None:
                own_ids[sub] = ids
        new_recipients = (
            None if "" in own_ids else (self._inherited_change(old_clean, new_clean))
        )
        resign = self.signer.enabled and bool(own_ids)
        if not keep_source and new_recipients is None and not resign:
            os.replace(source, target)
            return
        staging = tempfile.mkdtemp(dir=os.path.dirname(target), prefix=STAGING_PREFIX)
        os.rmdir(staging)
        previous = {}
        written = {}
        try:
            # Links are copied as links (they are not followed either way);
            # a junction would be copied as a folder, so it is left out.
            shutil.copytree(
                source,
                staging,
                symlinks=True,
                ignore=lambda folder, names: [
                    name
                    for name in names
                    if is_link(os.path.join(folder, name))
                    and not os.path.islink(os.path.join(folder, name))
                ],
            )
            if new_recipients is not None:
                self._reencrypt_inherited(staging, set(own_ids), new_recipients)
            if resign:
                for sub, ids in own_ids.items():
                    key = list_key(os.path.join(target, sub, GPG_ID))
                    previous[key] = self.signer.entry(key)
                    self.write_gpg_id(
                        os.path.join(staging, sub, GPG_ID),
                        self._join(new_clean, sub),
                        ids,
                        record_path=os.path.join(target, sub, GPG_ID),
                    )
                    written[key] = self.signer.entry(key)
            os.replace(staging, target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            if written:
                # The new lists never took their place: the record goes back
                # to what it knew of the target, which may be a list there
                # that is to be kept, rather than forgetting it.
                with contextlib.suppress(TrustError):
                    self.signer.restore_entries(previous, written)
            raise
        if not keep_source:
            keys = self._list_keys(source, own_ids) if self.signer.enabled else []
            shutil.rmtree(source)
            self._forget(keys)

    def _reencrypt_inherited(self, folder_abs, own, recipients):
        """
        Re-encrypt the entries of a staged folder that inherit their
        recipients, leaving those under a list of their own alone.
        """
        for current, dirs, files in os.walk(folder_abs):
            dirs[:] = [
                name for name in dirs if not is_link(os.path.join(current, name))
            ]
            relative = os.path.relpath(current, folder_abs).replace(os.sep, "/")
            parts = [] if relative == "." else relative.split("/")
            if any("/".join(parts[:depth]) in own for depth in range(len(parts) + 1)):
                continue
            for name in files:
                path = os.path.join(current, name)
                if (
                    name.endswith(GPG_EXT)
                    and not is_link(path)
                    and os.path.isfile(path)
                ):
                    self.encrypt_to_file(path, self.decrypt_bytes(path), recipients)

    def _transfer(self, old_path, new_path, force, keep_source):
        """
        Move or copy an entry or folder; a failure leaves the store as it was.

        :return: Tuple of (old path, new path, git paths to commit).
        """
        old_clean, new_clean, source, target, relative_target = self._source_and_target(
            old_path, new_path, force
        )
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            if os.path.isdir(source):
                self._transfer_folder(old_clean, new_clean, source, target, keep_source)
            else:
                self._transfer_entry(old_clean, new_clean, source, target, keep_source)
        except TrustError as error:
            raise StoreError(str(error)) from error
        paths = [relative_target]
        if not keep_source:
            paths.insert(0, self.relative(source))
        return old_clean, new_clean, paths

    @locked
    def move_path(self, old_path, new_path, force=False):
        """
        Move or rename an entry or folder, re-encrypting it when the
        destination has other recipients, like 'pass mv'.

        :param old_path: Source path relative to the store root.
        :param new_path: Destination path; an existing folder or a path
                         ending in '/' moves the source into it.
        :param force: Overwrite an existing destination entry.
        :return: The destination path relative to the store root.
        """
        old_clean, new_clean, paths = self._transfer(
            old_path, new_path, force, keep_source=False
        )
        self.git_commit(paths, f"Rename {old_clean} to {new_clean}.")
        return new_clean

    @locked
    def copy_path(self, old_path, new_path, force=False):
        """
        Copy an entry or folder, re-encrypting it when the destination has
        other recipients, like 'pass cp'.

        :param old_path: Source path relative to the store root.
        :param new_path: Destination path, see move_path.
        :param force: Overwrite an existing destination entry.
        :return: The destination path relative to the store root.
        """
        old_clean, new_clean, paths = self._transfer(
            old_path, new_path, force, keep_source=True
        )
        self.git_commit(paths, f"Copy {old_clean} to {new_clean}.")
        return new_clean
