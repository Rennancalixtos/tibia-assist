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

    from gui.app import App

    app = App()
    if not getattr(app, "license_ok", True):
        app.destroy()
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
