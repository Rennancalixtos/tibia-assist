from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

_BORDER_COLOR = "#39ff14"
_BORDER_THICKNESS = 2
_LABEL_BG = "#1a1d24"
_LABEL_FG = "#39ff14"
_GAP_ABOVE_LOG = 6


class _RegionMarker(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        pen = QPen(QColor(_BORDER_COLOR))
        pen.setWidth(_BORDER_THICKNESS)
        painter.setPen(pen)
        half = _BORDER_THICKNESS // 2
        painter.drawRect(half, half, self.width() - _BORDER_THICKNESS, self.height() - _BORDER_THICKNESS)


class _ValueLabel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(0.85)
        self.setStyleSheet(f"background-color: {_LABEL_BG};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        self.label = QLabel("Mana: ?")
        self.label.setStyleSheet(f"color: {_LABEL_FG}; font-weight: 700; font-size: 10pt; background: transparent;")
        layout.addWidget(self.label)


class ManaOverlay:
    def __init__(self, parent=None, log_overlay=None):
        self._parent = parent
        self._log_overlay = log_overlay
        self._marker: _RegionMarker | None = None
        self._label: _ValueLabel | None = None
        self._region: tuple[int, int, int, int] | None = None

    def configure_region(self, region) -> None:
        self._region = tuple(region) if region and len(region) == 4 else None
        if self._marker is not None:
            self._layout_marker()

    def show(self) -> None:
        if self._region and self._marker is None:
            self._marker = _RegionMarker(self._parent)
            self._layout_marker()
            self._marker.show()
        if self._log_overlay is not None and self._label is None:
            self._label = _ValueLabel(self._parent)
            self._layout_label()
            self._label.show()
        self.update_value(None)

    def hide(self) -> None:
        if self._marker is not None:
            self._marker.close()
            self._marker = None
        if self._label is not None:
            self._label.close()
            self._label = None

    def update_value(self, value) -> None:
        if self._label is not None:
            self._label.label.setText(f"Mana: {value}" if value is not None else "Mana: ?")
            self._layout_label()

    def _layout_marker(self) -> None:
        if self._marker is None or not self._region:
            return
        x, y, w, h = self._region
        t = _BORDER_THICKNESS
        self._marker.setGeometry(x - t, y - t, w + 2 * t, h + 2 * t)

    def _layout_label(self) -> None:
        if self._label is None or self._log_overlay is None:
            return
        self._label.adjustSize()
        log_geo = self._log_overlay.geometry()
        x = log_geo.x()
        y = log_geo.y() - self._label.height() - _GAP_ABOVE_LOG
        self._label.move(max(0, x), max(0, y))
