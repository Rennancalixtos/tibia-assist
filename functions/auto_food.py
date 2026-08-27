from __future__ import annotations

import os

import pyautogui as pg
import win32gui

from core import background_input
from core.config import RESOURCE_DIR
from core.worker import BaseWorker

pg.useImageNotFoundException(False)

ICON_NAMES = ["meat1", "meat2", "meat3", "meat4", "meat5", "whitemushrooms", "ham1"]


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
            name: os.path.join(RESOURCE_DIR, "img", "food", f"{name}.png") for name in ICON_NAMES
        }
        self.log("AutoFood iniciado (clique em segundo plano, sem fallback pro mouse real).")

    def teardown(self) -> None:
        self.log(f"AutoFood finalizado. Comidas usadas na sessão: {self.counter}.")

    def _click(self, x: int, y: int) -> None:
        if not win32gui.IsWindow(self.hwnd):
            raise RuntimeError("Janela do jogo não encontrada (hwnd inválido).")
        background_input.post_click(self.hwnd, x, y, "right")

    def loop(self) -> None:
        while not self.stopped:
            if not self.wait_while_paused():
                return

            clicked = False
            for nome, icon in self.icons.items():
                if not self.sleep(self.check_interval):
                    return
                localizar_na_tela = pg.locateCenterOnScreen(icon, confidence=self.confidence)
                if localizar_na_tela:
                    self._click(localizar_na_tela.x, localizar_na_tela.y)
                    self.bump_counter()
                    self.log(f"Comeu {nome} (#{self.counter}). Próxima em {self.eat_cooldown:.0f}s.")
                    clicked = True
                    break

            if clicked:
                if not self.sleep(self.eat_cooldown):
                    return
