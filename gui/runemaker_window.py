"""Aba RuneMaker: configuracao, teste de OCR e controle da criacao de runas."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from core.screen_capture import ScreenCapture, is_valid_region
from core.tesseract_installer import _bundled_installer_path, find_tesseract, install_tesseract
from functions.rune_maker import OCRUnavailable, RuneMakerWorker, configure_tesseract, read_number
from gui.widgets import LogPanel, ScrollableFrame, add_field, parse_float, parse_int, region_text


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
        self.var_tesseract = tk.StringVar(value=self.cfg.get("tesseract_cmd", ""))
        self.var_slot = tk.StringVar(value=region_text(self.cfg.get("blank_slot")))
        self.var_mana_region = tk.StringVar(value=region_text(self.cfg.get("mana_region")))
        self.var_status = tk.StringVar(value="parado")
        self.var_counter = tk.StringVar(value="0")

        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        self.body = scroll.body
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._build()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        body = self.body
        # Magia e alvo ------------------------------------------------------
        box_spell = ttk.LabelFrame(body, text="1. Magia e blank runes")
        box_spell.grid(row=0, column=0, sticky="ew", pady=4)
        add_field(box_spell, 0, "Tecla da magia", self.var_spell, 8, "hotkey configurada no jogo (ex: f2)")
        add_field(box_spell, 1, "Quantidade de runas", self.var_amount, 8, "0 = ate acabar a mana")

        ttk.Button(box_spell, text="Selecionar slot da blank rune...", command=self.pick_slot).grid(
            row=2, column=0, padx=4, pady=6, sticky="w"
        )
        ttk.Label(box_spell, textvariable=self.var_slot).grid(row=2, column=1, columnspan=2, sticky="w")

        # OCR ---------------------------------------------------------------
        box_ocr = ttk.LabelFrame(body, text="2. Limites de seguranca (OCR)")
        box_ocr.grid(row=1, column=0, sticky="ew", pady=4)

        ttk.Checkbutton(box_ocr, text="Verificar mana", variable=self.var_check_mana).grid(
            row=0, column=0, sticky="w", padx=4, pady=3
        )
        ttk.Button(box_ocr, text="Regiao da mana...", command=lambda: self.pick_ocr_region("mana")).grid(
            row=0, column=1, padx=4
        )
        ttk.Label(box_ocr, textvariable=self.var_mana_region).grid(row=0, column=2, sticky="w", padx=4)

        add_field(box_ocr, 1, "Mana minima", self.var_min_mana, 8, "pausa abaixo disso")
        add_field(box_ocr, 2, "Caminho do Tesseract", self.var_tesseract, 36, "vazio = usar o PATH")

        ttk.Button(box_ocr, text="Testar OCR", command=self.test_ocr).grid(
            row=3, column=0, padx=4, pady=6, sticky="w"
        )
        ttk.Button(
            box_ocr, text="Instalar Tesseract automaticamente...", command=self.install_tesseract
        ).grid(row=3, column=1, columnspan=2, padx=4, pady=6, sticky="w")

        # Ritmo -------------------------------------------------------------
        box_rate = ttk.LabelFrame(body, text="3. Ritmo")
        box_rate.grid(row=2, column=0, sticky="ew", pady=4)
        add_field(box_rate, 0, "Delay minimo (s)", self.var_delay_min, 8, ">= cooldown real da magia")
        add_field(box_rate, 1, "Delay maximo (s)", self.var_delay_max, 8, "ex: 2.5")
        add_field(box_rate, 2, "Variacao do clique (px)", self.var_jitter, 8, "+/- pixels")

        # Controles ---------------------------------------------------------
        box_run = ttk.LabelFrame(body, text="4. Execucao")
        box_run.grid(row=3, column=0, sticky="ew", pady=4)
        self.btn_start = ttk.Button(box_run, text="Iniciar", command=self.start)
        self.btn_start.grid(row=0, column=0, padx=4, pady=6)
        self.btn_pause = ttk.Button(box_run, text="Pausar/Retomar", command=self.toggle_pause, state="disabled")
        self.btn_pause.grid(row=0, column=1, padx=4)
        self.btn_stop = ttk.Button(box_run, text="Parar", command=self.stop, state="disabled")
        self.btn_stop.grid(row=0, column=2, padx=4)
        ttk.Button(box_run, text="Salvar config", command=self.save_config).grid(row=0, column=3, padx=12)

        ttk.Label(box_run, text="Status:").grid(row=1, column=0, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_status, font=("Segoe UI", 9, "bold")).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(box_run, text="Runas criadas:").grid(row=1, column=2, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_counter, font=("Segoe UI", 9, "bold")).grid(
            row=1, column=3, sticky="w"
        )

        self.log_panel = LogPanel(body, title="Log", height=9)
        self.log_panel.grid(row=4, column=0, sticky="nsew", pady=4)

        body.columnconfigure(0, weight=1)

    # --------------------------------------------------------------- selecao
    def pick_slot(self) -> None:
        point = self.app.select_point("Clique no slot da BLANK RUNE  -  ESC cancela")
        if point:
            self.cfg["blank_slot"] = list(point)
            self.var_slot.set(region_text(point))
            self.app.config_store.save()
            self.log(f"Slot da blank rune definido: {region_text(point)}")

    def pick_ocr_region(self, key: str) -> None:
        label = "MANA"
        region = self.app.select_region(f"Selecione o numero de {label} na barra de status  -  ESC cancela")
        if not region:
            return
        self.cfg[f"{key}_region"] = region
        self.var_mana_region.set(region_text(region))
        self.app.config_store.save()
        self.log(f"Regiao de {label} definida: {region_text(region)}")

    def test_ocr(self) -> None:
        """Le a mana uma unica vez e mostra o que o Tesseract entendeu."""
        self.save_config()
        configure_tesseract(self.cfg.get("tesseract_cmd"))

        region = self.cfg.get("mana_region")
        if not is_valid_region(region):
            self.log("Regiao de mana nao configurada.")
            return
        try:
            with ScreenCapture() as cap:
                value = read_number(cap.grab(region))
        except OCRUnavailable as exc:
            messagebox.showerror("RuneMaker", str(exc))
            return
        self.log(f"OCR mana: {value if value is not None else 'nao reconhecido'}")

    def install_tesseract(self) -> None:
        """Baixa e instala o Tesseract OCR silenciosamente, se ainda nao
        estiver presente no PATH ou no local padrao de instalacao."""
        existing = find_tesseract()
        if existing:
            messagebox.showinfo("RuneMaker", f"Tesseract ja instalado em:\n{existing}")
            return
        if _bundled_installer_path():
            action = "Instalar automaticamente agora? (ja incluso no programa, sem download)"
        else:
            action = "Baixar e instalar automaticamente agora? (~25 MB, alguns segundos)"
        if not messagebox.askyesno(
            "RuneMaker",
            f"O Tesseract OCR (usado pra ler a mana) nao foi encontrado.\n\n{action}",
        ):
            return

        def report(msg: str) -> None:
            self.log(msg)
            self.update_idletasks()

        ok, message = install_tesseract(on_progress=report)
        self.log(message)
        if ok:
            messagebox.showinfo("RuneMaker", message)
        else:
            messagebox.showerror("RuneMaker", message)

    # -------------------------------------------------------------- controles
    def save_config(self) -> None:
        self.cfg["spell_hotkey"] = self.var_spell.get().strip().lower()
        self.cfg["amount"] = parse_int(self.var_amount.get(), 0)
        self.cfg["delay_min"] = parse_float(self.var_delay_min.get(), 1.5)
        self.cfg["delay_max"] = parse_float(self.var_delay_max.get(), 2.5)
        self.cfg["click_jitter"] = parse_int(self.var_jitter.get(), 2)
        self.cfg["min_mana"] = parse_int(self.var_min_mana.get(), 300)
        self.cfg["check_mana"] = bool(self.var_check_mana.get())
        self.cfg["tesseract_cmd"] = self.var_tesseract.get().strip()
        self.app.config_store.save()

    def start(self) -> None:
        self.save_config()
        if not self.cfg.get("blank_slot"):
            messagebox.showwarning("RuneMaker", "Selecione o slot da blank rune primeiro.")
            return
        self.app.start_worker(self.worker_key, RuneMakerWorker, dict(self.cfg))

    def toggle_pause(self) -> None:
        self.app.toggle_pause(self.worker_key)

    def stop(self) -> None:
        self.app.stop_worker(self.worker_key)

    # ------------------------------------------------------------- callbacks
    def log(self, message: str) -> None:
        self.log_panel.append(message)

    def on_state(self, state: str) -> None:
        self.var_status.set(state)
        running = state in ("running", "paused")
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_pause.configure(state="normal" if running else "disabled")
        self.btn_stop.configure(state="normal" if running else "disabled")

    def on_counter(self, value: int) -> None:
        self.var_counter.set(str(value))
