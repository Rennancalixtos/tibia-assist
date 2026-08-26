from __future__ import annotations

import copy
import json
import os
import re

from core.config import BASE_DIR, DEFAULTS, _deep_merge

PROFILES_DIR = os.path.join(BASE_DIR, "profiles")

EXCLUDED_SECTIONS = {"license"}

_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_profile_name(name: str) -> str:
    name = (name or "").strip()
    name = _INVALID_CHARS_RE.sub("", name)
    return name.strip(" .")


def profile_path(name: str) -> str:
    return os.path.join(PROFILES_DIR, f"{name}.json")


def list_profiles() -> list[str]:
    if not os.path.isdir(PROFILES_DIR):
        return []
    names = [fn[:-5] for fn in os.listdir(PROFILES_DIR) if fn.endswith(".json")]
    return sorted(names, key=str.lower)


def save_profile(name: str, config_data: dict) -> str:
    name = sanitize_profile_name(name)
    if not name:
        raise ValueError("Nome de perfil invalido.")
    os.makedirs(PROFILES_DIR, exist_ok=True)
    snapshot = {k: v for k, v in copy.deepcopy(config_data).items() if k not in EXCLUDED_SECTIONS}
    with open(profile_path(name), "w", encoding="utf-8") as fp:
        json.dump(snapshot, fp, indent=2, ensure_ascii=False)
    return name


def load_profile(name: str) -> dict:
    path = profile_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Perfil {name!r} nao encontrado.")
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def delete_profile(name: str) -> None:
    path = profile_path(name)
    if os.path.exists(path):
        os.remove(path)


def merge_into_config(current_data: dict, profile_data: dict) -> dict:
    merged = _deep_merge(DEFAULTS, profile_data)
    if "license" in current_data:
        merged["license"] = copy.deepcopy(current_data["license"])
    return merged
