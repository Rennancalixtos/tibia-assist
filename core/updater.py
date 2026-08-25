"""Auto-update: consulta o backend por uma versao mais nova e, se aceito,
baixa e troca o .exe sozinho.

O repositorio no GitHub e privado, entao o app nunca fala com a API do
GitHub diretamente (exigiria embutir um token no binario, legivel por
qualquer um). Em vez disso, o backend (que ja existe na Vercel para a
licenca) expoe `/api/update/latest` e `/api/update/download`, que fazem essa
consulta usando um token guardado so no servidor.

So funciona quando empacotado com PyInstaller (`sys.frozen`) - rodando a
partir do codigo-fonte, so informa que ha uma versao nova, sem tentar
substituir nada (nao ha .exe pra trocar).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

REQUEST_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 180


def _parse_version(value: str) -> tuple[int, ...]:
    value = (value or "").strip().lstrip("vV")
    parts = []
    for chunk in value.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def check_for_update(api_base_url: str, current_version: str) -> dict | None:
    """Consulta {api_base_url}/api/update/latest.

    Devolve None se nao houver versao mais nova, se a checagem falhar, ou se
    api_base_url nao estiver configurado - nunca bloqueia o boot do app por
    causa disso.
    """
    api_base_url = (api_base_url or "").rstrip("/")
    if not api_base_url:
        return None
    try:
        req = urllib.request.Request(f"{api_base_url}/api/update/latest", method="GET")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None

    remote_version = info.get("version") or ""
    if not remote_version or not info.get("asset_id"):
        return None
    if _parse_version(remote_version) <= _parse_version(current_version):
        return None
    return info


def apply_update(api_base_url: str, update_info: dict, on_progress=None) -> bool:
    """Baixa o novo .exe e reinicia o programa com ele no lugar do atual.

    So funciona empacotado (PyInstaller/`sys.frozen`); rodando do
    codigo-fonte devolve False sem fazer nada, ja que nao ha .exe pra
    substituir. Quem chamar isso e receber True deve encerrar o processo
    atual imediatamente (o .exe em uso precisa ser liberado para a troca).

    `on_progress(downloaded_bytes, total_bytes)`, se informado, e chamado a
    cada pedaco baixado (`total_bytes` pode ser 0 se o servidor nao mandar
    Content-Length).
    """
    if not getattr(sys, "frozen", False):
        return False

    asset_id = update_info.get("asset_id")
    asset_name = update_info.get("asset_name") or "EasyF.exe"
    if not asset_id:
        return False

    current_exe = sys.executable
    exe_dir = os.path.dirname(current_exe)
    new_exe = os.path.join(exe_dir, f"_update_{asset_name}")

    api_base_url = api_base_url.rstrip("/")
    try:
        req = urllib.request.Request(f"{api_base_url}/api/update/download?asset_id={asset_id}")
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, open(new_exe, "wb") as fp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fp.write(chunk)
                downloaded += len(chunk)
                if on_progress:
                    on_progress(downloaded, total)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        try:
            os.remove(new_exe)
        except OSError:
            pass
        return False

    # Nao da pra sobrescrever o .exe em execucao - um script auxiliar espera
    # este processo terminar, faz a troca e reabre o programa.
    script_path = os.path.join(tempfile.gettempdir(), "tibia_assist_update.bat")
    with open(script_path, "w", encoding="utf-8") as fp:
        fp.write(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'del /f /q "{current_exe}"\r\n'
            f'move /y "{new_exe}" "{current_exe}"\r\n'
            f'start "" "{current_exe}"\r\n'
            'del "%~f0"\r\n'
        )

    subprocess.Popen(
        ["cmd.exe", "/c", script_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    return True
