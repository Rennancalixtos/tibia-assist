from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.rune_maker import OCRUnavailable, configure_tesseract, read_number
from functions.training import TrainingWorker
from gui.mana_overlay import ManaOverlay
from gui.widgets import ScrollableFrame, add_field, add_hotkey_field, parse_float, parse_int, region_text


class TrainingWindow(ttk.Frame):
    worker_key = "training"

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.cfg = app.config_store.section("training")

        self.var_region = tk.StringVar(value=region_text(self.cfg.get("battle_list_region")))
        self.var_empty_template = tk.StringVar(
            value="Modelo calibrado" if self.cfg.get("training_battle_empty_template") else "não calibrado"
        )
        self.var_empty_threshold = tk.StringVar(
            value=str(int(float(self.cfg.get("empty_match_threshold", 0.85)) * 100))
        )

        rgb = self.cfg.get("attack_color_rgb") or [254, 0, 0]
        self.var_color_r = tk.StringVar(value=str(rgb[0]))
        self.var_color_g = tk.StringVar(value=str(rgb[1]))
        self.var_color_b = tk.StringVar(value=str(rgb[2]))
        self.var_color_tolerance = tk.StringVar(value=str(self.cfg.get("attack_color_tolerance", 6)))
        self.var_color_min_pixels = tk.StringVar(value=str(self.cfg.get("attack_color_min_pixels", 3)))

        self.var_attack_key = tk.StringVar(value=self.cfg.get("attack_key", "space"))
        self.var_attack_check_delay = tk.StringVar(value=str(self.cfg.get("attack_check_delay", 0.5)))

        self.var_idle_min = tk.StringVar(value=str(self.cfg.get("idle_delay_min", 2.0)))
        self.var_idle_max = tk.StringVar(value=str(self.cfg.get("idle_delay_max", 4.0)))
        self.var_engaged_min = tk.StringVar(value=str(self.cfg.get("engaged_delay_min", 1.0)))
        self.var_engaged_max = tk.StringVar(value=str(self.cfg.get("engaged_delay_max", 2.0)))

        self.var_creature_name = tk.StringVar(value=self.cfg.get("creature_name", ""))
        self.var_name_threshold = tk.StringVar(
            value=str(int(float(self.cfg.get("name_match_threshold", 0.80)) * 100))
        )
        self.var_missing_retries = tk.StringVar(value=str(self.cfg.get("missing_retries", 5)))
        self.var_missing_retry_interval = tk.StringVar(value=str(self.cfg.get("missing_retry_interval", 2.0)))

        self.var_cast_spell = tk.BooleanVar(value=bool(self.cfg.get("cast_spell_enabled", False)))
        self.var_spell_hotkey = tk.StringVar(value=self.cfg.get("spell_hotkey", ""))
        self.var_check_mana = tk.BooleanVar(value=bool(self.cfg.get("check_mana", True)))
        self.var_mana_region = tk.StringVar(value=region_text(self.cfg.get("mana_region")))
        self.var_min_mana = tk.StringVar(value=str(self.cfg.get("min_mana", 300)))
        self.var_spell_delay_min = tk.StringVar(value=str(self.cfg.get("spell_delay_min", 1.5)))
        self.var_spell_delay_max = tk.StringVar(value=str(self.cfg.get("spell_delay_max", 2.5)))

        self.var_afk_enabled = tk.BooleanVar(value=bool(self.cfg.get("anti_afk_enabled", False)))
        self.var_afk_interval = tk.StringVar(value=str(self.cfg.get("anti_afk_interval_minutes", 10)))
        self.var_afk_key_a = tk.StringVar(value=self.cfg.get("anti_afk_key_a", "up"))
        self.var_afk_key_b = tk.StringVar(value=self.cfg.get("anti_afk_key_b", "down"))

        self.var_status = tk.StringVar(value="parado")
        self.var_elapsed = tk.StringVar(value="00:00:00")
        self.var_counter = tk.StringVar(value="0")

        self.battle_overlay = ManaOverlay(self.app)
        self.battle_overlay.configure_region(self.cfg.get("battle_list_region"))

        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        self.body = scroll.body
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._build()

        self._config_dialog = tk.Toplevel(self)
        self._config_dialog.title("Configurar - Training")
        self._config_dialog.geometry("640x600")
        self._config_dialog.transient(self.winfo_toplevel())
        self._config_dialog.protocol("WM_DELETE_WINDOW", self._hide_config_dialog)
        config_scroll = ScrollableFrame(self._config_dialog)
        config_scroll.pack(fill="both", expand=True)
        self._build_config_dialog(config_scroll.body)
        self._config_dialog.withdraw()

        self._update_field_states()

    def _build(self) -> None:
        body = self.body

        box_run = ttk.LabelFrame(body, text="1. Execução")
        box_run.grid(row=0, column=0, sticky="ew", pady=4)

        actions = ttk.Frame(box_run)
        actions.grid(row=0, column=0, columnspan=4, sticky="w", pady=(2, 6))
        ttk.Button(actions, text="Testar detecção", command=self.test_detection).pack(side="left", padx=8)
        ttk.Button(actions, text="Testar tecla de ataque", command=self.test_attack_key).pack(side="left", padx=8)

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
        ttk.Label(box_run, text="Ataques disparados:").grid(row=3, column=2, sticky="e", padx=4)
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

    def _build_config_dialog(self, parent) -> None:
        box_list = ttk.LabelFrame(parent, text="1. Battle List")
        box_list.grid(row=0, column=0, sticky="ew", pady=4)

        ttk.Button(
            box_list, text="Selecionar região da Battle List...", command=self.pick_battle_list_region
        ).grid(row=0, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(box_list, textvariable=self.var_region).grid(row=0, column=1, sticky="w")
        ttk.Label(
            box_list,
            text="Arraste só pela LISTA de criaturas (comece no topo da 1a linha - sem "
            "pegar o título/ícones/dropdown de ordenação).",
            foreground="#666",
            wraplength=580,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=4)

        ttk.Button(
            box_list, text="Capturar modelo de lista vazia (cabeçalho + 1a linha)...",
            command=self.capture_empty_template,
        ).grid(row=2, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(box_list, textvariable=self.var_empty_template).grid(row=2, column=1, sticky="w")
        ttk.Label(
            box_list,
            text="Com a lista VAZIA no jogo, arraste incluindo o título da janela 'Battle' + a "
            "1a linha (vazia) logo abaixo.",
            foreground="#666",
            wraplength=580,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=4)

        self.entry_empty_threshold = add_field(
            box_list, 4, "Confiança mínima do modelo vazio (%)", self.var_empty_threshold, 8, "0 a 100 (padrão 85)"
        )

        box_color = ttk.LabelFrame(parent, text="2. Cor de ataque (nome da criatura)")
        box_color.grid(row=1, column=0, sticky="ew", pady=4)
        color_row = ttk.Frame(box_color)
        color_row.grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=3)
        ttk.Label(color_row, text="RGB:").pack(side="left", padx=(0, 4))
        ttk.Entry(color_row, textvariable=self.var_color_r, width=5).pack(side="left")
        ttk.Entry(color_row, textvariable=self.var_color_g, width=5).pack(side="left", padx=4)
        ttk.Entry(color_row, textvariable=self.var_color_b, width=5).pack(side="left")
        add_field(box_color, 1, "Tolerância por canal", self.var_color_tolerance, 8, "0 a 255 (padrão 6)")
        add_field(box_color, 2, "Pixels mínimos", self.var_color_min_pixels, 8, "padrão 3")
        ttk.Label(
            box_color,
            text="Padrão RGB 254,0,0 (vermelho puro do nome em ATAQUE) - o mesmo mecanismo usado no Target.",
            foreground="#666",
            wraplength=580,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=4)

        box_key = ttk.LabelFrame(parent, text="3. Tecla de ataque")
        box_key.grid(row=2, column=0, sticky="ew", pady=4)
        add_hotkey_field(box_key, 0, "Tecla de ataque", self.var_attack_key, 10, "ex: space")
        add_field(
            box_key, 1, "Delay após apertar (s)", self.var_attack_check_delay, 8, "aguarda antes de conferir a cor"
        )
        ttk.Label(
            box_key,
            text="Precisa estar configurada DENTRO do Tibia primeiro (Options > Hotkeys > "
            "Attack) para atacar a criatura selecionada.",
            foreground="#a33",
            wraplength=580,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 0))

        box_rate = ttk.LabelFrame(parent, text="4. Ritmo")
        box_rate.grid(row=3, column=0, sticky="ew", pady=4)
        add_field(box_rate, 0, "Delay mínimo (alvo sumido) (s)", self.var_idle_min, 8, "ex: 2.0")
        add_field(box_rate, 1, "Delay máximo (alvo sumido) (s)", self.var_idle_max, 8, "ex: 4.0")
        add_field(box_rate, 2, "Delay mínimo (já atacando) (s)", self.var_engaged_min, 8, "ex: 1.0")
        add_field(box_rate, 3, "Delay máximo (já atacando) (s)", self.var_engaged_max, 8, "ex: 2.0")

        self.box_target = ttk.LabelFrame(parent, text="5. Alvo de treino permanente")
        self.box_target.grid(row=4, column=0, sticky="ew", pady=4)
        self.entry_creature_name = add_field(
            self.box_target, 0, "Nome do monstro de treino", self.var_creature_name, 24, "ex: Training Monk"
        )
        self.entry_name_threshold = add_field(
            self.box_target, 1, "Similaridade mínima do nome (%)", self.var_name_threshold, 8, "tolerante a falhas de OCR"
        )
        self.entry_missing_retries = add_field(
            self.box_target, 2, "Tentativas antes de pausar", self.var_missing_retries, 8, "alvo sumido da lista"
        )
        self.entry_missing_interval = add_field(
            self.box_target, 3, "Intervalo entre tentativas (s)", self.var_missing_retry_interval, 8, "ex: 2.0"
        )
        ttk.Label(
            self.box_target,
            text="O nome é lido via OCR na região inteira da Battle List, ignorando maiúsculas "
            "e pequenas falhas de leitura - assim o bot só ataca enquanto o monstro certo "
            "estiver na lista.",
            foreground="#666",
            wraplength=600,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=4)

        self.box_spell = ttk.LabelFrame(parent, text="6. Magia de ataque (opcional, treino de magic level)")
        self.box_spell.grid(row=5, column=0, sticky="ew", pady=4)
        self.chk_cast_spell = ttk.Checkbutton(
            self.box_spell, text="Também conjurar magia de ataque enquanto o alvo estiver selecionado",
            variable=self.var_cast_spell, command=self._update_field_states,
        )
        self.chk_cast_spell.grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=3)
        self.entry_spell_hotkey = add_hotkey_field(
            self.box_spell, 1, "Tecla da magia de ataque", self.var_spell_hotkey, 10, "hotkey configurada no jogo"
        )
        self.chk_check_mana = ttk.Checkbutton(self.box_spell, text="Verificar mana", variable=self.var_check_mana)
        self.chk_check_mana.grid(row=2, column=0, sticky="w", padx=4, pady=3)
        self.btn_pick_mana_region = ttk.Button(
            self.box_spell, text="Região da mana...", command=self.pick_mana_region
        )
        self.btn_pick_mana_region.grid(row=2, column=1, padx=4)
        ttk.Label(self.box_spell, textvariable=self.var_mana_region).grid(row=2, column=2, sticky="w", padx=4)
        self.entry_min_mana = add_field(self.box_spell, 3, "Mana mínima", self.var_min_mana, 8, "pausa a magia abaixo disso")
        self.entry_spell_delay_min = add_field(
            self.box_spell, 4, "Delay mínimo entre magias (s)", self.var_spell_delay_min, 8, "ex: 1.5"
        )
        self.entry_spell_delay_max = add_field(
            self.box_spell, 5, "Delay máximo entre magias (s)", self.var_spell_delay_max, 8, "ex: 2.5"
        )
        self.btn_test_ocr_mana = ttk.Button(self.box_spell, text="Testar OCR da mana", command=self.test_mana_ocr)
        self.btn_test_ocr_mana.grid(row=6, column=0, padx=4, pady=(4, 6), sticky="w")

        box_afk = ttk.LabelFrame(parent, text="7. Anti-AFK-kick")
        box_afk.grid(row=6, column=0, sticky="ew", pady=4)
        ttk.Checkbutton(
            box_afk, text="Enviar ação anti-AFK periodicamente", variable=self.var_afk_enabled
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=3)
        add_field(box_afk, 1, "Intervalo (minutos)", self.var_afk_interval, 8, "ex: 10")
        add_hotkey_field(box_afk, 2, "Tecla de movimento (ida)", self.var_afk_key_a, 10, "ex: up")
        add_hotkey_field(box_afk, 3, "Tecla de movimento (volta)", self.var_afk_key_b, 10, "ex: down")
        ttk.Label(
            box_afk,
            text="Fallback de 'movimento leve' (aperta uma tecla e a oposta em seguida) caso a "
            "tecla de ataque em loop não conte como atividade no seu servidor.",
            foreground="#666",
            wraplength=680,
            justify="left",
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4))

        ttk.Label(
            parent,
            text="Aviso: esta função depende de leitura visual (template/cor/OCR) da Battle List. "
            "Mudar o tamanho da janela do jogo, o zoom ou a skin da Battle List depois de "
            "calibrar pode quebrar a detecção - recalibre se isso acontecer.",
            foreground="#a33",
            wraplength=700,
            justify="left",
        ).grid(row=7, column=0, sticky="w", pady=(4, 0))

        actions_bar = ttk.Frame(parent)
        actions_bar.grid(row=8, column=0, sticky="e", pady=(8, 4))
        ttk.Button(actions_bar, text="Salvar config", command=self.save_config).pack(side="left", padx=4)
        ttk.Button(actions_bar, text="Fechar", command=self._hide_config_dialog).pack(side="left", padx=4)

        parent.columnconfigure(0, weight=1)

    def _update_field_states(self) -> None:
        cast_spell_state = "normal" if self.var_cast_spell.get() else "disabled"
        for widget in (
            self.entry_spell_hotkey, self.chk_check_mana, self.btn_pick_mana_region, self.entry_min_mana,
            self.entry_spell_delay_min, self.entry_spell_delay_max, self.btn_test_ocr_mana,
        ):
            widget.configure(state=cast_spell_state)

    def pick_battle_list_region(self) -> None:
        region = self.app.select_region(
            "Arraste cobrindo toda a área visível da Battle List (cabeçalho + linhas)  -  ESC cancela"
        )
        if not region:
            return
        self.cfg["battle_list_region"] = region
        self.var_region.set(region_text(region))
        self.battle_overlay.configure_region(region)
        self.app.config_store.save()
        self.log(f"Região da Battle List definida: {region_text(region)}")

    def capture_empty_template(self) -> None:
        region = self.app.select_region(
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
        self.var_empty_template.set(f"Modelo salvo ({region[2]}x{region[3]} px)")
        self.app.config_store.save()
        self.log(f"Modelo de lista vazia salvo em {path}")

    def pick_mana_region(self) -> None:
        region = self.app.select_region("Selecione o número de MANA na barra de status  -  ESC cancela")
        if not region:
            return
        self.cfg["mana_region"] = region
        self.var_mana_region.set(region_text(region))
        self.app.config_store.save()
        self.log(f"Região de mana definida: {region_text(region)}")

    def test_mana_ocr(self) -> None:
        self.save_config()
        configure_tesseract(on_progress=self.log)
        region = self.cfg.get("mana_region")
        if not is_valid_region(region):
            messagebox.showwarning("Training", "Região de mana não configurada.")
            return
        try:
            with ScreenCapture() as cap:
                value = read_number(cap.grab(region))
        except OCRUnavailable as exc:
            messagebox.showerror("Training", str(exc))
            return
        message = f"OCR mana: {value if value is not None else 'não reconhecido'}"
        self.log(message)
        messagebox.showinfo("Training", message)

    def worker_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(self.app.build_worker_extras())
        return cfg

    def test_detection(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TrainingWorker(dict(cfg), self.app.events)
            worker.setup()
        except Exception as exc:
            messagebox.showerror("Training", f"Falha ao preparar detecção: {exc}")
            return

        try:
            score = worker.battle_list_empty_score()
            vazia = worker.is_battle_list_empty()
            presente = worker.creature_present() if not vazia else False
            attacking = worker.is_attacking() if presente else False
        except Exception as exc:
            worker.teardown()
            messagebox.showerror("Training", f"Falha na detecção: {exc}")
            return
        worker.teardown()

        score_text = f"{score * 100:.1f}%" if score is not None else "modelo maior que a região"
        message = (
            f"Battle List vazia: {'sim' if vazia else 'não'} (confiança: {score_text}, mínimo: "
            f"{worker.empty_threshold * 100:.0f}%)\n"
            f"Alvo de treino '{worker.creature_name}' presente: {'sim' if presente else 'não'}\n"
            f"Cor de ataque detectada: {'sim' if attacking else 'não'}"
        )
        self.log(message.replace("\n", " | "))
        messagebox.showinfo("Training - Testar detecção", message)

    def test_attack_key(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TrainingWorker(dict(cfg), self.app.events)
            worker.setup()
        except Exception as exc:
            messagebox.showerror("Training", f"Falha ao preparar teste: {exc}")
            return

        try:
            dry_run = bool(self.app.var_dry_run_enabled.get())
            if not dry_run and not messagebox.askyesno(
                "Training", f"Modo REAL: isso vai apertar a tecla '{worker.attack_key}' de verdade. Continuar?"
            ):
                return
            worker.press_attack_key(dry_run=dry_run)
        except Exception as exc:
            messagebox.showerror("Training", f"Falha no teste da tecla de ataque: {exc}")
            return
        finally:
            worker.teardown()

        self.log(f"Teste da tecla de ataque concluído ('{worker.attack_key}').")
        messagebox.showinfo("Training", f"Tecla de ataque testada ('{worker.attack_key}' - ver log).")

    def save_config(self) -> None:
        self.cfg["attack_color_rgb"] = [
            max(0, min(255, parse_int(self.var_color_r.get(), 254))),
            max(0, min(255, parse_int(self.var_color_g.get(), 0))),
            max(0, min(255, parse_int(self.var_color_b.get(), 0))),
        ]
        self.cfg["attack_color_tolerance"] = max(0, parse_int(self.var_color_tolerance.get(), 6))
        self.cfg["attack_color_min_pixels"] = max(1, parse_int(self.var_color_min_pixels.get(), 3))
        self.cfg["attack_key"] = (self.var_attack_key.get() or "space").strip().lower()
        self.cfg["attack_check_delay"] = max(0.0, parse_float(self.var_attack_check_delay.get(), 0.5))
        self.cfg["idle_delay_min"] = parse_float(self.var_idle_min.get(), 2.0)
        self.cfg["idle_delay_max"] = parse_float(self.var_idle_max.get(), 4.0)
        self.cfg["engaged_delay_min"] = parse_float(self.var_engaged_min.get(), 1.0)
        self.cfg["engaged_delay_max"] = parse_float(self.var_engaged_max.get(), 2.0)
        coverage_pct = max(0, min(100, parse_int(self.var_empty_threshold.get(), 85)))
        self.cfg["empty_match_threshold"] = coverage_pct / 100

        self.cfg["creature_name"] = self.var_creature_name.get().strip()
        threshold_pct = max(0, min(100, parse_int(self.var_name_threshold.get(), 80)))
        self.cfg["name_match_threshold"] = threshold_pct / 100
        self.cfg["missing_retries"] = max(1, parse_int(self.var_missing_retries.get(), 5))
        self.cfg["missing_retry_interval"] = parse_float(self.var_missing_retry_interval.get(), 2.0)

        self.cfg["cast_spell_enabled"] = bool(self.var_cast_spell.get())
        self.cfg["spell_hotkey"] = self.var_spell_hotkey.get().strip().lower()
        self.cfg["check_mana"] = bool(self.var_check_mana.get())
        self.cfg["min_mana"] = parse_int(self.var_min_mana.get(), 300)
        self.cfg["spell_delay_min"] = parse_float(self.var_spell_delay_min.get(), 1.5)
        self.cfg["spell_delay_max"] = parse_float(self.var_spell_delay_max.get(), 2.5)

        self.cfg["anti_afk_enabled"] = bool(self.var_afk_enabled.get())
        self.cfg["anti_afk_interval_minutes"] = parse_float(self.var_afk_interval.get(), 10.0)
        self.cfg["anti_afk_key_a"] = self.var_afk_key_a.get().strip().lower()
        self.cfg["anti_afk_key_b"] = self.var_afk_key_b.get().strip().lower()

        self.app.config_store.save()

    def start(self) -> None:
        self.save_config()
        if not is_valid_region(self.cfg.get("battle_list_region")):
            messagebox.showwarning("Training", "Selecione a região da Battle List primeiro.")
            return
        if not self.cfg.get("training_battle_empty_template"):
            messagebox.showwarning("Training", "Capture o modelo de lista vazia primeiro.")
            return
        if not self.cfg.get("creature_name"):
            messagebox.showwarning("Training", "Informe o nome do monstro de treino primeiro.")
            return
        self.app.start_worker(self.worker_key, TrainingWorker, self.worker_config())

    def toggle_pause(self) -> None:
        self.app.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.app.stop_worker(self.worker_key)

    def log(self, message: str) -> None:
        self.app.log(message, source=self.worker_key)

    def on_state(self, state: str) -> None:
        self.var_status.set(state)
        running = state in ("running", "paused")
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_pause.configure(state="normal" if running else "disabled")
        self.btn_stop.configure(state="normal" if running else "disabled")
        if running and self.cfg.get("training_battle_empty_template"):
            self.battle_overlay.show()
        else:
            self.battle_overlay.hide()

    def on_counter(self, value: int) -> None:
        self.var_counter.set(str(value))

    def on_elapsed(self, value: str) -> None:
        self.var_elapsed.set(value)
