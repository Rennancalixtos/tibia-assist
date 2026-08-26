from __future__ import annotations

import tkinter as tk

from core.screen_capture import ScreenCapture


def _virtual_geometry() -> tuple[int, int, int, int]:
    try:
        with ScreenCapture() as cap:
            return cap.virtual_screen_size()
    except Exception:
        root = tk._default_root
        if root is not None:
            return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
        return 0, 0, 1920, 1080


class _Overlay(tk.Toplevel):
    def __init__(self, master: tk.Misc, hint: str):
        super().__init__(master)
        left, top, width, height = _virtual_geometry()
        self._origin = (left, top)

        self.overrideredirect(True)
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.30)
        except tk.TclError:
            pass
        self.configure(bg="black", cursor="crosshair")

        self.canvas = tk.Canvas(
            self, bg="black", highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            width // 2,
            40,
            text=hint,
            fill="white",
            font=("Segoe UI", 16, "bold"),
        )

        self.result = None
        self.bind("<Escape>", lambda _e: self._cancel())
        self.focus_force()
        self.grab_set()

    def to_absolute(self, x: int, y: int) -> tuple[int, int]:
        return int(x) + self._origin[0], int(y) + self._origin[1]

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


def select_region(
    master: tk.Misc, hint: str = "Arraste para selecionar a regiao  -  ESC cancela"
) -> list[int] | None:
    overlay = _Overlay(master, hint)
    state = {"x": 0, "y": 0, "rect": None}

    def on_press(event):
        state["x"], state["y"] = event.x, event.y
        if state["rect"] is not None:
            overlay.canvas.delete(state["rect"])
        state["rect"] = overlay.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#00ff88", width=2
        )

    def on_drag(event):
        if state["rect"] is not None:
            overlay.canvas.coords(state["rect"], state["x"], state["y"], event.x, event.y)

    def on_release(event):
        x1, y1 = min(state["x"], event.x), min(state["y"], event.y)
        x2, y2 = max(state["x"], event.x), max(state["y"], event.y)
        w, h = x2 - x1, y2 - y1
        if w < 5 or h < 5:
            overlay.result = None
        else:
            ax, ay = overlay.to_absolute(x1, y1)
            overlay.result = [ax, ay, w, h]
        overlay.destroy()

    overlay.canvas.bind("<ButtonPress-1>", on_press)
    overlay.canvas.bind("<B1-Motion>", on_drag)
    overlay.canvas.bind("<ButtonRelease-1>", on_release)
    master.wait_window(overlay)
    return overlay.result


def select_point(master: tk.Misc, hint: str = "Clique no ponto desejado  -  ESC cancela") -> tuple[int, int] | None:
    overlay = _Overlay(master, hint)

    def on_click(event):
        overlay.result = overlay.to_absolute(event.x, event.y)
        overlay.destroy()

    overlay.canvas.bind("<ButtonPress-1>", on_click)
    master.wait_window(overlay)
    return overlay.result
