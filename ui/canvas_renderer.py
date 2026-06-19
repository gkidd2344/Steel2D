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
from game.objects import NPC, Item, Door, PlayerObject
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

        self.bubbles: List[dict] = []

        self._combat_action: Optional[dict] = None
        self._valid_targets: Set[Tuple[int, int]] = set()

        self._hover_cell: Optional[Tuple[int, int]] = None
        self._img_cache: Dict[Tuple, object] = {}
        self._anim_frame = 0

        self.bind("<Motion>", self._on_motion)
        self.bind("<Button-1>", self._on_left_click)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<ButtonPress-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_move)
        self.bind("<ButtonRelease-1>", self._on_drag_end)
        self.bind("<MouseWheel>", self._on_scroll)

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

    def _draw_tiles(self, min_cx, max_cx, min_cy, max_cy, cell_px) -> None:
        pad = 2 * self.zoom
        for (gx, gy), cell in self.state.grid.items():
            if not cell.walkable:
                continue
            if not (min_cx <= gx <= max_cx and min_cy <= gy <= max_cy):
                continue
            x0, y0, x1, y1 = self._cell_rect(gx, gy, cell_px)
            self.create_rectangle(
                x0 + pad, y0 + pad, x1 - pad, y1 - pad,
                fill=PALETTE["tile"], outline="", tags="tile",
            )

    def _draw_combat_highlights(self, cell_px: float) -> None:
        if not (self.state.combat and self.state.combat.active):
            return
        tq = self.state.combat.turn_queue
        if not tq:
            return
        cur = tq[self.state.combat.current_index]

        cur_cell = self._find_combatant_cell(cur)
        if cur_cell and not cur.has_moved:
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

        if cur_cell:
            x0, y0, x1, y1 = self._cell_rect(cur_cell[0], cur_cell[1], cell_px)
            dash_offset = self._anim_frame % 6
            self.create_rectangle(
                x0 - 4, y0 - 4, x1 + 4, y1 + 4,
                outline="#ffffff", width=3,
                dash=(4, 2), dashoffset=dash_offset,
                tags="glow",
            )

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

    def _draw_npc(self, npc: NPC, x0, y0, x1, y1, cx, cy, pad) -> None:
        size = min(x1 - x0, y1 - y0) * 0.70
        if npc.Hostile:
            h = size / 2
            pts = [cx, y0 + pad, cx - h * 0.866, y1 - pad, cx + h * 0.866, y1 - pad]
            self.create_polygon(pts, fill="#cc2222", outline="#880000", width=2)
        else:
            r = size / 2
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             fill="#22aa22", outline="#115511", width=2)
        self._draw_hp_bar(npc, x0, y0, x1)

    def _draw_hp_bar(self, entity, x0, y0, x1) -> None:
        bw = x1 - x0 - 4
        bh = max(3, 4 * self.zoom)
        by = y0 + 2
        ratio = entity.CurrentHP / max(entity.MaximumHP, 1)
        self.create_rectangle(x0 + 2, by, x1 - 2, by + bh, fill="#333", outline="")
        self.create_rectangle(x0 + 2, by, x0 + 2 + bw * ratio, by + bh,
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
                                  fill="", outline="#8b4513", width=7)
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
                pad = cell_px * 0.1
                self.create_rectangle(x0 + pad, y0 + pad, x1 - pad, y1 - pad,
                                      fill=player.color,
                                      outline=_darken(player.color, 0.6),
                                      width=2)
                if player.avatar_png and HAS_PIL:
                    self._draw_avatar(player, x0, y0, x1, y1, cell_px)
                else:
                    abbrev = (player.Name or "?")[:2].upper()
                    self.create_text((x0 + x1) / 2, (y0 + y1) / 2,
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

        if not cell:
            if self.is_dm:
                lines = [f"({gx}, {gy}) — empty"]
        else:
            uuids = self.state.players_at.get(f"{gx},{gy}", [])
            if uuids:
                for pid in uuids:
                    p = self.state.players.get(pid)
                    if p:
                        lines.append(f"{p.Name}  HP {p.CurrentHP}/{p.MaximumHP}")
                        if self.is_dm:
                            for k in ("Str", "Dex", "Con", "Int", "Wis", "Cha"):
                                lines.append(f"  {k}: {p.Stats.get(k, 0)}")
            if cell.occupant:
                obj = cell.occupant
                pc = self._player_cell()
                can_see = True
                if not self.is_dm and pc:
                    can_see = has_los(self.state, pc, (gx, gy),
                                      self.state.settings.los_max_distance)
                if isinstance(obj, NPC):
                    if can_see:
                        lines.append(f"NPC: {obj.Name}")
                        if self.is_dm:
                            lines += [obj.Description,
                                      f"HP {obj.CurrentHP}/{obj.MaximumHP}",
                                      f"Size: {obj.Size}  Hostile: {obj.Hostile}"]
                        else:
                            lines.append(obj.Description)
                elif isinstance(obj, Item):
                    if can_see:
                        lines.append(f"Item: {obj.Name}")
                        if self.is_dm:
                            lines += [obj.Description,
                                      f"Qty: {obj.Quantity}  Val: {obj.Value}g"]
                        else:
                            lines.append(obj.Description)
                elif isinstance(obj, Door):
                    if can_see:
                        state_str = "Open" if obj.Open else "Closed"
                        lines.append(f"Door — {state_str}")
                        if obj.Locked:
                            lines.append("Locked")
                        if obj.Broken:
                            lines.append("Broken")
            if not lines and self.is_dm:
                lines = [f"({gx}, {gy})"]

        if not lines:
            return

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

    def _on_left_click(self, event) -> None:
        gx, gy = self._canvas_to_cell(event.x, event.y)

        if self._combat_action is not None:
            if (gx, gy) in self._valid_targets:
                self.open_context("combat_action_confirm", (gx, gy))
            else:
                self.set_combat_action(None, set())
            return

        if self.is_dm:
            cell = self.state.grid.get((gx, gy))
            if not cell or not cell.walkable:
                self.send({"type": "DM_TILE_SET", "cell": [gx, gy], "walkable": True})
        else:
            pc = self._player_cell()
            if pc:
                px, py = pc
                if abs(gx - px) <= 1 and abs(gy - py) <= 1 and (gx, gy) != pc:
                    cell = self.state.grid.get((gx, gy))
                    if cell:
                        uuids = self.state.players_at.get(f"{gx},{gy}", [])
                        if cell.occupant or uuids:
                            self.open_context("left_interact", (gx, gy))
                            return
                if abs(gx - px) + abs(gy - py) == 1:
                    self.send({"type": "PLAYER_MOVE", "target_cell": [gx, gy]})

    def _on_right_click(self, event) -> None:
        gx, gy = self._canvas_to_cell(event.x, event.y)
        self.open_context("right_click", (gx, gy), (event.x_root, event.y_root))

    def _on_drag_start(self, event) -> None:
        if not self.is_dm:
            return
        gx, gy = self._canvas_to_cell(event.x, event.y)
        cell = self.state.grid.get((gx, gy))
        if cell and cell.occupant:
            self._drag_source = (gx, gy)
            self._drag_obj = cell.occupant
            self._drag_mouse = (event.x, event.y)

    def _on_drag_move(self, event) -> None:
        if self._drag_obj:
            self._drag_mouse = (event.x, event.y)

    def _on_drag_end(self, event) -> None:
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
