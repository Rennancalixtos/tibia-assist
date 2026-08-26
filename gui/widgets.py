from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)

        canvas = tk.Canvas(self, highlightthickness=0)
        vscroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.body = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=self.body, anchor="nw")

        def _sync_scrollregion(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_body_width(event) -> None:
            canvas.itemconfig(window_id, width=event.width)

        self.body.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_body_width)

        def _on_mousewheel(event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))


class LogPanel(ttk.LabelFrame):
    def __init__(self, master, title: str = "Log", height: int = 10, max_lines: int = 500):
        super().__init__(master, text=title)
        self.max_lines = max_lines

        self.text = tk.Text(self, height=height, wrap="none", state="disabled")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)

        self.text.grid(row=0, column=0, sticky="nsew", padx=(4, 0), pady=4)
        scroll.grid(row=0, column=1, sticky="ns", pady=4, padx=(0, 4))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def append(self, message: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", message + "\n")
        total = int(self.text.index("end-1c").split(".")[0])
        if total > self.max_lines:
            self.text.delete("1.0", f"{total - self.max_lines}.0")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class HotkeyButton(ttk.Button):
    _IGNORED_KEYSYMS = {
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
        "Caps_Lock", "Num_Lock", "Scroll_Lock", "Super_L", "Super_R",
        "Meta_L", "Meta_R",
    }
    _KEYSYM_MAP = {
        "Return": "enter",
        "Escape": "esc",
        "BackSpace": "backspace",
        "Delete": "delete",
        "Tab": "tab",
        "Pause": "pause",
        "Up": "up",
        "Down": "down",
        "Left": "left",
        "Right": "right",
        "Prior": "pageup",
        "Next": "pagedown",
        "Home": "home",
        "End": "end",
        "space": "space",
    }

    def __init__(self, parent, variable: tk.StringVar, width: int = 10, on_change=None):
        super().__init__(parent, width=width, command=self._start_capture)
        self.variable = variable
        self.on_change = on_change
        self._refresh_label()

    def _refresh_label(self) -> None:
        self.configure(text=(self.variable.get() or "-").upper())

    def _start_capture(self) -> None:
        self.configure(text="Pressione uma tecla...")
        self.focus_set()
        self.bind("<KeyPress>", self._on_key)
        self.bind("<FocusOut>", self._cancel_capture)

    def _cancel_capture(self, _event=None) -> None:
        self.unbind("<KeyPress>")
        self.unbind("<FocusOut>")
        self._refresh_label()

    def _on_key(self, event) -> None:
        if event.keysym in self._IGNORED_KEYSYMS:
            return
        name = self._normalize(event.keysym)
        if not name:
            return
        self.unbind("<KeyPress>")
        self.unbind("<FocusOut>")
        self.variable.set(name)
        self._refresh_label()
        if self.on_change:
            self.on_change(name)

    @classmethod
    def _normalize(cls, keysym: str) -> str | None:
        if len(keysym) == 1:
            return keysym.lower()
        if keysym in cls._KEYSYM_MAP:
            return cls._KEYSYM_MAP[keysym]
        if len(keysym) in (2, 3) and keysym[0] in ("F", "f") and keysym[1:].isdigit():
            return keysym.lower()
        return None


def add_hotkey_field(parent, row: int, label: str, variable, width: int = 10, hint: str = "", on_change=None):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=3)
    button = HotkeyButton(parent, variable, width=width, on_change=on_change)
    button.grid(row=row, column=1, sticky="w", padx=4, pady=3)
    if hint:
        ttk.Label(parent, text=hint, foreground="#666").grid(row=row, column=2, sticky="w", padx=4)
    return button


def add_field(parent, row: int, label: str, variable, width: int = 12, hint: str = ""):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=3)
    entry = ttk.Entry(parent, textvariable=variable, width=width)
    entry.grid(row=row, column=1, sticky="w", padx=4, pady=3)
    if hint:
        ttk.Label(parent, text=hint, foreground="#666").grid(
            row=row, column=2, sticky="w", padx=4
        )
    return entry


def region_text(region) -> str:
    if not region:
        return "nao configurado"
    if len(region) == 4:
        return f"x={region[0]}  y={region[1]}  {region[2]}x{region[3]}"
    return f"x={region[0]}  y={region[1]}"


def parse_float(value: str, fallback: float) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return fallback


def parse_int(value: str, fallback: int) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return fallback
