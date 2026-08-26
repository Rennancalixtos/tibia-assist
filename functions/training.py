"""Training - mantem o personagem engajado no mesmo alvo de treino (monstro
parado ou boneco de treino) pelo maior tempo possivel, sem trocar de alvo.

O Target foi desenhado pra "matar e trocar": primeiro alvo valido, ataca,
espera morrer, seleciona o proximo. Treino e o oposto - o alvo NAO morre e
NAO deve ser trocado; o objetivo e ficar engajado nele ininterruptamente ate
o usuario parar ou acabar algum recurso (mana, arma de treino).

Dois modos, escolhidos pelo usuario (`mode` na config):

- "battle_list" (Modo A - monstro de treino, ex: "training monk"): aparece na
  Battle List como qualquer criatura normal. Reaproveita INTEGRALMENTE a
  leitura de linha ja implementada em `functions/target.py` (mesmo parsing
  de slot vazio/nome/selecao por borda), mas com uma WHITELIST FIXA de um
  unico nome, tratado como alvo permanente: nunca troca, so reforca a
  selecao se ela cair da lista/perder o destaque. Sub-opcao: tambem conjurar
  magia de ataque, mesma logica do ManaTraining do RuneMaker
  (`functions/rune_maker.py`), condicionada ao alvo continuar selecionado.

- "dummy" (Modo B - boneco de treino / Exercise Dummy): objeto fixo do
  cenario, nao aparece na Battle List - so uma posicao de tela calibrada.
  Clica periodicamente nela (a arma de treino equipada faz o personagem
  bater ao clicar no alvo, como atacar uma criatura) e monitora o slot da
  arma por template matching pra detectar quando ela esgota.

Comum aos dois modos: anti-AFK-kick (acao periodica pra provar atividade ao
servidor, ja que treino roda por horas sem nenhuma outra interacao) e
pausas de descanso (mesmo padrao ja usado no AutoFishing).

Tudo baseado em pixels da tela + input simulado. Nenhuma leitura de memoria.

Fora de escopo nesta versao (ver prompt original):
    - movimentacao automatica ate o boneco/monstro caso o personagem seja
      empurrado (assume que o usuario se posiciona manualmente antes)
    - troca automatica de arma de treino ao esgotar (so pausa e avisa)
    - leitura de dano numerico/golpes por OCR pra estimar progresso no Modo B
      (contagem de "golpes desferidos" fica como extensao futura - exigiria
      calibrar uma regiao de numero flutuante de dano, instavel o bastante
      pra nao entrar nesta versao; o contador de cliques de reforco jah
      exposto serve como proxy aproximado por enquanto)
"""

from __future__ import annotations

import time

from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image
from core.worker import BaseWorker
from functions.rune_maker import OCRUnavailable, configure_tesseract, read_number, slot_is_empty
from functions.target import (
    BattleListRow,
    classify_name_color,
    crop_offset,
    name_passes_filter,
    read_name,
    row_count_for,
    row_is_empty,
)


