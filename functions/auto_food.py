from __future__ import annotations

import os

import cv2
import numpy as np
import win32gui

from core import background_input
from core.config import RESOURCE_DIR
from core.screen_capture import ScreenCapture, load_image
from core.worker import BaseWorker

ICON_NAMES = ["meat1", "meat2", "meat3", "meat4", "meat5", "whitemushrooms", "ham1", "ham2", "ham3", "ham4", "ham5", "fish1"]

BADGE_HEIGHT_RATIO = 0.35


def _load_icon_without_badge(path: str) -> np.ndarray:
    icon = load_image(path)
    if icon is None:
        raise ValueError(f"Ícone de comida não encontrado: {path}")
    crop_height = max(1, int(icon.shape[0] * (1 - BADGE_HEIGHT_RATIO)))
    return icon[:crop_height, :, :].copy()


class AutoFoodWorker(BaseWorker):
    name_label = "auto_food"

    def setup(self) -> None:
        self.hwnd = self.config.get("_background_hwnd")
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            raise ValueError(
                "Janela do jogo (modo background) não configurada ou não encontrada. "
                "Configure em Configurações > Modo background."
            )
        self.confidence = float(self.config.get("confidence", 0.85))
        self.check_interval = float(self.config.get("check_interval", 1.0))
        self.eat_cooldown = float(self.config.get("eat_cooldown", 120.0))
        self.icons = {
            name: _load_icon_without_badge(os.path.join(RESOURCE_DIR, "img", "food", f"{name}.png"))
            for name in ICON_NAMES
        }
        self.min_region_width = max(icon.shape[1] for icon in self.icons.values())
        self.min_region_height = max(icon.shape[0] for icon in self.icons.values())
        self.capture = ScreenCapture()
        self.register_with_coordinator("auto_food")
        self.log("AutoFood iniciado (clique em segundo plano, sem fallback pro mouse real).")

    def teardown(self) -> None:
        capture = getattr(self, "capture", None)
        if capture is not None:
            capture.close()
        self.unregister_from_coordinator()
        self.log(f"AutoFood finalizado. Comidas usadas na sessão: {self.counter}.")

    def _click(self, x: int, y: int) -> None:
        if not win32gui.IsWindow(self.hwnd):
            raise RuntimeError("Janela do jogo não encontrada (hwnd inválido).")
        background_input.post_click(self.hwnd, x, y, "right")

    def _client_region(self) -> tuple[int, int, int, int] | None:
        if not win32gui.IsWindow(self.hwnd):
            raise RuntimeError("Janela do jogo não encontrada (hwnd inválido).")
        rect = background_input.client_screen_rect(self.hwnd)
        if rect is None:
            return None
        _left, _top, width, height = rect
        if width < self.min_region_width or height < self.min_region_height:
            return None
        return rect

    def _locate_icon(self, frame: np.ndarray, icon: np.ndarray) -> tuple[int, int] | None:
        if frame.shape[0] < icon.shape[0] or frame.shape[1] < icon.shape[1]:
            return None
        result = cv2.matchTemplate(frame, icon, cv2.TM_CCOEFF_NORMED)
        _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val < self.confidence:
            return None
        height, width = icon.shape[:2]
        return max_loc[0] + width // 2, max_loc[1] + height // 2

    def loop(self) -> None:
        region_indisponivel_avisado = False
        while not self.stopped:
            if not self.wait_for_higher_priority():
                return

            region = self._client_region()
            if region is None:
                if not region_indisponivel_avisado:
                    self.log(
                        "Janela do jogo minimizada ou sem área visível no momento - "
                        "aguardando ela voltar pra checar a bolsa."
                    )
                    region_indisponivel_avisado = True
                if not self.sleep(self.check_interval):
                    return
                continue
            region_indisponivel_avisado = False

            frame = self.capture.grab(region)
            clicked = False
            for nome, icon in self.icons.items():
                if not self.sleep(self.check_interval):
                    return
                match = self._locate_icon(frame, icon)
                if match:
                    rel_x, rel_y = match
                    abs_x, abs_y = region[0] + rel_x, region[1] + rel_y
                    if not self.wait_for_higher_priority():
                        return
                    if not self.request_floor(timeout=5.0):
                        self.log(f"{nome} encontrado, mas outra rotina está com prioridade - tentando de novo em seguida.")
                        break
                    try:
                        self._click(abs_x, abs_y)
                    finally:
                        self.release_floor()
                    self.bump_counter()
                    self.log(f"Comeu {nome} (#{self.counter}). Próxima em {self.eat_cooldown:.0f}s.")
                    clicked = True
                    break

            if clicked:
                if not self.sleep(self.eat_cooldown):
                    return
