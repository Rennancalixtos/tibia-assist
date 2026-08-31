from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
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
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.rune_maker import OCRUnavailable, configure_tesseract, read_number
from functions.training import TrainingWorker
from gui.qt.components.action_button import ActionButton
from gui.qt.components.hotkey_button import HotkeyButton
from gui.qt.components.info_tooltip import InfoIcon
from gui.qt.components.module_card import ModuleCard
from gui.qt.overlays.mana_overlay import ManaOverlay
from gui.widgets import parse_float, parse_int, region_text


class _ConfigDialog(QDialog):
    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


class TrainingModuleView:
    worker_key = "training"

    def __init__(self, controller, main_window):
        self.controller = controller
        self.main_window = main_window
        self.cfg = controller.config_store.section("training")

        self.card = ModuleCard(
            "Training",
            extra_actions=[
                ("Testar detecção", self.test_detection),
                ("Testar tecla de ataque", self.test_attack_key),
            ],
            stat_specs=[
                ("elapsed", "Tempo total treinando:", "00:00:00"),
                ("counter", "Ataques disparados:", "0"),
            ],
            icon="training.svg",
        )
        self.card.configure_requested.connect(self.open_config_dialog)
        self.card.start_requested.connect(self.start)
        self.card.pause_requested.connect(self.toggle_pause)
        self.card.stop_requested.connect(self.stop)

        self.battle_overlay = ManaOverlay(self.main_window)
        self.battle_overlay.configure_region(self.cfg.get("battle_list_region"))
        self._last_state = "stopped"

        self.config_dialog = _ConfigDialog(main_window)
        self.config_dialog.setWindowTitle("Configurar - Training")
        self.config_dialog.resize(640, 600)
        self._build_config_dialog()

        self._update_field_states()

        controller.register_module_view("training", self)
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

        box_list = QGroupBox("1. Battle List")
        box_list_layout = QVBoxLayout(box_list)

        region_row = QHBoxLayout()
        button_region = ActionButton("Selecionar região da Battle List...", variant="secondary")
        button_region.clicked.connect(self.pick_battle_list_region)
        self.label_region = QLabel(region_text(self.cfg.get("battle_list_region")))
        region_row.addWidget(button_region)
        region_row.addWidget(self.label_region)
        region_row.addWidget(
            InfoIcon(
                "Arraste só pela LISTA de criaturas (comece no topo da 1ª linha - sem "
                "pegar o título/ícones/dropdown de ordenação)."
            )
        )
        region_row.addStretch(1)
        box_list_layout.addLayout(region_row)

        empty_row = QHBoxLayout()
        button_empty = ActionButton(
            "Capturar modelo de lista vazia (cabeçalho + 1ª linha)...", variant="secondary"
        )
        button_empty.clicked.connect(self.capture_empty_template)
        self.label_empty_template = QLabel(
            "Modelo calibrado" if self.cfg.get("training_battle_empty_template") else "não calibrado"
        )
        empty_row.addWidget(button_empty)
        empty_row.addWidget(self.label_empty_template)
        empty_row.addWidget(
            InfoIcon(
                "Com a lista VAZIA no jogo, arraste incluindo o título da janela 'Battle' + a "
                "1ª linha (vazia) logo abaixo."
            )
        )
        empty_row.addStretch(1)
        box_list_layout.addLayout(empty_row)

        list_form = QFormLayout()
        self.input_empty_threshold = QLineEdit(
            str(int(float(self.cfg.get("empty_match_threshold", 0.85)) * 100))
        )
        self.input_empty_threshold.setFixedWidth(60)
        list_form.addRow("Confiança mínima do modelo vazio (%) (0 a 100, padrão 85)", self.input_empty_threshold)
        box_list_layout.addLayout(list_form)

        layout.addWidget(box_list)

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
                "Padrão RGB 254,0,0 (vermelho puro do nome em ATAQUE) - o mesmo mecanismo usado no Target."
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

        box_key = QGroupBox("3. Tecla de ataque")
        box_key_layout = QVBoxLayout(box_key)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Tecla de ataque (ex: space)"))
        self.button_attack_key = HotkeyButton(self.cfg.get("attack_key", "space"))
        key_row.addWidget(self.button_attack_key)
        key_row.addWidget(
            InfoIcon(
                "Precisa estar configurada DENTRO do Tibia primeiro (Options > Hotkeys > "
                "Attack) para atacar a criatura selecionada."
            )
        )
        key_row.addStretch(1)
        box_key_layout.addLayout(key_row)

        key_form = QFormLayout()
        self.input_attack_check_delay = QLineEdit(str(self.cfg.get("attack_check_delay", 0.5)))
        self.input_attack_check_delay.setFixedWidth(60)
        key_form.addRow("Delay após apertar (s) (aguarda antes de conferir a cor)", self.input_attack_check_delay)
        box_key_layout.addLayout(key_form)

        layout.addWidget(box_key)

        box_rate = QGroupBox("4. Ritmo")
        rate_form = QFormLayout(box_rate)
        self.input_idle_min = QLineEdit(str(self.cfg.get("idle_delay_min", 2.0)))
        self.input_idle_min.setFixedWidth(60)
        rate_form.addRow("Delay mínimo (alvo sumido) (s) (ex: 2.0)", self.input_idle_min)
        self.input_idle_max = QLineEdit(str(self.cfg.get("idle_delay_max", 4.0)))
        self.input_idle_max.setFixedWidth(60)
        rate_form.addRow("Delay máximo (alvo sumido) (s) (ex: 4.0)", self.input_idle_max)
        self.input_engaged_min = QLineEdit(str(self.cfg.get("engaged_delay_min", 1.0)))
        self.input_engaged_min.setFixedWidth(60)
        rate_form.addRow("Delay mínimo (já atacando) (s) (ex: 1.0)", self.input_engaged_min)
        self.input_engaged_max = QLineEdit(str(self.cfg.get("engaged_delay_max", 2.0)))
        self.input_engaged_max.setFixedWidth(60)
        rate_form.addRow("Delay máximo (já atacando) (s) (ex: 2.0)", self.input_engaged_max)

        layout.addWidget(box_rate)

        box_target = QGroupBox("5. Alvo de treino permanente")
        box_target_layout = QVBoxLayout(box_target)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Nome do monstro de treino (ex: Training Monk)"))
        self.input_creature_name = QLineEdit(self.cfg.get("creature_name", ""))
        self.input_creature_name.setFixedWidth(220)
        name_row.addWidget(self.input_creature_name)
        name_row.addWidget(
            InfoIcon(
                "O nome é lido via OCR na região inteira da Battle List, ignorando maiúsculas "
                "e pequenas falhas de leitura - assim o bot só ataca enquanto o monstro certo "
                "estiver na lista."
            )
        )
        name_row.addStretch(1)
        box_target_layout.addLayout(name_row)

        target_form = QFormLayout()
        self.input_name_threshold = QLineEdit(
            str(int(float(self.cfg.get("name_match_threshold", 0.80)) * 100))
        )
        self.input_name_threshold.setFixedWidth(60)
        target_form.addRow("Similaridade mínima do nome (%) (tolerante a falhas de OCR)", self.input_name_threshold)
        self.input_missing_retries = QLineEdit(str(self.cfg.get("missing_retries", 5)))
        self.input_missing_retries.setFixedWidth(60)
        target_form.addRow("Tentativas antes de pausar (alvo sumido da lista)", self.input_missing_retries)
        self.input_missing_interval = QLineEdit(str(self.cfg.get("missing_retry_interval", 2.0)))
        self.input_missing_interval.setFixedWidth(60)
        target_form.addRow("Intervalo entre tentativas (s) (ex: 2.0)", self.input_missing_interval)
        box_target_layout.addLayout(target_form)

        layout.addWidget(box_target)

        box_spell = QGroupBox("6. Magia de ataque (opcional, treino de magic level)")
        box_spell_layout = QVBoxLayout(box_spell)

        self.check_cast_spell = QCheckBox(
            "Também conjurar magia de ataque enquanto o alvo estiver selecionado"
        )
        self.check_cast_spell.setChecked(bool(self.cfg.get("cast_spell_enabled", False)))
        self.check_cast_spell.stateChanged.connect(self._update_field_states)
        box_spell_layout.addWidget(self.check_cast_spell)

        spell_key_row = QHBoxLayout()
        spell_key_row.addWidget(QLabel("Tecla da magia de ataque (hotkey configurada no jogo)"))
        self.button_spell_hotkey = HotkeyButton(self.cfg.get("spell_hotkey", ""))
        spell_key_row.addWidget(self.button_spell_hotkey)
        spell_key_row.addStretch(1)
        box_spell_layout.addLayout(spell_key_row)

        self.check_check_mana = QCheckBox("Verificar mana")
        self.check_check_mana.setChecked(bool(self.cfg.get("check_mana", True)))
        box_spell_layout.addWidget(self.check_check_mana)

        mana_region_row = QHBoxLayout()
        self.button_pick_mana_region = ActionButton("Região da mana...", variant="secondary")
        self.button_pick_mana_region.clicked.connect(self.pick_mana_region)
        mana_region_row.addWidget(self.button_pick_mana_region)
        self.label_mana_region = QLabel(region_text(self.cfg.get("mana_region")))
        mana_region_row.addWidget(self.label_mana_region)
        mana_region_row.addStretch(1)
        box_spell_layout.addLayout(mana_region_row)

        spell_form = QFormLayout()
        self.input_min_mana = QLineEdit(str(self.cfg.get("min_mana", 300)))
        self.input_min_mana.setFixedWidth(80)
        spell_form.addRow("Mana mínima (pausa a magia abaixo disso)", self.input_min_mana)
        self.input_spell_delay_min = QLineEdit(str(self.cfg.get("spell_delay_min", 1.5)))
        self.input_spell_delay_min.setFixedWidth(60)
        spell_form.addRow("Delay mínimo entre magias (s) (ex: 1.5)", self.input_spell_delay_min)
        self.input_spell_delay_max = QLineEdit(str(self.cfg.get("spell_delay_max", 2.5)))
        self.input_spell_delay_max.setFixedWidth(60)
        spell_form.addRow("Delay máximo entre magias (s) (ex: 2.5)", self.input_spell_delay_max)
        box_spell_layout.addLayout(spell_form)

        self.button_test_ocr_mana = ActionButton("Testar OCR da mana", variant="secondary")
        self.button_test_ocr_mana.clicked.connect(self.test_mana_ocr)
        box_spell_layout.addWidget(self.button_test_ocr_mana)

        layout.addWidget(box_spell)

        box_afk = QGroupBox("7. Anti-AFK-kick")
        box_afk_layout = QVBoxLayout(box_afk)

        afk_row = QHBoxLayout()
        self.check_afk_enabled = QCheckBox("Enviar ação anti-AFK periodicamente")
        self.check_afk_enabled.setChecked(bool(self.cfg.get("anti_afk_enabled", False)))
        afk_row.addWidget(self.check_afk_enabled)
        afk_row.addWidget(
            InfoIcon(
                "Fallback de 'movimento leve' (aperta uma tecla e a oposta em seguida) caso a "
                "tecla de ataque em loop não conte como atividade no seu servidor."
            )
        )
        afk_row.addStretch(1)
        box_afk_layout.addLayout(afk_row)

        afk_form = QFormLayout()
        self.input_afk_interval = QLineEdit(str(self.cfg.get("anti_afk_interval_minutes", 10)))
        self.input_afk_interval.setFixedWidth(60)
        afk_form.addRow("Intervalo (minutos) (ex: 10)", self.input_afk_interval)
        box_afk_layout.addLayout(afk_form)

        afk_key_a_row = QHBoxLayout()
        afk_key_a_row.addWidget(QLabel("Tecla de movimento (ida) (ex: up)"))
        self.button_afk_key_a = HotkeyButton(self.cfg.get("anti_afk_key_a", "up"))
        afk_key_a_row.addWidget(self.button_afk_key_a)
        afk_key_a_row.addStretch(1)
        box_afk_layout.addLayout(afk_key_a_row)

        afk_key_b_row = QHBoxLayout()
        afk_key_b_row.addWidget(QLabel("Tecla de movimento (volta) (ex: down)"))
        self.button_afk_key_b = HotkeyButton(self.cfg.get("anti_afk_key_b", "down"))
        afk_key_b_row.addWidget(self.button_afk_key_b)
        afk_key_b_row.addStretch(1)
        box_afk_layout.addLayout(afk_key_b_row)

        layout.addWidget(box_afk)

        warning_label = QLabel(
            "Aviso: esta função depende de leitura visual (template/cor/OCR) da Battle List. "
            "Mudar o tamanho da janela do jogo, o zoom ou a skin da Battle List depois de "
            "calibrar pode quebrar a detecção - recalibre se isso acontecer."
        )
        warning_label.setStyleSheet("color: #a33;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        layout.addStretch(1)

        actions_bar = QHBoxLayout()
        actions_bar.addStretch(1)
        button_save = ActionButton("Salvar config", variant="primary")
        button_save.clicked.connect(self.save_config)
        button_close = ActionButton("Fechar", variant="secondary")
        button_close.clicked.connect(self.config_dialog.hide)
        actions_bar.addWidget(button_save)
        actions_bar.addWidget(button_close)
        outer.addLayout(actions_bar)

    def _update_field_states(self) -> None:
        enabled = bool(self.check_cast_spell.isChecked())
        for widget in (
            self.button_spell_hotkey,
            self.check_check_mana,
            self.button_pick_mana_region,
            self.input_min_mana,
            self.input_spell_delay_min,
            self.input_spell_delay_max,
            self.button_test_ocr_mana,
        ):
            widget.setEnabled(enabled)

    def open_config_dialog(self) -> None:
        self.config_dialog.show()
        self.config_dialog.raise_()
        self.config_dialog.activateWindow()

    def pick_battle_list_region(self) -> None:
        region = self.controller.select_region(
            "Arraste cobrindo toda a área visível da Battle List (cabeçalho + linhas)  -  ESC cancela"
        )
        if not region:
            return
        self.cfg["battle_list_region"] = region
        self.label_region.setText(region_text(region))
        self.battle_overlay.configure_region(region)
        self.controller.config_store.save()
        self.controller.log(f"Região da Battle List definida: {region_text(region)}", source="training")

    def capture_empty_template(self) -> None:
        region = self.controller.select_region(
            "Com a lista VAZIA, selecione o cabeçalho 'Battle' + a 1a linha (vazia)  -  ESC cancela"
        )
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, "training_battle_empty.png")
        save_image(path, frame)
        self.cfg["training_battle_empty_template"] = path
        self.label_empty_template.setText(f"Modelo salvo ({region[2]}x{region[3]} px)")
        self.controller.config_store.save()
        self.controller.log(f"Modelo de lista vazia salvo em {path}", source="training")

    def pick_mana_region(self) -> None:
        region = self.controller.select_region("Selecione o número de MANA na barra de status  -  ESC cancela")
        if not region:
            return
        self.cfg["mana_region"] = region
        self.label_mana_region.setText(region_text(region))
        self.controller.config_store.save()
        self.controller.log(f"Região de mana definida: {region_text(region)}", source="training")

    def test_mana_ocr(self) -> None:
        self.save_config()
        configure_tesseract(on_progress=lambda message: self.controller.log(message, source="training"))
        region = self.cfg.get("mana_region")
        if not is_valid_region(region):
            QMessageBox.warning(self.main_window, "Training", "Região de mana não configurada.")
            return
        try:
            with ScreenCapture() as cap:
                value = read_number(cap.grab(region))
        except OCRUnavailable as exc:
            QMessageBox.critical(self.main_window, "Training", str(exc))
            return
        message = f"OCR mana: {value if value is not None else 'não reconhecido'}"
        self.controller.log(message, source="training")
        QMessageBox.information(self.main_window, "Training", message)

    def worker_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(self.controller.build_worker_extras())
        return cfg

    def test_detection(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TrainingWorker(dict(cfg), self.controller.events)
            worker.setup()
        except Exception as exc:
            QMessageBox.critical(self.main_window, "Training", f"Falha ao preparar detecção: {exc}")
            return
        try:
            score = worker.battle_list_empty_score()
            vazia = worker.is_battle_list_empty()
            presente = worker.creature_present() if not vazia else False
            attacking = worker.is_attacking() if presente else False
        except Exception as exc:
            worker.teardown()
            QMessageBox.critical(self.main_window, "Training", f"Falha na detecção: {exc}")
            return
        worker.teardown()
        score_text = f"{score * 100:.1f}%" if score is not None else "modelo maior que a região"
        message = (
            f"Battle List vazia: {'sim' if vazia else 'não'} (confiança: {score_text}, mínimo: "
            f"{worker.empty_threshold * 100:.0f}%)\n"
            f"Alvo de treino '{worker.creature_name}' presente: {'sim' if presente else 'não'}\n"
            f"Cor de ataque detectada: {'sim' if attacking else 'não'}"
        )
        self.controller.log(message.replace("\n", " | "), source="training")
        QMessageBox.information(self.main_window, "Training - Testar detecção", message)

    def test_attack_key(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TrainingWorker(dict(cfg), self.controller.events)
            worker.setup()
        except Exception as exc:
            QMessageBox.critical(self.main_window, "Training", f"Falha ao preparar teste: {exc}")
            return
        try:
            dry_run = bool(self.controller.dry_run_enabled)
            if not dry_run and QMessageBox.question(
                self.main_window,
                "Training",
                f"Modo REAL: isso vai apertar a tecla '{worker.attack_key}' de verdade. Continuar?",
            ) != QMessageBox.Yes:
                return
            worker.press_attack_key(dry_run=dry_run)
        except Exception as exc:
            QMessageBox.critical(self.main_window, "Training", f"Falha no teste da tecla de ataque: {exc}")
            return
        finally:
            worker.teardown()
        self.controller.log(f"Teste da tecla de ataque concluído ('{worker.attack_key}').", source="training")
        QMessageBox.information(
            self.main_window, "Training", f"Tecla de ataque testada ('{worker.attack_key}' - ver log)."
        )

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
        coverage_pct = max(0, min(100, parse_int(self.input_empty_threshold.text(), 85)))
        self.cfg["empty_match_threshold"] = coverage_pct / 100

        self.cfg["creature_name"] = self.input_creature_name.text().strip()
        threshold_pct = max(0, min(100, parse_int(self.input_name_threshold.text(), 80)))
        self.cfg["name_match_threshold"] = threshold_pct / 100
        self.cfg["missing_retries"] = max(1, parse_int(self.input_missing_retries.text(), 5))
        self.cfg["missing_retry_interval"] = parse_float(self.input_missing_interval.text(), 2.0)

        self.cfg["cast_spell_enabled"] = bool(self.check_cast_spell.isChecked())
        self.cfg["spell_hotkey"] = (self.button_spell_hotkey.value() or "").strip().lower()
        self.cfg["check_mana"] = bool(self.check_check_mana.isChecked())
        self.cfg["min_mana"] = parse_int(self.input_min_mana.text(), 300)
        self.cfg["spell_delay_min"] = parse_float(self.input_spell_delay_min.text(), 1.5)
        self.cfg["spell_delay_max"] = parse_float(self.input_spell_delay_max.text(), 2.5)

        self.cfg["anti_afk_enabled"] = bool(self.check_afk_enabled.isChecked())
        self.cfg["anti_afk_interval_minutes"] = parse_float(self.input_afk_interval.text(), 10.0)
        self.cfg["anti_afk_key_a"] = (self.button_afk_key_a.value() or "up").strip().lower()
        self.cfg["anti_afk_key_b"] = (self.button_afk_key_b.value() or "down").strip().lower()

        self.controller.config_store.save()

    def start(self) -> None:
        self.save_config()
        if not is_valid_region(self.cfg.get("battle_list_region")):
            QMessageBox.warning(self.main_window, "Training", "Selecione a região da Battle List primeiro.")
            return
        if not self.cfg.get("training_battle_empty_template"):
            QMessageBox.warning(self.main_window, "Training", "Capture o modelo de lista vazia primeiro.")
            return
        if not self.cfg.get("creature_name"):
            QMessageBox.warning(self.main_window, "Training", "Informe o nome do monstro de treino primeiro.")
            return
        self.controller.start_worker(self.worker_key, TrainingWorker, self.worker_config())

    def toggle_pause(self) -> None:
        self.controller.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.controller.stop_worker(self.worker_key)

    def close_overlays(self) -> None:
        self.battle_overlay.hide()

    def on_state(self, state: str) -> None:
        self.card.set_state(state)
        self._last_state = state
        self._apply_overlay_visibility()

    def _apply_overlay_visibility(self) -> None:
        running = self._last_state in ("running", "paused")
        if running and self.cfg.get("training_battle_empty_template") and self.controller.region_overlays_enabled:
            self.battle_overlay.show()
        else:
            self.battle_overlay.hide()

    def on_counter(self, value) -> None:
        self.card.set_stat("counter", str(value))

    def on_elapsed(self, value) -> None:
        self.card.set_stat("elapsed", str(value))

    def _on_module_event(self, source: str, kind: str, payload) -> None:
        if source != "training":
            return
        if kind == "state":
            self.on_state(payload)
        elif kind == "counter":
            self.on_counter(payload)
        elif kind == "elapsed":
            self.on_elapsed(payload)
