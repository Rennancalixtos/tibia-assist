from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.config import RESOURCE_DIR
from core.screen_capture import is_valid_region
from functions.cavebot import CavebotWorker
from gui.qt.components.action_button import ActionButton
from gui.qt.components.info_tooltip import InfoIcon
from gui.qt.components.module_card import ModuleCard
from gui.qt.overlays.mana_overlay import ManaOverlay
from gui.widgets import parse_float, parse_int, region_text

ICONS_DIR = os.path.join(RESOURCE_DIR, "img", "map", "icons")
MAX_ICON_INDEX = 15


def _list_icon_files() -> list[str]:
    if not os.path.isdir(ICONS_DIR):
        return []
    files = []
    for name in os.listdir(ICONS_DIR):
        if not name.lower().endswith(".png"):
            continue
        stem = os.path.splitext(name)[0]
        if not stem.isdigit() or int(stem) > MAX_ICON_INDEX:
            continue
        files.append(name)

    files.sort(key=lambda name: int(os.path.splitext(name)[0]))
    return files


def _waypoint_label(index: int, waypoint: dict, default_confidence: float) -> str:
    icon_nome = os.path.basename(waypoint.get("icon") or "?")
    wait_s = waypoint.get("wait_s", 0.0)
    confidence = waypoint.get("confidence") or default_confidence
    return f"{index + 1}. {icon_nome} - espera: {wait_s:.0f}s - confiança: {confidence:.2f}"


class _ConfigDialog(QDialog):
    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


