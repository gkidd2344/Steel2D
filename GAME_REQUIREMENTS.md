# Game Lobby — Full Technical Requirements
**Target audience:** Claude Code (automated implementation)  
**Version:** 0.4.0 — combat system, NPC actions, DM impersonation incorporated  
**Supersedes:** REQUIREMENTS v0.3.0

---

## Table of Contents

1. [Overview](#1-overview)
2. [Technology Stack & Dependencies](#2-technology-stack--dependencies)
   - 2.1 [Game Configuration System](#21-game-configuration-system)
3. [Project Structure](#3-project-structure)
4. [Data Models](#4-data-models)
5. [Configuration & Persistence Files](#5-configuration--persistence-files)
6. [Network Architecture & Protocol](#6-network-architecture--protocol)
7. [Main Menu & Profile Screen](#7-main-menu--profile-screen)
8. [Host & Load Game Flows](#8-host--load-game-flows)
9. [Game Canvas & Camera](#9-game-canvas--camera)
10. [Rendering Specification](#10-rendering-specification)
11. [Host (Dungeon Master) Capabilities](#11-host-dungeon-master-capabilities)
12. [Player Capabilities](#12-player-capabilities)
13. [Object System](#13-object-system)
14. [Combat & NPC Interactions](#14-combat--npc-interactions)
15. [Inventory & Equipment System](#15-inventory--equipment-system)
16. [Chat System](#16-chat-system)
17. [Save & Load System](#17-save--load-system)
18. [Settings & Banlist](#18-settings--banlist)
19. [Keybindings Reference](#19-keybindings-reference)
20. [Open Questions](#20-open-questions)

---

## 1. Overview

A desktop **multiplayer tabletop RPG lobby and game runner** built in Python.

One player acts as the **Host (Dungeon Master / DM)**: they build and manage the game world — placing and removing tiles, spawning objects, managing players. Other players act as **Player Characters (PC)**: they join via connection string, move around the world, interact with objects, manage inventories, and participate in chat.

The host runs the authoritative game **server**; all game-state mutations are validated and broadcast by the server. The host also runs a local client on top of the server, with elevated DM-only permissions.

The v0.1.0 skeleton (`main.py`) is valid and must be **refactored into the module structure in §3** without breaking existing behaviour.

---

## 2. Technology Stack & Dependencies

All packages must be declared in `requirements.txt`.

| Package | Version constraint | Purpose |
|---|---|---|
| `Pillow` | `>=10.0` | Avatar image processing, canvas image rendering |
| `msgpack` | `>=1.0` | Binary save-file serialisation (replaces JSON for saves) |
| `asyncio` | stdlib | Async I/O backbone for networking |
| `tkinter` | stdlib (Python ≥ 3.9) | GUI framework |
| `uuid` | stdlib | UUID generation |
| `json` | stdlib | Config files, banlist, network protocol messages |
| `zlib` | stdlib | Save-file compression |
| `threading` | stdlib | Network thread isolation |
| `queue` | stdlib | Thread-safe UI event delivery |
| `dataclasses` | stdlib | Data model definitions |
| `typing` | stdlib | Type annotations |
| `socket` | stdlib | TCP networking |
| `struct` | stdlib | Message framing (length prefix) |
| `pathlib` | stdlib | Cross-platform path handling |
| `datetime` | stdlib | Timestamps |
| `base64` | stdlib | Avatar bytes in config / protocol |
| `re` | stdlib | Chat command parsing |
| `colorsys` | stdlib | Unique player colour generation |
| `math` | stdlib | `math.ceil` in damage formula |

**Python version requirement:** 3.9+  
**Entry point:** `python main.py`

---

### 2.1 Game Configuration System

Two tiers of configuration exist:

#### Global defaults — `game_config.json`

Stored at `<game_dir>/game_config.json`. Created automatically with defaults if absent. Contains the default values used when a new game is created. May be edited manually by the operator; the application reads it at startup. Never written by the application at runtime (operator-only file).

```json
{
  "hp_base_multiplier": 6.0,
  "enemy_damage_multiplier": 1.0,
  "los_max_distance": 20
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `hp_base_multiplier` | float | 6.0 | Multiplier `M` in HP formula: `M * (SizeLookup + Level * max(Con-20, 0))` |
| `enemy_damage_multiplier` | float | 1.0 | Multiplier applied to all NPC-sourced damage against players |
| `los_max_distance` | int | 20 | Maximum grid-cell radius for player line-of-sight |

#### Per-game settings — `GameSettings` (inside `GameState`)

These values are copied from `game_config.json` when a new game is created, then stored inside the `GameState` and saved with the game. They can be adjusted by the DM at game-creation time (see §8.1) or during the game from the DM's ESC menu (§18.2). Changing them mid-game takes effect immediately.

```python
@dataclass
class GameSettings:
    hp_base_multiplier:      float = 6.0
    enemy_damage_multiplier: float = 1.0
    los_max_distance:        int   = 20
```

---

## 3. Project Structure

```
game_lobby/
│
├── main.py                      # Entry point only: App().mainloop()
├── requirements.txt
├── REQUIREMENTS.md              # This document
├── game_config.json             # Global defaults (§2.1) — auto-created
│
├── user.config                  # UUID, alias, avatar (§5.1) — auto-created
├── banlist.json                 # Ban records (§5.4) — auto-created
│
├── saves/                       # Auto-created; holds .sav files (§17)
│
├── app/
│   ├── __init__.py
│   ├── controller.py            # App(tk.Tk) — navigation, owns profile & network refs
│   ├── constants.py             # PALETTE, FONTS, CELL_SIZE, ZOOM_*, PORT, etc.
│   └── config.py                # load_user_config(), save_user_config(),
│                                # load_game_config(), HEALTH_SIZE_LOOKUP,
│                                # SCALAR_WEIGHT_LOOKUP
│
├── screens/
│   ├── __init__.py
│   ├── main_menu.py             # MainMenuScreen
│   ├── profile.py               # ProfileScreen
│   └── game.py                  # GameScreen (host & client; role governs widgets)
│
├── dialogs/
│   ├── __init__.py
│   ├── host_dialog.py           # HostDialog (New Game / Load Game)
│   ├── join_dialog.py           # JoinDialog
│   ├── new_game_settings.py     # NewGameSettingsDialog (pre-game DM config)
│   ├── load_game_dialog.py      # LoadGameDialog
│   ├── spawn_object_dialog.py   # SpawnObjectDialog & ModifyObjectDialog
│   ├── door_dialog.py           # DoorInteractionDialog
│   ├── inventory_dialog.py      # InventoryDialog (B key)
│   ├── player_list_overlay.py   # PlayerListOverlay (TAB key)
│   ├── player_stats_dialog.py   # PlayerStatsDialog (C key) & PlayerStatsTooltip
│   ├── object_tooltip.py        # ObjectTooltip
│   ├── confirm_dialog.py        # Reusable yes/no popup
│   ├── banlist_dialog.py        # BanlistDialog
│   ├── combat_overlay.py        # TurnOrderPanel overlay (rendered during combat)
│   └── dm_options_dialog.py     # DM right-click → Options
│
├── game/
│   ├── __init__.py
│   ├── state.py                 # GameState, GameSettings, Cell — authoritative
│   ├── objects.py               # NPC, Item, ItemAction, Door, PlayerObject
│   ├── stats.py                 # clamp_stats(), calc_max_hp(), effective_stats()
│   ├── combat.py                # CombatState, CombatTurn, roll_initiative(), advance_turn()
│   ├── los.py                   # has_los(), cells_in_range()
│   └── serialise.py             # dump_state() → bytes, load_state(bytes) → GameState
│
├── network/
│   ├── __init__.py
│   ├── protocol.py              # Message constants, encode_msg(), decode_msg()
│   ├── server.py                # GameServer (asyncio TCP, background thread)
│   └── client.py                # GameClient (asyncio TCP, background thread)
│
└── ui/
    ├── __init__.py
    ├── widgets.py               # flat_btn(), hr(), styled_entry() — from v0.1.0
    ├── canvas_renderer.py       # GameCanvas(tk.Canvas)
    └── chat_widget.py           # ChatWidget
```

### Migration note (from v0.1.0)

Move all shared helpers (`flat_btn`, `hr`, `styled_entry`, `C`, `F_*`) into `ui/widgets.py`. Move `load_profile`/`save_profile` into `app/config.py` (merging with `load_user_config`). Move `App` into `app/controller.py`. Rename profile storage from `~/.game_lobby/profile.json` to `<game_dir>/user.config`. `main.py` becomes only:

```python
from app.controller import App
if __name__ == "__main__":
    App().mainloop()
```

---

## 4. Data Models

All models are defined with `@dataclass`. Every model implements `to_dict() -> dict` and a `@classmethod from_dict(d: dict) -> Self` for msgpack/JSON serialisation. Tuple keys `(x, y)` are serialised as the string `"x,y"` and deserialised back to tuples.

---

### 4.1 Lookup Tables (in `app/config.py`)

```python
HEALTH_SIZE_LOOKUP: dict[str, int] = {
    "Small":    2,
    "Medium":   4,
    "Large":    6,
    "Giant":    9,
    "Colossal": 13,
}

SCALAR_WEIGHT_LOOKUP: dict[str, float] = {
    "S": 1.00,
    "A": 0.70,
    "B": 0.45,
    "C": 0.15,
    "F": 0.05,
}

STAT_KEYS = ("Str", "Dex", "Con", "Int", "Wis", "Cha")
```

---

### 4.2 Stats Dict

```python
# Dict always has exactly the six STAT_KEYS as keys with int values.
Stats = dict  # TypeAlias: Dict[str, int]
```

#### Constraint rules (`game/stats.py`)

```
MAX_INDIVIDUAL(level) = 18 + (level * 2)
MAX_TOTAL(level)      = 70 + (level * 3)
MIN_INDIVIDUAL        = 0
```

#### Clamping algorithm — `clamp_stats(stats: Stats, level: int) -> Stats`

1. For each key in `STAT_KEYS`: clamp `stats[key]` to `[0, MAX_INDIVIDUAL(level)]`.
2. While `sum(stats.values()) > MAX_TOTAL(level)`:
   - Iterate `STAT_KEYS` in order, cycling.
   - For each key whose value > 0: subtract 1.
   - Break as soon as sum ≤ MAX_TOTAL.
3. Return the clamped dict.

#### HP calculation — `calc_max_hp(size: str, level: int, con: int, multiplier: float) -> int`

```python
import math

def calc_max_hp(size: str, level: int, con: int, multiplier: float) -> int:
    size_val = HEALTH_SIZE_LOOKUP.get(size, 4)   # default Medium if unknown
    con_bonus = max(con - 20, 0)
    return max(1, math.ceil(multiplier * (size_val + level * con_bonus)))
```

`multiplier` comes from `GameSettings.hp_base_multiplier`. The result is always ≥ 1.

#### For Items with optional Stats

Always use `stats.get(key, 0)` — never assume all keys exist.

---

### 4.3 NPC

```python
@dataclass
class NPC:
    id:          str           # UUID4; assigned by server at spawn
    type:        str = "NPC"  # literal discriminator
    Name:        str = ""
    Description: str = ""
    Level:       int = 1
    Size:        str = "Medium"   # "Small"|"Medium"|"Large"|"Giant"|"Colossal"
    Hostile:     bool = True
    MaximumHP:   int = 10         # Set at spawn; recalculated if Level/Size/Con change
    CurrentHP:   int = 10         # Active-state; modified by combat/healing
    Stats:       Stats = field(default_factory=lambda: {k: 0 for k in STAT_KEYS})
    Scalars:     Optional[Dict[str, str]] = None  # e.g. {"Str": "A"} — same grade system as Item
    Actions:     Optional[Dict[str, "ItemActionDict"]] = None  # same schema as Item.Actions
```

`NPC.Scalars` and `NPC.Actions` follow the identical schema as `Item.Scalars` / `Item.Actions` (§4.4). The DM may define NPC-specific attack abilities at spawn time or via "Modify Object". During combat, the DM selects from these actions when controlling the NPC's turn (§11.8). The `Scalars` dict applies globally to all of the NPC's actions in the damage formula (§14.2), using the NPC's own `Stats` as the combatant stats.

**Spawn default pre-fill:**
```python
MaximumHP = CurrentHP = calc_max_hp(
    size=Size, level=Level, con=Stats.get("Con", 0),
    multiplier=game_settings.hp_base_multiplier
)
```

The DM may override both `MaximumHP` and `CurrentHP` freely in the spawn form and at any time via "Modify Object". Changing `Level`, `Size`, or any stat in a modify dialog triggers `MaximumHP` to recalculate and display the new value as a pre-fill, but the DM must confirm before it is written.

---

### 4.4 Item

```python
@dataclass
class Item:
    id:            str
    type:          str = "Item"
    Name:          str = ""
    Description:   str = ""
    Level:         int = 1
    Consumable:    bool = False
    Quantity:      int = 1
    Value:         int = 0
    Stats:         Optional[Stats]                    = None
    Scalars:       Optional[Dict[str, str]]           = None  # e.g. {"Str": "A", "Int": "C"}
    Actions:       Optional[Dict[str, "ItemAction"]]  = None  # key = action display name
    EquipmentSlot: Optional[int]                      = None  # see §4.7
```

#### 4.4.1 ItemAction

Each entry in `Item.Actions` is a dict (not a separate dataclass, for serialisation simplicity):

```python
ItemAction = {
    "Description": str,   # Shown in action sub-menu tooltip
    "Range":       int,   # 0 = self-only; 1 = adjacent 4 cells; N = radius N (Euclidean) + LOS
    "BaseDamage":  int,   # Positive = damage; negative = healing; see §14
    "Hits":        int,   # Number of times damage is applied (total = damage_per_hit * Hits)
}
```

**Example (for DM reference in UI):**

```python
item.Actions = {
    "Attack": {
        "Description": "A broad swing of the mace.",
        "Range": 1,
        "BaseDamage": 4,
        "Hits": 1,
    },
    "Fireball": {
        "Description": "Launch molten slag at a distant enemy.",
        "Range": 5,
        "BaseDamage": 9,
        "Hits": 1,
    },
    "Lay On Hands": {
        "Description": "Uses holy power to heal an adjacent target.",
        "Range": 1,
        "BaseDamage": -999,
        "Hits": 1,
    },
}
```

**`Item.Scalars`** is the item-level stat-scaling dict, applied globally to **all** of the item's actions during damage calculation. If `Scalars` is `None` or `{}`, damage equals `BaseDamage` only (no stat contribution). See §14 for the full formula.

---

### 4.5 Door

```python
@dataclass
class Door:
    id:     str
    type:   str  = "Door"
    Open:   bool = False
    Broken: bool = False
    Locked: bool = False
```

---

### 4.6 PlayerObject

```python
@dataclass
class PlayerObject:
    id:          str           # == connecting player's UUID from user.config
    type:        str = "Player"
    Name:        str = ""      # == PlayerAlias at join time; does not update if alias changes mid-session
    Size:        str = "Medium"
    Level:       int = 1
    MaximumHP:   int = 24      # Recalculated on Level Up or Con stat change; see §4.6.1
    CurrentHP:   int = 24      # Modified only by DM action or combat; see §4.6.1
    color:       str = "#ffffff"
    Stats:       Stats = field(default_factory=lambda: {k: 0 for k in STAT_KEYS})
    Equipment:   Dict[int, "Item"] = field(default_factory=dict)
    Inventory:   List["Item"]      = field(default_factory=list)
    avatar_png:  Optional[bytes]   = None   # 128×128 PNG bytes
```

#### 4.6.1 Player HP Rules

**Initial HP at first join (new game):**
```python
MaximumHP = CurrentHP = calc_max_hp(
    size="Medium", level=1, con=0,
    multiplier=game_settings.hp_base_multiplier
)
# = ceil(6.0 * (4 + 1 * max(0-20, 0))) = ceil(6.0 * 4) = 24
```

**Players CANNOT directly edit their own HP.** Only the DM or NPC/item combat effects modify `CurrentHP`.

**On Level Up** (`Level += 1`):
1. Recalculate `MaximumHP` using new Level and current Con.
2. Set `CurrentHP = MaximumHP` (full heal on level up).

**On Con stat change** (whenever `Stats["Con"]` is updated via `STATS_UPDATE` or DM modification):
```python
old_max = MaximumHP
new_max = calc_max_hp(size, level, new_con, multiplier)
MaximumHP = new_max

if con_increased:
    if CurrentHP == old_max:
        CurrentHP = new_max   # Was at full health → stay at full
    # else: CurrentHP stays unchanged (damaged players don't auto-heal)
else:  # con_decreased
    CurrentHP = max(1, new_max - 1)   # Always drops below new max; never below 1
```

---

### 4.7 Equipment Slot IDs

```python
EQUIPMENT_SLOTS = {
    1: "Head",
    2: "Chest",
    3: "Legs",
    4: "Feet",
    5: "Ring",
    6: "Trinket",
    7: "Main Hand",
    8: "Off Hand",
}
```

---

### 4.8 Cell

```python
@dataclass
class Cell:
    walkable:  bool = False
    protected: bool = False   # True for initial 4x4 spawn cells; cannot be deleted
    occupant:  Optional[Union[NPC, Item, Door]] = None
```

A cell can simultaneously have a `walkable` tile, one non-player `occupant`, and zero-or-more PlayerObjects (tracked via `GameState.players_at`). A non-player occupant can only exist on a walkable cell.

---

### 4.9 GameState

```python
@dataclass
class GameState:
    name:            str = "Untitled"
    settings:        GameSettings = field(default_factory=GameSettings)
    grid:            Dict[str, Cell] = field(default_factory=dict)
    # Serialised grid key: "x,y" string; deserialised back to (int,int) tuple
    players:         Dict[str, PlayerObject] = field(default_factory=dict)
    # players_at: "x,y" → list of player UUIDs on that cell
    players_at:      Dict[str, List[str]] = field(default_factory=dict)
    chat_history:    List[dict] = field(default_factory=list)   # excludes whispers
    host_view:       Tuple[float, float] = (0.0, 0.0)           # viewport offset at save
    host_zoom:       float = 1.0
    assigned_colors: Dict[str, str] = field(default_factory=dict)  # uuid → hex color
    avatar_cache:    Dict[str, str] = field(default_factory=dict)   # uuid → base64 PNG
    combat:          Optional["CombatState"] = None                 # None = free-move mode
```

**Grid coordinate system:**
- Origin `(0,0)` = top-left of the initial 4×4 block.
- X increases rightward, Y increases downward.
- Coordinates are unbounded integers in both directions.
- **New game initial state**: cells `(x, y)` for `x in range(4), y in range(4)` created as `Cell(walkable=True, protected=True)`. These 16 cells' `protected=True` flag makes their tiles permanent.

---

### 4.10 ChatMessage dict

```python
{
    "sender_uuid":    str,           # "SYSTEM" for automated messages
    "sender_alias":   str,
    "content":        str,
    "msg_type":       str,           # "normal" | "yell" | "whisper" | "system" | "error"
    "recipient_uuid": Optional[str], # whisper only
    "timestamp":      str,           # ISO-8601
}
```

Whisper messages (`msg_type == "whisper"`) are **excluded** from `chat_history` and save files.

---

### 4.11 BanRecord

In `banlist.json`, stored as a JSON array:

```json
{
  "uuid":       "...",
  "alias":      "PlayerAlias",
  "banned_at":  "2024-01-01T12:00:00",
  "expires_at": null,
  "reason":     "ban | temp_disconnect"
}
```

`expires_at == null` → permanent. Temp-block records (1-minute disconnect) have `expires_at = banned_at + 60s`. Expired temp-block records may be auto-purged when `banlist.json` is read.

---

### 4.12 CombatTurn

One entry in the encounter initiative order:

```python
@dataclass
class CombatTurn:
    combatant_type: str   # "player" | "npc"
    id:             str   # player UUID or NPC UUID
    name:           str   # PlayerAlias or NPC.Name (for UI display)
    initiative:     int   # roll result; higher goes first
    has_moved:      bool = False   # used their 1 movement this turn
    has_acted:      bool = False   # used their 1 action this turn
```

Both resources reset to `False` at the start of each combatant's turn.

---

### 4.13 CombatState

```python
@dataclass
class CombatState:
    active:              bool = False
    encounter_npc_ids:   List[str]        = field(default_factory=list)
    # ^^ NPC UUIDs added via "Add To Encounter"; persists across Start/End Combat cycles
    turn_queue:          List[CombatTurn] = field(default_factory=list)
    # ^^ Populated by START_COMBAT; sorted descending by initiative
    current_index:       int = 0
    # ^^ Index into turn_queue; wraps around on full rotation
    round_number:        int = 1
```

`CombatState` lives inside `GameState` as `GameState.combat: Optional[CombatState] = None`. If `combat is None` or `combat.active == False`, the game is in free-move mode. `CombatState` is serialised and saved with the game; if a save is loaded with `combat.active == True`, combat resumes from the saved state.

**When an NPC in `turn_queue` is killed:** remove it from `turn_queue`. If it was the current combatant (`turn_queue[current_index].id == dead_npc_id`): do NOT advance `current_index` (the next element has shifted into the current slot). Adjust `current_index` only if the killed NPC was before the current position in the queue.

---

## 5. Configuration & Persistence Files

### 5.1 `user.config`

Located at `<game_dir>/user.config`. Format: JSON. Auto-created on first launch.

```json
{
  "uuid":           "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx",
  "alias":          "",
  "avatar_b64":     null,
  "preferred_port": 5000
}
```

- `uuid`: generated once via `uuid.uuid4()`, never regenerated.
- `alias`: string, max 32 chars.
- `avatar_b64`: base64-encoded 128×128 PNG, or `null`.
- `preferred_port`: default host port; configurable in future.

### 5.2 `game_config.json`

Located at `<game_dir>/game_config.json`. See §2.1. Auto-created with defaults. Never written by the app at runtime.

### 5.3 `saves/` directory

At `<game_dir>/saves/`. Auto-created. See §17 for naming and format.

### 5.4 `banlist.json`

At `<game_dir>/banlist.json`. Auto-created as `[]`. See §4.11.

---

## 6. Network Architecture & Protocol

### 6.1 Roles

| Role | Runs | Notes |
|---|---|---|
| Host / DM | `GameServer` + local `GameClient` | Authoritative; DM commands validated server-side |
| Player Character | `GameClient` | Remote; no DM permissions |

The host's local `GameClient` connects to `127.0.0.1:<port>` and is marked `is_host=True` server-side. All privilege checks are server-side.

**Networking scope:** TCP sockets. Works on LAN without configuration. For internet play, the host must port-forward `preferred_port`. No NAT traversal in v0.3.0 (Steamworks integration is a post-v0.3.0 milestone).

### 6.2 Thread Safety

- All network I/O runs in a dedicated background `threading.Thread` via an `asyncio` event loop.
- A `queue.Queue` named `ui_queue` is polled by `root.after(50, _poll_ui_queue)` on the main thread.
- Network thread posts `(event_type: str, payload: dict)` tuples; UI thread dequeues and dispatches.
- **Never call tkinter methods from the network thread directly.**

### 6.3 Message Framing

```
[4 bytes little-endian uint32: body_length][body_length bytes: UTF-8 JSON]
```

```python
# network/protocol.py
import struct, json

def encode_msg(msg: dict) -> bytes:
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    return struct.pack("<I", len(body)) + body

def decode_msg(data: bytes) -> dict:
    # data starts immediately after the length prefix has been consumed
    return json.loads(data.decode("utf-8"))
```

The server reads the 4-byte prefix first, then reads exactly that many bytes for the body. The protocol uses JSON (human-readable; small messages). Only save files use msgpack+zlib.

### 6.4 Message Catalogue

All messages contain `"type": str` as their first key.

#### Client → Server

| type | Key payload fields | Notes |
|---|---|---|
| `HELLO` | `uuid, alias, avatar_b64` (nullable) | First message post-connect |
| `PLAYER_MOVE` | `target_cell: [x, y]` | Server validates adjacency and occupancy |
| `PLAYER_ACTION` | `action_name, item_id, target_id, target_cell` | `item_id` null for default Attack |
| `CHAT_SEND` | `content, msg_type, recipient_alias` (whisper) | |
| `DOOR_INTERACT` | `cell: [x, y], action: "open"/"close"` | |
| `ITEM_PICKUP` | `cell: [x, y], item_id` | Pick up item from map |
| `ITEM_DROP` | `item_id` | Drop from inventory to map |
| `ITEM_DISCARD` | `item_id` | Delete from inventory |
| `ITEM_USE` | `item_id` | Use consumable |
| `ITEM_EQUIP` | `item_id` | Equip to slot |
| `STATS_UPDATE` | `stats: dict` | After player confirms stat allocation |
| `PLAYER_END_TURN` | — | Player signals their combat turn is complete |
| `DISCONNECT` | — | Graceful disconnect |
| `PING` | `ts: float` | Keepalive |

#### Server → Client (all)

| type | Key payload fields | Notes |
|---|---|---|
| `WELCOME` | `player_id, game_state: dict, your_cell: [x, y]` | Full initial state |
| `REJECT` | `reason: str` | Connection refused |
| `STATE_PATCH` | `patches: list[PatchOp]` | Incremental update |
| `CHAT_RECV` | `message: ChatMessage dict` | Display in chat |
| `CHAT_ERROR` | `text: str` | Red system error in chat (client-side only triggering) |
| `CAMERA_CENTER` | `cell: [x, y]` | Recipient must centre their viewport on this cell |
| `PLAYER_DISCONNECTED` | `uuid, alias` | Another player left |
| `YOU_WERE_KICKED` | `reason: str` | Force-disconnect |
| `PONG` | `ts: float, server_ts: float` | Keepalive response |
| `COMBAT_STARTED` | `turn_queue: list[CombatTurn dict], round: int` | Broadcast at combat start |
| `COMBAT_ENDED` | — | Broadcast when DM ends combat |
| `COMBAT_TURN_ADVANCED` | `current: CombatTurn dict, queue: list, round: int` | Next combatant's turn |
| `COMBAT_RESOURCES_USED` | `combatant_id: str, has_moved: bool, has_acted: bool` | Sync turn resource state |

#### Host DM → Server (DM-only; server validates `is_host`)

| type | Key payload fields |
|---|---|
| `DM_TILE_SET` | `cell: [x, y], walkable: bool` |
| `DM_SPAWN_OBJECT` | `cell: [x, y], object: dict` |
| `DM_DELETE_OBJECT` | `cell: [x, y]` |
| `DM_MODIFY_OBJECT` | `cell: [x, y], object: dict` |
| `DM_MOVE_OBJECT` | `from_cell: [x, y], to_cell: [x, y]` |
| `DM_WARP_PLAYERS` | `target_cells: list[[x, y]]` — one per connected player, in random order |
| `DM_LEVEL_UP_PLAYER` | `player_uuid: str` |
| `DM_KICK_PLAYER` | `player_uuid: str` |
| `DM_BAN_PLAYER` | `player_uuid: str` |
| `DM_MODIFY_PLAYER` | `player_uuid: str, patch: dict` — arbitrary field overrides (DM editing player stats) |
| `DM_UPDATE_SETTINGS` | `settings: dict` — update `GameSettings` fields |
| `DM_ADD_TO_ENCOUNTER` | `npc_id: str` — add NPC to `encounter_npc_ids` |
| `DM_REMOVE_FROM_ENCOUNTER` | `npc_id: str` — remove NPC from `encounter_npc_ids` |
| `DM_START_COMBAT` | — — server rolls initiatives and populates `turn_queue` |
| `DM_END_COMBAT` | — — server clears `CombatState`, returns to free-move |
| `DM_NPC_MOVE` | `npc_id: str, target_cell: [x, y]` — move NPC 1 tile during its turn |
| `DM_NPC_ACTION` | `npc_id: str, action_name: str, target_id: str, target_cell: [x, y]` |
| `DM_NPC_END_TURN` | `npc_id: str` — DM signals end of NPC's combat turn |
| `DM_CHAT_AS_NPC` | `npc_id: str, content: str, msg_type: str, recipient_alias: str` (optional, whisper) |

### 6.5 PatchOp format

```python
{
    "op":    str,    # "set_cell" | "set_player" | "del_player" |
                     # "set_players_at" | "set_settings" | ...
    "path":  any,    # Target key (cell "x,y" string, player uuid, etc.)
    "value": any,    # New value (serialised dict or primitive); omitted for delete ops
}
```

### 6.6 Connection Flow

```
Client                               Server
  │                                     │
  ├──[TCP connect]────────────────────→ │ Check banlist; if banned → REJECT + close
  │ ←─[REJECT]───────────────────────── │ (if banned)
  │                                     │
  ├──[HELLO: uuid, alias, avatar_b64]─→ │ Assign/restore PlayerObject
  │                                     │ Assign colour (from assigned_colors or new unique)
  │                                     │ Store avatar if not already in avatar_cache
  │ ←─[WELCOME: full state, your_cell]── │
  │                                     │ Broadcast STATE_PATCH (new player joined) to others
  │  [session …]                        │
  ├──[DISCONNECT]─────────────────────→ │ Broadcast PLAYER_DISCONNECTED to remaining clients
```

Avatar logic: if `avatar_cache[uuid]` already exists server-side, the `avatar_b64` field in `HELLO` is ignored (even if the player's local avatar has changed). The saved avatar is used. This is intentional — it matches what other players have already rendered.

### 6.7 Keepalive & Latency

- Clients send `PING` with `ts = time.time()` every 5 seconds.
- Server responds with `PONG` containing the original `ts` and `server_ts`.
- Client records round-trip latency `ms = (time.time() - ts) * 1000`.
- If no `PONG` within 15 seconds of a `PING`, server considers the client timed out and broadcasts `PLAYER_DISCONNECTED`.
- Latency is displayed in the Player List overlay (§12.4).

---

## 7. Main Menu & Profile Screen

### 7.1 Main Menu Layout

```
┌──────────────────────────────────── [⚙]─┐
│                                          │
│  GAME LOBBY  v0.3.0                      │
│  multiplayer lobby                       │
│  ──────────────────────────────────      │
│  [avatar 40×40]  Signed in as  <alias>   │
│                                          │
│  [ 👤  Configure Profile             ]   │
│  [ 🖥  Host a Game                   ]   │
│  [ 🌐  Join a Game                   ]   │
│  [ ✕   Quit                          ]   │
└──────────────────────────────────────────┘
```

- **⚙ gear icon**: top-right of the window (not of the card). Opens `BanlistDialog`.
- **Avatar thumbnail**: if `user.config["avatar_b64"]` is not null, display a 40×40 scaled `PIL.ImageTk.PhotoImage` inline beside "Signed in as".

### 7.2 Profile Screen Layout

```
┌──────────────────────────────────────────┐
│  Configure Profile                       │
│  ─────────────────────────────────────   │
│  Username / Alias  [__________________]  │
│                                          │
│  Profile Picture                         │
│  ┌──────────┐                            │
│  │          │  [ Upload Image  ]         │
│  │  128×128 │  [ Remove Image  ]         │
│  │ preview  │                            │
│  └──────────┘                            │
│                                          │
│  [ Save ]  [ Cancel ]                    │
└──────────────────────────────────────────┘
```

**Avatar upload flow:**

1. `filedialog.askopenfilename` with filter `("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp")`.
2. Open with `PIL.Image.open(path)`.
3. Process to 128×128 PNG:
   - Determine shortest dimension `s`.
   - Scale so `s = 128` (preserve aspect ratio, `Image.LANCZOS` resampling).
   - Crop the longer dimension to 128 from centre:
     - Width > height after scale: `left = (w - 128) / 2`; crop `(left, 0, left+128, 128)`.
     - Height > width after scale: `top = (h - 128) / 2`; crop `(0, top, 128, top+128)`.
     - Equal: no crop needed.
   - Convert to `"RGBA"`, save to `io.BytesIO` as PNG, base64-encode.
4. Show 128×128 preview in dialog using `PIL.ImageTk.PhotoImage`.
5. **On Save**: write `avatar_b64` to `user.config` and call `save_user_config()`.
6. **On Cancel**: discard; config unchanged.
7. **Remove Image**: set `avatar_b64 = null`, clear preview.

---

## 8. Host & Load Game Flows

### 8.1 New Game Flow

Clicking "🖥 Host a Game" opens `HostDialog`. Clicking "🆕 New Game" opens `NewGameSettingsDialog` (a `tk.Toplevel`) **before** the game starts:

```
┌──────────────────────────────────────┐
│  New Game Settings                   │
│  ─────────────────────────────────   │
│  Game Name  [________________]       │
│                                      │
│  HP Base Multiplier  [ 6.0 ]         │
│  Enemy Damage Mult.  [ 1.0 ]         │
│  LOS Max Distance    [  20 ]         │
│                                      │
│  [ Start ]  [ Cancel ]               │
└──────────────────────────────────────┘
```

- Pre-populate with values from `game_config.json`.
- "Game Name" field defaults to `"Untitled"`.
- On **Start**: create `GameState` with the entered `GameSettings`, start `GameServer`, navigate to `GameScreen` (DM role).

### 8.2 Load Game Dialog

See §17.3 for details. Clicking "📂 Load Game" opens `LoadGameDialog`.

### 8.3 Join Dialog

`JoinDialog` now actually creates a `GameClient`, connects, and on `WELCOME` navigates to `GameScreen` (PC role). On `REJECT`, shows the rejection reason in `messagebox.showerror`.

---

## 9. Game Canvas & Camera

### 9.1 GameScreen Layout

```
┌──────────────────────────────────────────────────────┐
│  [DM HUD: Connection string | N players online]      │  ← DM only; thin tk.Frame
├──────────────────────────────────────────────────────┤
│                                                      │
│                    GameCanvas                        │
│               (tk.Canvas, fills rest)                │
│                                                      │
│  ┌──────────────────────────────┐                    │
│  │ ChatWidget (bottom-left)     │                    │
│  │ 300×150px                    │                    │
│  └──────────────────────────────┘                    │
└──────────────────────────────────────────────────────┘
```

The `ChatWidget` is placed using `canvas.create_window` or `place()` so it floats above the canvas, always on top. The DM HUD bar above the canvas shows the host's LAN IP:Port and the count of connected players.

### 9.2 Cell Size & Zoom

```python
BASE_CELL_PX = 64     # pixels per cell at zoom 1.0
ZOOM_MIN     = 0.25
ZOOM_MAX     = 4.0
ZOOM_STEP    = 0.1    # per scroll tick
```

**Effective cell size** = `BASE_CELL_PX * zoom`.

**Scroll-to-zoom** centres on the mouse cursor:
1. Record mouse canvas coords `(mx, my)`.
2. Compute world coords before zoom: `wx = mx / zoom + offset_x`, `wy = my / zoom + offset_y`.
3. Apply `zoom ± ZOOM_STEP`, clamped.
4. Compute new offsets so the same world point stays under cursor:
   `offset_x = wx - mx / new_zoom`, `offset_y = wy - my / new_zoom`.

### 9.3 Viewport & Pan

Viewport defined by `(offset_x, offset_y)` in **world pixels** (cell coord × `BASE_CELL_PX`).

**WASD / Arrow keys** pan by `BASE_CELL_PX / 2` world-pixels per event (repeatable while held).

**Canvas-to-cell conversion:**
```python
def canvas_to_cell(cx: float, cy: float, offset_x: float, offset_y: float, zoom: float):
    wpx = cx / zoom + offset_x
    wpy = cy / zoom + offset_y
    return int(wpx // BASE_CELL_PX), int(wpy // BASE_CELL_PX)
```

### 9.4 Render Loop

`canvas.after(16, _redraw)` (≈60 fps). Each frame:

1. `canvas.delete("all")`.
2. Draw background grid lines.
3. Draw walkable tiles.
4. Draw object sprites (NPC, Item, Door).
5. Draw player sprites.
6. Draw active animations (death fades, text bubbles).
7. Draw hover tooltip if applicable.
8. Draw drag-ghost if DM is mid-drag.

---

## 10. Rendering Specification

### 10.1 Background Grid

- Canvas background: `#000000`.
- Faint grid lines at every cell boundary across visible area: colour `#1a1a1a`, width 1px.

### 10.2 Walkable Tiles

- Fill `#ffffff`, drawn with a **2px inward padding** on all sides from the cell boundary.
- Cell at world-rect `(cx, cy, cx+cell, cy+cell)` → tile rect `(cx+2, cy+2, cx+cell-2, cy+cell-2)`.
- No border on tile itself.

### 10.3 Object Sprites (centred in cell, minimum 4px padding from cell edges)

#### NPC — Hostile (`Hostile=True`)
- Upward equilateral triangle, ~70% of cell area.
- Fill `#cc2222`, outline `#880000`, 2px.
- `canvas.create_polygon`.

#### NPC — Friendly (`Hostile=False`)
- Circle, diameter ~70% of cell.
- Fill `#22aa22`, outline `#115511`, 2px.
- `canvas.create_oval`.

#### Item
- 8-vertex 4-pointed star. Outer radius ≈ 38% of cell, inner radius ≈ 18% of cell.
- Vertices at 0°, 45°, 90°… alternating outer/inner.
- Fill `#ff8800`, outline `#000000`, 1.5px.

#### Door — Closed (`Open=False`)
- Rectangle: cell rect inset by **2px** on all sides.
- Fill `#8b4513`, outline `#5c2d0a`, 2px.

#### Door — Open (`Open=True`)
- Same bounding rect.
- Fill `""` (no fill), outline `#8b4513`, 2px.

#### Door — Broken modifier (`Broken=True`)
- Draw two short diagonal lines crossing the door rect: colour `#333333`, 1px.

#### Door — Locked modifier (`Locked=True`)
- Draw a small padlock symbol (simplified polygon) centred on the door in `#ffcc00`.

### 10.4 Player Sprites

- Rectangle filling ~80% of cell (centred).
- Fill: player's `assigned_colors[uuid]`.
- Outline: fill colour with each RGB channel × 0.6 (darker), 2px.
- If `avatar_png` is not None: render the PNG scaled to `int(cell_size * 0.75)` px, centred.
  - Cache resized `PIL.ImageTk.PhotoImage` by `(uuid, int(cell_size))` to avoid redundant scaling.

### 10.5 Player Color Assignment

When a new player has no entry in `GameState.assigned_colors`:
1. Generate `colorsys.hsv_to_rgb(h, 0.75, 0.85)` with `h` maximising distance from existing hues.
2. Reject hues within 0.08 of reserved hues: black, white, red (NPC hostile), green (NPC friendly), orange (Item), brown (Door).
3. Convert to `#rrggbb`. Store in `assigned_colors[uuid]`.

### 10.6 Text Bubbles (Chat)

Text bubbles appear **above the player sprite** of the message sender. They are rendered on the game canvas as:
- A rounded rectangle (dark semi-transparent background: `#000000` with ~80% apparent opacity via blending).
- Text rendered on top in the message's colour (see §16.2 tag colours).
- Content: the message text, truncated at 60 chars if longer (with `…`).
- Auto-dismissed after **3 seconds**.
- Multiple consecutive messages from the same player stack vertically (newest at bottom, closest to sprite).

**Per-player bubble state** (maintained in `GameCanvas`):
```python
bubbles: List[{
    "player_uuid": str,
    "text":        str,
    "color":       str,
    "born_at":     float,   # time.time() at creation
}]
```

On each render frame, remove entries where `time.time() - born_at > 3.0`. For alpha fade in the final 0.5 seconds, interpolate text colour toward background.

**Whisper bubbles**: only appear on the **receiving** client's screen, above the receiving player's sprite. The server routes whisper `CHAT_RECV` only to sender and recipient. The recipient's client displays the bubble; no other client sees it.

### 10.7 Hover Tooltips

On `<Motion>`, convert canvas coords to cell. Determine what is in that cell and whether the hovering entity has LOS.

| Hovering over | LOS required (PC) | DM sees | PC sees |
|---|---|---|---|
| Player cell | No | Name, HP (`CurrentHP/MaxHP`), Stats + equipment bonuses | Same |
| NPC cell | Yes | Name, Desc, HP, Stats, Hostile, Size | Name, Desc |
| Item cell | Yes | Name, Desc, Quantity, Level, Value | Name, Desc |
| Door cell | Yes | All Door metadata | (Door interaction via click) |
| Empty cell | — | Cell coordinates | Nothing |

Tooltip panel: `canvas.create_rectangle` (`fill="#000000"`) + `canvas.create_text` layered on top. Positioned near cursor, offset to avoid covering the target cell. Dismissed when cursor moves to a different cell.

### 10.8 Line of Sight (`game/los.py`)

```python
def has_los(state: GameState, from_cell: Tuple[int,int], to_cell: Tuple[int,int],
            max_distance: int) -> bool:
    """
    Returns True if to_cell is visible from from_cell.
    Checks:
      1. Euclidean distance ≤ max_distance (from GameSettings.los_max_distance).
      2. Bresenham ray from from_cell to to_cell: any intermediate cell that is
         NOT walkable blocks LOS. Diagonal corners (1-cell diagonal gap) do NOT block.
    """
```

```python
def cells_in_range(origin: Tuple[int,int], action_range: int,
                   state: GameState, max_los: int) -> Set[Tuple[int,int]]:
    """
    Returns all cells reachable by an action with the given Range.
    Range = 0: {origin} only.
    Range = 1: the 4 orthogonal neighbours of origin.
    Range > 1: all cells with Euclidean distance ≤ action_range AND has_los(origin, cell).
    """
```

### 10.9 Death Animation

When an NPC's `CurrentHP ≤ 0` and the server deletes it, the client-side animation runs before removing the canvas items:

- Duration: 500ms, 10 steps at 50ms intervals via `canvas.after`.
- Each step: blend NPC fill colour toward `#000000` by 10% per step.
  - `r_new = int(r * (1 - step/10))` etc.; `canvas.itemconfig(tag, fill=new_hex)`.
- After step 10: remove canvas items.

The server has already sent the `STATE_PATCH` deleting the NPC. The client delays applying the deletion to the local game state until the animation completes.

---

### 10.10 Combat Rendering

Additional canvas elements rendered only when `GameState.combat.active == True`.

#### Active Combatant Glow

The current combatant (`turn_queue[current_index]`) has a bright white outer glow on their sprite:
- Draw a rectangle (or circle for friendly NPCs) 4px larger on all sides than the normal sprite bounding box.
- Stroke only (no fill): `#ffffff`, width 3px, `dash=(4,2)` animated (offset shifts by 1 each frame to create a "marching ants" effect).

#### Valid Movement Highlight (during player or DM-NPC turn, before movement used)

When it is the active combatant's turn and `has_moved == False`:
- Compute the 4 orthogonal cells adjacent to the combatant's position that are valid movement targets (walkable, unoccupied by other players/NPCs/closed doors).
- Draw a semi-transparent light-blue rectangle over each: `canvas.create_rectangle(..., fill="#3399ff", stipple="gray25", outline="#3399ff")`.

#### Action Range Highlight (after player selects an action from the menu)

When the player has selected an action and is choosing a target:
- Compute `cells_in_range(origin, action.Range, state, los_max)` (§10.8).
- Filter to cells that contain a valid target (NPC for damage actions; PlayerObject or friendly NPC for healing actions).
- Draw a semi-transparent red-orange rectangle over each valid target cell: `fill="#ff4400"`, `stipple="gray25"`.
- Player clicks a highlighted cell to confirm the action. Pressing ESC cancels action selection.

#### Turn Order Panel

A vertical strip rendered as a floating `tk.Frame` (or `canvas.create_window`) on the **right side** of the game canvas during combat:

```
┌────────────────────┐
│  ⚔  COMBAT  Rd 1  │
│  ──────────────    │
│ ▶ [■] PlayerA   12 │  ← active (accent bg)
│   [■] Goblin 1  8  │
│   [■] PlayerB   7  │
│   [■] OrcGuard  4  │
│  ──────────────    │
│  [End Turn]        │  ← visible only to active PC/DM-NPC
└────────────────────┘
```

- Each row: coloured square (`assigned_colors` for players; dark-red for hostile NPC; dark-green for friendly NPC), name (truncated to 10 chars), initiative value.
- Active combatant row: highlighted with accent background colour (`#2f7ee0`).
- "End Turn" button: shown at the bottom to the active PC only (or the DM when it's an NPC's turn).
- Panel width: 160px; height: auto (fits queue + header). Scrollable if queue > 8 entries.

#### Combat Mode HUD Additions (DM only)

A **"Start Combat" / "End Combat" toggle button** is placed above the chat widget at the bottom-left of the game canvas:
- Outside combat: `"⚔ Start Combat"` in default button style.
- Inside combat: `"■ End Combat"` in danger button style.
- Visible only to the DM's client.

An **encounter list badge** (small pill label) next to the button shows `"N in encounter"` where N is `len(combat.encounter_npc_ids)`, so the DM can track how many NPCs have been added before starting.

---

## 11. Host (Dungeon Master) Capabilities

### 11.1 Tile Management

**Left click on empty/black grid cell**: creates `Cell(walkable=True, protected=False)`. Sends `DM_TILE_SET: {cell, walkable: true}`.

**Right click on a walkable tile**: opens a `tk.Menu` context menu. Available options depend on cell state:

| Condition | Options shown |
|---|---|
| No occupant, no players | "Spawn Object", "Delete Tile" (if not protected) |
| Has NPC/Item/Door occupant | "Modify Object", "Delete Object", "Delete Tile" (if not protected) |
| Has player(s) | "Spawn Object" greyed out if occupant; DM player options below |
| Protected cell | "Delete Tile" absent entirely |

**"Delete Tile"** (non-protected only):
- Removes walkable tile and its occupant.
- Any PlayerObject(s) on the cell are moved to the nearest walkable unoccupied adjacent cell (BFS).
- Sends `DM_TILE_SET: {cell, walkable: false}`.

**Spawn area protection**: Cells `(x, y)` for `x in [0,3], y in [0,3]` have `protected=True`. "Delete Tile" is never shown or sent for these cells. Their tiles are permanently walkable. Objects and players can still be placed/removed on protected cells normally.

### 11.2 Warp Players

Context menu option **"Warp Players"** appears when the DM right-clicks on a walkable tile that belongs to a **connected region of ≥ 16 walkable tiles** (4×4 or more contiguous tiles reachable by BFS from the clicked cell).

**Warp flow:**
1. BFS flood-fill from clicked cell, collecting all connected walkable cells in the component.
2. If component size < number of connected players: show `messagebox.showwarning("Not enough space", "Need at least N unoccupied tiles.")`. Abort.
3. Randomly shuffle the unoccupied cells in the component. Assign one unique cell per player.
4. Send `DM_WARP_PLAYERS: {target_cells: [[x1,y1], [x2,y2], ...]}` (ordered by UUID for determinism).
5. Server updates `players_at` for all affected players, broadcasts `STATE_PATCH`.
6. Server sends `CAMERA_CENTER: {cell: [x, y]}` to each warped player's client.
7. Each warped player's `GameCanvas` centres its viewport on the received cell.

### 11.3 Spawn Object Dialog

`SpawnObjectDialog` (and `ModifyObjectDialog` which pre-populates from existing data) uses a tabbed or sectioned form layout.

**Type selector**: radio buttons (NPC / Item / Door) at the top. Switching type replaces the fields below.

#### NPC Fields

| Field | Widget | Default | Notes |
|---|---|---|---|
| Name | Entry | `""` | Required |
| Description | Text (3 lines) | `""` | |
| Level | Spinbox 1–99 | `1` | Changing Level triggers HP pre-fill recalc |
| Size | Combobox | `"Medium"` | Choices from HEALTH_SIZE_LOOKUP keys |
| Hostile | Checkbutton | `True` | |
| MaximumHP | Spinbox 1–99999 | auto (formula) | DM may override; changes when Level/Size/Con change |
| CurrentHP | Spinbox 1–99999 | == MaximumHP | DM may set lower at spawn (e.g. wounded NPC) |
| Str/Dex/Con/Int/Wis/Cha | 6 Spinboxes | `0` each | Live clamping enforced |

When any stat spinbox changes, if `Con` changed: recalculate and update the MaximumHP pre-fill (but do not write it until the DM confirms). Show the formula-derived value in grey as a placeholder; the DM can override.

#### Item Fields

| Field | Widget | Default | Notes |
|---|---|---|---|
| Name | Entry | `""` | Required |
| Description | Text (3 lines) | `""` | |
| Level | Spinbox | `1` | |
| Consumable | Checkbutton | `False` | |
| Quantity | Spinbox 1–9999 | `1` | |
| Value | Spinbox 0–999999 | `0` | |
| Equipment Slot | Combobox | `(none)` | Optional; choices from `EQUIPMENT_SLOTS` |
| Has Stats | Checkbutton | `False` | Reveals 6 stat spinboxes |
| Stats (if enabled) | 6 Spinboxes | `0` | Optional; clamping applied |
| Has Scalars | Checkbutton | `False` | Reveals scalar editor |
| Scalars (if enabled) | Per-stat Combobox | — | Each STAT_KEY gets a Combobox: S/A/B/C/F/None |
| Has Actions | Checkbutton | `False` | Reveals action list |
| Actions (if enabled) | List + "Add Action" btn | `[]` | See below |

**Per-action inline form** (each row in the action list):
- Action Name: Entry (becomes the dict key)
- Description: Entry
- Range: Spinbox 0–99
- BaseDamage: Spinbox −99999–99999
- Hits: Spinbox 1–99
- "×" button removes that row

#### Door Fields

| Field | Widget | Default |
|---|---|---|
| Open | Checkbutton | `False` |
| Broken | Checkbutton | `False` |
| Locked | Checkbutton | `False` |

**Spawn button**: validates required fields (Name required for NPC/Item). Generates UUID4 for `id` (server overwrites with its own UUID for security). Sends `DM_SPAWN_OBJECT`. Closes dialog.

**Cancel button**: closes dialog, no action, discards all field values.

### 11.4 Modify Object

Right-click → "Modify Object" opens `ModifyObjectDialog` (same widgets as spawn, pre-populated). On confirm: sends `DM_MODIFY_OBJECT`. The DM can modify **any** field of an already-spawned object, including `MaximumHP`, `CurrentHP`, `Hostile`, all stats, all item metadata, and door state.

### 11.5 Drag and Drop

The DM drags objects by holding left-click on an occupied cell and moving the mouse.

- **Drag start**: record `drag_source_cell` and object reference. Render a semi-transparent ghost sprite following the cursor.
- **Drag end** (mouse release):
  - If target cell is **valid** (walkable, no conflicting occupant, no player for NPC/Item/Door moves):
    - Send `DM_MOVE_OBJECT: {from_cell, to_cell}`.
    - Server validates, updates `grid` and `players_at` (if moving a PlayerObject), broadcasts `STATE_PATCH`.
    - If dragged object was a PlayerObject: server also sends `CAMERA_CENTER: {cell: to_cell}` to that player.
  - If target cell is **invalid** (not walkable, already occupied, or outside grid):
    - Cancel drag entirely. No server message sent. Object stays at `drag_source_cell`. Ghost sprite removed.
- The drag ghost is rendered in the animation layer (step 8 of render loop), after all other sprites.

### 11.6 DM Right-Click on Player

Right-clicking on a cell containing a PlayerObject opens a context menu:

- **"Level Up"**: sends `DM_LEVEL_UP_PLAYER`. Server: `player.Level += 1`, recalculates `MaximumHP`, sets `CurrentHP = MaximumHP`, re-validates stats, broadcasts `STATE_PATCH` and `CAMERA_CENTER` (camera stays; just forces stat update on player's view).
- **"Modify Player"**: opens `ModifyObjectDialog`-style form pre-populated with the PlayerObject's editable fields (Stats, Level, CurrentHP, MaximumHP). DM changes are sent via `DM_MODIFY_PLAYER`. HP rules from §4.6.1 are enforced server-side.
- **"Options"**: opens `DmOptionsDialog` with:
  - **"Disconnect"**: `DM_KICK_PLAYER`. Server records 1-minute temp-ban in `banlist.json`, sends `YOU_WERE_KICKED`, disconnects.
  - **"Ban"**: `DM_BAN_PLAYER`. Server records permanent ban in `banlist.json`, sends `YOU_WERE_KICKED`, disconnects.

---

### 11.7 Encounter Management

The DM builds an **encounter list** — the set of NPCs that will participate in the next combat — by right-clicking NPCs on the canvas.

**DM right-click on NPC context menu additions:**

| Option | When shown | Behaviour |
|---|---|---|
| `"Add To Encounter"` | NPC not in `encounter_npc_ids` | Sends `DM_ADD_TO_ENCOUNTER`. Server appends NPC UUID to `encounter_npc_ids`, broadcasts `STATE_PATCH`. |
| `"Remove From Encounter"` | NPC already in `encounter_npc_ids` | Sends `DM_REMOVE_FROM_ENCOUNTER`. Server removes, broadcasts. |
| `"Actions"` | Always | Opens NPC Action sub-menu (§11.8). |

The encounter list persists through End Combat → Start Combat cycles. If an NPC in the encounter list is deleted while the list is active, remove its ID from `encounter_npc_ids` server-side at the time of deletion.

**"Start Combat" button** (DM only, above chat widget):

1. Server collects all combatants:
   - All currently connected `PlayerObject` entries (all players participate automatically).
   - All NPCs whose UUIDs are in `encounter_npc_ids`.
2. Roll initiative for each:
   ```python
   import random
   initiative = max(combatant.Stats.get("Dex", 0) - 20, 0) + random.randint(1, 20)
   ```
3. Build `turn_queue: List[CombatTurn]` sorted **descending** by `initiative`. Ties broken randomly.
4. Set `CombatState.active = True`, `round_number = 1`, `current_index = 0`.
5. Broadcast `COMBAT_STARTED: {turn_queue: [...], round: 1}` to all clients.
6. All clients render the Turn Order Panel (§10.10) and restrict movement to combat rules.

**"End Combat" button** (DM only):

1. Server sets `CombatState.active = False`, clears `turn_queue`, resets `current_index = 0`.
2. Does **not** clear `encounter_npc_ids` — the DM can restart combat with the same encounter.
3. Broadcasts `COMBAT_ENDED` to all clients.
4. All clients remove the Turn Order Panel and return to free-move.

**Turn advancement** (server-side, triggered by `PLAYER_END_TURN` or `DM_NPC_END_TURN`):

```python
def advance_turn(combat: CombatState) -> CombatTurn:
    combat.current_index = (combat.current_index + 1) % len(combat.turn_queue)
    if combat.current_index == 0:
        combat.round_number += 1
    current = combat.turn_queue[combat.current_index]
    current.has_moved = False
    current.has_acted = False
    return current
```

Server broadcasts `COMBAT_TURN_ADVANCED: {current: CombatTurn dict, queue: [...], round: int}`.

If the advancing combatant is an NPC: the server additionally sends `CAMERA_CENTER: {cell: [x,y]}` to the **DM's client** so the DM viewport jumps to the NPC.

---

### 11.8 DM NPC Actions (combat and general play)

The DM can use NPC actions both **outside combat** (for flavour, scripted events) and **during combat** (as the NPC's turn action).

**Context menu "Actions" on an NPC** opens a sub-menu listing:
- `"Default Attack"` — always present, uses the NPC's own damage formula (§14.2 with NPC as combatant).
- Each key in `NPC.Actions` (if not None) — listed by action name.

Clicking an action enters **target selection mode**:
- Canvas highlights valid target cells (same logic as player action targeting, §10.10, but originating from the NPC's cell).
- DM clicks a highlighted cell to confirm. Sends `DM_NPC_ACTION: {npc_id, action_name, target_id, target_cell}`.
- Server resolves using the NPC as attacker (§14.2, §14.3). `enemy_damage_multiplier` applies when the NPC damages a PlayerObject.

**During combat, on an NPC's turn:**
- DM may additionally move the NPC 1 tile using WASD or by left-clicking an adjacent valid cell. Sends `DM_NPC_MOVE`. Server validates exactly 1 tile, walkable, unoccupied. Marks `has_moved = True`.
- DM uses the "Actions" sub-menu as above. After action resolves, marks `has_acted = True`.
- When both resources are used, the "End NPC Turn" button in the Turn Order Panel becomes highlighted. DM may click it at any time to advance (early end of turn is valid).
- If the active NPC is killed during its own turn (e.g. reaction damage — future feature), treat it as DM_NPC_END_TURN and remove from queue.

**NPC spawn dialog additions** (§11.3) for `Scalars` and `Actions`:
- Same widgets as the Item Scalars and Actions sections.
- "Has Scalars" checkbutton → reveals per-stat grade comboboxes.
- "Has Actions" checkbutton → reveals the action list builder (Name, Description, Range, BaseDamage, Hits rows with "×" delete).

---

## 12. Player Capabilities

### 12.1 Movement

A PC may move to an **orthogonally adjacent cell** (up/down/left/right only) that is:
- `walkable=True`.
- Not occupied by another PlayerObject.
- Not occupied by an NPC.
- Not a Door with `Open=False`.

Triggers: **WASD** keys, or **left-click** on an adjacent walkable cell.

Client sends `PLAYER_MOVE: {target_cell: [x, y]}`. Server validates and broadcasts `STATE_PATCH`.

### 12.2 Adjacent Cell Interactions (PC left-click)

A PC may left-click any **adjacent cell** (all 8 directions — orthogonal and diagonal — for interaction purposes) to trigger context interactions. The cell must contain an occupant or player.

#### Door (adjacent)

Opens `DoorInteractionDialog` (`tk.Toplevel`):

```
┌────────────────────────────────┐
│  Door                          │
│  ──────────────────────────    │
│  [Open] or [Close]             │
│  (disabled if Broken=True)     │
└────────────────────────────────┘
```

- `Broken=True`: button disabled regardless of Open state.
- `Locked=True`, action = "Open": sends `DOOR_INTERACT: {action: "open"}`. Server rejects the open action and sends `CHAT_RECV` (type `system`) routed only to the requesting client. Client displays a **text bubble** above the door's canvas position saying `"The door is locked."` (3s duration). No state change.
- `Locked=True`, action = "Close": door closes normally; server sets `Open=False, Locked=False`.
- `Locked=False`: normal open/close toggle.

**Door text bubble**: displayed in the canvas animation layer centred above the door sprite's cell. Uses the same bubble rendering as chat bubbles (§10.6), with white text and dark background.

#### NPC (adjacent)

Opens a `tk.Menu` context menu:
- **"Inspect"**: shows `ObjectTooltip` with `Name`, `Description`.
- **"Action"**: opens a sub-menu listing available actions (see §14.1 for action source). Each action is a button. Clicking sends `PLAYER_ACTION`.

#### Item (adjacent)

Context menu:
- **"Pick Up"**: sends `ITEM_PICKUP: {cell, item_id}`. Server validates, moves item to player `Inventory`, broadcasts `STATE_PATCH`.
- **"Inspect"**: shows `ObjectTooltip` with `Name`, `Description`, `Quantity`, `Value`.

#### Player (adjacent)

Context menu:
- **"Inspect"**: shows `PlayerStatsTooltip` with `Name`, `CurrentHP/MaximumHP`, effective Stats (base + equipment).

### 12.3 ESC Menu

Pressing **ESC** opens a small `tk.Toplevel`:

| Button | PC behaviour | DM behaviour |
|---|---|---|
| "Main Menu" | Send `DISCONNECT`, stop `GameClient`, go to `MainMenuScreen` | Same |
| "Quit" | Send `DISCONNECT`, stop `GameClient`, `app.on_quit()` | Same |
| "Game Settings" | Not available | Opens `GameSettingsDialog` (§18.2) |
| "Save & Quit" | Not available | See §17.2 |

### 12.4 TAB — Player List Overlay

Pressing **TAB** toggles `PlayerListOverlay` (a semi-transparent floating panel):

```
┌────────────────────────────────────────────┐  85% opacity black bg
│  Connected Players (N)                     │
│  ──────────────────────────────────────    │
│  [■ color] [avatar 20px] Alias      HOST   │
│  [■ color] [avatar 20px] Alias       12ms  │
│  [■ color] [avatar 20px] Alias       45ms  │
└────────────────────────────────────────────┘
```

- Coloured square: player's `assigned_colors` value.
- Avatar: 20×20 scaled PNG if available; blank square otherwise.
- Latency: from last PING/PONG round-trip. Host entry shows `"HOST"`.

Pressing TAB again closes the overlay.

### 12.5 B — Inventory

Pressing **B** opens `InventoryDialog`. See §15.

### 12.6 C — Stats View

Pressing **C** opens `PlayerStatsDialog`:

```
┌──────────────────────────────────────────┐
│  <PlayerAlias> — Level <N>               │
│  HP:  <CurrentHP> / <MaximumHP>          │
│  Size: <Size>                            │
│  ────────────────────────────────────    │
│  STR    8   (+2 equip bonus) = 10        │
│  DEX   10   (+0 equip bonus) = 10        │
│  CON   12   (+1 equip bonus) = 13        │
│  INT    6   (+0 equip bonus) = 6         │
│  WIS    9   (+0 equip bonus) = 9         │
│  CHA    7   (+0 equip bonus) = 7         │
│  ────────────────────────────────────    │
│  Base total: 52 / 85 (max at Level N)    │
│                                          │
│  [ Edit Stats ]                          │
└──────────────────────────────────────────┘
```

- Equipment bonuses = sum of `item.Stats.get(key, 0)` for each item in `Equipment.values()` where `item.Stats is not None`. Displayed inline as `(+N equip bonus)` per stat; 0-bonus stats show just the base value.
- Players **cannot** edit `HP` or `Size` from this view.

#### "Edit Stats" sub-view

Replaces or expands the stat rows with Spinboxes pre-filled with current base values:
- Each Spinbox bounded `[0, MAX_INDIVIDUAL(Level)]`, clamping applied live.
- Running total displayed below: `"Total: N / MAX_TOTAL(Level)"`.
- **"Confirm"** button: validates via `clamp_stats()`, sends `STATS_UPDATE: {stats: dict}`. Server re-validates, broadcasts `STATE_PATCH`.
- **"Reset"** button: reverts all Spinboxes to saved values. No server message sent.
- Until "Confirm" is pressed, no server message is sent.

### 12.7 ENTER — Chat Focus

Pressing **ENTER** focuses the `ChatWidget`'s text entry field. Pressing **ENTER** again after typing sends the message. Pressing **ESC** while the chat input is focused blurs it without sending.

### 12.8 HP Rules (PC perspective)

- Players cannot edit `CurrentHP` or `MaximumHP` directly.
- `MaximumHP` changes only when: Level Up, DM Modify Player, or Con stat changes.
- `CurrentHP` changes when: Level Up (→ MaxHP), DM Modify Player, Con stat changes (§4.6.1), or combat damage/healing.

---

### 12.9 Combat Turn Actions (PC)

When `GameState.combat.active == True` and it is this player's turn (`turn_queue[current_index].id == self.uuid`):

**Movement resource** (`has_moved == False`):
- WASD or left-click on an adjacent valid cell moves the player **1 tile** and marks `has_moved = True`.
- Server validates same rules as free-move (walkable, unoccupied) but also enforces the 1-tile limit.
- The 4 valid adjacent cells are highlighted in light blue on the canvas (§10.10).

**Action resource** (`has_acted == False`):
- Left-clicking an adjacent NPC opens the "Action" context menu (§12.2) with all available actions.
- For actions with `Range > 1`: after selecting the action, the canvas highlights valid target cells in range + LOS. Player left-clicks a target cell to confirm. ESC cancels action selection.
- On a resolved action, server marks `has_acted = True` and broadcasts `COMBAT_RESOURCES_USED`.

**Movement and action may be used in any order** on the player's turn (move then act, act then move, or one without the other).

**End Turn**: player sends `PLAYER_END_TURN` when they are done. This can be explicit (clicking "End Turn" in the Turn Order Panel) or automatic when both `has_moved` and `has_acted` are `True` and the player right-clicks elsewhere. The "End Turn" button is always clickable once it's the player's turn (allows forfeiting unused resources).

**While NOT the active combatant:**
- WASD, left-click movement: rejected server-side with a `CHAT_ERROR` "It is not your turn." displayed locally.
- Viewing inventory (B), stats (C), player list (TAB), and chat (ENTER) remain available at all times during combat.

---

## 13. Object System

### 13.1 Server-Side Authority

All object mutations are server-authoritative. Sequence:
1. Client or DM sends a message.
2. Server validates; mutates `GameState`.
3. Server broadcasts `STATE_PATCH` to all clients.
4. Clients apply patch to their local `GameState` copy.

The host's local UI may optimistically render DM changes immediately (no network RTT on localhost), but must reconcile with the patch if it differs.

### 13.2 Object IDs

The server generates a fresh `uuid4()` for every spawned NPC, Item, and Door, overwriting any `id` sent by the client. `PlayerObject.id == player_uuid` from `user.config`.

---

## 14. Combat & NPC Interactions

### 14.1 Available Actions

When a PC clicks "Action" on an adjacent NPC, the action sub-menu is populated with:

1. **Default "Attack"** — always present. Uses the formula in §14.2 with `BaseDamage=0, Scalars=None` (pure stat-only damage: `Str + Level`). See §14.2 edge case.
2. **Item actions** — all `ItemAction` entries from every `Item` in `player.Equipment.values()` where `item.Actions is not None`. Listed by action name. Clicking sends `PLAYER_ACTION: {action_name, item_id, target_id, target_cell}`.

Action targeting:
- `Range = 0`: self-targeting (no NPC target required; used for buffs/self-heals).
- `Range = 1`: adjacent NPC or player cell only. The context menu only shows the action if the target cell is adjacent.
- `Range > 1`: any cell within Euclidean distance ≤ Range AND within LOS (§10.8). For range > 1 actions, clicking "Action" → action name opens a target-selection mode: the canvas highlights valid cells; the player then left-clicks a target cell.

### 14.2 Damage Formula

The damage formula is **combatant-agnostic** — it accepts either a `PlayerObject` or an `NPC` as the attacker. Both share the same stat system.

```python
import math
from typing import Union

SCALAR_WEIGHT_LOOKUP = {"S": 1.00, "A": 0.70, "B": 0.45, "C": 0.15, "F": 0.05}

CombatantType = Union["PlayerObject", "NPC"]

def default_attack_damage(combatant: CombatantType) -> int:
    """
    Default unarmed/no-action attack: uses the higher of Str or Dex,
    applies above-20 scaling, plus level bonus.
    Shared between players and NPCs.
    """
    dex  = combatant.Stats.get("Dex", 0)
    str_ = combatant.Stats.get("Str", 0)
    return max(max(dex, str_) - 20, 0) + math.ceil(combatant.Level * 1.5)


def calculate_damage(combatant: CombatantType,
                     scalars:   Optional[Dict[str, str]],
                     action:    Optional[dict]) -> int:
    """
    Returns net damage for ONE hit (before Hits multiplier).
    Positive = damage; negative = healing.

    scalars: the attacker's Scalars dict (from Item.Scalars or NPC.Scalars).
    action:  the ItemActionDict being used, or None for default attack.
    """
    if action is None:
        return default_attack_damage(combatant)

    base = action.get("BaseDamage", 0)
    active_scalars = scalars or {}

    scalar_total = sum(
        math.ceil(
            max(combatant.Stats.get(stat, 0) - 20, 0)
            * (1 + SCALAR_WEIGHT_LOOKUP.get(weight, 0))
        )
        for stat, weight in active_scalars.items()
    )
    return scalar_total + base


def apply_action(combatant: CombatantType,
                 scalars:   Optional[Dict[str, str]],
                 action:    Optional[dict],
                 target:    CombatantType,
                 settings:  "GameSettings") -> int:
    """
    Returns total damage after Hits multiplier and enemy_damage_multiplier.
    Negative = healing.

    enemy_damage_multiplier applies only when the attacker is an NPC
    and the target is a PlayerObject (i.e. the enemy is damaging a player).
    """
    hits         = (action or {}).get("Hits", 1)
    dmg_per_hit  = calculate_damage(combatant, scalars, action)
    total        = dmg_per_hit * hits

    npc_to_player = (
        isinstance(combatant, NPC)
        and isinstance(target, PlayerObject)
        and total > 0
    )
    if npc_to_player:
        total = math.ceil(total * settings.enemy_damage_multiplier)
    return total
```

**Caller conventions:**
- Player using equipped item action: `apply_action(player, item.Scalars, action_dict, target, settings)`
- Player using default attack: `apply_action(player, None, None, target, settings)`
- DM using NPC action: `apply_action(npc, npc.Scalars, action_dict, target, settings)`
- DM using NPC default attack: `apply_action(npc, None, None, target, settings)`

**Healing (negative total):**
- `abs(total)` is added to `target.CurrentHP`, capped at `target.MaximumHP`.
- Valid healing targets: any entity in range (players and NPCs).

### 14.3 Attack Resolution (server-side)

On receiving `PLAYER_ACTION`:

1. Validate: target exists at target cell; cell is within action Range of player; player has the item equipped (if `item_id` provided).
2. Calculate `total = apply_action(...)`.
3. If `total >= 0` (damage):
   a. `target.CurrentHP = max(0, target.CurrentHP - total)`.
   b. If target is an NPC and `target.CurrentHP <= 0`:
      - Remove NPC from `GameState.grid[cell].occupant`.
      - Broadcast `STATE_PATCH` (delete NPC).
      - The client plays the death animation (§10.9); the state patch application is deferred client-side until the animation completes.
   c. If target is NPC, `CurrentHP > 0`, and `Hostile was False`:
      - Set `Hostile = True`.
      - Broadcast `STATE_PATCH` updating NPC.
      - Client re-renders hostile sprite.
4. If `total < 0` (healing):
   - `target.CurrentHP = min(target.MaximumHP, target.CurrentHP + abs(total))`.
5. Broadcast `STATE_PATCH` with updated target HP.

---

### 14.4 DM NPC Attack Resolution (server-side)

On receiving `DM_NPC_ACTION`:

1. Validate: DM is sender (`is_host`); NPC exists; target exists at target cell; target cell is within action's `Range` of the NPC's cell.
2. If `action_name == "Default Attack"` or not in `NPC.Actions`: use `apply_action(npc, None, None, target, settings)`.
3. Else: look up `action_dict = npc.Actions[action_name]`; call `apply_action(npc, npc.Scalars, action_dict, target, settings)`.
4. Apply damage/healing identically to §14.3 steps 3–5.
5. If in combat (`combat.active`): mark `npc_turn.has_acted = True`; broadcast `COMBAT_RESOURCES_USED`.

---

## 15. Inventory & Equipment System

### 15.1 Inventory Dialog (B key)

`InventoryDialog` — `tk.Toplevel`:

```
┌──────────────────────────────────────┐
│  Inventory — <PlayerAlias>           │
│  ────────────────────────────────    │
│  ┌────┬────┬────┬────┬────┐          │
│  │ [I]│ [I]│    │    │    │          │  ← 5 columns, 64×64px cells
│  ├────┼────┼────┼────┼────┤          │
│  │    │    │    │    │    │          │
│  └────┴────┴────┴────┴────┘          │
│  (scrollable vertically)             │
└──────────────────────────────────────┘
```

Items from `player.Inventory` fill left-to-right, top-to-bottom. Cells are 64×64px with a `#2e2e4a` border. Item sprites are drawn scaled to fit the cell (same drawing routines as canvas, scaled).

**Hover**: show tooltip overlay with `Name`, `Description`, `Quantity`.

**Right-click on item cell**: context menu:
- `"Use"` (if `Consumable=True`) **or** `"Equip"` (if `Consumable=False`)
- `"Drop"`
- `"Discard"`

#### Use (Consumable=True)
Client sends `ITEM_USE: {item_id}`. Server removes item from `player.Inventory`, broadcasts `STATE_PATCH`. Client displays text bubble above player sprite: `"<Name> used <ItemName>"` (3s, white text).

#### Equip (Consumable=False)
Client sends `ITEM_EQUIP: {item_id}`. Server:
- Places item in `player.Equipment[item.EquipmentSlot]`.
- If that slot was occupied: previous item moved back to `Inventory`.
- Removes item from `Inventory`.
- Does **not** modify `player.Stats` — equipment bonuses are display-only modifiers.
- Broadcasts `STATE_PATCH`.

If `item.EquipmentSlot is None`: show `messagebox.showwarning("Cannot equip", "This item has no equipment slot defined.")`. No server message.

#### Drop
Client sends `ITEM_DROP: {item_id}`. Server BFS search for placement:
1. Check 4 orthogonal neighbours of player's cell.
2. Expand radius by 1 each iteration.
3. First cell found that is `walkable`, `occupant is None`, and has no players: place item as new object.
4. Remove from `player.Inventory`.
5. Broadcast `STATE_PATCH`.

#### Discard
Local `ConfirmDialog`: `"Are you sure you would like to discard <ItemName>?"` with "Yes" / "No".
- **Yes**: sends `ITEM_DISCARD: {item_id}`. Server removes from `Inventory`, broadcasts.
- **No**: dialog closes, nothing happens.

### 15.2 Effective Stats Display

Wherever player stats are shown (hover tooltip, C-key view), use:

```python
def effective_stat(player: PlayerObject, key: str) -> int:
    base = player.Stats.get(key, 0)
    bonus = sum(
        item.Stats.get(key, 0)
        for item in player.Equipment.values()
        if item.Stats is not None
    )
    return base + bonus
```

Display format: `"STR   8   (+2 equip bonus) = 10"`. If `bonus == 0`: `"STR   8"`.

---

## 16. Chat System

### 16.1 ChatWidget (`ui/chat_widget.py`)

A floating widget placed over the bottom-left of `GameScreen`:
- Fixed dimensions: **300px wide × 150px tall**.
- Background: `#000000` at ~85% apparent opacity (use a `tk.Frame` with `bg="#000000"`, placed via `place()` over the canvas).
- Message display: `tk.Text`, `state=DISABLED`, `bg="#000000"`, `fg="#e6e6f0"`, no border, no highlight ring, wrapping enabled.
- Scroll: `tk.Scrollbar` (vertical) linked to Text widget. Auto-scroll to bottom on new message unless user has scrolled up manually (detect via scrollbar position).
- Text input: `tk.Entry` visible at the bottom of the widget, always rendered. Focused by ENTER; blurred by ESC or after sending.

### 16.2 Text Tags

```python
TAG_COLOURS = {
    "normal":      "#e6e6f0",   # White-ish
    "yell":        "#cc6600",   # Burnt orange
    "whisper_out": "#9090cc",   # Muted blue (sender's view)
    "whisper_in":  "#9090cc",   # Same colour (receiver's view)
    "system":      "#888888",   # Grey
    "error":       "#cc3333",   # Red
}
```

Configure on the `tk.Text` widget at init:
```python
for tag, color in TAG_COLOURS.items():
    text_widget.tag_configure(tag, foreground=color)
```

Appending a message:
```python
text_widget.config(state=tk.NORMAL)
text_widget.insert(tk.END, formatted_text + "\n", tag_name)
text_widget.config(state=tk.DISABLED)
text_widget.see(tk.END)   # only if auto-scroll is active
```

### 16.3 Message Formats

| msg_type | Sender display | Receiver display | Bubble shown |
|---|---|---|---|
| `normal` | `<Alias>: <message>` white | Same to all | Above sender's sprite (all clients) |
| `yell` | `<Alias> yells: <message>` orange | Same to all | Above sender's sprite (all clients), orange |
| `whisper` | `[To <Alias>]: <message>` blue | `[<SenderAlias>]: <message>` blue | Above RECEIVING player's sprite (receiver's client only) |
| `system` | `<message>` grey | — | None |
| `error` | `<message>` red | — | None |

**Whisper routing**: Server receives `CHAT_SEND` (type `whisper`, `recipient_alias`). Server looks up the player UUID for the alias (case-insensitive). If not found: server sends `CHAT_RECV` (type `error`, text `"That player does not exist."`) **only to the sender**. If found: sends `CHAT_RECV` to sender (format `[To <alias>]: <message>`) and to recipient (format `[<SenderAlias>]: <message>`). The host does **not** receive whispers as a third-party — whispers are not visible to the host unless the host is the sender or recipient.

### 16.4 Chat Commands (parsed client-side before send)

| Input pattern | Action |
|---|---|
| Any text not starting with `/` | Normal message |
| `/y <message>` | Yell message |
| `/w <alias> <message>` | Whisper to alias (case-insensitive) |
| `/as <NPC.Name> <message>` | DM only: speak in chat as the named NPC (normal msg) |
| `/as <NPC.Name> -y <message>` | DM only: yell as the named NPC |
| `/as <NPC.Name> -w <RecipientAlias> <message>` | DM only: whisper as the named NPC to a recipient |
| `/help` | Client-side only; print help text to chat in `system` colour |

`/help` output (printed locally as system messages, not sent to server):
```
/y <msg>                          — Yell (visible to all, burnt orange)
/w <alias> <msg>                  — Whisper to player (private)
/as <NPC> <msg>                   — Speak as NPC [DM only]
/as <NPC> -y <msg>                — Yell as NPC [DM only]
/as <NPC> -w <alias> <msg>        — Whisper as NPC [DM only]
/help                             — Show this help
```

**`/as` NPC name lookup**: client searches all `NPC` occupants in `GameState.grid` for a case-insensitive exact match on `NPC.Name`. If not found: show `CHAT_ERROR` locally: `"No NPC named '<name>' found."`. If found: send `DM_CHAT_AS_NPC: {npc_id, content, msg_type, recipient_alias}`.

**Tab autocomplete in chat input:**
- If the entry starts with `/`, pressing Tab cycles through matching command prefixes: `/y`, `/w`, `/as`, `/help`.
- For `/w <partial_alias>` and `/as <partial_NPC.Name>`, pressing Tab completes against current players or NPC names respectively (case-insensitive prefix match).
- If a single match exists, complete it. If multiple, cycle alphabetically.

### 16.5 Chat Persistence

`GameState.chat_history` stores all messages **except** `msg_type == "whisper"`. `/as` NPC messages are saved as normal/yell messages with `sender_alias = NPC.Name`. On game load, all history messages are replayed into `ChatWidget` in order.

---

### 16.6 DM NPC Chat Impersonation

#### General play: `/as` command

Client parses the `/as` prefix and sends `DM_CHAT_AS_NPC` to the server.

Server handling:
1. Validate `is_host` and that the NPC exists.
2. Look up NPC `Name` from `npc_id`.
3. Build `ChatMessage` with `sender_alias = NPC.Name`, `sender_uuid = "NPC:<npc_id>"`.
4. Route based on `msg_type`:
   - `"normal"`: broadcast to all clients.
   - `"yell"`: broadcast to all clients with yell formatting.
   - `"whisper"`: route only to sender (DM) and `recipient_alias` target.
5. Include `npc_cell: [x, y]` in the `CHAT_RECV` payload so clients know where to render the bubble.

Client rendering:
- Render a text bubble **above the NPC sprite** at the NPC's current cell (same bubble rendering as player chat bubbles, §10.6).
- The bubble uses the message's colour coding (white for normal, burnt orange for yell).
- For whisper `msg_type`: the bubble appears only on the recipient's client and the DM's client.

**The host (DM) does NOT receive `/as` whispers as a third-party observer**, consistent with normal whisper privacy rules — even though the server knows the NPC ID.

#### Combat: automatic NPC impersonation during NPC turns

When combat is active and the current turn belongs to an NPC (`turn_queue[current_index].combatant_type == "npc"`):

1. The DM's `ChatWidget` text entry displays a **prefix indicator** in grey text before the input field: `[As <NPC.Name>]`.
2. Any message the DM sends while in this state is automatically treated as `/as <NPC.Name> <message>` (normal) or `/as <NPC.Name> -y <message>` (if input starts with `/y`) or `/as <NPC.Name> -w <alias> <message>` (if input starts with `/w <alias>`).
3. Raw `/as` commands entered manually during NPC turn still work normally.
4. When the NPC's turn ends (`DM_NPC_END_TURN` confirmed), the prefix indicator is cleared and the DM's alias reverts.
5. If the DM presses ESC to blur the chat input during an NPC turn and opens the ESC menu or performs DM actions, the impersonation state is maintained until the turn ends.

**`DM_CHAT_AS_NPC` is the single message type** used for all NPC chat — whether sent via `/as` command, automatic turn impersonation, or the `/as` sub-flags. The `msg_type` field within it carries `"normal"`, `"yell"`, or `"whisper"`.

---

## 17. Save & Load System

### 17.1 Save File Naming

```
saves/<GameName>.sav               ← first save of a new game
saves/<GameName>_YYYYMMDD_HHMMSS.sav  ← all subsequent saves
```

- `<GameName>` sanitised: strip characters outside `[A-Za-z0-9_\- ]`, replace with `_`.
- Datetime: local time at save.
- Load Game dialog sorts by datetime component in filename, **newest first**. Files without a datetime suffix (original first save) are sorted by file `mtime`.

### 17.2 Save Format (`game/serialise.py`)

Format: **msgpack + zlib compression** (compact binary; not human-readable).

```python
import msgpack, zlib

def dump_state(state: GameState) -> bytes:
    d = state.to_dict()
    packed = msgpack.packb(d, use_bin_type=True)
    return zlib.compress(packed, level=9)

def load_state(data: bytes) -> GameState:
    packed = zlib.decompress(data)
    d = msgpack.unpackb(packed, raw=False)
    return GameState.from_dict(d)
```

**Serialisation notes:**
- Tuple grid keys `(x, y)` → serialised as string `"x,y"`. `from_dict` converts back.
- `bytes` values (avatar PNGs stored in `avatar_cache`) → base64-encoded strings in the dict, decoded back to bytes on load.
- All `@dataclass` objects implement `to_dict() -> dict` recursively. Nested objects are also dicts.
- `GameSettings` is serialised as a flat sub-dict under `"settings"`.

### 17.3 Save & Quit Flow (DM only)

DM presses ESC → "Save & Quit":

1. If `state.name == "Untitled"`: show an inline prompt: `"Game Name:"` Entry + Confirm. Sanitise input and set `state.name`.
2. Broadcast `CHAT_RECV` (type `system`, content `"Host is saving and closing the game. Disconnecting in 3 seconds."`) to all PCs.
3. `await asyncio.sleep(3)` (in server thread).
4. Send `YOU_WERE_KICKED: {reason: "Host has ended the session."}` to each PC.
5. Disconnect all clients.
6. Record `state.host_view` and `state.host_zoom` from the DM's current viewport.
7. Determine filename: if `saves/<GameName>.sav` does not exist → use it. If it does → use `saves/<GameName>_YYYYMMDD_HHMMSS.sav`.
8. Write `dump_state(state)` to the chosen path.
9. Stop `GameServer`. Navigate to `MainMenuScreen`.

### 17.4 Load Game Dialog (`dialogs/load_game_dialog.py`)

```
┌─────────────────────────────────────────────────────────────┐
│  Load Game                                                  │
│  ─────────────────────────────────────────────────────────  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  [btn]  Dungeon Name    │  PlayerA, PlayerB, PlayerC │   │
│  │  [btn]  Another Name   │  PlayerA                   │   │
│  │  ...                                                │   │
│  └─────────────────────────────────────────────────────┘   │
│  (scrollable list)                                          │
│                                                             │
│  [ Start (disabled) ]   [ Delete (disabled) ]               │
└─────────────────────────────────────────────────────────────┘
```

- Each row: wide horizontal button. Format: `"<GameName>   │   <alias1>, <alias2>, ..."`.
- Sorted newest-first (by datetime in filename; fallback: file mtime).
- Selecting a row highlights it and enables **Start** and **Delete**.
- **Start**: calls `load_state(file_bytes)`, starts `GameServer`, navigates to `GameScreen` (DM role). DM viewport restored to `state.host_view` / `state.host_zoom`.
- **Delete**: opens `ConfirmDialog` `"Delete '<GameName>'? This cannot be undone."`. On confirm: deletes the `.sav` file and reloads the save list.

---

## 18. Settings & Banlist

### 18.1 Gear Icon on Main Menu

A `⚙` icon (font size 14) as a `tk.Button` (or Label with binding) placed at the top-right corner of the `MainMenuScreen` frame. Clicking opens `BanlistDialog`.

### 18.2 Game Settings (DM ESC menu)

"Game Settings" in the DM's ESC menu opens `GameSettingsDialog`:

```
┌───────────────────────────────────────┐
│  Game Settings                        │
│  ─────────────────────────────────    │
│  HP Base Multiplier  [ 6.0 ]          │
│  Enemy Damage Mult.  [ 1.0 ]          │
│  LOS Max Distance    [  20 ]          │
│                                       │
│  [ Apply ]  [ Cancel ]                │
└───────────────────────────────────────┘
```

- Pre-populated with current `GameState.settings`.
- **Apply**: sends `DM_UPDATE_SETTINGS: {settings: {hp_base_multiplier, enemy_damage_multiplier, los_max_distance}}`. Server updates `GameState.settings`, recalculates MaximumHP for all existing NPCs and PlayerObjects, broadcasts `STATE_PATCH`.
- **Cancel**: no action.

Changing `hp_base_multiplier` mid-game:
- All NPC `MaximumHP` values are recalculated. `CurrentHP` is clamped to `min(CurrentHP, new MaximumHP)`.
- All PlayerObject `MaximumHP` values are recalculated. Same `CurrentHP` clamp.

### 18.3 Banlist Dialog (`dialogs/banlist_dialog.py`)

```
┌──────────────────────────────────────────────────────┐
│  Manage Banlist                                      │
│  ────────────────────────────────────────────────    │
│  Alias        UUID (short)    Banned At      [del]  │
│  ─────────    ───────────    ─────────────   ─────  │
│  PlayerA      xxxx-xxxx…     2024-01-01      [🗑]   │
│  PlayerB      yyyy-yyyy…     2024-02-15      [🗑]   │
│  (Expired)    zzzz-zzzz…     2024-01-01  *   [🗑]   │
│                                                      │
│  [ Close ]                                           │
└──────────────────────────────────────────────────────┘
```

- UUID shown truncated: first 8 chars + `"…"`.
- Expired temp-blocks marked with `*` and rendered in muted grey.
- Clicking 🗑 opens `ConfirmDialog`. On confirm: removes record from `banlist.json`, reloads table.

---

## 19. Keybindings Reference

| Key | Context | Action |
|---|---|---|
| `W` / `↑` | Game (PC) | Move player up |
| `A` / `←` | Game (PC) | Move player left |
| `S` / `↓` | Game (PC) | Move player down |
| `D` / `→` | Game (PC) | Move player right |
| `W A S D` / Arrows | Game (DM) | Pan viewport |
| Scroll wheel ↑ | Game | Zoom in (centred on cursor) |
| Scroll wheel ↓ | Game | Zoom out |
| Left click | Game (DM) on empty cell | Create walkable tile |
| Right click | Game (DM) on tile | Context menu |
| Left click | Game (PC) on adjacent cell | Move or interact |
| Right click | Game (DM) on player | DM player context menu |
| `TAB` | Game | Toggle Player List overlay |
| `B` | Game | Toggle Inventory |
| `C` | Game | Toggle Stats view |
| `ESC` | Game | Open ESC menu (PC) or DM ESC menu |
| `ESC` | Chat input focused | Blur chat input (no send) |
| `ENTER` | Game | Focus chat input |
| `ENTER` | Chat input focused | Send message |
| `Tab` | Chat input, after `/` | Autocomplete command or alias |
| `SPACE` | Game (PC, own combat turn) | End turn early (forfeit unused resources) |
| `SPACE` | Game (DM, NPC combat turn) | End NPC turn early |
| Left click | Canvas (PC, own combat turn, action selected) | Confirm action on highlighted cell |
| `ESC` | Action target selection mode | Cancel action selection |

---

## 20. Open Questions

All questions from v0.2.0 and v0.3.0 have been resolved. The answers are incorporated throughout the document. For reference, the resolutions:

| RQ | Resolution | Where implemented |
|---|---|---|
| RQ-01: Default attack formula | `max(max(Dex,Str)-20, 0) + ceil(Level*1.5)` | §14.2 `default_attack_damage()` |
| RQ-02: Player Size | Defaults `"Medium"`, DM-editable via "Modify Player" | §4.6, §11.6 |
| RQ-03: NPC attacks & combat | Full turn-based encounter system added | §4.12, §4.13, §10.10, §11.7, §11.8, §12.9, §14.4 |
| RQ-04: Equipment slots | Single Ring, single Trinket; 8 slots total; no expansion planned | §4.7 |
| RQ-05: Save migration | `GameSettings.from_dict` uses defaults for missing keys; show version warning on load | §17.2 |

### Remaining minor decision points

**RQ-06 — `/as -w` whisper recipient visibility**  
The `/as <NPC> -w <Alias> <msg>` whisper is visible to: the DM (as sender) and the recipient player only. The whisper is NOT saved to chat history. This mirrors standard `/w` behaviour. No ambiguity — confirmed.

**RQ-07 — Combat save/load resume**  
If a game is saved mid-combat (`combat.active == True`), loading that save resumes combat from the exact saved `CombatState` (same turn queue, same index, same resource states). If any player who was in the turn queue is no longer connected on load, their `CombatTurn` entry is removed from the queue and indices adjusted. The DM is warned if connected players differ from the saved state.

**RQ-08 — NPC death mid-own-turn**  
If a NPC is killed (e.g. by a reaction or DM direct-modify) while it is the active combatant in combat: remove it from `turn_queue`, advance the turn to the next combatant. Server handles this identically to killing any combatant, checking `current_index` against the removed element's position.

---

*End of Requirements Document v0.4.0*
