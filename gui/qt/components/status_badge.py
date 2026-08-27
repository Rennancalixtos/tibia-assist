from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

STATE_LABELS = {
    "running": "Rodando",
    "paused": "Pausado",
    "stopped": "Parado",
    "error": "Erro",
}


class StatusBadge(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.set_state("stopped")

    def set_state(self, state: str) -> None:
        state = state if state in STATE_LABELS else "stopped"
        self.setText(STATE_LABELS[state])
        self.setProperty("state", state)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
