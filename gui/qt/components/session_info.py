from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel

from gui.qt.components.action_button import ActionButton


class SessionInfoCard(QFrame):
    logout_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SessionInfoCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        self.user_label = QLabel("-")
        self.user_label.setObjectName("SessionInfoUser")
        self.user_label.setWordWrap(True)

        self.expiry_label = QLabel("-")
        self.expiry_label.setObjectName("SessionInfoExpiry")
        self.expiry_label.setWordWrap(True)

        self.logout_button = ActionButton("Sair da conta", variant="danger")
        self.logout_button.clicked.connect(self.logout_requested.emit)

        layout.addWidget(self.user_label)
        layout.addWidget(self.expiry_label)
        layout.addWidget(self.logout_button)

    def set_info(self, email: str, expires_label: str) -> None:
        self.user_label.setText(f"Logado como: {email or '-'}")
        self.expiry_label.setText(f"Acesso restante: {expires_label}")
