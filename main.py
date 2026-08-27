from __future__ import annotations

import sys
import tkinter.messagebox as messagebox

REQUIRED = [
    ("mss", "mss"),
    ("cv2", "opencv-python"),
    ("numpy", "numpy"),
    ("pyautogui", "pyautogui"),
]


def check_dependencies() -> list[str]:
    missing = []
    for module_name, package_name in REQUIRED:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)
    return missing


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
        message = (
            "Dependências ausentes: " + ", ".join(missing) + "\n\n"
            "Instale com:\n    pip install -r requirements.txt"
        )
        print(message, file=sys.stderr)
        try:
            messagebox.showerror("EasyF", message)
        except Exception:
            pass
        return 1

    from core.config import Config
    from core.license import LicenseManager
    from core.version import APP_VERSION
    from gui.app import App
    from gui.license_dialog import run_startup_login
    from gui.splash import run_update_check

    config_store = Config()

    api_base_url = config_store.get("license.api_base_url", "")
    license_manager = LicenseManager(config_store.section("license"))

    update_result = run_update_check(api_base_url, APP_VERSION, license_manager)
    config_store.save()
    if update_result == "updated":
        return 0

    while True:
        if not run_startup_login(license_manager, config_store.save):
            return 1

        app = App(config_store, license_manager)
        app.mainloop()
        if not getattr(app, "logout_requested", False):
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
