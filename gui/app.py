"""Janela principal do EasyF.

Responsabilidades:
  - montar as abas (AutoFishing / RuneMaker)
  - gerenciar o ciclo de vida das threads de trabalho
  - registrar as hotkeys globais de pausa/parada
  - drenar a fila de eventos das threads e atualizar a interface

Regra importante: widgets do tkinter so podem ser tocados pela thread da GUI.
Por isso as rotinas nunca chamam a interface diretamente - elas publicam
eventos numa `queue.Queue` que este modulo consome no loop do tkinter.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk

from core import background_input, region_selector
from core.config import Config
from core.coordinator import AutomationCoordinator
from core.input_simulator import InputSimulator
from core.license import LicenseManager
from core.version import APP_VERSION
from gui.license_dialog import ensure_license
from gui.widgets import HotkeyButton

try:
    import keyboard  # hotkeys globais (funciona com a janela do jogo em foco)
except Exception:  # pragma: no cover - pode faltar permissao no Linux
    keyboard = None


APP_NAME = "EasyF"

DISCLAIMER = (
    "Aviso: automacao pode violar os termos de uso do servidor/jogo e "
    "resultar em banimento. O uso e responsabilidade do usuario."
)


class App(tk.Tk):
    def __init__(self, config_store: Config, license_manager: LicenseManager) -> None:
        """`config_store` e `license_manager` vem prontos de main.py - o
        login (janela standalone, ver gui/license_dialog.py) roda ANTES
        desta janela ser criada, garantindo que so uma janela apareca por
        vez (login primeiro, app depois)."""
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("760x760")
        self.minsize(700, 640)

        self.config_store = config_store
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.workers: dict[str, object] = {}
        self._hotkey_handles: list = []
        self.license = license_manager
        self.logout_requested = False
        self.coordinator = AutomationCoordinator()

        self._build()
        self._register_hotkeys()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._pump_events)

        self._schedule_license_check()
        self._schedule_heartbeat()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        # Barra de conta (usuario logado + tempo restante de assinatura) ----
        account_bar = ttk.Frame(self, padding=(8, 6, 8, 0))
        account_bar.pack(fill="x")
        self.var_account_info = tk.StringVar(value="")
        ttk.Label(
            account_bar, textvariable=self.var_account_info, foreground="#0a5", font=("Segoe UI", 9, "bold")
        ).pack(side="left", anchor="w")
        ttk.Button(account_bar, text="Sair da conta", command=self.logout).pack(side="right")
        self._tick_account_info()

        # Barra de hotkeys globais -----------------------------------------
        top = ttk.LabelFrame(self, text="Hotkeys globais", padding=6)
        top.pack(fill="x", padx=8, pady=(8, 4))

        hk = self.config_store.section("hotkeys")
        self.var_pause_key = tk.StringVar(value=hk.get("pause", "pause"))
        self.var_stop_key = tk.StringVar(value=hk.get("stop", "f7"))
        self.var_hotkeys_on = tk.BooleanVar(value=bool(hk.get("enabled", True)))

        ttk.Label(top, text="Pausar/Retomar").grid(row=0, column=0, sticky="w", padx=4)
        HotkeyButton(top, self.var_pause_key, width=10).grid(row=0, column=1, padx=4)
        ttk.Label(top, text="Parar tudo").grid(row=0, column=2, sticky="w", padx=4)
        HotkeyButton(top, self.var_stop_key, width=10).grid(row=0, column=3, padx=4)
        ttk.Checkbutton(top, text="ativas", variable=self.var_hotkeys_on).grid(row=0, column=4, padx=8)
        ttk.Button(top, text="Aplicar", command=self._apply_hotkeys).grid(row=0, column=5, padx=4)
        ttk.Button(top, text="Parar tudo agora", command=self.stop_all).grid(row=0, column=6, padx=12)

        self.var_hotkey_status = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.var_hotkey_status, foreground="#666").grid(
            row=1, column=0, columnspan=7, sticky="w", padx=4, pady=(4, 0)
        )

        # Modo background (PostMessage, sem mover o mouse real) -------------
        bg = ttk.LabelFrame(self, text="Modo background", padding=6)
        bg.pack(fill="x", padx=8, pady=(0, 4))

        bgcfg = self.config_store.section("background_mode")
        self.var_background_enabled = tk.BooleanVar(value=bool(bgcfg.get("enabled", False)))
        self.var_background_window = tk.StringVar(value=bgcfg.get("window_title", ""))

        ttk.Checkbutton(
            bg, text="Nao usar o mouse real (PostMessage direto pra janela do jogo)",
            variable=self.var_background_enabled,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=4)
        ttk.Label(bg, text="Janela:").grid(row=1, column=0, sticky="w", padx=4, pady=(4, 0))
        ttk.Entry(bg, textvariable=self.var_background_window, width=32, state="readonly").grid(
            row=1, column=1, sticky="w", pady=(4, 0)
        )
        ttk.Button(bg, text="Selecionar janela do jogo...", command=self._pick_background_window).grid(
            row=1, column=2, padx=8, pady=(4, 0)
        )
        ttk.Button(bg, text="Testar clique em background...", command=self._test_background_click).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0)
        )
        ttk.Button(bg, text="Aplicar", command=self._apply_background_mode).grid(
            row=2, column=2, padx=8, pady=(4, 0)
        )

        self.var_background_status = tk.StringVar(value="")
        ttk.Label(bg, textvariable=self.var_background_status, foreground="#666", wraplength=700).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=4, pady=(4, 0)
        )

        # Abas ---------------------------------------------------------------
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=4)

        # Import tardio para evitar dependencia circular entre app e abas.
        from gui.fishing_window import FishingWindow
        from gui.runemaker_window import RuneMakerWindow

        self.tabs = {
            "fishing": FishingWindow(notebook, self),
            "runemaker": RuneMakerWindow(notebook, self),
        }
        notebook.add(self.tabs["fishing"], text="AutoFishing")
        notebook.add(self.tabs["runemaker"], text="RuneMaker")

        # Rodape -------------------------------------------------------------
        footer = ttk.Frame(self, padding=(8, 4))
        footer.pack(fill="x")
        ttk.Label(footer, text=DISCLAIMER, foreground="#a33", wraplength=720, justify="left").pack(
            anchor="w"
        )
        ttk.Label(
            footer,
            text=f"Input: {InputSimulator.backend_name()}  |  "
            f"Escape de emergencia: mova o mouse para o canto superior esquerdo da tela.",
            foreground="#666",
        ).pack(anchor="w", pady=(2, 0))

    # -------------------------------------------------------------- hotkeys
    def _register_hotkeys(self) -> None:
        self._clear_hotkeys()
        if not self.var_hotkeys_on.get():
            self.var_hotkey_status.set("Hotkeys globais desativadas - use os botoes da interface.")
            return
        if keyboard is None:
            self.var_hotkey_status.set(
                "Modulo 'keyboard' indisponivel (no Linux exige root). Use os botoes da interface."
            )
            return
        try:
            self._hotkey_handles.append(
                keyboard.add_hotkey(self.var_pause_key.get(), lambda: self.events.put(("app", "hotkey", "pause")))
            )
            self._hotkey_handles.append(
                keyboard.add_hotkey(self.var_stop_key.get(), lambda: self.events.put(("app", "hotkey", "stop")))
            )
            self.var_hotkey_status.set(
                f"Hotkeys ativas: {self.var_pause_key.get().upper()} pausa/retoma, "
                f"{self.var_stop_key.get().upper()} para tudo."
            )
        except Exception as exc:
            self.var_hotkey_status.set(f"Nao foi possivel registrar as hotkeys: {exc}")

    def _clear_hotkeys(self) -> None:
        if keyboard is None:
            self._hotkey_handles.clear()
            return
        for handle in self._hotkey_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._hotkey_handles.clear()

    def _apply_hotkeys(self) -> None:
        hk = self.config_store.section("hotkeys")
        hk["pause"] = self.var_pause_key.get().strip().lower() or "pause"
        hk["stop"] = self.var_stop_key.get().strip().lower() or "f7"
        hk["enabled"] = bool(self.var_hotkeys_on.get())
        self.config_store.save()
        self._register_hotkeys()

    # -------------------------------------------------------- selecao de tela
    def select_region(self, hint: str):
        """Esconde a janela, deixa o usuario desenhar um retangulo e restaura."""
        self.withdraw()
        self.update_idletasks()
        try:
            overlay_result = region_selector.select_region(self, hint)
        finally:
            self.deiconify()
            self.lift()
        return overlay_result

    def select_point(self, hint: str):
        self.withdraw()
        self.update_idletasks()
        try:
            point = region_selector.select_point(self, hint)
        finally:
            self.deiconify()
            self.lift()
        return point

    # --------------------------------------------------------- modo background
    def _resolve_background_hwnd(self):
        """Devolve o hwnd atual da janela do jogo (ou None), resolvido de
        novo pelo titulo salvo - o hwnd muda a cada vez que o jogo abre."""
        title = self.config_store.get("background_mode.window_title", "") or ""
        if not title:
            return None
        try:
            return background_input.find_window_by_title(title)
        except Exception:
            return None

    def _pick_background_window(self) -> None:
        self.var_background_status.set("Clique em qualquer ponto da janela do jogo...")
        self.update_idletasks()
        point = self.select_point("Clique na janela do jogo (para o modo background)")
        if point is None:
            self.var_background_status.set("Selecao cancelada.")
            return
        x, y = point
        try:
            found = background_input.window_title_at_point(x, y)
        except Exception as exc:
            self.var_background_status.set(f"Falha ao identificar a janela: {exc}")
            return
        if not found:
            self.var_background_status.set("Nao foi possivel identificar uma janela nesse ponto.")
            return
        _hwnd, title = found
        self.var_background_window.set(title)
        self.var_background_status.set(f"Janela selecionada: {title!r}. Clique em Aplicar para salvar.")

    def _apply_background_mode(self) -> None:
        bgcfg = self.config_store.section("background_mode")
        bgcfg["enabled"] = bool(self.var_background_enabled.get())
        bgcfg["window_title"] = self.var_background_window.get().strip()
        self.config_store.save()
        if bgcfg["enabled"] and not bgcfg["window_title"]:
            self.var_background_status.set(
                "Modo background ativado, mas nenhuma janela foi selecionada ainda."
            )
        else:
            self.var_background_status.set("Configuracao de modo background salva.")

    def _test_background_click(self) -> None:
        title = self.var_background_window.get().strip()
        if not title:
            messagebox.showwarning(APP_NAME, "Selecione a janela do jogo primeiro.")
            return
        hwnd = None
        try:
            hwnd = background_input.find_window_by_title(title)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Falha ao localizar a janela: {exc}")
            return
        if not hwnd:
            messagebox.showerror(APP_NAME, "Janela do jogo nao encontrada (titulo salvo nao bate mais).")
            return

        point = self.select_point("Clique no ponto que sera usado no teste (ex: um botao do jogo)")
        if point is None:
            return
        x, y = point

        messages: list[str] = []
        tester = InputSimulator(background_hwnd=hwnd, on_fallback=messages.append)
        try:
            tester.click(x, y)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Falha ao enviar o clique de teste: {exc}")
            return

        if messages:
            messagebox.showwarning(
                APP_NAME,
                "O modo background falhou nesse teste e caiu para o mouse real:\n" + "\n".join(messages),
            )
        else:
            messagebox.showinfo(
                APP_NAME,
                "Mensagem de clique enviada para a janela do jogo sem mover o mouse real.\n"
                "Isso NAO confirma que o jogo reagiu - confirme visualmente se o clique funcionou.",
            )

    # --------------------------------------------------------------- licenca
    def _save_license(self) -> None:
        self.config_store.save()

    def _update_account_info(self) -> None:
        email = self.license.email or "-"
        self.var_account_info.set(f"Logado como: {email}   |   Acesso restante: {self.license.expires_label}")

    def _tick_account_info(self) -> None:
        """Reagenda a si mesma a cada minuto so pra atualizar o texto (o
        tempo restante e calculado local, sem precisar checar o servidor)."""
        self._update_account_info()
        self.after(60_000, self._tick_account_info)

    def logout(self) -> None:
        """Limpa a sessao salva (access/refresh token, status) e fecha o
        programa - main.py detecta `logout_requested` e mostra o login de
        novo, em vez do app continuar aberto sem licenca valida."""
        if not messagebox.askyesno(
            APP_NAME, "Sair da conta? Vai precisar logar novamente pra usar o programa."
        ):
            return
        self.stop_all()
        self.license.logout()
        self.config_store.save()
        self.logout_requested = True
        self.destroy()

    def _schedule_license_check(self) -> None:
        interval_min = float(self.config_store.get("license.check_interval_minutes", 30) or 30)
        self.after(max(60_000, int(interval_min * 60_000)), self._periodic_license_check)

    def _periodic_license_check(self) -> None:
        was_valid = self.license.valid
        self.license.refresh()
        self.config_store.save()
        self._update_account_info()
        if was_valid and not self.license.valid:
            self.stop_all()
            messagebox.showwarning(
                APP_NAME,
                f"Licenca invalida: {self.license.message}\nTodas as rotinas foram paradas.",
            )
        self._schedule_license_check()

    # ------------------------------------------------------- sessao unica (heartbeat)
    HEARTBEAT_INTERVAL_MS = 45_000

    def _schedule_heartbeat(self) -> None:
        self.after(self.HEARTBEAT_INTERVAL_MS, self._periodic_heartbeat)

    def _periodic_heartbeat(self) -> None:
        result = self.license.heartbeat()
        self.config_store.save()

        if result == "replaced":
            self._force_logout("Sua conta foi acessada em outro local. Esta sessao foi encerrada.")
            return
        if result == "auth_error" and not self.license.valid:
            # refresh() ja tentou renovar e falhou de verdade (nao e so falta
            # de rede) - sessao morta por outro motivo que nao "substituida".
            self._force_logout(f"Sessao expirada: {self.license.message}\nFaca login novamente.")
            return
        # "ok", "network_error" ou "auth_error" com sessao ainda valida em
        # cache (tolerancia offline) - nao e evidencia de nada, so tenta de
        # novo no proximo ciclo, do mesmo jeito que a validade de assinatura
        # ja tolera queda de rede passageira.
        self._schedule_heartbeat()

    def _force_logout(self, message: str) -> None:
        """Encerra a sessao pra sempre a partir de um evento assincrono
        (sessao substituida / expirada) - mesmo mecanismo do botao "Sair da
        conta", so sem a confirmacao (o usuario nao pediu isso agora)."""
        self.stop_all()
        self.license.logout()
        self.config_store.save()
        messagebox.showwarning(APP_NAME, message)
        self.logout_requested = True
        self.destroy()

    # ---------------------------------------------------------------- workers
    def start_worker(self, key: str, worker_class, cfg: dict) -> None:
        if not ensure_license(self, self.license, self._save_license):
            messagebox.showwarning(APP_NAME, "E necessaria uma licenca ativa para iniciar.")
            return

        existing = self.workers.get(key)
        if existing is not None and existing.is_alive():
            messagebox.showinfo(APP_NAME, "Esta rotina ja esta em execucao.")
            return
        cfg = dict(cfg)
        cfg["_coordinator"] = self.coordinator
        if self.config_store.get("background_mode.enabled", False):
            cfg["_background_hwnd"] = self._resolve_background_hwnd()
        else:
            cfg["_background_hwnd"] = None
        worker = worker_class(cfg, self.events)
        self.workers[key] = worker
        worker.start()

    def stop_worker(self, key: str) -> None:
        worker = self.workers.get(key)
        if worker is not None and worker.is_alive():
            worker.stop()

    def toggle_pause(self, key: str) -> None:
        worker = self.workers.get(key)
        if worker is not None and worker.is_alive():
            worker.toggle_pause()

    def stop_all(self) -> None:
        for key in list(self.workers):
            self.stop_worker(key)

    def toggle_pause_all(self) -> None:
        """Pausa/retoma todas as rotinas em execucao (hotkey global)."""
        running = [w for w in self.workers.values() if w.is_alive()]
        if not running:
            return
        for worker in running:
            worker.toggle_pause()

    # ----------------------------------------------------------------- eventos
    def _pump_events(self) -> None:
        """Consome a fila de eventos das threads e atualiza a interface."""
        try:
            while True:
                source, kind, payload = self.events.get_nowait()

                if source == "app":
                    if payload == "pause":
                        self.toggle_pause_all()
                    elif payload == "stop":
                        self.stop_all()
                    continue

                tab = self.tabs.get(source)
                if tab is None:
                    continue
                if kind == "log":
                    tab.log(payload)
                elif kind == "state":
                    tab.on_state(payload)
                elif kind == "counter":
                    tab.on_counter(payload)
                elif kind == "popup":
                    messagebox.showwarning(APP_NAME, payload)
                elif kind == "config_update":
                    apply = getattr(tab, "apply_config_update", None)
                    if apply:
                        apply(payload)
                elif kind == "mana_reading":
                    on_reading = getattr(tab, "on_mana_reading", None)
                    if on_reading:
                        on_reading(payload)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._pump_events)

    # ---------------------------------------------------------------- fechar
    def on_close(self) -> None:
        self.stop_all()
        self._clear_hotkeys()
        for tab in self.tabs.values():
            try:
                tab.save_config()
            except Exception:
                pass
        self.config_store.save()
        self.destroy()
