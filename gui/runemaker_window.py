"""Aba RuneMaker: configuracao, teste de OCR/sequencia e controle da automacao."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.rune_maker import OCRUnavailable, RuneMakerWorker, configure_tesseract, read_number
from gui.mana_overlay import ManaOverlay
from gui.widgets import ScrollableFrame, add_field, add_hotkey_field, parse_float, parse_int, region_text

MODE_LABELS = {"craft": "Criar runas", "mana_training": "ManaTraining"}
MODE_VALUES = {label: value for value, label in MODE_LABELS.items()}


class RuneMakerWindow(ttk.Frame):
    worker_key = "runemaker"

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.cfg = app.config_store.section("runemaker")

        self.var_spell = tk.StringVar(value=self.cfg.get("spell_hotkey", "f2"))
        self.var_amount = tk.StringVar(value=str(self.cfg.get("amount", 0)))
        self.var_delay_min = tk.StringVar(value=str(self.cfg.get("delay_min")))
        self.var_delay_max = tk.StringVar(value=str(self.cfg.get("delay_max")))
        self.var_jitter = tk.StringVar(value=str(self.cfg.get("click_jitter")))
        self.var_min_mana = tk.StringVar(value=str(self.cfg.get("min_mana")))
        self.var_check_mana = tk.BooleanVar(value=bool(self.cfg.get("check_mana", True)))
        self.var_slot = tk.StringVar(value=region_text(self.cfg.get("blank_slot")))
        self.var_mana_region = tk.StringVar(value=region_text(self.cfg.get("mana_region")))
        self.var_mana_point = tk.StringVar(value=region_text(self.cfg.get("mana_display_point")))
        self.var_status = tk.StringVar(value="parado")
        self.var_counter = tk.StringVar(value="0")

        self.var_mode = tk.StringVar(value=MODE_LABELS.get(self.cfg.get("mode", "craft"), "Criar runas"))
        self.var_no_hand = tk.BooleanVar(value=bool(self.cfg.get("no_hand_mode", False)))
        self.var_hand_slot = tk.StringVar(value=region_text(self.cfg.get("hand_slot")))
        self.var_output_slot = tk.StringVar(value=region_text(self.cfg.get("output_slot")))
        self.var_blank_region = tk.StringVar(value=region_text(self.cfg.get("blank_slot_region")))
        self.var_hand_region = tk.StringVar(value=region_text(self.cfg.get("hand_slot_region")))
        self.var_output_region = tk.StringVar(value=region_text(self.cfg.get("output_slot_region")))
        self.var_empty_threshold = tk.StringVar(
            value=str(int(float(self.cfg.get("empty_match_threshold", 0.90)) * 100))
        )
        self.var_dry_run = tk.BooleanVar(value=True)
        self.var_counter_label = tk.StringVar(value="Runas criadas:")

        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        self.body = scroll.body
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.mana_overlay = ManaOverlay(self.app)
        self.mana_overlay.configure_region(self.cfg.get("mana_region"))
        self.mana_overlay.configure_display_point(self.cfg.get("mana_display_point"))

        self._build()

        # Dialogo de configuracao (secoes 1 a 4) - construido ja aqui (nao so
        # no primeiro clique em "Configurar...") pra que os widgets ja
        # existam quando `_on_mode_change`/`_update_field_states` rodam logo
        # abaixo (ver `open_config_dialog`).
        self._config_dialog = tk.Toplevel(self)
        self._config_dialog.title("Configurar - RuneMaker")
        self._config_dialog.geometry("640x600")
        self._config_dialog.transient(self.winfo_toplevel())
        self._config_dialog.protocol("WM_DELETE_WINDOW", self._hide_config_dialog)
        config_scroll = ScrollableFrame(self._config_dialog)
        config_scroll.pack(fill="both", expand=True)
        self._build_config_dialog(config_scroll.body)
        self._config_dialog.withdraw()

        self._on_mode_change()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        body = self.body

        # Execucao ------------------------------------------------------------
        box_run = ttk.LabelFrame(body, text="1. Execucao")
        box_run.grid(row=0, column=0, sticky="ew", pady=4)
        self.btn_start = ttk.Button(box_run, text="Iniciar", command=self.start)
        self.btn_start.grid(row=0, column=0, padx=4, pady=6)
        self.btn_pause = ttk.Button(box_run, text="Pausar/Retomar", command=self.toggle_pause, state="disabled")
        self.btn_pause.grid(row=0, column=1, padx=4)
        self.btn_stop = ttk.Button(box_run, text="Parar", command=self.stop, state="disabled")
        self.btn_stop.grid(row=0, column=2, padx=4)
        self.btn_configure = ttk.Button(box_run, text="Configurar...", command=self.open_config_dialog)
        self.btn_configure.grid(row=0, column=3, padx=12)

        ttk.Label(box_run, text="Status:").grid(row=1, column=0, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_status, font=("Segoe UI", 9, "bold")).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(box_run, textvariable=self.var_counter_label).grid(row=1, column=2, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_counter, font=("Segoe UI", 9, "bold")).grid(
            row=1, column=3, sticky="w"
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
        # Modo ----------------------------------------------------------------
        box_mode = ttk.LabelFrame(parent, text="1. Modo")
        box_mode.grid(row=0, column=0, sticky="ew", pady=4)
        self.radio_craft = ttk.Radiobutton(
            box_mode, text="Criar runas", value="Criar runas", variable=self.var_mode, command=self._on_mode_change
        )
        self.radio_craft.grid(row=0, column=0, sticky="w", padx=4, pady=3)
        self.radio_mana_training = ttk.Radiobutton(
            box_mode,
            text="ManaTraining (so conjura a magia, sem item)",
            value="ManaTraining",
            variable=self.var_mode,
            command=self._on_mode_change,
        )
        self.radio_mana_training.grid(row=0, column=1, sticky="w", padx=4, pady=3)
        ttk.Label(
            box_mode,
            text="⚠ Nao ative os dois ao mesmo tempo - sao modos alternativos, escolha um.",
            foreground="#a33",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))

        # Magia e blank runes -------------------------------------------------
        box_spell = ttk.LabelFrame(parent, text="2. Magia e blank runes")
        box_spell.grid(row=1, column=0, sticky="ew", pady=4)
        add_hotkey_field(box_spell, 0, "Tecla da magia", self.var_spell, 10, "hotkey configurada no jogo (ex: f2)")
        self.entry_amount = add_field(box_spell, 1, "Quantidade de runas", self.var_amount, 8, "0 = ate acabar a mana")

        self.btn_pick_blank_slot = ttk.Button(
            box_spell, text="Selecionar slot da blank rune...", command=self.pick_slot
        )
        self.btn_pick_blank_slot.grid(row=2, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(box_spell, textvariable=self.var_slot).grid(row=2, column=1, columnspan=2, sticky="w")

        self.chk_no_hand = ttk.Checkbutton(
            box_spell,
            text="Servidor nao requer mao (aplicar magia direto no slot da blank rune)",
            variable=self.var_no_hand,
            command=self._on_no_hand_toggle,
        )
        self.chk_no_hand.grid(row=3, column=0, columnspan=3, sticky="w", padx=4, pady=(6, 3))

        self.btn_pick_hand = ttk.Button(
            box_spell, text="Selecionar slot da mao...", command=self.pick_hand_slot
        )
        self.btn_pick_hand.grid(row=4, column=0, padx=4, pady=3, sticky="w")
        ttk.Label(box_spell, textvariable=self.var_hand_slot).grid(row=4, column=1, columnspan=2, sticky="w")

        self.btn_pick_output = ttk.Button(
            box_spell, text="Selecionar slot livre (destino)...", command=self.pick_output_slot
        )
        self.btn_pick_output.grid(row=5, column=0, padx=4, pady=3, sticky="w")
        ttk.Label(box_spell, textvariable=self.var_output_slot).grid(row=5, column=1, columnspan=2, sticky="w")

        # Deteccao de slot vazio -----------------------------------------------
        box_slots = ttk.LabelFrame(parent, text="2.1 Deteccao de slot vazio (template)")
        box_slots.grid(row=2, column=0, sticky="ew", pady=4)
        self.btn_capture_blank_empty = ttk.Button(
            box_slots, text="Capturar slot vazio (origem)...",
            command=lambda: self._capture_empty_template("blank_slot", "de ORIGEM (blank rune)", self.var_blank_region),
        )
        self.btn_capture_blank_empty.grid(row=0, column=0, padx=4, pady=4, sticky="w")
        ttk.Label(box_slots, textvariable=self.var_blank_region).grid(row=0, column=1, sticky="w", padx=4)

        self.btn_capture_hand_empty = ttk.Button(
            box_slots, text="Capturar slot vazio (mao)...",
            command=lambda: self._capture_empty_template("hand_slot", "da MAO", self.var_hand_region),
        )
        self.btn_capture_hand_empty.grid(row=1, column=0, padx=4, pady=4, sticky="w")
        ttk.Label(box_slots, textvariable=self.var_hand_region).grid(row=1, column=1, sticky="w", padx=4)

        self.btn_capture_output_empty = ttk.Button(
            box_slots, text="Capturar slot vazio (destino)...",
            command=lambda: self._capture_empty_template("output_slot", "de DESTINO", self.var_output_region),
        )
        self.btn_capture_output_empty.grid(row=2, column=0, padx=4, pady=4, sticky="w")
        ttk.Label(box_slots, textvariable=self.var_output_region).grid(row=2, column=1, sticky="w", padx=4)

        self.entry_empty_threshold = add_field(
            box_slots, 3, "Cobertura minima do slot vazio (%)", self.var_empty_threshold, 8, "0 a 100 (padrao 90)"
        )

        actions_slots = ttk.Frame(box_slots)
        actions_slots.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 2))
        self.chk_dry_run = ttk.Checkbutton(
            actions_slots, text="Modo teste (dry-run: so loga, nao clica)", variable=self.var_dry_run
        )
        self.chk_dry_run.pack(side="left", padx=4)
        self.btn_test_sequence = ttk.Button(actions_slots, text="Testar sequencia", command=self.test_sequence)
        self.btn_test_sequence.pack(side="left", padx=8)

        # OCR ---------------------------------------------------------------
        box_ocr = ttk.LabelFrame(parent, text="3. Limites de seguranca (OCR)")
        box_ocr.grid(row=3, column=0, sticky="ew", pady=4)

        ttk.Checkbutton(box_ocr, text="Verificar mana", variable=self.var_check_mana).grid(
            row=0, column=0, sticky="w", padx=4, pady=3
        )
        ttk.Button(box_ocr, text="Regiao da mana...", command=lambda: self.pick_ocr_region("mana")).grid(
            row=0, column=1, padx=4
        )
        ttk.Label(box_ocr, textvariable=self.var_mana_region).grid(row=0, column=2, sticky="w", padx=4)

        add_field(box_ocr, 1, "Mana minima", self.var_min_mana, 8, "pausa abaixo disso")

        ttk.Button(box_ocr, text="Testar OCR", command=self.test_ocr).grid(
            row=2, column=0, padx=4, pady=6, sticky="w"
        )

        ttk.Button(
            box_ocr, text="Selecionar onde exibir o valor da mana...", command=self.pick_mana_display_point
        ).grid(row=3, column=0, columnspan=2, padx=4, pady=(0, 6), sticky="w")
        ttk.Label(box_ocr, textvariable=self.var_mana_point).grid(row=3, column=2, sticky="w", padx=4)
        ttk.Label(
            box_ocr,
            text="Overlay sobre a tela do jogo: marca a regiao acima e mostra o valor lido nesse ponto.",
            foreground="#666",
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4))

        # Ritmo -------------------------------------------------------------
        box_rate = ttk.LabelFrame(parent, text="4. Ritmo")
        box_rate.grid(row=4, column=0, sticky="ew", pady=4)
        add_field(box_rate, 0, "Delay minimo (s)", self.var_delay_min, 8, ">= cooldown real da magia")
        add_field(box_rate, 1, "Delay maximo (s)", self.var_delay_max, 8, "ex: 2.5")
        add_field(box_rate, 2, "Variacao do clique (px)", self.var_jitter, 8, "+/- pixels")

        # Salvar / Fechar -------------------------------------------------------
        actions_bar = ttk.Frame(parent)
        actions_bar.grid(row=5, column=0, sticky="e", pady=(8, 4))
        ttk.Button(actions_bar, text="Salvar config", command=self.save_config).pack(side="left", padx=4)
        ttk.Button(actions_bar, text="Fechar", command=self._hide_config_dialog).pack(side="left", padx=4)

        parent.columnconfigure(0, weight=1)

    # ------------------------------------------------------------ modo/estado
    def _on_no_hand_toggle(self) -> None:
        self._update_field_states()

    def _on_mode_change(self) -> None:
        is_mana_training = self.var_mode.get() == "ManaTraining"
        self.var_counter_label.set("Magias conjuradas:" if is_mana_training else "Runas criadas:")
        self._update_field_states()

    def _update_field_states(self) -> None:
        """So a tecla da magia (usada por todos os modos) e as secoes 3/4/5
        continuam sempre ativas. O resto depende do modo escolhido e do
        checkbox "sem mao"."""
        mana_training = self.var_mode.get() == "ManaTraining"
        item_state = "disabled" if mana_training else "normal"

        self.entry_amount.configure(state=item_state)
        self.btn_pick_blank_slot.configure(state=item_state)
        self.chk_no_hand.configure(state=item_state)
        for widget in (
            self.btn_capture_blank_empty,
            self.entry_empty_threshold,
            self.chk_dry_run,
            self.btn_test_sequence,
        ):
            widget.configure(state=item_state)

        hand_state = "disabled" if (mana_training or self.var_no_hand.get()) else "normal"
        for widget in (self.btn_pick_hand, self.btn_pick_output, self.btn_capture_hand_empty, self.btn_capture_output_empty):
            widget.configure(state=hand_state)

    # --------------------------------------------------------------- selecao
    def pick_slot(self) -> None:
        point = self.app.select_point("Clique no slot da BLANK RUNE  -  ESC cancela")
        if point:
            self.cfg["blank_slot"] = list(point)
            self.var_slot.set(region_text(point))
            self.app.config_store.save()
            self.log(f"Slot da blank rune definido: {region_text(point)}")

    def pick_hand_slot(self) -> None:
        point = self.app.select_point("Clique no slot da MAO do personagem  -  ESC cancela")
        if point:
            self.cfg["hand_slot"] = list(point)
            self.var_hand_slot.set(region_text(point))
            self.app.config_store.save()
            self.log(f"Slot da mao definido: {region_text(point)}")

    def pick_output_slot(self) -> None:
        point = self.app.select_point("Clique no slot LIVRE de destino  -  ESC cancela")
        if point:
            self.cfg["output_slot"] = list(point)
            self.var_output_slot.set(region_text(point))
            self.app.config_store.save()
            self.log(f"Slot de destino definido: {region_text(point)}")

    def pick_ocr_region(self, key: str) -> None:
        label = "MANA"
        region = self.app.select_region(f"Selecione o numero de {label} na barra de status  -  ESC cancela")
        if not region:
            return
        self.cfg[f"{key}_region"] = region
        self.var_mana_region.set(region_text(region))
        self.mana_overlay.configure_region(region)
        self.app.config_store.save()
        self.log(f"Regiao de {label} definida: {region_text(region)}")

    def pick_mana_display_point(self) -> None:
        point = self.app.select_point(
            "Clique onde exibir o valor da mana durante a automacao  -  ESC cancela"
        )
        if not point:
            return
        self.cfg["mana_display_point"] = list(point)
        self.var_mana_point.set(region_text(point))
        self.mana_overlay.configure_display_point(point)
        self.app.config_store.save()
        self.log(f"Ponto de exibicao da mana definido: {region_text(point)}")

    def _capture_empty_template(self, slot_key: str, label: str, region_var: tk.StringVar) -> None:
        """Recorta o slot VAZIO como referencia pra deteccao por template
        (mesmo padrao do "Capturar template" do AutoFishing)."""
        region = self.app.select_region(f"Selecione o slot {label} VAZIO  -  ESC cancela")
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, f"rune_{slot_key}_empty.png")
        save_image(path, frame)
        self.cfg[f"{slot_key}_region"] = region
        self.cfg[f"{slot_key}_empty_template"] = path
        region_var.set(region_text(region))
        self.app.config_store.save()
        self.log(f"Template de slot vazio ({label}) salvo em {path} ({region[2]}x{region[3]} px)")

    def test_ocr(self) -> None:
        """Le a mana uma unica vez e mostra o que o Tesseract entendeu."""
        self.save_config()
        configure_tesseract(on_progress=self.log)

        region = self.cfg.get("mana_region")
        if not is_valid_region(region):
            messagebox.showwarning("RuneMaker", "Regiao de mana nao configurada.")
            return
        try:
            with ScreenCapture() as cap:
                value = read_number(cap.grab(region))
        except OCRUnavailable as exc:
            messagebox.showerror("RuneMaker", str(exc))
            return
        message = f"OCR mana: {value if value is not None else 'nao reconhecido'}"
        self.log(message)
        messagebox.showinfo("RuneMaker", message)

    def test_sequence(self) -> None:
        """Roda um ciclo unico de criacao (dry-run ou real) - reaproveita
        exatamente a mesma logica do worker (`_craft_cycle`/`_simple_craft_cycle`)
        pra nao ter dois caminhos de codigo divergentes."""
        self.save_config()
        if self.cfg.get("mode") == "mana_training":
            messagebox.showinfo("RuneMaker", "Testar sequencia so se aplica ao modo 'Criar runas'.")
            return

        dry_run = bool(self.var_dry_run.get())
        if not dry_run and not messagebox.askyesno(
            "RuneMaker", "Modo REAL: isso vai clicar/arrastar de verdade. Continuar?"
        ):
            return

        cfg = dict(self.cfg)
        cfg.update(self.app.build_worker_extras())
        try:
            worker = RuneMakerWorker(cfg, self.app.events)
            worker.setup()
            if worker.no_hand_mode:
                ok = worker._simple_craft_cycle(dry_run=dry_run)
            else:
                ok = worker._craft_cycle(dry_run=dry_run)
            worker.teardown()
        except Exception as exc:
            messagebox.showerror("RuneMaker", f"Falha no teste: {exc}")
            return

        message = "Sequencia de teste concluida (ver log)." if ok else "Sequencia de teste falhou em alguma validacao (ver log)."
        messagebox.showinfo("RuneMaker", message)

    # -------------------------------------------------------------- controles
    def save_config(self) -> None:
        self.cfg["spell_hotkey"] = self.var_spell.get().strip().lower()
        self.cfg["amount"] = parse_int(self.var_amount.get(), 0)
        self.cfg["delay_min"] = parse_float(self.var_delay_min.get(), 1.5)
        self.cfg["delay_max"] = parse_float(self.var_delay_max.get(), 2.5)
        self.cfg["click_jitter"] = parse_int(self.var_jitter.get(), 2)
        self.cfg["min_mana"] = parse_int(self.var_min_mana.get(), 300)
        self.cfg["check_mana"] = bool(self.var_check_mana.get())
        self.cfg["mode"] = MODE_VALUES.get(self.var_mode.get(), "craft")
        self.cfg["no_hand_mode"] = bool(self.var_no_hand.get())
        coverage_pct = max(0, min(100, parse_int(self.var_empty_threshold.get(), 90)))
        self.cfg["empty_match_threshold"] = coverage_pct / 100
        self.app.config_store.save()

    def start(self) -> None:
        self.save_config()
        mode = self.cfg.get("mode")
        if mode != "mana_training":
            if not self.cfg.get("blank_slot"):
                messagebox.showwarning("RuneMaker", "Selecione o slot da blank rune primeiro.")
                return
            if not self.cfg.get("no_hand_mode"):
                if not self.cfg.get("hand_slot"):
                    messagebox.showwarning("RuneMaker", "Selecione o slot da mao do personagem primeiro.")
                    return
                if not self.cfg.get("output_slot"):
                    messagebox.showwarning("RuneMaker", "Selecione o slot livre de destino primeiro.")
                    return
        self.app.start_worker(self.worker_key, RuneMakerWorker, dict(self.cfg))

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
        lock_state = "disabled" if running else "normal"
        self.radio_craft.configure(state=lock_state)
        self.radio_mana_training.configure(state=lock_state)
        self.chk_no_hand.configure(state=lock_state)
        if running:
            self.mana_overlay.show()
        else:
            self.mana_overlay.hide()

    def on_counter(self, value: int) -> None:
        self.var_counter.set(str(value))

    def on_mana_reading(self, value) -> None:
        self.mana_overlay.update_value(value)
