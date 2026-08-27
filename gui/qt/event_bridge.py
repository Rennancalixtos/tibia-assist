from __future__ import annotations

import queue

from PySide6.QtCore import QThread, Signal


class EventBridge(QThread):
    event_received = Signal(str, str, object)

    def __init__(self, events: "queue.Queue[tuple]", parent=None):
        super().__init__(parent)
        self._events = events
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            try:
                source, kind, payload = self._events.get(timeout=0.2)
            except queue.Empty:
                continue
            self.event_received.emit(source, kind, payload)
