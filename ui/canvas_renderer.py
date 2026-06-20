from __future__ import annotations
import math
import time
import tkinter as tk
from tkinter import Menu
from typing import Optional, Callable, Tuple, Dict, List, Set, TYPE_CHECKING

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from app.constants import BASE_CELL_PX, ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, PALETTE
from game.objects import NPC, Item, Door, Wall, Stairs, PlayerObject
from game.state import GameState
from game.los import has_los, cells_in_range

if TYPE_CHECKING:
    pass


class GameCanvas(tk.Canvas):
    def __init__(self, parent, state: GameState, local_uuid: str,
                 is_dm: bool, send_fn: Callable, open_context_fn: Callable,
                 **kwargs):
        super().__init__(parent, bg=PALETTE["canvas_bg"],
                         highlightthickness=0, **kwargs)
        self.state = state
        self.local_uuid = local_uuid
        self.is_dm = is_dm
        self.send = send_fn
        self.open_context = open_context_fn

        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        self.zoom: float = 1.0

        self._drag_source: Optional[Tuple[int, int]] = None
        self._drag_mouse: Optional[Tuple[int, int]] = None
        self._drag_obj = None
        self._painting: bool = False
        self._paint_type: str = "ground"   # "ground" | "water" | "wall"
        self._painted_cells: Set[Tuple[int, int]] = set()
        self._erasing: bool = False
        self._erased_cells: Set[Tuple[int, int]] = set()
        # Set by GameScreen key bindings
        self.u_held: bool = False
        self.y_held: bool = False
        self._erasing: bool = False
        self._erased_cells: Set[Tuple[int, int]] = set()
        # Paintbrush size (1 = single cell, N = Chebyshev radius N-1)
        self.brush_size: int = 1

        self.bubbles: List[dict] = []

        self._combat_action: Optional[dict] = None
        self._valid_targets: Set[Tuple[int, int]] = set()

        self._hover_cell: Optional[Tuple[int, int]] = None
        self._img_cache: Dict[Tuple, object] = {}
        self._anim_frame = 0

        # ── Water depth colours (precomputed from base) ───────────────────────
        # Four variants: depth 0 (shallow) → 3 (deep).
        # Each deeper level: brightness −12.5 %, saturation +12.5 %.
        import colorsys as _cs
        _b = "#a8d8ea"
        _rv = int(_b[1:3], 16) / 255
        _gv = int(_b[3:5], 16) / 255
        _bv = int(_b[5:7], 16) / 255
        _h, _s, _v = _cs.rgb_to_hsv(_rv, _gv, _bv)
        self._WATER_COLORS: list = []
        for _depth in range(4):
            _as = min(1.0, _s + _depth * 0.125)
            _av = max(0.0, _v - _depth * 0.125)
            _r2, _g2, _b2 = _cs.hsv_to_rgb(_h, _as, _av)
            self._WATER_COLORS.append(
                "#{:02x}{:02x}{:02x}".format(
                    int(_r2 * 255), int(_g2 * 255), int(_b2 * 255)))

        # Water depth cache — invalidated whenever cells change
        self._water_depth_cache: Dict[Tuple[int, int], int] = {}
        self._water_cache_key: int = 0   # id() of grid dict as proxy for change

        # Single binding per button — <Button-1> and <ButtonPress-1> are
        # the same Tk event; binding both overwrites the first.
        self.bind("<Motion>",          self._on_motion)
        self.bind("<Button-1>",        self._on_left_press)
        self.bind("<B1-Motion>",       self._on_drag_move)
        self.bind("<ButtonRelease-1>", self._on_drag_end)
        self.bind("<Button-3>",        self._on_right_click)
        self.bind("<Button-2>",        self._on_middle_press)
        self.bind("<B2-Motion>",       self._on_middle_drag)
        self.bind("<ButtonRelease-2>", self._on_middle_release)
        self.bind("<MouseWheel>",      self._on_scroll)

        self._redraw()

    # ── public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        pass

    def center_on_cell(self, x: int, y: int) -> None:
        w = self.winfo_width() or 800
        h = self.winfo_height() or 600
        cell_px = BASE_CELL_PX * self.zoom
        cx = x * BASE_CELL_PX + BASE_CELL_PX / 2
        cy = y * BASE_CELL_PX + BASE_CELL_PX / 2
        self.offset_x = cx - w / (2 * self.zoom)
        self.offset_y = cy - h / (2 * self.zoom)

    def add_bubble(self, msg: dict) -> None:
        sender = msg.get("sender_uuid", "")
        if sender.startswith("NPC:"):
            npc_id = sender[4:]
            npc_cell = self.state.find_object_cell(npc_id)
            if npc_cell:
                self.bubbles.append({
                    "cell": npc_cell,
                    "text": msg.get("content", "")[:60],
                    "color": _tag_color(msg.get("msg_type", "normal")),
                    "born_at": time.time(),
                    "player_uuid": None,
                })
            return
        cell_key = f"{0},{0}"
        for key, uuids in self.state.players_at.items():
            if sender in uuids:
                cell_key = key
                break
        if cell_key:
            x, y = map(int, cell_key.split(","))
            self.bubbles.append({
                "cell": (x, y),
                "text": msg.get("content", "")[:60],
                "color": _tag_color(msg.get("msg_type", "normal")),
                "born_at": time.time(),
                "player_uuid": sender,
            })

    def set_combat_action(self, action_dict: Optional[dict], targets: set) -> None:
        self._combat_action = action_dict
        self._valid_targets = targets

    def pan(self, dx: float, dy: float) -> None:
        self.offset_x += dx
        self.offset_y += dy

    # ── render loop ───────────────────────────────────────────────────────────

    def _redraw(self) -> None:
        try:
            self.delete("all")
            self._anim_frame = (self._anim_frame + 1) % 60
            now = time.time()
            self.bubbles = [b for b in self.bubbles if now - b["born_at"] < 3.0]

            w = self.winfo_width() or 800
            h = self.winfo_height() or 600
            cell_px = BASE_CELL_PX * self.zoom

            min_cx = int(self.offset_x / BASE_CELL_PX) - 1
            max_cx = int((self.offset_x + w / self.zoom) / BASE_CELL_PX) + 2
            min_cy = int(self.offset_y / BASE_CELL_PX) - 1
            max_cy = int((self.offset_y + h / self.zoom) / BASE_CELL_PX) + 2

            self._draw_grid(w, h, cell_px)
            self._draw_tiles(min_cx, max_cx, min_cy, max_cy, cell_px)
            self._draw_combat_highlights(cell_px)
            self._draw_objects(min_cx, max_cx, min_cy, max_cy, cell_px)
            self._draw_players(cell_px)
            self._draw_bubbles(cell_px)
            self._draw_drag_ghost(cell_px)
            self._draw_tooltip(cell_px)
        except Exception:
            pass
        finally:
            self.after(16, self._redraw)

    def _world_to_canvas(self, wx: float, wy: float) -> Tuple[float, float]:
        return (wx - self.offset_x) * self.zoom, (wy - self.offset_y) * self.zoom

    def _canvas_to_cell(self, cx: float, cy: float) -> Tuple[int, int]:
        wpx = cx / self.zoom + self.offset_x
        wpy = cy / self.zoom + self.offset_y
        return int(wpx // BASE_CELL_PX), int(wpy // BASE_CELL_PX)

    def _cell_rect(self, gx: int, gy: int, cell_px: float) -> Tuple[float, float, float, float]:
        wx = gx * BASE_CELL_PX
        wy = gy * BASE_CELL_PX
        cx, cy = self._world_to_canvas(wx, wy)
        return cx, cy, cx + cell_px, cy + cell_px

    def _draw_grid(self, w: int, h: int, cell_px: float) -> None:
        color = PALETTE["grid"]
        x = -self.offset_x * self.zoom % cell_px
        while x < w:
            self.create_line(x, 0, x, h, fill=color, width=1)
            x += cell_px
        y = -self.offset_y * self.zoom % cell_px
        while y < h:
            self.create_line(0, y, w, y, fill=color, width=1)
            y += cell_px

    _GROUND_COLOR = "#ffffff"

    def _draw_tiles(self, min_cx, max_cx, min_cy, max_cy, cell_px) -> None:
        pad = 2 * self.zoom
        grid = self.state.grid

        # Invalidate water depth cache when the grid changes
        grid_key = id(grid) ^ len(grid)
        if grid_key != self._water_cache_key:
            self._water_cache_key = grid_key
            self._water_depth_cache = {}

        def _water_neighbor(nx, ny) -> bool:
            c = grid.get((nx, ny))
            return c is not None and c.tile_type == "water"

        for (gx, gy), cell in grid.items():
            if not (min_cx <= gx <= max_cx and min_cy <= gy <= max_cy):
                continue
            tile_type = cell.tile_type
            if tile_type == "ground":
                x0, y0, x1, y1 = self._cell_rect(gx, gy, cell_px)
                self.create_rectangle(x0 + pad, y0 + pad, x1 - pad, y1 - pad,
                                      fill=self._GROUND_COLOR, outline="", tags="tile")
            elif tile_type == "water":
                x0, y0, x1, y1 = self._cell_rect(gx, gy, cell_px)
                # Extend toward adjacent water to close inter-cell gaps
                ax0 = x0 if _water_neighbor(gx - 1, gy) else x0 + pad
                ay0 = y0 if _water_neighbor(gx, gy - 1) else y0 + pad
                ax1 = x1 if _water_neighbor(gx + 1, gy) else x1 - pad
                ay1 = y1 if _water_neighbor(gx, gy + 1) else y1 - pad
                # Depth-based colour
                depth = self._water_depth_cache.get((gx, gy))
                if depth is None:
                    depth = self._compute_water_depth(gx, gy)
                    self._water_depth_cache[(gx, gy)] = depth
                color = self._WATER_COLORS[depth]
                self.create_rectangle(ax0, ay0, ax1, ay1,
                                      fill=color, outline="", tags="tile")

    def _compute_water_depth(self, gx: int, gy: int) -> int:
        """Return depth 0-3 based on distance to nearest ground tile (Chebyshev)."""
        grid = self.state.grid
        min_dist = 5   # sentinel — no ground found within search radius
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                d = max(abs(dx), abs(dy))   # Chebyshev distance
                if d >= min_dist:
                    continue
                c = grid.get((gx + dx, gy + dy))
                if c and c.tile_type == "ground":
                    min_dist = d
                    if min_dist <= 2:
                        break           # can't get better than ≤ 2
            if min_dist <= 2:
                break
        # Map distance → depth level
        if min_dist <= 2:
            return 0
        elif min_dist == 3:
            return 1
        elif min_dist == 4:
            return 2
        else:
            return 3

    def _draw_combat_highlights(self, cell_px: float) -> None:
        if not (self.state.combat and self.state.combat.active):
            return
        tq = self.state.combat.turn_queue
        if not tq:
            return
        cur = tq[self.state.combat.current_index]

        cur_cell = self._find_combatant_cell(cur)
        if cur_cell and cur.can_move:
            cx, cy = cur_cell
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = cx + dx, cy + dy
                nc = self.state.grid.get((nx, ny))
                if nc and nc.walkable and not nc.occupant:
                    x0, y0, x1, y1 = self._cell_rect(nx, ny, cell_px)
                    self.create_rectangle(x0, y0, x1, y1,
                                         fill="#3399ff", stipple="gray25",
                                         outline="#3399ff", tags="highlight")

        if self._valid_targets:
            for (tx, ty) in self._valid_targets:
                x0, y0, x1, y1 = self._cell_rect(tx, ty, cell_px)
                self.create_rectangle(x0, y0, x1, y1,
                                      fill="#ff4400", stipple="gray25",
                                      outline="#ff4400", tags="highlight")

        # Glow removed per request (item 3)

    def _find_combatant_cell(self, turn) -> Optional[Tuple[int, int]]:
        if turn.combatant_type == "player":
            for key, uuids in self.state.players_at.items():
                if turn.id in uuids:
                    x, y = map(int, key.split(","))
                    return (x, y)
        else:
            return self.state.find_object_cell(turn.id)
        return None

    def _draw_objects(self, min_cx, max_cx, min_cy, max_cy, cell_px) -> None:
        for (gx, gy), cell in self.state.grid.items():
            if not cell.occupant:
                continue
            if not (min_cx <= gx <= max_cx and min_cy <= gy <= max_cy):
                continue
            x0, y0, x1, y1 = self._cell_rect(gx, gy, cell_px)
            obj = cell.occupant
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            pad = max(4 * self.zoom, 4)

            if isinstance(obj, NPC):
                self._draw_npc(obj, x0, y0, x1, y1, cx, cy, pad)
            elif isinstance(obj, Item):
                self._draw_item(x0, y0, x1, y1, cx, cy, cell_px)
            elif isinstance(obj, Door):
                self._draw_door(obj, x0, y0, x1, y1, cx, cy)
            elif isinstance(obj, Wall):
                self._draw_wall(gx, gy, x0, y0, x1, y1)
            elif isinstance(obj, Stairs):
                self._draw_stairs(obj, x0, y0, x1, y1, cx, cy)

    def _draw_npc(self, npc: NPC, x0, y0, x1, y1, cx, cy, pad) -> None:
        size = min(x1 - x0, y1 - y0) * 0.595
        # Icon floats from the bottom of the tile.
        # Tile has 2*zoom inward pad; leave an additional 4*zoom gap above tile edge.
        icon_bottom = y1 - 2 * self.zoom - 4 * self.zoom
        if npc.Hostile:
            s = size
            h_tri = s * 0.866   # equilateral triangle height
            base_y = icon_bottom
            apex_y = base_y - h_tri
            pts = [cx, apex_y, cx - s / 2, base_y, cx + s / 2, base_y]
            self.create_polygon(pts, fill="#cc2222", outline="#880000", width=2)
        else:
            r = size / 2
            center_y = icon_bottom - r
            self.create_oval(cx - r, center_y - r, cx + r, center_y + r,
                             fill="#22aa22", outline="#115511", width=2)
        self._draw_hp_bar(npc, x0, y0, x1)

    def _draw_hp_bar(self, entity, x0, y0, x1) -> None:
        if not self.is_dm:
            return
        pad_side = 10 * self.zoom
        bw = (x1 - x0) - pad_side * 2
        bh = max(3, 4 * self.zoom)
        by = y0 + 8 * self.zoom
        ratio = entity.CurrentHP / max(entity.MaximumHP, 1)
        # 2px black outer border
        self.create_rectangle(x0 + pad_side - 2, by - 2,
                              x1 - pad_side + 2, by + bh + 2,
                              fill="#000000", outline="")
        self.create_rectangle(x0 + pad_side, by, x1 - pad_side, by + bh,
                              fill="#333", outline="")
        self.create_rectangle(x0 + pad_side, by,
                              x0 + pad_side + bw * ratio, by + bh,
                              fill="#44ee44", outline="")

    def _draw_item(self, x0, y0, x1, y1, cx, cy, cell_px) -> None:
        outer = min(x1 - x0, y1 - y0) * 0.38
        inner = outer * 0.47
        pts = []
        for i in range(8):
            angle = math.radians(i * 45)
            r = outer if i % 2 == 0 else inner
            pts += [cx + r * math.cos(angle), cy + r * math.sin(angle)]
        self.create_polygon(pts, fill="#ff8800", outline="#000000", width=2)

    def _draw_door(self, door: Door, x0, y0, x1, y1, cx, cy) -> None:
        pad = 2
        if door.Open:
            self.create_rectangle(x0 + pad, y0 + pad, x1 - pad, y1 - pad,
                                  fill="", outline="#8b4513", width=6)
        else:
            self.create_rectangle(x0 + pad, y0 + pad, x1 - pad, y1 - pad,
                                  fill="#8b4513", outline="#5c2d0a", width=2)
        if door.Broken:
            self.create_line(x0 + pad, y0 + pad, x1 - pad, y1 - pad,
                             fill="#333", width=1)
            self.create_line(x0 + pad, y1 - pad, x1 - pad, y0 + pad,
                             fill="#333", width=1)
        if door.Locked:
            s = min(x1 - x0, y1 - y0) * 0.2
            self.create_oval(cx - s, cy - s, cx + s, cy + s,
                             fill="#ffcc00", outline="#cc9900", width=1)

    def _draw_stairs(self, stairs: Stairs,
                    x0: float, y0: float, x1: float, y1: float,
                    cx: float, cy: float) -> None:
        UP_COLOR   = "#3388bb"   # blue for going up
        DOWN_COLOR = "#883388"   # purple for going down
        pad = 4 * self.zoom
        color = UP_COLOR if stairs.Direction == "Up" else DOWN_COLOR
        arrow = "▲" if stairs.Direction == "Up" else "▼"
        self.create_rectangle(x0 + pad, y0 + pad, x1 - pad, y1 - pad,
                              fill=color, outline="#ffffff", width=1, tags="stairs")
        font_size = max(8, int((x1 - x0 - pad * 2) * 0.45))
        self.create_text(cx, cy, text=arrow, fill="#ffffff",
                         font=("Segoe UI", font_size, "bold"), tags="stairs")

    def _draw_wall(self, gx: int, gy: int,
                   x0: float, y0: float, x1: float, y1: float) -> None:
        WALL_COLOR = "#888888"
        pad = 2 * self.zoom

        def _has_wall(nx, ny) -> bool:
            c = self.state.grid.get((nx, ny))
            return c is not None and isinstance(c.occupant, Wall)

        # Extend toward each neighbor that also has a wall,
        # filling the 2-pad gap between adjacent tiles.
        ax0 = x0 if _has_wall(gx - 1, gy) else (x0 + pad)
        ay0 = y0 if _has_wall(gx, gy - 1) else (y0 + pad)
        ax1 = x1 if _has_wall(gx + 1, gy) else (x1 - pad)
        ay1 = y1 if _has_wall(gx, gy + 1) else (y1 - pad)

        self.create_rectangle(ax0, ay0, ax1, ay1,
                              fill=WALL_COLOR, outline="", tags="wall")

    def _draw_players(self, cell_px: float) -> None:
        for key, uuids in self.state.players_at.items():
            if not uuids:
                continue
            x, y = map(int, key.split(","))
            for idx, pid in enumerate(uuids):
                player = self.state.players.get(pid)
                if not player:
                    continue
                x0, y0, x1, y1 = self._cell_rect(x, y, cell_px)
                if len(uuids) > 1:
                    offset = idx * cell_px * 0.1
                    x0 += offset
                    y0 += offset
                    x1 += offset
                    y1 += offset
                h_pad = cell_px * 0.175   # 65% fill horizontally
                # Float from bottom: 4*zoom gap above tile bottom edge
                # (tile itself has 2*zoom inward padding)
                icon_bottom = y1 - 2 * self.zoom - 4 * self.zoom
                icon_h = cell_px * 0.65
                icon_top = icon_bottom - icon_h
                self.create_rectangle(x0 + h_pad, icon_top, x1 - h_pad, icon_bottom,
                                      fill=player.color,
                                      outline=_darken(player.color, 0.6),
                                      width=2)
                if player.avatar_png and HAS_PIL:
                    self._draw_avatar(player, x0, icon_top, x1, icon_bottom, cell_px)
                else:
                    abbrev = (player.Name or "?")[:2].upper()
                    self.create_text((x0 + x1) / 2, (icon_top + icon_bottom) / 2,
                                     text=abbrev, fill="#ffffff",
                                     font=("Segoe UI", max(8, int(cell_px * 0.22)), "bold"))
                self._draw_hp_bar(player, x0, y0, x1)

    def _draw_avatar(self, player: PlayerObject, x0, y0, x1, y1, cell_px) -> None:
        size = int(cell_px * 0.75)
        key = (player.id, size)
        if key not in self._img_cache:
            try:
                import io
                img = Image.open(io.BytesIO(player.avatar_png))
                img = img.resize((size, size), Image.LANCZOS)
                self._img_cache[key] = ImageTk.PhotoImage(img)
            except Exception:
                return
        img = self._img_cache.get(key)
        if img:
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            self.create_image(cx, cy, image=img, anchor=tk.CENTER)

    def _draw_bubbles(self, cell_px: float) -> None:
        now = time.time()
        for bubble in self.bubbles:
            cell = bubble.get("cell")
            if not cell:
                continue
            gx, gy = cell
            x0, y0, x1, y1 = self._cell_rect(gx, gy, cell_px)
            cx = (x0 + x1) / 2

            age = now - bubble["born_at"]
            alpha = 1.0
            if age > 2.5:
                alpha = 1.0 - (age - 2.5) / 0.5

            color = bubble["color"]
            if alpha < 0.3:
                continue

            text = bubble["text"]
            font_size = max(7, int(10 * self.zoom))
            bub_w = min(len(text) * font_size * 0.62 + 12, 200 * self.zoom)
            bub_h = 18 * self.zoom
            bub_y = y0 - bub_h - 6

            self.create_rectangle(cx - bub_w / 2, bub_y,
                                  cx + bub_w / 2, bub_y + bub_h,
                                  fill="#111", outline=PALETTE["border"])
            self.create_text(cx, bub_y + bub_h / 2, text=text,
                             fill=color, font=("Segoe UI", font_size))

    def _draw_drag_ghost(self, cell_px: float) -> None:
        if not self._drag_obj or not self._drag_mouse:
            return
        mx, my = self._drag_mouse
        s = cell_px * 0.5
        self.create_rectangle(mx - s, my - s, mx + s, my + s,
                              fill=PALETTE["accent"], outline="#ffffff",
                              stipple="gray50", width=1)

    def _draw_tooltip(self, cell_px: float) -> None:
        if not self._hover_cell:
            return
        gx, gy = self._hover_cell
        cell = self.state.grid.get((gx, gy))
        lines = []

        # Players on this cell
        uuids = self.state.players_at.get(f"{gx},{gy}", [])
        for pid in uuids:
            p = self.state.players.get(pid)
            if p:
                if self.is_dm:
                    lines.append(f"{p.Name}  HP {p.CurrentHP}/{p.MaximumHP}")
                    for k in ("Str", "Dex", "Con", "Int", "Wis", "Cha"):
                        lines.append(f"  {k}: {p.Stats.get(k, 0)}")
                else:
                    lines.append(p.Name)

        # Occupant (NPC / Item / Door)
        npc_included_location = False
        if cell and cell.occupant:
            obj = cell.occupant
            pc = self._player_cell()
            can_see = True
            if not self.is_dm and pc:
                can_see = has_los(self.state, pc, (gx, gy),
                                  self.state.settings.los_max_distance)
            if isinstance(obj, NPC):
                if can_see:
                    if self.is_dm:
                        status = "Hostile" if obj.Hostile else "Friendly"
                        lines += [
                            obj.Name,
                            f"Health: {obj.CurrentHP}/{obj.MaximumHP}",
                            f"Size: {obj.Size}",
                            f"Status: {status}",
                            f"Location: ({gx}, {gy})",
                        ]
                        npc_included_location = True
                    else:
                        lines.append(obj.Name)
                        if obj.Description:
                            lines.append(obj.Description)
            elif isinstance(obj, Item):
                if can_see:
                    lines.append(f"Item: {obj.Name}")
                    if self.is_dm:
                        if obj.Description:
                            lines.append(obj.Description)
                        lines.append(f"Qty: {obj.Quantity}  Val: {obj.Value}g")
                    else:
                        if obj.Description:
                            lines.append(obj.Description)
            elif isinstance(obj, Door):
                if can_see:
                    state_str = "Open" if obj.Open else "Closed"
                    lines.append(f"Door — {state_str}")
                    if obj.Locked:
                        lines.append("Locked")
                    if obj.Broken:
                        lines.append("Broken")
            elif isinstance(obj, Stairs):
                if can_see:
                    if self.is_dm:
                        lines.append(f"Stairs: {obj.Name}")
                        lines.append(f"Direction: {obj.Direction}")
                        if obj.LinkedStair:
                            linked_cell = self.state.find_object_cell(obj.LinkedStair)
                            lines.append(f"Linked: {linked_cell}")
                    else:
                        lines.append(f"Stairs {obj.Direction}")

        # Append coordinates for all non-NPC tooltips (NPC format includes it inline)
        if not lines:
            return
        if not npc_included_location:
            lines.append(f"({gx}, {gy})")


        mx = self.winfo_pointerx() - self.winfo_rootx()
        my = self.winfo_pointery() - self.winfo_rooty()
        font_h = 14
        pad = 6
        tw = max(len(l) for l in lines) * 7 + pad * 2
        th = len(lines) * font_h + pad * 2
        tx = min(mx + 15, self.winfo_width() - tw - 5)
        ty = min(my + 15, self.winfo_height() - th - 5)
        self.create_rectangle(tx, ty, tx + tw, ty + th,
                              fill="#111111", outline=PALETTE["border"])
        for i, line in enumerate(lines):
            self.create_text(tx + pad, ty + pad + i * font_h,
                             text=line, fill=PALETTE["fg"],
                             font=("Segoe UI", 8), anchor="nw")

    # ── input handlers ────────────────────────────────────────────────────────

    def _on_motion(self, event) -> None:
        self._hover_cell = self._canvas_to_cell(event.x, event.y)
        if self._drag_obj:
            self._drag_mouse = (event.x, event.y)

    # ── left mouse (click + paint + object drag) ──────────────────────────────

    def _on_left_press(self, event) -> None:
        gx, gy = self._canvas_to_cell(event.x, event.y)

        if self._combat_action is not None:
            if (gx, gy) in self._valid_targets:
                self.open_context("combat_action_confirm", (gx, gy))
            else:
                self.set_combat_action(None, set())
            return

        if self.is_dm:
            cell = self.state.grid.get((gx, gy))

            # ── DM NPC combat movement (click adjacent ground tile) ──────────
            if (self.state.combat and self.state.combat.active
                    and not self.y_held and not self.u_held):
                ct_idx = self.state.combat.current_index
                if ct_idx < len(self.state.combat.turn_queue):
                    ct = self.state.combat.turn_queue[ct_idx]
                    if ct.combatant_type == "npc" and ct.can_move:
                        npc_cell = self.state.find_object_cell(ct.id)
                        if npc_cell:
                            nx, ny = npc_cell
                            if (abs(gx - nx) + abs(gy - ny) == 1
                                    and cell and cell.walkable
                                    and not cell.occupant
                                    and cell.tile_type == "ground"):
                                self.send({"type": "DM_NPC_MOVE",
                                           "npc_id": ct.id,
                                           "target_cell": [gx, gy]})
                                return

            # ── Block most DM edits during active combat ─────────────────────
            in_combat = bool(self.state.combat and self.state.combat.active)
            if in_combat:
                self._painting = False
                return  # NPC movement (above) already handled; everything else blocked

            # ── Guard: never paint over protected cells ───────────────────────
            if cell and cell.protected and (self.y_held or self.u_held):
                return

            if self.y_held:
                self._painting = True
                self._paint_type = "wall"
                self._painted_cells = set()
                self._apply_brush(gx, gy)
                return

            if self.u_held:
                if (cell and cell.protected) or (cell and cell.occupant):
                    self._painting = False
                    return
                self._painting = True
                self._paint_type = "water"
                self._painted_cells = set()
                self._apply_brush(gx, gy)
                return

            if cell and cell.occupant:
                if isinstance(cell.occupant, Wall):
                    self._painting = True
                    self._paint_type = "wall_clear"
                    self._painted_cells = set()
                    self._apply_brush(gx, gy)
                else:
                    # Object drag — single cell, no brush
                    self._drag_source = (gx, gy)
                    self._drag_obj = cell.occupant
                    self._drag_mouse = (event.x, event.y)
                    self._painting = False
            else:
                if cell and cell.protected:
                    self._painting = False
                    return
                tile_type = cell.tile_type if cell else None
                if cell is None or not cell.walkable or tile_type == "water":
                    self._painting = True
                    self._paint_type = "ground"
                    self._painted_cells = set()
                    self._apply_brush(gx, gy)
                else:
                    self._painting = False
        else:
            pc = self._player_cell()
            if pc:
                px, py = pc
                if (gx, gy) == (px, py):
                    # Clicking own cell — trigger Ground interaction for Stairs / Items
                    gc = self.state.grid.get((gx, gy))
                    if gc and isinstance(gc.occupant, (Stairs, Item)):
                        self.open_context("own_cell_interact", (gx, gy))
                        return
                elif abs(gx - px) <= 1 and abs(gy - py) <= 1:
                    cell = self.state.grid.get((gx, gy))
                    if cell:
                        uuids = self.state.players_at.get(f"{gx},{gy}", [])
                        if cell.occupant or uuids:
                            self.open_context("left_interact", (gx, gy))
                            return
                if abs(gx - px) + abs(gy - py) == 1:
                    self.send({"type": "PLAYER_MOVE", "target_cell": [gx, gy]})

    def _place_wall_at(self, gx: int, gy: int) -> None:
        cell = self.state.grid.get((gx, gy))
        if cell and cell.occupant:
            return
        # Ensure ground tile first
        if cell is None or cell.tile_type != "ground":
            self.send({"type": "DM_TILE_SET",
                       "cell": [gx, gy], "walkable": True, "tile_type": "ground"})
        import uuid as _uuid_mod
        self.send({"type": "DM_SPAWN_OBJECT", "cell": [gx, gy],
                   "object": {"type": "Wall", "id": str(_uuid_mod.uuid4())}})

    def _on_drag_move(self, event) -> None:
        if self._drag_obj:
            self._drag_mouse = (event.x, event.y)
            return
        if not (self._painting and self.is_dm):
            return
        gx, gy = self._canvas_to_cell(event.x, event.y)
        # _apply_brush handles deduplication via _painted_cells internally
        self._apply_brush(gx, gy)

    def _on_drag_end(self, event) -> None:
        self._painting = False
        self._painted_cells = set()
        if not self._drag_obj or not self._drag_source:
            self._drag_obj = None
            self._drag_source = None
            self._drag_mouse = None
            return
        tx, ty = self._canvas_to_cell(event.x, event.y)
        fx, fy = self._drag_source
        if (tx, ty) != (fx, fy):
            target = self.state.grid.get((tx, ty))
            if target and target.walkable and not target.occupant:
                self.send({"type": "DM_MOVE_OBJECT",
                           "from_cell": [fx, fy], "to_cell": [tx, ty]})
        self._drag_obj = None
        self._drag_source = None
        self._drag_mouse = None

    # ── middle mouse (tile eraser) ────────────────────────────────────────────

    def _on_middle_press(self, event) -> None:
        if not self.is_dm:
            return
        if self.state.combat and self.state.combat.active:
            return
        gx, gy = self._canvas_to_cell(event.x, event.y)
        self._erasing = True
        self._erased_cells = set()
        for bx, by in self._brush_cells(gx, gy):
            self._try_erase(bx, by)

    def _on_middle_drag(self, event) -> None:
        if not self._erasing or not self.is_dm:
            return
        gx, gy = self._canvas_to_cell(event.x, event.y)
        for bx, by in self._brush_cells(gx, gy):
            if (bx, by) not in self._erased_cells:
                self._try_erase(bx, by)

    def _on_middle_release(self, event) -> None:
        self._erasing = False
        self._erased_cells = set()

    def _try_erase(self, gx: int, gy: int) -> None:
        cell = self.state.grid.get((gx, gy))
        if not cell:
            return   # nothing to erase
        if cell.protected:
            return
        # Skip if a player is on this cell or within 1-tile radius
        if self.state.players_at.get(f"{gx},{gy}"):
            return
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                if self.state.players_at.get(f"{gx+dx},{gy+dy}"):
                    return
        self._erased_cells.add((gx, gy))
        # Erase regardless of tile type (ground, water) or occupant
        self.send({"type": "DM_TILE_SET", "cell": [gx, gy],
                   "walkable": False, "tile_type": "ground"})

    def _on_right_click(self, event) -> None:
        gx, gy = self._canvas_to_cell(event.x, event.y)
        self.open_context("right_click", (gx, gy), (event.x_root, event.y_root))

    def _on_scroll(self, event) -> None:
        mx, my = event.x, event.y
        wx = mx / self.zoom + self.offset_x
        wy = my / self.zoom + self.offset_y
        delta = 1 if event.delta > 0 else -1
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom + delta * ZOOM_STEP))
        self.zoom = new_zoom
        self.offset_x = wx - mx / new_zoom
        self.offset_y = wy - my / new_zoom

    # ── helpers ───────────────────────────────────────────────────────────────

    def invalidate_water_depth(self) -> None:
        """Force-clear the full water depth cache."""
        self._water_depth_cache = {}
        self._water_cache_key = 0

    def mark_tile_dirty(self) -> None:
        """No-op in the non-PIL renderer (kept for API compatibility)."""
        pass

    def invalidate_water_near(self, gx: int, gy: int, ground_changed: bool) -> None:
        """Targeted cache invalidation: only evict depth entries within radius 5
        when a ground tile changes (water depth depends only on ground proximity)."""
        if ground_changed:
            r = 5
            for cx in range(gx - r, gx + r + 1):
                for cy in range(gy - r, gy + r + 1):
                    self._water_depth_cache.pop((cx, cy), None)

    # ── brush helpers ─────────────────────────────────────────────────────────

    def _brush_cells(self, gx: int, gy: int) -> List[Tuple[int, int]]:
        """All cells within Chebyshev radius (brush_size - 1) of (gx, gy)."""
        r = self.brush_size - 1
        return [(gx + dx, gy + dy)
                for dx in range(-r, r + 1)
                for dy in range(-r, r + 1)]

    def _apply_brush(self, gx: int, gy: int) -> None:
        """Apply _paint_type to every cell in the brush centered on (gx, gy),
        skipping cells already in _painted_cells or that fail validity checks."""
        pt = self._paint_type
        for bx, by in self._brush_cells(gx, gy):
            if (bx, by) in self._painted_cells:
                continue
            cell = self.state.grid.get((bx, by))

            if pt == "wall_clear":
                if cell and isinstance(cell.occupant, Wall):
                    self._painted_cells.add((bx, by))
                    self.send({"type": "DM_DELETE_OBJECT", "cell": [bx, by]})

            elif pt == "wall":
                if cell and (cell.protected or cell.occupant):
                    continue
                self._painted_cells.add((bx, by))
                self._place_wall_at(bx, by)

            elif pt == "water":
                if (cell and cell.protected) or (cell and cell.occupant):
                    continue
                if cell is None or (cell.tile_type == "ground" and not cell.occupant):
                    self._painted_cells.add((bx, by))
                    self.send({"type": "DM_TILE_SET",
                               "cell": [bx, by], "walkable": False,
                               "tile_type": "water"})

            else:  # ground
                if cell and cell.protected:
                    continue
                if cell and isinstance(cell.occupant, Wall):
                    self._painted_cells.add((bx, by))
                    self.send({"type": "DM_DELETE_OBJECT", "cell": [bx, by]})
                elif cell is None or cell.tile_type == "water":
                    if cell is None or not cell.occupant:
                        self._painted_cells.add((bx, by))
                        self.send({"type": "DM_TILE_SET",
                                   "cell": [bx, by], "walkable": True,
                                   "tile_type": "ground"})

    def center_on_origin_grid(self) -> None:
        """Centre the viewport on the middle of the initial 4×4 grid block."""
        w = self.winfo_width() or 1280
        h = self.winfo_height() or 720
        world_cx = 2 * BASE_CELL_PX
        world_cy = 2 * BASE_CELL_PX
        self.offset_x = world_cx - w / (2 * self.zoom)
        self.offset_y = world_cy - h / (2 * self.zoom)

    def _player_cell(self) -> Optional[Tuple[int, int]]:
        for key, uuids in self.state.players_at.items():
            if self.local_uuid in uuids:
                x, y = map(int, key.split(","))
                return (x, y)
        return None


def _tag_color(msg_type: str) -> str:
    from app.constants import TAG_COLOURS
    return TAG_COLOURS.get(msg_type, TAG_COLOURS["normal"])


def _darken(hex_color: str, factor: float) -> str:
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return "#{:02x}{:02x}{:02x}".format(
            int(r * factor), int(g * factor), int(b * factor)
        )
    except Exception:
        return hex_color
