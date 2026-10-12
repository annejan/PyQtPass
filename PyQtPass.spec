# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build of PyQtPass: pyinstaller PyQtPass.spec
#
# Windows and Linux get a single-file program. macOS gets a folder-based
# .app (PyInstaller is dropping single-file .app bundles), and so does any
# build with PYQTPASS_ONEDIR=1, which the AppImage is made from.

import os
import re
import sys

with open(os.path.join("pyqtpass", "__init__.py"), encoding="utf-8") as handle:
    VERSION = re.search(r'__version__ = "([^"]+)"', handle.read()).group(1)

ONEDIR = sys.platform == "darwin" or os.environ.get("PYQTPASS_ONEDIR") == "1"

a = Analysis(
    [os.path.join("pyqtpass", "__main__.py")],
    pathex=["."],
    binaries=[],
    datas=[
        ("pyqtpass/artwork", "pyqtpass/artwork"),
        ("pyqtpass/localization", "pyqtpass/localization"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

common = dict(
    name="PyQtPass",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="pyqtpass/artwork/icon.ico",
)

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PyQtPass")
    if sys.platform == "darwin":
        app = BUNDLE(
            coll,
            name="PyQtPass.app",
            icon="pyqtpass/artwork/icon.icns",
            bundle_identifier="com.IJHack.PyQtPass",
            version=VERSION,
            info_plist={
                "CFBundleShortVersionString": VERSION,
                "NSHighResolutionCapable": True,
            },
        )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
