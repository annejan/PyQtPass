# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['pyqtpass.py'],
    pathex=[],
    binaries=[],
    datas=[('artwork', 'artwork'), ('localization', 'localization')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    upx=True
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PyQtPass',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='artwork/icon.ico',
)

app = BUNDLE(
    exe,
    name='PyQtPass.app',
    icon='artwork/icon.icns',
    bundle_identifier='com.IJHack.PyQtPass'
)