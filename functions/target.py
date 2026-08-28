from __future__ import annotations

import difflib

import cv2
import numpy as np

from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image
from core.worker import BaseWorker
from functions.rune_maker import OCRUnavailable

try:
    import pytesseract
except ImportError:
    pytesseract = None


NAME_OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz' "


def preprocess_name_for_ocr(frame: np.ndarray) -> np.ndarray:
    bright = np.max(frame, axis=2).astype(np.uint8)
    bright = cv2.resize(bright, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    bright = cv2.medianBlur(bright, 3)
    _, binary = cv2.threshold(bright, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(binary) < 127:
        binary = cv2.bitwise_not(binary)
    return binary


def read_name(frame: np.ndarray) -> str:
    if pytesseract is None:
        raise OCRUnavailable(
            "pytesseract não instalado. Instale-o e o Tesseract OCR."
        )
    processed = preprocess_name_for_ocr(frame)
    try:
        text = pytesseract.image_to_string(processed, config=NAME_OCR_CONFIG)
    except Exception as exc:
        raise OCRUnavailable(f"Falha ao executar o Tesseract: {exc}") from exc
    return " ".join(text.split())


def battle_list_empty_score(frame: np.ndarray, template: np.ndarray | None) -> float | None:
    if template is None or frame.size == 0:
        return None
    fh, fw = frame.shape[:2]
    th, tw = template.shape[:2]
    th, tw = min(th, fh), min(tw, fw)
    if th <= 0 or tw <= 0:
        return None
    template = template[:th, :tw]
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
    return float(result.max())


def battle_list_is_empty(frame: np.ndarray, template: np.ndarray | None, threshold: float = 0.85) -> bool | None:
    score = battle_list_empty_score(frame, template)
    if score is None:
        return None
    return score >= threshold


def attack_color_present(
    frame: np.ndarray,
    rgb: tuple[int, int, int] = (254, 0, 0),
    tolerance: int = 6,
    min_pixels: int = 3,
) -> bool:
    if frame is None or frame.size == 0:
        return False
    r, g, b = rgb
    target_bgr = np.array([b, g, r], dtype=np.int16)
    lower = np.clip(target_bgr - tolerance, 0, 255).astype(np.uint8)
    upper = np.clip(target_bgr + tolerance, 0, 255).astype(np.uint8)
    mask = cv2.inRange(frame, lower, upper)
    return int(np.count_nonzero(mask)) >= min_pixels


def normalize_name(name: str | None) -> str:
    return " ".join((name or "").strip().split()).lower()


def name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


class TargetWorker(BaseWorker):
    name_label = "target"

    def setup(self) -> None:
        self.capture = ScreenCapture()
        self.mouse = InputSimulator(
            background_hwnd=self.config.get("_background_hwnd"),
            on_fallback=self.log,
        )
        self.register_with_coordinator("target")

        self.battle_list_region = self.config.get("battle_list_region")
        if not is_valid_region(self.battle_list_region):
            raise ValueError("Região da Battle List não configurada.")

        self.empty_template = self._load_template("battle_empty_template")
        if self.empty_template is None:
            raise ValueError("Modelo de lista vazia não calibrado.")
        self.empty_threshold = 0.85

        rgb = self.config.get("attack_color_rgb") or [254, 0, 0]
        self.attack_rgb = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        self.attack_tolerance = int(self.config.get("attack_color_tolerance", 6))
        self.attack_min_pixels = int(self.config.get("attack_color_min_pixels", 3))

        self.attack_key = (self.config.get("attack_key") or "space").strip().lower()
        if not self.attack_key:
            raise ValueError("Tecla de ataque não configurada.")
        self.attack_check_delay = float(self.config.get("attack_check_delay", 0.5))
        self.max_unconfirmed_attacks = int(self.config.get("max_unconfirmed_attacks", 10))

        self._last_warning = ""
        self._empty_score_failures = 0
        self._unconfirmed_attacks = 0

        self.log(
            f"Target iniciado (tecla de ataque='{self.attack_key}', "
            f"backend={InputSimulator.backend_name()})."
        )

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        self.log(f"Target finalizado. Ataques disparados na sessão: {self.counter}.")

    def _load_template(self, key: str):
        path = self.config.get(key)
        if not path:
            return None
        try:
            return load_image(path)
        except Exception:
            return None

    def warn_once(self, message: str) -> None:
        if message != self._last_warning:
            self.log(message)
            self._last_warning = message

    def battle_list_empty_score(self) -> float | None:
        frame = self.capture.grab(self.battle_list_region)
        return battle_list_empty_score(frame, self.empty_template)

    def is_battle_list_empty(self) -> bool:
        score = self.battle_list_empty_score()
        if score is None:
            self._empty_score_failures += 1
            if self._empty_score_failures >= 3:
                raise RuntimeError(
                    "Modelo de lista vazia maior que a região configurada - "
                    "reconfigure a região/modelo da Battle List antes de continuar."
                )
            self.warn_once(
                "AVISO: modelo de lista vazia maior que a região configurada - "
                "recalibre a região da Battle List ou o modelo."
            )
            return False
        self._empty_score_failures = 0
        return score >= self.empty_threshold

    def is_attacking(self) -> bool:
        frame = self.capture.grab(self.battle_list_region)
        return attack_color_present(frame, self.attack_rgb, self.attack_tolerance, self.attack_min_pixels)

    def press_attack_key(self, dry_run: bool = False) -> None:
        if dry_run:
            self.log(f"[dry-run] pressionaria a tecla de ataque '{self.attack_key}'")
            return
        self.mouse.press_key(self.attack_key)

    def loop(self) -> None:
        while not self.stopped:
            if not self.wait_for_higher_priority():
                return

            if self.is_battle_list_empty():
                if not self.sleep(InputSimulator.random_delay(
                    self.config.get("idle_delay_min", 2.0), self.config.get("idle_delay_max", 4.0)
                )):
                    return
                continue

            if not self.is_attacking():
                if not self.request_floor(timeout=5.0):
                    if not self.sleep(1.0):
                        return
                    continue
                try:
                    self.press_attack_key()
                finally:
                    self.release_floor()

                if not self.sleep(self.attack_check_delay):
                    return
                attacking = self.is_attacking()
                self.bump_counter()
                self.log(
                    f"Ataque #{self.counter}: tecla '{self.attack_key}' pressionada - "
                    f"atacando={'sim' if attacking else 'não confirmado'}."
                )
                if attacking:
                    self._unconfirmed_attacks = 0
                else:
                    self._unconfirmed_attacks += 1
                    if self._unconfirmed_attacks >= self.max_unconfirmed_attacks:
                        raise RuntimeError(
                            f"{self.max_unconfirmed_attacks} ataques seguidos sem confirmação - "
                            "provavelmente a região da Battle List/cor de ataque não bate mais "
                            "com a posição atual do jogo. Reconfigure antes de continuar."
                        )

            while not self.stopped:
                if not self.wait_for_higher_priority():
                    return
                if not self.sleep(InputSimulator.random_delay(
                    self.config.get("engaged_delay_min", 1.0), self.config.get("engaged_delay_max", 2.0)
                )):
                    return
                if self.is_battle_list_empty():
                    break
                if not self.is_attacking():
                    break
