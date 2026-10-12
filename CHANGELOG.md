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
- Python 3.11 or newer is required.
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
- Configurable gpg, git, pass and qrencode executables; on Windows gpg is
  also found in the Gpg4win folder.
- Signed `.gpg-id` files: with a signing key configured, globally or per
  profile, recipient lists are signed (`.gpg-id.sig`, compatible with pass's
  `PASSWORD_STORE_SIGNING_KEY`) and verified before anything is encrypted.
  Lists written here carry the QtPass 2.0 generation and folder header, and
  a record next to the settings refuses an older generation, a list copied
  from another folder or a different list under the same generation. The
  Users dialog preselects only a trusted list and says why otherwise.
- "Use the pass command-line tool": changes go through the `pass` script
  (listing and search stay native, links are still refused first).
- Profiles are a list with a form: folder, signing key, and whether to use
  Git, push automatically and pull on startup, each "as configured" or
  overridden. Profiles stored by 0.2 (just a path) are read as before.
- The menu bar can be hidden with Ctrl+M (also in the tray menu); Alt shows
  it for as long as it is used.

### Translations

- The translations of QtPass's Weblate translators are reused for every
  string PyQtPass shares with QtPass: 64 languages, around 75 strings each
  (`scripts/import_qtpass_translations.py`). Existing translations are kept.
- Translations load for the system's UI languages, with a language-only
  file (`localization_it`) serving its regional variants.

### Fixes

- Translations were never loaded (wrong directory, and the translator was
  garbage collected).
- Toolbar and menu actions passed a stray `checked` argument to their slots.
- Saving settings before the window had stored its geometry wrote a Python
  type into the settings.
- The lint workflow's `**/*.py` glob did not match the files in the root.

### Security notes

- With a signing key, a folder whose signed list was removed, is a link or
  is not a file is refused instead of falling back to its parent's
  recipients, and a list naming no key is refused like pass does.
- A signed list is never replaced by an unsigned one: without the signing
  key the recipients of such a folder cannot be changed.
- Signing uses `--local-user <fingerprint>!` and the signature is checked
  against the configured key before the list is written.
- Re-encryption works on the exact decrypted bytes, and a move or copy that
  needs re-encryption only takes its place once that succeeded.
- PyQtPass's own git commits run without repository hooks or fsmonitor and
  commit only their own paths; pull and push keep the user's git setup.
- Commands run in a session of their own with empty standard input and
  `GIT_TERMINAL_PROMPT=0`, so git and ssh never wait on a hidden terminal;
  a timeout ends the whole process group.
- The single-instance socket lives in the private runtime directory, and
  only an instance that answers with PyQtPass's greeting is taken for one.

### Responsiveness

- Copying, editing, saving, renaming, moving, duplicating and deleting run
  gpg and git on a worker thread. Store changes and git pull/push share a
  lock, so they never run at the same time.
- Quitting while work is running no longer hangs: tasks are cancelled, given
  a moment, and their commands are then terminated.
- A save whose commit fails says that the entry was saved but not committed,
  and closes; an unchanged entry is not written again.

### Maintenance

- pytest suite (store backend against a throwaway GnuPG home, RFC 6238
  vectors, entry parsing, offscreen GUI smoke tests), run in CI on Python 3.11
  and 3.13.
- Release builds compile the translations with Qt 6.8 LTS tools.
- `requirements-dev.txt` and `pyproject.toml` for the development tools.
- Python 3.11 or newer is required (Markdown 3.11 needs it; 3.10 is end of
  life).
