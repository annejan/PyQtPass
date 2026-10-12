# Changelog

## Unreleased

### Clipboard

- The clipboard setting has QtPass's three modes: No clipboard, Always copy
  and On-demand copy. No clipboard removes the copy buttons from the content
  panel. The old "Always copy to clipboard" setting carries over: on becomes
  Always, off becomes On demand (#47).
- Quitting PyQtPass clears a password or OTP code it copied, like QtPass.
  Before, only the autoclear timer did, so quitting before it ran, or with
  autoclear off, left the password in the clipboard (#45).

## 0.5.0

Portable mode, translated store messages, QtPass's addGPGId setting, and
the first release on PyPI.

### Portable mode

- A `pyqtpass.ini` next to the program holds the settings instead of the
  user's settings, like QtPass's portable `qtpass.ini`. Create an empty one
  to run PyQtPass from a USB stick; the record of signed recipient lists
  moves along with it.

### Translations and settings

- The messages of the password store, the signed recipient lists, gpg and
  the GnuPG home are translatable now; they were English in every language.
  QtPass's translations fill in the ones the projects share, and Dutch has
  all of them.
- Settings, Git has "Automatically add .gpg-id files", like QtPass's
  addGPGId. It is on by default, as before; turned off, setting the
  recipients commits the re-encrypted passwords but leaves the `.gpg-id`
  files out of git.

### Release builds

- A workflow run no longer replaces the files of a draft release that already
  has signatures. Re-pushing the release tag (say, to sign it) used to rebuild
  the files after they were signed, so the `.asc` files no longer matched.
- PyQtPass is published on PyPI: `pipx install pyqtpass`. Publishing a
  release uploads its sdist and wheel, with the translations, using trusted
  publishing; every pull request builds and checks the package.
- The package metadata names the supported Python versions and platforms,
  and the README's picture and links work on PyPI too. The package carries
  every licence text and names the logo's and font's licences as well.
- Licensing follows the REUSE specification, like QtPass: `REUSE.toml`
  records the copyright and licence of every file (GPL-3.0-or-later; the
  logo WTFPL; the Lato font OFL-1.1), with the licence texts in `LICENSES/`,
  and CI checks it.

## 0.4.1

Fixes from the review of 0.3.0 and 0.4.0 (#30), and releases made like
QtPass's: a draft first, source archives, and the maintainer's GnuPG
signature on every file.

### Release builds

- Source archives (`PyQtPass-x.y.z.tar.gz` and `.zip`) are attached to each
  release, with checksums and build provenance like the other files.
- Releases start as drafts. The maintainer signs every file with GnuPG
  (`scripts/sign-release-assets.sh`, like QtPass) before publishing, so each
  file has a `.asc` signature next to it. A workflow re-run never replaces
  the files of a published release.
- The build jobs can only read the repository, and no job keeps the GitHub
  token in its checkout. A release is made from `main` only (a dry run can
  build any branch), and two runs for one version wait for each other.
- PyInstaller is pinned (`requirements-build.txt`). The Windows build no
  longer downloads UPX, which it never actually used.

### Fixes

- A signed move or copy that fails halfway (say, pinentry cancelled) puts
  the generation record back as it was. It used to forget what it knew of
  the destination, so a removed signed list there was no longer noticed and
  new entries were encrypted to the parent's recipients.
- Quitting while git or a store change runs waits at most a minute in all,
  instead of a minute for each, shows a window after a second with a
  "Quit now" button, and never starts a command once it has ended the
  running ones.
- Changing recipients can be cancelled; it says which passwords still use
  the old keys.
- The store lock follows the folder itself, so two spellings of it on a
  case-insensitive volume, or a link to it made later, share one lock.
- Clearer messages: a failed commit after changing recipients no longer
  repeats itself, and a signing failure during a move is reported like any
  other store error.

## 0.4.0

The rest of the QtPass 2.0 feature set (field editing, store templates,
pwgen, GnuPG home, ssh agent, WSL), an installable package, sturdier release
builds and a redrawn icon.

### Upgrade notes

- Release files are named by version and platform, like
  `PyQtPass-0.4.0-windows-x64.exe`; check them against `SHA256SUMS`.
- Running from a checkout is now `python -m pyqtpass` (or `pip install .`
  and `pyqtpass`); the old `pyqtpass.py` script is gone.

### New features

- Field names can be edited in the password dialog, and fields added and
  removed; template fields keep their fixed name.
- Templates kept in the store, like QtPass: a `.templates` file in the store
  root defines named field lists, and a `.default_template` file in a folder
  (or a parent) picks the one its entries use. The password dialog can switch
  templates and keeps everything typed.
- Passwords can be generated with `pwgen`, with the QtPass options (avoid
  capitals or numbers, symbols, easier to remember). The built-in generator
  is used when `pwgen` is missing or fails.
- A GnuPG home other than the default one (System tab).
- Git over ssh works without an ssh agent in the session: a configured
  socket, or the ssh socket of a running gpg-agent (on macOS also the launchd
  one), becomes `SSH_AUTH_SOCK`.
- Windows: programs inside WSL, configured like `wsl gpg2`, run through
  `wsl --exec` with Windows paths translated.
- `pip install .` installs a `pyqtpass` command; `python -m pyqtpass` works.
  A Linux `.desktop` file and an AppImage build are included.
- The icon is redrawn as clean vector shapes (it was a traced bitmap of 270
  KB with visible seams); `scripts/update_icons.py` makes the PNG, ICO and
  ICNS files from it.

### Release builds

- File names carry the version and platform; every release has `SHA256SUMS`
  and a signed build provenance attestation.
- The macOS app is a folder bundle, so it starts without unpacking itself
  first.
- Every GitHub Action is pinned to a commit.

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
- Signing uses `--local-user <fingerprint>` (a signing subkey works) and
  the signature is checked against the configured key before the list is
  written.
- Changing recipients commits the list together with the re-encrypted
  passwords, after re-encryption, so a failed commit never hides passwords
  still encrypted to a removed member.
- Moving, copying or deleting a folder with its own signed list signs the
  list again for its new place and updates the generation record, so the
  folder (or a new one of the old name) is not refused afterwards.
- The generation record is locked with an operating system file lock,
  which a crash releases; there are no stale locks to take over.
- Re-encryption works on the exact decrypted bytes, and a move or copy that
  needs re-encryption only takes its place once that succeeded.
- PyQtPass's own git commits run without repository hooks or fsmonitor and
  commit only their own paths; pull and push keep the user's git setup.
- Commands run in a session of their own with empty standard input and
  `GIT_TERMINAL_PROMPT=0`, so git and ssh never wait on a hidden terminal;
  a timeout ends the whole process group.
- The single-instance socket lives in the private runtime directory (on
  Windows the pipe name carries a private random token), and only an
  instance that answers with this user's token is taken for one.

### Responsiveness

- Copying, editing, saving, renaming, moving, duplicating and deleting run
  gpg and git on a worker thread. Store changes and git pull/push share a
  lock, so they never run at the same time.
- Quitting while work is running no longer hangs: tasks are cancelled and
  given a moment (git and store changes up to a minute, so no lock or half
  merge is left behind), then their commands are terminated.
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
