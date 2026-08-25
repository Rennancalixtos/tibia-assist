"""Simulacao de mouse e teclado.

Somente input sintetico de alto nivel (SendInput/pyautogui). Nao ha injecao
de DLL, hooking do processo do jogo nem escrita em memoria.

No Windows usamos `pydirectinput` por padrao porque muitos clientes que usam
DirectInput ignoram eventos gerados pelo pyautogui. Em outros sistemas (ou se
o pydirectinput nao estiver instalado) caimos para o pyautogui.
"""

from __future__ import annotations

import random
import time

import pyautogui

# Desliga o fail-safe de canto de tela? NAO. Mantemos ligado de proposito:
# mover o mouse para o canto superior esquerdo aborta o script - e a valvula
# de escape mais confiavel que o usuario tem.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0  # controlamos os delays manualmente

try:  # pragma: no cover - depende do SO
    import pydirectinput

    pydirectinput.FAILSAFE = True
    pydirectinput.PAUSE = 0.0
    _HAS_DIRECTINPUT = True
except Exception:  # ImportError em Linux/macOS
    pydirectinput = None
    _HAS_DIRECTINPUT = False


class InputSimulator:
    """Cliques e teclas com pequenas variacoes aleatorias.

    A aleatoriedade existe para nao repetir exatamente o mesmo pixel/intervalo
    a cada iteracao (movimento humano nao e deterministico), nao para burlar
    qualquer sistema de deteccao.
    """

    def __init__(self, prefer_directinput: bool = True):
        self.use_directinput = bool(prefer_directinput and _HAS_DIRECTINPUT)

    # ------------------------------------------------------------------ mouse
    @property
    def _backend(self):
        return pydirectinput if self.use_directinput else pyautogui

    def move_to(self, x: int, y: int, jitter: int = 0) -> tuple[int, int]:
        """Move o cursor para (x, y) com variacao de +/- `jitter` pixels."""
        tx = int(x) + random.randint(-jitter, jitter) if jitter else int(x)
        ty = int(y) + random.randint(-jitter, jitter) if jitter else int(y)
        try:
            self._backend.moveTo(tx, ty)
        except Exception:
            pyautogui.moveTo(tx, ty)
        return tx, ty

    def click(self, x: int, y: int, button: str = "left", jitter: int = 0) -> tuple[int, int]:
        """Move ate (x, y) (com jitter) e clica com o botao indicado."""
        tx, ty = self.move_to(x, y, jitter)
        # Pequena pausa entre mover e clicar, como um humano faria.
        time.sleep(random.uniform(0.03, 0.12))
        button = "right" if button == "right" else "left"
        try:
            self._backend.click(x=tx, y=ty, button=button)
        except Exception:
            pyautogui.click(x=tx, y=ty, button=button)
        return tx, ty

    # --------------------------------------------------------------- teclado
    def press_key(self, key: str) -> None:
        """Pressiona e solta uma tecla (ex: 'f2', 'space')."""
        key = (key or "").strip().lower()
        if not key:
            return
        try:
            self._backend.keyDown(key)
            time.sleep(random.uniform(0.03, 0.09))
            self._backend.keyUp(key)
        except Exception:
            pyautogui.press(key)

    # ----------------------------------------------------------------- utils
    @staticmethod
    def random_delay(minimum: float, maximum: float) -> float:
        """Sorteia um intervalo entre `minimum` e `maximum` segundos."""
        lo, hi = float(minimum), float(maximum)
        if hi < lo:
            lo, hi = hi, lo
        return random.uniform(lo, hi)

    @staticmethod
    def backend_name() -> str:
        return "pydirectinput" if _HAS_DIRECTINPUT else "pyautogui"
