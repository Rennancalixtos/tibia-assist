from __future__ import annotations

import tkinter as tk

_BG = "#000000"
_FG = "#39ff14"
_ALPHA = 0.55
_WIDTH = 460
_HEIGHT = 170
_MARGIN_X = 10
_MARGIN_Y = 48
_MAX_LINES = 200


class LogOverlay:
    def __init__(self, master: tk.Tk):
        self.master = master
        self._win: tk.Toplevel | None = None
        self._text: tk.Text | None = None

    def show(self) -> None:
        if self._win is not None:
            return
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", _ALPHA)
        except tk.TclError:
            pass
        win.configure(bg=_BG)
        text = tk.Text(
            win, bg=_BG, fg=_FG, font=("Consolas", 9), wrap="word",
            bd=0, highlightthickness=0, state="disabled",
        )
        text.pack(fill="both", expand=True, padx=6, pady=6)
        self._win = win
        self._text = text
        self._layout()

    def hide(self) -> None:
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
        self._win = None
        self._text = None

    def _layout(self) -> None:
        if self._win is None:
            return
        sw = self.master.winfo_screenwidth()
        sh = self.master.winfo_screenheight()
        x = _MARGIN_X
        y = sh - _HEIGHT - _MARGIN_Y
        self._win.geometry(f"{_WIDTH}x{_HEIGHT}+{max(0, x)}+{max(0, y)}")

    def append(self, message: str) -> None:
        if self._text is None:
            return
        self._text.configure(state="normal")
        self._text.insert("end", message + "\n")
        total = int(self._text.index("end-1c").split(".")[0])
        if total > _MAX_LINES:
            self._text.delete("1.0", f"{total - _MAX_LINES}.0")
        self._text.see("end")
        self._text.configure(state="disabled")
