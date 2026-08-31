from __future__ import annotations

import os

import cv2

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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
from functions.auto_fishing import (
    AutoFishingWorker,
    draw_tile_grid,
    dynamic_v_bounds,
    find_water_template,
    find_water_tiles_hsv,
    median_brightness,
    sample_hsv_range,
)
from gui.qt.components.action_button import ActionButton
from gui.qt.components.info_tooltip import InfoIcon
from gui.qt.components.module_card import ModuleCard
from gui.qt.overlays.fishing_warning_overlay import FishingWarningOverlay
from gui.widgets import parse_float, parse_int, region_text

BUTTON_LABELS = {"right": "direito", "left": "esquerdo"}
BUTTON_VALUES = {label: value for value, label in BUTTON_LABELS.items()}


def _add_field(layout: QVBoxLayout, label: str, width: int = 12, hint: str = "") -> QLineEdit:
    row = QHBoxLayout()
    row.addWidget(QLabel(label))
    edit = QLineEdit()
    edit.setFixedWidth(width * 9)
    row.addWidget(edit)
    if hint:
        hint_label = QLabel(hint)
        hint_label.setObjectName("HintLabel")
        row.addWidget(hint_label)
    row.addStretch(1)
    layout.addLayout(row)
    return edit


class _ConfigDialog(QDialog):
    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


