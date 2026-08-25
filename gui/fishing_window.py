"""Aba AutoFishing: configuracao, calibracao e controle da rotina de pesca."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

import cv2

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.auto_fishing import AutoFishingWorker, draw_tile_grid, sample_hsv_range
from gui.widgets import LogPanel, ScrollableFrame, add_field, parse_float, parse_int, region_text

# O worker/InputSimulator so reconhecem os valores internos "right"/"left" -
# esse mapeamento so existe para exibir rotulos em portugues na interface.
BUTTON_LABELS = {"right": "direito", "left": "esquerdo"}
BUTTON_VALUES = {label: value for value, label in BUTTON_LABELS.items()}


class FishingWindow(ttk.Frame):
    worker_key = "fishing"

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.cfg = app.config_store.section("fishing")

        # --------------------------------------------------- variaveis da GUI
        self.var_mode = tk.StringVar(value=self.cfg.get("detection_mode", "hsv"))
        self.var_hsv_lower = tk.StringVar(value=", ".join(map(str, self.cfg.get("hsv_lower"))))
        self.var_hsv_upper = tk.StringVar(value=", ".join(map(str, self.cfg.get("hsv_upper"))))
        self.var_min_area = tk.StringVar(value=str(self.cfg.get("min_area")))
        self.var_tile_size = tk.StringVar(value=str(self.cfg.get("tile_size", 32)))
        self.var_tile_coverage = tk.StringVar(
            value=str(int(self.cfg.get("min_tile_coverage", 0.35) * 100))
        )
        self.var_threshold = tk.StringVar(value=str(self.cfg.get("template_threshold")))
        self.var_button = tk.StringVar(
            value=BUTTON_LABELS.get(self.cfg.get("mouse_button", "right"), "direito")
        )
        self.var_delay_min = tk.StringVar(value=str(self.cfg.get("delay_min")))
        self.var_delay_max = tk.StringVar(value=str(self.cfg.get("delay_max")))
        self.var_jitter = tk.StringVar(value=str(self.cfg.get("click_jitter")))
        self.var_max_casts = tk.StringVar(value=str(self.cfg.get("max_casts")))
        self.var_randomize = tk.BooleanVar(value=bool(self.cfg.get("randomize_target", True)))
        self.var_region = tk.StringVar(value=region_text(self.cfg.get("region")))
        self.var_rod_slot = tk.StringVar(value=region_text(self.cfg.get("rod_slot")))
        self.var_break_enabled = tk.BooleanVar(value=bool(self.cfg.get("break_enabled", True)))
        self.var_break_interval_min = tk.StringVar(value=str(self.cfg.get("break_interval_min", 60)))
        self.var_break_interval_max = tk.StringVar(value=str(self.cfg.get("break_interval_max", 300)))
        self.var_break_duration_min = tk.StringVar(value=str(self.cfg.get("break_duration_min", 15)))
        self.var_break_duration_max = tk.StringVar(value=str(self.cfg.get("break_duration_max", 120)))
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
        # Vara de pescar ------------------------------------------------------
        box_rod = ttk.LabelFrame(body, text="1. Vara de pescar")
        box_rod.grid(row=0, column=0, sticky="ew", pady=4)
        box_rod.columnconfigure(1, weight=1)
        ttk.Button(box_rod, text="Selecionar posicao da vara...", command=self.pick_rod_slot).grid(
            row=0, column=0, padx=4, pady=6
        )
        ttk.Label(box_rod, textvariable=self.var_rod_slot).grid(row=0, column=1, sticky="w")

        # Regiao monitorada -------------------------------------------------
        box_region = ttk.LabelFrame(body, text="2. Regiao monitorada (lago)")
        box_region.grid(row=1, column=0, sticky="ew", pady=4)
        box_region.columnconfigure(1, weight=1)
        ttk.Button(box_region, text="Selecionar regiao...", command=self.pick_region).grid(
            row=0, column=0, padx=4, pady=6
        )
        ttk.Label(box_region, textvariable=self.var_region).grid(row=0, column=1, sticky="w")

        # Deteccao ----------------------------------------------------------
        box_detect = ttk.LabelFrame(body, text="3. Deteccao de agua")
        box_detect.grid(row=2, column=0, sticky="ew", pady=4)

        ttk.Label(box_detect, text="Modo").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        combo = ttk.Combobox(
            box_detect,
            textvariable=self.var_mode,
            values=["hsv", "template"],
            state="readonly",
            width=10,
        )
        combo.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(
            box_detect, text="hsv = cor da agua | template = imagem de referencia", foreground="#666"
        ).grid(row=0, column=2, sticky="w", padx=4)

        add_field(box_detect, 1, "HSV minimo", self.var_hsv_lower, 16, "H, S, V")
        add_field(box_detect, 2, "HSV maximo", self.var_hsv_upper, 16, "H, S, V")
        add_field(box_detect, 3, "Area minima", self.var_min_area, 8, "px de agua na regiao")
        add_field(box_detect, 4, "Threshold template", self.var_threshold, 8, "0.0 a 1.0")
        add_field(
            box_detect, 5, "Tamanho do SQM (px)", self.var_tile_size, 8, "32 = tile padrao sem zoom"
        )
        add_field(
            box_detect, 6, "Cobertura minima do SQM (%)", self.var_tile_coverage, 8, "0 a 100"
        )

        actions = ttk.Frame(box_detect)
        actions.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 6))
        ttk.Button(actions, text="Calibrar cor da agua...", command=self.calibrate_color).pack(
            side="left", padx=4
        )
        ttk.Button(actions, text="Capturar template...", command=self.capture_template).pack(
            side="left", padx=4
        )
        ttk.Button(actions, text="Testar deteccao", command=self.test_detection).pack(
            side="left", padx=4
        )
        ttk.Button(actions, text="Visualizar grid (SQM)...", command=self.preview_grid).pack(
            side="left", padx=4
        )

        # Clique e ritmo ----------------------------------------------------
        box_click = ttk.LabelFrame(body, text="4. Clique e ritmo")
        box_click.grid(row=3, column=0, sticky="ew", pady=4)

        ttk.Label(box_click, text="Botao na agua").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Combobox(
            box_click,
            textvariable=self.var_button,
            values=["direito", "esquerdo"],
            state="readonly",
            width=10,
        ).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(
            box_click,
            text="obs: a vara (aba 1) usa sempre o botao direito - isso aqui e so pra agua",
            foreground="#666",
        ).grid(row=0, column=2, sticky="w", padx=4)

        add_field(box_click, 1, "Delay minimo (s)", self.var_delay_min, 8, "ex: 1.8")
        add_field(box_click, 2, "Delay maximo (s)", self.var_delay_max, 8, "ex: 3.2")
        add_field(box_click, 3, "Variacao do clique (px)", self.var_jitter, 8, "+/- pixels")
        add_field(box_click, 4, "Limite de lances", self.var_max_casts, 8, "0 = ilimitado")
        ttk.Checkbutton(
            box_click,
            text="Sortear entre as tiles de agua encontradas",
            variable=self.var_randomize,
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=4, pady=3)

        # Pausas periodicas ---------------------------------------------------
        box_break = ttk.LabelFrame(body, text="5. Pausas periodicas (descanso)")
        box_break.grid(row=4, column=0, sticky="ew", pady=4)
        ttk.Checkbutton(
            box_break, text="Ativar pausas periodicas", variable=self.var_break_enabled
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=3)
        add_field(
            box_break, 1, "Pesca no minimo (s)", self.var_break_interval_min, 8, "antes de considerar pausa"
        )
        add_field(
            box_break, 2, "Pesca no maximo (s)", self.var_break_interval_max, 8, "ex: 300 = ate 5 min"
        )
        add_field(
            box_break, 3, "Pausa minima (s)", self.var_break_duration_min, 8, "duracao minima do descanso"
        )
        add_field(
            box_break, 4, "Pausa maxima (s)", self.var_break_duration_max, 8, "ex: 120 = ate 2 min"
        )

        # Controles ---------------------------------------------------------
        box_run = ttk.LabelFrame(body, text="6. Execucao")
        box_run.grid(row=5, column=0, sticky="ew", pady=4)
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
        ttk.Label(box_run, text="Lances na sessao:").grid(row=1, column=2, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_counter, font=("Segoe UI", 9, "bold")).grid(
            row=1, column=3, sticky="w"
        )

        # Log ---------------------------------------------------------------
        self.log_panel = LogPanel(body, title="Log", height=9)
        self.log_panel.grid(row=6, column=0, sticky="nsew", pady=4)

        body.columnconfigure(0, weight=1)

    # ------------------------------------------------------------ calibracao
    def pick_rod_slot(self) -> None:
        point = self.app.select_point("Clique na posicao da VARA DE PESCAR  -  ESC cancela")
        if point:
            self.cfg["rod_slot"] = list(point)
            self.var_rod_slot.set(region_text(point))
            self.app.config_store.save()
            self.log(f"Posicao da vara definida: {region_text(point)}")

    def pick_region(self) -> None:
        region = self.app.select_region("Arraste sobre a area de pesca  -  ESC cancela")
        if region:
            self.cfg["region"] = region
            self.var_region.set(region_text(region))
            self.app.config_store.save()
            self.log(f"Regiao de pesca definida: {region_text(region)}")

    def calibrate_color(self) -> None:
        """Usuario recorta um pedaco de agua; derivamos a faixa HSV dele."""
        region = self.app.select_region("Selecione um pedaco de AGUA  -  ESC cancela")
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        lower, upper = sample_hsv_range(frame)
        self.var_hsv_lower.set(", ".join(map(str, lower)))
        self.var_hsv_upper.set(", ".join(map(str, upper)))
        self.var_mode.set("hsv")
        self.save_config()
        self.log(f"Cor calibrada: HSV {lower} - {upper}")

    def capture_template(self) -> None:
        """Usuario recorta uma tile de agua; salvamos como template PNG."""
        region = self.app.select_region("Selecione UMA tile de agua  -  ESC cancela")
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, self.cfg.get("template_file", "water_template.png"))
        save_image(path, frame)
        self.var_mode.set("template")
        self.save_config()
        self.log(f"Template salvo em {path} ({region[2]}x{region[3]} px)")

    def test_detection(self) -> None:
        """Roda a deteccao uma unica vez e informa quantas tiles foram achadas."""
        self.save_config()
        cfg = self.worker_config()
        if not is_valid_region(cfg.get("region")):
            messagebox.showwarning("AutoFishing", "Selecione a regiao monitorada primeiro.")
            return
        try:
            worker = AutoFishingWorker(cfg, self.app.events)
            worker.setup()
            with ScreenCapture() as cap:
                frame = cap.grab(cfg["region"])
            targets = worker.detect(frame)
            worker.teardown()
        except Exception as exc:
            messagebox.showerror("AutoFishing", f"Falha no teste: {exc}")
            return
        self.log(f"Teste de deteccao: {len(targets)} SQM(s) de agua encontrado(s).")
        if targets:
            cx, cy, score = targets[0]
            self.log(f"Melhor candidato (relativo a regiao): x={cx} y={cy} score/cobertura={score}")

    def preview_grid(self) -> None:
        """Mostra o grid de SQM sobre a regiao, com os tiles validos marcados."""
        self.save_config()
        cfg = self.worker_config()
        if not is_valid_region(cfg.get("region")):
            messagebox.showwarning("AutoFishing", "Selecione a regiao monitorada primeiro.")
            return
        try:
            worker = AutoFishingWorker(cfg, self.app.events)
            worker.setup()
            with ScreenCapture() as cap:
                frame = cap.grab(cfg["region"])
            targets = worker.detect(frame)
            worker.teardown()
        except Exception as exc:
            messagebox.showerror("AutoFishing", f"Falha no teste: {exc}")
            return

        tile_size = max(4, parse_int(self.var_tile_size.get(), 32))
        preview = draw_tile_grid(frame, targets, tile_size)
        self.log(f"Grid de SQM: {len(targets)} tile(s) valido(s) - feche a janela para continuar.")
        cv2.imshow("AutoFishing - grid de SQM (ESC ou fechar a janela)", preview)
        cv2.waitKey(0)
        cv2.destroyWindow("AutoFishing - grid de SQM (ESC ou fechar a janela)")

    # -------------------------------------------------------------- controles
    def worker_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg["template_path"] = os.path.join(
            ASSETS_DIR, self.cfg.get("template_file", "water_template.png")
        )
        return cfg

    def save_config(self) -> None:
        def parse_triple(text: str, fallback: list[int]) -> list[int]:
            parts = [p for p in str(text).replace(";", ",").split(",") if p.strip()]
            if len(parts) != 3:
                return fallback
            return [max(0, parse_int(p, 0)) for p in parts]

        self.cfg["detection_mode"] = self.var_mode.get()
        self.cfg["hsv_lower"] = parse_triple(self.var_hsv_lower.get(), self.cfg["hsv_lower"])
        self.cfg["hsv_upper"] = parse_triple(self.var_hsv_upper.get(), self.cfg["hsv_upper"])
        self.cfg["min_area"] = parse_int(self.var_min_area.get(), 200)
        self.cfg["tile_size"] = max(4, parse_int(self.var_tile_size.get(), 32))
        coverage_pct = max(0, min(100, parse_int(self.var_tile_coverage.get(), 35)))
        self.cfg["min_tile_coverage"] = coverage_pct / 100
        self.cfg["template_threshold"] = parse_float(self.var_threshold.get(), 0.80)
        self.cfg["mouse_button"] = BUTTON_VALUES.get(self.var_button.get(), "right")
        self.cfg["delay_min"] = parse_float(self.var_delay_min.get(), 1.8)
        self.cfg["delay_max"] = parse_float(self.var_delay_max.get(), 3.2)
        self.cfg["click_jitter"] = parse_int(self.var_jitter.get(), 2)
        self.cfg["max_casts"] = parse_int(self.var_max_casts.get(), 0)
        self.cfg["randomize_target"] = bool(self.var_randomize.get())
        self.cfg["break_enabled"] = bool(self.var_break_enabled.get())
        self.cfg["break_interval_min"] = parse_int(self.var_break_interval_min.get(), 30)
        self.cfg["break_interval_max"] = parse_int(self.var_break_interval_max.get(), 300)
        self.cfg["break_duration_min"] = parse_int(self.var_break_duration_min.get(), 10)
        self.cfg["break_duration_max"] = parse_int(self.var_break_duration_max.get(), 120)
        self.app.config_store.save()

    def start(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        if not self.cfg.get("rod_slot"):
            messagebox.showwarning("AutoFishing", "Selecione a posicao da vara de pescar primeiro.")
            return
        if not is_valid_region(cfg.get("region")):
            messagebox.showwarning("AutoFishing", "Selecione a regiao monitorada primeiro.")
            return
        self.app.start_worker(self.worker_key, AutoFishingWorker, cfg)

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
