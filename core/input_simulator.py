"""Simulacao de mouse e teclado.

Somente input sintetico de alto nivel (SendInput/pyautogui). Nao ha injecao
de DLL, hooking do processo do jogo nem escrita em memoria.

No Windows usamos `pydirectinput` por padrao porque muitos clientes que usam
DirectInput ignoram eventos gerados pelo pyautogui. Em outros sistemas (ou se
o pydirectinput nao estiver instalado) caimos para o pyautogui.
"""

from __future__ import annotations

import math
import random
import time

import pyautogui
import pytweening

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
        """Arrasta o cursor ate (x, y) (com jitter) em vez de teleportar.

        Cada passo do trajeto usa `pyautogui.moveTo` (absoluto, via
        `SetCursorPos`), NUNCA movimento relativo nem o `moveTo` absoluto do
        `pydirectinput`:

        - `pydirectinput.moveTo` normaliza a coordenada usando so as
          dimensoes do monitor primario, ignorando o desktop virtual - em
          qualquer ponto fora dele (comum com 2+ monitores) calcula a posicao
          errada.
        - Movimento relativo (`SendInput` sem `MOUSEEVENTF_ABSOLUTE`) sofre a
          curva de aceleracao do ponteiro do Windows, que pode amplificar o
          delta de forma imprevisivel e jogar o cursor num canto da tela -
          foi exatamente isso que disparava o fail-safe.

        `SetCursorPos` nao tem nenhum desses problemas: e absoluto, exato e
        funciona em qualquer monitor do desktop virtual.
        """
        tx = int(x) + random.randint(-jitter, jitter) if jitter else int(x)
        ty = int(y) + random.randint(-jitter, jitter) if jitter else int(y)

        start_x, start_y = pyautogui.position()
        distance = math.hypot(tx - start_x, ty - start_y)

        if distance >= 2:
            duration = min(0.55, max(0.10, distance / 1600.0)) * random.uniform(0.75, 1.35)
            steps = max(8, min(45, int(distance / 6)))
            tween = random.choice((pytweening.easeOutQuad, pytweening.easeInOutQuad, pytweening.easeOutCubic))

            # Arco perpendicular a linha reta, com magnitude limitada para nao
            # desviar demais em arrastos longos - uma mao humana raramente
            # move o mouse em linha perfeitamente reta.
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

        pyautogui.moveTo(tx, ty)  # garante que termina exatamente no alvo
        return tx, ty

    def click(self, x: int, y: int, button: str = "left", jitter: int = 0) -> tuple[int, int]:
        """Arrasta ate (x, y) (com jitter) e clica com o botao indicado.

        O clique em si tambem e composto de mouseDown + espera aleatoria +
        mouseUp, em vez de um unico evento instantaneo. Nao passamos x/y para
        mouseDown/mouseUp: no pydirectinput isso dispararia de novo o
        `moveTo` absoluto com bug de monitor (ver `move_to`) bem em cima da
        posicao certa que `move_to` acabou de garantir.
        """
        tx, ty = self.move_to(x, y, jitter)
        # Pequena pausa entre mover e clicar, como um humano faria.
        time.sleep(random.uniform(0.03, 0.12))
        button = "right" if button == "right" else "left"
        try:
            self._backend.mouseDown(button=button)
            time.sleep(random.uniform(0.05, 0.15))
            self._backend.mouseUp(button=button)
        except Exception:
            pyautogui.click(x=tx, y=ty, button=button)
        return tx, ty

    # --------------------------------------------------------------- teclado
    def press_key(self, key: str) -> None:
        """Pressiona e solta uma tecla (ex: 'f2', 'space') com timing aleatorio."""
        key = (key or "").strip().lower()
        if not key:
            return
        time.sleep(random.uniform(0.02, 0.08))  # "tempo de reacao" antes de apertar
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
