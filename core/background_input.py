"""Clique/tecla via PostMessage direto na janela do jogo (modo background).

Diferente do InputSimulator padrao (que move o cursor real do Windows via
SendInput), essas funcoes mandam mensagens diretamente pra fila da janela
alvo (`win32gui.PostMessage`) - o cursor do usuario nunca se move, ele pode
usar o mouse em outra janela enquanto a automacao roda.

Limitacao importante (documentar tambem na UI, nao so aqui): isso so
funciona em clients que escutam a fila de mensagens do Windows pra
mouse/teclado (apps Win32/Qt/SDL classicos). Clients que leem input via raw
input/DirectInput, ou que verificam a posicao real do cursor
(`GetCursorPos`) como protecao anti-macro, aceitam o PostMessage sem erro
nenhum da API mas simplesmente nao reagem - por isso o botao de teste na
GUI e essencial: e a unica forma de saber se vai funcionar pro client
especifico do usuario.

Nenhuma funcao aqui decide fallback - so executam ou levantam excecao. A
decisao de cair pro mouse real e do InputSimulator (core/input_simulator.py).
"""

from __future__ import annotations

import random
import time

import win32api
import win32con
import win32gui

_VK_NAME_MAP = {
    "space": win32con.VK_SPACE,
    "enter": win32con.VK_RETURN,
    "return": win32con.VK_RETURN,
    "esc": win32con.VK_ESCAPE,
    "escape": win32con.VK_ESCAPE,
    "tab": win32con.VK_TAB,
    "backspace": win32con.VK_BACK,
    "delete": win32con.VK_DELETE,
    "up": win32con.VK_UP,
    "down": win32con.VK_DOWN,
    "left": win32con.VK_LEFT,
    "right": win32con.VK_RIGHT,
}
for _i in range(1, 25):
    _vk = getattr(win32con, f"VK_F{_i}", None)
    if _vk is not None:
        _VK_NAME_MAP[f"f{_i}"] = _vk


def key_to_vk(key: str) -> int | None:
    """Mapeia um nome de tecla (mesma nomenclatura do InputSimulator.press_key
    - "f2", "space", letras/numeros) pro codigo de tecla virtual do Windows."""
    key = (key or "").strip().lower()
    if not key:
        return None
    if key in _VK_NAME_MAP:
        return _VK_NAME_MAP[key]
    if len(key) == 1:
        return ord(key.upper())
    return None


def find_window_by_title(substring: str) -> int | None:
    """Acha o primeiro hwnd visivel cujo titulo contem `substring` (case
    insensitive - titulos de jogo as vezes tem uma parte dinamica, tipo o
    nome do personagem, entao nao exigimos igualdade exata)."""
    substring = (substring or "").strip().lower()
    if not substring:
        return None

    found: list[int] = []

    def _callback(hwnd: int, _extra) -> bool:
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if substring in title.lower():
                found.append(hwnd)
        return True  # continua enumerando

    win32gui.EnumWindows(_callback, None)
    return found[0] if found else None


def window_title_at_point(x: int, y: int) -> tuple[int, str] | None:
    """Acha a janela de TOPO (nao um controle filho) na coordenada de tela
    (x, y) - usado pra calibrar clicando na janela do jogo."""
    try:
        child_hwnd = win32gui.WindowFromPoint((int(x), int(y)))
        if not child_hwnd:
            return None
        root_hwnd = win32gui.GetAncestor(child_hwnd, win32con.GA_ROOT)
        hwnd = root_hwnd or child_hwnd
        title = win32gui.GetWindowText(hwnd)
        return hwnd, title
    except Exception:
        return None


def post_click(hwnd: int, x: int, y: int, button: str = "left") -> None:
    """Converte (x, y) absoluto de tela pra coordenada de cliente da janela
    e manda mouseMove+mouseDown+mouseUp via PostMessage. Levanta a excecao
    original se o PostMessage falhar - quem chama decide o fallback.

    O WM_MOUSEMOVE antes do down NAO e cosmetico: muitos clients (incluindo
    os baseados em SDL/OpenGL testados neste projeto) guardam "qual widget
    esta sob o mouse" a partir das mensagens de MOUSEMOVE que recebem, e
    processam o botao usando esse estado - nao a coordenada do proprio
    evento de clique. Sem mandar o MOUSEMOVE primeiro, o client usa a ultima
    posicao real conhecida do mouse (a do cursor de verdade do usuario) pra
    decidir o alvo do clique, nao (x, y) - foi exatamente esse bug que o
    teste manual em jogo real revelou aqui.
    """
    cx, cy = win32gui.ScreenToClient(hwnd, (int(x), int(y)))
    lparam = win32api.MAKELONG(cx, cy)

    if button == "right":
        down_msg, up_msg, mk = win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON
    else:
        down_msg, up_msg, mk = win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON

    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
    time.sleep(random.uniform(0.03, 0.08))
    win32gui.PostMessage(hwnd, down_msg, mk, lparam)
    time.sleep(random.uniform(0.05, 0.15))
    win32gui.PostMessage(hwnd, up_msg, 0, lparam)


def post_drag(hwnd: int, from_x: int, from_y: int, to_x: int, to_y: int, steps: int = 4) -> None:
    """Arrasto via PostMessage: mouseDown na origem, alguns WM_MOUSEMOVE
    intermediarios (delay pequeno entre eles), mouseUp no destino. Isso e so
    pra o client registrar o arrasto - nao tenta imitar a curva/easing
    completa do movimento real de mouse (ver InputSimulator.move_to)."""
    fx, fy = win32gui.ScreenToClient(hwnd, (int(from_x), int(from_y)))
    tx, ty = win32gui.ScreenToClient(hwnd, (int(to_x), int(to_y)))

    # Move ate a origem ANTES do mouseDown - mesmo motivo do post_click: o
    # client precisa achar que o mouse ja esta em cima do item antes de
    # "pega-lo", senao usa a ultima posicao real conhecida do cursor.
    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, win32api.MAKELONG(fx, fy))
    time.sleep(random.uniform(0.03, 0.08))
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, win32api.MAKELONG(fx, fy))
    time.sleep(random.uniform(0.05, 0.15))

    steps = max(1, steps)
    for i in range(1, steps + 1):
        t = i / steps
        ix = int(fx + (tx - fx) * t)
        iy = int(fy + (ty - fy) * t)
        win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, win32api.MAKELONG(ix, iy))
        time.sleep(random.uniform(0.02, 0.06))

    time.sleep(random.uniform(0.05, 0.15))
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, win32api.MAKELONG(tx, ty))


def post_key(hwnd: int, key: str) -> None:
    """Manda WM_KEYDOWN + WM_KEYUP pra tecla `key`. lParam=0: alguns clients
    exigem os bits de scan-code/repeat-count pra reconhecer a tecla, o que
    nao esta implementado aqui - e uma das limitacoes que o botao de teste
    na GUI existe pra expor."""
    vk = key_to_vk(key)
    if vk is None:
        raise ValueError(f"Tecla desconhecida: {key!r}")
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
    time.sleep(random.uniform(0.03, 0.09))
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)
