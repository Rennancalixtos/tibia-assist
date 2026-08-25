"""Base comum para as rotinas em background (AutoFishing e RuneMaker).

Cada rotina roda em uma thread separada e nunca toca em widgets do tkinter
diretamente: toda comunicacao com a GUI passa por uma `queue.Queue`, drenada
pela janela principal no loop do tkinter.
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime


class BaseWorker(threading.Thread):
    """Thread com suporte a pausa, parada e envio de eventos para a GUI."""

    name_label = "worker"

    def __init__(self, config: dict, events: "queue.Queue[tuple]"):
        super().__init__(daemon=True)
        self.config = dict(config)
        self.events = events
        self._stop_event = threading.Event()
        self._resume_event = threading.Event()
        self._resume_event.set()  # comeca despausado
        self.counter = 0

    # ------------------------------------------------------------- controles
    def stop(self) -> None:
        self._stop_event.set()
        self._resume_event.set()  # libera quem estiver esperando para poder sair

    def pause(self) -> None:
        self._resume_event.clear()
        self.emit("state", "paused")
        self.log("Pausado.")

    def resume(self) -> None:
        self._resume_event.set()
        self.emit("state", "running")
        self.log("Retomado.")

    def toggle_pause(self) -> None:
        if self.is_paused:
            self.resume()
        else:
            self.pause()

    @property
    def is_paused(self) -> bool:
        return not self._resume_event.is_set()

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    # ---------------------------------------------------------------- eventos
    def emit(self, kind: str, payload=None) -> None:
        self.events.put((self.name_label, kind, payload))

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.emit("log", f"[{stamp}] {message}")

    def bump_counter(self, amount: int = 1) -> None:
        self.counter += amount
        self.emit("counter", self.counter)

    # ------------------------------------------------------------------ util
    def sleep(self, seconds: float) -> bool:
        """Dorme em fatias curtas para responder rapido a pause/stop.

        Devolve False se a rotina foi parada durante a espera.
        """
        deadline = time.monotonic() + max(0.0, float(seconds))
        while time.monotonic() < deadline:
            if self.stopped:
                return False
            time.sleep(min(0.05, deadline - time.monotonic()))
        return not self.stopped

    def wait_while_paused(self) -> bool:
        """Bloqueia enquanto pausado. Devolve False se foi parado."""
        while not self._resume_event.wait(timeout=0.1):
            if self.stopped:
                return False
        return not self.stopped

    # ------------------------------------------------------------------ ciclo
    def run(self) -> None:  # pragma: no cover - integracao
        self.emit("state", "running")
        try:
            self.setup()
            self.loop()
        except Exception as exc:  # erro inesperado nao pode matar a GUI
            self.log(f"ERRO: {exc}")
        finally:
            self.teardown()
            self.emit("state", "stopped")

    # Ganchos sobrescritos pelas subclasses ---------------------------------
    def setup(self) -> None:
        pass

    def loop(self) -> None:
        raise NotImplementedError

    def teardown(self) -> None:
        pass
