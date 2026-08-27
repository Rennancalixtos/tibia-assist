from __future__ import annotations

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from gui.qt.components.action_button import ActionButton


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogsPage")
        self._all_lines: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Logs")
        title.setObjectName("HeaderTitle")
        layout.addWidget(title)

        subtitle = QLabel("Histórico completo desta sessão - independente do overlay sobre o jogo.")
        subtitle.setObjectName("HeaderSubtitle")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar nos logs...")
        self.search_edit.textChanged.connect(self._refresh)
        toolbar.addWidget(self.search_edit)
        clear_button = ActionButton("Limpar", variant="secondary")
        clear_button.clicked.connect(self._clear)
        toolbar.addWidget(clear_button)
        layout.addLayout(toolbar)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

    def append(self, message: str) -> None:
        self._all_lines.append(message)
        term = self.search_edit.text().strip().lower()
        if not term or term in message.lower():
            self.text.appendPlainText(message)
            self.text.moveCursor(QTextCursor.End)

    def _refresh(self) -> None:
        term = self.search_edit.text().strip().lower()
        self.text.clear()
        for line in self._all_lines:
            if not term or term in line.lower():
                self.text.appendPlainText(line)
        self.text.moveCursor(QTextCursor.End)

    def _clear(self) -> None:
        self._all_lines.clear()
        self.text.clear()
