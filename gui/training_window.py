"""Aba Training: mantem o personagem engajado no mesmo alvo de treino
(monstro parado na Battle List ou boneco de treino fixo), sem trocar de alvo.

Reaproveita a mesma cara/convencao do Target (secoes numeradas, calibracao
que salva na hora) e do RuneMaker (seletor de modo que habilita/desabilita
os campos relevantes de cada um, em vez de duas telas separadas).
"""

from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import messagebox, ttk

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.rune_maker import OCRUnavailable, configure_tesseract, read_number
from functions.target import crop_offset, row_is_empty, sample_name_text_color
from functions.training import TrainingWorker
from gui.target_window import ATTACK_MODE_LABELS, ATTACK_MODE_VALUES, BATTLE_LIST_CALIBRATION_KEYS, offset_text
from gui.widgets import ScrollableFrame, add_field, add_hotkey_field, parse_float, parse_int, region_text

MODE_LABELS = {
    "battle_list": "Monstro de treino (Battle List)",
    "dummy": "Boneco de treino (objeto fixo)",
}
MODE_VALUES = {label: value for value, label in MODE_LABELS.items()}


class TrainingWindow(ttk.Frame):
    worker_key = "training"

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.cfg = app.config_store.section("training")

        self.var_mode = tk.StringVar(
            value=MODE_LABELS.get(self.cfg.get("mode", "battle_list"), MODE_LABELS["battle_list"])
        )

        # Modo A: Battle List --------------------------------------------------
        self.var_region = tk.StringVar(value=region_text(self.cfg.get("battle_list_region")))
        self.var_row_height = tk.StringVar(value=str(self.cfg.get("row_height") or "nao calibrado"))
        self.var_empty_template = tk.StringVar(
            value="Template calibrado" if self.cfg.get("row_empty_template") else "nao calibrado"
        )
        self.var_empty_threshold = tk.StringVar(
            value=str(int(float(self.cfg.get("empty_match_threshold", 0.90)) * 100))
        )
        self.var_name_offset = tk.StringVar(value=offset_text(self.cfg.get("name_crop_offset")))
        self.var_name_color_status = tk.StringVar(value=self._name_color_status_text())
        self.var_attack_mode = tk.StringVar(
            value=ATTACK_MODE_LABELS.get(self.cfg.get("attack_mode", "single_click"), "Clique simples")
        )
        self.var_menu_offset = tk.StringVar(value=offset_text(self.cfg.get("context_menu_offset")))
        self.var_creature_name = tk.StringVar(value=self.cfg.get("creature_name", ""))
        self.var_name_threshold = tk.StringVar(
            value=str(int(float(self.cfg.get("name_match_threshold", 0.80)) * 100))
        )
        self.var_missing_retries = tk.StringVar(value=str(self.cfg.get("missing_retries", 5)))
        self.var_missing_retry_interval = tk.StringVar(value=str(self.cfg.get("missing_retry_interval", 2.0)))
        self.var_delay_min = tk.StringVar(value=str(self.cfg.get("delay_min", 0.6)))
        self.var_delay_max = tk.StringVar(value=str(self.cfg.get("delay_max", 1.4)))
        self.var_jitter = tk.StringVar(value=str(self.cfg.get("click_jitter", 2)))

        self.var_cast_spell = tk.BooleanVar(value=bool(self.cfg.get("cast_spell_enabled", False)))
        self.var_spell_hotkey = tk.StringVar(value=self.cfg.get("spell_hotkey", ""))
        self.var_check_mana = tk.BooleanVar(value=bool(self.cfg.get("check_mana", True)))
        self.var_mana_region = tk.StringVar(value=region_text(self.cfg.get("mana_region")))
        self.var_min_mana = tk.StringVar(value=str(self.cfg.get("min_mana", 300)))
        self.var_spell_delay_min = tk.StringVar(value=str(self.cfg.get("spell_delay_min", 1.5)))
        self.var_spell_delay_max = tk.StringVar(value=str(self.cfg.get("spell_delay_max", 2.5)))

        # Modo B: boneco de treino ----------------------------------------------
        self.var_dummy_position = tk.StringVar(value=region_text(self.cfg.get("dummy_position")))
        self.var_weapon_region = tk.StringVar(value=region_text(self.cfg.get("weapon_slot_region")))
        self.var_weapon_template = tk.StringVar(
            value="Template calibrado" if self.cfg.get("weapon_equipped_template") else "nao calibrado"
        )
        self.var_weapon_threshold = tk.StringVar(
            value=str(int(float(self.cfg.get("weapon_match_threshold", 0.90)) * 100))
        )
        self.var_click_interval_min = tk.StringVar(value=str(self.cfg.get("click_interval_min", 2.0)))
        self.var_click_interval_max = tk.StringVar(value=str(self.cfg.get("click_interval_max", 4.0)))

        # Comum: anti-AFK e pausas -----------------------------------------------
        self.var_afk_enabled = tk.BooleanVar(value=bool(self.cfg.get("anti_afk_enabled", False)))
        self.var_afk_interval = tk.StringVar(value=str(self.cfg.get("anti_afk_interval_minutes", 10)))
        self.var_afk_key_a = tk.StringVar(value=self.cfg.get("anti_afk_key_a", "up"))
        self.var_afk_key_b = tk.StringVar(value=self.cfg.get("anti_afk_key_b", "down"))

        self.var_break_enabled = tk.BooleanVar(value=bool(self.cfg.get("break_enabled", True)))
        self.var_break_interval_min = tk.StringVar(value=str(self.cfg.get("break_interval_min", 30)))
        self.var_break_interval_max = tk.StringVar(value=str(self.cfg.get("break_interval_max", 300)))
        self.var_break_duration_min = tk.StringVar(value=str(self.cfg.get("break_duration_min", 10)))
        self.var_break_duration_max = tk.StringVar(value=str(self.cfg.get("break_duration_max", 120)))

        self.var_dry_run = tk.BooleanVar(value=True)
        self.var_status = tk.StringVar(value="parado")
        self.var_elapsed = tk.StringVar(value="00:00:00")
        self.var_counter = tk.StringVar(value="0")
        self.var_counter_label = tk.StringVar(value="Selecoes reforcadas:")

        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        self.body = scroll.body
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._build()

        # Dialogo de configuracao (secoes 1 a 8) - construido ja aqui (nao so
        # no primeiro clique em "Configurar...") pra que os widgets ja
        # existam quando `_on_attack_mode_change`/`_on_mode_change` rodam
        # logo abaixo (ver `open_config_dialog`).
        self._config_dialog = tk.Toplevel(self)
        self._config_dialog.title("Configurar - Training")
        self._config_dialog.geometry("640x600")
        self._config_dialog.transient(self.winfo_toplevel())
        self._config_dialog.protocol("WM_DELETE_WINDOW", self._hide_config_dialog)
        config_scroll = ScrollableFrame(self._config_dialog)
        config_scroll.pack(fill="both", expand=True)
        self._build_config_dialog(config_scroll.body)
        self._config_dialog.withdraw()

        self._on_attack_mode_change()
        self._on_mode_change()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        body = self.body

        # Execucao ------------------------------------------------------------
        box_run = ttk.LabelFrame(body, text="1. Execucao")
        box_run.grid(row=0, column=0, sticky="ew", pady=4)

        actions = ttk.Frame(box_run)
        actions.grid(row=0, column=0, columnspan=4, sticky="w", pady=(2, 6))
        ttk.Checkbutton(
            actions, text="Modo teste (dry-run: so loga, nao clica)", variable=self.var_dry_run
        ).pack(side="left", padx=4)
        ttk.Button(actions, text="Testar deteccao", command=self.test_detection).pack(side="left", padx=8)

        self.btn_start = ttk.Button(box_run, text="Iniciar", command=self.start)
        self.btn_start.grid(row=1, column=0, padx=4, pady=6)
        self.btn_pause = ttk.Button(box_run, text="Pausar/Retomar", command=self.toggle_pause, state="disabled")
        self.btn_pause.grid(row=1, column=1, padx=4)
        self.btn_stop = ttk.Button(box_run, text="Parar", command=self.stop, state="disabled")
        self.btn_stop.grid(row=1, column=2, padx=4)
        self.btn_configure = ttk.Button(box_run, text="Configurar...", command=self.open_config_dialog)
        self.btn_configure.grid(row=1, column=3, padx=12)

        ttk.Label(box_run, text="Status:").grid(row=2, column=0, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_status, font=("Segoe UI", 9, "bold")).grid(
            row=2, column=1, sticky="w"
        )
        ttk.Label(box_run, text="Tempo total treinando:").grid(row=2, column=2, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_elapsed, font=("Segoe UI", 9, "bold")).grid(
            row=2, column=3, sticky="w"
        )
        ttk.Label(box_run, textvariable=self.var_counter_label).grid(row=3, column=2, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_counter, font=("Segoe UI", 9, "bold")).grid(
            row=3, column=3, sticky="w"
        )

        body.columnconfigure(0, weight=1)

    def open_config_dialog(self) -> None:
        self._config_dialog.deiconify()
        self._config_dialog.lift()
        self._config_dialog.focus_force()

    def _hide_config_dialog(self) -> None:
        self._config_dialog.withdraw()

    # ------------------------------------------------------- dialogo de config
    def _build_config_dialog(self, parent) -> None:
        # Modo ------------------------------------------------------------------
        box_mode = ttk.LabelFrame(parent, text="1. Modo")
        box_mode.grid(row=0, column=0, sticky="ew", pady=4)
        for i, label in enumerate(MODE_LABELS.values()):
            ttk.Radiobutton(
                box_mode, text=label, value=label, variable=self.var_mode, command=self._on_mode_change
            ).grid(row=0, column=i, sticky="w", padx=4, pady=3)

        # Modo A: Battle List -----------------------------------------------------
        self.box_battle_list = ttk.LabelFrame(parent, text="2. Battle List (Modo A)")
        self.box_battle_list.grid(row=1, column=0, sticky="ew", pady=4)
        self.btn_calibrate_all = ttk.Button(
            self.box_battle_list, text="Calibracao guiada (todos os passos abaixo, em sequencia)...",
            command=self.calibrate_all,
        )
        self.btn_calibrate_all.grid(row=0, column=0, columnspan=2, padx=4, pady=(6, 4), sticky="w")
        self.btn_import_calibration = ttk.Button(
            self.box_battle_list, text="Importar calibracao do Target...",
            command=lambda: self.import_calibration_from("target"),
        )
        self.btn_import_calibration.grid(row=1, column=0, columnspan=2, padx=4, pady=(0, 10), sticky="w")

        self.btn_pick_region = ttk.Button(
            self.box_battle_list, text="Selecionar regiao da Battle List...", command=self.pick_battle_list_region
        )
        self.btn_pick_region.grid(row=2, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(self.box_battle_list, textvariable=self.var_region).grid(row=2, column=1, sticky="w")

        self.btn_calibrate_row = ttk.Button(
            self.box_battle_list, text="Calibrar altura de linha...", command=self.calibrate_row_height
        )
        self.btn_calibrate_row.grid(row=3, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(self.box_battle_list, textvariable=self.var_row_height).grid(row=3, column=1, sticky="w")

        self.btn_capture_empty = ttk.Button(
            self.box_battle_list, text="Capturar linha vazia (template)...", command=self.capture_row_empty_template
        )
        self.btn_capture_empty.grid(row=4, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(self.box_battle_list, textvariable=self.var_empty_template).grid(row=4, column=1, sticky="w")

        self.entry_empty_threshold = add_field(
            self.box_battle_list, 5, "Cobertura minima do slot vazio (%)", self.var_empty_threshold, 8, "0 a 100 (padrao 90)"
        )

        self.btn_pick_name = ttk.Button(
            self.box_battle_list, text="Selecionar faixa de texto do nome...", command=self.pick_name_crop
        )
        self.btn_pick_name.grid(row=6, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(self.box_battle_list, textvariable=self.var_name_offset).grid(row=6, column=1, sticky="w")

        self.btn_calibrate_attack_border = ttk.Button(
            self.box_battle_list, text="Calibrar ATAQUE normal (vermelho)...",
            command=lambda: self._calibrate_name_color("attack", "normal"),
        )
        self.btn_calibrate_attack_border.grid(row=7, column=0, padx=4, pady=4, sticky="w")
        self.btn_calibrate_attack_hover = ttk.Button(
            self.box_battle_list, text="Calibrar ATAQUE hover (mouse em cima)...",
            command=lambda: self._calibrate_name_color("attack", "hover"),
        )
        self.btn_calibrate_attack_hover.grid(row=7, column=1, padx=4, pady=4, sticky="w")
        self.btn_calibrate_follow_border = ttk.Button(
            self.box_battle_list, text="Calibrar FOLLOW normal (verde)...",
            command=lambda: self._calibrate_name_color("follow", "normal"),
        )
        self.btn_calibrate_follow_border.grid(row=8, column=0, padx=4, pady=4, sticky="w")
        self.btn_calibrate_follow_hover = ttk.Button(
            self.box_battle_list, text="Calibrar FOLLOW hover (mouse em cima)...",
            command=lambda: self._calibrate_name_color("follow", "hover"),
        )
        self.btn_calibrate_follow_hover.grid(row=8, column=1, padx=4, pady=4, sticky="w")
        ttk.Label(self.box_battle_list, textvariable=self.var_name_color_status).grid(
            row=9, column=0, columnspan=2, sticky="w", padx=4
        )
        ttk.Label(
            self.box_battle_list,
            text="'Hover' e opcional - so calibre se o bot ficar re-clicando um alvo que ja "
            "esta atacando (mouse em cima da linha as vezes deixa a cor mais clara).",
            foreground="#666",
            wraplength=600,
            justify="left",
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=4)

        # Forma de selecao --------------------------------------------------------
        self.box_select = ttk.LabelFrame(parent, text="3. Forma de selecao do alvo (Modo A)")
        self.box_select.grid(row=2, column=0, sticky="ew", pady=4)
        self.radios_attack_mode = []
        for i, label in enumerate(ATTACK_MODE_LABELS.values()):
            radio = ttk.Radiobutton(
                self.box_select, text=label, value=label, variable=self.var_attack_mode,
                command=self._on_attack_mode_change,
            )
            radio.grid(row=0, column=i, sticky="w", padx=4, pady=3)
            self.radios_attack_mode.append(radio)

        self.btn_calibrate_menu = ttk.Button(
            self.box_select, text="Calibrar deslocamento do menu de contexto...", command=self.calibrate_context_menu
        )
        self.btn_calibrate_menu.grid(row=1, column=0, columnspan=2, padx=4, pady=6, sticky="w")
        ttk.Label(self.box_select, textvariable=self.var_menu_offset).grid(row=1, column=2, sticky="w")

        # Alvo de treino ------------------------------------------------------
        self.box_target = ttk.LabelFrame(parent, text="4. Alvo de treino permanente (Modo A)")
        self.box_target.grid(row=3, column=0, sticky="ew", pady=4)
        self.entry_creature_name = add_field(
            self.box_target, 0, "Nome do monstro de treino", self.var_creature_name, 24, "ex: Training Monk"
        )
        self.entry_name_threshold = add_field(
            self.box_target, 1, "Similaridade minima do nome (%)", self.var_name_threshold, 8, "tolerante a falhas de OCR"
        )
        self.entry_missing_retries = add_field(
            self.box_target, 2, "Tentativas antes de pausar", self.var_missing_retries, 8, "alvo sumido da lista"
        )
        self.entry_missing_interval = add_field(
            self.box_target, 3, "Intervalo entre tentativas (s)", self.var_missing_retry_interval, 8, "ex: 2.0"
        )
        self.entry_delay_min = add_field(self.box_target, 4, "Delay minimo por ciclo (s)", self.var_delay_min, 8, "ex: 0.6")
        self.entry_delay_max = add_field(self.box_target, 5, "Delay maximo por ciclo (s)", self.var_delay_max, 8, "ex: 1.4")
        self.entry_jitter = add_field(self.box_target, 6, "Variacao do clique (px)", self.var_jitter, 8, "+/- pixels")

        # Magia de ataque (opcional) -------------------------------------------
        self.box_spell = ttk.LabelFrame(parent, text="5. Magia de ataque (opcional, treino de magic level - Modo A)")
        self.box_spell.grid(row=4, column=0, sticky="ew", pady=4)
        self.chk_cast_spell = ttk.Checkbutton(
            self.box_spell, text="Tambem conjurar magia de ataque enquanto o alvo estiver selecionado",
            variable=self.var_cast_spell, command=self._update_field_states,
        )
        self.chk_cast_spell.grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=3)
        self.entry_spell_hotkey = add_hotkey_field(
            self.box_spell, 1, "Tecla da magia de ataque", self.var_spell_hotkey, 10, "hotkey configurada no jogo"
        )
        self.chk_check_mana = ttk.Checkbutton(self.box_spell, text="Verificar mana", variable=self.var_check_mana)
        self.chk_check_mana.grid(row=2, column=0, sticky="w", padx=4, pady=3)
        self.btn_pick_mana_region = ttk.Button(
            self.box_spell, text="Regiao da mana...", command=self.pick_mana_region
        )
        self.btn_pick_mana_region.grid(row=2, column=1, padx=4)
        ttk.Label(self.box_spell, textvariable=self.var_mana_region).grid(row=2, column=2, sticky="w", padx=4)
        self.entry_min_mana = add_field(self.box_spell, 3, "Mana minima", self.var_min_mana, 8, "pausa a magia abaixo disso")
        self.entry_spell_delay_min = add_field(
            self.box_spell, 4, "Delay minimo entre magias (s)", self.var_spell_delay_min, 8, "ex: 1.5"
        )
        self.entry_spell_delay_max = add_field(
            self.box_spell, 5, "Delay maximo entre magias (s)", self.var_spell_delay_max, 8, "ex: 2.5"
        )
        self.btn_test_ocr_mana = ttk.Button(self.box_spell, text="Testar OCR da mana", command=self.test_mana_ocr)
        self.btn_test_ocr_mana.grid(row=6, column=0, padx=4, pady=(4, 6), sticky="w")

        # Modo B: boneco de treino -------------------------------------------
        self.box_dummy = ttk.LabelFrame(parent, text="6. Boneco de treino / Exercise Dummy (Modo B)")
        self.box_dummy.grid(row=5, column=0, sticky="ew", pady=4)
        self.btn_pick_dummy = ttk.Button(
            self.box_dummy, text="Selecionar posicao do boneco na tela...", command=self.pick_dummy_position
        )
        self.btn_pick_dummy.grid(row=0, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(self.box_dummy, textvariable=self.var_dummy_position).grid(row=0, column=1, sticky="w")

        self.btn_capture_weapon = ttk.Button(
            self.box_dummy, text="Selecionar slot da arma de treino...", command=self.capture_weapon_template
        )
        self.btn_capture_weapon.grid(row=1, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(self.box_dummy, textvariable=self.var_weapon_region).grid(row=1, column=1, sticky="w")
        ttk.Label(self.box_dummy, textvariable=self.var_weapon_template).grid(row=2, column=0, columnspan=2, sticky="w", padx=4)

        self.entry_weapon_threshold = add_field(
            self.box_dummy, 3, "Cobertura minima do template (%)", self.var_weapon_threshold, 8, "0 a 100 (padrao 90)"
        )
        self.entry_click_interval_min = add_field(
            self.box_dummy, 4, "Intervalo minimo de re-clique (s)", self.var_click_interval_min, 8, "ex: 2.0"
        )
        self.entry_click_interval_max = add_field(
            self.box_dummy, 5, "Intervalo maximo de re-clique (s)", self.var_click_interval_max, 8, "ex: 4.0"
        )
        ttk.Label(
            self.box_dummy,
            text="Alguns clients so precisam de um clique inicial (combate se mantem sozinho); "
            "outros pedem reforco periodico - ajuste o intervalo conforme necessario.",
            foreground="#666",
            wraplength=680,
            justify="left",
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4))

        # Anti-AFK ------------------------------------------------------------
        box_afk = ttk.LabelFrame(parent, text="7. Anti-AFK-kick")
        box_afk.grid(row=6, column=0, sticky="ew", pady=4)
        ttk.Checkbutton(
            box_afk, text="Enviar acao anti-AFK periodicamente", variable=self.var_afk_enabled
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=3)
        add_field(box_afk, 1, "Intervalo (minutos)", self.var_afk_interval, 8, "ex: 10")
        add_hotkey_field(box_afk, 2, "Tecla de movimento (ida)", self.var_afk_key_a, 10, "ex: up")
        add_hotkey_field(box_afk, 3, "Tecla de movimento (volta)", self.var_afk_key_b, 10, "ex: down")
        ttk.Label(
            box_afk,
            text="Fallback de 'movimento leve' (aperta uma tecla e a oposta em seguida) caso o "
            "clique/tecla de ataque em loop nao conte como atividade no seu servidor.",
            foreground="#666",
            wraplength=680,
            justify="left",
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4))

        # Pausas periodicas -----------------------------------------------------
        box_break = ttk.LabelFrame(parent, text="8. Pausas periodicas (descanso)")
        box_break.grid(row=7, column=0, sticky="ew", pady=4)
        ttk.Checkbutton(
            box_break, text="Ativar pausas periodicas", variable=self.var_break_enabled
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=3)
        add_field(box_break, 1, "Treino no minimo (s)", self.var_break_interval_min, 8, "antes de considerar pausa")
        add_field(box_break, 2, "Treino no maximo (s)", self.var_break_interval_max, 8, "ex: 300 = ate 5 min")
        add_field(box_break, 3, "Pausa minima (s)", self.var_break_duration_min, 8, "duracao minima do descanso")
        add_field(box_break, 4, "Pausa maxima (s)", self.var_break_duration_max, 8, "ex: 120 = ate 2 min")
        ttk.Label(
            box_break,
            text="Treino automatizado prolongado (horas seguidas, sem pausa humana) e um dos "
            "padroes mais visados por deteccao de bot - manter as pausas ativas e recomendado.",
            foreground="#a33",
            wraplength=680,
            justify="left",
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4))

        ttk.Label(
            parent,
            text="Aviso: esta funcao depende de leitura visual (OCR/template) e/ou de coordenadas "
            "fixas de tela. Mudar o tamanho da janela do jogo, o zoom, a skin da Battle List ou a "
            "posicao do personagem/boneco depois de calibrar pode quebrar a deteccao - recalibre "
            "se isso acontecer.",
            foreground="#a33",
            wraplength=700,
            justify="left",
        ).grid(row=8, column=0, sticky="w", pady=(4, 0))

        # Salvar / Fechar -------------------------------------------------------
        actions_bar = ttk.Frame(parent)
        actions_bar.grid(row=9, column=0, sticky="e", pady=(8, 4))
        ttk.Button(actions_bar, text="Salvar config", command=self.save_config).pack(side="left", padx=4)
        ttk.Button(actions_bar, text="Fechar", command=self._hide_config_dialog).pack(side="left", padx=4)

        parent.columnconfigure(0, weight=1)

    # ------------------------------------------------------------ modo/estado
    def _on_mode_change(self) -> None:
        self._update_field_states()

    def _update_field_states(self) -> None:
        is_dummy = MODE_VALUES.get(self.var_mode.get()) == "dummy"
        battle_list_state = "disabled" if is_dummy else "normal"
        dummy_state = "normal" if is_dummy else "disabled"

        for widget in (
            self.btn_calibrate_all, self.btn_import_calibration,
            self.btn_pick_region, self.btn_calibrate_row, self.btn_capture_empty, self.entry_empty_threshold,
            self.btn_pick_name, self.btn_calibrate_attack_border, self.btn_calibrate_attack_hover,
            self.btn_calibrate_follow_border, self.btn_calibrate_follow_hover,
            self.btn_calibrate_menu, self.entry_creature_name, self.entry_name_threshold,
            self.entry_missing_retries, self.entry_missing_interval, self.entry_delay_min, self.entry_delay_max,
            self.entry_jitter, self.chk_cast_spell,
        ):
            widget.configure(state=battle_list_state)
        for radio in self.radios_attack_mode:
            radio.configure(state=battle_list_state)

        cast_spell_state = "normal" if (not is_dummy and self.var_cast_spell.get()) else "disabled"
        for widget in (
            self.entry_spell_hotkey, self.chk_check_mana, self.btn_pick_mana_region, self.entry_min_mana,
            self.entry_spell_delay_min, self.entry_spell_delay_max, self.btn_test_ocr_mana,
        ):
            widget.configure(state=cast_spell_state)

        for widget in (
            self.btn_pick_dummy, self.btn_capture_weapon, self.entry_weapon_threshold,
            self.entry_click_interval_min, self.entry_click_interval_max,
        ):
            widget.configure(state=dummy_state)

        if not is_dummy:
            self._on_attack_mode_change()
        self.var_counter_label.set("Cliques de reforco no boneco:" if is_dummy else "Selecoes reforcadas:")

    def _on_attack_mode_change(self) -> None:
        is_dummy = MODE_VALUES.get(self.var_mode.get()) == "dummy"
        is_menu = ATTACK_MODE_VALUES.get(self.var_attack_mode.get()) == "context_menu"
        self.btn_calibrate_menu.configure(state="normal" if (is_menu and not is_dummy) else "disabled")

    # ------------------------------------------------------------ calibracao
    def _relative_row_offset(self, region) -> list[int] | None:
        """Mesma logica de `TargetWindow._relative_row_offset` (ver
        gui/target_window.py) - converte uma regiao ABSOLUTA no offset
        relativo ao topo-esquerda da linha em que ela caiu."""
        battle_region = self.cfg.get("battle_list_region")
        row_height = self.cfg.get("row_height")
        if not is_valid_region(battle_region) or not row_height:
            messagebox.showwarning("Training", "Calibre a regiao da Battle List e a altura de linha primeiro.")
            return None
        bx, by, _bw, _bh = battle_region
        rx, ry, rw, rh = region
        row_index = max(0, int((ry - by) // row_height))
        row_top = by + row_index * row_height
        return [rx - bx, ry - row_top, rw, rh]

    def import_calibration_from(self, source_key: str) -> None:
        """Copia a calibracao de Battle List (regiao, altura, template de
        linha vazia, faixa/cores do nome, forma de ataque) de outra aba com
        o mesmo formato de config (`BATTLE_LIST_CALIBRATION_KEYS`, ver
        gui/target_window.py) - evita recalibrar tudo de novo quando as
        duas abas leem a MESMA Battle List na tela. So copia campos que a
        origem ja tem preenchidos."""
        source_cfg = self.app.config_store.section(source_key)
        imported = 0
        for key in BATTLE_LIST_CALIBRATION_KEYS:
            value = source_cfg.get(key)
            if value not in (None, "", [], {}):
                self.cfg[key] = copy.deepcopy(value)
                imported += 1
        if imported == 0:
            messagebox.showwarning("Training", f"A aba '{source_key}' ainda nao tem nada calibrado.")
            return
        self._refresh_calibration_vars()
        self.app.config_store.save()
        self.log(f"Calibracao importada de '{source_key}' ({imported} campo(s)).")
        messagebox.showinfo(
            "Training", f"Calibracao importada de '{source_key}'! Confira com 'Testar deteccao'."
        )

    def _refresh_calibration_vars(self) -> None:
        """Atualiza os StringVars da tela com os valores atuais de `self.cfg`
        - usado depois de uma importacao (os campos mudam sem passar pelos
        metodos de calibracao normais, que ja atualizam a var na hora)."""
        self.var_region.set(region_text(self.cfg.get("battle_list_region")))
        row_height = self.cfg.get("row_height")
        self.var_row_height.set(f"{row_height}px" if row_height else "nao calibrado")
        self.var_empty_template.set("Template calibrado" if self.cfg.get("row_empty_template") else "nao calibrado")
        self.var_empty_threshold.set(str(int(float(self.cfg.get("empty_match_threshold", 0.90)) * 100)))
        self.var_name_offset.set(offset_text(self.cfg.get("name_crop_offset")))
        self.var_name_color_status.set(self._name_color_status_text())
        self.var_attack_mode.set(
            ATTACK_MODE_LABELS.get(self.cfg.get("attack_mode", "single_click"), "Clique simples")
        )
        self.var_menu_offset.set(offset_text(self.cfg.get("context_menu_offset")))
        self._on_attack_mode_change()

    def calibrate_all(self) -> None:
        """Encadeia os 4 passos de calibracao BLOQUEANTES do Modo A em
        sequencia (regiao, altura de linha, linha vazia, nome), reaproveitando
        exatamente os mesmos metodos dos botoes individuais - so pra nao
        precisar caçar cada botao na ordem certa toda vez que a regiao ou a
        altura de linha mudam (o que invalida tudo que depende delas).

        A cor do nome (attack/follow) fica de fora deste encadeamento de
        proposito - a captura dela e assincrona (espera o usuario posicionar
        o mouse) e depende do jogo estar naquele estado especifico bem
        naquele momento, nao encaixa numa sequencia rigida."""
        messagebox.showinfo(
            "Training",
            "Calibracao guiada: 4 passos em sequencia (regiao, altura de linha, "
            "linha vazia, nome). Clique OK pra comecar o passo 1.",
        )
        self.pick_battle_list_region()
        if not is_valid_region(self.cfg.get("battle_list_region")):
            self.log("Calibracao guiada cancelada (regiao nao definida).")
            return

        self.calibrate_row_height()
        if not self.cfg.get("row_height"):
            self.log("Calibracao guiada cancelada (altura de linha nao definida).")
            return

        self.capture_row_empty_template()
        if not self.cfg.get("row_empty_template"):
            self.log("Calibracao guiada cancelada (template de linha vazia nao definido).")
            return

        messagebox.showinfo("Training", "Passo 4/4: agora selecione a faixa de texto do NOME, numa linha OCUPADA.")
        self.pick_name_crop()

        self.log("Calibracao guiada concluida - falta so a cor do nome (botoes logo abaixo).")
        messagebox.showinfo(
            "Training",
            "Calibracao guiada concluida! Falta so calibrar a COR DO NOME - use os botoes "
            "'Calibrar ATAQUE normal...' e 'Calibrar FOLLOW normal...' com uma criatura em "
            "cada estado.",
        )

    def pick_battle_list_region(self) -> None:
        region = self.app.select_region(
            "Arraste so pela LISTA de criaturas (comece no topo da 1a linha - sem "
            "pegar o titulo/icones/dropdown de ordenacao)  -  ESC cancela"
        )
        if not region:
            return
        self.cfg["battle_list_region"] = region
        self.var_region.set(region_text(region))
        self.app.config_store.save()
        self.log(f"Regiao da Battle List definida: {region_text(region)}")

    def calibrate_row_height(self) -> None:
        """Arraste um retangulo cobrindo EXATAMENTE uma linha (do topo dela
        ao topo da linha seguinte) - a altura do retangulo vira `row_height`.
        Mais facil de acertar do que 2 cliques as cegas: da pra ver o
        retangulo se ajustando em tempo real antes de soltar o botao."""
        region = self.app.select_region(
            "Arraste cobrindo UMA linha inteira da Battle List (do topo dela ate o "
            "topo da linha seguinte)  -  ESC cancela"
        )
        if not region:
            return
        height = int(region[3])
        if height < 4:
            messagebox.showwarning("Training", "Altura muito pequena - arraste novamente com mais precisao.")
            return
        self.cfg["row_height"] = height
        self.var_row_height.set(f"{height}px")
        self.app.config_store.save()
        self.log(f"Altura de linha calibrada: {height}px")

    def capture_row_empty_template(self) -> None:
        region = self.app.select_region("Selecione UMA linha VAZIA da Battle List  -  ESC cancela")
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, "training_row_empty.png")
        save_image(path, frame)
        self.cfg["row_empty_template"] = path
        self.var_empty_template.set(f"Template salvo ({region[2]}x{region[3]} px)")
        self.app.config_store.save()
        self.log(f"Template de linha vazia salvo em {path}")

    def pick_name_crop(self) -> None:
        region = self.app.select_region(
            "Selecione APENAS a faixa de texto do nome, numa linha OCUPADA  -  ESC cancela"
        )
        if not region:
            return
        offset = self._relative_row_offset(region)
        if offset is None:
            return
        self.cfg["name_crop_offset"] = offset
        self.var_name_offset.set(offset_text(offset))
        self.app.config_store.save()
        self.log(f"Faixa de texto do nome definida: {offset_text(offset)}")

    def _name_color_status_text(self) -> str:
        def ok(key: str) -> str:
            return "OK" if self.cfg.get(key) else "-"

        return (
            f"Attack: normal={ok('attack_name_hsv_lower')} hover={ok('attack_hover_name_hsv_lower')}"
            f"   |   Follow: normal={ok('follow_name_hsv_lower')} hover={ok('follow_hover_name_hsv_lower')}"
        )

    def _calibrate_name_color(self, kind: str, variant: str = "normal") -> None:
        """Amostra a cor do nome direto da tela, sem arrastar sobre o jogo -
        evita que o proprio ato de calibrar (com o mouse ali) contamine a
        amostra com hover sem querer. Da 3s de atraso depois do aviso pro
        usuario posicionar o mouse como quiser antes da captura automatica."""
        if (
            not is_valid_region(self.cfg.get("battle_list_region"))
            or not self.cfg.get("row_height")
            or not self.cfg.get("name_crop_offset")
        ):
            messagebox.showwarning("Training", "Calibre a regiao, a altura de linha e a faixa do nome primeiro.")
            return
        kind_label = "ATAQUE (vermelho)" if kind == "attack" else "FOLLOW (verde)"
        if variant == "hover":
            instr = f"deixe o MOUSE EM CIMA da linha da criatura em modo {kind_label}"
        else:
            instr = f"deixe o mouse LONGE da Battle List, com uma criatura em modo {kind_label} visivel"
        messagebox.showinfo(
            "Training",
            f"Depois de clicar OK voce tem 3 segundos: {instr} (na PRIMEIRA linha ocupada). "
            "A captura e automatica, sem precisar clicar na tela do jogo.",
        )
        self.after(3000, lambda: self._do_calibrate_name_color(kind, variant))

    def _do_calibrate_name_color(self, kind: str, variant: str) -> None:
        cfg = self.worker_config()
        # calibracao de cor nao depende do alvo de treino - evita que o
        # TrainingWorker.setup() bloqueie so por falta do nome ainda nao
        # preenchido nesta tela.
        if not cfg.get("creature_name"):
            cfg["creature_name"] = "_calibration_placeholder_"
        try:
            worker = TrainingWorker(dict(cfg), self.app.events)
            worker.setup()
        except Exception as exc:
            messagebox.showerror("Training", f"Falha ao capturar: {exc}")
            return

        crop = None
        try:
            frame = worker.capture.grab(worker.battle_list_region)
            for i in range(worker.row_count):
                y0, y1 = i * worker.row_height, i * worker.row_height + worker.row_height
                row_frame = frame[y0:y1, :]
                if row_frame.size == 0:
                    continue
                if not row_is_empty(row_frame, worker.empty_template, worker.empty_threshold):
                    candidate = crop_offset(row_frame, worker.name_crop_offset)
                    if candidate is not None and candidate.size > 0:
                        crop = candidate
                        break
        finally:
            worker.teardown()

        if crop is None:
            messagebox.showwarning(
                "Training", "Nenhuma linha ocupada encontrada agora - confira se a criatura "
                "esta visivel na PRIMEIRA linha da Battle List."
            )
            return

        lower, upper = sample_name_text_color(crop)
        key_prefix = f"{kind}_hover_name" if variant == "hover" else f"{kind}_name"
        self.cfg[f"{key_prefix}_hsv_lower"] = lower
        self.cfg[f"{key_prefix}_hsv_upper"] = upper
        self.var_name_color_status.set(self._name_color_status_text())
        self.app.config_store.save()
        kind_label = "ATAQUE" if kind == "attack" else "FOLLOW"
        self.log(f"Cor do nome em {kind_label} ({variant}) calibrada: HSV {lower} - {upper}")

    def calibrate_context_menu(self) -> None:
        point1 = self.app.select_point(
            "PASSO 1/2: clique no local onde o botao direito seria aplicado "
            "(ex: o centro de uma linha da Battle List)  -  ESC cancela"
        )
        if not point1:
            return
        messagebox.showinfo(
            "Training",
            "Agora clique com o BOTAO DIREITO nesse mesmo ponto, dentro do jogo, "
            "para abrir o menu de contexto de verdade. Com o menu aberto, clique OK "
            "e marque a opcao 'Attack'.",
        )
        point2 = self.app.select_point("PASSO 2/2: clique na opcao 'Attack' do menu aberto  -  ESC cancela")
        if not point2:
            return
        dx = int(point2[0]) - int(point1[0])
        dy = int(point2[1]) - int(point1[1])
        self.cfg["context_menu_offset"] = [dx, dy]
        self.var_menu_offset.set(offset_text([dx, dy]))
        self.app.config_store.save()
        self.log(f"Deslocamento do menu de contexto calibrado: dx={dx} dy={dy}")

    def pick_mana_region(self) -> None:
        region = self.app.select_region("Selecione o numero de MANA na barra de status  -  ESC cancela")
        if not region:
            return
        self.cfg["mana_region"] = region
        self.var_mana_region.set(region_text(region))
        self.app.config_store.save()
        self.log(f"Regiao de mana definida: {region_text(region)}")

    def test_mana_ocr(self) -> None:
        self.save_config()
        configure_tesseract(on_progress=self.log)
        region = self.cfg.get("mana_region")
        if not is_valid_region(region):
            messagebox.showwarning("Training", "Regiao de mana nao configurada.")
            return
        try:
            with ScreenCapture() as cap:
                value = read_number(cap.grab(region))
        except OCRUnavailable as exc:
            messagebox.showerror("Training", str(exc))
            return
        message = f"OCR mana: {value if value is not None else 'nao reconhecido'}"
        self.log(message)
        messagebox.showinfo("Training", message)

    def pick_dummy_position(self) -> None:
        point = self.app.select_point("Clique na posicao do BONECO DE TREINO na tela  -  ESC cancela")
        if not point:
            return
        self.cfg["dummy_position"] = list(point)
        self.var_dummy_position.set(region_text(point))
        self.app.config_store.save()
        self.log(f"Posicao do boneco de treino definida: {region_text(point)}")

    def capture_weapon_template(self) -> None:
        region = self.app.select_region(
            "Selecione o SLOT da arma de treino, ja EQUIPADA  -  ESC cancela"
        )
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, "training_weapon_equipped.png")
        save_image(path, frame)
        self.cfg["weapon_slot_region"] = region
        self.cfg["weapon_equipped_template"] = path
        self.var_weapon_region.set(region_text(region))
        self.var_weapon_template.set(f"Template salvo ({region[2]}x{region[3]} px)")
        self.app.config_store.save()
        self.log(f"Template da arma de treino equipada salvo em {path}")

    # ------------------------------------------------------------- testes
    def worker_config(self) -> dict:
        """Inclui os mesmos extras (`_coordinator`/`_background_hwnd`) que
        `app.start_worker` injeta - sem isso, "Testar deteccao" cairia sempre
        no mouse real, mesmo com "Modo background" ligado."""
        cfg = dict(self.cfg)
        cfg.update(self.app.build_worker_extras())
        return cfg

    def test_detection(self) -> None:
        """Dry-run - Modo A mostra a leitura da Battle List (linha
        encontrada, selecionada ou nao); Modo B mostra o resultado do
        template match da arma de treino, sem clicar em nada."""
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TrainingWorker(dict(cfg), self.app.events)
            worker.setup()
        except Exception as exc:
            messagebox.showerror("Training", f"Falha ao preparar deteccao: {exc}")
            return

        try:
            if worker.mode == "dummy":
                still_equipped = worker._weapon_still_equipped()
                if still_equipped is None:
                    message = "Slot da arma de treino nao calibrado - checagem desativada."
                else:
                    message = "Arma de treino: EQUIPADA (bate com o template)" if still_equipped else \
                        "Arma de treino: NAO bate com o template calibrado (esgotada/trocada)."
            else:
                frame = worker.capture.grab(worker.battle_list_region)
                rows = worker.read_rows(frame)
                occupied = [r for r in rows if r.occupied]
                target_row = worker.find_trained_creature(occupied)
                lines = []
                for row in rows:
                    if not row.occupied:
                        lines.append(f"Linha {row.index}: vazia")
                        continue
                    marker = "  <- ALVO DE TREINO" if target_row is not None and target_row.index == row.index else ""
                    lines.append(f"Linha {row.index}: nome='{row.name or '?'}' selecao={row.selection}{marker}")
                message = "\n".join(lines) if lines else "Nenhuma linha detectada (confira a altura de linha)."
        except Exception as exc:
            worker.teardown()
            messagebox.showerror("Training", f"Falha na deteccao: {exc}")
            return
        worker.teardown()

        self.log(message)
        messagebox.showinfo("Training - Testar deteccao", message)

    # -------------------------------------------------------------- controles
    def save_config(self) -> None:
        self.cfg["mode"] = MODE_VALUES.get(self.var_mode.get(), "battle_list")

        self.cfg["attack_mode"] = ATTACK_MODE_VALUES.get(self.var_attack_mode.get(), "single_click")
        self.cfg["creature_name"] = self.var_creature_name.get().strip()
        threshold_pct = max(0, min(100, parse_int(self.var_name_threshold.get(), 80)))
        self.cfg["name_match_threshold"] = threshold_pct / 100
        self.cfg["missing_retries"] = max(1, parse_int(self.var_missing_retries.get(), 5))
        self.cfg["missing_retry_interval"] = parse_float(self.var_missing_retry_interval.get(), 2.0)
        self.cfg["delay_min"] = parse_float(self.var_delay_min.get(), 0.6)
        self.cfg["delay_max"] = parse_float(self.var_delay_max.get(), 1.4)
        self.cfg["click_jitter"] = parse_int(self.var_jitter.get(), 2)
        coverage_pct = max(0, min(100, parse_int(self.var_empty_threshold.get(), 90)))
        self.cfg["empty_match_threshold"] = coverage_pct / 100

        self.cfg["cast_spell_enabled"] = bool(self.var_cast_spell.get())
        self.cfg["spell_hotkey"] = self.var_spell_hotkey.get().strip().lower()
        self.cfg["check_mana"] = bool(self.var_check_mana.get())
        self.cfg["min_mana"] = parse_int(self.var_min_mana.get(), 300)
        self.cfg["spell_delay_min"] = parse_float(self.var_spell_delay_min.get(), 1.5)
        self.cfg["spell_delay_max"] = parse_float(self.var_spell_delay_max.get(), 2.5)

        weapon_pct = max(0, min(100, parse_int(self.var_weapon_threshold.get(), 90)))
        self.cfg["weapon_match_threshold"] = weapon_pct / 100
        self.cfg["click_interval_min"] = parse_float(self.var_click_interval_min.get(), 2.0)
        self.cfg["click_interval_max"] = parse_float(self.var_click_interval_max.get(), 4.0)

        self.cfg["anti_afk_enabled"] = bool(self.var_afk_enabled.get())
        self.cfg["anti_afk_interval_minutes"] = parse_float(self.var_afk_interval.get(), 10.0)
        self.cfg["anti_afk_key_a"] = self.var_afk_key_a.get().strip().lower()
        self.cfg["anti_afk_key_b"] = self.var_afk_key_b.get().strip().lower()

        self.cfg["break_enabled"] = bool(self.var_break_enabled.get())
        self.cfg["break_interval_min"] = parse_int(self.var_break_interval_min.get(), 30)
        self.cfg["break_interval_max"] = parse_int(self.var_break_interval_max.get(), 300)
        self.cfg["break_duration_min"] = parse_int(self.var_break_duration_min.get(), 10)
        self.cfg["break_duration_max"] = parse_int(self.var_break_duration_max.get(), 120)

        self.app.config_store.save()

    def start(self) -> None:
        self.save_config()
        mode = self.cfg.get("mode")
        if mode == "dummy":
            if not self.cfg.get("dummy_position"):
                messagebox.showwarning("Training", "Selecione a posicao do boneco de treino primeiro.")
                return
        else:
            if not is_valid_region(self.cfg.get("battle_list_region")):
                messagebox.showwarning("Training", "Selecione a regiao da Battle List primeiro.")
                return
            if not self.cfg.get("row_height"):
                messagebox.showwarning("Training", "Calibre a altura de linha primeiro.")
                return
            if not self.cfg.get("row_empty_template"):
                messagebox.showwarning("Training", "Capture o template de linha vazia primeiro.")
                return
            if not self.cfg.get("creature_name"):
                messagebox.showwarning("Training", "Informe o nome do monstro de treino primeiro.")
                return
        self.app.start_worker(self.worker_key, TrainingWorker, self.worker_config())

    def toggle_pause(self) -> None:
        self.app.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.app.stop_worker(self.worker_key)

    # ------------------------------------------------------------- callbacks
    def log(self, message: str) -> None:
        self.app.log(message, source=self.worker_key)

    def on_state(self, state: str) -> None:
        self.var_status.set(state)
        running = state in ("running", "paused")
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_pause.configure(state="normal" if running else "disabled")
        self.btn_stop.configure(state="normal" if running else "disabled")

    def on_counter(self, value: int) -> None:
        self.var_counter.set(str(value))

    def on_elapsed(self, value: str) -> None:
        self.var_elapsed.set(value)
