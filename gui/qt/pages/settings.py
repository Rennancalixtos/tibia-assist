from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core import profiles as profile_store
from gui.qt.components.action_button import ActionButton
from gui.qt.components.hotkey_button import HotkeyButton
from gui.qt.components.warning_banner import WarningBanner
from gui.qt.controller import APP_NAME, Controller


class SettingsPage(QWidget):
    def __init__(self, controller: Controller, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self.controller = controller

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Configurações")
        title.setObjectName("HeaderTitle")
        layout.addWidget(title)

        layout.addWidget(self._build_hotkeys_box())
        layout.addWidget(self._build_background_box())
        layout.addWidget(self._build_profiles_box())
        layout.addStretch(1)

    def _build_hotkeys_box(self) -> QGroupBox:
        box = QGroupBox("Hotkeys globais")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Pausar/Retomar"))
        self.pause_hotkey = HotkeyButton(self.controller.pause_key)
        row.addWidget(self.pause_hotkey)
        row.addWidget(QLabel("Parar tudo"))
        self.stop_hotkey = HotkeyButton(self.controller.stop_key)
        row.addWidget(self.stop_hotkey)
        self.hotkeys_enabled_check = QCheckBox("ativas")
        self.hotkeys_enabled_check.setChecked(self.controller.hotkeys_enabled)
        row.addWidget(self.hotkeys_enabled_check)
        apply_button = ActionButton("Aplicar", variant="secondary")
        apply_button.clicked.connect(self._apply_hotkeys)
        row.addWidget(apply_button)
        stop_all_button = ActionButton("Parar tudo agora", variant="danger")
        stop_all_button.clicked.connect(self.controller.stop_all)
        row.addWidget(stop_all_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.hotkey_status_label = QLabel(self.controller.hotkey_status)
        self.hotkey_status_label.setObjectName("StatLabel")
        self.hotkey_status_label.setWordWrap(True)
        layout.addWidget(self.hotkey_status_label)
        return box

    def _apply_hotkeys(self) -> None:
        status = self.controller.apply_hotkeys(
            self.pause_hotkey.value(), self.stop_hotkey.value(), self.hotkeys_enabled_check.isChecked()
        )
        self.hotkey_status_label.setText(status)

    def _build_background_box(self) -> QGroupBox:
        box = QGroupBox("Modo background")
        layout = QVBoxLayout(box)

        self.background_enabled_check = QCheckBox(
            "Não usar o mouse real (PostMessage direto pra janela do jogo)"
        )
        self.background_enabled_check.setChecked(self.controller.background_enabled)
        layout.addWidget(self.background_enabled_check)

        background_warning = WarningBanner(
            "Aviso: alguns clients de Tibia (ex: Miracle) processam cliques pela posição real do "
            "cursor do mouse, não pelas coordenadas enviadas em segundo plano. Nesses clients, mexer "
            "o mouse dentro do jogo enquanto uma rotina está clicando (AutoFood, AutoFishing, Cavebot, "
            "RuneMaker, AutoLoot) pode fazer o clique cair no lugar errado - inclusive arrastar ou usar "
            "um item sem querer. Evite usar o mouse dentro do jogo enquanto os módulos estiverem rodando."
        )
        layout.addWidget(background_warning)

        window_row = QHBoxLayout()
        window_row.addWidget(QLabel("Janela:"))
        self.background_window_edit = QLineEdit(self.controller.background_window_title)
        self.background_window_edit.setReadOnly(True)
        window_row.addWidget(self.background_window_edit)
        pick_button = ActionButton("Selecionar janela do jogo...", variant="secondary")
        pick_button.clicked.connect(self._pick_background_window)
        window_row.addWidget(pick_button)
        layout.addLayout(window_row)

        actions_row = QHBoxLayout()
        test_button = ActionButton("Testar clique em background...", variant="secondary")
        test_button.clicked.connect(self._test_background_click)
        actions_row.addWidget(test_button)
        apply_button = ActionButton("Aplicar", variant="secondary")
        apply_button.clicked.connect(self._apply_background_mode)
        actions_row.addWidget(apply_button)
        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        self.background_status_label = QLabel("")
        self.background_status_label.setObjectName("StatLabel")
        self.background_status_label.setWordWrap(True)
        layout.addWidget(self.background_status_label)
        return box

    def _pick_background_window(self) -> None:
        title = self.controller.pick_background_window(self.background_status_label.setText)
        if title:
            self.background_window_edit.setText(title)

    def _apply_background_mode(self) -> None:
        status = self.controller.apply_background_mode(
            self.background_enabled_check.isChecked(), self.background_window_edit.text()
        )
        self.background_status_label.setText(status)

    def _test_background_click(self) -> None:
        self.controller.test_background_click(self.background_window_edit.text())

    def _build_profiles_box(self) -> QGroupBox:
        box = QGroupBox("Perfis")
        layout = QVBoxLayout(box)

        new_row = QHBoxLayout()
        new_row.addWidget(QLabel("Nome do novo perfil:"))
        self.profile_name_edit = QLineEdit()
        new_row.addWidget(self.profile_name_edit)
        save_button = ActionButton("Salvar como novo perfil", variant="secondary")
        save_button.clicked.connect(self._save_profile)
        new_row.addWidget(save_button)
        layout.addLayout(new_row)

        load_row = QHBoxLayout()
        load_row.addWidget(QLabel("Perfil salvo:"))
        self.profile_combo = QComboBox()
        load_row.addWidget(self.profile_combo)
        load_button = ActionButton("Carregar", variant="secondary")
        load_button.clicked.connect(self._load_profile)
        load_row.addWidget(load_button)
        delete_button = ActionButton("Excluir", variant="danger")
        delete_button.clicked.connect(self._delete_profile)
        load_row.addWidget(delete_button)
        layout.addLayout(load_row)

        share_row = QHBoxLayout()
        export_button = ActionButton("Exportar para arquivo...", variant="secondary")
        export_button.clicked.connect(self._export_profile)
        share_row.addWidget(export_button)
        import_button = ActionButton("Importar de arquivo...", variant="secondary")
        import_button.clicked.connect(self._import_profile)
        share_row.addWidget(import_button)
        share_row.addStretch(1)
        layout.addLayout(share_row)

        self.profile_status_label = QLabel("")
        self.profile_status_label.setObjectName("StatLabel")
        self.profile_status_label.setWordWrap(True)
        layout.addWidget(self.profile_status_label)

        hint = QLabel(
            "Um perfil guarda todas as configurações das abas, hotkeys e modo background "
            "(a conta logada não entra no perfil). Carregar um perfil pede pra reiniciar o app.\n\n"
            "Exportar salva o perfil selecionado num arquivo .json à sua escolha (pra compartilhar ou "
            "guardar em outro lugar). Importar lê um desses arquivos e adiciona à lista de perfis salvos."
        )
        hint.setObjectName("StatLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._refresh_profile_list()
        return box

    def _refresh_profile_list(self) -> None:
        names = profile_store.list_profiles()
        current = self.profile_combo.currentText()
        self.profile_combo.clear()
        self.profile_combo.addItems(names)
        if current in names:
            self.profile_combo.setCurrentText(current)

    def _save_profile(self) -> None:
        name = self.profile_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, APP_NAME, "Digite um nome para o perfil.")
            return
        self.controller.sync_config_from_ui()
        try:
            saved_name = profile_store.save_profile(name, self.controller.config_store.data)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Falha ao salvar perfil: {exc}")
            return
        self.profile_status_label.setText(f"Perfil {saved_name!r} salvo.")
        self.profile_name_edit.clear()
        self._refresh_profile_list()
        self.profile_combo.setCurrentText(saved_name)

    def _load_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        if not name:
            QMessageBox.warning(self, APP_NAME, "Selecione um perfil para carregar.")
            return
        if (
            QMessageBox.question(
                self,
                APP_NAME,
                f"Carregar o perfil {name!r} vai substituir as configurações atuais "
                "(exceto a conta logada). Será preciso reiniciar o app depois. Continuar?",
            )
            != QMessageBox.Yes
        ):
            return
        try:
            data = profile_store.load_profile(name)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Falha ao carregar perfil: {exc}")
            return
        self.controller.apply_profile_data(data)
        QMessageBox.information(
            self,
            APP_NAME,
            f"Perfil {name!r} aplicado. Feche e abra o {APP_NAME} de novo para usar as novas configurações.",
        )

    def _export_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        if not name:
            QMessageBox.warning(self, APP_NAME, "Selecione um perfil salvo para exportar primeiro.")
            return
        dest_path, _filter = QFileDialog.getSaveFileName(
            self, "Exportar perfil", f"{name}.json", "Arquivo de perfil (*.json)"
        )
        if not dest_path:
            return
        try:
            profile_store.export_profile(name, dest_path)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Falha ao exportar perfil: {exc}")
            return
        self.profile_status_label.setText(f"Perfil {name!r} exportado para {dest_path!r}.")

    def _import_profile(self) -> None:
        src_path, _filter = QFileDialog.getOpenFileName(
            self, "Importar perfil", "", "Arquivo de perfil (*.json)"
        )
        if not src_path:
            return
        default_name = os.path.splitext(os.path.basename(src_path))[0]
        name, ok = QInputDialog.getText(
            self, APP_NAME, "Nome pra salvar esse perfil importado:", text=default_name
        )
        if not ok or not name.strip():
            return
        try:
            saved_name = profile_store.import_profile_file(src_path, name.strip())
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Falha ao importar perfil: {exc}")
            return
        self.profile_status_label.setText(f"Perfil {saved_name!r} importado.")
        self._refresh_profile_list()
        self.profile_combo.setCurrentText(saved_name)

    def _delete_profile(self) -> None:
        name = self.profile_combo.currentText().strip()
        if not name:
            QMessageBox.warning(self, APP_NAME, "Selecione um perfil para excluir.")
            return
        if (
            QMessageBox.question(self, APP_NAME, f"Excluir o perfil {name!r}? Essa ação não pode ser desfeita.")
            != QMessageBox.Yes
        ):
            return
        profile_store.delete_profile(name)
        self.profile_status_label.setText(f"Perfil {name!r} excluído.")
        self._refresh_profile_list()
