from __future__ import annotations

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from core.license import LicenseManager

RATE_LIMIT_MS = 3000
DISCORD_INVITE_URL = "https://discord.gg/zcMm5N4x9M"
_ERROR_COLOR = "#ff5c5c"
_SUCCESS_COLOR = "#3ddc84"


class _AuthWorker(QThread):
    finished_result = Signal(bool)

    def __init__(self, license_manager: LicenseManager, mode: str, email: str, password: str, parent=None):
        super().__init__(parent)
        self.license_manager = license_manager
        self.mode = mode
        self.email = email
        self.password = password

    def run(self) -> None:
        if self.mode == "login":
            ok = self.license_manager.login(self.email, self.password)
        else:
            ok = self.license_manager.signup(self.email, self.password)
        self.finished_result.emit(ok)


class LoginDialog(QDialog):
    def __init__(self, license_manager: LicenseManager, on_save, parent=None):
        super().__init__(parent)
        self.license_manager = license_manager
        self.on_save = on_save
        self._worker: _AuthWorker | None = None
        self._token_before = ""

        self.setWindowTitle("Login - EasyF")
        self.setModal(True)
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self._set_message(license_manager.message or "")
        layout.addWidget(self.message_label)

        form = QFormLayout()
        self.email_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Email:", self.email_edit)
        form.addRow("Senha:", self.password_edit)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.login_button = QPushButton("Entrar")
        self.signup_button = QPushButton("Cadastrar")
        self.cancel_button = QPushButton("Sair")
        self.login_button.clicked.connect(self._login)
        self.signup_button.clicked.connect(self._signup)
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.login_button)
        actions.addWidget(self.signup_button)
        actions.addStretch(1)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)

        hint = QLabel(
            f'Ainda não tem assinatura? <a href="{DISCORD_INVITE_URL}">Clique aqui</a> e '
            "acesse nosso Discord."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9298a8;")
        hint.setTextInteractionFlags(Qt.TextBrowserInteraction)
        hint.setOpenExternalLinks(True)
        layout.addWidget(hint)

        self.email_edit.setFocus()
        self.email_edit.returnPressed.connect(self._login)
        self.password_edit.returnPressed.connect(self._login)

    def _set_message(self, text: str, success: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setStyleSheet(f"color: {_SUCCESS_COLOR if success else _ERROR_COLOR};")

    def _credentials(self) -> tuple[str, str] | None:
        email = self.email_edit.text().strip()
        password = self.password_edit.text()
        if not email or not password:
            self._set_message("Informe email e senha.")
            return None
        return email, password

    def _busy(self, busy: bool) -> None:
        self.login_button.setEnabled(not busy)
        self.signup_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)

    def _start_cooldown(self) -> None:
        self._busy(False)
        self.login_button.setEnabled(False)
        self.signup_button.setEnabled(False)
        QTimer.singleShot(RATE_LIMIT_MS, self._end_cooldown)

    def _end_cooldown(self) -> None:
        self.login_button.setEnabled(True)
        self.signup_button.setEnabled(True)

    def _login(self) -> None:
        if not self.login_button.isEnabled():
            return
        creds = self._credentials()
        if creds is None:
            return
        self._busy(True)
        self._set_message("Entrando...")
        self._worker = _AuthWorker(self.license_manager, "login", *creds)
        self._worker.finished_result.connect(self._on_login_finished)
        self._worker.start()

    def _on_login_finished(self, ok: bool) -> None:
        self.on_save()
        if ok:
            self.accept()
            return
        self._set_message(self.license_manager.message or "Não foi possível entrar.")
        self._start_cooldown()

    def _session_renewed(self, token_before) -> bool:
        token_after = self.license_manager.section.get("refresh_token")
        return bool(token_after) and token_after != token_before

    def _signup(self) -> None:
        if not self.signup_button.isEnabled():
            return
        creds = self._credentials()
        if creds is None:
            return
        self._busy(True)
        self._set_message("Cadastrando...")
        self._token_before = self.license_manager.section.get("refresh_token")
        self._worker = _AuthWorker(self.license_manager, "signup", *creds)
        self._worker.finished_result.connect(self._on_signup_finished)
        self._worker.start()

    def _on_signup_finished(self, _ok: bool) -> None:
        self.on_save()
        if self._session_renewed(self._token_before):
            self._set_message("Cadastro realizado com sucesso!", success=True)
        else:
            self._set_message(self.license_manager.message or "Não foi possível cadastrar.")
        self._start_cooldown()


def prompt_login(license_manager: LicenseManager, on_save, parent=None) -> bool:
    if license_manager.valid:
        return True
    dialog = LoginDialog(license_manager, on_save, parent=parent)
    return dialog.exec() == QDialog.Accepted
