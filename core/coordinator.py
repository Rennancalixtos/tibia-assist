"""Coordenacao entre AutoFishing, RuneMaker e Target quando rodam juntos.

Sem isso, rotinas simultaneas atropelam o mouse umas das outras (cliques
disparados ao mesmo tempo). Generaliza o mecanismo original (so
AutoFishing vs RuneMaker) para N participantes com prioridade: quem quer
agir "pede a vez" (`request_floor`) a todo participante ATIVO de prioridade
menor, espera a confirmacao de pausa de cada um (`should_pause` +
`confirm_paused`, chamados pelo proprio loop de quem esta pausando) e so
entao age; ao terminar, libera a vez (`release_floor`) e quem pausou retoma
sozinho.

So se aplica quando dois ou mais participantes estao ATIVOS (registrados via
`started`/`stopped`) ao mesmo tempo - com so um rodando, `request_floor`
devolve True na hora, sem ninguem esperar nada.

Prioridade (da mais alta para a mais baixa - indice menor pede a vez de
indice maior, nunca o contrario): Target > RuneMaker > AutoFishing, porque
reagir a um monstro tende a ser mais sensivel a tempo do que criar runa, que
por sua vez e mais sensivel do que pescar. Ajustavel aqui, num lugar so.
"""

from __future__ import annotations

import threading

PRIORITY_ORDER = ["target", "training", "runemaker", "fishing"]


def _priority_rank(name: str) -> int:
    try:
        return PRIORITY_ORDER.index(name)
    except ValueError:
        return len(PRIORITY_ORDER)  # nome desconhecido = prioridade minima


class AutomationCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._current_requester: str | None = None
        self._confirm_events: dict[str, threading.Event] = {}

    # ------------------------------------------------------------ ciclo de vida
    def started(self, name: str) -> None:
        with self._lock:
            self._active.add(name)

    def stopped(self, name: str) -> None:
        with self._lock:
            self._active.discard(name)
            if self._current_requester == name:
                self._current_requester = None
            event = self._confirm_events.pop(name, None)
        if event is not None:
            event.set()  # libera quem estivesse esperando a confirmacao desse participante

    def is_active(self, name: str) -> bool:
        with self._lock:
            return name in self._active

    # --------------------------------------------------------------- pausas
    def should_pause(self, name: str) -> bool:
        """Chamado pelo proprio loop de `name` a cada iteracao: True se um
        participante de prioridade MAIOR esta com a vez agora."""
        with self._lock:
            requester = self._current_requester
        return requester is not None and requester != name and _priority_rank(requester) < _priority_rank(name)

    def confirm_paused(self, name: str) -> None:
        """Chamado por `name` assim que ele reconhece o pedido de pausa
        (entre acoes, nunca no meio de uma) - libera quem pediu a vez."""
        with self._lock:
            event = self._confirm_events.get(name)
        if event is not None:
            event.set()

    def request_floor(self, name: str, timeout: float = 5.0) -> bool:
        """`name` quer agir agora - pede a vez a todo participante ATIVO de
        prioridade menor e espera a confirmacao de cada um. Devolve True se
        todos confirmarem a tempo (ou se nao havia ninguem para pausar)."""
        with self._lock:
            lower_active = [
                p for p in self._active if p != name and _priority_rank(p) > _priority_rank(name)
            ]
            if not lower_active:
                return True
            events = {p: threading.Event() for p in lower_active}
            self._confirm_events.update(events)
            self._current_requester = name

        ok = all(event.wait(timeout) for event in events.values())

        with self._lock:
            for p in lower_active:
                self._confirm_events.pop(p, None)
            # `_current_requester` so e limpo em release_floor - mesmo se
            # `ok` for False, mante-lo mantem os retardatarios pausados ate
            # a proxima tentativa (evita agir junto com quem ainda nao
            # confirmou).
        return ok

    def release_floor(self, name: str) -> None:
        with self._lock:
            if self._current_requester == name:
                self._current_requester = None
            self._confirm_events.clear()