class _AddWaypointDialog(QDialog):
    def __init__(self, default_confidence: float, initial: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar ponto" if initial else "Adicionar ponto")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_icon = QComboBox()
        self.combo_icon.addItems(_list_icon_files())
        if initial:
            icon_nome = os.path.basename(initial.get("icon") or "")
            index = self.combo_icon.findText(icon_nome)
            if index >= 0:
                self.combo_icon.setCurrentIndex(index)
        form.addRow("Ícone do mini mapa", self.combo_icon)

        self.input_wait = QLineEdit(str(initial.get("wait_s", 5.0)) if initial else "5")
        self.input_wait.setFixedWidth(80)
        form.addRow("Espera após o clique (s)", self.input_wait)

        initial_confidence = initial.get("confidence") if initial else None
        confidence_row = QHBoxLayout()
        self.input_confidence = QLineEdit(str(initial_confidence or default_confidence))
        self.input_confidence.setFixedWidth(80)
        confidence_row.addWidget(self.input_confidence)
        confidence_row.addWidget(
            InfoIcon(
                "Menor = acha mais fácil, mais risco de confundir. Maior = mais seguro, mas pode não "
                "achar o marcador.\n\n"
                "Comece em 0.60-0.65 e só suba se esse ponto especificamente estiver "
                "clicando errado; se ele nunca for encontrado, tente baixar em vez de subir."
            )
        )
        confidence_row.addStretch(1)
        form.addRow("Confiança mínima deste ponto (0 a 1)", confidence_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_data(self) -> dict | None:
        icon_name = self.combo_icon.currentText()
        if not icon_name:
            return None
        return {
            "icon": f"img/map/icons/{icon_name}",
            "wait_s": max(0.0, parse_float(self.input_wait.text(), 5.0)),
            "confidence": max(0.0, min(1.0, parse_float(self.input_confidence.text(), 0.65))),
        }


class CavebotModuleView:
    worker_key = "cavebot"

    def __init__(self, controller, main_window):
        self.controller = controller
        self.main_window = main_window
        self.cfg = controller.config_store.section("cavebot")

        self.card = ModuleCard(
            "Cavebot",
            stat_specs=[("counter", "Pontos percorridos:", "0")],
        )
        self.card.configure_requested.connect(self.open_config_dialog)
        self.card.start_requested.connect(self.start)
        self.card.pause_requested.connect(self.toggle_pause)
        self.card.stop_requested.connect(self.stop)

        self.minimap_overlay = ManaOverlay(main_window)
        self.minimap_overlay.configure_region(self.cfg.get("minimap_region"))

        self.config_dialog = _ConfigDialog(main_window)
        self.config_dialog.setWindowTitle("Configurar - Cavebot")
        self.config_dialog.resize(560, 560)
        self._build_config_dialog()

        controller.register_module_view("cavebot", self)
        controller.module_event.connect(self._on_module_event)

    def _build_config_dialog(self) -> None:
        outer = QVBoxLayout(self.config_dialog)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        box_region = QGroupBox("1. Mini mapa")
        box_region_layout = QHBoxLayout(box_region)
        button_region = ActionButton("Capturar região do mini mapa...", variant="secondary")
        button_region.clicked.connect(self.pick_minimap_region)
        self.label_region = QLabel(region_text(self.cfg.get("minimap_region")))
        box_region_layout.addWidget(button_region)
        box_region_layout.addWidget(self.label_region)
        box_region_layout.addWidget(
            InfoIcon("Arraste cobrindo toda a área do mini mapa exibida na tela - ESC cancela.")
        )
        box_region_layout.addStretch(1)
        layout.addWidget(box_region)

        box_route = QGroupBox("2. Rota")
        box_route_layout = QVBoxLayout(box_route)

        route_hint_row = QHBoxLayout()
        route_hint_row.addWidget(
            InfoIcon(
                "Cada ponto é um marcador colocado de verdade no mini mapa do jogo (botão direito no "
                "mini mapa > Adicionar marcador), não um ícone genérico. Os arquivos 1.png a 15.png já "
                "vêm recortados na escala real do marcador no jogo - os ícones 16 a 20 ficam de fora de "
                "propósito (setas de direção e duplicatas, fáceis de confundir entre si).\n\n"
                "Se precisar de um marcador que ainda não existe, ou um que não está sendo reconhecido "
                "direito, capture-o ao vivo direto do mini mapa (com o marcador de verdade visível na "
                "tela) - nunca a partir da tela de seleção de marcador do jogo, que mostra o ícone numa "
                "escala bem maior que a real e não vai bater com o que aparece no mini mapa."
            )
        )
        route_hint_label = QLabel("Como funciona a rota")
        route_hint_label.setObjectName("HintLabel")
        route_hint_row.addWidget(route_hint_label)
        route_hint_row.addStretch(1)
        box_route_layout.addLayout(route_hint_row)

        self.list_waypoints = QListWidget()
        self._refresh_waypoint_list()
        box_route_layout.addWidget(self.list_waypoints)

        route_actions = QHBoxLayout()
        button_add = ActionButton("Adicionar ponto...", variant="secondary")
        button_add.clicked.connect(self.add_waypoint)
        route_actions.addWidget(button_add)
        button_edit = ActionButton("Editar selecionado...", variant="secondary")
        button_edit.clicked.connect(self.edit_waypoint)
        route_actions.addWidget(button_edit)
        button_remove = ActionButton("Remover selecionado", variant="secondary")
        button_remove.clicked.connect(self.remove_waypoint)
        route_actions.addWidget(button_remove)
        button_up = ActionButton("Mover para cima", variant="secondary")
        button_up.clicked.connect(self.move_waypoint_up)
        route_actions.addWidget(button_up)
        button_down = ActionButton("Mover para baixo", variant="secondary")
        button_down.clicked.connect(self.move_waypoint_down)
        route_actions.addWidget(button_down)
        route_actions.addStretch(1)
        box_route_layout.addLayout(route_actions)

        layout.addWidget(box_route)

        box_detect = QGroupBox("3. Detecção e clique")
        detect_form = QFormLayout(box_detect)

        confidence_row = QHBoxLayout()
        self.input_confidence = QLineEdit(str(self.cfg.get("confidence", 0.85)))
        self.input_confidence.setFixedWidth(60)
        confidence_row.addWidget(self.input_confidence)
        confidence_row.addWidget(
            InfoIcon(
                "Quanto menor, mais tolerante o reconhecimento do ícone (acha mais fácil, mas com mais "
                "risco de confundir com outra coisa). Quanto maior, mais rigoroso (mais seguro, mas pode "
                "não achar se o marcador não bater pixel a pixel com a imagem capturada).\n\n"
                "Para os ícones pequenos do mini mapa, 0.60-0.65 costuma funcionar bem - ajuste por ponto "
                "individual (botão Editar) se um marcador específico não estiver sendo achado ou estiver "
                "clicando no lugar errado."
            )
        )
        confidence_row.addStretch(1)
        detect_form.addRow("Confiança padrão (0 a 1) - usada só nos pontos sem valor próprio", confidence_row)

        self.input_check_interval = QLineEdit(str(self.cfg.get("check_interval", 0.3)))
        self.input_check_interval.setFixedWidth(60)
        detect_form.addRow("Intervalo entre tentativas (s)", self.input_check_interval)

        self.input_search_timeout = QLineEdit(str(self.cfg.get("search_timeout", 5.0)))
        self.input_search_timeout.setFixedWidth(60)
        detect_form.addRow("Tempo máximo procurando o ícone (s)", self.input_search_timeout)

        self.input_max_failures = QLineEdit(str(self.cfg.get("max_search_failures", 3)))
        self.input_max_failures.setFixedWidth(60)
        detect_form.addRow("Falhas seguidas antes de pular pro próximo ponto", self.input_max_failures)

        self.input_click_jitter = QLineEdit(str(self.cfg.get("click_jitter", 2)))
        self.input_click_jitter.setFixedWidth(60)
        detect_form.addRow("Variação do clique (px)", self.input_click_jitter)

        layout.addWidget(box_detect)

        warning_label = QLabel(
            "Aviso: o Cavebot não lê a Battle List sozinho - inicie o Target junto para ele pausar a "
            "rota durante combates e retomar depois. Recolher itens do chão (loot) não é feito "
            "automaticamente nesta versão."
        )
        warning_label.setStyleSheet("color: #a33;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        layout.addStretch(1)

        actions_bar = QHBoxLayout()
        actions_bar.addStretch(1)
        button_save = ActionButton("Salvar config", variant="primary")
        button_save.clicked.connect(self.save_config)
        actions_bar.addWidget(button_save)
        button_close = ActionButton("Fechar", variant="secondary")
        button_close.clicked.connect(self.config_dialog.hide)
        actions_bar.addWidget(button_close)
        outer.addLayout(actions_bar)

    def _refresh_waypoint_list(self) -> None:
        default_confidence = float(self.cfg.get("confidence", 0.65))
        self.list_waypoints.clear()
        for index, waypoint in enumerate(self.cfg.get("waypoints") or []):
            self.list_waypoints.addItem(_waypoint_label(index, waypoint, default_confidence))

    def open_config_dialog(self) -> None:
        self.config_dialog.show()
        self.config_dialog.raise_()
        self.config_dialog.activateWindow()

    def pick_minimap_region(self) -> None:
        region = self.controller.select_region("Arraste cobrindo toda a área do mini mapa  -  ESC cancela")
        if not region:
            return
        self.cfg["minimap_region"] = region
        self.label_region.setText(region_text(region))
        self.minimap_overlay.configure_region(region)
        self.controller.config_store.save()
        self.controller.log(f"Região do mini mapa definida: {region_text(region)}", source="cavebot")

    def add_waypoint(self) -> None:
        available = _list_icon_files()
        if not available:
            QMessageBox.warning(self.main_window, "Cavebot", f"Nenhum ícone encontrado em {ICONS_DIR}.")
            return
        default_confidence = float(self.cfg.get("confidence", 0.65))
        dialog = _AddWaypointDialog(default_confidence, parent=self.config_dialog)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()
        if not data:
            return
        waypoints = list(self.cfg.get("waypoints") or [])
        waypoints.append(data)
        self.cfg["waypoints"] = waypoints
        self._refresh_waypoint_list()
        self.controller.config_store.save()

    def edit_waypoint(self) -> None:
        row = self.list_waypoints.currentRow()
        waypoints = list(self.cfg.get("waypoints") or [])
        if row < 0 or row >= len(waypoints):
            QMessageBox.warning(self.main_window, "Cavebot", "Selecione um ponto da lista primeiro.")
            return
        default_confidence = float(self.cfg.get("confidence", 0.65))
        dialog = _AddWaypointDialog(default_confidence, initial=waypoints[row], parent=self.config_dialog)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()
        if not data:
            return
        waypoints[row] = data
        self.cfg["waypoints"] = waypoints
        self._refresh_waypoint_list()
        self.list_waypoints.setCurrentRow(row)
        self.controller.config_store.save()

    def remove_waypoint(self) -> None:
        row = self.list_waypoints.currentRow()
        waypoints = list(self.cfg.get("waypoints") or [])
        if row < 0 or row >= len(waypoints):
            return
        del waypoints[row]
        self.cfg["waypoints"] = waypoints
        self._refresh_waypoint_list()
        self.controller.config_store.save()

    def move_waypoint_up(self) -> None:
        row = self.list_waypoints.currentRow()
        if row <= 0:
            return
        waypoints = list(self.cfg.get("waypoints") or [])
        waypoints[row - 1], waypoints[row] = waypoints[row], waypoints[row - 1]
        self.cfg["waypoints"] = waypoints
        self._refresh_waypoint_list()
        self.list_waypoints.setCurrentRow(row - 1)
        self.controller.config_store.save()

    def move_waypoint_down(self) -> None:
        row = self.list_waypoints.currentRow()
        waypoints = list(self.cfg.get("waypoints") or [])
        if row < 0 or row >= len(waypoints) - 1:
            return
        waypoints[row + 1], waypoints[row] = waypoints[row], waypoints[row + 1]
        self.cfg["waypoints"] = waypoints
        self._refresh_waypoint_list()
        self.list_waypoints.setCurrentRow(row + 1)
        self.controller.config_store.save()

    def worker_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(self.controller.build_worker_extras())
        return cfg

    def save_config(self) -> None:
        self.cfg["confidence"] = max(0.0, min(1.0, parse_float(self.input_confidence.text(), 0.85)))
        self.cfg["check_interval"] = max(0.05, parse_float(self.input_check_interval.text(), 0.3))
        self.cfg["search_timeout"] = max(0.5, parse_float(self.input_search_timeout.text(), 5.0))
        self.cfg["max_search_failures"] = max(1, parse_int(self.input_max_failures.text(), 3))
        self.cfg["click_jitter"] = max(0, parse_int(self.input_click_jitter.text(), 2))
        self.controller.config_store.save()

    def start(self) -> None:
        self.save_config()
        if not self.cfg.get("waypoints"):
            QMessageBox.warning(self.main_window, "Cavebot", "Adicione ao menos um ponto na rota primeiro.")
            return
        if not is_valid_region(self.cfg.get("minimap_region")):
            QMessageBox.warning(self.main_window, "Cavebot", "Capture a região do mini mapa primeiro.")
            return
        self.controller.start_worker(self.worker_key, CavebotWorker, self.worker_config())

    def toggle_pause(self) -> None:
        self.controller.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.controller.stop_worker(self.worker_key)

    def close_overlays(self) -> None:
        self.minimap_overlay.hide()

    def on_state(self, state: str) -> None:
        self.card.set_state(state)
        if state in ("running", "paused"):
            self.minimap_overlay.show()
        else:
            self.minimap_overlay.hide()

    def on_counter(self, value) -> None:
        self.card.set_stat("counter", str(value))

    def _on_module_event(self, source: str, kind: str, payload) -> None:
        if source != "cavebot":
            return
        if kind == "state":
            self.on_state(payload)
        elif kind == "counter":
            self.on_counter(payload)
