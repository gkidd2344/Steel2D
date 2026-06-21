# Steel2D — Full Technical Requirements
**Target audience:** Claude Code (automated implementation)  
**Version:** v0.15  
**Supersedes:** v0.14

---

## Table of Contents

1. [Overview](#1-overview)
2. [Technology Stack & Dependencies](#2-technology-stack--dependencies)
3. [Project Structure](#3-project-structure)
4. [Data Models](#4-data-models)
5. [Configuration & Persistence Files](#5-configuration--persistence-files)
6. [Network Architecture & Protocol](#6-network-architecture--protocol)
7. [Main Menu & Profile Screen](#7-main-menu--profile-screen)
8. [DM Workshop (Prefab System)](#8-dm-workshop-prefab-system)
9. [Game Canvas & Camera](#9-game-canvas--camera)
10. [Rendering Specification](#10-rendering-specification)
11. [Tile System](#11-tile-system)
12. [Object System](#12-object-system)
13. [Combat System](#13-combat-system)
14. [Buff System](#14-buff-system)
15. [Player Capabilities](#15-player-capabilities)
16. [Host (DM) Capabilities](#16-host-dm-capabilities)
17. [Inventory & Equipment System](#17-inventory--equipment-system)
18. [Stairs System](#18-stairs-system)
19. [Chat System](#19-chat-system)
20. [Save & Load System](#20-save--load-system)
21. [Settings & Banlist](#21-settings--banlist)
22. [Build & Distribution](#22-build--distribution)
23. [Keybindings Reference](#23-keybindings-reference)

---

## 1. Overview

A desktop **multiplayer tabletop RPG lobby and game runner** built in Python.

One player acts as the **Host (Dungeon Master / DM)**: they build and manage the game world — placing tiles, spawning objects, managing players, running combat. Other players act as **Player Characters (PC)**: they join via connection string, move around the world, interact with objects, manage inventories, and participate in chat.

The host runs the authoritative game **server**; all game-state mutations are validated and broadcast by the server. The host also runs a local client on top of the server, with elevated DM-only permissions. The **DM does not have a PlayerObject** in the game world.

All dialogs open as **in-app floating panels** — no detached OS windows. Most panels float on the **right side** of the window. Short blocking confirmations (Door interaction, Stair prompt) appear at the **top-centre** of the screen without any backdrop, so the game canvas remains fully visible behind them.

---

## 2. Technology Stack & Dependencies

All packages declared in `requirements.txt`.

| Package | Version | Purpose |
|---|---|---|
| `Pillow` | `>=10.0` | Avatar image processing, canvas image rendering |
| `msgpack` | `>=1.0` | Binary save-file serialisation |
| `pyinstaller` | `>=6.0` | Standalone executable build |
| `asyncio` | stdlib | Async I/O backbone for networking |
| `tkinter` | stdlib (Python >= 3.9) | GUI framework |
| `uuid`, `json`, `zlib`, `threading`, `queue`, `dataclasses`, `typing`, `socket`, `struct`, `pathlib`, `datetime`, `base64`, `re`, `colorsys`, `math` | stdlib | Various utilities |

**Python version:** 3.9+  
**Entry point:** `python main.py`  
**Default window size:** 1280x720, resizable (minimum 900x600)

---

## 3. Project Structure

```
<project_root>/
├── main.py                        # Entry: App().mainloop()
├── requirements.txt
├── build.bat                      # Build script -> dist/Steel2D/ + dist/Steel2D.zip
├── Steel2D.spec                   # PyInstaller spec (one-directory bundle)
├── GAME_REQUIREMENTS.md
│
├── app/
│   ├── controller.py              # App(tk.Tk) — navigation, session management
│   ├── constants.py               # PALETTE, FONTS, cell sizes, tag colours, BUFF_TYPES
│   └── config.py                  # load/save config, get_base_dir(), get_saves_dir(), get_prefabs_dir()
│
├── screens/
│   ├── main_menu.py               # MainMenuScreen
│   ├── profile.py                 # ProfileScreen
│   ├── game.py                    # GameScreen (host & client; role governs widgets)
│   └── dm_tool.py                 # DmToolScreen + PrefabBuilder + EmbeddedSpawnForm
│
├── dialogs/
│   ├── confirm_dialog.py          # ask_confirm() blocking Panel
│   ├── banlist_dialog.py          # BanlistDialog
│   ├── host_dialog.py             # HostDialog (New / Load)
│   ├── join_dialog.py             # JoinDialog
│   ├── new_game_settings.py       # NewGameSettingsDialog
│   ├── load_game_dialog.py        # LoadGameDialog
│   ├── spawn_object_dialog.py     # SpawnObjectDialog (NPC/Item) & ModifyObjectDialog
│   ├── door_dialog.py             # DoorInteractionDialog (PC side)
│   ├── inventory_dialog.py        # InventoryDialog
│   ├── player_list_overlay.py     # PlayerListOverlay (TAB/O key)
│   ├── player_stats_dialog.py     # PlayerStatsDialog + PlayerStatsTooltip
│   ├── object_tooltip.py          # ObjectTooltip
│   ├── dm_options_dialog.py       # DmOptionsDialog (kick/ban)
│   ├── combat_overlay.py          # TurnOrderPanel (right side during combat)
│   ├── prefab_load_dialog.py      # PrefabLoadDialog (DM Workshop)
│   ├── spawn_prefab_dialog.py     # SpawnPrefabDialog (in-game Spawn Prefab)
│   └── stair_dialog.py            # StairModifyDialog + StairPromptDialog
│
├── game/
│   ├── state.py                   # GameState, GameSettings, Cell, CombatState, CombatTurn
│   ├── objects.py                 # NPC, Item, Door, Wall, Stairs, PlayerObject, BUFF_TYPES
│   ├── stats.py                   # clamp_stats, calc_max_hp, effective_stat, apply_action
│   ├── combat.py                  # build_turn_queue, advance_turn, remove_combatant
│   ├── los.py                     # has_los, cells_in_range
│   └── serialise.py               # dump_state, load_state (msgpack + zlib)
│
├── network/
│   ├── protocol.py                # Message constants, encode_msg, decode_msg
│   ├── server.py                  # GameServer (asyncio TCP)
│   └── client.py                  # GameClient (asyncio TCP)
│
└── ui/
    ├── panel.py                   # Panel(tk.Frame) — in-app overlay (right-side or top-centre)
    ├── widgets.py                 # flat_btn, hr, styled_entry, styled_check
    ├── canvas_renderer.py         # GameCanvas(tk.Canvas)
    └── chat_widget.py             # ChatWidget
```

**User data directory:**
- Frozen (PyInstaller): `%APPDATA%\Steel2D\`
- Development: project root

---

## 4. Data Models

All models use `@dataclass`. Every model implements `to_dict() -> dict` and `@classmethod from_dict(d) -> Self`. Grid keys `(x, y)` are serialised as `"x,y"` strings.

---

### 4.1 Lookup Tables (`app/config.py`)

```python
STAT_KEYS = ("Str", "Dex", "Con", "Int", "Wis", "Cha")

HEALTH_SIZE_LOOKUP = {"Small": 1, "Medium": 2, "Large": 3, "Giant": 6, "Colossal": 10}

SCALAR_WEIGHT_LOOKUP = {"S": 1.00, "A": 0.70, "B": 0.45, "C": 0.15, "F": 0.05}
```

```python
# game/objects.py
BUFF_TYPES = ("HP Over Time", "Stat Modifier", "Turn Modifier", "Defense Modifier")
```

---

### 4.2 NPC

```python
@dataclass
class NPC:
    id:            str
    type:          str = "NPC"
    Name:          str = ""
    Description:   str = ""
    Level:         int = 1
    Size:          str = "Medium"    # Small | Medium | Large | Giant | Colossal
    Hostile:       bool = True
    MaximumHP:     int = 10
    CurrentHP:     int = 10
    Stats:         Dict[str, int] = field(default_factory=lambda: {k: 10 for k in STAT_KEYS})
    Scalars:       Optional[Dict[str, str]] = None     # per-stat grade (NPC-level; Items no longer use this)
    Actions:       Optional[Dict[str, dict]] = None    # see §4.4
    TurnsAllowed:  int = 1           # extra initiative rolls & turn slots in combat
    Buffs:         List[dict] = field(default_factory=list)  # see §4.5
```

Default Stats are **10** for all keys when spawned fresh. Stats obey the same `MAX_INDIVIDUAL(level)` / `MAX_TOTAL(level)` constraints as player stats (warning shown, DM may override).

Spawn default HP:
```python
MaximumHP = CurrentHP = calc_max_hp(Size, Level, Stats["Con"], hp_base_multiplier)
```

---

### 4.3 Item

```python
@dataclass
class Item:
    id:            str
    type:          str = "Item"
    Name:          str = ""
    Description:   str = ""
    Level:         int = 1     # always 1; no longer user-editable
    Consumable:    bool = False
    Quantity:      int = 1
    Value:         int = 0
    Stats:         Optional[Dict[str, int]] = None    # equipment stat bonuses
    Scalars:       None                               # removed in v0.15
    Actions:       Optional[Dict[str, dict]] = None
    EquipmentSlot: Optional[int] = None               # 1-8; see §17.1
```

Items no longer have a user-editable Level field and no longer support item-level Scalars. Per-action ScalesWith is still available via action rows.

---

### 4.4 ActionDict

Each key in `NPC.Actions` or `Item.Actions` is a display name; the value:

```python
ActionDict = {
    "Description": str,
    "Range":       int,        # 0=self; 1=adjacent; N=radius N + LOS
    "BaseDamage":  int,        # positive=damage; negative=healing
    "Hits":        int,
    # Optional
    "Casts":       Optional[{"max_per_rest": int, "remaining": int}],
    "GivesBuffs":  Optional[List[BuffDef]],   # see §4.6
    "ScalesWith":  Optional[Dict[str, str]],  # per-stat grade (NPC actions and Action prefabs only)
}
```

NPC actions carry their own per-action `ScalesWith`. Items no longer have item-level Scalars.

---

### 4.5 Buff (list entry in entity.Buffs)

```python
BuffEntry = {
    "Name":     str,          # display name; uniquely identifies within entity
    "Type":     str,          # one of BUFF_TYPES
    "Value":    int,          # meaning depends on Type (see §14)
    "Duration": float,        # remaining minutes
    "Stat":     Optional[str], # required when Type == "Stat Modifier"
}
```

**BuffDef** (inside ActionDict.GivesBuffs):
```python
BuffDef = {
    "Name":     str,
    "Type":     str,
    "Value":    int,
    "Duration": int,           # minutes
    "Stat":     Optional[str],
}
```

Standalone "Buff" prefab objects share the same fields plus `"type": "Buff"` and `"Description": str`.

---

### 4.6 Door

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

### 4.7 Wall

```python
@dataclass
class Wall:
    id:   str
    type: str = "Wall"
```

---

### 4.8 Stairs

```python
@dataclass
class Stairs:
    id:          str
    type:        str = "Stairs"
    Name:        str = "Stairs"
    Direction:   str = "Up"     # "Up" | "Down"
    LinkedStair: str = ""       # UUID of linked Stairs, or ""
```

Bidirectional linking is maintained by the server at all times (see §18).

---

### 4.9 PlayerObject

```python
@dataclass
class PlayerObject:
    id:          str           # == connecting player UUID
    type:        str = "Player"
    Name:        str = ""
    Size:        str = "Medium"
    Level:       int = 1
    MaximumHP:   int = 24
    CurrentHP:   int = 24
    color:       str = "#ffffff"
    Stats:       Dict[str, int] = field(default_factory=lambda: {k: 0 for k in STAT_KEYS})
    Equipment:   Dict[int, Item] = field(default_factory=dict)
    Inventory:   List[Item]     = field(default_factory=list)
    avatar_png:  Optional[bytes] = None
    Buffs:       List[dict]     = field(default_factory=list)
```

#### Equipment Slot IDs

```python
EQUIPMENT_SLOTS = {
    1: "Head", 2: "Chest", 3: "Legs", 4: "Feet",
    5: "Ring", 6: "Trinket", 7: "Main Hand", 8: "Off Hand",
}
```

#### Player HP Rules

Initial HP on first join: `calc_max_hp("Medium", 1, 10, hp_base_multiplier)` using default stat of 10 for Con.

Players **cannot** edit their own HP. Only DM action or combat/buff effects modify `CurrentHP`.

On Level Up: `MaximumHP` recalculated; `CurrentHP = MaximumHP`.

On Con change:
- Increased and was at full health: stay at full.
- Decreased: `CurrentHP = max(1, new_max - 1)`.

---

### 4.10 Cell

```python
@dataclass
class Cell:
    walkable:  bool = False
    protected: bool = False
    tile_type: str  = "ground"    # "ground" | "water"
    occupant:  Optional[Union[NPC, Item, Door, Wall, Stairs]] = None
```

**Protected cells** (x in [0,3], y in [0,3]) can never be deleted, converted to water, or have objects spawned in them. They can contain PlayerObjects and NPC occupants that moved in via drag or combat.

---

### 4.11 GameState

```python
@dataclass
class GameState:
    name:             str = "Untitled"
    settings:         GameSettings = field(default_factory=GameSettings)
    grid:             Dict[Tuple[int,int], Cell] = field(default_factory=dict)
    players:          Dict[str, PlayerObject] = field(default_factory=dict)
    players_at:       Dict[str, List[str]] = field(default_factory=dict)  # "x,y" -> [uuid]
    chat_history:     List[dict] = field(default_factory=list)
    host_view:        Tuple[float, float] = (0.0, 0.0)
    host_zoom:        float = 1.0
    assigned_colors:  Dict[str, str] = field(default_factory=dict)    # uuid -> hex
    avatar_cache:     Dict[str, str] = field(default_factory=dict)    # uuid -> base64
    combat:           Optional[CombatState] = None
```

**Initial state:** Cells `(x, y)` for `x in range(4), y in range(4)` created as `Cell(walkable=True, protected=True, tile_type="ground")`.

---

### 4.12 GameSettings

```python
@dataclass
class GameSettings:
    hp_base_multiplier:      float = 4.0
    enemy_damage_multiplier: float = 1.0
    los_max_distance:        int   = 20
```

---

### 4.13 CombatTurn

```python
MOVE_COST      = 1.5
ACTION_COST    = 2.0
TURN_THRESHOLD = 3.0

@dataclass
class CombatTurn:
    combatant_type: str    # "player" | "npc"
    id:             str    # player UUID or NPC UUID
    name:           str
    initiative:     int
    has_acted:      bool  = False
    points_spent:   float = 0.0

    @property
    def can_move(self) -> bool: return self.points_spent < TURN_THRESHOLD
    @property
    def can_act(self)  -> bool: return not self.has_acted and self.points_spent < TURN_THRESHOLD
```

---

### 4.14 CombatState

```python
@dataclass
class CombatState:
    active:            bool = False
    encounter_npc_ids: List[str] = field(default_factory=list)
    turn_queue:        List[CombatTurn] = field(default_factory=list)
    current_index:     int = 0
    round_number:      int = 1
```

---

## 5. Configuration & Persistence Files

| File | Location | Format | Written by |
|---|---|---|---|
| `user.config` | `<game_dir>/` | JSON | App (on profile save) |
| `game_config.json` | `<game_dir>/` | JSON | Operator only |
| `banlist.json` | `<game_dir>/` | JSON array | Server (on kick/ban) |
| `saves/*.sav` | `<game_dir>/saves/` | msgpack+zlib | Server (on Save & Quit) |
| `prefabs/*.json` | `<game_dir>/prefabs/` | JSON | DM Workshop |

`<game_dir>` = `%APPDATA%\Steel2D\` when frozen; project root when running from source.

### 5.1 `user.config`

```json
{
  "uuid": "xxxxxxxx-...",
  "alias": "",
  "avatar_b64": null,
  "preferred_port": 5000
}
```

### 5.2 `game_config.json` (global defaults, operator-only)

```json
{
  "hp_base_multiplier": 4.0,
  "enemy_damage_multiplier": 1.0,
  "los_max_distance": 20
}
```

### 5.3 Prefab File Format

```json
{
  "name": "My Prefabs",
  "updated_at": "2024-01-15T10:30:00+00:00",
  "objects": [
    {"type": "NPC",    "id": "...", "Name": "Goblin", "...": "..."},
    {"type": "Item",   "id": "...", "Name": "Sword",  "...": "..."},
    {"type": "Action", "id": "...", "Name": "Fireball", "...": "..."},
    {"type": "Buff",   "id": "...", "Name": "Haste", "...": "..."}
  ]
}
```

---

## 6. Network Architecture & Protocol

### 6.1 Roles

| Role | Runs | Notes |
|---|---|---|
| Host / DM | `GameServer` + local `GameClient` | Authoritative; **DM has no PlayerObject** |
| Player Character | `GameClient` only | Remote; no DM permissions |

The host's local `GameClient` connects to `127.0.0.1:<port>`. The server identifies the DM by `host_uuid` and sets `conn.is_host = True`. When the DM's HELLO arrives, the server sends WELCOME with full game state but **does not** create a PlayerObject for the DM.

### 6.2 Thread Safety

Network I/O runs in a background thread via asyncio. A `queue.Queue` (`ui_queue`) carries `(event_type, payload)` tuples from network to UI, polled every 50 ms via `root.after`.

### 6.3 Message Framing

```
[4 bytes LE uint32: body_length][body_length bytes: UTF-8 JSON]
```

### 6.4 Connection Flow

```
Client  -> [TCP connect] -> Server: check banlist -> REJECT if banned
Client  -> HELLO(uuid, alias, avatar_b64) -> Server
Server  -> WELCOME(full game_state, your_cell) -> Client
Server  -> STATE_PATCH (new player joined) -> All other clients
```

Avatar: if `avatar_cache[uuid]` exists server-side, HELLO's `avatar_b64` is ignored.

### 6.5 STATE_PATCH Operations

```python
# op values
"set_cell"       # path: "x,y", value: Cell dict
"del_cell"       # path: "x,y"
"set_player"     # path: uuid, value: PlayerObject dict
"del_player"     # path: uuid
"set_players_at" # path: "x,y", value: [uuid, ...]
"set_settings"   # value: GameSettings dict
"set_combat"     # value: CombatState dict or null
```

### 6.6 Message Catalogue (abridged)

All messages carry `"type": str`.

**Client -> Server (all players):**
`HELLO`, `PLAYER_MOVE`, `PLAYER_ACTION`, `CHAT_SEND`, `DOOR_INTERACT`, `ITEM_PICKUP`, `ITEM_DROP`, `ITEM_DISCARD`, `ITEM_USE`, `ITEM_EQUIP`, `STATS_UPDATE`, `PLAYER_END_TURN`, `PLAYER_TAKE_STAIRS`, `DISCONNECT`, `PING`

**Server -> Client (broadcasts):**
`WELCOME`, `REJECT`, `STATE_PATCH`, `CHAT_RECV`, `CAMERA_CENTER`, `PLAYER_DISCONNECTED`, `YOU_WERE_KICKED`, `PONG`, `COMBAT_STARTED`, `COMBAT_ENDED`, `COMBAT_TURN_ADVANCED`, `COMBAT_RESOURCES_USED`

**Host DM -> Server (DM-only; server validates `is_host`):**
`DM_TILE_SET`, `DM_SPAWN_OBJECT`, `DM_DELETE_OBJECT`, `DM_MODIFY_OBJECT`, `DM_MOVE_OBJECT`, `DM_WARP_PLAYERS`, `DM_LEVEL_UP_PLAYER`, `DM_KICK_PLAYER`, `DM_BAN_PLAYER`, `DM_MODIFY_PLAYER`, `DM_UPDATE_SETTINGS`, `DM_ADD_TO_ENCOUNTER`, `DM_REMOVE_FROM_ENCOUNTER`, `DM_START_COMBAT`, `DM_END_COMBAT`, `DM_NPC_MOVE`, `DM_NPC_ACTION`, `DM_NPC_END_TURN`, `DM_CHAT_AS_NPC`, `DM_LONG_REST`

### 6.7 Player Color Assignment

HSV `(h, 0.85, 1.0)` — always full brightness and high saturation. Hue must maintain Chebyshev distance >= 0.10 from reserved hues (NPC red, NPC green, Item orange, DM orange, yell salmon, whisper blue/purple, etc.). Fallback: hash of UUID.

---

## 7. Main Menu & Profile Screen

### 7.1 Main Menu Layout

```
[⚙]  (gear icon, top-right; opens BanlistDialog)

   STEEL2D
   v0.15 · multiplayer tabletop lobby
   ─────────────────────────────────────────
   [avatar 40x40]  Signed in as  <alias>
   ─────────────────────────────────────────
   [ 👤  Create Profile ]   <- "Edit Profile" if alias set
   <- Set up your player to continue  (hint only shown if no alias)

   [ 🛠  DM Workshop ]           (spectre style: dark violet / lavender)

   [ 🖥  Host ]   [ 🌐  Join ]   (both disabled if no alias)
   ─────────────────────────────────────────
   [ ✕   Quit ]
```

- **DM Workshop**: available to any player; opens `DmToolScreen`.
- **Host / Join**: disabled until alias is configured.

### 7.2 Profile Screen

Full-window swap (like GameScreen). Fields:
- Player Name (Entry, max 32 chars)
- UUID (read-only, small monospace, single line, no wrap)
- Profile Picture (128x128 Canvas preview; Upload / Remove buttons; PIL crop-to-square)

Save persists to `user.config`. Player Name must not contain spaces (enforced on save with an error message).

---

## 8. DM Workshop (Prefab System)

Opened from the main menu. A full-window screen (replaces the window content). Available to any player.

### 8.1 Landing Page

Two buttons: **Create Prefab Objects** (new builder) and **Load Prefab Objects** (file list panel). Back to Menu.

**Load dialog** (`PrefabLoadDialog`): lists all `*.json` in the prefabs directory, sorted newest-first by mtime. Shows **Name** and **Date** columns at 50% width each (Object Count column removed). Supports Open and Delete (with confirmation).

### 8.2 Prefab Builder Layout

```
Header: "Prefab Builder — <file name>"
─────────────────────────────────────────────────────────────────────
Left panel (50%)             |  Right panel (50%)
─────────────────────────────|───────────────────────────────────────
Type: [NPC][Item][Action]    |  Prefab Objects
       [Buff]                |  Name  | Type | Description   <- bold header, dark bg
[form fields...]             |  ─────────────────────────────
[✚ Add to Prefabs]           |  row1 (clickable -> Modify)
                             |  row2 ...
                             |  [x] delete per row
─────────────────────────────────────────────────────────────────────
         [💾 Save Prefabs]           [✕ Exit Prefab Builder]
```

- Bottom bar packed BEFORE content frame so it remains visible.
- Rows in the right table: clickable to open the Modify Object dialog (SpawnObjectDialog / Action editor / Buff editor).

#### 8.2.1 NPC / Item Forms (left panel)

Reuses `SpawnObjectDialog` form builders. Collapsible sections; **General always starts expanded**.

**NPC sections:** General (Name, Description, Level, Size, Hostile, Turns Allowed, **Maximum HP readonly** auto-calculated from Size + Con), Stats, Actions.
- Current HP is **not** shown in the create/modify form. Use right-click → **Modify Current HP** on a spawned NPC.

**Item sections:** General (Name, Description, Quantity, Value (g), Consumable, Equipment Slot), Stat Modifiers, Actions.
- Items no longer have Level or Scalars fields.

#### 8.2.2 Action Form (left panel)

Flat layout (no collapsible sections), mirroring NPC/Item action row style:
- Name (required), Description (2-line textarea)
- Range, Dmg, Hits
- `[  ] Limited Uses (Casts)` -> Max/rest, Remaining (hidden until checked)
- `[  ] Applies Buffs` -> list of buff entries (`+Buff` button — loads from session table + disk)
- `[  ] Scales With Stat` -> per-stat grade dropdowns

`+Buff` searches session Prefab Objects table first, then disk prefab files, merging both (session takes priority on name collision).

#### 8.2.3 Buff Form (left panel)

Flat layout:
- Name (required, blank default), Description
- Type (dropdown: HP Over Time | Stat Modifier | Turn Modifier | Defense Modifier)
- Stat (dropdown of STAT_KEYS, only when Type = "Stat Modifier")
- Value (int), Duration (int, minutes)

#### 8.2.4 Unique Name Enforcement

Names must be unique **within the same object type** (NPC/Item/Action/Buff). Doors and Stairs are exempt. Error message shown inline; form not submitted.

#### 8.2.5 Save / Exit

**Save Prefabs**: if new session (no loaded file), prompt for name -> write `<name>.json`. If loaded file, silently overwrite.

**Exit Prefab Builder**: confirmation "Would you like to exit? Anything not saved will be lost." -> Exit (danger) or Go Back (normal).

### 8.3 In-Game Spawn Object Using Prefabs

DM right-clicks unoccupied non-protected ground -> **Spawn Object...** (only shown when `GameScreen.prefabs` is non-empty).

Opens `SpawnPrefabDialog` — NPC and Item types only, on individual tabs (Action/Buff cannot be placed on the grid):
1. **Table view**: Name / Type / Description; clickable rows; search bar at top filters on Name and Description text for substring matches.
2. **Detail view** (on row click): read-only field list; Spawn / <- Back.
3. Spawn: fresh UUID assigned; placed via DM_SPAWN_OBJECT; panel closes.

### 8.3 Session Prefabs

- All prefab files in `<game_dir>/prefabs/` loaded at host-game-start into `GameScreen.prefabs`.
- Every NPC or Item the DM creates in-game via Spawn Object is also appended to `self.prefabs` immediately (without saving to disk), making it reusable via Spawn Prefab for the rest of the session.

---

## 9. Game Canvas & Camera

### 9.1 Layout

```
[DM HUD: IP:port | N players online]  (DM only, thin bar at top)
─────────────────────────────────────────────────────────────────
                       GameCanvas
                  (tk.Canvas, fills rest)

[🌙 Long Rest]                          (DM only, above combat bar)
[⚔ Start Combat        0 in encounter]  (DM only, full-width, above chat)
[Chat log  380x180px]                   (bottom-left, over canvas)
```

Chat entry: dark when unfocused; white background with black text when focused. Scrollbar inside chat log (dark 6px, overlaid).

Long Rest and Start/End Combat buttons span the full chat width (380px) so the bar fills edge-to-edge above the chat.

### 9.2 Cell Size & Zoom

```python
BASE_CELL_PX = 64
ZOOM_MIN     = 0.25
ZOOM_MAX     = 4.0
ZOOM_STEP    = 0.1
```

Scroll-to-zoom centres on the mouse cursor.

### 9.3 DM Camera Pan (smooth)

WASD / arrow keys held → continuous pan at 9 canvas px/frame divided by zoom. Diagonal speed normalised (× 0.707). DM may zoom freely with the scroll wheel. Panning starts on key-press, stops on key-release. All keys suppressed when any text input has focus.

### 9.4 PC Movement & Camera

WASD / arrow keys → `PLAYER_MOVE` for one orthogonal tile per press. Disabled when text input focused.

**PC camera is locked to the player sprite** and recenters every frame — players cannot pan or zoom. The scroll wheel is ignored for PC clients. Movement keys are additionally blocked while a blocking interaction panel (Door or Stairs dialogue) is open.

### 9.5 DM Camera Centering

- **New game**: DM viewport centres on the 4x4 initial grid after 120 ms delay.
- **Teleportation** (stairs/warp): camera centres client-side immediately for the teleporting PC.

### 9.6 PC Disconnected — Main Menu Notice

When the server connection drops (`DISCONNECTED` event), the PC is navigated back to the main menu and a top-centre Panel appears: **"Disconnected from server"** with a Close button.

---

## 10. Rendering Specification

### 10.1 Background

Canvas background: `#000000`. Grid lines at every cell boundary: `#1a1a1a`, 1px.

### 10.2 Tiles

- **Ground**: `#ffffff`, 2px inward padding on all sides.
- **Water**: pastel blue (base `#a8d8ea`), 2px padding. Adjacent water tiles extend to the shared cell boundary (no black gap). Depth shading based on Chebyshev distance to nearest ground tile:
  - Ground within 2 cells: base color `#a8d8ea`
  - No ground within 2, some within 3: -12.5% brightness / +12.5% saturation
  - No ground within 3, some within 4: -25% / +25%
  - No ground within 4+: -37.5% / +37.5% (deepest)
  
  Depth cached per cell; cache invalidated on cell STATE_PATCH.

### 10.3 Object Sprites

All icons **float from the bottom** of the tile: `icon_bottom = y1 - 2*zoom - 4*zoom` (tile edge minus 4px gap, both scaled by zoom).

| Object | Sprite |
|---|---|
| NPC (Hostile) | Upward equilateral triangle, ~60% of cell. `#cc2222` fill / `#880000` outline 2px. Centroid at `icon_bottom - height/3`. |
| NPC (Friendly) | Circle, ~60% diameter. `#22aa22` / `#115511` 2px. Bottom at icon_bottom. |
| Item | 4-pointed star, outer r ~38%, inner r ~18% of cell. `#ff8800` / `#000000`. Bottom at icon_bottom. |
| Door (Closed) | Brown rect inset 2px. `#8b4513` fill / `#5c2d0a` outline 2px. |
| Door (Open) | Same rect, no fill. `#8b4513` outline **6px**. |
| Door (Broken) | Diagonal X lines over rect, `#333333`, 1px. |
| Door (Locked) | Small gold circle centred on rect. `#ffcc00` / `#cc9900`. |
| Wall | `#888888` fill. Extends to shared boundary with each orthogonal adjacent wall, eliminating the inter-cell gap. |
| Stairs (Up) | `#3388bb` rect (4px pad all sides) + centred `▲` white bold text. |
| Stairs (Down) | `#883388` rect (4px pad) + centred `▼` white bold. |
| Player | Colored rect (65% cell fill; 17.5% pad each side). Outline: fill color x0.6 darker, 2px. Avatar PNG if available (scaled to 75% cell). Abbreviation otherwise. |

### 10.4 HP Bars (DM only)

Rendered only when `self.is_dm == True`.
- 2px solid black outer border.
- Background bar `#333333`; fill bar `#44ee44`.
- Position: `y = cell_top + 8*zoom`; side padding `10*zoom`.

### 10.5 Player Color Assignment

HSV `(h, 0.85, 1.0)`. Reserved hue exclusion (Chebyshev radius 0.10):
NPC red, NPC green, Item orange, DM orange, yell salmon, yellow, cyan-blue, whisper blue, purple/magenta bands. Fallback: deterministic hash of UUID.

### 10.6 Hover Tooltips

Tooltip only appears when cell has an occupant or players. Coordinates always shown.

| Hovering over | DM sees | PC sees |
|---|---|---|
| Player cell | Name, HP, all stats | Name |
| NPC (in LOS) | Name, `Health: cur/max`, `Size:`, `Status: Hostile/Friendly`, `Location: (x,y)` | Name, Description |
| Item (in LOS) | Name, Description, Qty, Value | Name, Description |
| Door (in LOS) | State, Locked, Broken | State, Locked, Broken |
| Stairs (in LOS) | Name, Direction, linked cell coords | "Stairs Up" / "Stairs Down" |
| Empty cell | (nothing) | (nothing) |

### 10.7 Text Bubbles

Rendered above the sprite of the sender. Auto-dismissed after 3 s. Whisper bubbles only on sender's and recipient's client. NPC chat renders bubble above the NPC sprite.

### 10.8 Combat Highlights

- **Active combatant glow**: none (removed).
- **Valid movement** (when `can_move`): light-blue stippled rects on valid adjacent cells.
- **Valid action targets** (after action selected): red-orange stippled rects on all in-range cells (including empty — fizzle allowed).

### 10.9 Death Animation

NPC HP hits 0 -> 500 ms fade to black (10 steps x 50 ms). Cell occupant removed after animation.

---

## 11. Tile System

### 11.1 Tile Types

| Type | Walkable | Color | Notes |
|---|---|---|---|
| Ground | Yes | `#ffffff` | Default; can hold objects; supports Y+drag walls |
| Water | No (for NPCs) | Blue (depth-shaded) | Cannot hold objects; NPCs cannot enter; **players can enter** (Drowning after 5 ticks — see §15.1) |
| None (black) | No | `#000000` | Empty grid cell |

### 11.2 DM Tile Editing

| Input | Result |
|---|---|
| Left click on empty black cell | Create ground tile |
| Left drag from any ground tile | Paint ground tiles on drag-over; also clears Wall objects on pass-over |
| Left drag from empty black | Same: paint ground tiles |
| U + left drag on unoccupied ground or empty | Create/convert to water |
| Without U, left drag over water | Convert water -> ground |
| Y + left drag on ground/water/empty | Spawn wall (auto-converts non-ground first) |
| Middle click + drag | Delete ground and water tiles |
| Middle drag restrictions | Not during combat; not protected cells; not within 1 tile radius of any player |

**Protected cells (0-3, 0-3)** are silently skipped by all painting operations.

### 11.3 Paintbrush Size

The DM HUD (top bar, right side) always shows **Paintbrush Size: N**. Size determines how many cells are affected by each painting or erasing operation:

| Size | Affected area | Chebyshev radius |
|---|---|---|
| 1 (default) | Single hovered cell | 0 |
| 2 | 3×3 block | 1 |
| 3 | 5×5 block | 2 |
| N | (2N-1) × (2N-1) | N-1 |
| 10 (max) | 19×19 block | 9 |

Brush size applies to **all** left-drag painting modes (ground, water, wall, wall-clear) and to **middle-mouse erasing**. Object drag is always single-cell regardless of brush size.

Size is clamped to `[1, 10]`. While `]` or `[` is held, size increments/decrements at 10 steps/second.

---

### 11.4 Known Performance Limitation

The renderer uses tkinter's Canvas widget with individual draw calls (rectangle per tile, line per grid line). **Performance degrades proportionally to the total number of filled grid cells:**

- ~50 filled cells: mild frame-rate drop noticeable.
- ~200+ filled cells: camera panning becomes jittery; tile spawn/delete operations slow noticeably.

This is a fundamental constraint of the tkinter Canvas approach; no architecture-level fix is present in v0.15.

**Workaround:** middle-mouse drag (with a large brush size) over large regions deletes tiles quickly, reducing the cell count and restoring performance. The performance issue is **content-count-driven** (not content-type-driven — ground tiles without any shading cause the same drop as water tiles).

---

## 12. Object System

### 12.1 Placement Rules

| Object | May be placed on | Via |
|---|---|---|
| NPC | Non-protected ground (no other occupant) | DM_SPAWN_OBJECT |
| Item | Same | DM_SPAWN_OBJECT |
| Door | Same | Right-click -> Spawn Door |
| Wall | Same (auto-creates ground if needed) | Y+drag |
| Stairs | Same | Right-click -> Spawn Stairs |

Objects cannot be spawned in protected cells. NPCs and objects can be dragged into protected cells via DM drag-and-drop.

### 12.2 Traversal Rules

| Object | PC can walk onto it? |
|---|---|
| NPC | No |
| Item | Yes |
| Door (Open) | Yes |
| Door (Closed) | No |
| Wall | **No** (blocks like a closed door) |
| Stairs | Yes (triggers prompt on step-in via WASD only) |
| Water tile | **Yes** (Drowning mechanic after 5 ticks — see §15.1) |

### 12.3 Action Row Fields

Per action row (shared by NPC/Item Spawn dialog and Action prefab editor):
- Name, Description (2-line textarea), Range, Dmg, Hits
- `[  ] Limited Uses (Casts)` -> Max/rest, Remaining (hidden until checked)
- `[  ] Applies Buffs` -> list of buff defs (`+Buff` loads from session + disk Buff prefabs)
- `[  ] Scales With Stat` -> per-stat grade dropdowns (NPC forms and Action prefabs only)

### 12.4 DM Right-Click Context Menu (out of combat)

**On unoccupied non-protected ground:**
- **Spawn Object** — opens `SpawnFromPrefabsDialog` (tabbed NPC/Item table with search bar); places the selected prefab as a new instance
- Spawn Door (default: closed, unlocked, intact)
- Spawn Stairs (default: Up, no link)
- Spawn Prefab... (shown only when `GameScreen.prefabs` is non-empty; opens full prefab picker)
- Warp Players Here (if >= 16 contiguous tiles in the connected component)

**On NPC:**
- Modify Object, Delete Object
- **Modify Current HP** — in-app panel: enter signed integer delta; positive = heal (clamped to MaxHP), negative = damage; `<= 0` triggers full death path (DM_DELETE_OBJECT)
- **Speak as NPC…** — opens a right-side Panel with a textarea; submitting sends `DM_CHAT_AS_NPC` so the NPC speaks in chat under its own name. Replaces the old `/as` command.
- Add To Encounter / Remove From Encounter
- Actions -> submenu (with combat-aware Casts display)

**On Door:**
- Open/Close toggle, Break/Fix toggle, Lock/Unlock toggle
- Delete Door (non-protected only)

**On Stairs:**
- Modify Stairs (StairModifyDialog)
- Delete Stairs (non-protected only)

**On Wall:**
- Delete Wall

**On protected cells:** player sub-menus only; no spawn/delete options.

**During active combat:**
- Left and middle click: all tile/object editing blocked (only NPC click-to-move allowed).
- Right click: player sub-menus only (Level Up, Modify Player, Options).

---

## 13. Combat System

### 13.1 Initiative & Turn Order

When DM clicks **Start Combat**:
1. All connected players enter automatically.
2. NPC participants = `encounter_npc_ids` (built via "Add To Encounter").
3. Initiative per slot: `max(Dex - 20, 0) + randint(1, 20)`.
4. NPCs with `TurnsAllowed > 1` get that many separate rolls and slots.
5. Players with active "Turn Modifier" buff get `buff.Value` extra rolls/slots.
6. Sort descending; ties randomised. Set `active = True`, `round = 1`, `index = 0`.
7. Broadcast COMBAT_STARTED.

### 13.2 Points System

Each turn has a 3.0-point budget:

| Resource | Cost | Blocked when |
|---|---|---|
| Move (1 tile) | 1.5 pts | `points_spent >= 3.0` (auto-ends turn) |
| Action (attack/ability) | 2.0 pts | `has_acted == True` or `points_spent >= 3.0` |
| Second action | Invalid | `has_acted == True` always blocks |

Valid combos: Move+Move (3.0 -> auto-end), Move+Action (3.5 -> auto-end), Action+Move (3.5 -> auto-end). Two actions per turn is invalid.

Auto-end fires immediately after the triggering move/action — no manual "End Turn" required.

### 13.3 Player Combat Turn

- **Move**: WASD or left-click adjacent walkable ground. Deducts MOVE_COST; auto-ends if total >= 3.0.
- **Action**: left-click adjacent NPC -> Action context menu. Range > 1: highlights valid cells; click to confirm. Empty cells are valid (result = fizzle).
- **Range 0 actions**: self-target (no NPC target required).
- **End Turn**: SPACE or "End Turn" button in Turn Order Panel.

### 13.4 DM NPC Turn

- WASD pans camera normally.
- Left-click adjacent walkable non-protected ground -> move active NPC (`DM_NPC_MOVE`).
- Right-click NPC -> Actions submenu -> target selection.
- SPACE or "End NPC Turn" in Turn Order Panel -> `DM_NPC_END_TURN`.

### 13.5 Stat Modifier Formula

All stat-based bonuses use the **standard D&D ability score modifier**:

```python
def stat_mod(stat_value: int) -> int:
    return (stat_value - 10) // 2   # floor division; negatives handled correctly
```

Examples: 6→-2, 8→-1, 10→0, 12→+1, 14→+2, 16→+3, 18→+4, 20→+5

### 13.6 HP Formula

```python
def calc_max_hp(size: str, level: int, con: int, multiplier: float) -> int:
    size_val = HEALTH_SIZE_LOOKUP[size]          # see §4.1
    con_mod  = stat_mod(con)
    per_level_base = max(1, size_val + con_mod)  # never < 1 so level always helps
    return max(1, ceil(multiplier * level * per_level_base))
```

A higher Level **always** produces more HP regardless of Con. Negative Con modifiers reduce the per-level base but it is clamped to ≥ 1.

### 13.7 Damage Formula

```python
# Ability score modifier helper (see §13.5)
# stat_mod(v) = (v - 10) // 2

# Default (unarmed) attack — always available
best_mod = stat_mod(max(Dex, Str))
dmg = max(1, best_mod + ceil(Level * 1.5))

# Weapon/spell action
scalar_total = sum(
    ceil(stat_mod(combatant.Stats.get(stat, 0)) * (1 + SCALAR_WEIGHT[weight]))
    for stat, weight in (action_scalars or {}).items()
)
dmg_per_hit = scalar_total + BaseDamage
total = dmg_per_hit * Hits

# NPC vs Player: multiply by enemy_damage_multiplier
if isinstance(attacker, NPC) and isinstance(target, PlayerObject) and total > 0:
    total = ceil(total * settings.enemy_damage_multiplier)

# Defense Modifier (target's buffs reduce/increase incoming damage)
def_mod = sum(b["Value"] for b in target.Buffs if b["Type"] == "Defense Modifier")
if total > 0 and def_mod:
    total = max(1, total - def_mod)

# Negative total = healing
```

### 13.8 Initiative Formula

```python
dex_mod = stat_mod(combatant.Stats.get("Dex", 0))
initiative = dex_mod + random.randint(1, 20)
```

### 13.9 Turn End Processing

At the end of every combatant's turn (`PLAYER_END_TURN` or `DM_NPC_END_TURN`):
1. Apply HP Over Time buffs individually (heals before damage) — see §14.
2. Tick all buff durations by 1 minute; remove expired.
3. Broadcast STATE_PATCH with entity update.
4. Advance to next turn (`advance_turn(combat)`).

### 13.10 Long Rest (DM button)

Resets all `action["Casts"]["remaining"] = max_per_rest` for every Action on every player and NPC. Broadcasts STATE_PATCH + system chat.

### 13.11 Combat Chat

| Event | Tag | Color |
|---|---|---|
| Damage dealt | `combat_damage` | `#ff4444` red |
| HP restored | `combat_heal` | `#44ff88` green |
| Fizzle (empty cell) | `combat_fizzle` | `#888888` grey |

---

## 14. Buff System

### 14.1 Buff Types

| Type | Effect |
|---|---|
| **HP Over Time** | Positive Value = heal; negative = damage. Applied individually per buff at each tick. |
| **Stat Modifier** | `effective_stat(entity, key) += buff.Value` when `buff.Stat == key`. |
| **Turn Modifier** | On application during combat: adds `Value` extra initiative slots. Works for players and NPCs. |
| **Defense Modifier** | `final_damage = max(raw_damage - sum_of_all_DefMod_values, 1)`. Negative value = extra damage taken. |

### 14.2 HP Over Time Application Order

Each tick (turn-end in combat, 60 s out of combat):
1. Collect all "HP Over Time" buffs from entity.
2. Apply **all heals** (positive Value) individually first.
3. Apply **all damages** (negative Value) individually second.
4. Each buff fires its own chat message:
   - Heal: `"{name} regenerates {amt} HP from [{buff_name}]."` -> `combat_heal`
   - Damage: `"{name} takes {amt} damage from [{buff_name}]."` -> `combat_damage`

### 14.3 Duration Ticking

- **In combat**: 1 minute decremented when the **buffed entity's** turn ends.
- **Out of combat**: 1 minute decremented every 60 s by the server's `_buff_tick_loop`.
- At `Duration <= 0`: buff entry removed from list. Out-of-combat NPC death from DoT removes the NPC from the grid.

### 14.4 Applying Buffs

Via `Action.GivesBuffs` list — applied to the target on hit (fizzle does NOT apply buffs). Same-named buff replaces the existing entry. `Dispell` (Name = "Dispell") clears all buffs. Buff with `Value=0, Duration=0` removes the named buff only.

### 14.5 Buffs Data on Entities

`PlayerObject.Buffs` and `NPC.Buffs` are both `List[dict]`. Old saves with legacy `Dict[str, dict]` format are automatically migrated in `from_dict()`. Effective stat calculation uses Stat Modifier buffs from this list.

### 14.6 Saving Throws (optional per-buff)

A buff may carry:
```python
"HasSavingThrow": True,
"SavingThrow":    {"Con": 12}   # stat key -> DC threshold
```

Before the buff ticks (applies its effect or ticks its duration), the server rolls:
```
roll = stat_mod(entity.Stats[stat]) + randint(1, 20)
```
If `roll >= threshold` for any non-zero SavingThrow entry, the buff is **immediately removed** without applying its effect. A system chat message announces the successful save: `"{name} succeeded a saving throw for [{buff_name}]."`.

### 14.7 Removed Hardcoded Buffs

"Poison" and "Burn" as hardcoded buff types no longer exist. Their behavior is replicated via HP Over Time (for damage) combined with Stat Modifier buffs (for stat penalties) through the Action GivesBuffs system.

---

## 15. Player Capabilities

### 15.1 Movement

PC moves to an **orthogonally adjacent** cell that is:
- `walkable = True` (ground tile `tile_type = "ground"`) **or** `tile_type = "water"` (players may walk on water)
- Not occupied by NPC, **Wall**, or another Player
- Not a Door with `Open = False`

Via WASD / arrow keys (also triggers `PLAYER_MOVE`; panning is not available to PC), or left-click adjacent cell.

**Movement is blocked** while a Door or Stairs confirmation panel is open.

#### Water & Drowning

- Players may freely step onto water tiles.
- The server tracks consecutive ticks spent on water per player (`_water_ticks`).
- After **5 ticks** (turn-ends in combat, or 60-second real-time ticks out of combat), a **"Drowning"** buff is applied:
  ```python
  {"Name": "Drowning", "Type": "HP Over Time",
   "Value": -int(hp_base_multiplier), "Duration": 99999.0}
  ```
  Damage equals the session's `hp_base_multiplier` per tick.
- When a player **steps off water** (server-side, on the PLAYER_MOVE handler), Drowning is removed immediately and the water tick counter resets to 0.
- NPCs cannot walk on water (no special case in DM_NPC_MOVE).

### 15.2 Cell Interactions (left-click adjacent; 8 directions)

| Cell content | Interaction |
|---|---|
| Door | `DoorInteractionDialog` opens at **top-centre** (background stays visible). Locked door shows error; broken door disables button. |
| NPC | Context: Inspect / Action |
| Item | Context: Pick Up / Inspect |
| Player | Show PlayerStatsTooltip |

**Left-click own cell** when standing on Stairs or Item: Ground interaction.
- Stairs: re-trigger `StairPromptDialog` (top-centre, background visible). Note: prompt is **only shown when stepping onto stairs via WASD** — teleporting to a paired stair does NOT trigger the prompt.
- Item: Pick Up / Inspect.

### 15.3 Keys

| Key | Action |
|---|---|
| WASD / Arrows (PC) | Move player one tile |
| WASD / Arrows (DM) | Smooth camera pan (hold to repeat) |
| Scroll wheel (DM only) | Zoom in/out (ignored for PC) |
| ESC | Toggle ESC menu |
| TAB or O | Toggle Player List overlay |
| B | Toggle Inventory |
| C | Toggle Stats view |
| ENTER | Focus chat input |
| SPACE | End turn early (forfeit remaining points) |
| ESC (chat focused) | Blur chat, do not send |
| ENTER (chat focused) | Send message |
| TAB (chat focused, after /) | Autocomplete |
| [ / ] (DM only) | Decrease / increase paintbrush size |

All keys suppressed when any `tk.Entry` or `tk.Text` has keyboard focus. ESC, TAB/O, B, C all **toggle** — pressing again closes the panel.

### 15.4 Stats View (C key)

Shows: alias, Level, HP, Size, all stats with equipment bonuses and buff modifiers. "Edit Stats" sub-view: spinboxes with live clamping. Confirm -> `STATS_UPDATE`.

### 15.5 Player List (TAB/O key)

Overlay panel: color swatch, avatar, name, latency (ms) or "HOST".

---

## 16. Host (DM) Capabilities

### 16.1 Tile Management

See §11.2.

### 16.2 Object Management

- **Drag and drop**: left-click occupied cell -> drag to valid destination. Ghost sprite follows cursor. Invalid drop = cancel (no server message).
- **Spawn**: right-click -> context menu (§12.5).
- **Modify**: right-click occupant -> Modify Object.
- **Delete**: right-click -> Delete [type].

### 16.3 Warp Players

Right-click walkable cell in a connected component of >= 16 tiles -> "Warp Players Here". Server BFS assigns one unique cell per connected player; sends CAMERA_CENTER to each.

### 16.4 Player Management (right-click player sprite)

- **Level Up**: Level += 1, MaxHP recalculated, full heal.
- **Modify Player**: edit Stats via dialog, patch via DM_MODIFY_PLAYER.
- **Options**: Disconnect (1-min temp ban) or Ban (permanent).

### 16.5 Encounter & Combat

- **Add/Remove From Encounter**: right-click NPC.
- **Start Combat** (full-width button, shows "N in encounter"): triggers initiative rolls, populates turn queue.
- **End Combat**: clears active flag; encounter_npc_ids preserved.
- **Long Rest**: resets all Casts remaining.

### 16.6 NPC Chat Impersonation (out of combat)

DM right-click any NPC → **Speak as NPC…** opens a right-side Panel with a multi-line textarea. Submitting sends `DM_CHAT_AS_NPC{npc_id, text}`. The server broadcasts a normal-type chat message with `sender_alias = NPC.Name` and tags it as an NPC message.

### 16.7 DM ESC Menu

| Option | Notes |
|---|---|
| Main Menu | Sends DISCONNECT to all players, navigates home |
| Game Settings | Adjust settings; recalculates all MaxHP |
| Save & Quit | Name prompt if Untitled; broadcasts warning; saves; disconnects all |
| Quit | Close application |

---

## 17. Inventory & Equipment System

### 17.1 Equipment Slots

```
1: Head    2: Chest    3: Legs    4: Feet
5: Ring    6: Trinket  7: Main Hand  8: Off Hand
```

One item per slot. Equipping to occupied slot swaps old item to Inventory.

### 17.2 Inventory Dialog (B key)

5-column 64x64px grid. Right-click item -> Use (Consumable) / Equip / Drop / Discard.
- **Use**: removes from Inventory; text bubble above player.
- **Equip**: moves to Equipment slot (item must have EquipmentSlot defined).
- **Drop**: BFS finds nearest empty unoccupied ground; places as world object.
- **Discard**: confirm -> permanently removed.

### 17.3 Effective Stats Calculation

```python
effective = base_stat
           + sum(equip.Stats.get(key, 0) for equip in Equipment.values() if equip.Stats)
           + sum(b["Value"] for b in Buffs
                 if b["Type"] == "Stat Modifier" and b.get("Stat") == key)
```

Shown as `"STR   8   (+2 equip) = 10"`.

### 17.4 Actions in Combat

Available attack actions = "Attack (default)" + all `Actions` from all equipped items. Actions with Casts show `[N/M]` remaining; greyed out at 0.

---

## 18. Stairs System

### 18.1 Properties

Stairs placed via DM right-click -> Spawn Stairs (defaults: Name="Stairs", Direction="Up", no link). DM edits via Modify Stairs dialog:
- **Name**: freeform (visible to DM only; players see "Stairs Up/Down" on hover).
- **Direction**: Up | Down (dropdown).
- **Linked Stair**: dropdown showing `<Name>:(<x>,<y>)` for all other Stairs; stores UUID.
- **Coords** and **UUID**: read-only display.

### 18.2 Bidirectional Linking (server-enforced)

When Stair A's `LinkedStair` changes to B at modify time:
1. A's old partner (if any): `LinkedStair = ""`.
2. B's old partner (if any): `LinkedStair = ""`.
3. `B.LinkedStair = A.id`.
4. `A.LinkedStair = B.id`.

All changes broadcast in a single STATE_PATCH.

### 18.3 Player Traversal

When PC **steps onto a Stairs cell via WASD** (Chebyshev distance == 1):
1. Server broadcasts STATE_PATCH (player moved).
2. Client detects `dist == 1` step-onto-stairs -> 60 ms delay -> `StairPromptDialog`.

Teleportation (PLAYER_TAKE_STAIRS arriving at destination) does **not** retrigger the prompt.

**StairPromptDialog**: `Panel` subclass with `placement="top"` — appears at top-centre of the screen; no dark backdrop, game canvas stays fully visible. "Proceed up/down the stairs?" + Yes / No.
- **Yes + LinkedStair set**: `PLAYER_TAKE_STAIRS{stair_id}` -> server validates, moves player to destination, STATE_PATCH + CAMERA_CENTER.
- **No**: closes; player stays.

**Re-trigger**: left-click own cell while standing on Stairs.

### 18.4 Rendering

Stairs Up: `#3388bb` rectangle (4px inset padding) + centred `▲` white bold.  
Stairs Down: `#883388` rectangle + centred `▼` white bold.

---

## 19. Chat System

### 19.1 ChatWidget

Dimensions: 380x180 px. Placed bottom-left, floating over canvas.
- Background: `#141420` (dark, opacity-approximating).
- Scrollbar: overlaid inside text area, 6px wide, dark grey.
- Entry: dark background when unfocused; white background, black text when focused.

### 19.2 Message Types & Colors

| msg_type | Color | Format |
|---|---|---|
| `normal` | `#e6e6f0` | `Alias: message` |
| `yell` | `#f07060` (salmon) | `Alias yells: message` |
| `whisper_in / out` | `#9090cc` (blue) | `[To/From Alias]: message` |
| `system` | `#888888` | message only |
| `error` | `#cc3333` | message only |
| `combat_damage` | `#ff4444` | message only |
| `combat_heal` | `#44ff88` | message only |
| `combat_fizzle` | `#888888` | message only |
| DM sender | `#ff9500` orange | `[DM] Alias: message` |
| Player sender | Saturation-boosted assigned color | `Alias: message` |

### 19.3 Chat Commands

| Command | Effect |
|---|---|
| `/y <msg>` | Yell (broadcast, salmon) |
| `/w <alias> <msg>` | Whisper (private, both see it) |
| `/r` | Pre-fill entry with `/w <last_whisper_sender> ` |
| `/r <msg>` | Reply directly to last whisper sender |
| `/help` | Local help text (not sent to server) |

Tab autocomplete cycles: `/y `, `/w `, `/r `, `/help`. Pressing TAB a second time expands to player/NPC alias after `/w `.

The `/as` command has been **removed**. Use the "Speak as NPC…" right-click menu item instead (see §16.6).

### 19.4 NPC Impersonation

Two paths for DM to speak as an NPC:

- **Combat auto-impersonation**: when it is an NPC's turn in combat, the chat entry shows `[As <NPC.Name>]` prefix; messages auto-route as NPC speech (`DM_CHAT_AS_NPC`). Clears when the NPC's turn ends.
- **Out-of-combat**: right-click NPC → **Speak as NPC…** (see §16.6).

### 19.5 Chat Bubbles

A text bubble appears above the entity sprite for 3 seconds after a message is sent:

- **Follows the entity**: bubble position is resolved every render frame from the entity's current cell, so bubbles follow moving players and NPCs.
- **Whispers**: bubble shown only on the sender's and recipient's client.
- **DM messages**: the DM does **not** get a chat bubble for their own out-of-character speech. When the DM speaks as an NPC (via "Speak as NPC…" or combat auto-impersonation), the NPC's sprite gets the bubble.
- **Player aliases** must not contain spaces (enforced in Profile screen).

### 19.6 Chat Persistence

All messages except whispers stored in `GameState.chat_history`. Replayed on load. NPC impersonation messages saved with `sender_alias = NPC.Name`.

---

## 20. Save & Load System

### 20.1 Save File Naming

```
saves/<GameName>.sav                    <- first save
saves/<GameName>_YYYYMMDD_HHMMSS.sav   <- subsequent saves
```

### 20.2 Format

msgpack + zlib (level 9). Tuple grid keys as `"x,y"` strings. Avatar PNG as base64 in `avatar_cache`. `Buffs` migrated from legacy dict format on load.

### 20.3 Save & Quit Flow (DM)

1. If name is "Untitled": prompt for name (Panel).
2. Broadcast system chat: "Host is saving and closing."
3. Server disconnects all clients.
4. Record `host_view` and `host_zoom`.
5. Write save file; navigate to main menu.

### 20.4 Load Game Dialog

Lists saves sorted newest-first. Format: `"<GameName>   |   <alias1>, <alias2>"`. Select -> Start or Delete (with confirmation). DM viewport restored to saved `host_view` / `host_zoom`.

### 20.5 Combat Save / Load

If loaded with `combat.active == True`, combat resumes from saved state. Players absent from the queue are removed; DM warned if player count differs.

---

## 21. Settings & Banlist

### 21.1 Gear Icon

On main menu, top-right. Opens `BanlistDialog`: lists ban records (alias, truncated UUID, banned-at, status). Expired temp-blocks shown in muted grey with asterisk. Trash icon per row -> confirm -> delete.

### 21.2 Game Settings (DM ESC Menu)

Adjusts `hp_base_multiplier`, `enemy_damage_multiplier`, `los_max_distance`. Applying recalculates all NPC and player `MaximumHP`; CurrentHP clamped.

### 21.3 Ban Records

```json
{"uuid": "...", "alias": "...", "banned_at": "ISO8601", "expires_at": null, "reason": "ban|temp_disconnect"}
```

`expires_at = null` -> permanent. Temp-disconnect expires after 60 s.

---

## 22. Build & Distribution

### 22.1 Build Script (`build.bat` only)

Steps:
1. Locate Python 3.9+ (PATH then common install locations).
2. Create `.venv` if not present.
3. Install `Pillow>=10.0`, `msgpack>=1.0`, `pyinstaller>=6.0`.
4. `pyinstaller --clean --noconfirm Steel2D.spec` -> `dist/Steel2D/`.
5. Deletes any existing `Steel2D-*.zip` in the project root, then PowerShell `Compress-Archive 'dist\Steel2D' -> 'Steel2D.zip'` in the project root (non-fatal if PowerShell unavailable).

### 22.2 Output

| Path | Purpose |
|---|---|
| `dist/Steel2D/Steel2D.exe` | Launch directly (double-click) |
| `dist/Steel2D/` | Full distributable folder |
| `Steel2D.zip` | Portable archive in **project root**; share this |

Zip structure: `Steel2D.zip -> Steel2D/ -> Steel2D.exe + _internal/...`

Only one build zip exists in the project root at a time — previous ones are deleted before the new zip is created.

Recipients extract zip, enter `Steel2D/`, double-click `Steel2D.exe`. No Python or install required.

### 22.3 User Data

All runtime data goes to `%APPDATA%\Steel2D\` (frozen) or project root (dev):
- `user.config`, `game_config.json`, `banlist.json`
- `saves/*.sav`
- `prefabs/*.json`

---

## 23. Keybindings Reference

### Game Screen — PC

| Key | Action |
|---|---|
| `W A S D` / Arrows | Move player (one tile per press) |
| Left click adjacent cell | Move or interact |
| Left click own cell | Ground context (Stairs prompt / Item pickup) if applicable |
| `ESC` | Toggle ESC menu |
| `TAB` or `O` | Toggle Player List overlay |
| `B` | Toggle Inventory |
| `C` | Toggle Stats view |
| `ENTER` | Focus chat input |
| `SPACE` | End turn (forfeit remaining budget) |
| `ESC` (chat focused) | Blur chat (no send) |
| `ENTER` (chat focused) | Send message |
| `TAB` (chat, after `/`) | Autocomplete command / alias |
| Scroll wheel | Ignored (PC camera is always locked; no zoom) |

### Game Screen — DM

| Key | Action |
|---|---|
| `W A S D` / Arrows (held) | Smooth camera pan (9 canvas px/frame / zoom) |
| Left click empty tile | Create ground tile |
| Left drag (from ground or black) | Paint ground; clear walls on pass-over |
| `U` + left drag | Paint water tiles |
| `Y` + left drag | Spawn walls (auto-converts non-ground) |
| Middle click + drag | Delete tiles (ground/water) |
| Right click | Context menu (see §12.5) |
| Left click adjacent ground (NPC combat turn) | Move active NPC |
| `SPACE` (NPC combat turn) | End NPC turn early |
| All other keys | Same as PC column |

*All WASD/movement keys suppressed while any `tk.Entry` or `tk.Text` widget holds keyboard focus.*

---

*End of Requirements Document v0.15*
