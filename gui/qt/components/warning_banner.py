from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QFrame


class WarningBanner(QFrame):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("WarningBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def set_text(self, text: str) -> None:
        self.label.setText(text)
        self.setVisible(bool(text))
