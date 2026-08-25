"""Overlay visual sobre a tela do jogo: marca a regiao de OCR da mana e
mostra, ao lado, o ultimo valor lido - so pra o usuario confirmar visualmente
que a leitura esta correta, sem precisar abrir o log.

Duas janelas `Toplevel` sem borda, sempre no topo (bloqueiam clique na area
delas - sem clique-atraves por enquanto, pode ser reavaliado depois se for
um problema na pratica). O retangulo que marca a regiao usa uma cor
"magica" como `-transparentcolor` (recurso exclusivo do Tk no Windows) pra
deixar o meio do retangulo invisivel, sobrando so a borda colorida; o
rotulo do valor e uma caixinha solida de HUD, sem esse truque.
"""

from __future__ import annotations

import tkinter as tk

_BORDER_COLOR = "#39ff14"
_BORDER_THICKNESS = 2
_TRANSPARENT_KEY = "#0a0b0d"  # cor improvavel de aparecer de verdade na tela
_LABEL_BG = "#1a1d24"
_LABEL_FG = "#39ff14"


class ManaOverlay:
    """Gerencia as duas janelas de overlay. Nao faz nada até `show()`."""

    def __init__(self, master: tk.Tk):
        self.master = master
        self._marker: tk.Toplevel | None = None
        self._marker_inner: tk.Frame | None = None
        self._label: tk.Toplevel | None = None
        self._label_var: tk.StringVar | None = None
        self._region: tuple[int, int, int, int] | None = None
        self._point: tuple[int, int] | None = None

    # ------------------------------------------------------------- calibracao
    def configure_region(self, region) -> None:
        self._region = tuple(region) if region and len(region) == 4 else None
        if self._marker is not None:
            self._layout_marker()

    def configure_display_point(self, point) -> None:
        self._point = tuple(point) if point and len(point) == 2 else None
        if self._label is not None:
            self._layout_label()

    # ------------------------------------------------------------------ ciclo
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

    # --------------------------------------------------------------- widgets
    def _build_marker(self) -> tk.Toplevel:
        """A janela e MAIOR que a regiao (expande pra fora por
        `_BORDER_THICKNESS`) e a area transparente por dentro tem
        exatamente o tamanho da regiao - a borda visivel fica so na moldura
        de fora, nunca por cima de um pixel que o OCR vai ler. Um marcador
        desenhado por dentro da regiao (como era antes) acaba cobrindo parte
        do numero e corrompe a leitura de vez em quando - foi exatamente
        isso que o teste em jogo real revelou aqui.
        """
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=_BORDER_COLOR)
        try:
            win.attributes("-transparentcolor", _TRANSPARENT_KEY)
        except tk.TclError:
            pass  # so existe no Tk do Windows - sem isso o meio fica opaco
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
        win.update_idletasks()  # calcula o tamanho natural ANTES de posicionar
        self._layout_label(win)
        return win

    def _layout_label(self, win: tk.Toplevel | None = None) -> None:
        win = win or self._label
        if win is None or not self._point:
            return
        x, y = self._point
        win.geometry(f"+{x}+{y}")
