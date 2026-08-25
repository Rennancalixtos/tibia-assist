"""Coordenacao entre AutoFishing e RuneMaker quando rodam juntos.

Sem isso, os dois workers atropelam o mouse um do outro (cliques/arrastos
simultaneos). O RuneMaker pede uma pausa ao AutoFishing antes de agir
(nunca no meio de uma acao dele) e espera a confirmacao antes de prosseguir;
ao terminar o ciclo, libera a pausa e o AutoFishing retoma sozinho.

So se aplica quando as duas rotinas estao rodando ao mesmo tempo - com o
AutoFishing parado, `fishing_active` fica False e o RuneMaker nunca espera
nada.
"""

from __future__ import annotations

import threading


class AutomationCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fishing_active = False
        self._pause_requested = threading.Event()
        self._pause_confirmed = threading.Event()

    # -------------------------------------------------------------- fishing
    def fishing_started(self) -> None:
        with self._lock:
            self._fishing_active = True
            self._pause_requested.clear()
            self._pause_confirmed.clear()

    def fishing_stopped(self) -> None:
        with self._lock:
            self._fishing_active = False
            self._pause_requested.clear()
            self._pause_confirmed.set()  # libera qualquer um esperando

    @property
    def fishing_active(self) -> bool:
        with self._lock:
            return self._fishing_active

    def should_fishing_pause(self) -> bool:
        return self._pause_requested.is_set()

    def confirm_fishing_paused(self) -> None:
        self._pause_confirmed.set()

    # ------------------------------------------------------------ runemaker
    def request_pause_for_runemaker(self, timeout: float = 5.0) -> bool:
        """Pede ao AutoFishing pra pausar entre ciclos. Devolve True se
        confirmado a tempo (ou se o AutoFishing nem esta rodando)."""
        with self._lock:
            if not self._fishing_active:
                return True
            self._pause_confirmed.clear()
            self._pause_requested.set()
        return self._pause_confirmed.wait(timeout)

    def release_pause_for_runemaker(self) -> None:
        self._pause_requested.clear()
        self._pause_confirmed.clear()
