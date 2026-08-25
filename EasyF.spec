# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o EasyF.

Build normal (sem console):
    pyinstaller EasyF.spec --noconfirm

Build de diagnostico (com janela de console mostrando tracebacks):
    set EASYF_CONSOLE=1 && pyinstaller EasyF.spec --noconfirm
"""

import os

# Console ligado por variavel de ambiente - util no primeiro teste, quando
# qualquer erro de importacao ou de tela precisa aparecer em algum lugar.
CONSOLE = os.environ.get("EASYF_CONSOLE", "") not in ("", "0")

# Icone opcional: se voce colocar assets/icon.ico, ele e usado.
icon_path = os.path.join("assets", "icon.ico")
icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    # Os templates calibrados ficam em assets/. Em --onefile o conteudo e
    # extraido para uma pasta temporaria, mas o programa grava e le os
    # templates ao lado do executavel (ver nota no README).
    datas=[("assets", "assets")],
    hiddenimports=[
        "mss.windows",   # o mss escolhe o backend em tempo de execucao
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
    a.binaries,
    a.datas,
    [],
    name="EasyF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                   
    runtime_tmpdir=None,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version="version_info.txt",  
    # Muitos clientes (ex: OTClient/derivados) rodam elevados. O Windows usa
    # UIPI para bloquear silenciosamente cliques/teclas sinteticos vindos de
    # um processo de privilegio mais baixo chegando numa janela elevada -
    # o cursor se move (estado global do SO), mas o clique nao tem efeito.
    # uac_admin embute um manifest pedindo elevacao ao abrir o .exe, para o
    # EasyF sempre rodar no mesmo nivel do cliente do jogo.
    uac_admin=True,
)
