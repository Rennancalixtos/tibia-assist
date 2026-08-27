from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

_OBJECT_NAMES = {
    "primary": "ActionPrimary",
    "secondary": "ActionSecondary",
    "danger": "ActionDanger",
}


class ActionButton(QPushButton):
    def __init__(self, text: str, variant: str = "secondary", parent=None):
        super().__init__(text, parent)
        self.setObjectName(_OBJECT_NAMES.get(variant, "ActionSecondary"))
        self.setCursor(Qt.PointingHandCursor)
