# PyQtPass: Python Port of QtPass

## Introduction

<img align="right" src="artwork/icon.png" width="30%" />

Welcome to PyQtPass, an experimental and early-stage Python port of the renowned QtPass, originally developed in C++.
This initiative aims to leverage the versatility and simplicity of Python to enhance maintainability and extend the functionality of QtPass, a user-friendly GUI for `pass`, the standard Unix password manager.

QtPass has been a staple for users who prefer a graphical interface to manage their passwords securely and conveniently.
Recognizing the growing Python ecosystem and its powerful libraries, PyQtPass is an endeavor to transition the application from C++ to Python.
This move not only aligns with modern development practices but also opens up new avenues for features and improvements.

## Project Status: Experimental

Please note that PyQtPass is currently in an **early experimental phase**.
This means that while it encompasses the core functionalities of the original QtPass, it might not yet offer the full range of features, and you might encounter bugs or limitations that are typical in early-stage software.

We are actively developing PyQtPass and working towards a more stable and feature-rich version.
Your feedback and contributions during this phase are invaluable and will help shape the future of this project.

## Features

PyQtPass follows the feature set of [QtPass 2.0](https://github.com/IJHack/QtPass):

- Talks to `gpg` and `git` directly, like QtPass's native backend; no Python password store library needed.
  Entries are written atomically, so a failing `gpg` never truncates a password.
- Tree view for password navigation; the search box matches its words literally and in order against the full path.
- Optional content search: press Enter to search the decrypted contents with a regular expression.
- Content panel showing the password and every field in its own row with a copy button,
  an "open in browser" button for web addresses and optional QR codes (with `qrencode`).
- Built-in TOTP one-time passwords (`otpauth://` URIs or `otp:` fields, including Steam codes), no `pass-otp` needed.
- One dialog for adding and editing entries, with folder picker, field templates (e.g. `login`, `url`)
  and configurable password generation (including a custom character set).
- Adding, editing, renaming, duplicating and deleting passwords and folders; drag and drop to move (Ctrl to copy).
- Clipboard integration: copy on demand or automatically, optional X11 selection, automatic clearing after a timeout,
  and marked as secret so clipboard managers skip it.
- Git integration: pull and push in the background, update on startup and automatic pushing of local changes;
  every change to the store is committed.
- Per-folder GPG recipients (the Users dialog, like `pass init`) with background re-encryption,
  import of keys from a file or the clipboard, key pair generation and exporting your public key to share a store.
- A first-run wizard that sets up a store, a key and Git for new users.
- A dockable process output panel showing what `gpg` and `git` were asked and what they said.
- Multiple password store profiles that can be switched from the toolbar.
- Links inside the store are never followed, and paths cannot escape the store.
- System tray icon, start minimized, hide on close, always on top and a single running instance.
- Cross-platform compatibility, thanks to the Python and PyQt6 combination.

## Installation

PyQtPass needs Python 3.10 or newer and GnuPG (`gpg` or `gpg2`) with a graphical pinentry.
Git is optional (for synchronisation) and so is `qrencode` (for QR codes). Then:

1. Clone this repository:

   ```sh
   git clone https://github.com/annejan/PyQtPass.git
   cd PyQtPass
   ```

2. Install the required Python packages:

   ```sh
   pip install -r requirements.txt
   ```

3. Run the application:

   ```sh
   python pyqtpass.py
   ```

When no password store exists yet, a wizard helps you set one up.

## Usage

Upon launching PyQtPass, you will see a split interface.
On the left side is the tree view of your passwords, and on the right is the content panel of the selected entry.
You can filter the entries using the search box above the tree view.

Fields are `name: value` lines below the password. Add a line like
`otpauth://totp/Example?secret=JBSWY3DPEHPK3PXP` (or `otp: JBSWY3DPEHPK3PXP`) to an entry to get one-time passwords.

## Development

```sh
pip install -r requirements-dev.txt
pylint $(git ls-files '*.py')
black --check .
QT_QPA_PLATFORM=offscreen python -m pytest
```

The tests create a throwaway GnuPG home and key, so they never touch your own keyring or store.

## Contributions and Feedback

We warmly welcome contributions, be it in the form of code, bug reports, suggestions, or documentation.

Since PyQtPass is in its experimental stage, your input is crucial for its refinement and progression.

Should you encounter any issues or have feature suggestions, please feel free to open an issue on our [GitHub issues page](https://github.com/annejan/PyQtPass/issues).

## License

### GNU GPL v3.0

[![GNU GPL v3.0](http://www.gnu.org/graphics/gplv3-127x51.png)](http://www.gnu.org/licenses/gpl.html)

[View official GNU site](http://www.gnu.org/licenses/gpl.html)

[<img src="https://opensource.org/wp-content/uploads/2022/10/osi-badge-dark.svg" alt="OSI-approved license" width="127">](https://opensource.org/licenses/GPL-3.0)

[View the Open Source Initiative site](https://opensource.org/licenses/GPL-3.0)

## Acknowledgments

- `pass`: The standard Unix password manager. For more information, visit [passwordstore.org](https://www.passwordstore.org/).
- `Qt Framework`: PyQtPass utilizes the Qt Framework, specifically Qt 6, a comprehensive set of C++ libraries and development tools that enable the creation of cross-platform applications.
  Discover more about the Qt Framework at [qt.io](https://www.qt.io/).
- `QtPass`: Qt GUI for Pass, written in C++, can be found at [qtpass.org](https://qtpass.org/).
- Co-Authorship: This project includes code and documentation co-written with the assistance of ChatGPT from OpenAI.
- Co-Authorship: The QtPass feature-parity work (clipboard, content panel, git sync, GPG user management, profiles, the native store backend, TOTP, templates, the first-run wizard and key management) and the PyQt6 migration were co-written with the assistance of Claude from Anthropic.
