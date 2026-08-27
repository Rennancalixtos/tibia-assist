from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QDialog, QLabel, QRubberBand, QWidget

from core.screen_capture import ScreenCapture


def _virtual_geometry() -> tuple[int, int, int, int]:
    try:
        with ScreenCapture() as cap:
            return cap.virtual_screen_size()
    except Exception:
        screen = QWidget().screen()
        if screen is not None:
            geo = screen.virtualGeometry()
            return geo.x(), geo.y(), geo.width(), geo.height()
        return 0, 0, 1920, 1080


class _Overlay(QDialog):
    def __init__(self, hint: str, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        self.setWindowModality(Qt.ApplicationModal)
        self.result_value = None
        self._origin_point = None

        left, top, width, height = _virtual_geometry()
        self._origin = (left, top)
        self.setGeometry(left, top, width, height)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 90);")

        self.hint_label = QLabel(hint, self)
        self.hint_label.setStyleSheet(
            "color: white; font-size: 16px; font-weight: 700; background: transparent;"
        )
        self.hint_label.adjustSize()
        self.hint_label.move(max(0, (width - self.hint_label.width()) // 2), 40)

        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self)

    def to_absolute(self, x: int, y: int) -> tuple[int, int]:
        return int(x) + self._origin[0], int(y) + self._origin[1]

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.result_value = None
            self.reject()
        else:
            super().keyPressEvent(event)


class _RegionOverlay(_Overlay):
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._origin_point = event.pos()
            self._rubber_band.setGeometry(QRect(self._origin_point, self._origin_point))
            self._rubber_band.show()

    def mouseMoveEvent(self, event) -> None:
        if self._origin_point is not None:
            self._rubber_band.setGeometry(QRect(self._origin_point, event.pos()).normalized())

    def mouseReleaseEvent(self, event) -> None:
        if self._origin_point is None:
            return
        rect = QRect(self._origin_point, event.pos()).normalized()
        self._origin_point = None
        if rect.width() < 5 or rect.height() < 5:
            self.result_value = None
        else:
            ax, ay = self.to_absolute(rect.x(), rect.y())
            self.result_value = [ax, ay, rect.width(), rect.height()]
        self.accept()


class _PointOverlay(_Overlay):
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.result_value = self.to_absolute(event.pos().x(), event.pos().y())
            self.accept()


def select_region(
    hint: str = "Arraste para selecionar a região  -  ESC cancela", window=None
) -> list[int] | None:
    if window is not None:
        window.hide()
    try:
        overlay = _RegionOverlay(hint)
        overlay.exec()
        return overlay.result_value
    finally:
        if window is not None:
            window.show()
            window.raise_()
            window.activateWindow()


def select_point(
    hint: str = "Clique no ponto desejado  -  ESC cancela", window=None
) -> tuple[int, int] | None:
    if window is not None:
        window.hide()
    try:
        overlay = _PointOverlay(hint)
        overlay.exec()
        return overlay.result_value
    finally:
        if window is not None:
            window.show()
            window.raise_()
            window.activateWindow()
