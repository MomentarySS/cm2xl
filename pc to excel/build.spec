# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

import customtkinter

ROOT = Path(SPECPATH)
CTK_DIR = Path(customtkinter.__file__).resolve().parent

datas = [
    (str(ROOT / "data" / "settings.json"), "data"),
    (str(ROOT / "scripts" / "export_current.bas.template"), "scripts"),
    (str(ROOT / "scripts" / "export_current.bas"), "scripts"),
    (str(CTK_DIR / "assets"), "customtkinter/assets"),
]

hiddenimports = [
    "win32com",
    "win32com.client",
    "pythoncom",
    "pywintypes",
    "customtkinter",
    "openpyxl",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="PCDMIS按需Excel报告",
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
    icon=None,
)
