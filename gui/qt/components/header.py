from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gui.qt.components.action_button import ActionButton


class Header(QWidget):
    settings_requested = Signal()

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Header")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("HeaderTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("HeaderSubtitle")
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.subtitle_label)

        layout.addLayout(text_col)
        layout.addStretch(1)

        self.settings_button = ActionButton("Configurações", variant="secondary")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.settings_button)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
