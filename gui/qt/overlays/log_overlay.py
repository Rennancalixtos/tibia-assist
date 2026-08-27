from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

_WIDTH = 460
_HEIGHT = 170
_MARGIN_X = 10
_MARGIN_Y = 48
_MAX_LINES = 200


class LogOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(0.55)
        self.setStyleSheet("background-color: black;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            "background-color: black; color: #39ff14; border: none; "
            "font-family: Consolas, monospace; font-size: 9pt;"
        )
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        layout.addWidget(self.text)

        self._layout_position()

    def _layout_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        geo = screen.geometry() if screen is not None else QRect(0, 0, 1920, 1080)
        x = _MARGIN_X
        y = geo.height() - _HEIGHT - _MARGIN_Y
        self.setGeometry(max(0, x), max(0, y), _WIDTH, _HEIGHT)

    def append(self, message: str) -> None:
        self.text.appendPlainText(message)
        document = self.text.document()
        overflow = document.blockCount() - _MAX_LINES
        if overflow > 0:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            for _ in range(overflow):
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()
        self.text.moveCursor(QTextCursor.End)
