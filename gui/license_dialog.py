"""Janela/dialogo de login+cadastro.

Duas situacoes usam o mesmo formulario (por isso o mixin `_LoginForm`):

- No boot, ANTES da janela principal existir: `run_startup_login` cria uma
  janela Tk standalone, sozinha na tela - so depois de logar com sucesso a
  janela principal e criada. Nao reaproveita a janela principal como "master"
  de um Toplevel aqui porque, no Windows, um Toplevel "transient" de uma
  janela raiz escondida (`withdraw`) por vezes nao e exibido pelo gerenciador
  de janelas - testado e confirmado neste projeto.
- Depois que a janela principal ja existe (licenca caiu no meio do uso, ou
  o usuario tenta iniciar uma rotina sem sessao ativa): `ensure_license`
  mostra um dialogo modal (Toplevel) por cima da janela principal, que fica
  visivel mas bloqueada por tras (grab_set).
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from core.license import LicenseManager

# Cooldown minimo (segundos) entre tentativas de login/cadastro - evita
# martelar a API do backend com cliques repetidos (engano do usuario ou
# tentativa de forca bruta de senha). Vale pros dois botoes juntos, ja que
# ambos batem no mesmo backend pequeno.
RATE_LIMIT_SECONDS = 3


class _LoginForm:
    """Mixin com o formulario de login/cadastro e os handlers dos botoes.

    A classe que usa este mixin precisa definir `self.license_manager`,
    `self.on_save` e `self.accepted` antes de chamar `_build_form()`, e ser
    ela mesma um widget Tk/Toplevel (usa `self` como container/janela).
    """

    def _build_form(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)

        self.var_message = tk.StringVar(value=self.license_manager.message or "")
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
        self.btn_login = ttk.Button(actions, text="Entrar", command=self._login)
        self.btn_login.pack(side="left")
        self.btn_signup = ttk.Button(actions, text="Cadastrar...", command=self._signup)
        self.btn_signup.pack(side="left", padx=8)
        ttk.Button(actions, text="Sair", command=self._cancel).pack(side="right")
        self._cooldown_job = None

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

    def _credentials(self) -> tuple[str, str] | None:
        email = self.var_email.get().strip()
        password = self.var_password.get()
        if not email or not password:
            self.var_message.set("Informe email e senha.")
            return None
        return email, password

    # ------------------------------------------------------------- rate limit
    def _start_cooldown(self) -> None:
        """Desativa Entrar/Cadastrar por `RATE_LIMIT_SECONDS` - chamado so
        depois que a chamada ao backend termina (nao antes), pra garantir o
        intervalo minimo de verdade entre uma tentativa e a proxima, em vez
        de descontar do cooldown o tempo que a propria chamada levou."""
        if self._cooldown_job is not None:
            self.after_cancel(self._cooldown_job)
        self.btn_login.configure(state="disabled")
        self.btn_signup.configure(state="disabled")
        self._cooldown_job = self.after(RATE_LIMIT_SECONDS * 1000, self._end_cooldown)

    def _end_cooldown(self) -> None:
        self._cooldown_job = None
        try:
            self.btn_login.configure(state="normal")
            self.btn_signup.configure(state="normal")
        except tk.TclError:
            pass  # janela ja fechada antes do cooldown acabar

    def _login(self) -> None:
        if self._cooldown_job is not None:
            return  # cooldown ativo - o "Enter" nao passa pelo estado disabled do botao
        creds = self._credentials()
        if creds is None:
            return
        self.btn_login.configure(state="disabled")
        self.btn_signup.configure(state="disabled")
        self.var_message.set("Entrando...")
        self.update_idletasks()
        ok = self.license_manager.login(*creds)
        self.on_save()
        if ok:
            self.accepted = True
            self.destroy()
            return
        self.var_message.set(self.license_manager.message or "Nao foi possivel entrar.")
        self._maybe_offer_checkout()
        self._start_cooldown()

    def _signup(self) -> None:
        if self._cooldown_job is not None:
            return  # cooldown ativo
        creds = self._credentials()
        if creds is None:
            return
        self.btn_login.configure(state="disabled")
        self.btn_signup.configure(state="disabled")
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
        self._start_cooldown()

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
        if self._cooldown_job is not None:
            self.after_cancel(self._cooldown_job)
            self._cooldown_job = None
        self.accepted = False
        self.destroy()


class LicenseDialog(tk.Toplevel, _LoginForm):
    """Dialogo modal usado quando a janela principal ja existe."""

    def __init__(self, master: tk.Tk, license_manager: LicenseManager, on_save):
        tk.Toplevel.__init__(self, master)
        self.license_manager = license_manager
        self.on_save = on_save
        self.accepted = False

        self.title("Login - EasyF")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build_form()

        self.grab_set()
        self.focus_force()


class LoginWindow(tk.Tk, _LoginForm):
    """Janela standalone usada ANTES da janela principal existir.

    Assim so uma janela aparece por vez: login primeiro, app depois - em vez
    de mostrar as duas juntas.
    """

    def __init__(self, license_manager: LicenseManager, on_save):
        tk.Tk.__init__(self)
        self.license_manager = license_manager
        self.on_save = on_save
        self.accepted = False

        self.title("Login - EasyF")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build_form()


def ensure_license(master: tk.Tk, license_manager: LicenseManager, on_save) -> bool:
    """Mostra o dialogo modal se a sessao atual nao for valida (janela
    principal ja existe). Devolve True se ok."""
    if license_manager.valid:
        return True
    dialog = LicenseDialog(master, license_manager, on_save)
    master.wait_window(dialog)
    return dialog.accepted


def run_startup_login(license_manager: LicenseManager, on_save) -> bool:
    """Mostra a janela de login standalone se a sessao atual nao for valida
    (usado ANTES de criar a janela principal). Devolve True se ok."""
    if license_manager.valid:
        return True
    window = LoginWindow(license_manager, on_save)
    window.mainloop()
    return window.accepted
