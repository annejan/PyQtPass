#!/bin/bash
# Build the Linux AppImage from a folder build:
#   PYQTPASS_ONEDIR=1 pyinstaller PyQtPass.spec
#   packaging/linux/build-appimage.sh 0.3.0
# The result is dist/PyQtPass-<version>-x86_64.AppImage. It bundles Qt and
# Python only; gpg, git and pass are the system's.
set -euo pipefail

VERSION="$1"
APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
TOOL="build/appimagetool-x86_64.AppImage"
APPDIR="build/PyQtPass.AppDir"

mkdir -p build
if [ ! -f "$TOOL" ]; then
  curl -sSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-x86_64.AppImage"
fi
echo "${APPIMAGETOOL_SHA256}  ${TOOL}" | sha256sum --check --quiet
chmod +x "$TOOL"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a dist/PyQtPass/. "$APPDIR/usr/bin/"
cp packaging/linux/pyqtpass.desktop "$APPDIR/pyqtpass.desktop"
cp packaging/linux/pyqtpass.desktop "$APPDIR/usr/share/applications/"
cp pyqtpass/artwork/icon.svg "$APPDIR/pyqtpass.svg"
cp pyqtpass/artwork/icon.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/pyqtpass.svg"
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/PyQtPass" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# --appimage-extract-and-run: no FUSE needed on the build machine.
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream \
  "$APPDIR" "dist/PyQtPass-${VERSION}-x86_64.AppImage"
