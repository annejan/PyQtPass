# Contributing to PyQtPass

Bug reports, ideas and pull requests are welcome on
[GitHub](https://github.com/annejan/PyQtPass/issues).

## Code

```sh
pip install -r requirements-dev.txt
pylint $(git ls-files '*.py')
black --check .
QT_QPA_PLATFORM=offscreen python -m pytest --cov=pyqtpass
```

CI runs the same checks on Python 3.11 and 3.13. The tests make their own
GnuPG home and key, and never touch your keyring or password store.

Licensing follows [REUSE](https://reuse.software): `REUSE.toml` says who
holds the copyright of each file and under which licence it is, and the
licence texts are in `LICENSES/`. A new file under GPL-3.0-or-later needs
nothing extra; for anything else, add it to `REUSE.toml`. Check with
`pipx run reuse lint`.

The code lives in the `pyqtpass` package. `main_window.py` holds the main
window; its menus, store changes, clipboard and git actions are mixins in
`window_actions.py`, `store_actions.py`, `clipboard_actions.py` and
`git_actions.py`. `password_store.py` is the `pass` compatible store,
`real_pass.py` the variant that runs the `pass` script.

## Translations

PyQtPass uses Qt's translation files, one per language in
`pyqtpass/localization/localization_<language>.ts`.

### Translating

1. Open the `.ts` file of your language with Qt Linguist (`linguist`, in the
   `qt6-tools-dev-tools` or `qt6-l10n-tools` package or the Qt installer),
   or with any editor: each `<message>` has a `<source>` and a
   `<translation>`.
2. Translate the messages marked unfinished. Keep placeholders like `{}` and
   `{0}` as they are; they are filled in by the program.
3. Check the result: compile it and start PyQtPass in your language.

   ```sh
   lrelease pyqtpass/localization/localization_nl_NL.ts
   LANGUAGE=nl_NL python -m pyqtpass
   ```

4. Open a pull request with the changed `.ts` file. The `.qm` files are made
   by the build; do not commit them.

A language that is missing can be added by copying `localization_en_US.ts`
to the new name, setting its `language` attribute, and adding it to
`pyqtpass.pro`.

### Strings shared with QtPass

Many strings are the same as in [QtPass](https://github.com/IJHack/QtPass),
whose translators work on
[Weblate](https://hosted.weblate.org/projects/qtpass/). Those translations
can be imported from a QtPass checkout; existing PyQtPass translations are
never overwritten:

```sh
git clone https://github.com/IJHack/QtPass.git ../QtPass
python scripts/import_qtpass_translations.py ../QtPass
```

### After changing strings in the code

User-visible text goes through `self.tr()`, or through
`QCoreApplication.translate("QtPassGUI", ...)` in the main window mixins so
it stays in the main window's context. The modules that do not use Qt
themselves, like the password store, use `translate()` from
`pyqtpass/i18n.py`. Pass literal strings and fill in `{}` placeholders
afterwards, so `pylupdate6` finds them. Update the `.ts` files with
`pylupdate6` (which comes with PyQt6) from inside the package folder; the
import script above does this too:

```sh
cd pyqtpass
pylupdate6 --ts localization/localization_nl_NL.ts *.py
```

`tests/test_translations.py` checks that every translation keeps the
placeholders of its source text.

## Releasing

1. Set the version in `pyqtpass/__init__.py` and turn the "Unreleased"
   section of `CHANGELOG.md` into that version; merge that.
2. Run the Build and Release workflow on `main` with the version, like
   `v0.5.0` (or push that tag). It makes the tag and a draft release with the
   changelog section as notes, and attaches the builds, source archives,
   `SHA256SUMS` and the build provenance attestation. With `dry_run` it only
   builds, and keeps the files as a workflow artifact.
3. Sign the files with your GnuPG key; `--dryrun` first shows what it would
   upload:

   ```sh
   scripts/sign-release-assets.sh v0.5.0
   ```

4. Publish the draft. A published release's files are never replaced by a
   workflow re-run.
5. Publishing the release runs the PyPI workflow, which builds the sdist and
   the wheel from the tag and uploads them to PyPI with trusted publishing
   (no token; the `pypi` environment must approve it if it has reviewers).
   To try a version on TestPyPI first, or to retry an upload, run the PyPI
   workflow by hand with the version and `testpypi` or `pypi`.

The PyPI workflow also builds and checks the package on every pull request.
