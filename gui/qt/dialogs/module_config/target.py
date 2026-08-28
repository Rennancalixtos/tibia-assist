from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, load_image, save_image
from functions.target import TargetWorker
from gui.qt.components.action_button import ActionButton
from gui.qt.components.hotkey_button import HotkeyButton
from gui.qt.components.info_tooltip import InfoIcon
from gui.qt.components.module_card import ModuleCard
from gui.widgets import parse_float, parse_int, region_text


class TargetModuleView:
    worker_key = "target"

    def __init__(self, controller, main_window):
        self.controller = controller
        self.main_window = main_window
        self.cfg = controller.config_store.section("target")

        self.card = ModuleCard(
            "Target",
            extra_actions=[
                ("Testar leitura da Battle List", self.test_read),
                ("Testar tecla de ataque", self.test_attack_key),
            ],
            stat_specs=[("counter", "Ataques disparados:", "0")],
            icon="target.svg",
        )
        self.card.configure_requested.connect(self.open_config_dialog)
        self.card.start_requested.connect(self.start)
        self.card.pause_requested.connect(self.toggle_pause)
        self.card.stop_requested.connect(self.stop)

        self._build_config_dialog()

        controller.register_module_view("target", self)
        controller.module_event.connect(self._on_module_event)

    def _build_config_dialog(self) -> None:
        self.config_dialog = QDialog(self.main_window)
        self.config_dialog.setWindowTitle("Configurar - Target")
        self.config_dialog.resize(640, 480)
        self.config_dialog.closeEvent = self._config_dialog_close_event

        outer_layout = QVBoxLayout(self.config_dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        body_layout = QVBoxLayout(body)

        box_list = QGroupBox("1. Battle List")
        box_list_layout = QVBoxLayout(box_list)

        region_row = QHBoxLayout()
        button_region = ActionButton("Capturar Battle List", variant="secondary")
        button_region.clicked.connect(self.pick_battle_list_region)
        self.label_region = QLabel(region_text(self.cfg.get("battle_list_region")))
        region_row.addWidget(button_region)
        region_row.addWidget(self.label_region)
        region_row.addWidget(
            InfoIcon(
                "Arraste cobrindo toda a área visível do Battle (completo) - cabeçalho + linhas)  -  ESC cancela. "
                "conferir a cor de ataque em qualquer linha."
            )
        )
        region_row.addStretch(1)
        box_list_layout.addLayout(region_row)

        empty_row = QHBoxLayout()
        button_empty = ActionButton("Capturar Battle vazia", variant="secondary")
        button_empty.clicked.connect(self.capture_empty_template)
        self.label_empty_template = QLabel(self._empty_template_label_text())
        empty_row.addWidget(button_empty)
        empty_row.addWidget(self.label_empty_template)
        empty_row.addWidget(
            InfoIcon(
                "Com a lista VAZIA no jogo, arraste incluindo o título da janela 'Battle' + a 1ª linha (vazia) "
                "logo abaixo (onde ficaria o primeiro monstro) - esse recorte maior identifica melhor e dispensa "
                "saber quantas linhas cabem na Battle List."
            )
        )
        empty_row.addStretch(1)
        box_list_layout.addLayout(empty_row)

        body_layout.addWidget(box_list)

        box_color = QGroupBox("2. Cor de ataque (nome da criatura)")
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
        color_row.addWidget(
            InfoIcon(
                "Sem variante de hover: o ataque agora é por tecla de atalho, o mouse nunca fica em cima da lista. "
                "Padrão RGB 254,0,0 (vermelho puro do nome em ATAQUE)."
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

        body_layout.addWidget(box_color)

        box_key = QGroupBox("3. Tecla de ataque")
        box_key_layout = QVBoxLayout(box_key)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Tecla de ataque (ex: space)"))
        self.button_attack_key = HotkeyButton(self.cfg.get("attack_key", "space"))
        key_row.addWidget(self.button_attack_key)
        key_row.addWidget(
            InfoIcon(
                "Precisa estar configurada DENTRO do Tibia primeiro (Options > Hotkeys > Attack) para atacar "
                "a criatura mais próxima/selecionada."
            )
        )
        key_row.addStretch(1)
        box_key_layout.addLayout(key_row)

        key_form = QFormLayout()
        self.input_attack_check_delay = QLineEdit(str(self.cfg.get("attack_check_delay", 0.5)))
        self.input_attack_check_delay.setFixedWidth(60)
        key_form.addRow("Delay após apertar (s) (aguarda antes de conferir a cor)", self.input_attack_check_delay)
        box_key_layout.addLayout(key_form)

        body_layout.addWidget(box_key)

        box_rate = QGroupBox("4. Ritmo")
        rate_form = QFormLayout(box_rate)
        self.input_idle_min = QLineEdit(str(self.cfg.get("idle_delay_min", 2.0)))
        self.input_idle_min.setFixedWidth(60)
        rate_form.addRow("Delay mínimo (lista vazia) (s) (ex: 2.0)", self.input_idle_min)
        self.input_idle_max = QLineEdit(str(self.cfg.get("idle_delay_max", 4.0)))
        self.input_idle_max.setFixedWidth(60)
        rate_form.addRow("Delay máximo (lista vazia) (s) (ex: 4.0)", self.input_idle_max)
        self.input_engaged_min = QLineEdit(str(self.cfg.get("engaged_delay_min", 1.0)))
        self.input_engaged_min.setFixedWidth(60)
        rate_form.addRow("Delay mínimo (já atacando) (s) (ex: 1.0)", self.input_engaged_min)
        self.input_engaged_max = QLineEdit(str(self.cfg.get("engaged_delay_max", 2.0)))
        self.input_engaged_max.setFixedWidth(60)
        rate_form.addRow("Delay máximo (já atacando) (s) (ex: 2.0)", self.input_engaged_max)

        body_layout.addWidget(box_rate)

        warning_label = QLabel(
            "Aviso: esta função depende de leitura visual (template/cor) da Battle List. Mudar o tamanho da "
            "janela do jogo, o zoom ou a skin da Battle List depois de calibrar pode quebrar a detecção - "
            "recalibre se isso acontecer."
        )
        warning_label.setStyleSheet("color: #a33;")
        warning_label.setWordWrap(True)
        body_layout.addWidget(warning_label)

        actions_bar = QHBoxLayout()
        actions_bar.addStretch(1)
        button_save = ActionButton("Salvar config", variant="primary")
        button_save.clicked.connect(self.save_config)
        button_close = ActionButton("Fechar", variant="secondary")
        button_close.clicked.connect(self.config_dialog.hide)
        actions_bar.addWidget(button_save)
        actions_bar.addWidget(button_close)
        body_layout.addLayout(actions_bar)

        body_layout.addStretch(1)

    def _config_dialog_close_event(self, event) -> None:
        event.ignore()
        self.config_dialog.hide()

    def open_config_dialog(self) -> None:
        self.config_dialog.show()
        self.config_dialog.raise_()
        self.config_dialog.activateWindow()

    def _empty_template_label_text(self) -> str:
        path = self.cfg.get("battle_empty_template")
        if not path:
            return "não calibrado"
        image = load_image(path)
        if image is None:
            return "não calibrado (arquivo do modelo não encontrado)"
        height, width = image.shape[:2]
        return f"Modelo salvo ({width}x{height} px)"

    def pick_battle_list_region(self) -> None:
        region = self.controller.select_region(
            "Arraste cobrindo toda a área visível da Battle List (cabeçalho + linhas)  -  ESC cancela"
        )
        if not region:
            return
        self.cfg["battle_list_region"] = region
        self.label_region.setText(region_text(region))
        self.controller.config_store.save()
        self.controller.log(f"Região da Battle List definida: {region_text(region)}", source="target")

    def capture_empty_template(self) -> None:
        region = self.controller.select_region(
            "Com a lista VAZIA, selecione o cabeçalho 'Battle' + a 1ª linha (vazia)  -  ESC cancela"
        )
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, "target_battle_empty.png")
        save_image(path, frame)
        self.cfg["battle_empty_template"] = path
        self.label_empty_template.setText(self._empty_template_label_text())
        self.controller.config_store.save()
        self.controller.log(f"Modelo de lista vazia salvo em {path}", source="target")

    def worker_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(self.controller.build_worker_extras())
        return cfg

    def test_read(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TargetWorker(dict(cfg), self.controller.events)
            worker.setup()
        except Exception as exc:
            QMessageBox.critical(self.main_window, "Target", f"Falha ao preparar leitura: {exc}")
            return
        try:
            score = worker.battle_list_empty_score()
            vazia = worker.is_battle_list_empty()
            attacking = worker.is_attacking() if not vazia else False
        except Exception as exc:
            worker.teardown()
            QMessageBox.critical(self.main_window, "Target", f"Falha na leitura: {exc}")
            return
        worker.teardown()
        score_text = f"{score * 100:.1f}%" if score is not None else "modelo maior que a região"
        message = (
            f"Battle List vazia: {'sim' if vazia else 'não'} (confiança: {score_text}, mínimo: "
            f"{worker.empty_threshold * 100:.0f}%)\n"
            f"Cor de ataque detectada: {'sim' if attacking else 'não'}"
        )
        self.controller.log(message.replace("\n", " | "), source="target")
        QMessageBox.information(self.main_window, "Target - Testar leitura", message)

    def test_attack_key(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TargetWorker(dict(cfg), self.controller.events)
            worker.setup()
        except Exception as exc:
            QMessageBox.critical(self.main_window, "Target", f"Falha ao preparar teste: {exc}")
            return
        try:
            dry_run = bool(self.controller.dry_run_enabled)
            if not dry_run and QMessageBox.question(
                self.main_window,
                "Target",
                f"Modo REAL: isso vai apertar a tecla '{worker.attack_key}' de verdade. Continuar?",
            ) != QMessageBox.Yes:
                return
            worker.press_attack_key(dry_run=dry_run)
        except Exception as exc:
            QMessageBox.critical(self.main_window, "Target", f"Falha no teste da tecla de ataque: {exc}")
            return
        finally:
            worker.teardown()
        self.controller.log(f"Teste da tecla de ataque concluído ('{worker.attack_key}').", source="target")
        QMessageBox.information(self.main_window, "Target", f"Tecla de ataque testada ('{worker.attack_key}' - ver log).")

    def save_config(self) -> None:
        self.cfg["attack_color_rgb"] = [
            max(0, min(255, parse_int(self.input_color_r.text(), 254))),
            max(0, min(255, parse_int(self.input_color_g.text(), 0))),
            max(0, min(255, parse_int(self.input_color_b.text(), 0))),
        ]
        self.cfg["attack_color_tolerance"] = max(0, parse_int(self.input_color_tolerance.text(), 6))
        self.cfg["attack_color_min_pixels"] = max(1, parse_int(self.input_color_min_pixels.text(), 3))
        self.cfg["attack_key"] = (self.button_attack_key.value() or "space").strip().lower()
        self.cfg["attack_check_delay"] = max(0.0, parse_float(self.input_attack_check_delay.text(), 0.5))
        self.cfg["idle_delay_min"] = parse_float(self.input_idle_min.text(), 2.0)
        self.cfg["idle_delay_max"] = parse_float(self.input_idle_max.text(), 4.0)
        self.cfg["engaged_delay_min"] = parse_float(self.input_engaged_min.text(), 1.0)
        self.cfg["engaged_delay_max"] = parse_float(self.input_engaged_max.text(), 2.0)
        self.controller.config_store.save()

    def start(self) -> None:
        self.save_config()
        if not is_valid_region(self.cfg.get("battle_list_region")):
            QMessageBox.warning(self.main_window, "Target", "Selecione a região da Battle List primeiro.")
            return
        if not self.cfg.get("battle_empty_template"):
            QMessageBox.warning(self.main_window, "Target", "Capture o modelo de lista vazia primeiro.")
            return
        self.controller.start_worker(self.worker_key, TargetWorker, self.worker_config())

    def toggle_pause(self) -> None:
        self.controller.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.controller.stop_worker(self.worker_key)

    def on_state(self, state: str) -> None:
        self.card.set_state(state)

    def on_counter(self, value) -> None:
        self.card.set_stat("counter", str(value))

    def _on_module_event(self, source: str, kind: str, payload) -> None:
        if source != "target":
            return
        if kind == "state":
            self.on_state(payload)
        elif kind == "counter":
            self.on_counter(payload)
