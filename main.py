"""EasyF - ponto de entrada.

Uso:
    python main.py

Automacao baseada exclusivamente em captura de tela + simulacao de mouse e
teclado. O programa nao le nem escreve na memoria do jogo, nao injeta codigo
no cliente e nao esconde nada do sistema operacional.
"""

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
    """Devolve a lista de pacotes obrigatorios que nao estao instalados."""
    missing = []
    for module_name, package_name in REQUIRED:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)
    return missing


def main() -> int:
    missing = check_dependencies()
    if missing:
        message = (
            "Dependencias ausentes: " + ", ".join(missing) + "\n\n"
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
    from core.updater import apply_update, check_for_update
    from core.version import APP_VERSION
    from gui.app import App
    from gui.license_dialog import run_startup_login

    config_store = Config()

    # Update -> login -> app. So uma checagem, best-effort: qualquer falha
    # (sem internet, backend fora do ar) e ignorada e o boot continua normal.
    api_base_url = config_store.get("license.api_base_url", "")
    update_info = check_for_update(api_base_url, APP_VERSION)
    if update_info:
        notes = (update_info.get("notes") or "").strip()
        prompt = f"Nova versao disponivel: {update_info['version']} (atual: {APP_VERSION})."
        if notes:
            prompt += f"\n\n{notes}"
        prompt += "\n\nAtualizar agora?"
        if messagebox.askyesno("Atualizacao disponivel", prompt):
            if apply_update(api_base_url, update_info):
                return 0  # o script auxiliar troca o .exe e reabre o programa
            messagebox.showwarning(
                "EasyF",
                "Nao foi possivel baixar/instalar a atualizacao agora. "
                "Continuando com a versao atual.",
            )

    license_manager = LicenseManager(config_store.section("license"))

    # So uma janela por vez: login primeiro (standalone), app depois. Se o
    # usuario clicar em "Sair da conta" dentro do app, volta pro login em vez
    # de fechar o programa inteiro.
    while True:
        if license_manager.logged_in:
            license_manager.refresh()
            config_store.save()

        if not run_startup_login(license_manager, config_store.save):
            return 1

        app = App(config_store, license_manager)
        app.mainloop()
        if not getattr(app, "logout_requested", False):
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