class TrainingWorker(BaseWorker):
    name_label = "training"

    def setup(self) -> None:
        self.capture = ScreenCapture()
        self.mouse = InputSimulator(
            background_hwnd=self.config.get("_background_hwnd"),
            on_fallback=self.log,
        )
        self.register_with_coordinator("training")

        self.mode = self.config.get("mode", "battle_list")
        self._last_warning = ""
        self._session_started_at = time.monotonic()
        self._last_elapsed_emit = 0.0

        self.break_enabled = bool(self.config.get("break_enabled", True))
        self._schedule_next_break()

        self.anti_afk_enabled = bool(self.config.get("anti_afk_enabled", False))
        self.anti_afk_interval = float(self.config.get("anti_afk_interval_minutes", 10) or 10) * 60
        self._next_anti_afk_at = time.monotonic() + self.anti_afk_interval

        if self.mode == "dummy":
            self._setup_dummy_mode()
        else:
            self._setup_battle_list_mode()

        configure_tesseract(on_progress=self.log)

        mode_label = "boneco de treino" if self.mode == "dummy" else "monstro de treino (Battle List)"
        self.log(f"Training iniciado (modo={mode_label}, backend={InputSimulator.backend_name()}).")

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        elapsed = self._format_elapsed(time.monotonic() - self._session_started_at)
        self.log(f"Training finalizado. Tempo total treinando: {elapsed}.")

    # ------------------------------------------------------------- calibracao
    def _load_template(self, key: str):
        path = self.config.get(key)
        if not path:
            return None
        try:
            return load_image(path)
        except Exception:
            return None

    def _hsv_range(self, lower_key: str, upper_key: str):
        lower = self.config.get(lower_key)
        upper = self.config.get(upper_key)
        if not lower or not upper:
            return None
        return (lower, upper)

    def warn_once(self, message: str) -> None:
        if message != self._last_warning:
            self.log(message)
            self._last_warning = message

    # ------------------------------------------------------------ pausas/afk
    def _schedule_next_break(self) -> None:
        interval = InputSimulator.random_delay(
            self.config.get("break_interval_min", 30), self.config.get("break_interval_max", 300)
        )
        self._next_break_at = time.monotonic() + interval

    def maybe_take_break(self) -> bool:
        """Mesmo padrao do AutoFishing (`AutoFishingWorker.maybe_take_break`)
        - pausas de descanso pra nao rodar horas seguidas sem nenhum
        intervalo humano, especialmente relevante pra uma atividade tao
        prolongada quanto treino."""
        if not self.break_enabled or time.monotonic() < self._next_break_at:
            return True
        duration = InputSimulator.random_delay(
            self.config.get("break_duration_min", 10), self.config.get("break_duration_max", 120)
        )
        self.log(f"Pausa para descanso: {duration:.0f}s.")
        if not self.sleep(duration):
            return False
        self._schedule_next_break()
        return True

    def maybe_send_anti_afk(self) -> None:
        """Prova de atividade pro servidor nao derrubar a conexao por
        inatividade prolongada - um "movimento leve" (tecla de direcao e
        imediatamente a oposta) como fallback configuravel, pro caso do
        clique/tecla de ataque em loop nao contar como atividade no servidor
        do usuario."""
        if not self.anti_afk_enabled or time.monotonic() < self._next_anti_afk_at:
            return
        key_a = (self.config.get("anti_afk_key_a") or "up").strip().lower()
        key_b = (self.config.get("anti_afk_key_b") or "down").strip().lower()
        if self.request_floor(timeout=5.0):
            try:
                self.mouse.press_key(key_a)
                time.sleep(InputSimulator.random_delay(0.10, 0.25))
                self.mouse.press_key(key_b)
            finally:
                self.release_floor()
            self.log("Anti-AFK: movimento leve enviado.")
        self._next_anti_afk_at = time.monotonic() + self.anti_afk_interval

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _emit_elapsed(self, force: bool = False) -> None:
        """Cadencia baixa (1x/s) - um relogio HH:MM:SS nao precisa de mais
        que isso, e evita inundar a fila de eventos da GUI."""
        now = time.monotonic()
        if not force and now - self._last_elapsed_emit < 1.0:
            return
        self._last_elapsed_emit = now
        self.emit("elapsed", self._format_elapsed(now - self._session_started_at))

    # ------------------------------------------------------------------ ciclo
    def loop(self) -> None:
        if self.mode == "dummy":
            self._dummy_loop()
        else:
            self._battle_list_loop()

    # ======================================================================
    # Modo A - monstro de treino (Battle List)
    # ======================================================================
    def _setup_battle_list_mode(self) -> None:
        self.battle_list_region = self.config.get("battle_list_region")
        if not is_valid_region(self.battle_list_region):
            raise ValueError("Regiao da Battle List nao configurada.")

        self.row_height = int(self.config.get("row_height") or 0)
        if self.row_height <= 0:
            raise ValueError("Altura de linha nao calibrada.")

        self.row_count = row_count_for(self.battle_list_region, self.row_height)
        if self.row_count <= 0:
            raise ValueError("Regiao da Battle List menor que uma linha - recalibre.")

        self.empty_template = self._load_template("row_empty_template")
        if self.empty_template is None:
            raise ValueError("Template de linha vazia nao calibrado.")
        self.empty_threshold = float(self.config.get("empty_match_threshold", 0.90))

        self.name_crop_offset = self.config.get("name_crop_offset")
        if not self.name_crop_offset:
            self.log(
                "AVISO: faixa de texto do nome nao calibrada - o alvo de "
                "treino nao vai ser reconhecido na lista."
            )

        self.attack_range = self._hsv_range("attack_name_hsv_lower", "attack_name_hsv_upper")
        self.follow_range = self._hsv_range("follow_name_hsv_lower", "follow_name_hsv_upper")

        self.attack_mode = self.config.get("attack_mode", "single_click")
        self.context_menu_offset = self.config.get("context_menu_offset") or [0, 0]

        self.creature_name = (self.config.get("creature_name") or "").strip()
        if not self.creature_name:
            raise ValueError("Nome do monstro/boneco de treino (Modo A) nao configurado.")
        self.name_match_threshold = float(self.config.get("name_match_threshold", 0.80))

        self.missing_retries = max(1, int(self.config.get("missing_retries", 5)))
        self.missing_retry_interval = float(self.config.get("missing_retry_interval", 2.0))
        self._missing_count = 0

        self.cast_spell_enabled = bool(self.config.get("cast_spell_enabled", False))
        self._next_spell_at = 0.0
        if self.cast_spell_enabled:
            self.spell_hotkey = (self.config.get("spell_hotkey") or "").strip()
            if not self.spell_hotkey:
                raise ValueError("Tecla de atalho da magia de ataque nao configurada.")
            self.check_mana = bool(self.config.get("check_mana", True))
            if self.check_mana and not is_valid_region(self.config.get("mana_region")):
                raise ValueError("Regiao de OCR da mana (magia de ataque) nao configurada.")

    # ------------------------------------------------------------- leitura
    def read_rows(self, frame) -> list[BattleListRow]:
        """Mesma logica de `TargetWorker.read_rows` (ver functions/target.py)
        - reaproveita as mesmas funcoes de parsing, sem duplicar a heuristica
        de deteccao. Vida da criatura nao interessa aqui (alvo nao morre)."""
        rows: list[BattleListRow] = []
        for i in range(self.row_count):
            y0 = i * self.row_height
            y1 = y0 + self.row_height
            row_frame = frame[y0:y1, :]
            if row_frame.size == 0:
                continue

            empty = row_is_empty(row_frame, self.empty_template, self.empty_threshold)
            if empty:
                rows.append(BattleListRow(index=i, occupied=False))
                continue

            name = None
            selection = "none"
            if self.name_crop_offset:
                crop = crop_offset(row_frame, self.name_crop_offset)
                if crop is not None and crop.size > 0:
                    try:
                        name = read_name(crop)
                    except OCRUnavailable as exc:
                        self.warn_once(f"OCR indisponivel: {exc}")
                    selection = classify_name_color(crop, self.attack_range, self.follow_range)

            rows.append(BattleListRow(index=i, occupied=True, name=name, selection=selection))
        return rows

    def find_trained_creature(self, occupied_rows: list[BattleListRow]) -> BattleListRow | None:
        for row in occupied_rows:
            if name_passes_filter(row.name, [self.creature_name], "whitelist", self.name_match_threshold):
                return row
        return None

    # ------------------------------------------------------------------ acao
    def _row_center(self, index: int) -> tuple[int, int]:
        x, y, w, _h = self.battle_list_region
        cy = int(y + index * self.row_height + self.row_height / 2)
        cx = int(x + w / 2)
        return cx, cy

    def select_creature(self, index: int, dry_run: bool = False) -> None:
        """Mesma acao de selecao configurada no Target (clique simples/duplo/
        menu de contexto), so que aqui e disparada UMA vez pra prender o
        alvo permanente - nunca repetida so porque ele continua selecionado."""
        cx, cy = self._row_center(index)
        jitter = int(self.config.get("click_jitter", 2))

        if dry_run:
            self.log(f"[dry-run] acao de selecao ({self.attack_mode}) na linha {index} em ({cx}, {cy})")
            return

        # Mesmo motivo do Target (ver functions/target.py): devolve o cursor
        # pra onde estava antes do clique, senao o hover em cima da linha
        # pode mudar a cor do nome e confundir `classify_name_color` depois.
        using_real_mouse = self.mouse.is_using_real_mouse()
        origin = InputSimulator.current_position() if using_real_mouse else None

        if self.attack_mode == "double_click":
            self.mouse.double_click(cx, cy, jitter=jitter)
        elif self.attack_mode == "context_menu":
            self.mouse.click(cx, cy, button="right", jitter=jitter)
            time.sleep(InputSimulator.random_delay(0.15, 0.35))
            dx, dy = self.context_menu_offset
            self.mouse.click(cx + int(dx), cy + int(dy), button="left", jitter=0)
        else:
            self.mouse.click(cx, cy, button="left", jitter=jitter)

        if origin is not None:
            self.mouse.move_to(*origin)

    def _read_mana(self) -> int | None:
        frame = self.capture.grab(self.config.get("mana_region"))
        return read_number(frame)

    def _maybe_cast_spell(self) -> None:
        """Mesma logica do ManaTraining do RuneMaker
        (`RuneMakerWorker._mana_training_loop`): checa mana minima via OCR,
        conjura, espera o delay. So chamada quando o alvo de treino ainda
        esta na lista (ver `_battle_list_loop`) - nunca solta magia com o
        alvo sumido."""
        if time.monotonic() < self._next_spell_at:
            return
        try:
            if self.check_mana:
                mana = self._read_mana()
                self.emit("mana_reading", mana)
                if mana is None:
                    self.warn_once("Nao consegui ler a mana via OCR. Verifique a regiao configurada.")
                    return
                if mana < int(self.config.get("min_mana", 300)):
                    self.warn_once(f"Mana insuficiente ({mana}) para conjurar - aguardando regenerar...")
                    return
        except OCRUnavailable as exc:
            self.warn_once(f"ERRO de OCR (magia de ataque): {exc}")
            return

        if not self.request_floor(timeout=5.0):
            return
        try:
            self.mouse.press_key(self.spell_hotkey)
        finally:
            self.release_floor()
        self.log(f"Magia de ataque conjurada (tecla {self.spell_hotkey}).")
        self._next_spell_at = time.monotonic() + InputSimulator.random_delay(
            self.config.get("spell_delay_min", 1.5), self.config.get("spell_delay_max", 2.5)
        )

    # ------------------------------------------------------------------ loop
    def _battle_list_loop(self) -> None:
        while not self.stopped:
            if not self.wait_for_higher_priority():
                return
            if not self.maybe_take_break():
                return
            self.maybe_send_anti_afk()
            self._emit_elapsed()

            frame = self.capture.grab(self.battle_list_region)
            rows = self.read_rows(frame)
            occupied_rows = [r for r in rows if r.occupied]
            target_row = self.find_trained_creature(occupied_rows)

            if target_row is None:
                self._missing_count += 1
                if self._missing_count == 1:
                    self.log(f"Alvo de treino '{self.creature_name}' nao encontrado na lista - tentando de novo...")
                if self._missing_count >= self.missing_retries:
                    self.log("Alvo de treino nao encontrado - verifique se ainda esta por perto.")
                    self.warn_popup("Alvo de treino nao encontrado - verifique se ainda esta por perto.")
                    self.pause()
                    self._missing_count = 0
                    continue
                if not self.sleep(self.missing_retry_interval):
                    return
                continue

            self._missing_count = 0

            if target_row.selection == "none":
                if not self.request_floor(timeout=5.0):
                    if not self.sleep(1.0):
                        return
                    continue
                try:
                    self.select_creature(target_row.index)
                finally:
                    self.release_floor()
                self.bump_counter()
                self.log(
                    f"Alvo de treino '{target_row.name or self.creature_name}' selecionado "
                    f"(linha {target_row.index})."
                )
            # ja selecionado (borda de attack/follow): so continua monitorando,
            # sem reforcar a acao a toa - diferente do Target, este alvo nao
            # se move nem morre.

            if self.cast_spell_enabled:
                self._maybe_cast_spell()

            if not self.sleep(InputSimulator.random_delay(
                self.config.get("delay_min", 0.6), self.config.get("delay_max", 1.4)
            )):
                return

    # ======================================================================
    # Modo B - boneco de treino (objeto fixo)
    # ======================================================================
    def _setup_dummy_mode(self) -> None:
        self.dummy_position = self.config.get("dummy_position")
        if not (isinstance(self.dummy_position, (list, tuple)) and len(self.dummy_position) == 2):
            raise ValueError("Posicao do boneco de treino nao configurada.")

        self.weapon_slot_region = self.config.get("weapon_slot_region")
        self.weapon_template = self._load_template("weapon_equipped_template")
        if not is_valid_region(self.weapon_slot_region) or self.weapon_template is None:
            self.log(
                "AVISO: slot da arma de treino nao calibrado - deplecao da "
                "arma nao vai ser detectada."
            )
        self.weapon_match_threshold = float(self.config.get("weapon_match_threshold", 0.90))
        self.click_jitter = int(self.config.get("click_jitter", 2))

        self._next_dummy_click_at = 0.0

    def _weapon_still_equipped(self) -> bool | None:
        """None = sem template calibrado (checagem desativada, nao trava o
        ciclo); True/False = resultado do template match contra o template
        CALIBRADO da arma equipada - mesmo mecanismo de
        `functions.rune_maker.slot_is_empty` (so que aqui o template de
        referencia e o da arma "presente", nao "vazio"; a funcao so compara
        contra o que foi calibrado, o significado e de quem chama)."""
        if self.weapon_template is None or not is_valid_region(self.weapon_slot_region):
            return None
        frame = self.capture.grab(self.weapon_slot_region)
        return slot_is_empty(frame, self.weapon_template, self.weapon_match_threshold)

    def _schedule_next_dummy_click(self) -> None:
        interval = InputSimulator.random_delay(
            self.config.get("click_interval_min", 2.0), self.config.get("click_interval_max", 4.0)
        )
        self._next_dummy_click_at = time.monotonic() + interval

    def click_dummy(self, dry_run: bool = False) -> None:
        x, y = int(self.dummy_position[0]), int(self.dummy_position[1])
        if dry_run:
            self.log(f"[dry-run] clicaria no boneco de treino ({x}, {y})")
            return
        self.mouse.click(x, y, button="left", jitter=self.click_jitter)

    def _dummy_loop(self) -> None:
        self._schedule_next_dummy_click()
        while not self.stopped:
            if not self.wait_for_higher_priority():
                return
            if not self.maybe_take_break():
                return
            self.maybe_send_anti_afk()
            self._emit_elapsed()

            still_equipped = self._weapon_still_equipped()
            if still_equipped is False:
                self.log("Arma de treino esgotada - reponha e reative.")
                self.warn_popup("Arma de treino esgotada - reponha e reative.")
                self.pause()
                continue

            if time.monotonic() >= self._next_dummy_click_at:
                if not self.request_floor(timeout=5.0):
                    if not self.sleep(1.0):
                        return
                    continue
                try:
                    self.click_dummy()
                finally:
                    self.release_floor()
                self.bump_counter()
                self._schedule_next_dummy_click()

            if not self.sleep(0.5):
                return
