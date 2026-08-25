"""Widgets auxiliares reutilizados pelas duas abas da GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class LogPanel(ttk.LabelFrame):
    """Caixa de texto somente leitura com o historico de acoes."""

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
        # Descarta linhas antigas para a memoria nao crescer indefinidamente.
        total = int(self.text.index("end-1c").split(".")[0])
        if total > self.max_lines:
            self.text.delete("1.0", f"{total - self.max_lines}.0")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


def add_field(parent, row: int, label: str, variable, width: int = 12, hint: str = ""):
    """Adiciona um par label/entry numa grade e devolve o widget de entrada."""
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=3)
    entry = ttk.Entry(parent, textvariable=variable, width=width)
    entry.grid(row=row, column=1, sticky="w", padx=4, pady=3)
    if hint:
        ttk.Label(parent, text=hint, foreground="#666").grid(
            row=row, column=2, sticky="w", padx=4
        )
    return entry


def region_text(region) -> str:
    """Formata uma regiao/ponto para exibicao."""
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
