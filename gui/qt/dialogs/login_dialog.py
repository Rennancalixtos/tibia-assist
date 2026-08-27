from __future__ import annotations

import webbrowser

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from core.license import LicenseManager

RATE_LIMIT_MS = 3000


class LoginDialog(QDialog):
    def __init__(self, license_manager: LicenseManager, on_save, parent=None):
        super().__init__(parent)
        self.license_manager = license_manager
        self.on_save = on_save

        self.setWindowTitle("Login - EasyF")
        self.setModal(True)
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)

        self.message_label = QLabel(license_manager.message or "")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("color: #ff5c5c;")
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
        self.signup_button = QPushButton("Cadastrar...")
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
            "Ainda não tem assinatura? Clique em Cadastrar para criar a conta e "
            "abrir o pagamento no navegador."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9298a8;")
        layout.addWidget(hint)

        self.email_edit.setFocus()
        self.email_edit.returnPressed.connect(self._login)
        self.password_edit.returnPressed.connect(self._login)

    def _credentials(self) -> tuple[str, str] | None:
        email = self.email_edit.text().strip()
        password = self.password_edit.text()
        if not email or not password:
            self.message_label.setText("Informe email e senha.")
            return None
        return email, password

    def _start_cooldown(self) -> None:
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
        self.login_button.setEnabled(False)
        self.signup_button.setEnabled(False)
        self.message_label.setText("Entrando...")
        ok = self.license_manager.login(*creds)
        self.on_save()
        if ok:
            self.accept()
            return
        self.message_label.setText(self.license_manager.message or "Não foi possível entrar.")
        self._maybe_offer_checkout()
        self._start_cooldown()

    def _signup(self) -> None:
        if not self.signup_button.isEnabled():
            return
        creds = self._credentials()
        if creds is None:
            return
        self.login_button.setEnabled(False)
        self.signup_button.setEnabled(False)
        self.message_label.setText("Cadastrando...")
        self.license_manager.signup(*creds)
        self.on_save()
        url = self.license_manager.start_checkout()
        if url:
            webbrowser.open(url)
            self.message_label.setText(
                "Conta criada! Finalize o pagamento na aba que abriu no navegador e "
                "depois clique em Entrar aqui."
            )
        else:
            self.message_label.setText(self.license_manager.message or "Não foi possível iniciar o pagamento.")
        self._start_cooldown()

    def _maybe_offer_checkout(self) -> None:
        if not self.license_manager.logged_in:
            return
        if self.license_manager.section.get("status") == "active":
            return
        url = self.license_manager.start_checkout()
        if url:
            webbrowser.open(url)
            self.message_label.setText(
                "Login ok, mas sem assinatura ativa. Abrimos o pagamento no navegador - "
                "finalize e clique em Entrar novamente."
            )


def prompt_login(license_manager: LicenseManager, on_save, parent=None) -> bool:
    if license_manager.valid:
        return True
    dialog = LoginDialog(license_manager, on_save, parent=parent)
    return dialog.exec() == QDialog.Accepted