class FishingModuleView:
    worker_key = "fishing"

    def __init__(self, controller, main_window):
        self.controller = controller
        self.main_window = main_window
        self.cfg = controller.config_store.section("fishing")

        self.card = ModuleCard(
            "AutoFishing",
            stat_specs=[("counter", "Lances na sessão:", "0")],
            icon="fishing.svg",
        )
        self.card.start_requested.connect(self.start)
        self.card.pause_requested.connect(self.toggle_pause)
        self.card.stop_requested.connect(self.stop)
        self.card.configure_requested.connect(self.open_config_dialog)

        self.warning_overlay = FishingWarningOverlay(hwnd_resolver=controller.resolve_game_window_hwnd, parent=main_window)
        self._last_state = "stopped"

        self.config_dialog = _ConfigDialog(main_window)
        self.config_dialog.setWindowTitle("Configurar - AutoFishing")
        self.config_dialog.resize(640, 600)
        self._build_config_dialog()

        controller.register_module_view("fishing", self)
        controller.module_event.connect(self._on_module_event)
        controller.region_overlays_toggled.connect(self._apply_overlay_visibility)

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

        box_rod = QGroupBox("1. Vara de pescar")
        box_rod_layout = QHBoxLayout(box_rod)
        pick_rod_button = ActionButton("Selecionar posição da vara...", variant="secondary")
        pick_rod_button.clicked.connect(self.pick_rod_slot)
        box_rod_layout.addWidget(pick_rod_button)
        self.rod_slot_label = QLabel(region_text(self.cfg.get("rod_slot")))
        box_rod_layout.addWidget(self.rod_slot_label)
        box_rod_layout.addStretch(1)
        layout.addWidget(box_rod)

        box_region = QGroupBox("2. Região monitorada (lago)")
        box_region_layout = QHBoxLayout(box_region)
        pick_region_button = ActionButton("Selecionar região...", variant="secondary")
        pick_region_button.clicked.connect(self.pick_region)
        box_region_layout.addWidget(pick_region_button)
        self.region_label = QLabel(region_text(self.cfg.get("region")))
        box_region_layout.addWidget(self.region_label)
        box_region_layout.addStretch(1)
        layout.addWidget(box_region)

        box_detect = QGroupBox("3. Detecção de água")
        box_detect_layout = QVBoxLayout(box_detect)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Modo"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["hsv", "template"])
        self.mode_combo.setCurrentText(self.cfg.get("detection_mode", "hsv"))
        mode_row.addWidget(self.mode_combo)
        mode_row.addWidget(InfoIcon("hsv = cor da água | template = imagem de referência"))
        mode_row.addStretch(1)
        box_detect_layout.addLayout(mode_row)

        self.hsv_lower_edit = _add_field(box_detect_layout, "HSV mínimo", 16, "H, S, V")
        self.hsv_lower_edit.setText(", ".join(map(str, self.cfg.get("hsv_lower"))))
        self.hsv_upper_edit = _add_field(box_detect_layout, "HSV máximo", 16, "H, S, V")
        self.hsv_upper_edit.setText(", ".join(map(str, self.cfg.get("hsv_upper"))))
        self.min_area_edit = _add_field(box_detect_layout, "Área mínima", 8, "px de água na região")
        self.min_area_edit.setText(str(self.cfg.get("min_area")))
        self.threshold_edit = _add_field(box_detect_layout, "Threshold template", 8, "0.0 a 1.0")
        self.threshold_edit.setText(str(self.cfg.get("template_threshold")))
        self.tile_size_edit = _add_field(box_detect_layout, "Tamanho do SQM (px)", 8, "32 = tile padrão sem zoom")
        self.tile_size_edit.setText(str(self.cfg.get("tile_size", 32)))
        self.tile_coverage_edit = _add_field(box_detect_layout, "Cobertura mínima do SQM (%)", 8, "0 a 100")
        self.tile_coverage_edit.setText(str(int(self.cfg.get("min_tile_coverage", 0.35) * 100)))

        self.auto_recalibrate_check = QCheckBox("Recalibração automática periódica (EMA)")
        self.auto_recalibrate_check.setChecked(bool(self.cfg.get("auto_recalibrate_enabled", False)))
        box_detect_layout.addWidget(self.auto_recalibrate_check)

        self.recalibrate_interval_edit = _add_field(
            box_detect_layout, "Intervalo de recalibração (min)", 8, "ex: 15"
        )
        self.recalibrate_interval_edit.setText(str(self.cfg.get("auto_recalibrate_interval_minutes", 15)))

        self.effective_hsv_label = QLabel("HSV efetivo atual: -")
        self.effective_hsv_label.setObjectName("HintLabel")
        box_detect_layout.addWidget(self.effective_hsv_label)

        detect_actions = QHBoxLayout()
        calibrate_button = ActionButton("Calibrar cor da água...", variant="secondary")
        calibrate_button.clicked.connect(self.calibrate_color)
        detect_actions.addWidget(calibrate_button)
        capture_button = ActionButton("Capturar template...", variant="secondary")
        capture_button.clicked.connect(self.capture_template)
        detect_actions.addWidget(capture_button)
        test_button = ActionButton("Testar detecção", variant="secondary")
        test_button.clicked.connect(self.test_detection)
        detect_actions.addWidget(test_button)
        preview_button = ActionButton("Visualizar grid (SQM)...", variant="secondary")
        preview_button.clicked.connect(self.preview_grid)
        detect_actions.addWidget(preview_button)
        detect_actions.addStretch(1)
        box_detect_layout.addLayout(detect_actions)

        layout.addWidget(box_detect)

        box_click = QGroupBox("4. Clique e ritmo")
        box_click_layout = QVBoxLayout(box_click)

        button_row = QHBoxLayout()
        button_row.addWidget(QLabel("Botão na água"))
        self.button_combo = QComboBox()
        self.button_combo.addItems(["direito", "esquerdo"])
        self.button_combo.setCurrentText(
            BUTTON_LABELS.get(self.cfg.get("mouse_button", "right"), "direito")
        )
        button_row.addWidget(self.button_combo)
        button_row.addWidget(InfoIcon("A vara sempre usa o botão direito - isso aqui é só pra água."))
        button_row.addStretch(1)
        box_click_layout.addLayout(button_row)

        self.delay_min_edit = _add_field(box_click_layout, "Delay mínimo (s)", 8, "ex: 1.8")
        self.delay_min_edit.setText(str(self.cfg.get("delay_min")))
        self.delay_max_edit = _add_field(box_click_layout, "Delay máximo (s)", 8, "ex: 3.2")
        self.delay_max_edit.setText(str(self.cfg.get("delay_max")))
        self.jitter_edit = _add_field(box_click_layout, "Variação do clique (px)", 8, "+/- pixels")
        self.jitter_edit.setText(str(self.cfg.get("click_jitter")))
        self.max_casts_edit = _add_field(box_click_layout, "Limite de lances", 8, "0 = ilimitado")
        self.max_casts_edit.setText(str(self.cfg.get("max_casts")))

        self.randomize_check = QCheckBox("Sortear entre as tiles de água encontradas")
        self.randomize_check.setChecked(bool(self.cfg.get("randomize_target", True)))
        box_click_layout.addWidget(self.randomize_check)

        layout.addWidget(box_click)

        box_break = QGroupBox("5. Pausas periódicas (descanso)")
        box_break_layout = QVBoxLayout(box_break)

        self.break_enabled_check = QCheckBox("Ativar pausas periódicas")
        self.break_enabled_check.setChecked(bool(self.cfg.get("break_enabled", True)))
        box_break_layout.addWidget(self.break_enabled_check)

        self.break_interval_min_edit = _add_field(
            box_break_layout, "Pesca no mínimo (s)", 8, "antes de considerar pausa"
        )
        self.break_interval_min_edit.setText(str(self.cfg.get("break_interval_min", 60)))
        self.break_interval_max_edit = _add_field(
            box_break_layout, "Pesca no máximo (s)", 8, "ex: 300 = até 5 min"
        )
        self.break_interval_max_edit.setText(str(self.cfg.get("break_interval_max", 300)))
        self.break_duration_min_edit = _add_field(
            box_break_layout, "Pausa mínima (s)", 8, "duração mínima do descanso"
        )
        self.break_duration_min_edit.setText(str(self.cfg.get("break_duration_min", 15)))
        self.break_duration_max_edit = _add_field(
            box_break_layout, "Pausa máxima (s)", 8, "ex: 120 = até 2 min"
        )
        self.break_duration_max_edit.setText(str(self.cfg.get("break_duration_max", 120)))

        layout.addWidget(box_break)

        layout.addStretch(1)

        actions_bar = QHBoxLayout()
        actions_bar.addStretch(1)
        save_button = ActionButton("Salvar config", variant="primary")
        save_button.clicked.connect(self.save_config)
        actions_bar.addWidget(save_button)
        close_button = ActionButton("Fechar", variant="secondary")
        close_button.clicked.connect(self.config_dialog.hide)
        actions_bar.addWidget(close_button)
        outer.addLayout(actions_bar)

    def open_config_dialog(self) -> None:
        self.config_dialog.show()
        self.config_dialog.raise_()
        self.config_dialog.activateWindow()

    def pick_rod_slot(self) -> None:
        point = self.controller.select_point("Clique na posição da VARA DE PESCAR  -  ESC cancela")
        if point:
            self.cfg["rod_slot"] = list(point)
            self.rod_slot_label.setText(region_text(point))
            self.controller.config_store.save()
            self.controller.log(f"Posição da vara definida: {region_text(point)}", source=self.worker_key)

    def pick_region(self) -> None:
        region = self.controller.select_region("Arraste sobre a área de pesca  -  ESC cancela")
        if region:
            self.cfg["region"] = region
            self.region_label.setText(region_text(region))
            self.controller.config_store.save()
            self.controller.log(f"Região de pesca definida: {region_text(region)}", source=self.worker_key)

    def calibrate_color(self) -> None:
        region = self.controller.select_region("Selecione um pedaço de ÁGUA  -  ESC cancela")
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        lower, upper, reference_brightness = sample_hsv_range(frame)
        self.hsv_lower_edit.setText(", ".join(map(str, lower)))
        self.hsv_upper_edit.setText(", ".join(map(str, upper)))
        self.mode_combo.setCurrentText("hsv")
        self.cfg["hsv_reference_brightness"] = reference_brightness
        self.save_config()
        self.controller.log(
            f"Cor calibrada: HSV {lower} - {upper} (brilho de referência: {reference_brightness:.0f})",
            source=self.worker_key,
        )

    def capture_template(self) -> None:
        region = self.controller.select_region("Selecione UMA tile de água  -  ESC cancela")
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, self.cfg.get("template_file", "water_template.png"))
        save_image(path, frame)
        self.mode_combo.setCurrentText("template")
        self.save_config()
        self.controller.log(
            f"Template salvo em {path} ({region[2]}x{region[3]} px)", source=self.worker_key
        )

    def _run_detection(self) -> tuple:
        cfg = self.worker_config()
        if not is_valid_region(cfg.get("region")):
            raise ValueError("Selecione a região monitorada primeiro.")
        with ScreenCapture() as cap:
            frame = cap.grab(cfg["region"])
        if cfg.get("detection_mode") == "template":
            template = load_image(cfg["template_path"])
            if template is None:
                raise ValueError("Template de água não encontrado. Calibre um template ou use o modo HSV.")
            targets = find_water_template(frame, template, cfg.get("template_threshold", 0.80))
            self.effective_hsv_label.setText("HSV efetivo atual: - (modo template)")
        else:
            hsv_lower = cfg.get("hsv_lower", [90, 60, 40])
            hsv_upper = cfg.get("hsv_upper", [130, 255, 255])
            reference_brightness = cfg.get("hsv_reference_brightness")
            if reference_brightness is not None:
                hsv_lower, hsv_upper, delta = dynamic_v_bounds(
                    hsv_lower, hsv_upper, median_brightness(frame), reference_brightness
                )
                self.effective_hsv_label.setText(
                    f"HSV efetivo atual: {hsv_lower} - {hsv_upper}  (delta V={delta:+.0f} vs calibrado)"
                )
            else:
                self.effective_hsv_label.setText(
                    f"HSV efetivo atual: {hsv_lower} - {hsv_upper} (sem ajuste dia/noite)"
                )
            targets = find_water_tiles_hsv(
                frame,
                hsv_lower,
                hsv_upper,
                int(cfg.get("min_area", 200)),
                int(cfg.get("tile_size", 32)),
                float(cfg.get("min_tile_coverage", 0.35)),
            )
        return frame, targets

    def test_detection(self) -> None:
        self.save_config()
        try:
            _frame, targets = self._run_detection()
        except Exception as exc:
            QMessageBox.critical(self.config_dialog, "AutoFishing", f"Falha no teste: {exc}")
            return
        message = f"Teste de detecção: {len(targets)} SQM(s) de água encontrado(s)."
        if targets:
            cx, cy, score = targets[0]
            message += f"\nMelhor candidato (relativo à região): x={cx} y={cy} score/cobertura={score}"
        self.controller.log(message, source=self.worker_key)
        QMessageBox.information(self.config_dialog, "AutoFishing", message)

    def preview_grid(self) -> None:
        self.save_config()
        try:
            frame, targets = self._run_detection()
        except Exception as exc:
            QMessageBox.critical(self.config_dialog, "AutoFishing", f"Falha no teste: {exc}")
            return
        tile_size = max(4, parse_int(self.tile_size_edit.text(), 32))
        preview = draw_tile_grid(frame, targets, tile_size)
        self.controller.log(
            f"Grid de SQM: {len(targets)} tile(s) válido(s) - feche a janela para continuar.",
            source=self.worker_key,
        )
        cv2.imshow("AutoFishing - grid de SQM (ESC ou fechar a janela)", preview)
        cv2.waitKey(0)
        cv2.destroyWindow("AutoFishing - grid de SQM (ESC ou fechar a janela)")

    def worker_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg["template_path"] = os.path.join(ASSETS_DIR, self.cfg.get("template_file", "water_template.png"))
        return cfg

    def save_config(self) -> None:
        def parse_triple(text: str, fallback: list[int]) -> list[int]:
            parts = [p for p in str(text).replace(";", ",").split(",") if p.strip()]
            if len(parts) != 3:
                return fallback
            return [max(0, parse_int(p, 0)) for p in parts]

        self.cfg["detection_mode"] = self.mode_combo.currentText()
        self.cfg["hsv_lower"] = parse_triple(self.hsv_lower_edit.text(), self.cfg["hsv_lower"])
        self.cfg["hsv_upper"] = parse_triple(self.hsv_upper_edit.text(), self.cfg["hsv_upper"])
        self.cfg["min_area"] = parse_int(self.min_area_edit.text(), 200)
        self.cfg["tile_size"] = max(4, parse_int(self.tile_size_edit.text(), 32))
        coverage_pct = max(0, min(100, parse_int(self.tile_coverage_edit.text(), 35)))
        self.cfg["min_tile_coverage"] = coverage_pct / 100
        self.cfg["template_threshold"] = parse_float(self.threshold_edit.text(), 0.80)
        self.cfg["mouse_button"] = BUTTON_VALUES.get(self.button_combo.currentText(), "right")
        self.cfg["delay_min"] = parse_float(self.delay_min_edit.text(), 1.8)
        self.cfg["delay_max"] = parse_float(self.delay_max_edit.text(), 3.2)
        self.cfg["click_jitter"] = parse_int(self.jitter_edit.text(), 2)
        self.cfg["max_casts"] = parse_int(self.max_casts_edit.text(), 0)
        self.cfg["randomize_target"] = bool(self.randomize_check.isChecked())
        self.cfg["break_enabled"] = bool(self.break_enabled_check.isChecked())
        self.cfg["break_interval_min"] = parse_int(self.break_interval_min_edit.text(), 30)
        self.cfg["break_interval_max"] = parse_int(self.break_interval_max_edit.text(), 300)
        self.cfg["break_duration_min"] = parse_int(self.break_duration_min_edit.text(), 10)
        self.cfg["break_duration_max"] = parse_int(self.break_duration_max_edit.text(), 120)
        self.cfg["auto_recalibrate_enabled"] = bool(self.auto_recalibrate_check.isChecked())
        self.cfg["auto_recalibrate_interval_minutes"] = max(
            1, parse_int(self.recalibrate_interval_edit.text(), 15)
        )
        self.controller.config_store.save()

    def apply_config_update(self, updates: dict) -> None:
        self.cfg.update(updates)
        self.controller.config_store.save()
        if "hsv_lower" in updates:
            self.hsv_lower_edit.setText(", ".join(map(str, updates["hsv_lower"])))
        if "hsv_upper" in updates:
            self.hsv_upper_edit.setText(", ".join(map(str, updates["hsv_upper"])))

    def start(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        if not self.cfg.get("rod_slot"):
            QMessageBox.warning(
                self.main_window, "AutoFishing", "Selecione a posição da vara de pescar primeiro."
            )
            return
        if not is_valid_region(cfg.get("region")):
            QMessageBox.warning(self.main_window, "AutoFishing", "Selecione a região monitorada primeiro.")
            return
        self.controller.start_worker(self.worker_key, AutoFishingWorker, cfg)

    def toggle_pause(self) -> None:
        self.controller.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.controller.stop_worker(self.worker_key)

    def _apply_overlay_visibility(self) -> None:
        if self._last_state in ("running", "paused") and self.controller.region_overlays_enabled:
            self.warning_overlay.show()
        else:
            self.warning_overlay.hide()

    def on_state(self, state: str) -> None:
        self.card.set_state(state)
        self._last_state = state
        self._apply_overlay_visibility()

    def on_counter(self, value: int) -> None:
        self.card.set_stat("counter", str(value))

    def close_overlays(self) -> None:
        self.warning_overlay.hide()

    def _on_module_event(self, source: str, kind: str, payload) -> None:
        if source != "fishing":
            return
        if kind == "state":
            self.on_state(payload)
        elif kind == "counter":
            self.on_counter(payload)
        elif kind == "config_update":
            self.apply_config_update(payload)
