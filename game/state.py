from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Union

from game.objects import NPC, Item, Door, Wall, PlayerObject, occupant_from_dict


@dataclass
class GameSettings:
    hp_base_multiplier: float = 6.0
    enemy_damage_multiplier: float = 1.0
    los_max_distance: int = 20

    def to_dict(self) -> dict:
        return {
            "hp_base_multiplier": self.hp_base_multiplier,
            "enemy_damage_multiplier": self.enemy_damage_multiplier,
            "los_max_distance": self.los_max_distance,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameSettings":
        return cls(
            hp_base_multiplier=float(d.get("hp_base_multiplier", 6.0)),
            enemy_damage_multiplier=float(d.get("enemy_damage_multiplier", 1.0)),
            los_max_distance=int(d.get("los_max_distance", 20)),
        )


@dataclass
class Cell:
    walkable: bool = False
    protected: bool = False
    tile_type: str = "ground"   # "ground" | "water"
    occupant: Optional[Union[NPC, Item, Door]] = None

    def to_dict(self) -> dict:
        return {
            "walkable": self.walkable,
            "protected": self.protected,
            "tile_type": self.tile_type,
            "occupant": self.occupant.to_dict() if self.occupant else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Cell":
        return cls(
            walkable=d.get("walkable", False),
            protected=d.get("protected", False),
            tile_type=d.get("tile_type", "ground"),
            occupant=occupant_from_dict(d.get("occupant")),
        )


MOVE_COST   = 1.5   # points per movement
ACTION_COST = 2.0   # points per action
TURN_THRESHOLD = 3.0  # auto-end when points_spent >= this


@dataclass
class CombatTurn:
    combatant_type: str
    id: str
    name: str
    initiative: int
    has_acted: bool = False
    points_spent: float = 0.0

    @property
    def can_move(self) -> bool:
        return self.points_spent < TURN_THRESHOLD

    @property
    def can_act(self) -> bool:
        return not self.has_acted and self.points_spent < TURN_THRESHOLD

    def to_dict(self) -> dict:
        return {
            "combatant_type": self.combatant_type,
            "id": self.id,
            "name": self.name,
            "initiative": self.initiative,
            "has_acted": self.has_acted,
            "points_spent": self.points_spent,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CombatTurn":
        # back-compat: old saves used has_moved
        old_moved = d.get("has_moved", False)
        ps = float(d.get("points_spent", MOVE_COST if old_moved else 0.0))
        return cls(
            combatant_type=d["combatant_type"],
            id=d["id"],
            name=d["name"],
            initiative=d["initiative"],
            has_acted=d.get("has_acted", False),
            points_spent=ps,
        )


@dataclass
class CombatState:
    active: bool = False
    encounter_npc_ids: List[str] = field(default_factory=list)
    turn_queue: List[CombatTurn] = field(default_factory=list)
    current_index: int = 0
    round_number: int = 1

    def to_dict(self) -> dict:
        return {
            "active": self.active,
            "encounter_npc_ids": list(self.encounter_npc_ids),
            "turn_queue": [t.to_dict() for t in self.turn_queue],
            "current_index": self.current_index,
            "round_number": self.round_number,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CombatState":
        return cls(
            active=d.get("active", False),
            encounter_npc_ids=d.get("encounter_npc_ids", []),
            turn_queue=[CombatTurn.from_dict(t) for t in d.get("turn_queue", [])],
            current_index=d.get("current_index", 0),
            round_number=d.get("round_number", 1),
        )


@dataclass
class GameState:
    name: str = "Untitled"
    settings: GameSettings = field(default_factory=GameSettings)
    grid: Dict[Tuple[int, int], Cell] = field(default_factory=dict)
    players: Dict[str, PlayerObject] = field(default_factory=dict)
    players_at: Dict[str, List[str]] = field(default_factory=dict)
    chat_history: List[dict] = field(default_factory=list)
    host_view: Tuple[float, float] = (0.0, 0.0)
    host_zoom: float = 1.0
    assigned_colors: Dict[str, str] = field(default_factory=dict)
    avatar_cache: Dict[str, str] = field(default_factory=dict)
    combat: Optional[CombatState] = None

    def to_dict(self) -> dict:
        grid_d = {f"{x},{y}": cell.to_dict() for (x, y), cell in self.grid.items()}
        return {
            "name": self.name,
            "settings": self.settings.to_dict(),
            "grid": grid_d,
            "players": {uid: p.to_dict() for uid, p in self.players.items()},
            "players_at": dict(self.players_at),
            "chat_history": list(self.chat_history),
            "host_view": list(self.host_view),
            "host_zoom": self.host_zoom,
            "assigned_colors": dict(self.assigned_colors),
            "avatar_cache": dict(self.avatar_cache),
            "combat": self.combat.to_dict() if self.combat else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        grid = {}
        for key, cell_d in d.get("grid", {}).items():
            x, y = map(int, key.split(","))
            grid[(x, y)] = Cell.from_dict(cell_d)

        players = {uid: PlayerObject.from_dict(pd) for uid, pd in d.get("players", {}).items()}
        combat_d = d.get("combat")
        combat = CombatState.from_dict(combat_d) if combat_d else None
        hv = d.get("host_view", [0.0, 0.0])

        return cls(
            name=d.get("name", "Untitled"),
            settings=GameSettings.from_dict(d.get("settings", {})),
            grid=grid,
            players=players,
            players_at=d.get("players_at", {}),
            chat_history=d.get("chat_history", []),
            host_view=(float(hv[0]), float(hv[1])),
            host_zoom=float(d.get("host_zoom", 1.0)),
            assigned_colors=d.get("assigned_colors", {}),
            avatar_cache=d.get("avatar_cache", {}),
            combat=combat,
        )

    def find_player_cell(self, player_uuid: str) -> Optional[Tuple[int, int]]:
        for key, uuids in self.players_at.items():
            if player_uuid in uuids:
                x, y = map(int, key.split(","))
                return (x, y)
        return None

    def find_object_cell(self, obj_id: str) -> Optional[Tuple[int, int]]:
        for (x, y), cell in self.grid.items():
            if cell.occupant and cell.occupant.id == obj_id:
                return (x, y)
        return None


def make_initial_state(name: str, settings: GameSettings) -> GameState:
    state = GameState(name=name, settings=settings)
    for x in range(4):
        for y in range(4):
            state.grid[(x, y)] = Cell(walkable=True, protected=True)
    return state
