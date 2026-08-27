from __future__ import annotations

from PySide6.QtCore import QThread, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from core.updater import apply_update, check_for_update

_BG = "#1a1d24"
_FG = "#e7e7ea"
_FG_DIM = "#8a8f9c"


class _CheckWorker(QThread):
    downloading = Signal(dict)
    progress = Signal(int, int)
    updated = Signal()
    done = Signal()
    error = Signal(str)
    checking_license = Signal()

    def __init__(self, api_base_url: str, current_version: str, license_manager, parent=None):
        super().__init__(parent)
        self.api_base_url = api_base_url
        self.current_version = current_version
        self.license_manager = license_manager

    def run(self) -> None:
        try:
            update_info = check_for_update(self.api_base_url, self.current_version)
        except Exception as exc:
            self.error.emit(f"Falha ao checar atualização: {exc}")
            return

        if not update_info:
            self._check_license()
            self.done.emit()
            return

        self.downloading.emit(update_info)

        def report(downloaded: int, total: int) -> None:
            self.progress.emit(downloaded, total)

        try:
            applied = apply_update(self.api_base_url, update_info, on_progress=report)
        except Exception as exc:
            self.error.emit(f"Falha ao baixar/instalar a atualização: {exc}")
            return

        if applied:
            self.updated.emit()
        else:
            self.done.emit()

    def _check_license(self) -> None:
        if self.license_manager is None or not self.license_manager.logged_in:
            return
        self.checking_license.emit()
        try:
            self.license_manager.refresh()
        except Exception:
            pass


class SplashDialog(QDialog):
    def __init__(self, api_base_url: str, current_version: str, license_manager=None, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint)
        self.result_value = "checking"
        self._api_base_url = api_base_url
        self._current_version = current_version
        self._license_manager = license_manager
        self._worker: _CheckWorker | None = None

        self.setFixedSize(380, 150)
        self.setStyleSheet(f"background-color: {_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel("EasyF")
        title.setStyleSheet(f"color: {_FG}; font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        self.status_label = QLabel("Verificando atualizações...")
        self.status_label.setStyleSheet(f"color: {_FG_DIM}; font-size: 9pt;")
        layout.addWidget(self.status_label)
        layout.addSpacing(6)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        error_row = QHBoxLayout()
        self.retry_button = QPushButton("Tentar novamente")
        self.skip_button = QPushButton("Abrir mesmo assim")
        self.retry_button.clicked.connect(self._retry)
        self.skip_button.clicked.connect(self._skip)
        error_row.addWidget(self.retry_button)
        error_row.addWidget(self.skip_button)
        self._error_widgets = [self.retry_button, self.skip_button]
        for widget in self._error_widgets:
            widget.hide()
        layout.addLayout(error_row)

        self._center_on_screen()
        QTimer.singleShot(50, self._start_check)

    def _center_on_screen(self) -> None:
        screen = self.screen()
        if screen is not None:
            geo = screen.geometry()
            self.move((geo.width() - self.width()) // 2, (geo.height() - self.height()) // 2)

    def _start_check(self) -> None:
        self._worker = _CheckWorker(self._api_base_url, self._current_version, self._license_manager, self)
        self._worker.downloading.connect(self._on_downloading)
        self._worker.progress.connect(self._on_progress)
        self._worker.updated.connect(self._on_updated)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.checking_license.connect(self._on_checking_license)
        self._worker.start()

    def _on_downloading(self, update_info: dict) -> None:
        self.status_label.setText(f"Baixando atualização {update_info.get('version', '')}...")

    def _on_progress(self, downloaded: int, total: int) -> None:
        if not total:
            self.status_label.setText(f"Baixando atualização... {downloaded} bytes")
            return
        pct = int(downloaded * 100 / total)
        self.status_label.setText(f"Baixando atualização... {pct}% ({downloaded}/{total})")
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self.progress.setValue(pct)

    def _on_updated(self) -> None:
        self.status_label.setText("Atualização concluída - reabrindo...")
        self.result_value = "updated"
        QTimer.singleShot(300, self.accept)

    def _on_checking_license(self) -> None:
        self.status_label.setText("Verificando licença...")

    def _on_done(self) -> None:
        self.result_value = "no_update"
        self.accept()

    def _on_error(self, message: str) -> None:
        self.result_value = "error"
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self.progress.hide()
        self.status_label.setText(message)
        for widget in self._error_widgets:
            widget.show()

    def _retry(self) -> None:
        for widget in self._error_widgets:
            widget.hide()
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status_label.setText("Verificando atualizações...")
        self.result_value = "checking"
        self._start_check()

    def _skip(self) -> None:
        self.result_value = "skip"
        self.accept()


def run_update_check(api_base_url: str, current_version: str, license_manager=None) -> str:
    dialog = SplashDialog(api_base_url, current_version, license_manager)
    dialog.exec()
    return dialog.result_value
