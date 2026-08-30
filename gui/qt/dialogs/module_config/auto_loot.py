from __future__ import annotations

import os
import time

import cv2

from PySide6.QtWidgets import (
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

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.auto_loot import AutoLootWorker, resolve_icon_path
from gui.qt.components.action_button import ActionButton
from gui.qt.components.info_tooltip import InfoIcon
from gui.qt.components.module_card import ModuleCard
from gui.qt.overlays.mana_overlay import ManaOverlay
from gui.widgets import parse_float, parse_int, region_text

LOOT_ICONS_DIR = os.path.join(ASSETS_DIR, "auto_loot")

GOLD_PRESET_ITEMS = [
    {"icon": "img/itens/gold/gold_1.png", "nome": "Moeda de ouro (1)", "confidence": 0.75},
    {"icon": "img/itens/gold/gold_2.png", "nome": "Moeda de ouro (2)", "confidence": 0.75},
    {"icon": "img/itens/gold/gold_3.png", "nome": "Moeda de ouro (3)", "confidence": 0.75},
    {"icon": "img/itens/gold/gold_4.png", "nome": "Moeda de ouro (4)", "confidence": 0.75},
    {"icon": "img/itens/gold/gold_5_9.png", "nome": "Moeda de ouro (5-9)", "confidence": 0.75},
    {"icon": "img/itens/gold/gold_10_24.png", "nome": "Moeda de ouro (10-24)", "confidence": 0.75},
    {"icon": "img/itens/gold/gold_26_49.png", "nome": "Moeda de ouro (26-49)", "confidence": 0.75},
    {"icon": "img/itens/gold/gold_50_100.png", "nome": "Moeda de ouro (50-100)", "confidence": 0.75},
]


def _load_icon_for_display(path: str):
    resolved = resolve_icon_path(path)
    if not resolved:
        return None
    return cv2.imread(resolved, cv2.IMREAD_UNCHANGED)


def _loot_item_label(index: int, item: dict) -> str:
    nome = item.get("nome") or "?"
    confidence = item.get("confidence", 0.85)
    return f"{index + 1}. {nome} - confiança: {confidence:.2f}"


class _ConfigDialog(QDialog):
    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


class _AddLootItemDialog(QDialog):
    def __init__(self, controller, initial: dict | None = None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._icon_path = (initial or {}).get("icon")
        self.setWindowTitle("Editar item" if initial else "Adicionar item")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.input_nome = QLineEdit((initial or {}).get("nome", ""))
        form.addRow("Nome", self.input_nome)

        confidence_row = QHBoxLayout()
        self.input_confidence = QLineEdit(str((initial or {}).get("confidence", 0.85)))
        self.input_confidence.setFixedWidth(80)
        confidence_row.addWidget(self.input_confidence)
        confidence_row.addWidget(
            InfoIcon(
                "Menor = acha mais fácil, mais risco de confundir com outro item da bag. Maior = mais "
                "seguro, mas pode não achar o ícone.\n\n"
                "Ícones de item de inventário costumam ser maiores que os marcadores do mini mapa - "
                "comece em 0.80-0.85."
            )
        )
        confidence_row.addStretch(1)
        form.addRow("Confiança mínima (0 a 1)", confidence_row)

        layout.addLayout(form)

        icon_row = QHBoxLayout()
        button_capture = ActionButton("Capturar ícone...", variant="secondary")
        button_capture.clicked.connect(self._capture_icon)
        icon_row.addWidget(button_capture)
        self.label_icon = QLabel(self._icon_label_text())
        icon_row.addWidget(self.label_icon)
        icon_row.addStretch(1)
        layout.addLayout(icon_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.input_nome.textChanged.connect(self._refresh_ok_enabled)
        self._refresh_ok_enabled()

    def _icon_label_text(self) -> str:
        if not self._icon_path:
            return "não capturado"
        image = _load_icon_for_display(self._icon_path)
        if image is None:
            return "não capturado (arquivo do ícone não encontrado)"
        height, width = image.shape[:2]
        return f"Ícone salvo ({width}x{height} px)"

    def _capture_icon(self) -> None:
        region = self.controller.select_region("Recorte o ícone do item na bag  -  ESC cancela")
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(LOOT_ICONS_DIR, exist_ok=True)
        path = os.path.join(LOOT_ICONS_DIR, f"loot_{int(time.time() * 1000)}.png")
        save_image(path, frame)
        self._icon_path = path
        self.label_icon.setText(self._icon_label_text())
        self._refresh_ok_enabled()

    def _refresh_ok_enabled(self) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        ok_button.setEnabled(bool(self._icon_path) and bool(self.input_nome.text().strip()))

    def result_data(self) -> dict | None:
        if not self._icon_path:
            return None
        return {
            "icon": self._icon_path,
            "nome": self.input_nome.text().strip(),
            "confidence": max(0.0, min(1.0, parse_float(self.input_confidence.text(), 0.85))),
        }


class AutoLootModuleView:
    worker_key = "auto_loot"

    def __init__(self, controller, main_window):
        self.controller = controller
        self.main_window = main_window
        self.cfg = controller.config_store.section("auto_loot")

        self.card = ModuleCard(
            "AutoLoot",
            stat_specs=[("counter", "Itens recolhidos:", "0")],
        )
        self.card.configure_requested.connect(self.open_config_dialog)
        self.card.start_requested.connect(self.start)
        self.card.pause_requested.connect(self.toggle_pause)
        self.card.stop_requested.connect(self.stop)

        self.death_watch_overlay = ManaOverlay(main_window)
        self.death_watch_overlay.configure_region(self.cfg.get("death_watch_region"))
        self.corpse_overlay = ManaOverlay(main_window)
        self.corpse_overlay.configure_region(self.cfg.get("corpse_region"))

        self.config_dialog = _ConfigDialog(main_window)
        self.config_dialog.setWindowTitle("Configurar - AutoLoot")
        self.config_dialog.resize(560, 700)
        self._build_config_dialog()

        controller.register_module_view("auto_loot", self)
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

        box_death = QGroupBox("1. Área de monitoramento da morte")
        box_death_layout = QHBoxLayout(box_death)
        button_death = ActionButton("Capturar área...", variant="secondary")
        button_death.clicked.connect(self.pick_death_watch_region)
        self.label_death_region = QLabel(region_text(self.cfg.get("death_watch_region")))
        box_death_layout.addWidget(button_death)
        box_death_layout.addWidget(self.label_death_region)
        box_death_layout.addWidget(
            InfoIcon(
                "Área da tela do jogo onde o monstro engajado costuma aparecer. Necessária porque em "
                "servidores old-school a cave é escura e o monstro pode não aparecer visualmente mesmo "
                "com a Battle List mostrando o ataque.\n\n"
                "Cubra uma área generosa ao redor do personagem - a mesma cor de ataque do Target é "
                "monitorada aqui, só que na tela do jogo em vez da Battle List."
            )
        )
        box_death_layout.addStretch(1)
        layout.addWidget(box_death)

        box_color = QGroupBox("2. Cor de ataque")
        box_color_layout = QVBoxLayout(box_color)

        rgb = self.cfg.get("attack_color_rgb") or [254, 0, 0]
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("RGB:"))
        self.input_color_r = QLineEdit(str(rgb[0]))
        self.input_color_r.setFixedWidth(50)
        self.input_color_g = QLineEdit(str(rgb[1]))
        self.input_color_g.setFixedWidth(50)
        self.input_color_b = QLineEdit(str(rgb[2]))
        self.input_color_b.setFixedWidth(50)
        color_row.addWidget(self.input_color_r)
        color_row.addWidget(self.input_color_g)
        color_row.addWidget(self.input_color_b)
        button_copy_target = ActionButton("Copiar do Target", variant="secondary")
        button_copy_target.clicked.connect(self.copy_color_from_target)
        color_row.addWidget(button_copy_target)
        color_row.addWidget(
            InfoIcon(
                "Mesma cor de ataque já configurada no Target (nome da criatura em vermelho), só que "
                "lida na tela do jogo em vez da Battle List.\n\n"
                "Se o Target já estiver calibrado, use 'Copiar do Target' em vez de recalibrar do zero."
            )
        )
        color_row.addStretch(1)
        box_color_layout.addLayout(color_row)

        color_form = QFormLayout()
        self.input_color_tolerance = QLineEdit(str(self.cfg.get("attack_color_tolerance", 6)))
        self.input_color_tolerance.setFixedWidth(60)
        color_form.addRow("Tolerância por canal (0 a 255, padrão 6)", self.input_color_tolerance)
        self.input_color_min_pixels = QLineEdit(str(self.cfg.get("attack_color_min_pixels", 3)))
        self.input_color_min_pixels.setFixedWidth(60)
        color_form.addRow("Pixels mínimos (padrão 3)", self.input_color_min_pixels)
        box_color_layout.addLayout(color_form)

        layout.addWidget(box_color)

        box_corpse = QGroupBox("3. Bag de origem (corpo)")
        box_corpse_layout = QHBoxLayout(box_corpse)
        button_corpse = ActionButton("Capturar região do corpo...", variant="secondary")
        button_corpse.clicked.connect(self.pick_corpse_region)
        self.label_corpse_region = QLabel(region_text(self.cfg.get("corpse_region")))
        box_corpse_layout.addWidget(button_corpse)
        box_corpse_layout.addWidget(self.label_corpse_region)
        box_corpse_layout.addWidget(
            InfoIcon(
                "Com o corpo já aberto no jogo, arraste cobrindo toda a área de slots da bag do corpo - "
                "ESC cancela.\n\n"
                "Essa região é fixa (calibrada uma vez), assumindo que a janela do container sempre "
                "abre no mesmo lugar na tela."
            )
        )
        box_corpse_layout.addStretch(1)
        layout.addWidget(box_corpse)

        box_dest = QGroupBox("4. Bag de destino")
        box_dest_layout = QHBoxLayout(box_dest)
        button_dest = ActionButton("Selecionar ponto de destino...", variant="secondary")
        button_dest.clicked.connect(self.pick_destination_point)
        self.label_dest_point = QLabel(region_text(self.cfg.get("destination_point")))
        box_dest_layout.addWidget(button_dest)
        box_dest_layout.addWidget(self.label_dest_point)
        box_dest_layout.addWidget(
            InfoIcon(
                "Clique num ponto dentro da backpack para onde os itens encontrados serão arrastados.\n\n"
                "Esse ponto não pode cair dentro da região da bag de origem (item 3) - se as duas bags "
                "ficarem sobrepostas na tela, o AutoLoot pode confundir item já guardado no destino com "
                "item ainda no corpo."
            )
        )
        box_dest_layout.addStretch(1)
        layout.addWidget(box_dest)

        box_items = QGroupBox("5. Itens de loot")
        box_items_layout = QVBoxLayout(box_items)

        self.list_items = QListWidget()
        self._refresh_item_list()
        box_items_layout.addWidget(self.list_items)

        items_actions = QHBoxLayout()
        button_add = ActionButton("Adicionar item...", variant="secondary")
        button_add.clicked.connect(self.add_item)
        items_actions.addWidget(button_add)
        button_gold_preset = ActionButton("Adicionar predefinição: Moeda de ouro", variant="secondary")
        button_gold_preset.clicked.connect(self.add_gold_preset)
        items_actions.addWidget(button_gold_preset)
        items_actions.addWidget(
            InfoIcon(
                "Adiciona de uma vez os 8 ícones de moeda de ouro já embutidos no programa (um por faixa de "
                "quantidade: 1, 2, 3, 4, 5-9, 10-24, 26-49, 50-100) - não precisa capturar nada na tela."
            )
        )
        button_edit = ActionButton("Editar selecionado...", variant="secondary")
        button_edit.clicked.connect(self.edit_item)
        items_actions.addWidget(button_edit)
        button_remove = ActionButton("Remover selecionado", variant="secondary")
        button_remove.clicked.connect(self.remove_item)
        items_actions.addWidget(button_remove)
        button_up = ActionButton("Mover para cima", variant="secondary")
        button_up.clicked.connect(self.move_item_up)
        items_actions.addWidget(button_up)
        button_down = ActionButton("Mover para baixo", variant="secondary")
        button_down.clicked.connect(self.move_item_down)
        items_actions.addWidget(button_down)
        items_actions.addStretch(1)
        box_items_layout.addLayout(items_actions)

        layout.addWidget(box_items)

        box_rate = QGroupBox("6. Ritmo e limites")
        rate_form = QFormLayout(box_rate)

        self.input_open_delay = QLineEdit(str(self.cfg.get("open_corpse_delay_s", 0.6)))
        self.input_open_delay.setFixedWidth(60)
        rate_form.addRow("Espera após abrir o corpo (s)", self.input_open_delay)

        self.input_check_interval = QLineEdit(str(self.cfg.get("check_interval", 0.3)))
        self.input_check_interval.setFixedWidth(60)
        rate_form.addRow("Intervalo de checagem da morte (s)", self.input_check_interval)

        death_confirm_row = QHBoxLayout()
        self.input_death_confirm = QLineEdit(str(self.cfg.get("death_confirm_delay_s", 0.6)))
        self.input_death_confirm.setFixedWidth(60)
        death_confirm_row.addWidget(self.input_death_confirm)
        death_confirm_row.addWidget(
            InfoIcon(
                "Tempo que a cor de ataque precisa ficar ausente antes de considerar que o monstro morreu.\n\n"
                "Evita abrir corpo no lugar errado por causa de uma piscada rápida do marcador de ataque "
                "(o monstro continua vivo, só a cor sumiu por um instante). Se ainda estiver abrindo corpo "
                "onde não tem nada, aumente esse valor."
            )
        )
        death_confirm_row.addStretch(1)
        rate_form.addRow("Confirmação de morte (s)", death_confirm_row)

        self.input_scan_timeout = QLineEdit(str(self.cfg.get("loot_scan_timeout_s", 3.0)))
        self.input_scan_timeout.setFixedWidth(60)
        rate_form.addRow("Tempo máximo procurando item por passada (s)", self.input_scan_timeout)

        self.input_max_passes = QLineEdit(str(self.cfg.get("max_loot_passes", 10)))
        self.input_max_passes.setFixedWidth(60)
        rate_form.addRow("Passadas máximas de loot por corpo", self.input_max_passes)

        self.input_click_jitter = QLineEdit(str(self.cfg.get("click_jitter", 2)))
        self.input_click_jitter.setFixedWidth(60)
        rate_form.addRow("Variação do clique/arraste (px)", self.input_click_jitter)

        layout.addWidget(box_rate)

        warning_label = QLabel(
            "Aviso: a coleta de itens verifica a região da bag de origem continuamente, mesmo se o corpo "
            "for aberto manualmente ou pelo Cavebot - mas só enxerga um corpo por vez (o que estiver "
            "visível nessa região). Matar vários monstros em sequência sem dar tempo de lotar cada corpo "
            "não é tratado nesta versão."
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

    def _refresh_item_list(self) -> None:
        self.list_items.clear()
        for index, item in enumerate(self.cfg.get("loot_items") or []):
            self.list_items.addItem(_loot_item_label(index, item))

    def open_config_dialog(self) -> None:
        self.config_dialog.show()
        self.config_dialog.raise_()
        self.config_dialog.activateWindow()

    def pick_death_watch_region(self) -> None:
        region = self.controller.select_region(
            "Arraste cobrindo a área onde o monstro aparece  -  ESC cancela"
        )
        if not region:
            return
        self.cfg["death_watch_region"] = region
        self.label_death_region.setText(region_text(region))
        self.death_watch_overlay.configure_region(region)
        self.controller.config_store.save()
        self.controller.log(
            f"Área de monitoramento da morte definida: {region_text(region)}", source="auto_loot"
        )

    def pick_corpse_region(self) -> None:
        region = self.controller.select_region(
            "Com o corpo já aberto, arraste cobrindo a área de slots da bag  -  ESC cancela"
        )
        if not region:
            return
        self.cfg["corpse_region"] = region
        self.label_corpse_region.setText(region_text(region))
        self.corpse_overlay.configure_region(region)
        self.controller.config_store.save()
        self.controller.log(f"Região da bag do corpo definida: {region_text(region)}", source="auto_loot")

    def pick_destination_point(self) -> None:
        point = self.controller.select_point("Clique num ponto dentro da backpack de destino  -  ESC cancela")
        if not point:
            return
        self.cfg["destination_point"] = list(point)
        self.label_dest_point.setText(region_text(point))
        self.controller.config_store.save()
        self.controller.log(f"Ponto de destino definido: {region_text(point)}", source="auto_loot")

    def copy_color_from_target(self) -> None:
        target_cfg = self.controller.config_store.section("target")
        rgb = target_cfg.get("attack_color_rgb")
        if not rgb:
            QMessageBox.information(
                self.main_window, "AutoLoot", "O Target ainda não tem uma cor de ataque calibrada."
            )
            return
        self.input_color_r.setText(str(rgb[0]))
        self.input_color_g.setText(str(rgb[1]))
        self.input_color_b.setText(str(rgb[2]))

    def add_item(self) -> None:
        dialog = _AddLootItemDialog(self.controller, parent=self.config_dialog)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()
        if not data:
            return
        items = list(self.cfg.get("loot_items") or [])
        items.append(data)
        self.cfg["loot_items"] = items
        self._refresh_item_list()
        self.controller.config_store.save()

    def add_gold_preset(self) -> None:
        items = list(self.cfg.get("loot_items") or [])
        existing_icons = {item.get("icon") for item in items}
        added = 0
        for preset in GOLD_PRESET_ITEMS:
            if preset["icon"] in existing_icons:
                continue
            items.append(dict(preset))
            added += 1
        if added == 0:
            QMessageBox.information(
                self.main_window, "AutoLoot", "A predefinição de moeda de ouro já está toda adicionada."
            )
            return
        self.cfg["loot_items"] = items
        self._refresh_item_list()
        self.controller.config_store.save()
        self.controller.log(
            f"Predefinição de moeda de ouro adicionada ({added} ícone(s)).", source="auto_loot"
        )

    def edit_item(self) -> None:
        row = self.list_items.currentRow()
        items = list(self.cfg.get("loot_items") or [])
        if row < 0 or row >= len(items):
            QMessageBox.warning(self.main_window, "AutoLoot", "Selecione um item da lista primeiro.")
            return
        dialog = _AddLootItemDialog(self.controller, initial=items[row], parent=self.config_dialog)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.result_data()
        if not data:
            return
        items[row] = data
        self.cfg["loot_items"] = items
        self._refresh_item_list()
        self.list_items.setCurrentRow(row)
        self.controller.config_store.save()

    def remove_item(self) -> None:
        row = self.list_items.currentRow()
        items = list(self.cfg.get("loot_items") or [])
        if row < 0 or row >= len(items):
            return
        del items[row]
        self.cfg["loot_items"] = items
        self._refresh_item_list()
        self.controller.config_store.save()

    def move_item_up(self) -> None:
        row = self.list_items.currentRow()
        if row <= 0:
            return
        items = list(self.cfg.get("loot_items") or [])
        items[row - 1], items[row] = items[row], items[row - 1]
        self.cfg["loot_items"] = items
        self._refresh_item_list()
        self.list_items.setCurrentRow(row - 1)
        self.controller.config_store.save()

    def move_item_down(self) -> None:
        row = self.list_items.currentRow()
        items = list(self.cfg.get("loot_items") or [])
        if row < 0 or row >= len(items) - 1:
            return
        items[row + 1], items[row] = items[row], items[row + 1]
        self.cfg["loot_items"] = items
        self._refresh_item_list()
        self.list_items.setCurrentRow(row + 1)
        self.controller.config_store.save()

    def worker_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(self.controller.build_worker_extras())
        return cfg

    def save_config(self) -> None:
        self.cfg["attack_color_rgb"] = [
            max(0, min(255, parse_int(self.input_color_r.text(), 254))),
            max(0, min(255, parse_int(self.input_color_g.text(), 0))),
            max(0, min(255, parse_int(self.input_color_b.text(), 0))),
        ]
        self.cfg["attack_color_tolerance"] = max(0, parse_int(self.input_color_tolerance.text(), 6))
        self.cfg["attack_color_min_pixels"] = max(1, parse_int(self.input_color_min_pixels.text(), 3))
        self.cfg["open_corpse_delay_s"] = max(0.0, parse_float(self.input_open_delay.text(), 0.6))
        self.cfg["check_interval"] = max(0.05, parse_float(self.input_check_interval.text(), 0.3))
        self.cfg["death_confirm_delay_s"] = max(0.0, parse_float(self.input_death_confirm.text(), 0.6))
        self.cfg["loot_scan_timeout_s"] = max(0.0, parse_float(self.input_scan_timeout.text(), 3.0))
        self.cfg["max_loot_passes"] = max(1, parse_int(self.input_max_passes.text(), 10))
        self.cfg["click_jitter"] = max(0, parse_int(self.input_click_jitter.text(), 2))
        self.controller.config_store.save()

    def start(self) -> None:
        self.save_config()
        if not is_valid_region(self.cfg.get("death_watch_region")):
            QMessageBox.warning(
                self.main_window, "AutoLoot", "Capture a área de monitoramento da morte primeiro."
            )
            return
        if not is_valid_region(self.cfg.get("corpse_region")):
            QMessageBox.warning(
                self.main_window, "AutoLoot", "Capture a região da bag de origem (corpo) primeiro."
            )
            return
        if not self.cfg.get("destination_point"):
            QMessageBox.warning(self.main_window, "AutoLoot", "Selecione o ponto da bag de destino primeiro.")
            return
        if not self.cfg.get("loot_items"):
            QMessageBox.warning(self.main_window, "AutoLoot", "Adicione ao menos um item de loot primeiro.")
            return
        self.controller.start_worker(self.worker_key, AutoLootWorker, self.worker_config())

    def toggle_pause(self) -> None:
        self.controller.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.controller.stop_worker(self.worker_key)

    def close_overlays(self) -> None:
        self.death_watch_overlay.hide()
        self.corpse_overlay.hide()

    def on_state(self, state: str) -> None:
        self.card.set_state(state)
        if state in ("running", "paused"):
            self.death_watch_overlay.show()
            self.corpse_overlay.show()
        else:
            self.death_watch_overlay.hide()
            self.corpse_overlay.hide()

    def on_counter(self, value) -> None:
        self.card.set_stat("counter", str(value))

    def _on_module_event(self, source: str, kind: str, payload) -> None:
        if source != "auto_loot":
            return
        if kind == "state":
            self.on_state(payload)
        elif kind == "counter":
            self.on_counter(payload)
