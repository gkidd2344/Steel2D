from __future__ import annotations
import base64
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

BUFF_TYPES = ("HP Over Time", "Stat Modifier", "Turn Modifier", "Defense Modifier")


def _migrate_buffs(raw) -> List[dict]:
    """Convert old Dict[str, dict] Buffs format to the new List[dict] format."""
    if isinstance(raw, list):
        return list(raw)
    if not isinstance(raw, dict):
        return []
    result = []
    for name, val in raw.items():
        t = ("Turn Modifier" if name == "Agility" else "Stat Modifier")
        entry = {
            "Name":     name,
            "Type":     t,
            "Value":    int(val.get("Value", 0)),
            "Duration": float(val.get("Duration", 1)),
        }
        if t == "Stat Modifier" and name in STAT_KEYS:
            entry["Stat"] = name
        result.append(entry)
    return result

from app.config import STAT_KEYS


@dataclass
class NPC:
    id: str
    type: str = "NPC"
    Name: str = ""
    Description: str = ""
    Level: int = 1
    Size: str = "Medium"
    Hostile: bool = True
    MaximumHP: int = 10
    CurrentHP: int = 10
    Stats: Dict[str, int] = field(default_factory=lambda: {k: 0 for k in STAT_KEYS})
    Scalars: Optional[Dict[str, str]] = None
    Actions: Optional[Dict[str, dict]] = None
    TurnsAllowed: int = 1
    Buffs: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "Name": self.Name,
            "Description": self.Description,
            "Level": self.Level,
            "Size": self.Size,
            "Hostile": self.Hostile,
            "MaximumHP": self.MaximumHP,
            "CurrentHP": self.CurrentHP,
            "Stats": dict(self.Stats),
            "Scalars": self.Scalars,
            "Actions": self.Actions,
            "TurnsAllowed": self.TurnsAllowed,
            "Buffs": self.Buffs,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NPC":
        return cls(
            id=d["id"],
            type=d.get("type", "NPC"),
            Name=d.get("Name", ""),
            Description=d.get("Description", ""),
            Level=d.get("Level", 1),
            Size=d.get("Size", "Medium"),
            Hostile=d.get("Hostile", True),
            MaximumHP=d.get("MaximumHP", 10),
            CurrentHP=d.get("CurrentHP", 10),
            Stats=d.get("Stats", {k: 0 for k in STAT_KEYS}),
            Scalars=d.get("Scalars"),
            Actions=d.get("Actions"),
            TurnsAllowed=max(1, int(d.get("TurnsAllowed", 1))),
            Buffs=_migrate_buffs(d.get("Buffs", [])),
        )


@dataclass
class Item:
    id: str
    type: str = "Item"
    Name: str = ""
    Description: str = ""
    Level: int = 1
    Consumable: bool = False
    Quantity: int = 1
    Value: int = 0
    Stats: Optional[Dict[str, int]] = None
    Scalars: Optional[Dict[str, str]] = None
    Actions: Optional[Dict[str, dict]] = None
    EquipmentSlot: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "Name": self.Name,
            "Description": self.Description,
            "Level": self.Level,
            "Consumable": self.Consumable,
            "Quantity": self.Quantity,
            "Value": self.Value,
            "Stats": self.Stats,
            "Scalars": self.Scalars,
            "Actions": self.Actions,
            "EquipmentSlot": self.EquipmentSlot,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(
            id=d["id"],
            type=d.get("type", "Item"),
            Name=d.get("Name", ""),
            Description=d.get("Description", ""),
            Level=d.get("Level", 1),
            Consumable=d.get("Consumable", False),
            Quantity=d.get("Quantity", 1),
            Value=d.get("Value", 0),
            Stats=d.get("Stats"),
            Scalars=d.get("Scalars"),
            Actions=d.get("Actions"),
            EquipmentSlot=d.get("EquipmentSlot"),
        )


