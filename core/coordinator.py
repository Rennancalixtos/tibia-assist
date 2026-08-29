from __future__ import annotations

import threading

PRIORITY_ORDER = ["target", "training", "runemaker", "fishing", "auto_food", "cavebot"]


def _priority_rank(name: str) -> int:
    try:
        return PRIORITY_ORDER.index(name)
    except ValueError:
        return len(PRIORITY_ORDER)


class AutomationCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._current_requester: str | None = None
        self._confirm_events: dict[str, threading.Event] = {}

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
            event.set()

    def is_active(self, name: str) -> bool:
        with self._lock:
            return name in self._active

    def should_pause(self, name: str) -> bool:
        with self._lock:
            requester = self._current_requester
        return requester is not None and requester != name and _priority_rank(requester) < _priority_rank(name)

    def confirm_paused(self, name: str) -> None:
        with self._lock:
            event = self._confirm_events.get(name)
        if event is not None:
            event.set()

    def request_floor(self, name: str, timeout: float = 5.0) -> bool:
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
            if not ok and self._current_requester == name:
                self._current_requester = None
        return ok

    def release_floor(self, name: str) -> None:
        with self._lock:
            if self._current_requester == name:
                self._current_requester = None
