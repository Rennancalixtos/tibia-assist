"""Aba Target: le a Battle List e ataca a primeira criatura valida."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from core.config import ASSETS_DIR
from core.screen_capture import ScreenCapture, is_valid_region, save_image
from functions.target import TargetWorker, sample_name_text_color
from gui.widgets import ScrollableFrame, add_field, parse_float, parse_int, region_text

ATTACK_MODE_LABELS = {
    "single_click": "Clique simples",
    "double_click": "Clique duplo",
    "context_menu": "Botao direito + menu",
}
ATTACK_MODE_VALUES = {label: value for value, label in ATTACK_MODE_LABELS.items()}

FILTER_MODE_LABELS = {
    "whitelist": "Atacar somente estes",
    "blacklist": "Atacar todos, exceto estes",
}
FILTER_MODE_VALUES = {label: value for value, label in FILTER_MODE_LABELS.items()}


def offset_text(offset) -> str:
    """Formata um offset [dx, dy, (w, h)] relativo a uma linha - mesma ideia
    de `region_text`, mas com rotulo "dx/dy" pra nao confundir com coordenada
    absoluta de tela."""
    if not offset:
        return "nao configurado"
    if len(offset) == 4:
        return f"dx={offset[0]}  dy={offset[1]}  {offset[2]}x{offset[3]}"
    return f"dx={offset[0]}  dy={offset[1]}"


class TargetWindow(ttk.Frame):
    worker_key = "target"

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.cfg = app.config_store.section("target")

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
        self.var_life_offset = tk.StringVar(value=offset_text(self.cfg.get("life_bar_offset")))
        self.var_name_threshold = tk.StringVar(
            value=str(int(float(self.cfg.get("name_match_threshold", 0.80)) * 100))
        )

        self.var_attack_mode = tk.StringVar(
            value=ATTACK_MODE_LABELS.get(self.cfg.get("attack_mode", "single_click"), "Clique simples")
        )
        self.var_menu_offset = tk.StringVar(value=offset_text(self.cfg.get("context_menu_offset")))

        self.var_filter_mode = tk.StringVar(
            value=FILTER_MODE_LABELS.get(self.cfg.get("filter_mode", "blacklist"), "Atacar todos, exceto estes")
        )
        self.var_new_name = tk.StringVar()

        self.var_delay_min = tk.StringVar(value=str(self.cfg.get("delay_min", 0.6)))
        self.var_delay_max = tk.StringVar(value=str(self.cfg.get("delay_max", 1.4)))
        self.var_idle_min = tk.StringVar(value=str(self.cfg.get("idle_delay_min", 2.0)))
        self.var_idle_max = tk.StringVar(value=str(self.cfg.get("idle_delay_max", 4.0)))
        self.var_jitter = tk.StringVar(value=str(self.cfg.get("click_jitter", 2)))

        self.var_dry_run = tk.BooleanVar(value=True)
        self.var_status = tk.StringVar(value="parado")
        self.var_counter = tk.StringVar(value="0")

        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        self.body = scroll.body
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._build()

        # Dialogo de configuracao (secoes 1 a 6) - construido ja aqui (nao so
        # no primeiro clique em "Configurar...") pra que os widgets ja
        # existam quando `_on_attack_mode_change` roda logo abaixo (ver
        # `open_config_dialog`).
        self._config_dialog = tk.Toplevel(self)
        self._config_dialog.title("Configurar - Target")
        self._config_dialog.geometry("640x600")
        self._config_dialog.transient(self.winfo_toplevel())
        self._config_dialog.protocol("WM_DELETE_WINDOW", self._hide_config_dialog)
        config_scroll = ScrollableFrame(self._config_dialog)
        config_scroll.pack(fill="both", expand=True)
        self._build_config_dialog(config_scroll.body)
        self._config_dialog.withdraw()

        self._on_attack_mode_change()

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
        ttk.Button(actions, text="Testar leitura da Battle List", command=self.test_read).pack(side="left", padx=8)
        ttk.Button(actions, text="Testar clique de ataque", command=self.test_attack_click).pack(side="left", padx=8)

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
        ttk.Label(box_run, text="Alvos atacados:").grid(row=2, column=2, sticky="e", padx=4)
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

    # ------------------------------------------------------- dialogo de config
    def _build_config_dialog(self, parent) -> None:
        # Battle List ---------------------------------------------------------
        box_list = ttk.LabelFrame(parent, text="1. Battle List")
        box_list.grid(row=0, column=0, sticky="ew", pady=4)

        ttk.Button(
            box_list, text="Calibracao guiada (todos os passos abaixo, em sequencia)...",
            command=self.calibrate_all,
        ).grid(row=0, column=0, columnspan=2, padx=4, pady=(6, 10), sticky="w")

        ttk.Button(box_list, text="Selecionar regiao da Battle List...", command=self.pick_battle_list_region).grid(
            row=1, column=0, padx=4, pady=6, sticky="w"
        )
        ttk.Label(box_list, textvariable=self.var_region).grid(row=1, column=1, sticky="w")

        ttk.Button(box_list, text="Calibrar altura de linha...", command=self.calibrate_row_height).grid(
            row=2, column=0, padx=4, pady=6, sticky="w"
        )
        ttk.Label(box_list, textvariable=self.var_row_height).grid(row=2, column=1, sticky="w")

        ttk.Button(
            box_list, text="Capturar linha vazia (template)...", command=self.capture_row_empty_template
        ).grid(row=3, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(box_list, textvariable=self.var_empty_template).grid(row=3, column=1, sticky="w")

        self.entry_empty_threshold = add_field(
            box_list, 4, "Cobertura minima do slot vazio (%)", self.var_empty_threshold, 8, "0 a 100 (padrao 90)"
        )

        # Nome (OCR) ----------------------------------------------------------
        box_name = ttk.LabelFrame(parent, text="2. Leitura do nome (OCR)")
        box_name.grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(
            box_name, text="Selecionar faixa de texto do nome...", command=self.pick_name_crop
        ).grid(row=0, column=0, padx=4, pady=6, sticky="w")
        ttk.Label(box_name, textvariable=self.var_name_offset).grid(row=0, column=1, sticky="w")
        ttk.Label(
            box_name,
            text="Selecione numa linha OCUPADA, so a faixa de texto (nao o icone/barra de vida).",
            foreground="#666",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=4)

        # Selecao (borda) -------------------------------------------------------
        box_color = ttk.LabelFrame(parent, text="3. Deteccao de selecao (cor do nome attack/follow)")
        box_color.grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Button(
            box_color, text="Calibrar cor do nome em ATAQUE (vermelho)...",
            command=lambda: self._calibrate_name_color("attack"),
        ).grid(row=0, column=0, padx=4, pady=6, sticky="w")
        ttk.Button(
            box_color, text="Calibrar cor do nome em FOLLOW (verde)...",
            command=lambda: self._calibrate_name_color("follow"),
        ).grid(row=0, column=1, padx=4, pady=6, sticky="w")
        ttk.Label(box_color, textvariable=self.var_name_color_status).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=4
        )
        ttk.Label(
            box_color,
            text="Selecione o TEXTO do nome (mesma faixa usada no OCR), numa linha em cada "
            "estado - alguns clients mudam so a COR do nome, sem nenhuma borda separada.",
            foreground="#666",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=4)

        # Barra de vida (opcional) ---------------------------------------------
        box_life = ttk.LabelFrame(parent, text="3.1 Barra de vida (opcional - so exibida no teste)")
        box_life.grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Button(box_life, text="Selecionar barra de vida...", command=self.pick_life_bar).grid(
            row=0, column=0, padx=4, pady=6, sticky="w"
        )
        ttk.Label(box_life, textvariable=self.var_life_offset).grid(row=0, column=1, sticky="w")

        # Forma de ataque -------------------------------------------------------
        box_attack = ttk.LabelFrame(parent, text="4. Forma de ataque")
        box_attack.grid(row=4, column=0, sticky="ew", pady=4)
        for i, label in enumerate(ATTACK_MODE_LABELS.values()):
            ttk.Radiobutton(
                box_attack, text=label, value=label, variable=self.var_attack_mode,
                command=self._on_attack_mode_change,
            ).grid(row=0, column=i, sticky="w", padx=4, pady=3)

        self.btn_calibrate_menu = ttk.Button(
            box_attack, text="Calibrar deslocamento do menu de contexto...", command=self.calibrate_context_menu
        )
        self.btn_calibrate_menu.grid(row=1, column=0, columnspan=2, padx=4, pady=6, sticky="w")
        ttk.Label(box_attack, textvariable=self.var_menu_offset).grid(row=1, column=2, sticky="w")

        # Filtro de criaturas -----------------------------------------------
        box_filter = ttk.LabelFrame(parent, text="5. Filtro de criaturas")
        box_filter.grid(row=5, column=0, sticky="ew", pady=4)
        for i, label in enumerate(FILTER_MODE_LABELS.values()):
            ttk.Radiobutton(
                box_filter, text=label, value=label, variable=self.var_filter_mode
            ).grid(row=0, column=i, sticky="w", padx=4, pady=3)

        self.listbox_names = tk.Listbox(box_filter, height=5, selectmode="extended")
        self.listbox_names.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=(4, 2))
        for name in self.cfg.get("creature_list") or []:
            self.listbox_names.insert("end", name)

        name_row = ttk.Frame(box_filter)
        name_row.grid(row=2, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 6))
        ttk.Entry(name_row, textvariable=self.var_new_name, width=24).pack(side="left", padx=(0, 4))
        ttk.Button(name_row, text="Adicionar", command=self.add_creature_name).pack(side="left", padx=4)
        ttk.Button(name_row, text="Remover selecionado(s)", command=self.remove_selected_creature).pack(
            side="left", padx=4
        )

        add_field(
            box_filter, 3, "Similaridade minima do nome (%)", self.var_name_threshold, 8,
            "tolerante a falhas de OCR (0 a 100)",
        )

        # Ritmo ---------------------------------------------------------------
        box_rate = ttk.LabelFrame(parent, text="6. Ritmo")
        box_rate.grid(row=6, column=0, sticky="ew", pady=4)
        add_field(box_rate, 0, "Delay minimo com alvo (s)", self.var_delay_min, 8, "ex: 0.6")
        add_field(box_rate, 1, "Delay maximo com alvo (s)", self.var_delay_max, 8, "ex: 1.4")
        add_field(box_rate, 2, "Delay minimo (lista vazia) (s)", self.var_idle_min, 8, "ex: 2.0")
        add_field(box_rate, 3, "Delay maximo (lista vazia) (s)", self.var_idle_max, 8, "ex: 4.0")
        add_field(box_rate, 4, "Variacao do clique (px)", self.var_jitter, 8, "+/- pixels")

        ttk.Label(
            parent,
            text="Aviso: esta funcao depende de leitura visual (OCR/template) da Battle List. "
            "Mudar o tamanho da janela do jogo, o zoom ou a skin da Battle List depois de "
            "calibrar pode quebrar a deteccao - recalibre se isso acontecer.",
            foreground="#a33",
            wraplength=700,
            justify="left",
        ).grid(row=7, column=0, sticky="w", pady=(4, 0))

        # Salvar / Fechar -------------------------------------------------------
        actions_bar = ttk.Frame(parent)
        actions_bar.grid(row=8, column=0, sticky="e", pady=(8, 4))
        ttk.Button(actions_bar, text="Salvar config", command=self.save_config).pack(side="left", padx=4)
        ttk.Button(actions_bar, text="Fechar", command=self._hide_config_dialog).pack(side="left", padx=4)

        parent.columnconfigure(0, weight=1)

    # ------------------------------------------------------------ calibracao
    def _relative_row_offset(self, region) -> list[int] | None:
        """Converte uma regiao ABSOLUTA (retorno do select_region) no offset
        [dx, dy, w, h] relativo ao topo-esquerda da linha em que ela caiu -
        funciona nao importa em qual linha o usuario usou pra calibrar."""
        battle_region = self.cfg.get("battle_list_region")
        row_height = self.cfg.get("row_height")
        if not is_valid_region(battle_region) or not row_height:
            messagebox.showwarning("Target", "Calibre a regiao da Battle List e a altura de linha primeiro.")
            return None
        bx, by, _bw, _bh = battle_region
        rx, ry, rw, rh = region
        row_index = max(0, int((ry - by) // row_height))
        row_top = by + row_index * row_height
        return [rx - bx, ry - row_top, rw, rh]

    def calibrate_all(self) -> None:
        """Encadeia os 5 passos de calibracao em sequencia, reaproveitando
        exatamente os mesmos metodos dos botoes individuais - so pra nao
        precisar caçar cada botao na ordem certa toda vez que a regiao ou a
        altura de linha mudam (o que invalida tudo que depende delas)."""
        messagebox.showinfo(
            "Target",
            "Calibracao guiada: 5 passos em sequencia (regiao, altura de linha, "
            "linha vazia, nome, bordas). Clique OK pra comecar o passo 1.",
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

        messagebox.showinfo("Target", "Passo 4/5: agora selecione a faixa de texto do NOME, numa linha OCUPADA.")
        self.pick_name_crop()

        messagebox.showinfo(
            "Target", "Passo 5/5: com uma criatura em modo ATTACK (nome vermelho) selecionada no jogo, "
            "clique OK e marque o texto do nome."
        )
        self._calibrate_name_color("attack")

        messagebox.showinfo(
            "Target", "Agora com uma criatura em modo FOLLOW (nome verde) selecionada no jogo, "
            "clique OK e marque o texto do nome de novo."
        )
        self._calibrate_name_color("follow")

        self.log("Calibracao guiada concluida - use 'Testar leitura da Battle List' pra conferir.")
        messagebox.showinfo("Target", "Calibracao guiada concluida! Use 'Testar leitura da Battle List' pra conferir.")

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
            messagebox.showwarning("Target", "Altura muito pequena - arraste novamente com mais precisao.")
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
        path = os.path.join(ASSETS_DIR, "target_row_empty.png")
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
        attack_ok = "calibrado" if self.cfg.get("attack_name_hsv_lower") else "nao calibrado"
        follow_ok = "calibrado" if self.cfg.get("follow_name_hsv_lower") else "nao calibrado"
        return f"Attack: {attack_ok}   |   Follow: {follow_ok}"

    def _calibrate_name_color(self, kind: str) -> None:
        """Deriva a faixa HSV da COR DO TEXTO do nome (nao de uma borda
        separada - alguns clients, confirmado neste projeto, so mudam a cor
        do nome pra indicar selecao). Nao precisa de offset proprio: a
        classificacao em runtime reusa o mesmo recorte do OCR do nome."""
        label = "ATAQUE (vermelho)" if kind == "attack" else "FOLLOW (verde)"
        region = self.app.select_region(
            f"Selecione o TEXTO do nome (mesma faixa do OCR), numa linha em modo {label}  -  ESC cancela"
        )
        if not region:
            return
        with ScreenCapture() as cap:
            frame = cap.grab(region)
        lower, upper = sample_name_text_color(frame)
        if kind == "attack":
            self.cfg["attack_name_hsv_lower"] = lower
            self.cfg["attack_name_hsv_upper"] = upper
        else:
            self.cfg["follow_name_hsv_lower"] = lower
            self.cfg["follow_name_hsv_upper"] = upper
        self.var_name_color_status.set(self._name_color_status_text())
        self.app.config_store.save()
        self.log(f"Cor do nome em {label} calibrada: HSV {lower} - {upper}")

    def pick_life_bar(self) -> None:
        region = self.app.select_region(
            "Selecione a MINI BARRA DE VIDA da criatura, numa linha OCUPADA  -  ESC cancela"
        )
        if not region:
            return
        offset = self._relative_row_offset(region)
        if offset is None:
            return
        self.cfg["life_bar_offset"] = offset
        self.var_life_offset.set(offset_text(offset))
        self.app.config_store.save()
        self.log(f"Barra de vida (opcional) definida: {offset_text(offset)}")

    def calibrate_context_menu(self) -> None:
        point1 = self.app.select_point(
            "PASSO 1/2: clique no local onde o botao direito seria aplicado "
            "(ex: o centro de uma linha da Battle List)  -  ESC cancela"
        )
        if not point1:
            return
        messagebox.showinfo(
            "Target",
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

    def _on_attack_mode_change(self) -> None:
        is_menu = ATTACK_MODE_VALUES.get(self.var_attack_mode.get()) == "context_menu"
        self.btn_calibrate_menu.configure(state="normal" if is_menu else "disabled")

    # -------------------------------------------------------------- filtro
    def add_creature_name(self) -> None:
        name = self.var_new_name.get().strip()
        if not name:
            return
        self.listbox_names.insert("end", name)
        self.var_new_name.set("")
        self.save_config()

    def remove_selected_creature(self) -> None:
        for index in reversed(self.listbox_names.curselection()):
            self.listbox_names.delete(index)
        self.save_config()

    # ------------------------------------------------------------- testes
    def worker_config(self) -> dict:
        """Inclui os mesmos extras (`_coordinator`/`_background_hwnd`) que
        `app.start_worker` injeta - sem isso, os botoes de "Testar..." cairiam
        sempre no mouse real, mesmo com "Modo background" ligado."""
        cfg = dict(self.cfg)
        cfg.update(self.app.build_worker_extras())
        return cfg

    def test_read(self) -> None:
        """Captura a Battle List agora e mostra o que foi lido - dry-run,
        nao clica em nada (mesmo padrao do "Testar deteccao" do AutoFishing)."""
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TargetWorker(dict(cfg), self.app.events)
            worker.setup()
        except Exception as exc:
            messagebox.showerror("Target", f"Falha ao preparar leitura: {exc}")
            return

        try:
            frame = worker.capture.grab(worker.battle_list_region)
            rows = worker.read_rows(frame)
            target_row = worker.pick_target([r for r in rows if r.occupied])
        except Exception as exc:
            worker.teardown()
            messagebox.showerror("Target", f"Falha na leitura: {exc}")
            return
        worker.teardown()

        lines = []
        for row in rows:
            if not row.occupied:
                lines.append(f"Linha {row.index}: vazia")
                continue
            marker = "  <- ALVO ESCOLHIDO" if target_row is not None and target_row.index == row.index else ""
            life = f"{row.life_pct}%" if row.life_pct is not None else "n/d"
            lines.append(
                f"Linha {row.index}: nome='{row.name or '?'}' selecao={row.selection} vida={life}{marker}"
            )
        message = "\n".join(lines) if lines else "Nenhuma linha detectada (confira a altura de linha)."
        for line in lines:
            self.log(line)
        messagebox.showinfo("Target - Testar leitura", message)

    def test_attack_click(self) -> None:
        """Dispara a acao de ataque configurada numa linha detectada agora -
        dry-run por padrao (checkbox), real exige confirmacao explicita."""
        self.save_config()
        cfg = self.worker_config()
        try:
            worker = TargetWorker(dict(cfg), self.app.events)
            worker.setup()
        except Exception as exc:
            messagebox.showerror("Target", f"Falha ao preparar teste: {exc}")
            return

        try:
            frame = worker.capture.grab(worker.battle_list_region)
            rows = worker.read_rows(frame)
            occupied = [r for r in rows if r.occupied]
            target_row = worker.pick_target(occupied) or (occupied[0] if occupied else None)
            if target_row is None:
                messagebox.showwarning("Target", "Nenhuma linha ocupada detectada pra testar o clique.")
                return

            dry_run = bool(self.var_dry_run.get())
            if not dry_run and not messagebox.askyesno(
                "Target",
                f"Modo REAL: isso vai clicar/atacar de verdade na linha {target_row.index}. Continuar?",
            ):
                return
            worker.attack(target_row.index, dry_run=dry_run)
        except Exception as exc:
            messagebox.showerror("Target", f"Falha no teste de clique: {exc}")
            return
        finally:
            worker.teardown()

        self.log(f"Teste de clique de ataque concluido na linha {target_row.index}.")
        messagebox.showinfo("Target", f"Acao de ataque testada na linha {target_row.index} (ver log).")

    # -------------------------------------------------------------- controles
    def save_config(self) -> None:
        self.cfg["attack_mode"] = ATTACK_MODE_VALUES.get(self.var_attack_mode.get(), "single_click")
        self.cfg["filter_mode"] = FILTER_MODE_VALUES.get(self.var_filter_mode.get(), "blacklist")
        self.cfg["creature_list"] = list(self.listbox_names.get(0, "end"))
        threshold_pct = max(0, min(100, parse_int(self.var_name_threshold.get(), 80)))
        self.cfg["name_match_threshold"] = threshold_pct / 100
        self.cfg["delay_min"] = parse_float(self.var_delay_min.get(), 0.6)
        self.cfg["delay_max"] = parse_float(self.var_delay_max.get(), 1.4)
        self.cfg["idle_delay_min"] = parse_float(self.var_idle_min.get(), 2.0)
        self.cfg["idle_delay_max"] = parse_float(self.var_idle_max.get(), 4.0)
        self.cfg["click_jitter"] = parse_int(self.var_jitter.get(), 2)
        coverage_pct = max(0, min(100, parse_int(self.var_empty_threshold.get(), 90)))
        self.cfg["empty_match_threshold"] = coverage_pct / 100
        self.app.config_store.save()

    def start(self) -> None:
        self.save_config()
        if not is_valid_region(self.cfg.get("battle_list_region")):
            messagebox.showwarning("Target", "Selecione a regiao da Battle List primeiro.")
            return
        if not self.cfg.get("row_height"):
            messagebox.showwarning("Target", "Calibre a altura de linha primeiro.")
            return
        if not self.cfg.get("row_empty_template"):
            messagebox.showwarning("Target", "Capture o template de linha vazia primeiro.")
            return
        self.app.start_worker(self.worker_key, TargetWorker, self.worker_config())

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
