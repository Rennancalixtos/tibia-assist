"""Dialogo de configuracoes (hotkeys globais + modo background).

Essas duas secoes ficavam sempre visiveis no topo da janela principal, mas
sao configuradas uma vez e raramente mexidas de novo - por isso foram
movidas pra um dialogo separado, aberto sob demanda pelo botao
"Configuracoes..." da barra de conta (ver `App.open_settings` em
gui/app.py).

Toda a logica (aplicar hotkeys, selecionar janela de background, testar
clique, etc.) continua em `App` - este modulo so monta os widgets e os liga
as variaveis/metodos que ja existem em `app`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.widgets import HotkeyButton


class SettingsDialog(tk.Toplevel):
    """Dialogo modal com as secoes 'Hotkeys globais' e 'Modo background'.

    Fechar o dialogo (botao Fechar, X da janela ou Esc) so esconde/destroi o
    Toplevel - nao tem efeito colateral nenhum, ja que "Aplicar" em cada
    secao ja salva a config na hora.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self.app = app

        self.title("Configuracoes - EasyF")
        self.resizable(False, False)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._build()

        self.grab_set()
        self.focus_force()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        app = self.app

        # Hotkeys globais -----------------------------------------------
        top = ttk.LabelFrame(self, text="Hotkeys globais", padding=6)
        top.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(top, text="Pausar/Retomar").grid(row=0, column=0, sticky="w", padx=4)
        HotkeyButton(top, app.var_pause_key, width=10).grid(row=0, column=1, padx=4)
        ttk.Label(top, text="Parar tudo").grid(row=0, column=2, sticky="w", padx=4)
        HotkeyButton(top, app.var_stop_key, width=10).grid(row=0, column=3, padx=4)
        ttk.Checkbutton(top, text="ativas", variable=app.var_hotkeys_on).grid(row=0, column=4, padx=8)
        ttk.Button(top, text="Aplicar", command=app._apply_hotkeys).grid(row=0, column=5, padx=4)
        ttk.Button(top, text="Parar tudo agora", command=app.stop_all).grid(row=0, column=6, padx=12)

        ttk.Label(top, textvariable=app.var_hotkey_status, foreground="#666").grid(
            row=1, column=0, columnspan=7, sticky="w", padx=4, pady=(4, 0)
        )

        # Modo background (PostMessage, sem mover o mouse real) ----------
        bg = ttk.LabelFrame(self, text="Modo background", padding=6)
        bg.pack(fill="x", padx=8, pady=(0, 8))

        ttk.Checkbutton(
            bg, text="Nao usar o mouse real (PostMessage direto pra janela do jogo)",
            variable=app.var_background_enabled,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=4)
        ttk.Label(bg, text="Janela:").grid(row=1, column=0, sticky="w", padx=4, pady=(4, 0))
        ttk.Entry(bg, textvariable=app.var_background_window, width=32, state="readonly").grid(
            row=1, column=1, sticky="w", pady=(4, 0)
        )
        ttk.Button(bg, text="Selecionar janela do jogo...", command=app._pick_background_window).grid(
            row=1, column=2, padx=8, pady=(4, 0)
        )
        ttk.Button(bg, text="Testar clique em background...", command=app._test_background_click).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0)
        )
        ttk.Button(bg, text="Aplicar", command=app._apply_background_mode).grid(
            row=2, column=2, padx=8, pady=(4, 0)
        )

        ttk.Label(bg, textvariable=app.var_background_status, foreground="#666", wraplength=460).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=4, pady=(4, 0)
        )

        # Fechar -----------------------------------------------------------
        ttk.Button(self, text="Fechar", command=self.destroy).pack(anchor="e", padx=8, pady=(0, 8))
