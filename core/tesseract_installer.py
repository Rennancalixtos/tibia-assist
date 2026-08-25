"""Instala o Tesseract OCR automaticamente se nao estiver presente.

So usado pelo RuneMaker (leitura de mana via OCR) - o AutoFishing nao
depende disso. Baixa o instalador oficial mais recente do
tesseract-ocr/tesseract no GitHub (repo publico, sem necessidade de
autenticacao ou token) e roda silenciosamente.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

RELEASES_API = "https://api.github.com/repos/tesseract-ocr/tesseract/releases/latest"
DEFAULT_INSTALL_DIR = r"C:\Program Files\Tesseract-OCR"
REQUEST_TIMEOUT = 15


def find_tesseract() -> str | None:
    """Procura o tesseract.exe no PATH ou no local padrao de instalacao."""
    found = shutil.which("tesseract")
    if found:
        return found
    default_exe = os.path.join(DEFAULT_INSTALL_DIR, "tesseract.exe")
    if os.path.exists(default_exe):
        return default_exe
    return None


def _find_windows_installer_url() -> str | None:
    """Acha o asset do instalador Windows (64-bit) no ultimo release."""
    try:
        req = urllib.request.Request(
            RELEASES_API, headers={"Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            release = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None

    for asset in release.get("assets", []):
        name = (asset.get("name") or "").lower()
        if name.startswith("tesseract-ocr-w64-setup") and name.endswith(".exe"):
            return asset.get("browser_download_url")
    return None


def install_tesseract(on_progress=None) -> tuple[bool, str]:
    """Baixa e instala o Tesseract silenciosamente (instalador NSIS, `/S`).

    `on_progress`, se informado, e chamado com uma string descrevendo a
    etapa atual (pensado pra atualizar um label da GUI). Devolve
    (sucesso, mensagem).
    """

    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    url = _find_windows_installer_url()
    if not url:
        return False, "Nao foi possivel encontrar o instalador do Tesseract no GitHub."

    installer_path = os.path.join(tempfile.gettempdir(), "tesseract-ocr-setup.exe")
    report("Baixando instalador do Tesseract...")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp, open(installer_path, "wb") as fp:
            shutil.copyfileobj(resp, fp)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"Falha ao baixar o instalador: {exc}"

    report("Instalando (silencioso, pode levar um minuto)...")
    try:
        result = subprocess.run([installer_path, "/S"], timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Falha ao executar o instalador: {exc}"
    finally:
        try:
            os.remove(installer_path)
        except OSError:
            pass

    if result.returncode != 0:
        return False, f"Instalador terminou com codigo de saida {result.returncode}."

    if find_tesseract() is None:
        return False, "Instalacao concluida, mas o tesseract.exe nao foi encontrado depois."

    return True, "Tesseract instalado com sucesso."
