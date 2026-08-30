from __future__ import annotations

import threading
import time

PRIORITY_ORDER = ["auto_loot", "target", "training", "runemaker", "fishing", "auto_food", "cavebot"]


def _priority_rank(name: str) -> int:
    try:
        return PRIORITY_ORDER.index(name)
    except ValueError:
        return len(PRIORITY_ORDER)


class AutomationCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._requesters: set[str] = set()
        self._engaged: set[str] = set()
        self._confirm_events: dict[str, threading.Event] = {}

    def started(self, name: str) -> None:
        with self._lock:
            self._active.add(name)

    def stopped(self, name: str) -> None:
        with self._lock:
            self._active.discard(name)
            self._requesters.discard(name)
            self._engaged.discard(name)
            event = self._confirm_events.pop(name, None)
        if event is not None:
            event.set()

    def is_active(self, name: str) -> bool:
        with self._lock:
            return name in self._active

    def set_engaged(self, name: str, engaged: bool) -> None:
        with self._lock:
            if engaged:
                self._engaged.add(name)
            else:
                self._engaged.discard(name)

    def is_engaged(self, name: str) -> bool:
        with self._lock:
            return name in self._engaged

    def _blockers_of(self, name: str) -> list[str]:
        my_rank = _priority_rank(name)
        return [r for r in self._requesters if r != name and _priority_rank(r) < my_rank]

    def should_pause(self, name: str) -> bool:
        with self._lock:
            return bool(self._blockers_of(name))

    def current_blocker(self, name: str) -> str | None:
        with self._lock:
            blockers = self._blockers_of(name)
        if not blockers:
            return None
        return min(blockers, key=_priority_rank)

    def confirm_paused(self, name: str) -> None:
        with self._lock:
            event = self._confirm_events.get(name)
        if event is not None:
            event.set()

    def request_floor(self, name: str, timeout: float = 5.0, cancel_check=None) -> bool:
        with self._lock:
            lower_active = [
                p for p in self._active if p != name and _priority_rank(p) > _priority_rank(name)
            ]
            self._requesters.add(name)
            if not lower_active:
                return True
            events = {p: threading.Event() for p in lower_active}
            self._confirm_events.update(events)

        deadline = time.monotonic() + timeout
        ok = False
        while True:
            if all(event.is_set() for event in events.values()):
                ok = True
                break
            if cancel_check is not None and cancel_check():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))

        with self._lock:
            for p in lower_active:
                self._confirm_events.pop(p, None)
            if not ok:
                self._requesters.discard(name)
        return ok

    def release_floor(self, name: str) -> None:
        with self._lock:
            self._requesters.discard(name)
