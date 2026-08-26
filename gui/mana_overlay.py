from __future__ import annotations

import tkinter as tk

_BORDER_COLOR = "#39ff14"
_BORDER_THICKNESS = 2
_TRANSPARENT_KEY = "#0a0b0d"
_LABEL_BG = "#1a1d24"
_LABEL_FG = "#39ff14"


class ManaOverlay:
    def __init__(self, master: tk.Tk):
        self.master = master
        self._marker: tk.Toplevel | None = None
        self._marker_inner: tk.Frame | None = None
        self._label: tk.Toplevel | None = None
        self._label_var: tk.StringVar | None = None
        self._region: tuple[int, int, int, int] | None = None
        self._point: tuple[int, int] | None = None

    def configure_region(self, region) -> None:
        self._region = tuple(region) if region and len(region) == 4 else None
        if self._marker is not None:
            self._layout_marker()

    def configure_display_point(self, point) -> None:
        self._point = tuple(point) if point and len(point) == 2 else None
        if self._label is not None:
            self._layout_label()

    def show(self) -> None:
        if self._region and self._marker is None:
            self._marker = self._build_marker()
        if self._point and self._label is None:
            self._label = self._build_label()
        self.update_value(None)

    def hide(self) -> None:
        for attr in ("_marker", "_label"):
            win = getattr(self, attr)
            if win is not None:
                try:
                    win.destroy()
                except Exception:
                    pass
                setattr(self, attr, None)
        self._marker_inner = None
        self._label_var = None

    def update_value(self, value: int | None) -> None:
        if self._label_var is not None:
            self._label_var.set(f"Mana: {value}" if value is not None else "Mana: ?")

    def _build_marker(self) -> tk.Toplevel:
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=_BORDER_COLOR)
        try:
            win.attributes("-transparentcolor", _TRANSPARENT_KEY)
        except tk.TclError:
            pass
        self._marker_inner = tk.Frame(win, bg=_TRANSPARENT_KEY)
        self._marker_inner.place(x=_BORDER_THICKNESS, y=_BORDER_THICKNESS)
        win.update_idletasks()
        self._layout_marker(win)
        return win

    def _layout_marker(self, win: tk.Toplevel | None = None) -> None:
        win = win or self._marker
        if win is None or not self._region:
            return
        x, y, w, h = self._region
        t = _BORDER_THICKNESS
        win.geometry(f"{w + 2 * t}x{h + 2 * t}+{x - t}+{y - t}")
        if self._marker_inner is not None:
            self._marker_inner.place(x=t, y=t, width=w, height=h)

    def _build_label(self) -> tk.Toplevel:
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.85)
        win.configure(bg=_LABEL_BG)
        self._label_var = tk.StringVar(value="Mana: ?")
        tk.Label(
            win, textvariable=self._label_var, bg=_LABEL_BG, fg=_LABEL_FG, font=("Segoe UI", 10, "bold"), padx=6, pady=3
        ).pack()
        win.update_idletasks()
        self._layout_label(win)
        return win

    def _layout_label(self, win: tk.Toplevel | None = None) -> None:
        win = win or self._label
        if win is None or not self._point:
            return
        x, y = self._point
        win.geometry(f"+{x}+{y}")
