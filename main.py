from __future__ import annotations

import sys

REQUIRED = [
    ("mss", "mss"),
    ("cv2", "opencv-python"),
    ("numpy", "numpy"),
    ("pyautogui", "pyautogui"),
    ("PySide6", "PySide6"),
]


def check_dependencies() -> list[str]:
    missing = []
    for module_name, package_name in REQUIRED:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)
    return missing


def _show_dependency_error(message: str) -> None:
    print(message, file=sys.stderr)
    try:
        import tkinter.messagebox as messagebox

        messagebox.showerror("EasyF", message)
    except Exception:
        pass


def main() -> int:
    if not getattr(sys, "frozen", False):
        from core.elevation import is_admin, relaunch_elevated

        if not is_admin():
            if relaunch_elevated():
                return 0
            print(
                "AVISO: não foi possível obter privilégio de administrador - "
                "clique/tecla pode não ter efeito se o cliente do jogo rodar elevado.",
                file=sys.stderr,
            )

    missing = check_dependencies()
    if missing:
        _show_dependency_error(
            "Dependências ausentes: " + ", ".join(missing) + "\n\n"
            "Instale com:\n    pip install -r requirements.txt"
        )
        return 1

    from PySide6.QtWidgets import QApplication

    from core.config import Config
    from core.license import LicenseManager
    from core.version import APP_VERSION
    from gui.qt.controller import Controller
    from gui.qt.dialogs.login_dialog import prompt_login
    from gui.qt.dialogs.splash_dialog import run_update_check
    from gui.qt.main_window import MainWindow
    from gui.qt.theme import build_stylesheet

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(build_stylesheet())

    config_store = Config()
    api_base_url = config_store.get("license.api_base_url", "")
    license_manager = LicenseManager(config_store.section("license"))

    update_result = run_update_check(api_base_url, APP_VERSION, license_manager)
    config_store.save()
    if update_result == "updated":
        return 0

    while True:
        if not prompt_login(license_manager, config_store.save):
            return 1

        controller = Controller(config_store, license_manager)
        window = MainWindow(controller)
        window.show()
        app.exec()

        if not controller.logout_requested:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
