from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.version import APP_VERSION


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AboutPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        name = QLabel("EasyF")
        name.setObjectName("HeaderTitle")
        layout.addWidget(name)

        version = QLabel(f"Versão {APP_VERSION}")
        version.setObjectName("HeaderSubtitle")
        layout.addWidget(version)

        disclaimer = QLabel(
            "Automação de apoio para Tibia. Uso por conta e risco do usuário: pode "
            "violar os termos de uso do servidor/jogo e resultar em banimento."
        )
        disclaimer.setObjectName("FooterText")
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        layout.addStretch(1)
