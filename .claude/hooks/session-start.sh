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
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  # shellcheck disable=SC2086
  apt-get install -y -qq $missing >/dev/null
fi

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --disable-pip-version-check -r requirements-dev.txt

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$CLAUDE_PROJECT_DIR/.venv\""
    echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:/usr/lib/qt6/bin:\$PATH\""
    echo "export QT_QPA_PLATFORM=offscreen"
  } >> "$CLAUDE_ENV_FILE"
fi
