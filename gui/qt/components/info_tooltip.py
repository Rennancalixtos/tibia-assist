from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class InfoIcon(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__("ⓘ", parent)
        self.setObjectName("InfoIcon")
        self.setToolTip(text)
        self.setCursor(Qt.PointingHandCursor)
