"""RuneMaker - cria runas em sequencia (ou treina mana) usando a magia.

Tres modos, todos configurados na aba RuneMaker (`mode`/`no_hand_mode`):

- "craft" com mao (padrao): pega a blank rune da backpack de origem, leva
  pra mao do personagem, conjura a magia, guarda o resultado na backpack de
  destino. Slots vazios/ocupados sao detectados por template matching (nao
  por heuristica de cor), calibrados pelo usuario na propria tela.
- "craft" com `no_hand_mode` (alguns OTservers aplicam a magia direto no
  slot, sem precisar de mao): so clica no slot da blank rune e conjura,
  sem nenhum arraste.
- "mana_training": so conjura a magia repetidamente respeitando a mana
  minima, sem manusear nenhum item.

Em todos os modos, a mana e checada por OCR (Tesseract) antes de agir, e a
automacao pausa (nao so loga) quando faltar recurso (mana ou blank rune) ou
quando a backpack de destino estiver cheia - martelar contra um erro de
calibracao e pior do que parar e avisar.

Tudo baseado em pixels da tela + input simulado. Nenhuma leitura de memoria.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image
from core.tesseract_installer import find_tesseract, install_tesseract
from core.worker import BaseWorker

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789/"


class OCRUnavailable(RuntimeError):
    pass


def configure_tesseract(explicit_cmd: str | None = None, on_progress=None) -> None:
    """Aponta o pytesseract pro binario do Tesseract.

    Usa `explicit_cmd` se informado; senao tenta achar automaticamente (PATH
    ou pasta padrao de instalacao). Se nao achar de nenhum jeito, instala
    sozinho (instalador ja embutido no pacote - sem precisar de internet
    nesse momento, ver core/tesseract_installer.py) e tenta achar de novo -
    o usuario nunca precisa instalar o Tesseract manualmente.

    `on_progress`, se informado, recebe uma linha de status (mesma cara de
    `BaseWorker.log`) - so relevante quando uma instalacao de verdade
    acontece (a maioria das vezes o Tesseract ja esta la e isso e um no-op).
    """
    if pytesseract is None:
        return

    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    cmd = (explicit_cmd or "").strip() or find_tesseract()
    if not cmd:
        report("Tesseract OCR nao encontrado - instalando automaticamente...")
        ok, message = install_tesseract()
        report(message)
        cmd = find_tesseract()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def preprocess_for_ocr(frame: np.ndarray) -> np.ndarray:
    """Deixa o recorte mais legivel para o Tesseract.

    A fonte do cliente e pequena e clara sobre fundo escuro; ampliar e
    binarizar melhora bastante o reconhecimento.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.medianBlur(gray, 3)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Texto claro em fundo escuro -> inverte para texto preto em fundo branco.
    if np.mean(binary) < 127:
        binary = cv2.bitwise_not(binary)
    return binary


def read_number(frame: np.ndarray) -> int | None:
    """Le o primeiro numero inteiro visivel no recorte. None se falhar.

    Aceita formatos como "123" e "123 / 456" (nesse caso devolve 123).
    """
    if pytesseract is None:
        raise OCRUnavailable(
            "pytesseract nao instalado. Instale-o e o Tesseract OCR, "
            "ou desmarque a verificacao de mana."
        )
    processed = preprocess_for_ocr(frame)
    try:
        text = pytesseract.image_to_string(processed, config=OCR_CONFIG)
    except Exception as exc:  # binario do Tesseract ausente
        raise OCRUnavailable(f"Falha ao executar o Tesseract: {exc}") from exc

    match = re.search(r"\d+", text.replace(" ", ""))
    return int(match.group()) if match else None


def slot_is_empty(frame_region: np.ndarray, empty_template: np.ndarray, threshold: float = 0.90) -> bool:
    """Compara a regiao atual de um slot com o template de "vazio" calibrado.

    Decisivo e o template match (nao heuristica de cor/desvio-padrao): o
    fundo de um slot vazio e visualmente consistente, mas o conteudo de um
    slot ocupado varia muito (icones, contadores) - um threshold de cor
    simples gera falso positivo/negativo com frequencia.
    """
    if frame_region.shape[:2] != empty_template.shape[:2]:
        empty_template = cv2.resize(empty_template, (frame_region.shape[1], frame_region.shape[0]))
    result = cv2.matchTemplate(frame_region, empty_template, cv2.TM_CCOEFF_NORMED)
    return float(result.max()) >= threshold


