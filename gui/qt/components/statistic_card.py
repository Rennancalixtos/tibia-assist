from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatisticCard(QWidget):
    def __init__(self, caption: str, initial: str = "-", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("StatLabel")
        self.value_label = QLabel(initial)
        self.value_label.setObjectName("StatValue")

        layout.addWidget(self.caption_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)

    def set_caption(self, text: str) -> None:
        self.caption_label.setText(text)
