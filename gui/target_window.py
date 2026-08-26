from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.target import TargetWorker
from gui.widgets import ScrollableFrame, add_field, add_hotkey_field, parse_float, parse_int, region_text


class TargetWindow(ttk.Frame):
    worker_key = "target"

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.cfg = app.config_store.section("target")

        self.var_region = tk.StringVar(value=region_text(self.cfg.get("battle_list_region")))
        self.var_empty_template = tk.StringVar(
            value="Modelo calibrado" if self.cfg.get("battle_empty_template") else "nao calibrado"
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

        self.var_dry_run = tk.BooleanVar(value=True)
        self.var_status = tk.StringVar(value="parado")
        self.var_counter = tk.StringVar(value="0")

        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        self.body = scroll.body
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._build()

        self._config_dialog = tk.Toplevel(self)
        self._config_dialog.title("Configurar - Target")
        self._config_dialog.geometry("640x480")
        self._config_dialog.transient(self.winfo_toplevel())
        self._config_dialog.protocol("WM_DELETE_WINDOW", self._hide_config_dialog)
        config_scroll = ScrollableFrame(self._config_dialog)
        config_scroll.pack(fill="both", expand=True)
        self._build_config_dialog(config_scroll.body)
        self._config_dialog.withdraw()

    def _build(self) -> None:
        body = self.body

        box_run = ttk.LabelFrame(body, text="1. Execucao")
        box_run.grid(row=0, column=0, sticky="ew", pady=4)

        actions = ttk.Frame(box_run)
        actions.grid(row=0, column=0, columnspan=4, sticky="w", pady=(2, 6))
        ttk.Checkbutton(
            actions, text="Modo teste (dry-run: so loga, nao aperta a tecla)", variable=self.var_dry_run
        ).pack(side="left", padx=4)
        ttk.Button(actions, text="Testar leitura da Battle List", command=self.test_read).pack(side="left", padx=8)
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
        ttk.Label(box_run, text="Ataques disparados:").grid(row=2, column=2, sticky="e", padx=4)
        ttk.Label(box_run, textvariable=self.var_counter, font=("Segoe UI", 9, "bold")).grid(
            row=2, column=3, sticky="w"
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

        ttk.Button(box_list, text="Selecionar regiao da Battle List...", command=self.pick_battle_list_region).grid(
            row=0, column=0, padx=4, pady=6, sticky="w"
        )
        ttk.Label(box_list, textvariable=self.var_region).grid(row=0, column=1, sticky="w")
        ttk.Label(
            box_list,
            text="Arraste cobrindo toda a area visivel da lista (varias linhas) - usada pra "
            "conferir a cor de ataque em qualquer linha.",
            foreground="#666",
            wraplength=580,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=4)

        ttk.Button(
            box_list, text="Capturar modelo de lista vazia (cabecalho + 1a linha)...",
            command=self.capture_empty_template,
        ).grid(row=2, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(box_list, textvariable=self.var_empty_template).grid(row=2, column=1, sticky="w")
        ttk.Label(
            box_list,
            text="Com a lista VAZIA no jogo, arraste incluindo o titulo da janela 'Battle' + a "
            "1a linha (vazia) logo abaixo - esse recorte maior identifica melhor e dispensa "
            "saber quantas linhas cabem na Battle List.",
            foreground="#666",
            wraplength=580,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=4)

        add_field(
            box_list, 4, "Confianca minima do modelo vazio (%)", self.var_empty_threshold, 8, "0 a 100 (padrao 85)"
        )

        box_color = ttk.LabelFrame(parent, text="2. Cor de ataque (nome da criatura)")
        box_color.grid(row=1, column=0, sticky="ew", pady=4)
        color_row = ttk.Frame(box_color)
        color_row.grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=3)
        ttk.Label(color_row, text="RGB:").pack(side="left", padx=(0, 4))
        ttk.Entry(color_row, textvariable=self.var_color_r, width=5).pack(side="left")
        ttk.Entry(color_row, textvariable=self.var_color_g, width=5).pack(side="left", padx=4)
        ttk.Entry(color_row, textvariable=self.var_color_b, width=5).pack(side="left")
        add_field(box_color, 1, "Tolerancia por canal", self.var_color_tolerance, 8, "0 a 255 (padrao 6)")
        add_field(box_color, 2, "Pixels minimos", self.var_color_min_pixels, 8, "padrao 3")
        ttk.Label(
            box_color,
            text="Sem variante de hover: o ataque agora e por tecla de atalho, o mouse nunca "
            "fica em cima da lista. Padrao RGB 254,0,0 (vermelho puro do nome em ATAQUE).",
            foreground="#666",
            wraplength=580,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=4)

        box_key = ttk.LabelFrame(parent, text="3. Tecla de ataque")
        box_key.grid(row=2, column=0, sticky="ew", pady=4)
        add_hotkey_field(box_key, 0, "Tecla de ataque", self.var_attack_key, 10, "ex: space")
        add_field(
            box_key, 1, "Delay apos apertar (s)", self.var_attack_check_delay, 8, "aguarda antes de conferir a cor"
        )
        ttk.Label(
            box_key,
            text="Precisa estar configurada DENTRO do Tibia primeiro (Options > Hotkeys > "
            "Attack) para atacar a criatura mais proxima/selecionada.",
            foreground="#a33",
            wraplength=580,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 0))

        box_rate = ttk.LabelFrame(parent, text="4. Ritmo")
        box_rate.grid(row=3, column=0, sticky="ew", pady=4)
        add_field(box_rate, 0, "Delay minimo (lista vazia) (s)", self.var_idle_min, 8, "ex: 2.0")
        add_field(box_rate, 1, "Delay maximo (lista vazia) (s)", self.var_idle_max, 8, "ex: 4.0")
        add_field(box_rate, 2, "Delay minimo (ja atacando) (s)", self.var_engaged_min, 8, "ex: 1.0")
        add_field(box_rate, 3, "Delay maximo (ja atacando) (s)", self.var_engaged_max, 8, "ex: 2.0")

        ttk.Label(
            parent,
            text="Aviso: esta funcao depende de leitura visual (template/cor) da Battle List. "
            "Mudar o tamanho da janela do jogo, o zoom ou a skin da Battle List depois de "
            "calibrar pode quebrar a deteccao - recalibre se isso acontecer.",
            foreground="#a33",
            wraplength=580,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(4, 0))

        actions_bar = ttk.Frame(parent)
        actions_bar.grid(row=5, column=0, sticky="e", pady=(8, 4))
        ttk.Button(actions_bar, text="Salvar config", command=self.save_config).pack(side="left", padx=4)
        ttk.Button(actions_bar, text="Fechar", command=self._hide_config_dialog).pack(side="left", padx=4)

        parent.columnconfigure(0, weight=1)

    def pick_battle_list_region(self) -> None:
        region = self.app.select_region(
            "Arraste cobrindo toda a area visivel da Battle List (cabecalho + linhas)  -  ESC cancela"
        )
        if not region:
            return
        self.cfg["battle_list_region"] = region
        self.var_region.set(region_text(region))
        self.app.config_store.save()
        self.log(f"Regiao da Battle List definida: {region_text(region)}")

    def capture_empty_template(self) -> None:
        region = self.app.select_region(
            "Com a lista VAZIA, selecione o cabecalho 'Battle' + a 1a linha (vazia)  -  ESC cancela"
        )
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, "target_battle_empty.png")
        save_image(path, frame)
        self.cfg["battle_empty_template"] = path
        self.var_empty_template.set(f"Modelo salvo ({region[2]}x{region[3]} px)")
        self.app.config_store.save()
        self.log(f"Modelo de lista vazia salvo em {path}")

    def worker_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(self.app.build_worker_extras())
        return cfg

    def test_read(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TargetWorker(dict(cfg), self.app.events)
            worker.setup()
        except Exception as exc:
            messagebox.showerror("Target", f"Falha ao preparar leitura: {exc}")
            return

        try:
            score = worker.battle_list_empty_score()
            vazia = worker.is_battle_list_empty()
            attacking = worker.is_attacking() if not vazia else False
        except Exception as exc:
            worker.teardown()
            messagebox.showerror("Target", f"Falha na leitura: {exc}")
            return
        worker.teardown()

        score_text = f"{score * 100:.1f}%" if score is not None else "modelo maior que a regiao"
        message = (
            f"Battle List vazia: {'sim' if vazia else 'nao'} (confianca: {score_text}, minimo: "
            f"{worker.empty_threshold * 100:.0f}%)\n"
            f"Cor de ataque detectada: {'sim' if attacking else 'nao'}"
        )
        self.log(message.replace("\n", " | "))
        messagebox.showinfo("Target - Testar leitura", message)

    def test_attack_key(self) -> None:
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TargetWorker(dict(cfg), self.app.events)
            worker.setup()
        except Exception as exc:
            messagebox.showerror("Target", f"Falha ao preparar teste: {exc}")
            return

        try:
            dry_run = bool(self.var_dry_run.get())
            if not dry_run and not messagebox.askyesno(
                "Target", f"Modo REAL: isso vai apertar a tecla '{worker.attack_key}' de verdade. Continuar?"
            ):
                return
            worker.press_attack_key(dry_run=dry_run)
        except Exception as exc:
            messagebox.showerror("Target", f"Falha no teste da tecla de ataque: {exc}")
            return
        finally:
            worker.teardown()

        self.log(f"Teste da tecla de ataque concluido ('{worker.attack_key}').")
        messagebox.showinfo("Target", f"Tecla de ataque testada ('{worker.attack_key}' - ver log).")

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
        self.app.config_store.save()

    def start(self) -> None:
        self.save_config()
        if not is_valid_region(self.cfg.get("battle_list_region")):
            messagebox.showwarning("Target", "Selecione a regiao da Battle List primeiro.")
            return
        if not self.cfg.get("battle_empty_template"):
            messagebox.showwarning("Target", "Capture o modelo de lista vazia primeiro.")
            return
        self.app.start_worker(self.worker_key, TargetWorker, self.worker_config())

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

    def on_counter(self, value: int) -> None:
        self.var_counter.set(str(value))
