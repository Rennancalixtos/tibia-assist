from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from core import background_input

_MIN_WIDTH = 480
_HEIGHT = 170
_MARGIN_X = 10
_MARGIN_Y = 48
_MAX_LINES = 200
_CHAT_MARGIN = 8


class LogOverlay(QWidget):
    def __init__(self, hwnd_resolver=None, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self._hwnd_resolver = hwnd_resolver
        self._chat_region: tuple[int, int, int, int] | None = None
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(0.85)
        self.setStyleSheet("background-color: #0e1015;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            "background-color: #0e1015; color: #39ff14; border: none; "
            "font-family: Consolas, monospace; font-size: 9pt;"
        )
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        layout.addWidget(self.text)

        self._layout_position()

    def configure_chat_region(self, region) -> None:
        self._chat_region = tuple(region) if region and len(region) == 4 else None
        self._layout_position()

    def _layout_position(self) -> None:
        if self._chat_region is not None:
            cx, cy, cw, ch = self._chat_region
            box_width = max(200, cw // 2 - _CHAT_MARGIN)
            box_height = min(_HEIGHT, max(60, ch - 2 * _CHAT_MARGIN))
            x = cx + cw - box_width - _CHAT_MARGIN
            y = cy + ch - box_height - _CHAT_MARGIN
            self.setGeometry(max(0, x), max(0, y), box_width, box_height)
            return

        rect = self._client_rect()
        if rect is not None:
            left, top, width, height = rect
            x = left + _MARGIN_X
            y = top + height - _HEIGHT - _MARGIN_Y
            box_width = min(700, max(_MIN_WIDTH, width - 2 * _MARGIN_X))
        else:
            screen = QGuiApplication.primaryScreen()
            geo = screen.geometry() if screen is not None else QRect(0, 0, 1920, 1080)
            x = _MARGIN_X
            y = geo.height() - _HEIGHT - _MARGIN_Y
            box_width = _MIN_WIDTH
        self.setGeometry(max(0, x), max(0, y), box_width, _HEIGHT)

    def _client_rect(self) -> tuple[int, int, int, int] | None:
        if self._hwnd_resolver is None:
            return None
        hwnd = self._hwnd_resolver()
        if not hwnd:
            return None
        return background_input.client_screen_rect(hwnd)

    def append(self, message: str) -> None:
        self._layout_position()
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
