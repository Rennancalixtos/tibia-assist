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

from core import region_selector
from core.config import Config
from core.input_simulator import InputSimulator
from core.license import LicenseManager
from gui.license_dialog import ensure_license

try:
    import keyboard  # hotkeys globais (funciona com a janela do jogo em foco)
except Exception:  # pragma: no cover - pode faltar permissao no Linux
    keyboard = None


APP_NAME = "EasyF"
APP_VERSION = "1.0.0"

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

        self._build()
        self._register_hotkeys()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._pump_events)

        self._schedule_license_check()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        # Barra de hotkeys globais -----------------------------------------
        top = ttk.LabelFrame(self, text="Hotkeys globais", padding=6)
        top.pack(fill="x", padx=8, pady=(8, 4))

        hk = self.config_store.section("hotkeys")
        self.var_pause_key = tk.StringVar(value=hk.get("pause", "f6"))
        self.var_stop_key = tk.StringVar(value=hk.get("stop", "f7"))
        self.var_hotkeys_on = tk.BooleanVar(value=bool(hk.get("enabled", True)))

        ttk.Label(top, text="Pausar/Retomar").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Entry(top, textvariable=self.var_pause_key, width=8).grid(row=0, column=1, padx=4)
        ttk.Label(top, text="Parar tudo").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Entry(top, textvariable=self.var_stop_key, width=8).grid(row=0, column=3, padx=4)
        ttk.Checkbutton(top, text="ativas", variable=self.var_hotkeys_on).grid(row=0, column=4, padx=8)
        ttk.Button(top, text="Aplicar", command=self._apply_hotkeys).grid(row=0, column=5, padx=4)
        ttk.Button(top, text="Parar tudo agora", command=self.stop_all).grid(row=0, column=6, padx=12)

        self.var_hotkey_status = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.var_hotkey_status, foreground="#666").grid(
            row=1, column=0, columnspan=7, sticky="w", padx=4, pady=(4, 0)
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
        hk["pause"] = self.var_pause_key.get().strip().lower() or "f6"
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

    # --------------------------------------------------------------- licenca
    def _save_license(self) -> None:
        self.config_store.save()

    def _schedule_license_check(self) -> None:
        interval_min = float(self.config_store.get("license.check_interval_minutes", 30) or 30)
        self.after(max(60_000, int(interval_min * 60_000)), self._periodic_license_check)

    def _periodic_license_check(self) -> None:
        was_valid = self.license.valid
        self.license.refresh()
        self.config_store.save()
        if was_valid and not self.license.valid:
            self.stop_all()
            messagebox.showwarning(
                APP_NAME,
                f"Licenca invalida: {self.license.message}\nTodas as rotinas foram paradas.",
            )
        self._schedule_license_check()

    # ---------------------------------------------------------------- workers
    def start_worker(self, key: str, worker_class, cfg: dict) -> None:
        if not ensure_license(self, self.license, self._save_license):
            messagebox.showwarning(APP_NAME, "E necessaria uma licenca ativa para iniciar.")
            return

        existing = self.workers.get(key)
        if existing is not None and existing.is_alive():
            messagebox.showinfo(APP_NAME, "Esta rotina ja esta em execucao.")
            return
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
