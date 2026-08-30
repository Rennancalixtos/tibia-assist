from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

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


def _looks_like_valid_zip(path: str, expected_size: int) -> bool:
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if expected_size and size != expected_size:
        return False
    if size < 4:
        return False
    try:
        with open(path, "rb") as fp:
            header = fp.read(2)
    except OSError:
        return False
    if header != b"PK":
        return False
    return zipfile.is_zipfile(path)


def apply_update(api_base_url: str, update_info: dict, on_progress=None) -> bool:
    if not getattr(sys, "frozen", False):
        return False

    asset_id = update_info.get("asset_id")
    asset_name = update_info.get("asset_name") or "EasyF-portable.zip"
    if not asset_id:
        return False

    current_exe = sys.executable
    exe_name = os.path.basename(current_exe)
    exe_dir = os.path.dirname(current_exe)
    pid = os.getpid()
    zip_path = os.path.join(exe_dir, f"_update_{pid}_{asset_name}")
    staging_dir = os.path.join(exe_dir, f"_update_staging_{pid}")

    api_base_url = api_base_url.rstrip("/")
    try:
        req = urllib.request.Request(f"{api_base_url}/api/update/download?asset_id={asset_id}")
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, open(zip_path, "wb") as fp:
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
            os.remove(zip_path)
        except OSError:
            pass
        return False

    if not _looks_like_valid_zip(zip_path, expected_size=total):
        try:
            os.remove(zip_path)
        except OSError:
            pass
        return False

    shutil.rmtree(staging_dir, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(staging_dir)
    except (zipfile.BadZipFile, OSError):
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass

    if not os.path.exists(os.path.join(staging_dir, exe_name)):
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False

    script_path = os.path.join(tempfile.gettempdir(), f"tibia_assist_update_{pid}.bat")
    with open(script_path, "w", encoding="utf-8") as fp:
        fp.write(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'robocopy "{staging_dir}" "{exe_dir}" /E /IS /IT /R:3 /W:1 /NFL /NDL /NJH /NJS >nul\r\n'
            "if %errorlevel% GEQ 8 goto :falha\r\n"
            f'rmdir /s /q "{staging_dir}"\r\n'
            f'start "" "{current_exe}"\r\n'
            'del "%~f0"\r\n'
            "exit /b 0\r\n"
            ":falha\r\n"
            f'rmdir /s /q "{staging_dir}"\r\n'
            f'start "" "{current_exe}"\r\n'
            'del "%~f0"\r\n'
        )

    subprocess.Popen(
        ["cmd.exe", "/c", script_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    return True