@dataclass
class Door:
    id: str
    type: str = "Door"
    Open: bool = False
    Broken: bool = False
    Locked: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "Open": self.Open,
            "Broken": self.Broken,
            "Locked": self.Locked,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Door":
        return cls(
            id=d["id"],
            type=d.get("type", "Door"),
            Open=d.get("Open", False),
            Broken=d.get("Broken", False),
            Locked=d.get("Locked", False),
        )


@dataclass
class PlayerObject:
    id: str
    type: str = "Player"
    Name: str = ""         # PlayerAlias (shown in chat, session display name)
    CharacterName: str = "" # In-world character name
    Class: str = ""
    Backstory: str = ""
    Size: str = "Medium"
    Level: int = 1
    MaximumHP: int = 24
    CurrentHP: int = 24
    color: str = "#ffffff"
    Stats: Dict[str, int] = field(default_factory=lambda: {k: 0 for k in STAT_KEYS})
    Equipment: Dict[int, "Item"] = field(default_factory=dict)
    Inventory: List["Item"] = field(default_factory=list)
    avatar_png: Optional[bytes] = None
    # Buffs: list of {Name, Type, Value, Duration, ?Stat}
    # Types: "HP Over Time" | "Stat Modifier" | "Turn Modifier" | "Defense Modifier"
    Buffs: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "Name": self.Name,
            "CharacterName": self.CharacterName,
            "Class": self.Class,
            "Backstory": self.Backstory,
            "Size": self.Size,
            "Level": self.Level,
            "MaximumHP": self.MaximumHP,
            "CurrentHP": self.CurrentHP,
            "color": self.color,
            "Stats": dict(self.Stats),
            "Equipment": {str(k): v.to_dict() for k, v in self.Equipment.items()},
            "Inventory": [item.to_dict() for item in self.Inventory],
            "avatar_png": base64.b64encode(self.avatar_png).decode() if self.avatar_png else None,
            "Buffs": self.Buffs,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlayerObject":
        equipment = {int(k): Item.from_dict(v) for k, v in d.get("Equipment", {}).items()}
        inventory = [Item.from_dict(i) for i in d.get("Inventory", [])]
        avatar_raw = d.get("avatar_png")
        avatar_png = base64.b64decode(avatar_raw) if avatar_raw else None
        return cls(
            id=d["id"],
            type=d.get("type", "Player"),
            Name=d.get("Name", ""),
            CharacterName=d.get("CharacterName", ""),
            Class=d.get("Class", ""),
            Backstory=d.get("Backstory", ""),
            Size=d.get("Size", "Medium"),
            Level=d.get("Level", 1),
            MaximumHP=d.get("MaximumHP", 24),
            CurrentHP=d.get("CurrentHP", 24),
            color=d.get("color", "#ffffff"),
            Stats=d.get("Stats", {k: 0 for k in STAT_KEYS}),
            Equipment=equipment,
            Inventory=inventory,
            avatar_png=avatar_png,
            Buffs=_migrate_buffs(d.get("Buffs", [])),
        )


@dataclass
class Wall:
    id: str
    type: str = "Wall"

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type}

    @classmethod
    def from_dict(cls, d: dict) -> "Wall":
        return cls(id=d["id"], type=d.get("type", "Wall"))


@dataclass
class Stairs:
    id: str
    type: str = "Stairs"
    Name: str = "Stairs"
    Direction: str = "Up"       # "Up" | "Down"
    LinkedStair: str = ""       # UUID of linked Stairs, or ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "Name": self.Name,
            "Direction": self.Direction,
            "LinkedStair": self.LinkedStair,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Stairs":
        return cls(
            id=d["id"],
            type=d.get("type", "Stairs"),
            Name=d.get("Name", "Stairs"),
            Direction=d.get("Direction", "Up"),
            LinkedStair=d.get("LinkedStair", ""),
        )


def occupant_from_dict(d: Optional[dict]):
    if not d:
        return None
    t = d.get("type")
    if t == "NPC":
        return NPC.from_dict(d)
    if t == "Item":
        return Item.from_dict(d)
    if t == "Door":
        return Door.from_dict(d)
    if t == "Wall":
        return Wall.from_dict(d)
    if t == "Stairs":
        return Stairs.from_dict(d)
    return None
