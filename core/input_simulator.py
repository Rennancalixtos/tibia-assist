from __future__ import annotations

import math
import random
import time

import pyautogui
import pytweening

from core import background_input

try:
    import win32gui
except Exception:
    win32gui = None

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0

try:
    import pydirectinput

    pydirectinput.FAILSAFE = True
    pydirectinput.PAUSE = 0.0
    _HAS_DIRECTINPUT = True
except Exception:
    pydirectinput = None
    _HAS_DIRECTINPUT = False


class InputSimulator:
    def __init__(self, prefer_directinput: bool = True, background_hwnd=None, on_fallback=None):
        self.use_directinput = bool(prefer_directinput and _HAS_DIRECTINPUT)
        self.background_hwnd = background_hwnd
        self.on_fallback = on_fallback
        self._background_disabled = False

    def _background_failed(self, exc: Exception) -> None:
        self._background_disabled = True
        if self.on_fallback:
            self.on_fallback(f"Modo background falhou ({exc}) - revertendo para modo padrão (mouse real).")

    def _background_ready(self) -> bool:
        if not self.background_hwnd or self._background_disabled:
            return False
        if win32gui is None:
            self._background_failed(RuntimeError("pywin32 indisponível"))
            return False
        return True

    @property
    def _backend(self):
        return pydirectinput if self.use_directinput else pyautogui

    def move_to(self, x: int, y: int, jitter: int = 0) -> tuple[int, int]:
        tx = int(x) + random.randint(-jitter, jitter) if jitter else int(x)
        ty = int(y) + random.randint(-jitter, jitter) if jitter else int(y)

        start_x, start_y = pyautogui.position()
        distance = math.hypot(tx - start_x, ty - start_y)

        if distance >= 2:
            duration = min(0.55, max(0.10, distance / 1600.0)) * random.uniform(0.75, 1.35)
            steps = max(8, min(45, int(distance / 6)))
            tween = random.choice((pytweening.easeOutQuad, pytweening.easeInOutQuad, pytweening.easeOutCubic))

            bow = random.uniform(-0.12, 0.12) * min(distance, 300)
            mid_x = (start_x + tx) / 2 - bow * (ty - start_y) / distance
            mid_y = (start_y + ty) / 2 + bow * (tx - start_x) / distance

            step_sleep = duration / steps
            for i in range(1, steps + 1):
                e = tween(i / steps)
                ix = (1 - e) ** 2 * start_x + 2 * (1 - e) * e * mid_x + e**2 * tx
                iy = (1 - e) ** 2 * start_y + 2 * (1 - e) * e * mid_y + e**2 * ty
                pyautogui.moveTo(int(ix), int(iy))
                time.sleep(step_sleep)

        pyautogui.moveTo(tx, ty)
        return tx, ty

    def click(self, x: int, y: int, button: str = "left", jitter: int = 0) -> tuple[int, int]:
        button = "right" if button == "right" else "left"

        if self._background_ready():
            try:
                if not win32gui.IsWindow(self.background_hwnd):
                    raise RuntimeError("janela do jogo não encontrada")
                background_input.post_click(self.background_hwnd, x, y, button)
                return int(x), int(y)
            except Exception as exc:
                self._background_failed(exc)

        tx, ty = self.move_to(x, y, jitter)
        time.sleep(random.uniform(0.03, 0.12))
        try:
            self._backend.mouseDown(button=button)
            time.sleep(random.uniform(0.05, 0.15))
            self._backend.mouseUp(button=button)
        except Exception:
            pyautogui.click(x=tx, y=ty, button=button)
        return tx, ty

    def double_click(self, x: int, y: int, jitter: int = 0) -> tuple[int, int]:
        tx, ty = self.click(x, y, button="left", jitter=jitter)
        time.sleep(random.uniform(0.05, 0.12))
        self.click(tx, ty, button="left", jitter=0)
        return tx, ty

    def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        from_jitter: int = 0,
        to_jitter: int = 0,
    ) -> tuple[int, int]:
        if self._background_ready():
            try:
                if not win32gui.IsWindow(self.background_hwnd):
                    raise RuntimeError("janela do jogo não encontrada")
                background_input.post_drag(self.background_hwnd, from_x, from_y, to_x, to_y)
                return int(to_x), int(to_y)
            except Exception as exc:
                self._background_failed(exc)

        self.move_to(from_x, from_y, from_jitter)
        time.sleep(random.uniform(0.05, 0.15))
        self._backend.mouseDown(button="left")
        try:
            time.sleep(random.uniform(0.05, 0.15))
            tx, ty = self.move_to(to_x, to_y, to_jitter)
            time.sleep(random.uniform(0.05, 0.15))
        finally:
            self._backend.mouseUp(button="left")
        return tx, ty

    def press_key(self, key: str) -> None:
        key = (key or "").strip().lower()
        if not key:
            return

        if self._background_ready():
            try:
                if not win32gui.IsWindow(self.background_hwnd):
                    raise RuntimeError("janela do jogo não encontrada")
                background_input.post_key(self.background_hwnd, key)
                return
            except Exception as exc:
                self._background_failed(exc)

        time.sleep(random.uniform(0.02, 0.08))
        try:
            self._backend.keyDown(key)
            time.sleep(random.uniform(0.03, 0.09))
            self._backend.keyUp(key)
        except Exception:
            pyautogui.press(key)

    def is_using_real_mouse(self) -> bool:
        return not self._background_ready()

    @staticmethod
    def current_position() -> tuple[int, int]:
        return pyautogui.position()

    @staticmethod
    def random_delay(minimum: float, maximum: float) -> float:
        lo, hi = float(minimum), float(maximum)
        if hi < lo:
            lo, hi = hi, lo
        return random.uniform(lo, hi)

    @staticmethod
    def backend_name() -> str:
        return "pydirectinput" if _HAS_DIRECTINPUT else "pyautogui"
