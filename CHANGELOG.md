# Changelog

## 0.3.0

Brings PyQtPass up to date with the QtPass 2.0 feature set.

### Upgrade notes

- `passpy` is no longer used (it was unmaintained since 2019 and could write an
  empty file when encryption failed). PyQtPass talks to `gpg` and `git`
  directly. `pip install -r requirements.txt` now only installs PyQt6 and
  Markdown.
- The password store folder is a setting now (System tab), so a store outside
  `~/.password-store` no longer needs a profile. A missing store opens the
  first-run wizard instead of quitting.
- Ctrl+Q quits, Ctrl+W closes the window (hides it with "hide on close").
- The 32-bit Windows build is gone: PyQt6 has no 32-bit Windows wheels, so it
  was a 64-bit build under another name.

### New features

- Native `pass` compatible backend with atomic writes, `pass` style git
  commits, re-encryption when moving or copying between folders with other
  recipients, and refusal of symbolic links and paths outside the store.
- Built-in TOTP (RFC 6238; SHA1/256/512, Steam) with a live code and countdown
  in the content panel and a "Copy OTP code" action.
- Content panel with a row and copy button per field, "open in browser" for
  web addresses, QR codes through `qrencode`, monospace, "display as is" and
  line wrapping options.
- Field templates and "show all fields templated", in the panel and in the
  password dialog; repeated fields are kept.
- One dialog for adding and editing passwords, with a folder picker and a
  custom character set for password generation.
- Add folder, rename folder, duplicate, open folder in the file manager, and
  drag and drop to move (Ctrl to copy) entries and folders.
- Search box matches its words literally and in order against the full path;
  optional content search with regular expressions.
- Users dialog: search, keys that cannot be used are marked, recipients whose
  key is missing are kept, import keys from a file or the clipboard, generate a
  key pair, and a warning before locking yourself out.
- Share menu: re-encrypt a folder, export your public key, add a recipient.
- GPG key generation that requires a passphrase or an explicit "No passphrase".
- First-run wizard: pick or generate a key, choose the store folder and Git.
- Dockable process output panel; secrets are never shown in it.
- Git pull/push, re-encryption, search and decryption run in the background.
- Clipboard contents are marked as secret for clipboard managers, and can be
  copied to the X11 selection too.
- Single instance: starting PyQtPass again brings the running window forward.
- Configurable gpg, git and qrencode executables.

### Fixes

- Translations were never loaded (wrong directory, and the translator was
  garbage collected).
- Toolbar and menu actions passed a stray `checked` argument to their slots.
- Saving settings before the window had stored its geometry wrote a Python
  type into the settings.
- The lint workflow's `**/*.py` glob did not match the files in the root.

### Maintenance

- pytest suite (store backend against a throwaway GnuPG home, RFC 6238
  vectors, entry parsing, offscreen GUI smoke tests), run in CI on Python 3.11
  and 3.13.
- Release builds compile the translations with Qt 6.8 LTS tools.
- `requirements-dev.txt` and `pyproject.toml` for the development tools.
