from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core import background_input

_WIDTH = 480
_HEIGHT = 54
_MARGIN_BOTTOM = 90
_REPOSITION_INTERVAL_MS = 2000
_BORDER_COLOR = "#ff4d4d"
_BG_COLOR = "#2a0f0f"
_TEXT_COLOR = "#ffdada"

_MESSAGE = (
    "AutoFishing ativo - evite arrastar itens ou mexer na bolsa/equipamento "
    "agora, pra não correr o risco de derrubar algo sem querer."
)


class FishingWarningOverlay(QWidget):
    def __init__(self, hwnd_resolver=None, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self._hwnd_resolver = hwnd_resolver
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(_MESSAGE, self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            f"background-color: {_BG_COLOR}; color: {_TEXT_COLOR}; font-weight: 600; "
            f"font-size: 10pt; padding: 8px 16px; border: 2px solid {_BORDER_COLOR}; border-radius: 8px;"
        )
        layout.addWidget(self.label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)

    def _client_rect(self) -> tuple[int, int, int, int] | None:
        if self._hwnd_resolver is None:
            return None
        hwnd = self._hwnd_resolver()
        if not hwnd:
            return None
        return background_input.client_screen_rect(hwnd)

    def _target_rect(self) -> tuple[int, int, int, int]:
        rect = self._client_rect()
        if rect is not None:
            return rect
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            return geo.x(), geo.y(), geo.width(), geo.height()
        return 0, 0, 1920, 1080

    def reposition(self) -> None:
        left, top, width, height = self._target_rect()
        x = left + (width - _WIDTH) // 2
        y = top + height - _HEIGHT - _MARGIN_BOTTOM
        self.setGeometry(x, y, _WIDTH, _HEIGHT)

    def show(self) -> None:
        self.reposition()
        super().show()
        self._timer.start(_REPOSITION_INTERVAL_MS)

    def hide(self) -> None:
        self._timer.stop()
        super().hide()

    def _on_timer_tick(self) -> None:
        self.reposition()
