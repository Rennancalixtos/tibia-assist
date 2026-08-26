"""Deteccao/elevacao de privilegio de administrador (Windows).

Clique/tecla sintetico (mouse real ou PostMessage em modo background) e
bloqueado pelo UIPI quando o cliente do jogo roda elevado e este processo
nao - por isso o programa tenta relancar a si mesmo como administrador logo
no boot (ver main.py) e exibe o status atual na janela principal (ver
gui/app.py), pra o usuario nunca precisar adivinhar isso pelo Gerenciador de
Tarefas.
"""

from __future__ import annotations

import sys


def is_admin() -> bool:
    """So faz sentido no Windows - qualquer outro SO devolve True (nao
    bloqueia nada por causa disso)."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return True  # checagem falhou: nao bloqueia o boot por causa disso


def relaunch_elevated() -> bool:
    """Repete o processo atual pedindo elevacao via UAC - o proprio dialogo
    do Windows serve de confirmacao, sem precisar de um messagebox nosso
    antes. Devolve True se conseguiu disparar o relancamento (o processo
    atual deve encerrar em seguida sem abrir nenhuma janela)."""
    try:
        import ctypes

        # Rodando do fonte, sys.executable e o python.exe e precisa do
        # caminho do script (argv[0]) pra saber o que rodar; ja empacotado,
        # sys.executable e o proprio EasyF.exe (argv[0] seria redundante).
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        params = " ".join(f'"{arg}"' for arg in args)
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return ret > 32  # ShellExecuteW: valor > 32 = sucesso
    except Exception:
        return False
