from __future__ import annotations

import random
import time

import cv2
import numpy as np

from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image
from core.worker import BaseWorker


def find_water_tiles_hsv(
    frame: np.ndarray,
    hsv_lower: list[int],
    hsv_upper: list[int],
    min_area: int = 200,
    tile_size: int = 32,
    min_tile_coverage: float = 0.35,
) -> list[tuple[int, int, int]]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array(hsv_lower, dtype=np.uint8)
    upper = np.array(hsv_upper, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    if cv2.countNonZero(mask) < min_area:
        return []

    height, width = mask.shape[:2]
    tile_size = max(4, int(tile_size))
    results: list[tuple[int, int, int]] = []
    for ty in range(0, height, tile_size):
        for tx in range(0, width, tile_size):
            cell = mask[ty : ty + tile_size, tx : tx + tile_size]
            cell_area = cell.shape[0] * cell.shape[1]
            if cell_area == 0:
                continue
            coverage = cv2.countNonZero(cell) / cell_area
            if coverage < min_tile_coverage:
                continue
            cx = tx + cell.shape[1] // 2
            cy = ty + cell.shape[0] // 2
            results.append((cx, cy, int(coverage * 100)))

    results.sort(key=lambda item: item[2], reverse=True)
    return results


def draw_tile_grid(
    frame: np.ndarray,
    tiles: list[tuple[int, int, int]],
    tile_size: int = 32,
) -> np.ndarray:
    tile_size = max(4, int(tile_size))
    out = frame.copy()
    height, width = out.shape[:2]

    for x in range(0, width, tile_size):
        cv2.line(out, (x, 0), (x, height), (60, 60, 60), 1)
    for y in range(0, height, tile_size):
        cv2.line(out, (0, y), (width, y), (60, 60, 60), 1)

    half = tile_size // 2
    for cx, cy, coverage in tiles:
        top_left = (cx - half, cy - half)
        bottom_right = (cx + half, cy + half)
        cv2.rectangle(out, top_left, bottom_right, (0, 255, 0), 2)
        cv2.circle(out, (cx, cy), 2, (0, 0, 255), -1)

    return out


def find_water_template(
    frame: np.ndarray, template: np.ndarray, threshold: float = 0.80
) -> list[tuple[int, int, int]]:
    if template is None or frame.shape[0] < template.shape[0] or frame.shape[1] < template.shape[1]:
        return []

    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
    ys, xs = np.where(result >= float(threshold))
    th, tw = template.shape[:2]

    candidates = sorted(
        ((int(x), int(y), float(result[y, x])) for x, y in zip(xs, ys)),
        key=lambda item: item[2],
        reverse=True,
    )

    picked: list[tuple[int, int, int]] = []
    for x, y, score in candidates:
        cx, cy = x + tw // 2, y + th // 2
        if any(abs(cx - px) < tw and abs(cy - py) < th for px, py, _ in picked):
            continue
        picked.append((cx, cy, int(score * 1000)))
        if len(picked) >= 40:
            break
    return picked


def sample_hsv_range(frame: np.ndarray, tolerance: tuple[int, int, int] = (10, 60, 60)):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    median = np.median(hsv.reshape(-1, 3), axis=0)
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
    return lower, upper, float(median[2])


def median_brightness(frame: np.ndarray) -> float:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return float(np.median(hsv[:, :, 2]))


def dynamic_v_bounds(
    hsv_lower: list[int], hsv_upper: list[int], current_brightness: float, reference_brightness: float
) -> tuple[list[int], list[int], float]:
    delta = current_brightness - reference_brightness
    lower = list(hsv_lower)
    upper = list(hsv_upper)
    lower[2] = int(max(0, min(255, lower[2] + delta)))
    upper[2] = int(max(0, min(255, upper[2] + delta)))
    return lower, upper, delta


class AutoFishingWorker(BaseWorker):
    name_label = "fishing"

    def setup(self) -> None:
        self.capture = ScreenCapture()
        self.mouse = InputSimulator(
            background_hwnd=self.config.get("_background_hwnd"),
            on_fallback=self.log,
        )
        self.region = self.config.get("region")
        self.mode = self.config.get("detection_mode", "hsv")
        self.template = None
        self.register_with_coordinator("fishing")

        self.rod_slot = self.config.get("rod_slot")
        if not (isinstance(self.rod_slot, (list, tuple)) and len(self.rod_slot) == 2):
            raise ValueError("Slot da vara de pescar nao configurado.")

        if not is_valid_region(self.region):
            raise ValueError("Regiao de pesca nao configurada.")

        if self.mode == "template":
            path = self.config.get("template_path")
            self.template = load_image(path) if path else None
            if self.template is None:
                raise ValueError(
                    "Template de agua nao encontrado. Calibre um template ou use o modo HSV."
                )

        self.break_enabled = bool(self.config.get("break_enabled", True))
        self._schedule_next_break()

        self.hsv_reference_brightness = self.config.get("hsv_reference_brightness")
        self._last_logged_delta = 0.0

        self.auto_recalibrate_enabled = bool(self.config.get("auto_recalibrate_enabled", False))
        self.auto_recalibrate_interval_minutes = float(self.config.get("auto_recalibrate_interval_minutes", 15) or 15)
        self.ema_alpha = float(self.config.get("ema_alpha", 0.15))
        self._recent_water_pixels: list[np.ndarray] = []
        self._next_recalibrate_at = time.monotonic() + self.auto_recalibrate_interval_minutes * 60

        self.log(
            f"AutoFishing iniciado (modo={self.mode}, regiao={self.region}, "
            f"vara={tuple(self.rod_slot)}, backend={InputSimulator.backend_name()})."
        )

    def _schedule_next_break(self) -> None:
        interval = InputSimulator.random_delay(
            self.config.get("break_interval_min", 60), self.config.get("break_interval_max", 300)
        )
        self._next_break_at = time.monotonic() + interval

    def maybe_take_break(self) -> bool:
        if not self.break_enabled or time.monotonic() < self._next_break_at:
            return True
        duration = InputSimulator.random_delay(
            self.config.get("break_duration_min", 15), self.config.get("break_duration_max", 120)
        )
        self.log(f"Pausa para descanso: {duration:.0f}s.")
        if not self.sleep(duration):
            return False
        self._schedule_next_break()
        return True

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        self.log(f"AutoFishing finalizado. Lances na sessao: {self.counter}.")

    def detect(
        self, frame: np.ndarray, hsv_lower: list[int] | None = None, hsv_upper: list[int] | None = None
    ) -> list[tuple[int, int, int]]:
        if self.mode == "template":
            return find_water_template(
                frame, self.template, self.config.get("template_threshold", 0.80)
            )
        return find_water_tiles_hsv(
            frame,
            hsv_lower if hsv_lower is not None else self.config.get("hsv_lower", [90, 60, 40]),
            hsv_upper if hsv_upper is not None else self.config.get("hsv_upper", [130, 255, 255]),
            int(self.config.get("min_area", 200)),
            int(self.config.get("tile_size", 32)),
            float(self.config.get("min_tile_coverage", 0.35)),
        )

    def _recalibrate_ema(self) -> None:
        if not self._recent_water_pixels:
            return
        samples = np.concatenate(self._recent_water_pixels, axis=0)
        median = np.median(samples, axis=0)
        alpha = self.ema_alpha

        hsv_lower = list(self.config.get("hsv_lower", [90, 60, 40]))
        hsv_upper = list(self.config.get("hsv_upper", [130, 255, 255]))
        new_lower, new_upper = [], []
        for i in range(3):
            span = (hsv_upper[i] - hsv_lower[i]) / 2
            center = (hsv_upper[i] + hsv_lower[i]) / 2
            new_center = alpha * float(median[i]) + (1 - alpha) * center
            ceiling = 179 if i == 0 else 255
            new_lower.append(int(max(0, new_center - span)))
            new_upper.append(int(min(ceiling, new_center + span)))

        old_reference = self.hsv_reference_brightness if self.hsv_reference_brightness is not None else float(median[2])
        new_reference = alpha * float(median[2]) + (1 - alpha) * old_reference

        self.config["hsv_lower"] = new_lower
        self.config["hsv_upper"] = new_upper
        self.hsv_reference_brightness = new_reference
        self.emit_config_update(
            {"hsv_lower": new_lower, "hsv_upper": new_upper, "hsv_reference_brightness": new_reference}
        )
        self.log(f"Recalibracao automatica (EMA): HSV ajustado para {new_lower} - {new_upper}.")
        self._recent_water_pixels.clear()

    def _collect_recalibration_samples(self, frame: np.ndarray, targets: list[tuple[int, int, int]]) -> None:
        tile_size = int(self.config.get("tile_size", 32))
        half = tile_size // 2
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        height, width = hsv_frame.shape[:2]
        for cx, cy, coverage in targets:
            if coverage < 90:
                continue
            y0, y1 = max(0, cy - half), min(height, cy + half)
            x0, x1 = max(0, cx - half), min(width, cx + half)
            if y1 <= y0 or x1 <= x0:
                continue
            self._recent_water_pixels.append(hsv_frame[y0:y1, x0:x1].reshape(-1, 3))
        if len(self._recent_water_pixels) > 200:
            del self._recent_water_pixels[: len(self._recent_water_pixels) - 200]

    def loop(self) -> None:
        max_casts = int(self.config.get("max_casts", 0) or 0)
        button = self.config.get("mouse_button", "right")
        jitter = int(self.config.get("click_jitter", 2))
        randomize = bool(self.config.get("randomize_target", True))
        tile_size = int(self.config.get("tile_size", 32))
        rx, ry = int(self.region[0]), int(self.region[1])
        rod_x, rod_y = int(self.rod_slot[0]), int(self.rod_slot[1])

        while not self.stopped:
            if not self.wait_for_higher_priority():
                return

            if not self.maybe_take_break():
                return

            frame = self.capture.grab(self.region)

            effective_lower = effective_upper = None
            if self.mode != "template" and self.hsv_reference_brightness is not None:
                hsv_lower = self.config.get("hsv_lower", [90, 60, 40])
                hsv_upper = self.config.get("hsv_upper", [130, 255, 255])
                current_brightness = median_brightness(frame)
                effective_lower, effective_upper, delta = dynamic_v_bounds(
                    hsv_lower, hsv_upper, current_brightness, self.hsv_reference_brightness
                )
                if abs(delta - self._last_logged_delta) > 15:
                    self.log(f"Brilho da cena mudou (delta V={delta:+.0f}), ajustando deteccao de agua (dia/noite).")
                    self._last_logged_delta = delta

            targets = self.detect(frame, effective_lower, effective_upper)

            if self.auto_recalibrate_enabled and self.mode != "template":
                self._collect_recalibration_samples(frame, targets)
                if time.monotonic() >= self._next_recalibrate_at:
                    self._recalibrate_ema()
                    self._next_recalibrate_at = time.monotonic() + self.auto_recalibrate_interval_minutes * 60

            if not targets:
                self.log("Nenhuma tile de agua encontrada na regiao. Aguardando...")
                if not self.sleep(1.5):
                    return
                continue

            cx, cy, _score = random.choice(targets) if randomize else targets[0]

            half = max(0, tile_size // 2 - 3)
            if half:
                cx += random.randint(-half, half)
                cy += random.randint(-half, half)

            self.mouse.click(rod_x, rod_y, button="right", jitter=jitter)
            if not self.sleep(InputSimulator.random_delay(0.10, 0.25)):
                return

            abs_x, abs_y = rx + cx, ry + cy
            clicked_x, clicked_y = self.mouse.click(abs_x, abs_y, button=button, jitter=jitter)

            self.bump_counter()
            self.log(
                f"Vara aberta em ({rod_x}, {rod_y}) -> lance #{self.counter} em "
                f"({clicked_x}, {clicked_y}) - {len(targets)} tile(s) de agua detectada(s)."
            )

            if max_casts and self.counter >= max_casts:
                self.log(f"Limite de {max_casts} lances atingido. Parando.")
                return

            delay = InputSimulator.random_delay(
                self.config.get("delay_min", 1.8), self.config.get("delay_max", 3.2)
            )
            if not self.sleep(delay):
                return
