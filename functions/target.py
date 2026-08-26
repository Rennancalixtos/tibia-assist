from __future__ import annotations

import difflib
from dataclasses import dataclass

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


@dataclass
class BattleListRow:
    index: int
    occupied: bool
    name: str | None = None
    selection: str = "none"
    life_pct: int | None = None


def read_name(frame: np.ndarray) -> str:
    if pytesseract is None:
        raise OCRUnavailable(
            "pytesseract nao instalado. Instale-o e o Tesseract OCR."
        )
    processed = preprocess_name_for_ocr(frame)
    try:
        text = pytesseract.image_to_string(processed, config=NAME_OCR_CONFIG)
    except Exception as exc:
        raise OCRUnavailable(f"Falha ao executar o Tesseract: {exc}") from exc
    return " ".join(text.split())


def row_region(battle_list_region, row_height: int, index: int) -> list[int]:
    x, y, w, _h = battle_list_region
    return [int(x), int(y + index * row_height), int(w), int(row_height)]


def row_count_for(battle_list_region, row_height: int) -> int:
    if not battle_list_region or not row_height:
        return 0
    return max(0, int(battle_list_region[3]) // int(row_height))


def crop_offset(frame: np.ndarray, offset) -> np.ndarray | None:
    if not offset:
        return None
    dx, dy, w, h = (int(v) for v in offset)
    fh, fw = frame.shape[:2]
    x0, y0 = max(0, dx), max(0, dy)
    x1, y1 = min(fw, dx + w), min(fh, dy + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return frame[y0:y1, x0:x1]


def row_is_empty(frame_row: np.ndarray, empty_template: np.ndarray | None, threshold: float = 0.90) -> bool | None:
    if empty_template is None or frame_row.size == 0:
        return None
    template = empty_template
    if frame_row.shape[:2] != template.shape[:2]:
        template = cv2.resize(template, (frame_row.shape[1], frame_row.shape[0]))
    result = cv2.matchTemplate(frame_row, template, cv2.TM_CCOEFF_NORMED)
    result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
    return float(result.max()) >= threshold


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


def _text_foreground_mask(crop: np.ndarray, brightness_cutoff: int = 100) -> np.ndarray:
    return np.max(crop, axis=2) > brightness_cutoff


def sample_name_text_color(frame: np.ndarray, tolerance: tuple[int, int, int] = (10, 60, 60)):
    mask = _text_foreground_mask(frame)
    pixels = frame[mask] if np.any(mask) else frame.reshape(-1, 3)
    hsv_pixels = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    median = np.median(hsv_pixels, axis=0)
    th, ts, tv = tolerance
    lower = [
        int(max(0, median[0] - th)),
        int(max(0, median[1] - ts)),
        int(max(0, median[2] - tv)),
    ]
    upper = [
        int(min(179, median[0] + th)),
        int(min(255, median[1] + ts)),
        int(min(255, median[2] + tv)),
    ]
    return lower, upper


def classify_name_color(
    crop: np.ndarray | None,
    attack_ranges: list[tuple[list[int], list[int]]] | None,
    follow_ranges: list[tuple[list[int], list[int]]] | None,
    min_coverage: float = 0.15,
) -> str:
    if crop is None or crop.size == 0:
        return "none"
    mask = _text_foreground_mask(crop)
    total_fg = int(np.count_nonzero(mask))
    if total_fg == 0:
        return "none"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    def coverage(hsv_ranges) -> float:
        if not hsv_ranges:
            return 0.0
        best = 0.0
        for lower, upper in hsv_ranges:
            color_mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
            cov = int(np.count_nonzero((color_mask > 0) & mask)) / total_fg
            best = max(best, cov)
        return best

    red_cov = coverage(attack_ranges)
    green_cov = coverage(follow_ranges)
    if red_cov >= min_coverage and red_cov >= green_cov:
        return "attack"
    if green_cov >= min_coverage:
        return "follow"
    return "none"


def normalize_name(name: str | None) -> str:
    return " ".join((name or "").strip().split()).lower()


def name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def name_passes_filter(name: str | None, creature_list: list[str], mode: str, threshold: float = 0.80) -> bool:
    norm_name = normalize_name(name)
    if not norm_name:
        return False
    norm_list = [normalize_name(n) for n in creature_list if normalize_name(n)]
    matched = any(name_similarity(norm_name, entry) >= threshold for entry in norm_list)
    return matched if mode == "whitelist" else not matched


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
            raise ValueError("Regiao da Battle List nao configurada.")

        self.empty_template = self._load_template("battle_empty_template")
        if self.empty_template is None:
            raise ValueError("Modelo de lista vazia nao calibrado.")
        self.empty_threshold = float(self.config.get("empty_match_threshold", 0.85))

        rgb = self.config.get("attack_color_rgb") or [254, 0, 0]
        self.attack_rgb = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        self.attack_tolerance = int(self.config.get("attack_color_tolerance", 6))
        self.attack_min_pixels = int(self.config.get("attack_color_min_pixels", 3))

        self.attack_key = (self.config.get("attack_key") or "space").strip().lower()
        if not self.attack_key:
            raise ValueError("Tecla de ataque nao configurada.")
        self.attack_check_delay = float(self.config.get("attack_check_delay", 0.5))

        self._last_warning = ""

        self.log(
            f"Target iniciado (tecla de ataque='{self.attack_key}', "
            f"backend={InputSimulator.backend_name()})."
        )

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        self.log(f"Target finalizado. Ataques disparados na sessao: {self.counter}.")

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
            self.warn_once(
                "AVISO: modelo de lista vazia maior que a regiao configurada - "
                "recalibre a regiao da Battle List ou o modelo."
            )
            return False
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
                    f"atacando={'sim' if attacking else 'nao confirmado'}."
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
