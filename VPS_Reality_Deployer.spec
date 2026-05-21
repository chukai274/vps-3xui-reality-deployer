# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


BIN_DIR = Path(sys.executable).resolve().parent / "Library" / "bin"
DLL_NAMES = [
    "libssl-3-x64.dll",
    "libcrypto-3-x64.dll",
    "libexpat.dll",
    "libmpdec-4.dll",
    "liblzma.dll",
    "libbz2.dll",
    "ffi.dll",
]
binaries = [(str(BIN_DIR / name), ".") for name in DLL_NAMES if (BIN_DIR / name).exists()]


a = Analysis(
    ['vps_auto_deployer.py'],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VPS_Reality_Deployer',
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
    icon=['assets\\vps_deployer.ico'],
)
