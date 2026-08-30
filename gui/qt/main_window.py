from __future__ import annotations

import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from core.config import RESOURCE_DIR
from core.version import APP_VERSION
from gui.qt.components.sidebar import Sidebar
from gui.qt.controller import APP_NAME, Controller
from gui.qt.overlays.log_overlay import LogOverlay
from gui.qt.pages.about import AboutPage
from gui.qt.pages.dashboard import DashboardPage
from gui.qt.pages.logs import LogsPage
from gui.qt.pages.settings import SettingsPage

class MainWindow(QMainWindow):
    def __init__(self, controller: Controller):
        super().__init__()
        self.controller = controller
        controller.attach_window(self)

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1280, 760)
        self.setMinimumSize(1000, 620)
        self._apply_app_icon()

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar(APP_NAME, APP_VERSION)
        self.sidebar.nav_changed.connect(self._on_nav_changed)
        self.sidebar.logout_requested.connect(self._on_logout_requested)
        root_layout.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 0)
        content_layout.setSpacing(12)
        root_layout.addWidget(content, 1)

        self.log_overlay = LogOverlay(hwnd_resolver=controller.resolve_game_window_hwnd)
        self.log_overlay.configure_chat_region(controller.config_store.section("log").get("chat_region"))

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)

        self.dashboard_page = DashboardPage(controller, self, self.log_overlay)
        self.settings_page = SettingsPage(controller)
        self.logs_page = LogsPage()
        self.about_page = AboutPage()

        self._page_order = ["dashboard", "settings", "logs", "about"]
        for page in (self.dashboard_page, self.settings_page, self.logs_page, self.about_page):
            self.stack.addWidget(page)

        controller.log_line.connect(self.logs_page.append)
        controller.account_info_changed.connect(self.sidebar.session_info.set_info)
        controller.popup_warning.connect(self._on_popup_warning)
        controller.forced_logout.connect(self._on_forced_logout)

        self._on_nav_changed("dashboard")

    def _apply_app_icon(self) -> None:
        icon_path = os.path.join(RESOURCE_DIR, "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _on_nav_changed(self, key: str) -> None:
        if key not in self._page_order:
            return
        self.stack.setCurrentIndex(self._page_order.index(key))
        self.sidebar.set_active(key)

    def _on_logout_requested(self) -> None:
        if self.controller.logout():
            self.close()

    def _on_popup_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def _on_forced_logout(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, message)
        self.close()

    def closeEvent(self, event) -> None:
        self.controller.shutdown()
        self.log_overlay.close()
        for view in self.controller.module_views.values():
            closer = getattr(view, "close_overlays", None)
            if closer is not None:
                closer()
        super().closeEvent(event)
        QApplication.instance().quit()
