import os
import sys
import json
import base64
import uuid
from pathlib import Path
from typing import Optional, Dict

STAT_KEYS = ("Str", "Dex", "Con", "Int", "Wis", "Cha")

HEALTH_SIZE_LOOKUP: dict = {
    "Small":    1,
    "Medium":   2,
    "Large":    3,
    "Giant":    6,
    "Colossal": 10,
}

SCALAR_WEIGHT_LOOKUP: dict = {
    "S": 1.00,
    "A": 0.70,
    "B": 0.45,
    "C": 0.15,
    "F": 0.05,
}

_GAME_CONFIG_DEFAULTS = {
    "hp_base_multiplier": 4.0,
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


def get_prefabs_dir() -> Path:
    d = get_base_dir() / "prefabs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def merge_host_prefabs(host_uuid: str, new_objects: list) -> None:
    """
    Merge a host's prefab objects into <host_uuid>-Prefabs.json.

    Matching rule: an existing entry and a new entry are considered the same
    object when they share both `type` AND `Name`.

    Behaviour:
    - Matching pair found → existing entry is overwritten with the new data.
    - New entry has no match → appended to the file.
    - Existing entry has no match in the new data → kept unchanged (never deleted).
    """
    import json
    from datetime import datetime, timezone

    path = get_prefabs_dir() / f"{host_uuid}-Prefabs.json"

    # ── Load existing entries (if any) ────────────────────────────────────────
    existing: list = []
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f).get("objects", [])
        except Exception:
            existing = []

    # ── Build lookup: (type, Name) → index in `existing` ─────────────────────
    index: Dict[tuple, int] = {}
    for i, obj in enumerate(existing):
        key = (obj.get("type", ""), obj.get("Name", ""))
        index[key] = i

    # ── Merge ─────────────────────────────────────────────────────────────────
    result = list(existing)
    for new_obj in new_objects:
        key = (new_obj.get("type", ""), new_obj.get("Name", ""))
        if key in index:
            result[index[key]] = dict(new_obj)   # update in-place
        else:
            index[key] = len(result)
            result.append(dict(new_obj))          # append new entry

    # ── Persist ───────────────────────────────────────────────────────────────
    payload = {
        "name":       f"{host_uuid}-Prefabs",
        "host_uuid":  host_uuid,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "objects":    result,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def get_character_path() -> Path:
    return get_base_dir() / "character.sav"


def load_character() -> Optional[dict]:
    """Load character.sav → PlayerObject dict, or None if no file exists."""
    path = get_character_path()
    if not path.exists():
        return None
    try:
        import msgpack, zlib
        with open(path, "rb") as f:
            raw = f.read()
        return msgpack.unpackb(zlib.decompress(raw), raw=False)
    except Exception:
        return None


def save_character(player_dict: dict) -> None:
    """Write PlayerObject dict to character.sav (msgpack + zlib, same as game saves)."""
    import msgpack, zlib
    path = get_character_path()
    packed = msgpack.packb(player_dict, use_bin_type=True)
    with open(path, "wb") as f:
        f.write(zlib.compress(packed, level=9))


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
