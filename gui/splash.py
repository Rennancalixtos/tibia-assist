"""Splash de atualizacao - mostrada ANTES do login, no boot do programa.

Checa e (se houver uma versao nova) baixa/aplica a atualizacao sozinha, sem
perguntar - so avisa o progresso ("Verificando...", "Baixando X%",
"Concluido"). Roda numa thread separada pra nao travar a janela, reportando
progresso por fila consumida pelo `after()` da propria splash - mesmo padrao
de `App._pump_events`.

Janela standalone (`tk.Tk`), nunca `Toplevel` de outra janela: no Windows, um
Toplevel "transient" de uma raiz escondida (`withdraw`) por vezes nao e
exibido pelo gerenciador de janelas - bug real, encontrado e corrigido nesta
mesma sessao pro login (ver gui/license_dialog.py). Splash -> login -> app
sao 3 janelas `tk.Tk()` sequenciais, nunca duas ao mesmo tempo.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from core.updater import apply_update, check_for_update

_BG = "#1a1d24"
_FG = "#e7e7ea"
_FG_DIM = "#8a8f9c"
_FG_ERROR = "#ff6b6b"


class SplashScreen(tk.Tk):
    def __init__(self, api_base_url: str, current_version: str):
        super().__init__()
        self.api_base_url = api_base_url
        self.current_version = current_version
        # "checking" | "no_update" | "updated" | "error" | "skip"
        self.result = "checking"
        self._events: "queue.Queue[tuple]" = queue.Queue()

        self.title("EasyF")
        self.overrideredirect(True)
        self.resizable(False, False)
        self.configure(bg=_BG)
        width, height = 380, 150
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{width}x{height}+{(sw - width) // 2}+{(sh - height) // 2}")

        body = tk.Frame(self, bg=_BG, padx=20, pady=18)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="EasyF", fg=_FG, bg=_BG, font=("Segoe UI", 14, "bold")).pack(anchor="w")

        self.var_status = tk.StringVar(value="Verificando atualizacoes...")
        tk.Label(body, textvariable=self.var_status, fg=_FG_DIM, bg=_BG, font=("Segoe UI", 9)).pack(
            anchor="w", pady=(10, 10)
        )

        self.progress = ttk.Progressbar(body, mode="indeterminate", length=320)
        self.progress.pack(fill="x")
        self.progress.start(12)

        self.error_frame = tk.Frame(body, bg=_BG)

        self.after(50, self._start_check)

    # --------------------------------------------------------------- thread
    def _start_check(self) -> None:
        threading.Thread(target=self._worker_check, daemon=True).start()
        self.after(100, self._pump)

    def _worker_check(self) -> None:
        try:
            update_info = check_for_update(self.api_base_url, self.current_version)
        except Exception as exc:  # nunca deve travar o boot por causa disso
            self._events.put(("error", f"Falha ao checar atualizacao: {exc}"))
            return

        if not update_info:
            self._events.put(("done", None))
            return

        self._events.put(("downloading", update_info))

        def report(downloaded: int, total: int) -> None:
            pct = int(downloaded * 100 / total) if total else None
            self._events.put(("progress", pct))

        try:
            applied = apply_update(self.api_base_url, update_info, on_progress=report)
        except Exception as exc:
            self._events.put(("error", f"Falha ao baixar/instalar a atualizacao: {exc}"))
            return

        self._events.put(("updated", None) if applied else ("done", None))

    # ------------------------------------------------------------------ pump
    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "downloading":
                    self.var_status.set(f"Baixando atualizacao {payload.get('version', '')}...")
                elif kind == "progress":
                    if payload is None:
                        self.var_status.set("Baixando atualizacao...")
                    else:
                        self.var_status.set(f"Baixando atualizacao... {payload}%")
                        if str(self.progress["mode"]) != "determinate":
                            self.progress.stop()
                            self.progress.configure(mode="determinate", maximum=100)
                        self.progress["value"] = payload
                elif kind == "updated":
                    self.var_status.set("Atualizacao concluida - reabrindo...")
                    self.result = "updated"
                    self.after(300, self.destroy)
                    return
                elif kind == "done":
                    self.result = "no_update"
                    self.destroy()
                    return
                elif kind == "error":
                    self.result = "error"
                    self._show_error(payload)
                    return
        except queue.Empty:
            pass
        if self.result == "checking":
            self.after(100, self._pump)

    # ------------------------------------------------------------------ erro
    def _show_error(self, message: str) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.var_status.set(message)

        for child in self.error_frame.winfo_children():
            child.destroy()

        tk.Button(self.error_frame, text="Tentar novamente", command=self._retry).pack(side="left")
        tk.Button(self.error_frame, text="Abrir mesmo assim", command=self._skip).pack(side="left", padx=8)
        self.error_frame.pack(fill="x", pady=(6, 0))

    def _retry(self) -> None:
        self.error_frame.pack_forget()
        self.progress.configure(mode="indeterminate")
        self.progress.pack(fill="x")
        self.progress.start(12)
        self.var_status.set("Verificando atualizacoes...")
        self.result = "checking"
        self._start_check()

    def _skip(self) -> None:
        self.result = "skip"
        self.destroy()


def run_update_check(api_base_url: str, current_version: str) -> str:
    """Mostra a splash e roda a checagem/atualizacao. Devolve:

    - "updated": o .exe foi trocado e o script auxiliar vai reabrir o
      programa - quem chamar isso deve encerrar o processo atual agora.
    - "no_update" / "skip": nada a fazer, segue o boot normal (login/app).
    """
    splash = SplashScreen(api_base_url, current_version)
    splash.mainloop()
    return splash.result
