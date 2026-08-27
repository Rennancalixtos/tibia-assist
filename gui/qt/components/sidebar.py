from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QLabel, QPushButton, QVBoxLayout, QWidget

from gui.qt.components.session_info import SessionInfoCard

NAV_ITEMS = (
    ("dashboard", "Dashboard"),
    ("settings", "Configurações"),
    ("logs", "Logs"),
    ("about", "Sobre"),
)


class Sidebar(QWidget):
    nav_changed = Signal(str)
    logout_requested = Signal()

    def __init__(self, app_name: str, app_version: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(2)

        logo = QLabel(app_name)
        logo.setObjectName("SidebarLogo")
        layout.addWidget(logo)

        version = QLabel(f"v{app_version}")
        version.setObjectName("SidebarVersion")
        layout.addWidget(version)

        layout.addSpacing(24)

        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, label in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self.nav_changed.emit(k))
            layout.addWidget(button)
            self._group.addButton(button)
            self._buttons[key] = button
        self._buttons["dashboard"].setChecked(True)

        layout.addStretch(1)

        self.session_info = SessionInfoCard()
        self.session_info.logout_requested.connect(self.logout_requested.emit)
        layout.addWidget(self.session_info)

    def set_active(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None:
            button.setChecked(True)
