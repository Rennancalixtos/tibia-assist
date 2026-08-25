"""AutoFishing - detecta agua na regiao configurada e clica com a vara.

Fluxo de cada ciclo:
    1. captura a regiao monitorada (mss)
    2. procura tiles de agua (HSV ou template matching, escolha do usuario)
    3. move o mouse ate um tile com jitter de alguns pixels e clica
    4. espera um intervalo aleatorio (animacao da pesca) e repete

Tudo baseado em pixels da tela + input simulado. Nenhuma leitura de memoria.
"""

from __future__ import annotations

import random
import time

import cv2
import numpy as np

from core.input_simulator import InputSimulator
from core.screen_capture import ScreenCapture, is_valid_region, load_image
from core.worker import BaseWorker


# --------------------------------------------------------------------------
# Deteccao
# --------------------------------------------------------------------------
def find_water_hsv(
    frame: np.ndarray,
    hsv_lower: list[int],
    hsv_upper: list[int],
    min_area: int = 200,
) -> list[tuple[int, int, int]]:
    """Encontra blobs de agua por faixa de cor em HSV.

    Devolve uma lista de (cx, cy, area) em coordenadas RELATIVAS ao frame,
    ordenada da maior para a menor area.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array(hsv_lower, dtype=np.uint8)
    upper = np.array(hsv_upper, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    # Remove ruido (bordas de sprites, particulas) e fecha buracos pequenos.
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results: list[tuple[int, int, int]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
        results.append((cx, cy, int(area)))

    results.sort(key=lambda item: item[2], reverse=True)
    return results


def find_water_template(
    frame: np.ndarray, template: np.ndarray, threshold: float = 0.80
) -> list[tuple[int, int, int]]:
    """Encontra ocorrencias do template de agua via cv2.matchTemplate.

    Devolve (cx, cy, score*1000) relativos ao frame, com supressao simples de
    deteccoes sobrepostas.
    """
    if template is None or frame.shape[0] < template.shape[0] or frame.shape[1] < template.shape[1]:
        return []

    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    # Templates de cor totalmente uniforme geram NaN/Inf (variancia zero);
    # zeramos esses valores para nao virarem falsos positivos.
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
        # Supressao de nao-maximos: descarta qualquer deteccao que se sobreponha
        # a uma ja aceita (duas tiles distintas nao se sobrepoem).
        if any(abs(cx - px) < tw and abs(cy - py) < th for px, py, _ in picked):
            continue
        picked.append((cx, cy, int(score * 1000)))
        if len(picked) >= 40:
            break
    return picked


def sample_hsv_range(frame: np.ndarray, tolerance: tuple[int, int, int] = (10, 60, 60)):
    """Calcula uma faixa HSV a partir de um recorte de agua feito pelo usuario.

    Usa a mediana de cada canal +/- tolerancia, o que e mais estavel do que a
    media quando o recorte inclui alguns pixels que nao sao agua.
    """
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
    return lower, upper


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------
class AutoFishingWorker(BaseWorker):
    name_label = "fishing"

    def setup(self) -> None:
        self.capture = ScreenCapture()
        self.mouse = InputSimulator()
        self.region = self.config.get("region")
        self.mode = self.config.get("detection_mode", "hsv")
        self.template = None

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

        self.log(
            f"AutoFishing iniciado (modo={self.mode}, regiao={self.region}, "
            f"vara={tuple(self.rod_slot)}, backend={InputSimulator.backend_name()})."
        )

    # ------------------------------------------------------------- pausas
    def _schedule_next_break(self) -> None:
        """Sorteia daqui a quanto tempo a proxima pausa de descanso acontece."""
        interval = InputSimulator.random_delay(
            self.config.get("break_interval_min", 60), self.config.get("break_interval_max", 300)
        )
        self._next_break_at = time.monotonic() + interval

    def maybe_take_break(self) -> bool:
        """Se chegou a hora, para de pescar por um periodo aleatorio.

        Devolve False se a rotina foi parada durante a pausa.
        """
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
        self.log(f"AutoFishing finalizado. Lances na sessao: {self.counter}.")

    def detect(self, frame: np.ndarray) -> list[tuple[int, int, int]]:
        if self.mode == "template":
            return find_water_template(
                frame, self.template, self.config.get("template_threshold", 0.80)
            )
        return find_water_hsv(
            frame,
            self.config.get("hsv_lower", [90, 60, 40]),
            self.config.get("hsv_upper", [130, 255, 255]),
            int(self.config.get("min_area", 200)),
        )

    def loop(self) -> None:
        max_casts = int(self.config.get("max_casts", 0) or 0)
        button = self.config.get("mouse_button", "right")
        jitter = int(self.config.get("click_jitter", 2))
        randomize = bool(self.config.get("randomize_target", True))
        rx, ry = int(self.region[0]), int(self.region[1])
        rod_x, rod_y = int(self.rod_slot[0]), int(self.rod_slot[1])

        while not self.stopped:
            if not self.wait_while_paused():
                return

            if not self.maybe_take_break():
                return

            frame = self.capture.grab(self.region)
            targets = self.detect(frame)

            if not targets:
                self.log("Nenhuma tile de agua encontrada na regiao. Aguardando...")
                if not self.sleep(1.5):
                    return
                continue

            # Sorteia entre os melhores candidatos para nao clicar sempre no
            # mesmo tile (e tambem evita ficar preso num falso positivo).
            pool = targets[: min(5, len(targets))]
            cx, cy, _score = random.choice(pool) if randomize else targets[0]

            # Abre a vara com o botao direito (equivalente a "usar" o item) antes
            # de aplica-la na agua com o esquerdo - mecanica de "use with" do Tibia.
            self.mouse.click(rod_x, rod_y, button="right", jitter=jitter)
            if not self.sleep(InputSimulator.random_delay(0.10, 0.25)):
                return

            # Coordenada relativa -> absoluta na tela
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
