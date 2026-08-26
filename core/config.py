from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(appdata, "EasyF")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _base_dir()
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

DEFAULTS: dict[str, Any] = {
    "license": {
        "api_base_url": "https://tibia-assist.vercel.app",
        "grace_period_hours": 12,
        "check_interval_minutes": 30,
        "access_token": "",
        "refresh_token": "",
        "access_token_expires_at": None,
        "session_token": "",
        "status": "unknown",
        "expires_at": None,
        "checked_at": 0,
        "cache_sig": "",
    },
    "hotkeys": {
        "pause": "pause",
        "stop": "f7",
        "enabled": True,
    },
    "fishing": {
        "rod_slot": None,
        "region": None,
        "detection_mode": "hsv",
        "hsv_lower": [90, 60, 40],
        "hsv_upper": [130, 255, 255],
        "hsv_reference_brightness": None,
        "auto_recalibrate_enabled": False,
        "auto_recalibrate_interval_minutes": 15,
        "ema_alpha": 0.15,
        "min_area": 200,
        "tile_size": 32,
        "min_tile_coverage": 0.35,
        "template_file": "water_template.png",
        "template_threshold": 0.80,
        "mouse_button": "left",
        "delay_min": 1.8,
        "delay_max": 3.2,
        "click_jitter": 2,
        "randomize_target": True,
        "max_casts": 0,
        "break_enabled": True,
        "break_interval_min": 30,
        "break_interval_max": 300,
        "break_duration_min": 10,
        "break_duration_max": 120,
    },
    "background_mode": {
        "enabled": False,
        "window_title": "",
    },
    "runemaker": {
        "spell_hotkey": "f2",
        "blank_slot": None,
        "amount": 0,
        "mana_region": None,
        "mana_display_point": None,
        "min_mana": 300,
        "check_mana": True,
        "delay_min": 1.5,
        "delay_max": 2.5,
        "click_jitter": 2,
        "mode": "craft",
        "no_hand_mode": False,
        "hand_slot": None,
        "output_slot": None,
        "blank_slot_region": None,
        "hand_slot_region": None,
        "output_slot_region": None,
        "blank_empty_template": "",
        "hand_empty_template": "",
        "output_empty_template": "",
        "empty_match_threshold": 0.90,
    },
    "target": {
        "battle_list_region": None,
        "battle_empty_template": "",
        "empty_match_threshold": 0.85,
        "attack_color_rgb": [254, 0, 0],
        "attack_color_tolerance": 6,
        "attack_color_min_pixels": 3,
        "attack_key": "space",
        "attack_check_delay": 0.5,
        "idle_delay_min": 2.0,
        "idle_delay_max": 4.0,
        "engaged_delay_min": 1.0,
        "engaged_delay_max": 2.0,
    },
    "training": {
        "battle_list_region": None,
        "training_battle_empty_template": "",
        "empty_match_threshold": 0.85,
        "attack_color_rgb": [254, 0, 0],
        "attack_color_tolerance": 6,
        "attack_color_min_pixels": 3,
        "attack_key": "space",
        "attack_check_delay": 0.5,
        "idle_delay_min": 2.0,
        "idle_delay_max": 4.0,
        "engaged_delay_min": 1.0,
        "engaged_delay_max": 2.0,
        "creature_name": "",
        "name_match_threshold": 0.80,
        "missing_retries": 5,
        "missing_retry_interval": 2.0,
        "cast_spell_enabled": False,
        "spell_hotkey": "",
        "check_mana": True,
        "mana_region": None,
        "min_mana": 300,
        "spell_delay_min": 1.5,
        "spell_delay_max": 2.5,
        "anti_afk_enabled": False,
        "anti_afk_interval_minutes": 10,
        "anti_afk_key_a": "up",
        "anti_afk_key_b": "down",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fp:
                stored = json.load(fp)
            self.data = _deep_merge(DEFAULTS, stored)
        except (json.JSONDecodeError, OSError):
            try:
                os.replace(self.path, self.path + ".bak")
            except OSError:
                pass
            self.data = copy.deepcopy(DEFAULTS)
            self.save()

    def save(self) -> None:
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fp:
            json.dump(self.data, fp, indent=2, ensure_ascii=False)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def section(self, name: str) -> dict[str, Any]:
        return self.data.setdefault(name, {})

    def asset_path(self, filename: str) -> str:
        return os.path.join(ASSETS_DIR, filename)
