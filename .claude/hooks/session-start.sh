#!/bin/bash
# Prepares a Claude Code cloud session for PyQtPass: the system libraries
# PyQt6 needs, GnuPG, Git, pass and Qt's lrelease, and the Python tools
# (pylint, black, pytest) in a project virtualenv.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

PACKAGES="libegl1 libgl1 libxkbcommon0 libdbus-1-3 libglib2.0-0 libfontconfig1 \
gnupg git pass qt6-l10n-tools python3-venv"
missing=""
for package in $PACKAGES; do
  dpkg -s "$package" >/dev/null 2>&1 || missing="$missing $package"
done
if [ -n "$missing" ]; then
  as_root=""
  if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null && sudo -n true 2>/dev/null; then
      as_root="sudo -n"
    else
      echo "Not root and no sudo: install these yourself:$missing" >&2
      missing=""
    fi
  fi
  if [ -n "$missing" ]; then
    # shellcheck disable=SC2086
    $as_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq
    # shellcheck disable=SC2086
    $as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $missing >/dev/null
  fi
fi

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
# Only goes to the network when the requirements changed since last time.
wanted=$(cat requirements.txt requirements-dev.txt | sha256sum)
if [ "$(cat .venv/.requirements 2>/dev/null)" != "$wanted" ]; then
  .venv/bin/pip install -q --disable-pip-version-check -r requirements-dev.txt
  echo "$wanted" > .venv/.requirements
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$CLAUDE_PROJECT_DIR/.venv\""
    echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:/usr/lib/qt6/bin:\$PATH\""
    echo "export QT_QPA_PLATFORM=offscreen"
  } >> "$CLAUDE_ENV_FILE"
fi
