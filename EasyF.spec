# -*- mode: python ; coding: utf-8 -*-
import os

CONSOLE = os.environ.get("EASYF_CONSOLE", "") not in ("", "0")

icon_path = os.path.join("assets", "icon.ico")
icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=[
        "mss.windows",
        "pydirectinput",
        "pytesseract",
        "keyboard",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "PyQt5", "PySide2", "scipy", "pandas"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EasyF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version="version_info.txt",
    uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EasyF",
)
