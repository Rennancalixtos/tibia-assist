from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from core import background_input, profiles as profile_store, region_selector
from core.config import RESOURCE_DIR, Config
from core.coordinator import AutomationCoordinator
from core.elevation import is_admin
from core.input_simulator import InputSimulator
from core.license import LicenseManager
from core.version import APP_VERSION
from functions.auto_food import AutoFoodWorker
from gui.license_dialog import ensure_license
from gui.log_overlay import LogOverlay
from gui.settings_dialog import SettingsDialog
from gui.widgets import LogPanel, ScrollableFrame

try:
    import keyboard
except Exception:
    keyboard = None


APP_NAME = "EasyF"

DISCLAIMER = (
    "Aviso: automação pode violar os termos de uso do servidor/jogo e "
    "resultar em banimento. O uso é responsabilidade do usuário."
)

TAB_LABELS = {
    "fishing": "AutoFishing",
    "runemaker": "RuneMaker",
    "target": "Target",
    "training": "Training",
    "auto_food": "AutoFood",
}

SECTION_ORDER = ("fishing", "runemaker", "target", "training")


class App(tk.Tk):
    def __init__(self, config_store: Config, license_manager: LicenseManager) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1040x560")
        self.minsize(900, 420)
        self._apply_app_icon()

        self.config_store = config_store
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.workers: dict[str, object] = {}
        self._hotkey_handles: list = []
        self.license = license_manager
        self.logout_requested = False
        self.coordinator = AutomationCoordinator()

        self._init_settings_vars()
        self._build()
        self._register_hotkeys()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._pump_events)

        self._schedule_license_check()
        self._schedule_heartbeat()

    def _apply_app_icon(self) -> None:
        icon_path = os.path.join(RESOURCE_DIR, "assets", "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except tk.TclError:
                pass

    def _init_settings_vars(self) -> None:
        hk = self.config_store.section("hotkeys")
        self.var_pause_key = tk.StringVar(value=hk.get("pause", "pause"))
        self.var_stop_key = tk.StringVar(value=hk.get("stop", "f7"))
        self.var_hotkeys_on = tk.BooleanVar(value=bool(hk.get("enabled", True)))
        self.var_hotkey_status = tk.StringVar(value="")

        bgcfg = self.config_store.section("background_mode")
        self.var_background_enabled = tk.BooleanVar(value=bool(bgcfg.get("enabled", False)))
        self.var_background_window = tk.StringVar(value=bgcfg.get("window_title", ""))
        self.var_background_status = tk.StringVar(value="")

        self.var_auto_food_enabled = tk.BooleanVar(value=False)
        self.var_auto_food_status = tk.StringVar(value="parado")

        dry_run_cfg = self.config_store.section("dry_run")
        self.var_dry_run_enabled = tk.BooleanVar(value=bool(dry_run_cfg.get("enabled", False)))

        log_cfg = self.config_store.section("log")
        self.var_log_overlay_enabled = tk.BooleanVar(value=bool(log_cfg.get("overlay_enabled", True)))
        self.var_log_panel_enabled = tk.BooleanVar(value=bool(log_cfg.get("panel_enabled", False)))

        self._settings_dialog: SettingsDialog | None = None

    def open_settings(self) -> None:
        dialog = self._settings_dialog
        if dialog is not None and dialog.winfo_exists():
            dialog.lift()
            dialog.focus_force()
            return
        self._settings_dialog = SettingsDialog(self)

    def _build(self) -> None:
        account_bar = ttk.Frame(self, padding=(8, 6, 8, 0))
        account_bar.pack(fill="x")
        self.var_account_info = tk.StringVar(value="")
        ttk.Label(
            account_bar, textvariable=self.var_account_info, foreground="#0a5", font=("Segoe UI", 9, "bold")
        ).pack(side="left", anchor="w")
        ttk.Button(account_bar, text="Sair da conta", command=self.logout).pack(side="right")
        ttk.Button(
            account_bar, text="⚙ Configurações...", command=self.open_settings
        ).pack(side="right", padx=(0, 8))
        self._tick_account_info()

        sections_scroll = ScrollableFrame(self)
        sections_scroll.pack(fill="both", expand=True, padx=8, pady=4)
        sections_body = sections_scroll.body

        GRID_COLUMNS = 2
        for col in range(GRID_COLUMNS):
            sections_body.columnconfigure(col, weight=1, uniform="section")

        from gui.fishing_window import FishingWindow
        from gui.runemaker_window import RuneMakerWindow
        from gui.target_window import TargetWindow
        from gui.training_window import TrainingWindow

        self.tabs = {
            "fishing": FishingWindow(sections_body, self),
            "runemaker": RuneMakerWindow(sections_body, self),
            "target": TargetWindow(sections_body, self),
            "training": TrainingWindow(sections_body, self),
        }
        for i, key in enumerate(SECTION_ORDER):
            row, col = (i // GRID_COLUMNS) * 2, i % GRID_COLUMNS
            ttk.Label(
                sections_body, text=TAB_LABELS[key], font=("Segoe UI", 12, "bold")
            ).grid(row=row, column=col, sticky="w", padx=4, pady=(12 if row else 4, 2))
            self.tabs[key].grid(row=row + 1, column=col, sticky="new", padx=4)

        toggles_bar = ttk.Frame(self, padding=(8, 0, 8, 4))
        toggles_bar.pack(fill="x")

        dry_run_row = ttk.Frame(toggles_bar)
        dry_run_row.pack(fill="x")
        ttk.Checkbutton(
            dry_run_row,
            text="Modo teste (dry-run: só loga, não clica/aperta tecla)",
            variable=self.var_dry_run_enabled,
            command=self._toggle_dry_run,
        ).pack(side="left")

        auto_food_row = ttk.Frame(toggles_bar)
        auto_food_row.pack(fill="x")
        ttk.Checkbutton(
            auto_food_row,
            text="Auto Food (comer automaticamente em segundo plano)",
            variable=self.var_auto_food_enabled,
            command=self._toggle_auto_food,
        ).pack(side="left")
        ttk.Label(auto_food_row, textvariable=self.var_auto_food_status, foreground="#666").pack(
            side="left", padx=(8, 0)
        )

        log_overlay_row = ttk.Frame(toggles_bar)
        log_overlay_row.pack(fill="x")
        ttk.Checkbutton(
            log_overlay_row,
            text="Logs na tela do jogo",
            variable=self.var_log_overlay_enabled,
            command=self._toggle_log_overlay,
        ).pack(side="left")

        log_panel_row = ttk.Frame(toggles_bar)
        log_panel_row.pack(fill="x")
        ttk.Checkbutton(
            log_panel_row,
            text="Mostrar logs na aplicação",
            variable=self.var_log_panel_enabled,
            command=self._toggle_log_panel,
        ).pack(side="left")

        self.log_overlay = LogOverlay(self)
        if self.var_log_overlay_enabled.get():
            self.log_overlay.show()

        self.shared_log = LogPanel(self, title="Log", height=10)

        self.footer = ttk.Frame(self, padding=(8, 4))
        footer = self.footer
        footer.pack(fill="x")

        if self.var_log_panel_enabled.get():
            self.shared_log.pack(fill="x", padx=8, pady=(0, 4), before=footer)
        ttk.Label(footer, text=DISCLAIMER, foreground="#a33", wraplength=720, justify="left").pack(
            anchor="w"
        )
        admin_ok = is_admin()
        ttk.Label(
            footer,
            text=f"Input: {InputSimulator.backend_name()}  |  "
            f"Administrador: {'Sim' if admin_ok else 'Não'}  |  "
            f"Escape de emergência: mova o mouse para o canto superior esquerdo da tela.",
            foreground="#666" if admin_ok else "#a33",
        ).pack(anchor="w", pady=(2, 0))
        if not admin_ok:
            ttk.Label(
                footer,
                text="⚠ Sem privilégio de administrador: clique/tecla sintético pode não ter "
                "efeito se o cliente do jogo rodar elevado. Feche e abra o programa de novo "
                "aceitando o pedido de elevação (UAC) do Windows.",
                foreground="#a33",
                wraplength=720,
                justify="left",
            ).pack(anchor="w", pady=(2, 0))

    def _register_hotkeys(self) -> None:
        self._clear_hotkeys()
        if not self.var_hotkeys_on.get():
            self.var_hotkey_status.set("Hotkeys globais desativadas - use os botões da interface.")
            return
        if keyboard is None:
            self.var_hotkey_status.set(
                "Módulo 'keyboard' indisponível (no Linux exige root). Use os botões da interface."
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
            self.var_hotkey_status.set(f"Não foi possível registrar as hotkeys: {exc}")

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

    def select_region(self, hint: str):
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

    def _resolve_background_hwnd(self):
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
            self.var_background_status.set("Seleção cancelada.")
            return
        x, y = point
        try:
            found = background_input.window_title_at_point(x, y)
        except Exception as exc:
            self.var_background_status.set(f"Falha ao identificar a janela: {exc}")
            return
        if not found:
            self.var_background_status.set("Não foi possível identificar uma janela nesse ponto.")
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
            self.var_background_status.set("Configuração de modo background salva.")

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
            messagebox.showerror(APP_NAME, "Janela do jogo não encontrada (título salvo não bate mais).")
            return

        point = self.select_point("Clique no ponto que será usado no teste (ex: um botão do jogo)")
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
                "Isso NÃO confirma que o jogo reagiu - confirme visualmente se o clique funcionou.",
            )

    def _toggle_dry_run(self) -> None:
        self.config_store.section("dry_run")["enabled"] = bool(self.var_dry_run_enabled.get())
        self.config_store.save()

    def _toggle_log_overlay(self) -> None:
        if self.var_log_overlay_enabled.get():
            self.log_overlay.show()
        else:
            self.log_overlay.hide()
        self.config_store.section("log")["overlay_enabled"] = bool(self.var_log_overlay_enabled.get())
        self.config_store.save()

    def _toggle_log_panel(self) -> None:
        if self.var_log_panel_enabled.get():
            self.shared_log.pack(fill="x", padx=8, pady=(0, 4), before=self.footer)
        else:
            self.shared_log.pack_forget()
        self.config_store.section("log")["panel_enabled"] = bool(self.var_log_panel_enabled.get())
        self.config_store.save()

    def _toggle_auto_food(self) -> None:
        if self.var_auto_food_enabled.get():
            self.start_worker("auto_food", AutoFoodWorker, {})
            worker = self.workers.get("auto_food")
            if worker is None or not worker.is_alive():
                self.var_auto_food_enabled.set(False)
        else:
            self.stop_worker("auto_food")

    def _save_license(self) -> None:
        self.config_store.save()

    def _update_account_info(self) -> None:
        email = self.license.email or "-"
        self.var_account_info.set(f"Logado como: {email}   |   Acesso restante: {self.license.expires_label}")

    def _tick_account_info(self) -> None:
        self._update_account_info()
        self.after(60_000, self._tick_account_info)

    def logout(self) -> None:
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

        def worker() -> None:
            self.license.refresh()
            self.after(0, lambda: self._on_license_check_result(was_valid))

        threading.Thread(target=worker, daemon=True).start()

    def _on_license_check_result(self, was_valid: bool) -> None:
        self.config_store.save()
        self._update_account_info()
        if was_valid and not self.license.valid:
            self.stop_all()
            messagebox.showwarning(
                APP_NAME,
                f"Licença inválida: {self.license.message}\nTodas as rotinas foram paradas.",
            )
        self._schedule_license_check()

    HEARTBEAT_INTERVAL_MS = 45_000

    def _schedule_heartbeat(self) -> None:
        self.after(self.HEARTBEAT_INTERVAL_MS, self._periodic_heartbeat)

    def _periodic_heartbeat(self) -> None:
        def worker() -> None:
            result = self.license.heartbeat()
            self.after(0, lambda: self._on_heartbeat_result(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_heartbeat_result(self, result: str) -> None:
        self.config_store.save()

        if result == "replaced":
            self._force_logout("Sua conta foi acessada em outro local. Esta sessão foi encerrada.")
            return
        if result == "auth_error" and not self.license.valid:
            self._force_logout(f"Sessão expirada: {self.license.message}\nFaça login novamente.")
            return
        self._schedule_heartbeat()

    def _force_logout(self, message: str) -> None:
        self.stop_all()
        self.license.logout()
        self.config_store.save()
        messagebox.showwarning(APP_NAME, message)
        self.logout_requested = True
        self.destroy()

    def build_worker_extras(self) -> dict:
        extras = {"_coordinator": self.coordinator}
        if self.config_store.get("background_mode.enabled", False):
            extras["_background_hwnd"] = self._resolve_background_hwnd()
        else:
            extras["_background_hwnd"] = None
        return extras

    def start_worker(self, key: str, worker_class, cfg: dict) -> None:
        if not ensure_license(self, self.license, self._save_license):
            messagebox.showwarning(APP_NAME, "É necessária uma licença ativa para iniciar.")
            return

        existing = self.workers.get(key)
        if existing is not None and existing.is_alive():
            messagebox.showinfo(APP_NAME, "Esta rotina já está em execução.")
            return
        cfg = dict(cfg)
        cfg.update(self.build_worker_extras())
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
        running = [w for w in self.workers.values() if w.is_alive()]
        if not running:
            return
        for worker in running:
            worker.toggle_pause()

    def log(self, message: str, source: str = "app") -> None:
        label = TAB_LABELS.get(source, source)
        line = f"[{label}] {message}"
        self.shared_log.append(line)
        self.log_overlay.append(line)

    def _pump_events(self) -> None:
        try:
            while True:
                source, kind, payload = self.events.get_nowait()

                if source == "app":
                    if payload == "pause":
                        self.toggle_pause_all()
                    elif payload == "stop":
                        self.stop_all()
                    continue

                if source == "auto_food":
                    if kind == "log":
                        self.log(payload, source="auto_food")
                    elif kind == "state":
                        self.var_auto_food_status.set(payload)
                        if payload == "stopped":
                            self.var_auto_food_enabled.set(False)
                    elif kind == "counter":
                        self.var_auto_food_status.set(f"rodando (#{payload})")
                    elif kind == "popup":
                        messagebox.showwarning(APP_NAME, payload)
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
                elif kind == "elapsed":
                    on_elapsed = getattr(tab, "on_elapsed", None)
                    if on_elapsed:
                        on_elapsed(payload)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._pump_events)

    def sync_config_from_ui(self) -> None:
        for tab in self.tabs.values():
            try:
                tab.save_config()
            except Exception:
                pass

        hk = self.config_store.section("hotkeys")
        hk["pause"] = self.var_pause_key.get().strip().lower() or "pause"
        hk["stop"] = self.var_stop_key.get().strip().lower() or "f7"
        hk["enabled"] = bool(self.var_hotkeys_on.get())

        bgcfg = self.config_store.section("background_mode")
        bgcfg["enabled"] = bool(self.var_background_enabled.get())
        bgcfg["window_title"] = self.var_background_window.get().strip()

        self.config_store.section("dry_run")["enabled"] = bool(self.var_dry_run_enabled.get())

    def apply_profile_data(self, data: dict) -> None:
        self.config_store.data = profile_store.merge_into_config(self.config_store.data, data)
        self.config_store.save()

    def on_close(self) -> None:
        self.stop_all()
        self._clear_hotkeys()
        self.sync_config_from_ui()
        self.config_store.save()
        self.destroy()
