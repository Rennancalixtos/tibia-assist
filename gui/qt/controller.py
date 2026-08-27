from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QMessageBox

from core import background_input, profiles as profile_store
from core.config import Config
from core.coordinator import AutomationCoordinator
from core.elevation import is_admin
from core.input_simulator import InputSimulator
from core.license import LicenseManager
from functions.auto_food import AutoFoodWorker
from gui.qt import region_selector

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

HEARTBEAT_INTERVAL_MS = 45_000


class Controller(QObject):
    module_event = Signal(str, str, object)
    log_line = Signal(str)
    popup_warning = Signal(str, str)
    auto_food_state_changed = Signal(str)
    auto_food_counter_changed = Signal(str)
    account_info_changed = Signal(str, str)
    forced_logout = Signal(str)
    _license_check_done = Signal(bool)
    _heartbeat_done = Signal(str)

    def __init__(self, config_store: Config, license_manager: LicenseManager):
        super().__init__()
        self.config_store = config_store
        self.license = license_manager
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.workers: dict[str, object] = {}
        self.coordinator = AutomationCoordinator()
        self.logout_requested = False
        self.main_window = None
        self.module_views: dict[str, object] = {}

        hk = self.config_store.section("hotkeys")
        self.pause_key = hk.get("pause", "pause")
        self.stop_key = hk.get("stop", "f7")
        self.hotkeys_enabled = bool(hk.get("enabled", True))
        self.hotkey_status = ""

        bgcfg = self.config_store.section("background_mode")
        self.background_enabled = bool(bgcfg.get("enabled", False))
        self.background_window_title = bgcfg.get("window_title", "")

        self.dry_run_enabled = bool(self.config_store.section("dry_run").get("enabled", False))

        log_cfg = self.config_store.section("log")
        self.log_overlay_enabled = bool(log_cfg.get("overlay_enabled", True))
        self.log_panel_enabled = bool(log_cfg.get("panel_enabled", False))

        self._hotkey_handles: list = []

        self._bridge = None
        self._start_event_bridge()

        self._license_check_done.connect(self._on_license_check_result)
        self._heartbeat_done.connect(self._on_heartbeat_result)

        self._account_timer = QTimer(self)
        self._account_timer.timeout.connect(self._tick_account_info)
        self._account_timer.start(60_000)
        QTimer.singleShot(0, self._tick_account_info)

        self._schedule_license_check()
        QTimer.singleShot(HEARTBEAT_INTERVAL_MS, self._periodic_heartbeat)

        self.register_hotkeys()

    def _start_event_bridge(self) -> None:
        from gui.qt.event_bridge import EventBridge

        self._bridge = EventBridge(self.events)
        self._bridge.event_received.connect(self._on_event)
        self._bridge.start()

    def attach_window(self, window) -> None:
        self.main_window = window

    def register_module_view(self, key: str, view) -> None:
        self.module_views[key] = view

    @staticmethod
    def input_backend_name() -> str:
        return InputSimulator.backend_name()

    @staticmethod
    def admin_ok() -> bool:
        return is_admin()

    def _on_event(self, source: str, kind: str, payload) -> None:
        if source == "app":
            if payload == "pause":
                self.toggle_pause_all()
            elif payload == "stop":
                self.stop_all()
            return

        if source == "auto_food":
            if kind == "log":
                self._emit_log(payload, source)
            elif kind == "state":
                self.auto_food_state_changed.emit(payload)
            elif kind == "counter":
                self.auto_food_counter_changed.emit(f"rodando (#{payload})")
            elif kind == "popup":
                self.popup_warning.emit(APP_NAME, payload)
            return

        if kind == "log":
            self._emit_log(payload, source)
            return
        if kind == "popup":
            self.popup_warning.emit(APP_NAME, payload)
            return

        self.module_event.emit(source, kind, payload)

    def _emit_log(self, message: str, source: str) -> None:
        label = TAB_LABELS.get(source, source)
        self.log_line.emit(f"[{label}] {message}")

    def log(self, message: str, source: str = "app") -> None:
        self._emit_log(message, source)

    def select_region(self, hint: str):
        return region_selector.select_region(hint, window=self.main_window)

    def select_point(self, hint: str):
        return region_selector.select_point(hint, window=self.main_window)

    def _resolve_background_hwnd(self):
        title = self.config_store.get("background_mode.window_title", "") or ""
        if not title:
            return None
        try:
            return background_input.find_window_by_title(title)
        except Exception:
            return None

    def pick_background_window(self, on_status) -> str | None:
        on_status("Clique em qualquer ponto da janela do jogo...")
        point = self.select_point("Clique na janela do jogo (para o modo background)")
        if point is None:
            on_status("Seleção cancelada.")
            return None
        x, y = point
        try:
            found = background_input.window_title_at_point(x, y)
        except Exception as exc:
            on_status(f"Falha ao identificar a janela: {exc}")
            return None
        if not found:
            on_status("Não foi possível identificar uma janela nesse ponto.")
            return None
        _hwnd, title = found
        on_status(f"Janela selecionada: {title!r}. Clique em Aplicar para salvar.")
        return title

    def apply_background_mode(self, enabled: bool, window_title: str) -> str:
        bgcfg = self.config_store.section("background_mode")
        bgcfg["enabled"] = bool(enabled)
        bgcfg["window_title"] = (window_title or "").strip()
        self.config_store.save()
        self.background_enabled = bgcfg["enabled"]
        self.background_window_title = bgcfg["window_title"]
        if bgcfg["enabled"] and not bgcfg["window_title"]:
            return "Modo background ativado, mas nenhuma janela foi selecionada ainda."
        return "Configuração de modo background salva."

    def test_background_click(self, window_title: str) -> None:
        title = (window_title or "").strip()
        if not title:
            QMessageBox.warning(self.main_window, APP_NAME, "Selecione a janela do jogo primeiro.")
            return
        try:
            hwnd = background_input.find_window_by_title(title)
        except Exception as exc:
            QMessageBox.critical(self.main_window, APP_NAME, f"Falha ao localizar a janela: {exc}")
            return
        if not hwnd:
            QMessageBox.critical(
                self.main_window, APP_NAME, "Janela do jogo não encontrada (título salvo não bate mais)."
            )
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
            QMessageBox.critical(self.main_window, APP_NAME, f"Falha ao enviar o clique de teste: {exc}")
            return

        if messages:
            QMessageBox.warning(
                self.main_window,
                APP_NAME,
                "O modo background falhou nesse teste e caiu para o mouse real:\n" + "\n".join(messages),
            )
        else:
            QMessageBox.information(
                self.main_window,
                APP_NAME,
                "Mensagem de clique enviada para a janela do jogo sem mover o mouse real.\n"
                "Isso NÃO confirma que o jogo reagiu - confirme visualmente se o clique funcionou.",
            )

    def register_hotkeys(self) -> None:
        self._clear_hotkeys()
        if not self.hotkeys_enabled:
            self.hotkey_status = "Hotkeys globais desativadas - use os botões da interface."
            return
        if keyboard is None:
            self.hotkey_status = (
                "Módulo 'keyboard' indisponível (no Linux exige root). Use os botões da interface."
            )
            return
        try:
            self._hotkey_handles.append(
                keyboard.add_hotkey(self.pause_key, lambda: self.events.put(("app", "hotkey", "pause")))
            )
            self._hotkey_handles.append(
                keyboard.add_hotkey(self.stop_key, lambda: self.events.put(("app", "hotkey", "stop")))
            )
            self.hotkey_status = (
                f"Hotkeys ativas: {self.pause_key.upper()} pausa/retoma, {self.stop_key.upper()} para tudo."
            )
        except Exception as exc:
            self.hotkey_status = f"Não foi possível registrar as hotkeys: {exc}"

    def _clear_hotkeys(self) -> None:
        if keyboard is not None:
            for handle in self._hotkey_handles:
                try:
                    keyboard.remove_hotkey(handle)
                except Exception:
                    pass
        self._hotkey_handles.clear()

    def apply_hotkeys(self, pause_key: str, stop_key: str, enabled: bool) -> str:
        hk = self.config_store.section("hotkeys")
        self.pause_key = (pause_key or "").strip().lower() or "pause"
        self.stop_key = (stop_key or "").strip().lower() or "f7"
        self.hotkeys_enabled = bool(enabled)
        hk["pause"] = self.pause_key
        hk["stop"] = self.stop_key
        hk["enabled"] = self.hotkeys_enabled
        self.config_store.save()
        self.register_hotkeys()
        return self.hotkey_status

    def toggle_dry_run(self, enabled: bool) -> None:
        self.dry_run_enabled = bool(enabled)
        self.config_store.section("dry_run")["enabled"] = self.dry_run_enabled
        self.config_store.save()

    def toggle_log_overlay(self, enabled: bool) -> None:
        self.log_overlay_enabled = bool(enabled)
        self.config_store.section("log")["overlay_enabled"] = self.log_overlay_enabled
        self.config_store.save()

    def toggle_log_panel(self, enabled: bool) -> None:
        self.log_panel_enabled = bool(enabled)
        self.config_store.section("log")["panel_enabled"] = self.log_panel_enabled
        self.config_store.save()

    def toggle_auto_food(self, enabled: bool) -> bool:
        if enabled:
            self.start_worker("auto_food", AutoFoodWorker, {})
            worker = self.workers.get("auto_food")
            return bool(worker is not None and worker.is_alive())
        self.stop_worker("auto_food")
        return False

    def build_worker_extras(self) -> dict:
        extras = {"_coordinator": self.coordinator}
        if self.config_store.get("background_mode.enabled", False):
            extras["_background_hwnd"] = self._resolve_background_hwnd()
        else:
            extras["_background_hwnd"] = None
        return extras

    def ensure_license(self) -> bool:
        from gui.qt.dialogs.login_dialog import prompt_login

        return prompt_login(self.license, self.config_store.save, parent=self.main_window)

    def start_worker(self, key: str, worker_class, cfg: dict) -> None:
        if not self.ensure_license():
            QMessageBox.warning(self.main_window, APP_NAME, "É necessária uma licença ativa para iniciar.")
            return
        existing = self.workers.get(key)
        if existing is not None and existing.is_alive():
            QMessageBox.information(self.main_window, APP_NAME, "Esta rotina já está em execução.")
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
        for worker in running:
            worker.toggle_pause()

    def sync_config_from_ui(self) -> None:
        for view in self.module_views.values():
            try:
                view.save_config()
            except Exception:
                pass

    def apply_profile_data(self, data: dict) -> None:
        self.config_store.data = profile_store.merge_into_config(self.config_store.data, data)
        self.config_store.save()

    def logout(self) -> bool:
        if (
            QMessageBox.question(
                self.main_window,
                APP_NAME,
                "Sair da conta? Vai precisar logar novamente pra usar o programa.",
            )
            != QMessageBox.Yes
        ):
            return False
        self.stop_all()
        self.license.logout()
        self.config_store.save()
        self.logout_requested = True
        return True

    def _tick_account_info(self) -> None:
        email = self.license.email or "-"
        self.account_info_changed.emit(email, self.license.expires_label)

    def _schedule_license_check(self) -> None:
        interval_min = float(self.config_store.get("license.check_interval_minutes", 30) or 30)
        QTimer.singleShot(max(60_000, int(interval_min * 60_000)), self._periodic_license_check)

    def _periodic_license_check(self) -> None:
        was_valid = self.license.valid

        def worker() -> None:
            self.license.refresh()
            self._license_check_done.emit(was_valid)

        threading.Thread(target=worker, daemon=True).start()

    def _on_license_check_result(self, was_valid: bool) -> None:
        self.config_store.save()
        self._tick_account_info()
        if was_valid and not self.license.valid:
            self.stop_all()
            self.popup_warning.emit(
                APP_NAME, f"Licença inválida: {self.license.message}\nTodas as rotinas foram paradas."
            )
        self._schedule_license_check()

    def _periodic_heartbeat(self) -> None:
        def worker() -> None:
            result = self.license.heartbeat()
            self._heartbeat_done.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_heartbeat_result(self, result: str) -> None:
        self.config_store.save()
        if result == "replaced":
            self._force_logout("Sua conta foi acessada em outro local. Esta sessão foi encerrada.")
            return
        if result == "auth_error" and not self.license.valid:
            self._force_logout(f"Sessão expirada: {self.license.message}\nFaça login novamente.")
            return
        QTimer.singleShot(HEARTBEAT_INTERVAL_MS, self._periodic_heartbeat)

    def _force_logout(self, message: str) -> None:
        self.stop_all()
        self.license.logout()
        self.config_store.save()
        self.logout_requested = True
        self.forced_logout.emit(message)

    def shutdown(self) -> None:
        self.stop_all()
        self._clear_hotkeys()
        self.sync_config_from_ui()
        self.config_store.save()
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge.wait(1000)
