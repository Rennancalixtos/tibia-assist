"""Dialogo modal de login/cadastro.

Bloqueia a janela principal enquanto nao houver uma sessao com assinatura
ativa - o unico jeito de fechar este dialogo com sucesso e logando numa
conta com assinatura valida ou cancelando (o que fecha o programa, ja que
nenhuma rotina pode rodar sem licenca).
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from core.license import LicenseManager


class LicenseDialog(tk.Toplevel):
    def __init__(self, master: tk.Tk, license_manager: LicenseManager, on_save):
        super().__init__(master)
        self.license_manager = license_manager
        self.on_save = on_save
        self.accepted = False

        self.title("Login - TibiaAssist")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)

        self.var_message = tk.StringVar(value=license_manager.message or "")
        ttk.Label(body, textvariable=self.var_message, foreground="#a33", wraplength=360, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Label(body, text="Email:").grid(row=1, column=0, sticky="w")
        self.var_email = tk.StringVar()
        entry_email = ttk.Entry(body, textvariable=self.var_email, width=34)
        entry_email.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        entry_email.focus_set()

        ttk.Label(body, text="Senha:").grid(row=3, column=0, sticky="w")
        self.var_password = tk.StringVar()
        entry_password = ttk.Entry(body, textvariable=self.var_password, width=34, show="*")
        entry_password.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(2, 10))

        actions = ttk.Frame(body)
        actions.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Button(actions, text="Entrar", command=self._login).pack(side="left")
        ttk.Button(actions, text="Cadastrar...", command=self._signup).pack(side="left", padx=8)
        ttk.Button(actions, text="Sair", command=self._cancel).pack(side="right")

        hint = ttk.Label(
            body,
            text="Ainda nao tem assinatura? Clique em Cadastrar para criar a conta e "
            "abrir o pagamento no navegador.",
            foreground="#666",
            wraplength=360,
            justify="left",
        )
        hint.grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.bind("<Return>", lambda _e: self._login())
        self.grab_set()
        self.wait_visibility()
        self.focus_force()

    def _credentials(self) -> tuple[str, str] | None:
        email = self.var_email.get().strip()
        password = self.var_password.get()
        if not email or not password:
            self.var_message.set("Informe email e senha.")
            return None
        return email, password

    def _login(self) -> None:
        creds = self._credentials()
        if creds is None:
            return
        self.var_message.set("Entrando...")
        self.update_idletasks()
        ok = self.license_manager.login(*creds)
        self.on_save()
        if ok:
            self.accepted = True
            self.destroy()
        else:
            self.var_message.set(self.license_manager.message or "Nao foi possivel entrar.")
            self._maybe_offer_checkout()

    def _signup(self) -> None:
        creds = self._credentials()
        if creds is None:
            return
        self.var_message.set("Cadastrando...")
        self.update_idletasks()
        self.license_manager.signup(*creds)
        self.on_save()
        url = self.license_manager.start_checkout()
        if url:
            webbrowser.open(url)
            self.var_message.set(
                "Conta criada! Finalize o pagamento na aba que abriu no navegador e "
                "depois clique em Entrar aqui."
            )
        else:
            self.var_message.set(self.license_manager.message or "Nao foi possivel iniciar o pagamento.")

    def _maybe_offer_checkout(self) -> None:
        """Se o login funcionou mas nao ha assinatura ativa, oferece o checkout."""
        if not self.license_manager.logged_in:
            return
        if self.license_manager.section.get("status") == "active":
            return
        url = self.license_manager.start_checkout()
        if url:
            webbrowser.open(url)
            self.var_message.set(
                "Login ok, mas sem assinatura ativa. Abrimos o pagamento no navegador - "
                "finalize e clique em Entrar novamente."
            )

    def _cancel(self) -> None:
        self.accepted = False
        self.destroy()


def ensure_license(master: tk.Tk, license_manager: LicenseManager, on_save) -> bool:
    """Mostra o dialogo se a sessao atual nao for valida. Devolve True se ok."""
    if license_manager.valid:
        return True
    dialog = LicenseDialog(master, license_manager, on_save)
    master.wait_window(dialog)
    return dialog.accepted
