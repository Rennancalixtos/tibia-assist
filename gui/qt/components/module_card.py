from __future__ import annotations

import os

from PySide6.QtCore import QSize, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel

from gui.qt.components.action_button import ActionButton
from gui.qt.components.statistic_card import StatisticCard
from gui.qt.components.status_badge import StatusBadge

_ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")


class ModuleCard(QFrame):
    start_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    configure_requested = Signal()

    def __init__(self, title: str, extra_actions=None, stat_specs=None, icon: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("ModuleCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        if icon:
            icon_path = os.path.join(_ICONS_DIR, icon)
            if os.path.exists(icon_path):
                icon_widget = QSvgWidget(icon_path)
                icon_widget.setFixedSize(QSize(20, 20))
                header_row.addWidget(icon_widget)
        title_label = QLabel(title)
        title_label.setObjectName("ModuleCardTitle")
        header_row.addWidget(title_label)
        header_row.addStretch(1)
        self.status_badge = StatusBadge()
        header_row.addWidget(self.status_badge)
        layout.addLayout(header_row)

        if extra_actions:
            extra_row = QHBoxLayout()
            for label, slot in extra_actions:
                button = ActionButton(label, variant="secondary")
                button.clicked.connect(slot)
                extra_row.addWidget(button)
            extra_row.addStretch(1)
            layout.addLayout(extra_row)

        actions_row = QHBoxLayout()
        self.start_button = ActionButton("Iniciar", variant="primary")
        self.pause_button = ActionButton("Pausar/Retomar", variant="secondary")
        self.stop_button = ActionButton("Parar", variant="secondary")
        self.configure_button = ActionButton("Configurar...", variant="secondary")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(self.start_requested.emit)
        self.pause_button.clicked.connect(self.pause_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.configure_button.clicked.connect(self.configure_requested.emit)

        for button in (self.start_button, self.pause_button, self.stop_button, self.configure_button):
            actions_row.addWidget(button)
        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        self._stats: dict[str, StatisticCard] = {}
        stats_row = QHBoxLayout()
        stats_row.setSpacing(18)
        for key, caption, initial in (stat_specs or []):
            stat = StatisticCard(caption, initial)
            self._stats[key] = stat
            stats_row.addWidget(stat)
        stats_row.addStretch(1)
        layout.addLayout(stats_row)

    def set_state(self, state: str) -> None:
        self.status_badge.set_state(state)
        running = state in ("running", "paused")
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.stop_button.setEnabled(running)

    def set_stat(self, key: str, text: str) -> None:
        stat = self._stats.get(key)
        if stat is not None:
            stat.set_value(text)

    def set_stat_caption(self, key: str, text: str) -> None:
        stat = self._stats.get(key)
        if stat is not None:
            stat.set_caption(text)
