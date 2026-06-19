import os
import sys
import json
import base64
import uuid
from pathlib import Path
from typing import Optional

STAT_KEYS = ("Str", "Dex", "Con", "Int", "Wis", "Cha")

HEALTH_SIZE_LOOKUP: dict = {
    "Small":    2,
    "Medium":   4,
    "Large":    6,
    "Giant":    9,
    "Colossal": 13,
}

SCALAR_WEIGHT_LOOKUP: dict = {
    "S": 1.00,
    "A": 0.70,
    "B": 0.45,
    "C": 0.15,
    "F": 0.05,
}

_GAME_CONFIG_DEFAULTS = {
    "hp_base_multiplier": 6.0,
    "enemy_damage_multiplier": 1.0,
    "los_max_distance": 20,
}


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA", str(Path.home()))
        d = Path(appdata) / "Steel2D"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).resolve().parent.parent


def get_saves_dir() -> Path:
    d = get_base_dir() / "saves"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_user_config() -> dict:
    path = get_base_dir() / "user.config"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "uuid" not in data:
                data["uuid"] = str(uuid.uuid4())
            data.setdefault("alias", "")
            data.setdefault("avatar_b64", None)
            data.setdefault("preferred_port", 5000)
            return data
        except Exception:
            pass
    data = {
        "uuid": str(uuid.uuid4()),
        "alias": "",
        "avatar_b64": None,
        "preferred_port": 5000,
    }
    save_user_config(data)
    return data


def save_user_config(data: dict) -> None:
    path = get_base_dir() / "user.config"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_game_config() -> dict:
    path = get_base_dir() / "game_config.json"
    if not path.exists():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_GAME_CONFIG_DEFAULTS, f, indent=2)
        return dict(_GAME_CONFIG_DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = dict(_GAME_CONFIG_DEFAULTS)
        result.update({k: data[k] for k in _GAME_CONFIG_DEFAULTS if k in data})
        return result
    except Exception:
        return dict(_GAME_CONFIG_DEFAULTS)
