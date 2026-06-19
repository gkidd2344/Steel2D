from __future__ import annotations
import queue
import re
import time
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timezone
from typing import Optional, Callable, Tuple, TYPE_CHECKING

from app.constants import PALETTE, FONTS, BASE_CELL_PX, POLL_INTERVAL_MS
from ui.panel import Panel
from app.config import STAT_KEYS
from game.objects import NPC, Item, Door, PlayerObject, occupant_from_dict
from game.state import GameState, Cell, GameSettings, CombatState, CombatTurn
from game.stats import clamp_stats, calc_max_hp, effective_stat
from game.los import cells_in_range
from ui.canvas_renderer import GameCanvas
from ui.chat_widget import ChatWidget
from ui.widgets import flat_btn

if TYPE_CHECKING:
    from network.client import GameClient
    from network.server import GameServer


class GameScreen(tk.Frame):
    def __init__(self, parent, state: GameState, client: "GameClient",
                 server: Optional["GameServer"], ui_queue: queue.Queue,
                 local_uuid: str, is_dm: bool, **kwargs):
        super().__init__(parent, bg=PALETTE["bg"], **kwargs)
        self.state = state
        self.client = client
        self.server = server
        self.ui_queue = ui_queue
        self.local_uuid = local_uuid
        self.is_dm = is_dm
        self._latencies: dict = {}
        self._player_list_overlay = None
        self._turn_panel = None
        self._esc_open = False

        # Smooth-pan state (DM only)
        self._pan_keys: set = set()
        self._pan_active: bool = False
        self._PAN_SPEED: int = 9  # canvas pixels per frame

        self._build()
        self._start_poll()
        if client:
            client.start_ping_loop()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        if self.is_dm and self.server:
            self._hud = tk.Frame(self, bg=PALETTE["card2"], height=28)
            self._hud.pack(fill=tk.X)
            self._hud.pack_propagate(False)
            ip = self.server.local_ip
            port = self.server.port
            self._conn_lbl = tk.Label(
                self._hud,
                text=f"🔌 {ip}:{port}   0 players online",
                bg=PALETTE["card2"], fg=PALETTE["fg"],
                font=FONTS["small"], padx=10,
            )
            self._conn_lbl.pack(side=tk.LEFT, pady=2)

        self._canvas = GameCanvas(
            self, self.state, self.local_uuid, self.is_dm,
            send_fn=self._send,
            open_context_fn=self._open_context,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._chat = ChatWidget(
            self._canvas,
            on_send=self._on_chat_send,
            is_dm=self.is_dm,
            game_state=self.state,
        )
        self._chat.place(x=0, rely=1.0, y=-ChatWidget.HEIGHT,
                         width=ChatWidget.WIDTH, height=ChatWidget.HEIGHT)

        if self.is_dm:
            # Two-row DM bar above chat
            self._dm_bar_top = tk.Frame(self._canvas, bg=PALETTE["card2"])
            self._dm_bar_top.place(x=0, rely=1.0,
                                   y=-(ChatWidget.HEIGHT + 62),
                                   width=320, height=28)
            flat_btn(self._dm_bar_top, "🌙 Long Rest",
                     self._do_long_rest, style="ghost").pack(
                side=tk.LEFT, padx=4, pady=2)

            self._combat_bar = tk.Frame(self._canvas, bg=PALETTE["card2"])
            self._combat_bar.place(x=0, rely=1.0,
                                   y=-(ChatWidget.HEIGHT + 32),
                                   width=320, height=30)
            self._combat_btn = flat_btn(
                self._combat_bar, "⚔ Start Combat",
                self._toggle_combat, style="ghost")
            self._combat_btn.pack(side=tk.LEFT, padx=4, pady=2)
            self._encounter_lbl = tk.Label(
                self._combat_bar, text="0 in encounter",
                bg=PALETTE["card2"], fg=PALETTE["fg_dim"],
                font=FONTS["small"])
            self._encounter_lbl.pack(side=tk.LEFT, padx=6)

        self._canvas.center_on_cell(0, 0)
        self._bind_keys()
        self._refresh_combat_ui()

    def _bind_keys(self) -> None:
        root = self.winfo_toplevel()
        # Movement / pan — press and release for smooth DM pan; discrete for PC
        root.bind("<KeyPress>",   self._on_key_press)
        root.bind("<KeyRelease>", self._on_key_release)
        root.bind("<Escape>",     self._on_esc)
        root.bind("<Tab>",        self._on_tab)
        root.bind("<KeyPress-b>", self._on_b)
        root.bind("<KeyPress-c>", self._on_c)
        root.bind("<Return>",     self._on_enter)
        root.bind("<space>",      self._on_space)

    # ── smooth DM pan ─────────────────────────────────────────────────────────

    _PAN_KEY_MAP = {
        'w': (0, -1), 'up': (0, -1),
        's': (0,  1), 'down': (0,  1),
        'a': (-1, 0), 'left': (-1, 0),
        'd': (1,  0), 'right': (1,  0),
    }

    def _on_key_press(self, event) -> None:
        if self._is_chat_focused():
            return
        key = event.keysym.lower()
        if key not in self._PAN_KEY_MAP:
            return
        if self.is_dm:
            self._pan_keys.add(key)
            if not self._pan_active:
                self._pan_active = True
                self._pan_tick()
        else:
            dx, dy = self._PAN_KEY_MAP[key]
            pc = self._canvas._player_cell()
            if pc:
                tx, ty = pc[0] + dx, pc[1] + dy
                self._send({"type": "PLAYER_MOVE", "target_cell": [tx, ty]})

    def _on_key_release(self, event) -> None:
        key = event.keysym.lower()
        self._pan_keys.discard(key)

    def _pan_tick(self) -> None:
        if not self._pan_keys or not self.is_dm:
            self._pan_active = False
            return
        dx, dy = 0.0, 0.0
        for k in self._pan_keys:
            vx, vy = self._PAN_KEY_MAP.get(k, (0, 0))
            dx += vx
            dy += vy
        # Normalise diagonals so speed is consistent
        if dx and dy:
            dx *= 0.707
            dy *= 0.707
        speed = self._PAN_SPEED / self._canvas.zoom
        self._canvas.pan(dx * speed, dy * speed)
        self.after(16, self._pan_tick)

    # ── poll network queue ────────────────────────────────────────────────────

    def _start_poll(self) -> None:
        self.after(POLL_INTERVAL_MS, self._poll)

    def _poll(self) -> None:
        try:
            while True:
                event_type, payload = self.ui_queue.get_nowait()
                self._dispatch(event_type, payload)
        except queue.Empty:
            pass
        self.after(POLL_INTERVAL_MS, self._poll)

    def _dispatch(self, event_type: str, payload: dict) -> None:
        if event_type == "STATE_PATCH":
            self._apply_patches(payload.get("patches", []))
            self._refresh_combat_ui()
        elif event_type == "CHAT_RECV":
            msg = payload.get("message", payload)
            self._chat.add_message(msg)
            if msg.get("msg_type") not in ("system", "error"):
                if self._should_show_bubble(msg):
                    self._canvas.add_bubble(msg)
        elif event_type == "CAMERA_CENTER":
            cell = payload.get("cell", [0, 0])
            self._canvas.center_on_cell(cell[0], cell[1])
        elif event_type == "PLAYER_DISCONNECTED":
            alias = payload.get("alias", "?")
            self._chat.add_local(f"{alias} disconnected.", "system")
            self._update_hud()
        elif event_type == "PLAYER_JOINED":
            alias = payload.get("alias", "?")
            self._chat.add_local(f"{alias} joined.", "system")
            self._update_hud()
        elif event_type == "YOU_WERE_KICKED":
            reason = payload.get("reason", "You were removed from the server.")
            messagebox.showerror("Disconnected", reason)
            self._go_main_menu()
        elif event_type == "DISCONNECTED":
            self._chat.add_local("Disconnected from server.", "error")
        elif event_type == "PONG":
            pass
        elif event_type == "COMBAT_STARTED":
            self.state.combat = CombatState(
                active=True,
                turn_queue=[CombatTurn.from_dict(t) for t in payload.get("turn_queue", [])],
                round_number=payload.get("round", 1),
            )
            self._refresh_combat_ui()
            self._chat.add_local("⚔ Combat started!", "system")
        elif event_type == "COMBAT_ENDED":
            if self.state.combat:
                self.state.combat.active = False
                self.state.combat.turn_queue = []
            self._refresh_combat_ui()
            self._chat.add_local("Combat ended.", "system")
        elif event_type == "COMBAT_TURN_ADVANCED":
            cur = payload.get("current", {})
            round_n = payload.get("round", 1)
            if self.state.combat:
                self.state.combat.current_index = next(
                    (i for i, t in enumerate(self.state.combat.turn_queue) if t.id == cur.get("id")),
                    0,
                )
                self.state.combat.round_number = round_n
                cur_turn = self.state.combat.turn_queue[self.state.combat.current_index] if self.state.combat.turn_queue else None
                if cur_turn:
                    cur_turn.has_moved = False
                    cur_turn.has_acted = False
                    if cur_turn.combatant_type == "npc" and self.is_dm:
                        self._chat.set_npc_impersonate(cur_turn.name)
                    else:
                        self._chat.set_npc_impersonate(None)
            self._refresh_combat_ui()
        elif event_type == "COMBAT_RESOURCES_USED":
            cid = payload.get("combatant_id", "")
            if self.state.combat:
                for t in self.state.combat.turn_queue:
                    if t.id == cid:
                        t.has_moved = payload.get("has_moved", t.has_moved)
                        t.has_acted = payload.get("has_acted", t.has_acted)
            self._refresh_combat_ui()

    def _should_show_bubble(self, msg: dict) -> bool:
        sender = msg.get("sender_uuid", "")
        if msg.get("msg_type") == "whisper":
            recipient = msg.get("recipient_uuid")
            return self.local_uuid in (sender, recipient)
        return True

    def _apply_patches(self, patches: list) -> None:
        for patch in patches:
            op = patch.get("op")
            path = patch.get("path")
            value = patch.get("value")
            if op == "set_cell":
                x, y = map(int, path.split(","))
                self.state.grid[(x, y)] = Cell.from_dict(value)
            elif op == "del_cell":
                x, y = map(int, path.split(","))
                self.state.grid.pop((x, y), None)
            elif op == "set_player":
                self.state.players[path] = PlayerObject.from_dict(value)
            elif op == "del_player":
                self.state.players.pop(path, None)
                for k in list(self.state.players_at.keys()):
                    if path in self.state.players_at[k]:
                        self.state.players_at[k].remove(path)
            elif op == "set_players_at":
                self.state.players_at[path] = value
            elif op == "del_players_at":
                self.state.players_at.pop(path, None)
            elif op == "set_settings":
                self.state.settings = GameSettings.from_dict(value)
            elif op == "set_combat":
                if value is None:
                    self.state.combat = None
                else:
                    self.state.combat = CombatState.from_dict(value)

    # ── combat helpers ────────────────────────────────────────────────────────

    def _refresh_combat_ui(self) -> None:
        in_combat = bool(self.state.combat and self.state.combat.active)

        if self.is_dm and hasattr(self, "_combat_btn"):
            if in_combat:
                self._combat_btn.config(text="■ End Combat", bg=PALETTE["danger"])
            else:
                self._combat_btn.config(text="⚔ Start Combat", bg=PALETTE["card2"])
            n_enc = len((self.state.combat.encounter_npc_ids if self.state.combat else []))
            self._encounter_lbl.config(text=f"{n_enc} in encounter")

        if self._turn_panel and self._turn_panel.winfo_exists():
            self._turn_panel.destroy()
            self._turn_panel = None

        if in_combat:
            from dialogs.combat_overlay import TurnOrderPanel
            self._turn_panel = TurnOrderPanel(
                self._canvas, self.state, self.local_uuid,
                self.is_dm, on_end_turn=self._end_turn,
            )
            self._turn_panel.place(relx=1.0, x=-TurnOrderPanel.WIDTH,
                                   rely=0, y=0, relheight=1.0,
                                   width=TurnOrderPanel.WIDTH)

        self._update_hud()

    def _end_turn(self) -> None:
        if not (self.state.combat and self.state.combat.active):
            return
        ct = self._current_turn()
        if ct is None:
            return
        if ct.combatant_type == "player" and ct.id == self.local_uuid:
            self._send({"type": "PLAYER_END_TURN"})
        elif ct.combatant_type == "npc" and self.is_dm:
            self._send({"type": "DM_NPC_END_TURN", "npc_id": ct.id})

    def _toggle_combat(self) -> None:
        if self.state.combat and self.state.combat.active:
            self._send({"type": "DM_END_COMBAT"})
        else:
            self._send({"type": "DM_START_COMBAT"})

    def _do_long_rest(self) -> None:
        self._send({"type": "DM_LONG_REST"})

    def _current_turn(self):
        if not (self.state.combat and self.state.combat.turn_queue):
            return None
        idx = self.state.combat.current_index
        if idx < len(self.state.combat.turn_queue):
            return self.state.combat.turn_queue[idx]
        return None

    # ── key bindings ──────────────────────────────────────────────────────────

    def _on_esc(self, event) -> None:
        if self._is_chat_focused():
            self._chat.blur_input()
            return
        if self._esc_open:
            return
        self._open_esc_menu()

    def _on_tab(self, event) -> None:
        if self._is_chat_focused():
            return
        if self._player_list_overlay and self._player_list_overlay.winfo_exists():
            self._player_list_overlay.destroy()
            self._player_list_overlay = None
        else:
            from dialogs.player_list_overlay import PlayerListOverlay
            host_uuid = self.server.host_uuid if self.server else self.local_uuid
            self._player_list_overlay = PlayerListOverlay(
                self.winfo_toplevel(), self.state,
                host_uuid=host_uuid,
                local_uuid=self.local_uuid,
                latencies=self._latencies,
            )

    def _on_b(self, event) -> None:
        if self._is_chat_focused():
            return
        player = self.state.players.get(self.local_uuid)
        if not player:
            return
        from dialogs.inventory_dialog import InventoryDialog
        InventoryDialog(
            self.winfo_toplevel(), player,
            on_use=lambda iid: self._send({"type": "ITEM_USE", "item_id": iid}),
            on_equip=lambda iid: self._send({"type": "ITEM_EQUIP", "item_id": iid}),
            on_drop=lambda iid: self._send({"type": "ITEM_DROP", "item_id": iid}),
            on_discard=lambda iid: self._send({"type": "ITEM_DISCARD", "item_id": iid}),
        )

    def _on_c(self, event) -> None:
        if self._is_chat_focused():
            return
        player = self.state.players.get(self.local_uuid)
        if not player:
            return
        from dialogs.player_stats_dialog import PlayerStatsDialog
        PlayerStatsDialog(
            self.winfo_toplevel(), player,
            on_save_stats=lambda s: self._send({"type": "STATS_UPDATE", "stats": s}),
        )

    def _on_enter(self, event) -> None:
        self._chat.focus_input()

    def _on_space(self, event) -> None:
        if self._is_chat_focused():
            return
        ct = self._current_turn()
        if ct is None:
            return
        if (ct.combatant_type == "player" and ct.id == self.local_uuid) or \
           (ct.combatant_type == "npc" and self.is_dm):
            self._end_turn()

    # ── context menu dispatcher ───────────────────────────────────────────────

    def _open_context(self, context: str, cell: Tuple[int, int],
                      screen_pos: Tuple[int, int] = None) -> None:
        gx, gy = cell
        grid_cell = self.state.grid.get((gx, gy))

        if context == "combat_action_confirm":
            self._confirm_combat_action(gx, gy)
            return

        if context == "left_interact" and not self.is_dm:
            self._pc_left_interact(gx, gy, grid_cell)
            return

        if context == "right_click":
            if self.is_dm:
                self._dm_right_click(gx, gy, grid_cell, screen_pos)
            else:
                pass

    def _pc_left_interact(self, gx, gy, grid_cell) -> None:
        if not grid_cell:
            return
        uuids = self.state.players_at.get(f"{gx},{gy}", [])
        obj = grid_cell.occupant

        if isinstance(obj, Door):
            from dialogs.door_dialog import DoorInteractionDialog
            def _action(act):
                self._send({"type": "DOOR_INTERACT", "cell": [gx, gy], "action": act})
            DoorInteractionDialog(self.winfo_toplevel(), obj, _action)
        elif isinstance(obj, NPC):
            self._npc_context_menu(gx, gy, obj)
        elif isinstance(obj, Item):
            menu = tk.Menu(self.winfo_toplevel(), tearoff=0,
                           bg=PALETTE["card"], fg=PALETTE["fg"])
            menu.add_command(label="Pick Up",
                             command=lambda: self._send({"type": "ITEM_PICKUP",
                                                         "cell": [gx, gy],
                                                         "item_id": obj.id}))
            menu.add_command(label="Inspect",
                             command=lambda: self._inspect(obj))
            x = self.winfo_rootx() + self._canvas.winfo_x() + 100
            y = self.winfo_rooty() + self._canvas.winfo_y() + 100
            menu.tk_popup(x, y)
        elif uuids:
            for pid in uuids:
                if pid != self.local_uuid:
                    p = self.state.players.get(pid)
                    if p:
                        from dialogs.player_stats_dialog import PlayerStatsTooltip
                        PlayerStatsTooltip(self.winfo_toplevel(), p)

    def _npc_context_menu(self, gx, gy, npc: NPC) -> None:
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0,
                       bg=PALETTE["card"], fg=PALETTE["fg"])
        menu.add_command(label="Inspect", command=lambda: self._inspect(npc))

        player = self.state.players.get(self.local_uuid)
        if player:
            action_menu = tk.Menu(menu, tearoff=0, bg=PALETTE["card"], fg=PALETTE["fg"])
            action_menu.add_command(
                label="Attack (default)",
                command=lambda: self._pc_do_action(npc, gx, gy, None, None),
            )
            for slot_item in player.Equipment.values():
                if slot_item.Actions:
                    for act_name, action_def in slot_item.Actions.items():
                        casts = action_def.get("Casts") if action_def else None
                        if casts:
                            remaining = casts.get("remaining", 0)
                            mx = casts.get("max_per_rest", 0)
                            label = f"{act_name} ({slot_item.Name})  [{remaining}/{mx}]"
                            exhausted = remaining <= 0
                        else:
                            label = f"{act_name} ({slot_item.Name})"
                            exhausted = False
                        action_menu.add_command(
                            label=label,
                            state=tk.DISABLED if exhausted else tk.NORMAL,
                            command=lambda i=slot_item, a=act_name, nx=gx, ny=gy: (
                                self._start_action_targeting(i, a, nx, ny, npc)
                            ),
                        )
            menu.add_cascade(label="Action", menu=action_menu)

        x = self.winfo_rootx() + self._canvas.winfo_x() + 100
        y = self.winfo_rooty() + self._canvas.winfo_y() + 100
        menu.tk_popup(x, y)

    def _start_action_targeting(self, item: Item, action_name: str,
                                 npc_x, npc_y, npc: NPC) -> None:
        action = item.Actions.get(action_name) if item.Actions else None
        if action is None:
            return
        action_range = action.get("Range", 1)
        if action_range <= 1:
            self._pc_do_action(npc, npc_x, npc_y, item, action_name)
            return
        pc = self._canvas._player_cell()
        if not pc:
            return
        targets = cells_in_range(pc, action_range, self.state,
                                 self.state.settings.los_max_distance)
        valid = {t for t in targets if isinstance(
            self.state.grid.get(t, Cell()).occupant, NPC)}
        self._canvas.set_combat_action({"item_id": item.id, "action_name": action_name}, valid)

    def _confirm_combat_action(self, tx, ty) -> None:
        action_info = self._canvas._combat_action
        if not action_info:
            return
        cell = self.state.grid.get((tx, ty))
        target = cell.occupant if cell else None
        if isinstance(target, NPC):
            self._send({
                "type": "PLAYER_ACTION",
                "action_name": action_info.get("action_name", ""),
                "item_id": action_info.get("item_id"),
                "target_id": target.id,
                "target_cell": [tx, ty],
            })
        self._canvas.set_combat_action(None, set())

    def _pc_do_action(self, npc: NPC, gx, gy, item, action_name) -> None:
        self._send({
            "type": "PLAYER_ACTION",
            "action_name": action_name or "Attack",
            "item_id": item.id if item else None,
            "target_id": npc.id,
            "target_cell": [gx, gy],
        })

    def _inspect(self, obj) -> None:
        from dialogs.object_tooltip import ObjectTooltip
        ObjectTooltip(self.winfo_toplevel(), obj)

    def _dm_right_click(self, gx, gy, grid_cell, screen_pos) -> None:
        sx, sy = screen_pos if screen_pos else (100, 100)
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0,
                       bg=PALETTE["card"], fg=PALETTE["fg"])

        if not grid_cell or not grid_cell.walkable:
            menu.add_command(label="Create Tile",
                             command=lambda: self._send(
                                 {"type": "DM_TILE_SET", "cell": [gx, gy], "walkable": True}))
            menu.tk_popup(sx, sy)
            return

        obj = grid_cell.occupant
        uuids = self.state.players_at.get(f"{gx},{gy}", [])

        if obj:
            menu.add_command(label="Modify Object",
                             command=lambda: self._dm_modify_object(gx, gy, obj))
            menu.add_command(label="Delete Object",
                             command=lambda: self._send(
                                 {"type": "DM_DELETE_OBJECT", "cell": [gx, gy]}))
            if isinstance(obj, NPC):
                if self.state.combat:
                    if obj.id in self.state.combat.encounter_npc_ids:
                        menu.add_command(
                            label="Remove From Encounter",
                            command=lambda: self._send(
                                {"type": "DM_REMOVE_FROM_ENCOUNTER", "npc_id": obj.id}))
                    else:
                        menu.add_command(
                            label="Add To Encounter",
                            command=lambda: self._send(
                                {"type": "DM_ADD_TO_ENCOUNTER", "npc_id": obj.id}))
                npc_action_menu = tk.Menu(menu, tearoff=0, bg=PALETTE["card"], fg=PALETTE["fg"])
                npc_action_menu.add_command(
                    label="Default Attack",
                    command=lambda: self._dm_npc_target_select(obj, "Default Attack"))
                if obj.Actions:
                    for aname in obj.Actions:
                        npc_action_menu.add_command(
                            label=aname,
                            command=lambda a=aname: self._dm_npc_target_select(obj, a))
                menu.add_cascade(label="Actions", menu=npc_action_menu)
        else:
            menu.add_command(label="Spawn Object",
                             command=lambda: self._dm_spawn(gx, gy))

        if uuids:
            menu.add_separator()
            for pid in uuids:
                p = self.state.players.get(pid)
                if not p:
                    continue
                p_menu = tk.Menu(menu, tearoff=0, bg=PALETTE["card"], fg=PALETTE["fg"])
                p_menu.add_command(label="Level Up",
                                   command=lambda u=pid: self._send(
                                       {"type": "DM_LEVEL_UP_PLAYER", "player_uuid": u}))
                p_menu.add_command(label="Modify Player",
                                   command=lambda u=pid, pl=p: self._dm_modify_player(u, pl))
                p_menu.add_command(label="Options",
                                   command=lambda u=pid, pl=p: self._dm_player_options(u, pl))
                menu.add_cascade(label=f"Player: {p.Name}", menu=p_menu)

        if grid_cell.walkable:
            if not grid_cell.protected:
                menu.add_separator()
                menu.add_command(label="Delete Tile",
                                 command=lambda: self._send(
                                     {"type": "DM_TILE_SET", "cell": [gx, gy], "walkable": False}))
            menu.add_command(label="Warp Players Here",
                             command=lambda: self._dm_warp(gx, gy))

        menu.tk_popup(sx, sy)

    def _dm_spawn(self, gx, gy) -> None:
        from dialogs.spawn_object_dialog import SpawnObjectDialog
        SpawnObjectDialog(
            self.winfo_toplevel(),
            on_spawn=lambda obj_d: self._send(
                {"type": "DM_SPAWN_OBJECT", "cell": [gx, gy], "object": obj_d}),
            settings=self.state.settings,
        )

    def _dm_modify_object(self, gx, gy, obj) -> None:
        from dialogs.spawn_object_dialog import SpawnObjectDialog
        SpawnObjectDialog(
            self.winfo_toplevel(),
            on_spawn=lambda obj_d: self._send(
                {"type": "DM_MODIFY_OBJECT", "cell": [gx, gy], "object": obj_d}),
            settings=self.state.settings,
            existing=obj,
            title="Modify Object",
        )

    def _dm_modify_player(self, player_uuid: str, player: PlayerObject) -> None:
        from dialogs.player_stats_dialog import PlayerStatsDialog
        PlayerStatsDialog(
            self.winfo_toplevel(), player,
            on_save_stats=lambda s: self._send({
                "type": "DM_MODIFY_PLAYER",
                "player_uuid": player_uuid,
                "patch": {"Stats": s},
            }),
        )

    def _dm_player_options(self, player_uuid: str, player: PlayerObject) -> None:
        from dialogs.dm_options_dialog import DmOptionsDialog
        DmOptionsDialog(
            self.winfo_toplevel(), player.Name,
            on_kick=lambda: self._send({"type": "DM_KICK_PLAYER", "player_uuid": player_uuid}),
            on_ban=lambda: self._send({"type": "DM_BAN_PLAYER", "player_uuid": player_uuid}),
        )

    def _dm_npc_target_select(self, npc: NPC, action_name: str) -> None:
        from game.los import cells_in_range
        action = (npc.Actions or {}).get(action_name) if action_name != "Default Attack" else None
        action_range = (action or {}).get("Range", 1)
        npc_cell = self.state.find_object_cell(npc.id)
        if not npc_cell:
            return
        if action_range <= 1:
            target_cells = {
                (npc_cell[0] + dx, npc_cell[1] + dy)
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))
            }
        else:
            target_cells = cells_in_range(npc_cell, action_range, self.state,
                                          self.state.settings.los_max_distance)

        def _on_target(tx, ty):
            tc = self.state.grid.get((tx, ty))
            target_obj = tc.occupant if tc else None
            target_p = next((p for p in self.state.players.values()
                             if self.state.find_player_cell(p.id) == (tx, ty)), None)
            tid = ""
            if isinstance(target_obj, NPC):
                tid = target_obj.id
            elif target_p:
                tid = target_p.id
            self._send({
                "type": "DM_NPC_ACTION",
                "npc_id": npc.id,
                "action_name": action_name,
                "target_id": tid,
                "target_cell": [tx, ty],
            })

        self._canvas.set_combat_action(
            {"npc_id": npc.id, "action_name": action_name, "_on_target": _on_target},
            target_cells,
        )

    def _dm_warp(self, gx, gy) -> None:
        from collections import deque
        visited = {(gx, gy)}
        q = deque([(gx, gy)])
        component = []
        while q:
            cx, cy = q.popleft()
            cell = self.state.grid.get((cx, cy))
            if cell and cell.walkable:
                component.append((cx, cy))
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nb = (cx + dx, cy + dy)
                if nb not in visited:
                    visited.add(nb)
                    nc = self.state.grid.get(nb)
                    if nc and nc.walkable:
                        q.append(nb)

        connected_players = list(self.state.players.keys())
        if len(component) < len(connected_players):
            messagebox.showwarning("Not enough space",
                                   f"Need at least {len(connected_players)} unoccupied tiles.",
                                   parent=self.winfo_toplevel())
            return
        import random
        random.shuffle(component)
        target_cells = [list(c) for c in component[:len(connected_players)]]
        self._send({"type": "DM_WARP_PLAYERS", "target_cells": target_cells})

    # ── ESC menu ──────────────────────────────────────────────────────────────

    def _open_esc_menu(self) -> None:
        self._esc_open = True
        panel = Panel(self, padx=28, pady=20)

        def _close():
            self._esc_open = False
            panel.close()

        tk.Label(panel, text="Menu", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 12))

        flat_btn(panel, "Main Menu",
                 lambda: (_close(), self._go_main_menu()),
                 style="ghost").pack(fill=tk.X, pady=3, ipady=3)
        if self.is_dm:
            flat_btn(panel, "Game Settings",
                     lambda: (_close(), self._open_game_settings()),
                     style="ghost").pack(fill=tk.X, pady=3, ipady=3)
            flat_btn(panel, "Save & Quit",
                     lambda: (_close(), self._save_quit()),
                     style="normal").pack(fill=tk.X, pady=3, ipady=3)
        flat_btn(panel, "Quit",
                 lambda: (_close(), self._quit()),
                 style="danger").pack(fill=tk.X, pady=3, ipady=3)
        flat_btn(panel, "Cancel", _close,
                 style="muted").pack(fill=tk.X, pady=(10, 0), ipady=3)

    def _open_game_settings(self) -> None:
        from ui.widgets import styled_entry
        panel = Panel(self, padx=28, pady=20)

        tk.Label(panel, text="Game Settings", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 12))

        fields = [
            ("HP Base Multiplier", "hp_base_multiplier"),
            ("Enemy Damage Mult.", "enemy_damage_multiplier"),
            ("LOS Max Distance",   "los_max_distance"),
        ]
        form = tk.Frame(panel, bg=PALETTE["card"])
        form.pack(fill=tk.X)
        vars_ = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(form, text=label, bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                     font=FONTS["small"], anchor="e", width=20).grid(
                row=i, column=0, pady=5, sticky="e")
            v = tk.StringVar(value=str(getattr(self.state.settings, key)))
            vars_[key] = v
            styled_entry(form, textvariable=v, width=10).grid(
                row=i, column=1, pady=5, padx=(10, 0), sticky="w")

        def _apply():
            try:
                s = {
                    "hp_base_multiplier": float(vars_["hp_base_multiplier"].get()),
                    "enemy_damage_multiplier": float(vars_["enemy_damage_multiplier"].get()),
                    "los_max_distance": int(vars_["los_max_distance"].get()),
                }
            except ValueError:
                return
            self._send({"type": "DM_UPDATE_SETTINGS", "settings": s})
            panel.close()

        btn_row = tk.Frame(panel, bg=PALETTE["card"])
        btn_row.pack(anchor="e", pady=(12, 0))
        flat_btn(btn_row, "Apply", _apply, style="normal").pack(side=tk.LEFT, padx=(0, 8))
        flat_btn(btn_row, "Cancel", panel.close, style="ghost").pack(side=tk.LEFT)

    def _go_main_menu(self) -> None:
        if self.client:
            self.client.send({"type": "DISCONNECT"})
            self.client.stop()
        if self.server:
            self.server.stop()
        root = self.winfo_toplevel()
        root.event_generate("<<GoMainMenu>>")

    def _quit(self) -> None:
        if self.client:
            self.client.send({"type": "DISCONNECT"})
        root = self.winfo_toplevel()
        root.destroy()

    def _save_quit(self) -> None:
        self._do_save(quit_after=True)

    def _do_save(self, quit_after: bool = False) -> None:
        from game.serialise import dump_state
        from app.config import get_saves_dir
        import re as _re
        import datetime as _dt

        name = self.state.name
        if name == "Untitled":
            from ui.widgets import styled_entry
            panel = Panel(self, padx=28, pady=20)
            v = tk.StringVar(value="MyGame")
            tk.Label(panel, text="Name this save", bg=PALETTE["card"],
                     fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 10))
            styled_entry(panel, textvariable=v, width=22).pack(pady=(0, 10))

            def _confirm():
                self.state.name = v.get().strip() or "MyGame"
                panel.close()
                self._write_save(quit_after)

            flat_btn(panel, "Save", _confirm, style="normal").pack(fill=tk.X)
            panel.wait()
            return

        self._write_save(quit_after)

    def _write_save(self, quit_after: bool) -> None:
        from game.serialise import dump_state
        from app.config import get_saves_dir
        import re as _re
        import datetime as _dt

        if self.server:
            self.server.kick_all_with_message("Host is saving and closing. Disconnecting.")
            import time as _t
            _t.sleep(1)

        saves_dir = get_saves_dir()
        safe_name = _re.sub(r"[^A-Za-z0-9_\- ]", "_", self.state.name)
        first_path = saves_dir / f"{safe_name}.sav"
        if first_path.exists():
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = saves_dir / f"{safe_name}_{ts}.sav"
        else:
            path = first_path

        data = dump_state(self.state)
        with open(path, "wb") as f:
            f.write(data)

        if quit_after:
            self._go_main_menu()

    # ── chat send ─────────────────────────────────────────────────────────────

    def _on_chat_send(self, content: str, msg_type: str = "normal",
                      npc_name: str = None, recipient_alias: str = None) -> None:
        if npc_name:
            npc_id = self._find_npc_by_name(npc_name)
            if not npc_id:
                self._chat.add_local(f'No NPC named "{npc_name}" found.', "error")
                return
            self._send({
                "type": "DM_CHAT_AS_NPC",
                "npc_id": npc_id,
                "content": content,
                "msg_type": msg_type,
                "recipient_alias": recipient_alias or "",
            })
        else:
            self._send({
                "type": "CHAT_SEND",
                "content": content,
                "msg_type": msg_type,
                "recipient_alias": recipient_alias or "",
            })

    def _find_npc_by_name(self, name: str) -> Optional[str]:
        name_lower = name.lower()
        for cell in self.state.grid.values():
            if isinstance(cell.occupant, NPC):
                if cell.occupant.Name.lower() == name_lower:
                    return cell.occupant.id
        return None

    # ── helpers ───────────────────────────────────────────────────────────────

    def _send(self, msg: dict) -> None:
        if self.client:
            self.client.send(msg)

    def _is_chat_focused(self) -> bool:
        try:
            focused = self.winfo_toplevel().focus_get()
            return isinstance(focused, tk.Entry) and focused == self._chat._entry
        except Exception:
            return False

    def _update_hud(self) -> None:
        if self.is_dm and self.server and hasattr(self, "_conn_lbl"):
            n = sum(1 for uid in self.server.clients if uid != self.server.host_uuid)
            ip = self.server.local_ip
            self._conn_lbl.config(
                text=f"🔌 {ip}:{self.server.port}   {n} player(s) online"
            )
