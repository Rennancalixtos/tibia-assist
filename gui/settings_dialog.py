from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from core import profiles as profile_store
from gui.widgets import HotkeyButton

APP_NAME = "EasyF"


class SettingsDialog(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.app = app

        self.title("Configuracoes - EasyF")
        self.resizable(False, False)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.var_profile_new_name = tk.StringVar(value="")
        self.var_profile_select = tk.StringVar(value="")
        self.var_profile_status = tk.StringVar(value="")

        self._build()

        self.grab_set()
        self.focus_force()

    def _build(self) -> None:
        app = self.app

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

        prof = ttk.LabelFrame(self, text="Perfis", padding=6)
        prof.pack(fill="x", padx=8, pady=(0, 8))

        ttk.Label(prof, text="Nome do novo perfil:").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Entry(prof, textvariable=self.var_profile_new_name, width=24).grid(row=0, column=1, padx=4, sticky="w")
        ttk.Button(prof, text="Salvar como novo perfil", command=self._save_profile).grid(
            row=0, column=2, padx=8
        )

        ttk.Label(prof, text="Perfil salvo:").grid(row=1, column=0, sticky="w", padx=4, pady=(6, 0))
        self.profile_combo = ttk.Combobox(
            prof, textvariable=self.var_profile_select, width=22, state="readonly"
        )
        self.profile_combo.grid(row=1, column=1, padx=4, pady=(6, 0), sticky="w")
        ttk.Button(prof, text="Carregar", command=self._load_profile).grid(row=1, column=2, padx=8, pady=(6, 0))
        ttk.Button(prof, text="Excluir", command=self._delete_profile).grid(row=1, column=3, padx=4, pady=(6, 0))

        ttk.Label(prof, textvariable=self.var_profile_status, foreground="#666", wraplength=460).grid(
            row=2, column=0, columnspan=4, sticky="w", padx=4, pady=(4, 0)
        )
        ttk.Label(
            prof,
            text="Um perfil guarda todas as configuracoes das abas, hotkeys e modo background "
            "(a conta logada nao entra no perfil). Carregar um perfil pede pra reiniciar o app.",
            foreground="#666",
            wraplength=460,
            justify="left",
        ).grid(row=3, column=0, columnspan=4, sticky="w", padx=4, pady=(4, 0))

        self._refresh_profile_list()

        ttk.Button(self, text="Fechar", command=self.destroy).pack(anchor="e", padx=8, pady=(0, 8))

    def _refresh_profile_list(self) -> None:
        names = profile_store.list_profiles()
        self.profile_combo["values"] = names
        if self.var_profile_select.get() not in names:
            self.var_profile_select.set(names[0] if names else "")

    def _save_profile(self) -> None:
        name = self.var_profile_new_name.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "Digite um nome para o perfil.")
            return
        self.app.sync_config_from_ui()
        try:
            saved_name = profile_store.save_profile(name, self.app.config_store.data)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Falha ao salvar perfil: {exc}")
            return
        self.var_profile_status.set(f"Perfil {saved_name!r} salvo.")
        self.var_profile_new_name.set("")
        self.var_profile_select.set(saved_name)
        self._refresh_profile_list()

    def _load_profile(self) -> None:
        name = self.var_profile_select.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "Selecione um perfil para carregar.")
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Carregar o perfil {name!r} vai substituir as configuracoes atuais "
            "(exceto a conta logada). Sera preciso reiniciar o app depois. Continuar?",
        ):
            return
        try:
            data = profile_store.load_profile(name)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Falha ao carregar perfil: {exc}")
            return
        self.app.apply_profile_data(data)
        messagebox.showinfo(
            APP_NAME, f"Perfil {name!r} aplicado. Feche e abra o {APP_NAME} de novo para usar as novas configuracoes."
        )
        self.destroy()

    def _delete_profile(self) -> None:
        name = self.var_profile_select.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "Selecione um perfil para excluir.")
            return
        if not messagebox.askyesno(APP_NAME, f"Excluir o perfil {name!r}? Essa acao nao pode ser desfeita."):
            return
        profile_store.delete_profile(name)
        self.var_profile_status.set(f"Perfil {name!r} excluido.")
        self._refresh_profile_list()