class RuneMakerWorker(BaseWorker):
    name_label = "runemaker"

    def setup(self) -> None:
        self.capture = ScreenCapture()
        self.mouse = InputSimulator(
            background_hwnd=self.config.get("_background_hwnd"),
            on_fallback=self.log,
        )
        self.register_with_coordinator("runemaker")
        self._pause_failures = 0
        self._cycle_failures = 0

        self.mode = self.config.get("mode", "craft")
        self.no_hand_mode = bool(self.config.get("no_hand_mode", False))

        self.spell_hotkey = (self.config.get("spell_hotkey") or "").strip()
        if not self.spell_hotkey:
            raise ValueError("Tecla de atalho da magia nao configurada.")

        if self.mode != "mana_training":
            self.slot = self.config.get("blank_slot")
            if not (isinstance(self.slot, (list, tuple)) and len(self.slot) == 2):
                raise ValueError("Slot da blank rune nao configurado.")

            if not self.no_hand_mode:
                self.hand_slot = self.config.get("hand_slot")
                if not (isinstance(self.hand_slot, (list, tuple)) and len(self.hand_slot) == 2):
                    raise ValueError("Slot da mao do personagem nao configurado.")
                self.output_slot = self.config.get("output_slot")
                if not (isinstance(self.output_slot, (list, tuple)) and len(self.output_slot) == 2):
                    raise ValueError("Slot livre de destino nao configurado.")

        self.check_mana = bool(self.config.get("check_mana", True))
        if self.check_mana and not is_valid_region(self.config.get("mana_region")):
            raise ValueError("Regiao de OCR da mana nao configurada.")

        self.empty_match_threshold = float(self.config.get("empty_match_threshold", 0.90))
        self.blank_empty_template = self._load_slot_template("blank_slot")
        self.hand_empty_template = self._load_slot_template("hand_slot")
        self.output_empty_template = self._load_slot_template("output_slot")

        configure_tesseract(on_progress=self.log)

        # Evita repetir a mesma mensagem de "sem recurso" a cada iteracao.
        self._last_warning = ""

        mode_label = {"craft": "criar runas", "mana_training": "ManaTraining"}.get(self.mode, self.mode)
        self.log(
            f"RuneMaker iniciado (modo={mode_label}, sem_mao={self.no_hand_mode}, "
            f"magia={self.spell_hotkey}, backend={InputSimulator.backend_name()})."
        )

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        label = "Magias conjuradas" if self.mode == "mana_training" else "Runas criadas"
        self.log(f"RuneMaker finalizado. {label} na sessao: {self.counter}.")

    # -------------------------------------------------------------------- OCR
    def read_status(self, key: str) -> int | None:
        region = self.config.get(f"{key}_region")
        frame = self.capture.grab(region)
        return read_number(frame)

    def resources_ok(self) -> bool:
        """True se a mana esta acima do minimo configurado."""
        if self.check_mana:
            mana = self.read_status("mana")
            self.emit("mana_reading", mana)
            if mana is None:
                self.warn_once("Nao consegui ler a mana via OCR. Verifique a regiao configurada.")
                return False
            if mana < int(self.config.get("min_mana", 300)):
                self.warn_once(f"Mana insuficiente ({mana}). Aguardando regenerar...")
                return False

        self._last_warning = ""
        return True

    def warn_once(self, message: str) -> None:
        if message != self._last_warning:
            self.log(message)
            self._last_warning = message

    # ------------------------------------------------------------- item slots
    def _load_slot_template(self, slot_key: str) -> np.ndarray | None:
        path = self.config.get(f"{slot_key}_empty_template")
        if not path:
            return None
        try:
            return load_image(path)
        except Exception:
            return None

    def _slot_currently_empty(self, region_key: str, template: np.ndarray | None) -> bool | None:
        """Devolve True/False, ou None se o template nao foi calibrado (a
        checagem fica desativada pra aquele slot em vez de travar o ciclo)."""
        if template is None:
            return None
        region = self.config.get(region_key)
        if not is_valid_region(region):
            return None
        frame = self.capture.grab(region)
        return slot_is_empty(frame, template, self.empty_match_threshold)

    @staticmethod
    def _confirm(actual: bool | None, expected: bool) -> bool:
        if actual is None:  # sem template calibrado pra esse slot: nao bloqueia
            return True
        return actual == expected

    def _blank_stock_empty(self) -> bool:
        return bool(self._slot_currently_empty("blank_slot_region", self.blank_empty_template))

    def _post_drag_delay(self) -> bool:
        return self.sleep(InputSimulator.random_delay(0.10, 0.25))

    # -------------------------------------------------------- pausa mutua
    def _request_action_floor(self) -> bool:
        if self.request_floor(timeout=5.0):
            self._pause_failures = 0
            return True
        self._pause_failures += 1
        if self._pause_failures >= 3:
            self.log(
                "ERRO: uma rotina de prioridade menor nao libera a vez ha varias "
                "tentativas - verifique o estado das outras abas."
            )
        else:
            self.log("AVISO: outra rotina nao confirmou a pausa a tempo - tentando de novo no proximo ciclo.")
        return False

    # ------------------------------------------------------------------ ciclo
    def loop(self) -> None:
        if self.mode == "mana_training":
            self._mana_training_loop()
        else:
            self._craft_loop()

    def _mana_training_loop(self) -> None:
        while not self.stopped:
            if not self.wait_for_higher_priority():
                return

            try:
                if not self.resources_ok():
                    if not self.sleep(3.0):
                        return
                    continue
            except OCRUnavailable as exc:
                self.log(f"ERRO de OCR: {exc}")
                return

            if not self._request_action_floor():
                if not self.sleep(1.0):
                    return
                continue
            try:
                self.mouse.press_key(self.spell_hotkey)
            finally:
                self.release_floor()

            self.bump_counter()
            self.log(f"Magia #{self.counter} conjurada (tecla {self.spell_hotkey}) - ManaTraining.")

            delay = InputSimulator.random_delay(
                self.config.get("delay_min", 1.5), self.config.get("delay_max", 2.5)
            )
            if not self.sleep(delay):
                return

    def _craft_loop(self) -> None:
        target_amount = int(self.config.get("amount", 0) or 0)

        while not self.stopped:
            if not self.wait_for_higher_priority():
                return

            try:
                if not self.resources_ok():
                    if not self.sleep(3.0):
                        return
                    continue
            except OCRUnavailable as exc:
                self.log(f"ERRO de OCR: {exc}")
                return

            if self._blank_stock_empty():
                self.log("Sem blank runes na backpack - RuneMaker pausado.")
                self.warn_popup("Sem blank runes na backpack - RuneMaker pausado.")
                self.pause()
                continue

            if not self._request_action_floor():
                if not self.sleep(1.0):
                    return
                continue
            try:
                ok = self._simple_craft_cycle() if self.no_hand_mode else self._craft_cycle()
            finally:
                self.release_floor()

            if self.stopped:
                return

            if not ok:
                self._cycle_failures += 1
                if self._cycle_failures >= 3:
                    self.log("ERRO: falhas repetidas no ciclo de criacao - RuneMaker pausado, verifique a calibracao.")
                    self.warn_popup("Falhas repetidas no ciclo de criacao - RuneMaker pausado.")
                    self.pause()
                if not self.sleep(1.0):
                    return
                continue
            self._cycle_failures = 0

            self.bump_counter()
            self.log(f"Runa #{self.counter} criada.")

            if target_amount and self.counter >= target_amount:
                self.log(f"Quantidade configurada ({target_amount}) atingida. Parando.")
                return

            delay = InputSimulator.random_delay(
                self.config.get("delay_min", 1.5), self.config.get("delay_max", 2.5)
            )
            if not self.sleep(delay):
                return

    def _simple_craft_cycle(self, dry_run: bool = False) -> bool:
        """Modo `no_hand_mode`: clica direto no slot da blank rune, sem arrastar."""
        blank_x, blank_y = int(self.slot[0]), int(self.slot[1])
        jitter = int(self.config.get("click_jitter", 2))

        if dry_run:
            self.log(f"[dry-run] clicaria no slot da blank rune ({blank_x}, {blank_y})")
            self.log(f"[dry-run] pressionaria a tecla da magia ({self.spell_hotkey})")
            return True

        self.mouse.click(blank_x, blank_y, button="left", jitter=jitter)
        if not self._post_drag_delay():
            return False
        self.mouse.press_key(self.spell_hotkey)
        return True

    def _craft_cycle(self, dry_run: bool = False) -> bool:
        """Modo completo: pega a blank rune, leva pra mao, conjura, guarda."""
        blank_x, blank_y = int(self.slot[0]), int(self.slot[1])
        hand_x, hand_y = int(self.hand_slot[0]), int(self.hand_slot[1])
        output_x, output_y = int(self.output_slot[0]), int(self.output_slot[1])

        # 1. Sobrou item de um ciclo anterior na mao? guarda antes de continuar.
        hand_empty = self._slot_currently_empty("hand_slot_region", self.hand_empty_template)
        if hand_empty is False:
            output_empty = self._slot_currently_empty("output_slot_region", self.output_empty_template)
            if output_empty is False:
                self.log("Backpack de destino cheia - RuneMaker pausado.")
                self.warn_popup("Backpack de destino cheia - RuneMaker pausado.")
                if not dry_run:
                    self.pause()
                return False
            if dry_run:
                self.log(f"[dry-run] arrastaria mao ({hand_x},{hand_y}) -> destino ({output_x},{output_y})")
            else:
                self.mouse.drag(hand_x, hand_y, output_x, output_y, to_jitter=2)
                if not self._post_drag_delay():
                    return False
                if not self._confirm(self._slot_currently_empty("hand_slot_region", self.hand_empty_template), True):
                    self.log("Aviso: mao nao ficou vazia ao guardar item anterior - tentando de novo.")
                    return False

        # 2. Blank rune -> mao
        if dry_run:
            self.log(f"[dry-run] arrastaria blank rune ({blank_x},{blank_y}) -> mao ({hand_x},{hand_y})")
        else:
            self.mouse.drag(blank_x, blank_y, hand_x, hand_y, to_jitter=2)
            if not self._post_drag_delay():
                return False
            if not self._confirm(self._slot_currently_empty("hand_slot_region", self.hand_empty_template), False):
                self.log("Aviso: mao nao ficou ocupada ao pegar a blank rune - tentando de novo.")
                return False

        # 3. Conjura a magia com a rune na mao
        if dry_run:
            self.log(f"[dry-run] pressionaria a tecla da magia ({self.spell_hotkey})")
        else:
            self.mouse.press_key(self.spell_hotkey)
            if not self.sleep(
                InputSimulator.random_delay(self.config.get("delay_min", 1.5), self.config.get("delay_max", 2.5))
            ):
                return False

        # 4. Guarda o resultado na backpack de destino
        output_empty = self._slot_currently_empty("output_slot_region", self.output_empty_template)
        if output_empty is False:
            self.log("Backpack de destino cheia - RuneMaker pausado.")
            self.warn_popup("Backpack de destino cheia - RuneMaker pausado.")
            if not dry_run:
                self.pause()
            return False

        if dry_run:
            self.log(f"[dry-run] arrastaria mao ({hand_x},{hand_y}) -> destino ({output_x},{output_y})")
        else:
            self.mouse.drag(hand_x, hand_y, output_x, output_y, to_jitter=2)
            if not self._post_drag_delay():
                return False
            if not self._confirm(self._slot_currently_empty("hand_slot_region", self.hand_empty_template), True):
                self.log("Aviso: mao nao ficou vazia ao guardar a runa - tentando de novo.")
                return False

        return True
