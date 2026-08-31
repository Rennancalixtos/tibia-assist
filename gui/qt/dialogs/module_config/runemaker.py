from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.rune_maker import OCRUnavailable, RuneMakerWorker, configure_tesseract, read_number
from gui.qt.components.action_button import ActionButton
from gui.qt.components.hotkey_button import HotkeyButton
from gui.qt.components.info_tooltip import InfoIcon
from gui.qt.components.module_card import ModuleCard
from gui.qt.components.warning_banner import WarningBanner
from gui.qt.overlays.mana_overlay import ManaOverlay
from gui.widgets import parse_float, parse_int, region_text


class _ConfigDialog(QDialog):
    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


class RuneMakerModuleView:
    worker_key = "runemaker"

    def __init__(self, controller, main_window):
        self.controller = controller
        self.main_window = main_window
        self.cfg = controller.config_store.section("runemaker")

        self.card = ModuleCard(
            "RuneMaker", stat_specs=[("counter", "Runas criadas:", "0")], icon="runemaker.svg"
        )
        self.card.start_requested.connect(self.start)
        self.card.pause_requested.connect(self.toggle_pause)
        self.card.stop_requested.connect(self.stop)
        self.card.configure_requested.connect(self.open_config_dialog)

        self.mana_overlay = ManaOverlay(main_window, log_overlay=main_window.log_overlay)
        self.mana_overlay.configure_region(self.cfg.get("mana_region"))
        self._last_state = "stopped"

        self._build_config_dialog()

        controller.register_module_view("runemaker", self)
        controller.module_event.connect(self._on_module_event)
        controller.region_overlays_toggled.connect(self._apply_overlay_visibility)

        self._on_mode_change()

    def _build_config_dialog(self) -> None:
        self.config_dialog = _ConfigDialog(self.main_window)
        self.config_dialog.setWindowTitle("Configurar - RuneMaker")
        self.config_dialog.resize(640, 600)

        dialog_layout = QVBoxLayout(self.config_dialog)
        dialog_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        dialog_layout.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(10)

        body_layout.addWidget(self._build_mode_box())
        body_layout.addWidget(self._build_spell_box())
        body_layout.addWidget(self._build_slots_box())
        body_layout.addWidget(self._build_ocr_box())
        body_layout.addWidget(self._build_rate_box())

        actions_row = QHBoxLayout()
        btn_save = ActionButton("Salvar config", variant="primary")
        btn_save.clicked.connect(self.save_config)
        actions_row.addWidget(btn_save)
        btn_close = ActionButton("Fechar", variant="secondary")
        btn_close.clicked.connect(self.config_dialog.hide)
        actions_row.addWidget(btn_close)
        actions_row.addStretch(1)
        body_layout.addLayout(actions_row)

        body_layout.addStretch(1)

    def _build_mode_box(self) -> QGroupBox:
        box = QGroupBox("1. Modo")
        layout = QVBoxLayout(box)

        radio_row = QHBoxLayout()
        self.radio_craft = QRadioButton("Criar runas")
        self.radio_mana_training = QRadioButton("ManaTraining (só conjura a magia, sem item)")
        self._mode_group = QButtonGroup(box)
        self._mode_group.addButton(self.radio_craft)
        self._mode_group.addButton(self.radio_mana_training)
        initial_mode = self.cfg.get("mode", "craft")
        self.radio_mana_training.setChecked(initial_mode == "mana_training")
        self.radio_craft.setChecked(initial_mode != "mana_training")
        self.radio_craft.toggled.connect(lambda _checked: self._on_mode_change())
        self.radio_mana_training.toggled.connect(lambda _checked: self._on_mode_change())
        radio_row.addWidget(self.radio_craft)
        radio_row.addWidget(self.radio_mana_training)
        radio_row.addStretch(1)
        layout.addLayout(radio_row)

        layout.addWidget(WarningBanner("⚠ Não ative os dois ao mesmo tempo - são modos alternativos, escolha um."))
        return box

    def _build_spell_box(self) -> QGroupBox:
        box = QGroupBox("2. Magia e blank runes")
        layout = QVBoxLayout(box)

        spell_row = QHBoxLayout()
        spell_row.addWidget(QLabel("Tecla da magia"))
        self.hotkey_spell = HotkeyButton(self.cfg.get("spell_hotkey", "f2"))
        spell_row.addWidget(self.hotkey_spell)
        spell_hint = QLabel("hotkey configurada no jogo (ex: f2)")
        spell_hint.setObjectName("StatLabel")
        spell_row.addWidget(spell_hint)
        spell_row.addStretch(1)
        layout.addLayout(spell_row)

        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel("Quantidade de runas"))
        self.entry_amount = QLineEdit(str(self.cfg.get("amount", 0)))
        self.entry_amount.setMaximumWidth(90)
        amount_row.addWidget(self.entry_amount)
        amount_hint = QLabel("0 = até acabar a mana")
        amount_hint.setObjectName("StatLabel")
        amount_row.addWidget(amount_hint)
        amount_row.addStretch(1)
        layout.addLayout(amount_row)

        blank_row = QHBoxLayout()
        self.btn_pick_blank_slot = ActionButton("Selecionar slot da blank rune...", variant="secondary")
        self.btn_pick_blank_slot.clicked.connect(self.pick_slot)
        blank_row.addWidget(self.btn_pick_blank_slot)
        self.label_slot = QLabel(region_text(self.cfg.get("blank_slot")))
        blank_row.addWidget(self.label_slot)
        blank_row.addStretch(1)
        layout.addLayout(blank_row)

        self.chk_no_hand = QCheckBox("Servidor não requer mão (aplicar magia direto no slot da blank rune)")
        self.chk_no_hand.setChecked(bool(self.cfg.get("no_hand_mode", False)))
        self.chk_no_hand.toggled.connect(self._on_no_hand_toggle)
        layout.addWidget(self.chk_no_hand)

        hand_row = QHBoxLayout()
        self.btn_pick_hand = ActionButton("Selecionar slot da mão...", variant="secondary")
        self.btn_pick_hand.clicked.connect(self.pick_hand_slot)
        hand_row.addWidget(self.btn_pick_hand)
        self.label_hand_slot = QLabel(region_text(self.cfg.get("hand_slot")))
        hand_row.addWidget(self.label_hand_slot)
        hand_row.addStretch(1)
        layout.addLayout(hand_row)

        output_row = QHBoxLayout()
        self.btn_pick_output = ActionButton("Selecionar slot livre (destino)...", variant="secondary")
        self.btn_pick_output.clicked.connect(self.pick_output_slot)
        output_row.addWidget(self.btn_pick_output)
        self.label_output_slot = QLabel(region_text(self.cfg.get("output_slot")))
        output_row.addWidget(self.label_output_slot)
        output_row.addStretch(1)
        layout.addLayout(output_row)

        return box

    def _build_slots_box(self) -> QGroupBox:
        box = QGroupBox("2.1 Detecção de slot vazio (template)")
        layout = QVBoxLayout(box)

        blank_empty_row = QHBoxLayout()
        self.btn_capture_blank_empty = ActionButton("Capturar slot vazio (origem)...", variant="secondary")
        self.btn_capture_blank_empty.clicked.connect(
            lambda: self._capture_empty_template(
                "blank_slot", "de ORIGEM (blank rune)", self.label_blank_region
            )
        )
        blank_empty_row.addWidget(self.btn_capture_blank_empty)
        self.label_blank_region = QLabel(region_text(self.cfg.get("blank_slot_region")))
        blank_empty_row.addWidget(self.label_blank_region)
        blank_empty_row.addStretch(1)
        layout.addLayout(blank_empty_row)

        hand_empty_row = QHBoxLayout()
        self.btn_capture_hand_empty = ActionButton("Capturar slot vazio (mão)...", variant="secondary")
        self.btn_capture_hand_empty.clicked.connect(
            lambda: self._capture_empty_template("hand_slot", "da MÃO", self.label_hand_region)
        )
        hand_empty_row.addWidget(self.btn_capture_hand_empty)
        self.label_hand_region = QLabel(region_text(self.cfg.get("hand_slot_region")))
        hand_empty_row.addWidget(self.label_hand_region)
        hand_empty_row.addStretch(1)
        layout.addLayout(hand_empty_row)

        output_empty_row = QHBoxLayout()
        self.btn_capture_output_empty = ActionButton("Capturar slot vazio (destino)...", variant="secondary")
        self.btn_capture_output_empty.clicked.connect(
            lambda: self._capture_empty_template("output_slot", "de DESTINO", self.label_output_region)
        )
        output_empty_row.addWidget(self.btn_capture_output_empty)
        self.label_output_region = QLabel(region_text(self.cfg.get("output_slot_region")))
        output_empty_row.addWidget(self.label_output_region)
        output_empty_row.addStretch(1)
        layout.addLayout(output_empty_row)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Cobertura mínima do slot vazio (%)"))
        self.entry_empty_threshold = QLineEdit(
            str(int(float(self.cfg.get("empty_match_threshold", 0.90)) * 100))
        )
        self.entry_empty_threshold.setMaximumWidth(90)
        threshold_row.addWidget(self.entry_empty_threshold)
        threshold_hint = QLabel("0 a 100 (padrão 90)")
        threshold_hint.setObjectName("StatLabel")
        threshold_row.addWidget(threshold_hint)
        threshold_row.addStretch(1)
        layout.addLayout(threshold_row)

        test_row = QHBoxLayout()
        self.btn_test_sequence = ActionButton("Testar sequência", variant="secondary")
        self.btn_test_sequence.clicked.connect(self.test_sequence)
        test_row.addWidget(self.btn_test_sequence)
        test_row.addStretch(1)
        layout.addLayout(test_row)

        return box

    def _build_ocr_box(self) -> QGroupBox:
        box = QGroupBox("3. Limites de segurança (OCR)")
        layout = QVBoxLayout(box)

        check_row = QHBoxLayout()
        self.chk_check_mana = QCheckBox("Verificar mana")
        self.chk_check_mana.setChecked(bool(self.cfg.get("check_mana", True)))
        check_row.addWidget(self.chk_check_mana)
        btn_pick_mana_region = ActionButton("Região da mana...", variant="secondary")
        btn_pick_mana_region.clicked.connect(lambda: self.pick_ocr_region("mana"))
        check_row.addWidget(btn_pick_mana_region)
        self.label_mana_region = QLabel(region_text(self.cfg.get("mana_region")))
        check_row.addWidget(self.label_mana_region)
        check_row.addStretch(1)
        layout.addLayout(check_row)

        min_mana_row = QHBoxLayout()
        min_mana_row.addWidget(QLabel("Mana mínima"))
        self.entry_min_mana = QLineEdit(str(self.cfg.get("min_mana")))
        self.entry_min_mana.setMaximumWidth(90)
        min_mana_row.addWidget(self.entry_min_mana)
        min_mana_hint = QLabel("pausa abaixo disso")
        min_mana_hint.setObjectName("StatLabel")
        min_mana_row.addWidget(min_mana_hint)
        min_mana_row.addStretch(1)
        layout.addLayout(min_mana_row)

        test_ocr_row = QHBoxLayout()
        btn_test_ocr = ActionButton("Testar OCR", variant="secondary")
        btn_test_ocr.clicked.connect(self.test_ocr)
        test_ocr_row.addWidget(btn_test_ocr)
        test_ocr_row.addStretch(1)
        layout.addLayout(test_ocr_row)

        mana_hint_row = QHBoxLayout()
        mana_hint_row.addWidget(
            InfoIcon(
                "Overlay sobre a tela do jogo: marca a região acima e mostra o valor lido logo "
                "acima do log na tela do jogo."
            )
        )
        mana_hint_row.addStretch(1)
        layout.addLayout(mana_hint_row)

        return box

    def _build_rate_box(self) -> QGroupBox:
        box = QGroupBox("4. Ritmo")
        layout = QVBoxLayout(box)

        delay_min_row = QHBoxLayout()
        delay_min_row.addWidget(QLabel("Delay mínimo (s)"))
        self.entry_delay_min = QLineEdit(str(self.cfg.get("delay_min")))
        self.entry_delay_min.setMaximumWidth(90)
        delay_min_row.addWidget(self.entry_delay_min)
        delay_min_hint = QLabel(">= cooldown real da magia")
        delay_min_hint.setObjectName("StatLabel")
        delay_min_row.addWidget(delay_min_hint)
        delay_min_row.addStretch(1)
        layout.addLayout(delay_min_row)

        delay_max_row = QHBoxLayout()
        delay_max_row.addWidget(QLabel("Delay máximo (s)"))
        self.entry_delay_max = QLineEdit(str(self.cfg.get("delay_max")))
        self.entry_delay_max.setMaximumWidth(90)
        delay_max_row.addWidget(self.entry_delay_max)
        delay_max_hint = QLabel("ex: 2.5")
        delay_max_hint.setObjectName("StatLabel")
        delay_max_row.addWidget(delay_max_hint)
        delay_max_row.addStretch(1)
        layout.addLayout(delay_max_row)

        jitter_row = QHBoxLayout()
        jitter_row.addWidget(QLabel("Variação do clique (px)"))
        self.entry_jitter = QLineEdit(str(self.cfg.get("click_jitter")))
        self.entry_jitter.setMaximumWidth(90)
        jitter_row.addWidget(self.entry_jitter)
        jitter_hint = QLabel("+/- pixels")
        jitter_hint.setObjectName("StatLabel")
        jitter_row.addWidget(jitter_hint)
        jitter_row.addStretch(1)
        layout.addLayout(jitter_row)

        return box

    def open_config_dialog(self) -> None:
        self.config_dialog.show()
        self.config_dialog.raise_()
        self.config_dialog.activateWindow()

    def _on_no_hand_toggle(self) -> None:
        self._update_field_states()

    def _on_mode_change(self) -> None:
        is_mana_training = self.radio_mana_training.isChecked()
        self.card.set_stat_caption("counter", "Magias conjuradas:" if is_mana_training else "Runas criadas:")
        self._update_field_states()

    def _update_field_states(self) -> None:
        mana_training = self.radio_mana_training.isChecked()
        item_enabled = not mana_training

        self.entry_amount.setEnabled(item_enabled)
        self.btn_pick_blank_slot.setEnabled(item_enabled)
        self.chk_no_hand.setEnabled(item_enabled)
        for widget in (self.btn_capture_blank_empty, self.entry_empty_threshold, self.btn_test_sequence):
            widget.setEnabled(item_enabled)

        hand_enabled = not (mana_training or self.chk_no_hand.isChecked())
        for widget in (
            self.btn_pick_hand,
            self.btn_pick_output,
            self.btn_capture_hand_empty,
            self.btn_capture_output_empty,
        ):
            widget.setEnabled(hand_enabled)

    def pick_slot(self) -> None:
        point = self.controller.select_point("Clique no slot da BLANK RUNE  -  ESC cancela")
        if point:
            self.cfg["blank_slot"] = list(point)
            self.label_slot.setText(region_text(point))
            self.controller.config_store.save()
            self.log(f"Slot da blank rune definido: {region_text(point)}")

    def pick_hand_slot(self) -> None:
        point = self.controller.select_point("Clique no slot da MÃO do personagem  -  ESC cancela")
        if point:
            self.cfg["hand_slot"] = list(point)
            self.label_hand_slot.setText(region_text(point))
            self.controller.config_store.save()
            self.log(f"Slot da mão definido: {region_text(point)}")

    def pick_output_slot(self) -> None:
        point = self.controller.select_point("Clique no slot LIVRE de destino  -  ESC cancela")
        if point:
            self.cfg["output_slot"] = list(point)
            self.label_output_slot.setText(region_text(point))
            self.controller.config_store.save()
            self.log(f"Slot de destino definido: {region_text(point)}")

    def pick_ocr_region(self, key: str) -> None:
        label = "MANA"
        region = self.controller.select_region(f"Selecione o número de {label} na barra de status  -  ESC cancela")
        if not region:
            return
        self.cfg[f"{key}_region"] = region
        self.label_mana_region.setText(region_text(region))
        self.mana_overlay.configure_region(region)
        self.controller.config_store.save()
        self.log(f"Região de {label} definida: {region_text(region)}")

    def _capture_empty_template(self, slot_key: str, label: str, region_label: QLabel) -> None:
        region = self.controller.select_region(f"Selecione o slot {label} VAZIO  -  ESC cancela")
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, f"rune_{slot_key}_empty.png")
        save_image(path, frame)
        self.cfg[f"{slot_key}_region"] = region
        self.cfg[f"{slot_key}_empty_template"] = path
        region_label.setText(region_text(region))
        self.controller.config_store.save()
        self.log(f"Template de slot vazio ({label}) salvo em {path} ({region[2]}x{region[3]} px)")

    def test_ocr(self) -> None:
        self.save_config()
        configure_tesseract(on_progress=self.log)
        region = self.cfg.get("mana_region")
        if not is_valid_region(region):
            QMessageBox.warning(self.main_window, "RuneMaker", "Região de mana não configurada.")
            return
        try:
            with ScreenCapture() as cap:
                value = read_number(cap.grab(region))
        except OCRUnavailable as exc:
            QMessageBox.critical(self.main_window, "RuneMaker", str(exc))
            return
        message = f"OCR mana: {value if value is not None else 'não reconhecido'}"
        self.log(message)
        QMessageBox.information(self.main_window, "RuneMaker", message)

    def test_sequence(self) -> None:
        self.save_config()
        if self.cfg.get("mode") == "mana_training":
            QMessageBox.information(
                self.main_window, "RuneMaker", "Testar sequência só se aplica ao modo 'Criar runas'."
            )
            return

        dry_run = bool(self.controller.dry_run_enabled)
        if not dry_run:
            reply = QMessageBox.question(
                self.main_window,
                "RuneMaker",
                "Modo REAL: isso vai clicar/arrastar de verdade. Continuar?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        cfg = dict(self.cfg)
        cfg.update(self.controller.build_worker_extras())
        try:
            worker = RuneMakerWorker(cfg, self.controller.events)
            worker.setup()
            if worker.no_hand_mode:
                ok = worker._simple_craft_cycle(dry_run=dry_run)
            else:
                ok = worker._craft_cycle(dry_run=dry_run)
            worker.teardown()
        except Exception as exc:
            QMessageBox.critical(self.main_window, "RuneMaker", f"Falha no teste: {exc}")
            return

        message = (
            "Sequência de teste concluída (ver log)."
            if ok
            else "Sequência de teste falhou em alguma validação (ver log)."
        )
        QMessageBox.information(self.main_window, "RuneMaker", message)

    def save_config(self) -> None:
        self.cfg["spell_hotkey"] = self.hotkey_spell.value().strip().lower()
        self.cfg["amount"] = parse_int(self.entry_amount.text(), 0)
        self.cfg["delay_min"] = parse_float(self.entry_delay_min.text(), 1.5)
        self.cfg["delay_max"] = parse_float(self.entry_delay_max.text(), 2.5)
        self.cfg["click_jitter"] = parse_int(self.entry_jitter.text(), 2)
        self.cfg["min_mana"] = parse_int(self.entry_min_mana.text(), 300)
        self.cfg["check_mana"] = bool(self.chk_check_mana.isChecked())
        self.cfg["mode"] = "mana_training" if self.radio_mana_training.isChecked() else "craft"
        self.cfg["no_hand_mode"] = bool(self.chk_no_hand.isChecked())
        coverage_pct = max(0, min(100, parse_int(self.entry_empty_threshold.text(), 90)))
        self.cfg["empty_match_threshold"] = coverage_pct / 100
        self.controller.config_store.save()

    def start(self) -> None:
        self.save_config()
        mode = self.cfg.get("mode")
        if mode != "mana_training":
            if not self.cfg.get("blank_slot"):
                QMessageBox.warning(self.main_window, "RuneMaker", "Selecione o slot da blank rune primeiro.")
                return
            if not self.cfg.get("no_hand_mode"):
                if not self.cfg.get("hand_slot"):
                    QMessageBox.warning(
                        self.main_window, "RuneMaker", "Selecione o slot da mão do personagem primeiro."
                    )
                    return
                if not self.cfg.get("output_slot"):
                    QMessageBox.warning(
                        self.main_window, "RuneMaker", "Selecione o slot livre de destino primeiro."
                    )
                    return
        self.controller.start_worker(self.worker_key, RuneMakerWorker, dict(self.cfg))

    def toggle_pause(self) -> None:
        self.controller.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.controller.stop_worker(self.worker_key)

    def log(self, message: str) -> None:
        self.controller.log(message, source=self.worker_key)

    def on_state(self, state: str) -> None:
        self.card.set_state(state)
        running = state in ("running", "paused")
        self.radio_craft.setEnabled(not running)
        self.radio_mana_training.setEnabled(not running)
        self.chk_no_hand.setEnabled(not running)
        self._last_state = state
        self._apply_overlay_visibility()

    def _apply_overlay_visibility(self) -> None:
        if self._last_state in ("running", "paused") and self.controller.region_overlays_enabled:
            self.mana_overlay.show()
        else:
            self.mana_overlay.hide()

    def on_counter(self, value) -> None:
        self.card.set_stat("counter", str(value))

    def on_mana_reading(self, value) -> None:
        self.mana_overlay.update_value(value)

    def close_overlays(self) -> None:
        self.mana_overlay.hide()

    def _on_module_event(self, source: str, kind: str, payload) -> None:
        if source != "runemaker":
            return
        if kind == "state":
            self.on_state(payload)
        elif kind == "counter":
            self.on_counter(payload)
        elif kind == "mana_reading":
            self.on_mana_reading(payload)
