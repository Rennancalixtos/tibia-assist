from __future__ import annotations

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class LogPanel(QWidget):
    def __init__(self, title: str = "Log", max_lines: int = 500, parent=None):
        super().__init__(parent)
        self.max_lines = max_lines

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if title:
            label = QLabel(title)
            label.setObjectName("StatLabel")
            layout.addWidget(label)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFixedHeight(180)
        layout.addWidget(self.text)

    def append(self, message: str) -> None:
        self.text.appendPlainText(message)
        document = self.text.document()
        overflow = document.blockCount() - self.max_lines
        if overflow > 0:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            for _ in range(overflow):
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()
        self.text.moveCursor(QTextCursor.End)

    def clear(self) -> None:
        self.text.clear()
