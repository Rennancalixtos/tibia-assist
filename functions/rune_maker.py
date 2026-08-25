"""RuneMaker - cria runas em sequencia clicando na blank rune e usando a magia.

Fluxo de cada ciclo:
    1. le soul points e mana por OCR (Tesseract) nas regioes configuradas
    2. se algum estiver abaixo do minimo, pausa sozinho (evita spam sem soul)
    3. clica no slot da blank rune e pressiona a hotkey da magia
    4. espera um intervalo aleatorio (>= cooldown real da magia) e repete

Tudo baseado em pixels da tela + input simulado. Nenhuma leitura de memoria.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region
from core.worker import BaseWorker

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789/"


class OCRUnavailable(RuntimeError):
    pass


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
            "ou desmarque as verificacoes de soul/mana."
        )
    processed = preprocess_for_ocr(frame)
    try:
        text = pytesseract.image_to_string(processed, config=OCR_CONFIG)
    except Exception as exc:  # binario do Tesseract ausente
        raise OCRUnavailable(f"Falha ao executar o Tesseract: {exc}") from exc

    match = re.search(r"\d+", text.replace(" ", ""))
    return int(match.group()) if match else None


class RuneMakerWorker(BaseWorker):
    name_label = "runemaker"

    def setup(self) -> None:
        self.capture = ScreenCapture()
        self.mouse = InputSimulator()

        self.slot = self.config.get("blank_slot")
        if not (isinstance(self.slot, (list, tuple)) and len(self.slot) == 2):
            raise ValueError("Slot da blank rune nao configurado.")

        self.spell_hotkey = (self.config.get("spell_hotkey") or "").strip()
        if not self.spell_hotkey:
            raise ValueError("Tecla de atalho da magia nao configurada.")

        self.check_soul = bool(self.config.get("check_soul", True))
        self.check_mana = bool(self.config.get("check_mana", True))

        if self.check_soul and not is_valid_region(self.config.get("soul_region")):
            raise ValueError("Regiao de OCR do soul nao configurada.")
        if self.check_mana and not is_valid_region(self.config.get("mana_region")):
            raise ValueError("Regiao de OCR da mana nao configurada.")

        tesseract_cmd = (self.config.get("tesseract_cmd") or "").strip()
        if tesseract_cmd and pytesseract is not None:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        # Evita repetir a mesma mensagem de "sem recurso" a cada iteracao.
        self._last_warning = ""

        self.log(
            f"RuneMaker iniciado (magia={self.spell_hotkey}, slot={self.slot}, "
            f"backend={InputSimulator.backend_name()})."
        )

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.log(f"RuneMaker finalizado. Runas criadas na sessao: {self.counter}.")

    # -------------------------------------------------------------------- OCR
    def read_status(self, key: str) -> int | None:
        region = self.config.get(f"{key}_region")
        frame = self.capture.grab(region)
        return read_number(frame)

    def resources_ok(self) -> bool:
        """True se soul e mana estao acima dos minimos configurados."""
        if self.check_soul:
            soul = self.read_status("soul")
            if soul is None:
                self.warn_once("Nao consegui ler o soul via OCR. Verifique a regiao configurada.")
                return False
            if soul < int(self.config.get("min_soul", 5)):
                self.warn_once(f"Soul insuficiente ({soul}). Aguardando regenerar...")
                return False

        if self.check_mana:
            mana = self.read_status("mana")
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

    # ------------------------------------------------------------------ ciclo
    def loop(self) -> None:
        target_amount = int(self.config.get("amount", 0) or 0)
        jitter = int(self.config.get("click_jitter", 2))
        slot_x, slot_y = int(self.slot[0]), int(self.slot[1])

        while not self.stopped:
            if not self.wait_while_paused():
                return

            try:
                if not self.resources_ok():
                    # Recursos baixos: espera um pouco em vez de martelar a magia.
                    if not self.sleep(3.0):
                        return
                    continue
            except OCRUnavailable as exc:
                self.log(f"ERRO de OCR: {exc}")
                return

            # Seleciona a blank rune e conjura a magia.
            self.mouse.click(slot_x, slot_y, button="left", jitter=jitter)
            if not self.sleep(InputSimulator.random_delay(0.10, 0.25)):
                return
            self.mouse.press_key(self.spell_hotkey)

            self.bump_counter()
            self.log(f"Runa #{self.counter} conjurada (tecla {self.spell_hotkey}).")

            if target_amount and self.counter >= target_amount:
                self.log(f"Quantidade configurada ({target_amount}) atingida. Parando.")
                return

            delay = InputSimulator.random_delay(
                self.config.get("delay_min", 1.5), self.config.get("delay_max", 2.5)
            )
            if not self.sleep(delay):
                return
