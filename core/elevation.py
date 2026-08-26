from __future__ import annotations

import sys


def is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return True


def relaunch_elevated() -> bool:
    try:
        import ctypes

        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        params = " ".join(f'"{arg}"' for arg in args)
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return ret > 32
    except Exception:
        return False
