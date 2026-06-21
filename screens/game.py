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
from game.objects import NPC, Item, Door, Wall, Stairs, PlayerObject, occupant_from_dict
from game.state import GameState, Cell, GameSettings, CombatState, CombatTurn
from game.stats import clamp_stats, calc_max_hp, effective_stat, calculate_damage
from game.state import find_combat_move_cells
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
                 local_uuid: str, is_dm: bool,
                 prefabs: list = None, host_uuid: str = "", **kwargs):
        super().__init__(parent, bg=PALETTE["bg"], **kwargs)
        self.state = state
        self.client = client
        self.server = server
        self.ui_queue = ui_queue
        self.local_uuid = local_uuid
        self.is_dm = is_dm
        self.prefabs: list = prefabs or []
        # DM UUID — used by ChatWidget to tag DM messages; correct for both roles
        self._dm_uuid: str = (server.host_uuid if server else
                              host_uuid if host_uuid else local_uuid)
        # Track whether a blocking interaction panel (Door/Stairs) is open
        self._interaction_panel = None
        self._latencies: dict = {}
        self._player_list_overlay = None
        self._turn_panel = None
        self._combat_actions_panel = None
        # Combat state tracking
        self._combat_active_locally: bool = False  # set by COMBAT_STARTED/ENDED events
        self._combat_ui_mode: str = "normal"       # "normal"|"move_select"|"action_select"|"action_target"
        self._combat_pending_action: dict = {}
        self._esc_open = False
        self._esc_panel = None
        self._tab_panel = None
        self._b_panel = None
        self._c_panel = None

        # Smooth-pan state (DM only)
        self._pan_keys: set = set()
        self._pan_active: bool = False
        self._PAN_SPEED: int = 9  # canvas pixels per frame

        # Paintbrush size keys (DM only)
        self._brush_keys: set = set()   # contains +1 and/or -1
        self._brush_active: bool = False

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
            # Paintbrush size indicator (right side of HUD)
            self._brush_lbl = tk.Label(
                self._hud,
                text="Paintbrush Size: 1",
                bg=PALETTE["card2"], fg=PALETTE["fg_dim"],
                font=FONTS["small"], padx=10,
            )
            self._brush_lbl.pack(side=tk.RIGHT, pady=2)

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
            host_uuid=self._dm_uuid,   # correct for both DM and PC roles
        )
        CW = ChatWidget.WIDTH
        CH = ChatWidget.HEIGHT
        self._chat.place(x=0, rely=1.0, y=-CH, width=CW, height=CH)

        if self.is_dm:
            # Long Rest — full-width bar button
            self._dm_bar_top = tk.Frame(self._canvas, bg=PALETTE["card2"])
            self._dm_bar_top.place(x=0, rely=1.0, y=-(CH + 60), width=CW, height=30)
            self._long_rest_btn = flat_btn(
                self._dm_bar_top, "🌙  Long Rest",
                self._do_long_rest, style="rest")
            self._long_rest_btn.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

            # Combat — full-width bar button with encounter count on right
            self._combat_bar = tk.Frame(self._canvas, bg=PALETTE["card2"])
            self._combat_bar.place(x=0, rely=1.0, y=-(CH + 30), width=CW, height=30)
            self._encounter_lbl = tk.Label(
                self._combat_bar, text="0 in encounter",
                bg=PALETTE["fight"], fg="#ffaaaa",
                font=FONTS["small"], padx=8)
            self._encounter_lbl.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, pady=2)
            self._combat_btn = flat_btn(
                self._combat_bar, "⚔  Start Combat",
                self._toggle_combat, style="fight")
            self._combat_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=2, padx=(4, 0))
            # Make encounter label also trigger toggle
            self._encounter_lbl.bind("<Button-1>", lambda e: self._toggle_combat())

        # Click on canvas unfocuses chat
        self._canvas.bind("<Button-1>",
                          lambda e: self._chat.blur_input(), add=True)
        self._canvas.bind("<Button-3>",
                          lambda e: self._chat.blur_input(), add=True)

        if self.is_dm:
            self._canvas.after(120, self._canvas.center_on_origin_grid)
        else:
            self._canvas.after(120, lambda: self._canvas.center_on_cell(0, 0))
        self._bind_keys()
        self._refresh_combat_ui()

    def _bind_keys(self) -> None:
        root = self.winfo_toplevel()
        root.bind("<KeyPress>",   self._on_key_press)
        root.bind("<KeyRelease>", self._on_key_release)
        root.bind("<Escape>",     self._on_esc)
        root.bind("<Tab>",        self._on_tab)
        root.bind("<KeyPress-b>", self._on_b)
        root.bind("<KeyPress-c>", self._on_c)
        root.bind("<Return>",     self._on_enter)
        root.bind("<space>",      self._on_space)
        # Tile-type painting keys (DM only; canvas reads the flags)
        root.bind("<KeyPress-u>",   lambda e: self._set_paint_key("u", True))
        root.bind("<KeyRelease-u>", lambda e: self._set_paint_key("u", False))
        root.bind("<KeyPress-y>",   lambda e: self._set_paint_key("y", True))
        root.bind("<KeyRelease-y>", lambda e: self._set_paint_key("y", False))
        # [ / ] → change paintbrush size (DM only, hold to repeat)
        root.bind("<KeyPress-bracketleft>",    lambda e: self._brush_key_press(-1))
        root.bind("<KeyRelease-bracketleft>",  lambda e: self._brush_key_release(-1))
        root.bind("<KeyPress-bracketright>",   lambda e: self._brush_key_press(+1))
        root.bind("<KeyRelease-bracketright>", lambda e: self._brush_key_release(+1))

    def _set_paint_key(self, key: str, held: bool) -> None:
        if not self.is_dm:
            return
        if key == "u":
            self._canvas.u_held = held
        elif key == "y":
            self._canvas.y_held = held

    # ── paintbrush size (Numpad +/-) ─────────────────────────────────────────

    def _brush_key_press(self, delta: int) -> None:
        if not self.is_dm or self._is_chat_focused():
            return
        self._brush_keys.add(delta)
        if not self._brush_active:
            self._brush_active = True
            self._brush_tick()

    def _brush_key_release(self, delta: int) -> None:
        self._brush_keys.discard(delta)

    def _brush_tick(self) -> None:
        if not self._brush_keys:
            self._brush_active = False
            return
        net = sum(self._brush_keys)   # +1, -1, or 0 when both held
        if net:
            new_size = max(1, min(10, self._canvas.brush_size + net))
            if new_size != self._canvas.brush_size:
                self._canvas.brush_size = new_size
                if hasattr(self, "_brush_lbl"):
                    self._brush_lbl.config(text=f"Paintbrush Size: {new_size}")
        self.after(100, self._brush_tick)   # 10 increments/sec while held

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
        # Block PC movement while a blocking interaction dialogue is open
        if not self.is_dm and self._is_interaction_active():
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
            # WASD movement disabled during turn-based combat — use the combat panel
            if self.state.combat and self.state.combat.active:
                return
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
            prev_cell = self.state.find_player_cell(self.local_uuid)
            patches = payload.get("patches", [])
            self._apply_patches(patches)
            self._refresh_combat_ui()

            # Invalidate water depth cache whenever cells change
            if any(p.get("op") in ("set_cell", "del_cell") for p in patches):
                self._canvas.invalidate_water_depth()

            if not self.is_dm:
                new_cell = self.state.find_player_cell(self.local_uuid)
                if new_cell and new_cell != prev_cell:
                    dist = (max(abs(new_cell[0] - prev_cell[0]),
                                abs(new_cell[1] - prev_cell[1]))
                            if prev_cell else 2)

                    # ── Stair prompt ONLY on WASD step (dist==1); skip teleport ─
                    if dist == 1:
                        from game.objects import Stairs as _S
                        gc = self.state.grid.get(new_cell)
                        if gc and isinstance(gc.occupant, _S):
                            stair = gc.occupant
                            self.after(60, lambda s=stair, c=new_cell:
                                       self._show_stair_prompt(s, c))
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
        elif event_type == "PLAYER_DATA":
            # Server sent us our final player state — persist as character save
            if not self.is_dm:
                player_dict = payload.get("player")
                if player_dict:
                    try:
                        from app.config import save_character
                        save_character(player_dict)
                    except Exception:
                        pass
        elif event_type == "DISCONNECTED":
            root = self.winfo_toplevel()
            self._go_main_menu()
            root.after(150, lambda r=root: self._show_disconnected_notice(r))
        elif event_type == "PONG":
            pass
        elif event_type == "COMBAT_STARTED":
            self._combat_active_locally = True
            self._combat_ui_mode = "normal"
            self._canvas.set_combat_move_mode(False)
            self._canvas.set_combat_action(None, set())
            self.state.combat = CombatState(
                active=True,
                turn_queue=[CombatTurn.from_dict(t) for t in payload.get("turn_queue", [])],
                round_number=payload.get("round", 1),
            )
            self._refresh_combat_ui()
            self._chat.add_local("⚔ Combat started!", "system")
        elif event_type == "COMBAT_ENDED":
            self._combat_active_locally = False
            self._combat_ui_mode = "normal"
            self._canvas.set_combat_move_mode(False)
            self._canvas.set_combat_action(None, set())
            self._canvas.set_combat_valid_moves(set())
            if self.state.combat:
                self.state.combat.active = False
                self.state.combat.turn_queue = []
            self._refresh_combat_ui()
            self._chat.add_local("Combat ended.", "system")
        elif event_type == "COMBAT_TURN_ADVANCED":
            # New turn: reset UI mode and move/action selection
            self._combat_ui_mode = "normal"
            self._canvas.set_combat_move_mode(False)
            self._canvas.set_combat_action(None, set())
            self._canvas.set_combat_valid_moves(set())
            cur = payload.get("current", {})
            round_n = payload.get("round", 1)
            if self.state.combat:
                self.state.combat.current_index = next(
                    (i for i, t in enumerate(self.state.combat.turn_queue) if t.id == cur.get("id")),
                    0,
                )
                self.state.combat.round_number = round_n
                cur_turn = (self.state.combat.turn_queue[self.state.combat.current_index]
                            if self.state.combat.turn_queue else None)
                if cur_turn:
                    cur_turn.has_acted = False
                    cur_turn.points_spent = 0.0
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
                        t.has_acted = payload.get("has_acted", t.has_acted)
                        t.points_spent = float(payload.get("points_spent", t.points_spent))
            # Reset move mode after any resource is used
            self._canvas.set_combat_move_mode(False)
            self._combat_ui_mode = "normal"
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
                    new_cs = CombatState.from_dict(value)
                    # Guard: if COMBAT_ENDED already fired locally, don't let a stale
                    # set_combat{active:True} re-enable combat (race condition fix).
                    if not self._combat_active_locally:
                        new_cs.active = False
                    self.state.combat = new_cs

    # ── combat helpers ────────────────────────────────────────────────────────

    def _refresh_combat_ui(self) -> None:
        in_combat = bool(self.state.combat and self.state.combat.active)

        if self.is_dm and hasattr(self, "_combat_btn"):
            if in_combat:
                btn_bg = PALETTE["danger"]
                btn_txt = "■   End Combat "
                enc_bg = PALETTE["danger"]
            else:
                btn_bg = PALETTE["fight"]
                btn_txt = "⚔  Start Combat"
                enc_bg = PALETTE["fight"]
            self._combat_btn.config(text=btn_txt, bg=btn_bg,
                                    activebackground=btn_bg)
            n_enc = len((self.state.combat.encounter_npc_ids if self.state.combat else []))
            self._encounter_lbl.config(text=f"{n_enc} in encounter",
                                       bg=enc_bg)

        if self._turn_panel and self._turn_panel.winfo_exists():
            self._turn_panel.destroy()
            self._turn_panel = None

        if self._combat_actions_panel and self._combat_actions_panel.winfo_exists():
            self._combat_actions_panel.destroy()
            self._combat_actions_panel = None

        if in_combat:
            from dialogs.combat_overlay import TurnOrderPanel
            self._turn_panel = TurnOrderPanel(
                self._canvas, self.state, self.local_uuid,
                self.is_dm, on_end_turn=self._end_turn,
            )
            self._turn_panel.place(relx=1.0, x=-TurnOrderPanel.WIDTH,
                                   rely=0, y=0, relheight=1.0,
                                   width=TurnOrderPanel.WIDTH)
            self._precompute_combat_moves()
            self._rebuild_combat_actions_panel()
        else:
            self._canvas.set_combat_valid_moves(set())

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
        if self._esc_panel and not self._esc_panel._closing:
            self._esc_panel.close()
            self._esc_panel = None
            self._esc_open = False
            return
        self._open_esc_menu()

    def _on_tab(self, event) -> str:
        if self._is_chat_focused():
            return "break"
        if self._tab_panel and not self._tab_panel._closing:
            self._tab_panel.close()
            self._tab_panel = None
            return "break"
        from dialogs.player_list_overlay import PlayerListOverlay
        host_uuid = self.server.host_uuid if self.server else self.local_uuid
        self._tab_panel = PlayerListOverlay(
            self.winfo_toplevel(), self.state,
            host_uuid=host_uuid,
            local_uuid=self.local_uuid,
            latencies=self._latencies,
        )
        return "break"

    def _on_b(self, event) -> None:
        if self._is_chat_focused():
            return
        if self._b_panel and not self._b_panel._closing:
            self._b_panel.close()
            self._b_panel = None
            return
        player = self.state.players.get(self.local_uuid)
        if not player:
            return
        from dialogs.inventory_dialog import InventoryDialog
        self._b_panel = InventoryDialog(
            self.winfo_toplevel(), player,
            on_use=lambda iid: self._send({"type": "ITEM_USE", "item_id": iid}),
            on_equip=lambda iid: self._send({"type": "ITEM_EQUIP", "item_id": iid}),
            on_drop=lambda iid: self._send({"type": "ITEM_DROP", "item_id": iid}),
            on_discard=lambda iid: self._send({"type": "ITEM_DISCARD", "item_id": iid}),
        )

    def _on_c(self, event) -> None:
        if self._is_chat_focused():
            return
        if self._c_panel and not self._c_panel._closing:
            self._c_panel.close()
            self._c_panel = None
            return
        player = self.state.players.get(self.local_uuid)
        if not player:
            return
        from dialogs.player_stats_dialog import PlayerStatsDialog
        self._c_panel = PlayerStatsDialog(
            self.winfo_toplevel(), player,
            on_save_stats=lambda s: self._send({"type": "STATS_UPDATE", "stats": s}),
            multiplier=self.state.settings.hp_base_multiplier,
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

        if context == "combat_move":
            self._combat_do_move(gx, gy)
            return

        if context == "combat_targeting_cancelled":
            self._combat_ui_mode = "normal"
            self._canvas.set_combat_move_mode(False)
            self._rebuild_combat_actions_panel()
            return

        if context == "own_cell_interact" and not self.is_dm:
            if grid_cell and grid_cell.occupant:
                from game.objects import Stairs as _S, Item as _I
                obj = grid_cell.occupant
                if isinstance(obj, _S):
                    self._show_stair_prompt(obj, (gx, gy))
                elif isinstance(obj, _I):
                    self._pc_item_ground_menu(gx, gy, obj)
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
            door_panel = DoorInteractionDialog(self.winfo_toplevel(), obj, _action)
            self._interaction_panel = door_panel
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
        if action_range == 0:
            # Self-target — use player's own cell
            pc = self._canvas._player_cell()
            if pc:
                self._send({
                    "type": "PLAYER_ACTION",
                    "action_name": action_name,
                    "item_id": item.id,
                    "target_id": self.local_uuid,
                    "target_cell": list(pc),
                })
            return
        if action_range == 1:
            self._pc_do_action(npc, npc_x, npc_y, item, action_name)
            return
        pc = self._canvas._player_cell()
        if not pc:
            return
        # All walkable cells in range are valid — empty cells cause a fizzle
        targets = cells_in_range(pc, action_range, self.state,
                                 self.state.settings.los_max_distance)
        self._canvas.set_combat_action({"item_id": item.id, "action_name": action_name},
                                       targets)

    def _confirm_combat_action(self, tx, ty) -> None:
        action_info = self._canvas._combat_action
        if not action_info:
            return
        if "_on_target" in action_info:
            action_info["_on_target"](tx, ty)
        else:
            cell = self.state.grid.get((tx, ty))
            target = cell.occupant if cell else None
            target_id = target.id if (target and hasattr(target, "id")) else ""
            self._send({
                "type": "PLAYER_ACTION",
                "action_name": action_info.get("action_name", ""),
                "item_id": action_info.get("item_id"),
                "target_id": target_id,
                "target_cell": [tx, ty],
            })
        self._canvas.set_combat_action(None, set())
        self._combat_ui_mode = "normal"
        self._rebuild_combat_actions_panel()

    # ── combat actions panel ──────────────────────────────────────────────────

    def _precompute_combat_moves(self) -> None:
        """BFS-compute valid move destinations for the current combatant and
        store them in the canvas so highlights and click-validation both use
        the same pre-computed set.  Cleared when it is not this client's turn."""
        ct = self._current_turn()
        if not ct or not ct.can_move:
            self._canvas.set_combat_valid_moves(set())
            return

        if ct.combatant_type == "player" and ct.id == self.local_uuid:
            from_cell = self._canvas._player_cell()
        elif ct.combatant_type == "npc" and self.is_dm:
            from_cell = self.state.find_object_cell(ct.id)
        else:
            self._canvas.set_combat_valid_moves(set())
            return

        if not from_cell:
            self._canvas.set_combat_valid_moves(set())
            return

        valid = find_combat_move_cells(self.state, from_cell)
        self._canvas.set_combat_valid_moves(valid)

    def _rebuild_combat_actions_panel(self) -> None:
        """Create or refresh the left-side combat actions panel for current combatant."""
        if self._combat_actions_panel and self._combat_actions_panel.winfo_exists():
            self._combat_actions_panel.destroy()
        self._combat_actions_panel = None

        if not (self.state.combat and self.state.combat.active):
            return
        ct = self._current_turn()
        if not ct:
            return
        my_turn = (
            (ct.combatant_type == "player" and ct.id == self.local_uuid) or
            (ct.combatant_type == "npc" and self.is_dm)
        )
        if not my_turn:
            return

        CW = ChatWidget.WIDTH
        CH = ChatWidget.HEIGHT
        bar_h = 60 if self.is_dm else 0   # combat bar (30) + long rest (30)
        mode = self._combat_ui_mode
        actions = self._get_combat_actions_for_ct(ct) if mode == "action_select" else []

        if mode == "normal":
            PANEL_H = 88
        elif mode in ("move_select", "action_target"):
            PANEL_H = 58
        else:  # action_select: title + col-hdr + N rows + cancel
            PANEL_H = max(110, 28 + 20 + len(actions) * 32 + 34)

        panel = tk.Frame(self._canvas, bg=PALETTE["card2"],
                         highlightthickness=1,
                         highlightbackground=PALETTE["border"])
        self._combat_actions_panel = panel
        panel.place(x=0, rely=1.0, y=-(CH + bar_h + PANEL_H),
                    width=CW, height=PANEL_H)

        # Title row
        from ui.widgets import hr
        title = ("Your Turn" if ct.combatant_type == "player"
                 else f"{ct.name}'s Turn")
        title_row = tk.Frame(panel, bg=PALETTE["card2"], pady=3, padx=8)
        title_row.pack(fill=tk.X)
        tk.Label(title_row, text=f"⚔  {title}", bg=PALETTE["card2"],
                 fg=PALETTE["fg"], font=FONTS["sub"]).pack(side=tk.LEFT)
        hr(panel).pack(fill=tk.X)

        if mode == "normal":
            btn_row = tk.Frame(panel, bg=PALETTE["card2"])
            btn_row.pack(fill=tk.X, padx=4, pady=4)
            btn_row.grid_columnconfigure(0, weight=1)
            btn_row.grid_columnconfigure(1, weight=1)

            can_move = ct.can_move
            mbtn = flat_btn(btn_row, "🦶  Move", self._combat_click_move,
                            style="normal" if can_move else "muted")
            mbtn.grid(row=0, column=0, sticky="ew", padx=(0, 2), ipady=4)
            if not can_move:
                mbtn.config(state=tk.DISABLED)

            can_act = ct.can_act
            abtn = flat_btn(btn_row, "⚔  Do Action", self._combat_click_do_action,
                            style="normal" if can_act else "muted")
            abtn.grid(row=0, column=1, sticky="ew", padx=(2, 0), ipady=4)
            if not can_act:
                abtn.config(state=tk.DISABLED)

            hr(panel).pack(fill=tk.X)
            flat_btn(panel, "Pass Turn", self._end_turn, style="ghost").pack(
                fill=tk.X, padx=4, pady=3, ipady=2)

        elif mode == "move_select":
            tk.Label(panel, text="Click a highlighted cell to move",
                     bg=PALETTE["card2"], fg=PALETTE["fg_dim"],
                     font=FONTS["small"]).pack(padx=8, pady=6, anchor="w")
            flat_btn(panel, "Cancel", self._combat_cancel, style="muted").pack(
                fill=tk.X, padx=4, pady=3, ipady=2)

        elif mode == "action_select":
            # Column header
            from ui.widgets import hr as _hr
            hdr_row = tk.Frame(panel, bg=PALETTE["bg"])
            hdr_row.pack(fill=tk.X, padx=4)
            hdr_row.grid_columnconfigure(0, weight=3)
            hdr_row.grid_columnconfigure(1, weight=1)
            hdr_row.grid_columnconfigure(2, weight=3)
            hdr_row.grid_columnconfigure(3, weight=3)
            for col_txt, col_i in (("Action", 0), ("Rng", 1), ("Damage", 2), ("Buffs", 3)):
                tk.Label(hdr_row, text=col_txt, bg=PALETTE["bg"],
                         fg=PALETTE["muted"], font=FONTS["small"],
                         anchor="w", padx=2).grid(row=0, column=col_i, sticky="ew")
            _hr(panel).pack(fill=tk.X)
            inner = tk.Frame(panel, bg=PALETTE["card2"])
            inner.pack(fill=tk.X, padx=4, pady=2)
            for aname, scalars, adef, item_id, disabled in actions:
                self._build_action_row(inner, ct, aname, scalars, adef, item_id, disabled)
            _hr(panel).pack(fill=tk.X)
            flat_btn(panel, "Cancel", self._combat_cancel, style="muted").pack(
                fill=tk.X, padx=4, pady=3, ipady=2)

        elif mode == "action_target":
            aname = self._combat_pending_action.get("action_name", "Action")
            tk.Label(panel, text=f"Click a target for:  {aname}",
                     bg=PALETTE["card2"], fg=PALETTE["fg_dim"],
                     font=FONTS["small"]).pack(padx=8, pady=6, anchor="w")
            flat_btn(panel, "Cancel", self._combat_cancel, style="muted").pack(
                fill=tk.X, padx=4, pady=3, ipady=2)

    def _get_combat_actions_for_ct(self, ct) -> list:
        """Return [(name, scalars, action_def, item_id, disabled), ...] for combatant."""
        UNARMED_SCALARS = {"Str": "A", "Dex": "B"}
        UNARMED_ACTION = {"Range": 1, "BaseDamage": 1, "Hits": 2}
        result = [("Unarmed Attack", UNARMED_SCALARS, UNARMED_ACTION, None, False)]

        if ct.combatant_type == "player":
            player = self.state.players.get(ct.id)
            if player:
                for slot_item in player.Equipment.values():
                    if not slot_item.Actions:
                        continue
                    for aname, adef in slot_item.Actions.items():
                        casts = (adef or {}).get("Casts")
                        disabled = (casts is not None and casts.get("remaining", 0) <= 0)
                        a_scalars = (adef or {}).get("ScalesWith")
                        result.append((aname, a_scalars, adef, slot_item.id, disabled))
        elif ct.combatant_type == "npc":
            npc_cell = self.state.find_object_cell(ct.id)
            if npc_cell:
                npc = self.state.grid.get(npc_cell)
                npc = npc.occupant if npc else None
                if isinstance(npc, NPC) and npc.Actions:
                    for aname, adef in npc.Actions.items():
                        casts = (adef or {}).get("Casts")
                        disabled = (casts is not None and casts.get("remaining", 0) <= 0)
                        a_scalars = (adef or {}).get("ScalesWith") or getattr(npc, "Scalars", None)
                        result.append((aname, a_scalars, adef, None, disabled))
        return result

    def _combat_action_display_parts(self, ct, scalars, adef) -> tuple:
        """Return (range_str, dmg_str) for action list columns."""
        rng = (adef or {}).get("Range", 1)
        range_str = f"R:{rng}"
        entity = None
        if ct.combatant_type == "player":
            entity = self.state.players.get(ct.id)
        else:
            npc_cell = self.state.find_object_cell(ct.id)
            if npc_cell:
                c = self.state.grid.get(npc_cell)
                entity = c.occupant if c else None
        if not entity:
            return range_str, "?"
        try:
            dmg = calculate_damage(entity, scalars, adef)
            hits = (adef or {}).get("Hits", 1)
            total = dmg * hits
            dmg_str = f"{hits}×{dmg}={total}dmg" if hits > 1 else f"{total}dmg"
        except Exception:
            dmg_str = "?"
        return range_str, dmg_str

    def _combat_action_damage_text(self, ct, scalars, adef) -> str:
        r, d = self._combat_action_display_parts(ct, scalars, adef)
        return f"{r} {d}"

    @staticmethod
    def _add_buff_tooltip(widget, buff_list) -> None:
        """Attach a hover tooltip showing buff details to widget."""
        tip = [None]

        def _show(event):
            if tip[0]:
                return
            lines = []
            for b in buff_list:
                name = b.get("Name", "?")
                btype = b.get("Type", "?")
                val = b.get("Value", 0)
                dur = int(b.get("Duration", 0))
                sign = "+" if val > 0 else ""
                lines.append(name)
                lines.append(f"  {btype}  {sign}{val}")
                if dur < 99999:
                    lines.append(f"  Duration: {dur} min")
            if not lines:
                return
            t = tk.Toplevel(widget)
            t.overrideredirect(True)
            t.wm_attributes("-topmost", True)
            t.geometry(f"+{event.x_root + 14}+{event.y_root + 14}")
            tk.Label(t, text="\n".join(lines), bg=PALETTE["card"],
                     fg=PALETTE["fg"], font=FONTS["small"],
                     justify="left", padx=8, pady=6,
                     relief=tk.SOLID, bd=1).pack()
            tip[0] = t

        def _hide(event):
            if tip[0]:
                try:
                    tip[0].destroy()
                except Exception:
                    pass
                tip[0] = None

        widget.bind("<Enter>", _show, add=True)
        widget.bind("<Leave>", _hide, add=True)

    def _build_action_row(self, parent, ct, aname: str, scalars, adef,
                          item_id, disabled: bool) -> tk.Frame:
        """Build one 4-column action row (Name | R:# | DMG | Buff)."""
        range_str, dmg_str = self._combat_action_display_parts(ct, scalars, adef)
        gives_buffs = list((adef or {}).get("GivesBuffs") or [])
        buff_names = [b.get("Name", "?") for b in gives_buffs if b.get("Name")]
        buff_txt = f"Applies: {buff_names[0]}" if buff_names else ""

        row_bg = PALETTE["card2"] if disabled else PALETTE["card"]
        fg = PALETTE["fg_dim"] if disabled else PALETTE["fg"]

        row = tk.Frame(parent, bg=row_bg, height=30)
        row.pack(fill=tk.X, pady=1)
        row.pack_propagate(False)
        row.grid_columnconfigure(0, weight=3)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, weight=3)
        row.grid_columnconfigure(3, weight=3)

        tk.Label(row, text=aname[:18], bg=row_bg, fg=fg,
                 font=FONTS["small"], anchor="w", padx=2).grid(
            row=0, column=0, sticky="ew")
        tk.Label(row, text=range_str, bg=row_bg, fg=fg,
                 font=FONTS["small"], anchor="w", padx=2).grid(
            row=0, column=1, sticky="ew")
        tk.Label(row, text=dmg_str, bg=row_bg, fg=fg,
                 font=FONTS["small"], anchor="w", padx=2).grid(
            row=0, column=2, sticky="ew")
        buff_lbl = tk.Label(row, text=buff_txt[:16],
                            bg=row_bg,
                            fg=PALETTE["accent"] if buff_txt else PALETTE["muted"],
                            font=FONTS["small"], anchor="w", padx=2)
        buff_lbl.grid(row=0, column=3, sticky="ew")
        if gives_buffs:
            self._add_buff_tooltip(buff_lbl, gives_buffs)

        if not disabled:
            def _click(event=None, an=aname, sc=scalars, ad=adef, iid=item_id):
                self._combat_select_action(ct, an, sc, ad, iid)

            def _enter(event=None):
                row.config(bg=PALETTE["accent"])
                for w in row.grid_slaves():
                    try:
                        w.config(bg=PALETTE["accent"])
                    except Exception:
                        pass

            def _leave(event=None):
                row.config(bg=row_bg)
                for w in row.grid_slaves():
                    try:
                        w.config(bg=row_bg)
                    except Exception:
                        pass

            row.config(cursor="hand2")
            row.bind("<Button-1>", _click)
            row.bind("<Enter>", _enter)
            row.bind("<Leave>", _leave)
            for child in row.grid_slaves():
                child.config(cursor="hand2")
                child.bind("<Button-1>", _click)
                child.bind("<Enter>", _enter)
                child.bind("<Leave>", _leave)
        return row

    def _combat_click_move(self) -> None:
        ct = self._current_turn()
        if not ct or not ct.can_move:
            return
        self._combat_ui_mode = "move_select"
        self._canvas.set_combat_move_mode(True)
        self._rebuild_combat_actions_panel()

    def _combat_click_do_action(self) -> None:
        ct = self._current_turn()
        if not ct or not ct.can_act:
            return
        self._combat_ui_mode = "action_select"
        self._rebuild_combat_actions_panel()

    def _combat_cancel(self) -> None:
        self._combat_ui_mode = "normal"
        self._canvas.set_combat_move_mode(False)
        self._canvas.set_combat_action(None, set())
        self._rebuild_combat_actions_panel()

    def _combat_do_move(self, gx: int, gy: int) -> None:
        ct = self._current_turn()
        if not ct:
            return
        if ct.combatant_type == "player" and ct.id == self.local_uuid:
            self._send({"type": "PLAYER_MOVE", "target_cell": [gx, gy]})
        elif ct.combatant_type == "npc" and self.is_dm:
            self._send({"type": "DM_NPC_MOVE", "npc_id": ct.id,
                        "target_cell": [gx, gy]})
        self._canvas.set_combat_move_mode(False)
        self._combat_ui_mode = "normal"
        self._rebuild_combat_actions_panel()

    def _combat_select_action(self, ct, action_name: str, scalars, adef,
                              item_id: Optional[str]) -> None:
        action_range = (adef or {}).get("Range", 1)

        if ct.combatant_type == "player":
            pc = self._canvas._player_cell()
            if not pc:
                return
            if action_range == 0:
                self._send({"type": "PLAYER_ACTION", "action_name": action_name,
                             "item_id": item_id, "target_id": self.local_uuid,
                             "target_cell": list(pc)})
                self._combat_ui_mode = "normal"
                self._rebuild_combat_actions_panel()
                return
            if action_range == 1:
                targets = {(pc[0]+dx, pc[1]+dy)
                           for dx, dy in ((0,1),(0,-1),(1,0),(-1,0))}
            else:
                targets = cells_in_range(pc, action_range, self.state,
                                         self.state.settings.los_max_distance)
            self._combat_pending_action = {"action_name": action_name,
                                           "item_id": item_id}
            self._combat_ui_mode = "action_target"
            self._canvas.set_combat_action(self._combat_pending_action, targets)

        elif ct.combatant_type == "npc" and self.is_dm:
            npc_cell = self.state.find_object_cell(ct.id)
            if not npc_cell:
                return
            if action_range <= 1:
                targets = {(npc_cell[0]+dx, npc_cell[1]+dy)
                           for dx, dy in ((0,1),(0,-1),(1,0),(-1,0))}
            else:
                targets = cells_in_range(npc_cell, action_range, self.state,
                                         self.state.settings.los_max_distance)

            def _on_target(tx, ty):
                tc = self.state.grid.get((tx, ty))
                target_obj = tc.occupant if tc else None
                target_p = next(
                    (p for p in self.state.players.values()
                     if self.state.find_player_cell(p.id) == (tx, ty)), None)
                tid = ""
                if isinstance(target_obj, NPC):
                    tid = target_obj.id
                elif target_p:
                    tid = target_p.id
                self._send({"type": "DM_NPC_ACTION", "npc_id": ct.id,
                             "action_name": action_name, "target_id": tid,
                             "target_cell": [tx, ty]})

            self._combat_pending_action = {"action_name": action_name,
                                           "npc_id": ct.id, "_on_target": _on_target}
            self._combat_ui_mode = "action_target"
            self._canvas.set_combat_action(self._combat_pending_action, targets)

        self._rebuild_combat_actions_panel()

    def _pc_item_ground_menu(self, gx: int, gy: int, item: Item) -> None:
        """Pick-up/inspect menu shown when PC is standing on an Item tile."""
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0,
                       bg=PALETTE["card"], fg=PALETTE["fg"])
        menu.add_command(
            label="Pick Up",
            command=lambda: self._send({"type": "ITEM_PICKUP",
                                        "cell": [gx, gy], "item_id": item.id}))
        menu.add_command(label="Inspect", command=lambda: self._inspect(item))
        x = self.winfo_rootx() + self._canvas.winfo_width() // 2
        y = self.winfo_rooty() + self._canvas.winfo_height() // 2
        menu.tk_popup(x, y)

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

    def _is_interaction_active(self) -> bool:
        """True when a blocking interaction panel (Door/Stairs) is still open."""
        try:
            return (self._interaction_panel is not None
                    and not self._interaction_panel._closing
                    and self._interaction_panel.winfo_exists())
        except Exception:
            return False

    @staticmethod
    def _show_disconnected_notice(root) -> None:
        """Create a top-centre notice panel on whatever screen is now showing."""
        try:
            from ui.panel import Panel
            from ui.widgets import flat_btn
            panel = Panel(root, padx=28, pady=22, placement="top")
            tk.Label(panel, text="Disconnected from server",
                     bg=PALETTE["card"], fg=PALETTE["fg"],
                     font=FONTS["heading"]).pack(anchor="w", pady=(0, 10))
            tk.Label(panel,
                     text="The connection to the server was lost.",
                     bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                     font=FONTS["body"]).pack(anchor="w", pady=(0, 16))
            flat_btn(panel, "Close", panel.close, style="ghost").pack(
                fill=tk.X, ipady=4)
        except Exception:
            pass

    def _show_stair_prompt(self, stair, cell) -> None:
        from dialogs.stair_dialog import StairPromptDialog

        def _yes():
            if stair.LinkedStair:
                self._send({"type": "PLAYER_TAKE_STAIRS", "stair_id": stair.id})

        prompt = StairPromptDialog(self._canvas, stair, on_yes=_yes, on_no=lambda: None)
        self._interaction_panel = prompt

    def _dm_speak_as_npc(self, npc: NPC) -> None:
        """Open an in-app panel letting the DM send a message as the given NPC."""
        from ui.panel import Panel
        from ui.widgets import hr
        panel = Panel(self.winfo_toplevel(), padx=0, pady=0)

        hdr = tk.Frame(panel, bg=PALETTE["card"], padx=14, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Speak as {npc.Name}", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", panel.close, style="ghost").pack(side=tk.RIGHT)
        hr(panel).pack(fill=tk.X)

        body = tk.Frame(panel, bg=PALETTE["card"], padx=14, pady=10)
        body.pack(fill=tk.X)
        tk.Label(body, text="Message", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(anchor="w", pady=(0, 4))
        msg_text = tk.Text(body, height=3, width=32,
                           bg=PALETTE["card2"], fg=PALETTE["fg"],
                           insertbackground=PALETTE["fg"],
                           relief=tk.FLAT, bd=0)
        msg_text.pack(fill=tk.X)

        hr(panel).pack(fill=tk.X)
        btn_row = tk.Frame(panel, bg=PALETTE["card"], padx=14, pady=8)
        btn_row.pack(fill=tk.X)

        def _send():
            content = msg_text.get("1.0", "end-1c").strip()
            if content:
                self._send({"type": "DM_CHAT_AS_NPC",
                            "npc_id": npc.id,
                            "content": content,
                            "msg_type": "normal"})
            panel.close()

        flat_btn(btn_row, "Send", _send, style="normal").pack(side=tk.LEFT, padx=(0, 8))
        flat_btn(btn_row, "Cancel", panel.close, style="ghost").pack(side=tk.LEFT)
        msg_text.focus_set()
        panel.bind("<Return>", lambda e: _send() if not (e.state & 1) else None)

    def _dm_modify_stairs(self, stair, cell) -> None:
        from dialogs.stair_dialog import StairModifyDialog
        StairModifyDialog(
            self.winfo_toplevel(), stair, cell, self.state,
            on_save=lambda obj_d: self._send({
                "type": "DM_MODIFY_OBJECT",
                "cell": list(cell),
                "object": obj_d,
            }),
        )

    def _dm_right_click(self, gx, gy, grid_cell, screen_pos) -> None:
        sx, sy = screen_pos if screen_pos else (100, 100)
        in_combat = bool(self.state.combat and self.state.combat.active)

        # ── During combat: player-only sub-menu ──────────────────────────────
        if in_combat:
            uuids = self.state.players_at.get(f"{gx},{gy}", [])
            if not uuids:
                return
            menu = tk.Menu(self.winfo_toplevel(), tearoff=0,
                           bg=PALETTE["card"], fg=PALETTE["fg"])
            for pid in uuids:
                p = self.state.players.get(pid)
                if not p:
                    continue
                p_menu = tk.Menu(menu, tearoff=0,
                                 bg=PALETTE["card"], fg=PALETTE["fg"])
                p_menu.add_command(label="Level Up",
                                   command=lambda u=pid: self._send(
                                       {"type": "DM_LEVEL_UP_PLAYER",
                                        "player_uuid": u}))
                p_menu.add_command(label="Modify Player",
                                   command=lambda u=pid, pl=p:
                                       self._dm_modify_player(u, pl))
                p_menu.add_command(label="Options",
                                   command=lambda u=pid, pl=p:
                                       self._dm_player_options(u, pl))
                menu.add_cascade(label=f"Player: {p.Name}", menu=p_menu)
            menu.tk_popup(sx, sy)
            return

        # ── Normal DM right-click (out of combat) ─────────────────────────────
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0,
                       bg=PALETTE["card"], fg=PALETTE["fg"])

        tile_type = grid_cell.tile_type if grid_cell else "none"

        # Empty / water / non-walkable cell — minimal menu
        if not grid_cell or tile_type == "water" or not grid_cell.walkable:
            if not grid_cell:
                menu.add_command(
                    label="Create Ground Tile",
                    command=lambda: self._send(
                        {"type": "DM_TILE_SET", "cell": [gx, gy],
                         "walkable": True, "tile_type": "ground"}))
            if tile_type == "water":
                menu.add_command(
                    label="Convert to Ground",
                    command=lambda: self._send(
                        {"type": "DM_TILE_SET", "cell": [gx, gy],
                         "walkable": True, "tile_type": "ground"}))
                menu.add_command(
                    label="Delete Water Tile",
                    command=lambda: self._send(
                        {"type": "DM_TILE_SET", "cell": [gx, gy],
                         "walkable": False, "tile_type": "ground"}))
            menu.tk_popup(sx, sy)
            return

        obj = grid_cell.occupant
        uuids = self.state.players_at.get(f"{gx},{gy}", [])
        is_protected = bool(grid_cell.protected)

        if obj:
            from game.objects import Wall as _Wall, Door as _Door, Stairs as _Stairs
            if isinstance(obj, _Stairs):
                menu.add_command(label="Modify Stairs",
                                 command=lambda s=obj, c=(gx, gy):
                                     self._dm_modify_stairs(s, c))
                if not is_protected:
                    menu.add_command(label="Delete Stairs",
                                     command=lambda: self._send(
                                         {"type": "DM_DELETE_OBJECT", "cell": [gx, gy]}))
            elif isinstance(obj, _Wall):
                if not is_protected:
                    menu.add_command(label="Delete Wall",
                                     command=lambda: self._send(
                                         {"type": "DM_DELETE_OBJECT", "cell": [gx, gy]}))
            elif isinstance(obj, _Door):
                # Door-specific toggles (item 3)
                d = obj
                menu.add_command(
                    label="Close" if d.Open else "Open",
                    command=lambda _d=d: self._send({
                        "type": "DM_MODIFY_OBJECT", "cell": [gx, gy],
                        "object": {**_d.to_dict(), "Open": not _d.Open}}))
                menu.add_command(
                    label="Fix" if d.Broken else "Break",
                    command=lambda _d=d: self._send({
                        "type": "DM_MODIFY_OBJECT", "cell": [gx, gy],
                        "object": {**_d.to_dict(), "Broken": not _d.Broken}}))
                menu.add_command(
                    label="Unlock" if d.Locked else "Lock",
                    command=lambda _d=d: self._send({
                        "type": "DM_MODIFY_OBJECT", "cell": [gx, gy],
                        "object": {**_d.to_dict(), "Locked": not _d.Locked}}))
                if not is_protected:
                    menu.add_separator()
                    menu.add_command(label="Delete Door",
                                     command=lambda: self._send(
                                         {"type": "DM_DELETE_OBJECT", "cell": [gx, gy]}))
            elif not is_protected:
                menu.add_command(label="Modify Object",
                                 command=lambda: self._dm_modify_object(gx, gy, obj))
                menu.add_command(label="Delete Object",
                                 command=lambda: self._send(
                                     {"type": "DM_DELETE_OBJECT", "cell": [gx, gy]}))

            if isinstance(obj, NPC) and not is_protected:
                menu.add_command(
                    label="Modify Current HP",
                    command=lambda: self._modify_npc_hp(gx, gy))
                menu.add_separator()
                enc_ids = self.state.combat.encounter_npc_ids if self.state.combat else []
                if obj.id in enc_ids:
                    menu.add_command(
                        label="Remove From Encounter",
                        command=lambda: self._send(
                            {"type": "DM_REMOVE_FROM_ENCOUNTER", "npc_id": obj.id}))
                else:
                    menu.add_command(
                        label="Add To Encounter",
                        command=lambda: self._send(
                            {"type": "DM_ADD_TO_ENCOUNTER", "npc_id": obj.id}))
                npc_action_menu = tk.Menu(menu, tearoff=0,
                                          bg=PALETTE["card"], fg=PALETTE["fg"])
                if obj.Actions:
                    for aname in obj.Actions:
                        npc_action_menu.add_command(
                            label=aname,
                            command=lambda a=aname: self._dm_npc_target_select(obj, a))
                menu.add_cascade(label="Actions", menu=npc_action_menu)
                menu.add_command(label="Speak as NPC…",
                                 command=lambda _o=obj: self._dm_speak_as_npc(_o))

        elif not is_protected:
            # Unoccupied ground — spawn options
            import uuid as _uuid_mod
            menu.add_command(label="Spawn Object",
                             command=lambda: self._spawn_from_prefabs(gx, gy))
            menu.add_command(
                label="Spawn Door",
                command=lambda: self._send({
                    "type": "DM_SPAWN_OBJECT", "cell": [gx, gy],
                    "object": {"type": "Door", "id": str(_uuid_mod.uuid4()),
                               "Open": False, "Broken": False, "Locked": False}
                })
            )
            menu.add_command(
                label="Spawn Stairs",
                command=lambda: self._send({
                    "type": "DM_SPAWN_OBJECT", "cell": [gx, gy],
                    "object": {"type": "Stairs", "id": str(_uuid_mod.uuid4()),
                               "Name": "Stairs", "Direction": "Up", "LinkedStair": ""}
                })
            )

        if uuids:
            menu.add_separator()
            for pid in uuids:
                p = self.state.players.get(pid)
                if not p:
                    continue
                p_menu = tk.Menu(menu, tearoff=0,
                                 bg=PALETTE["card"], fg=PALETTE["fg"])
                p_menu.add_command(label="Level Up",
                                   command=lambda u=pid: self._send(
                                       {"type": "DM_LEVEL_UP_PLAYER", "player_uuid": u}))
                p_menu.add_command(label="Modify Player",
                                   command=lambda u=pid, pl=p:
                                       self._dm_modify_player(u, pl))
                p_menu.add_command(label="Options",
                                   command=lambda u=pid, pl=p:
                                       self._dm_player_options(u, pl))
                menu.add_cascade(label=f"Player: {p.Name}", menu=p_menu)

        if grid_cell.walkable:
            if not is_protected:
                menu.add_separator()
                menu.add_command(label="Delete Tile",
                                 command=lambda: self._send(
                                     {"type": "DM_TILE_SET", "cell": [gx, gy],
                                      "walkable": False}))
            if grid_cell.occupant is None:
                menu.add_command(label="Warp Players Here",
                                 command=lambda: self._dm_warp(gx, gy))

        menu.tk_popup(sx, sy)

    def _open_spawn_prefab(self, gx: int, gy: int) -> None:
        from dialogs.spawn_prefab_dialog import SpawnPrefabDialog

        def _do_spawn(obj_d: dict) -> None:
            self._send({"type": "DM_SPAWN_OBJECT",
                        "cell": [gx, gy], "object": obj_d})

        SpawnPrefabDialog(self.winfo_toplevel(), self.prefabs, on_spawn=_do_spawn)

    def _modify_npc_hp(self, gx: int, gy: int) -> None:
        """In-game panel: DM enters +/- delta to adjust an NPC's Current HP."""
        cell = self.state.grid.get((gx, gy))
        if not cell or not isinstance(cell.occupant, NPC):
            return
        npc = cell.occupant

        from ui.panel import Panel
        panel = Panel(self.winfo_toplevel(), padx=28, pady=20)

        tk.Label(panel, text=f"Modify HP — {npc.Name}",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["heading"]).pack(anchor="w", pady=(0, 6))
        tk.Label(panel, text=f"Current:  {npc.CurrentHP} / {npc.MaximumHP}",
                 bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["body"]).pack(anchor="w", pady=(0, 12))

        entry_row = tk.Frame(panel, bg=PALETTE["card"])
        entry_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(entry_row, text="Amount (+/−)", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"]).pack(side=tk.LEFT, padx=(0, 10))
        delta_var = tk.StringVar(value="0")
        delta_entry = tk.Entry(entry_row, textvariable=delta_var,
                               bg=PALETTE["card2"], fg=PALETTE["fg"],
                               insertbackground=PALETTE["fg"],
                               relief=tk.FLAT, font=FONTS["body"], width=8)
        delta_entry.pack(side=tk.LEFT)
        delta_entry.focus_set()
        delta_entry.select_range(0, tk.END)

        err_var = tk.StringVar()
        tk.Label(panel, textvariable=err_var, bg=PALETTE["card"],
                 fg=PALETTE["danger"], font=FONTS["small"]).pack(pady=(0, 4))

        btn_row = tk.Frame(panel, bg=PALETTE["card"])
        btn_row.pack(anchor="e")

        def _confirm():
            try:
                delta = int(delta_var.get())
            except ValueError:
                err_var.set("Enter a whole number, e.g. −5 or +10")
                return
            # Read fresh state in case NPC was modified since menu opened
            fresh_cell = self.state.grid.get((gx, gy))
            if not fresh_cell or not isinstance(fresh_cell.occupant, NPC):
                panel.close()
                return
            fresh_npc = fresh_cell.occupant
            new_hp = fresh_npc.CurrentHP + delta
            panel.close()
            if new_hp <= 0:
                # Treat as kill — same path as combat death
                self._send({"type": "DM_DELETE_OBJECT", "cell": [gx, gy]})
            else:
                new_hp = min(fresh_npc.MaximumHP, new_hp)
                updated = dict(fresh_npc.to_dict())
                updated["CurrentHP"] = new_hp
                self._send({"type": "DM_MODIFY_OBJECT",
                            "cell": [gx, gy], "object": updated})

        delta_entry.bind("<Return>", lambda e: _confirm())
        flat_btn(btn_row, "Confirm", _confirm, style="normal").pack(
            side=tk.LEFT, padx=(0, 8), ipadx=6)
        flat_btn(btn_row, "Cancel", panel.close, style="ghost").pack(side=tk.LEFT)

    def _spawn_from_prefabs(self, gx: int, gy: int) -> None:
        """Open the prefab-picker dialog and spawn the selected object."""
        from dialogs.spawn_from_prefabs_dialog import SpawnFromPrefabsDialog
        spawnable = [p for p in self.prefabs if p.get("type") in ("NPC", "Item")]
        if not spawnable:
            from ui.panel import Panel
            panel = Panel(self.winfo_toplevel(), padx=28, pady=22)
            tk.Label(panel, text="No Prefabs Loaded", bg=PALETTE["card"],
                     fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 8))
            tk.Label(panel,
                     text=(
                         "No NPC or Item prefabs are loaded.\n"
                         "Use the DM Workshop or ESC → Prefab Objects\n"
                         "to create some first."),
                     bg=PALETTE["card"], fg=PALETTE["fg"], font=FONTS["body"],
                     justify="left").pack(anchor="w", pady=(0, 16))
            flat_btn(panel, "OK", panel.close, style="normal").pack(fill=tk.X, ipady=4)
            return
        SpawnFromPrefabsDialog(
            self.winfo_toplevel(),
            prefabs=spawnable,
            on_spawn=lambda obj_d: self._send({
                "type": "DM_SPAWN_OBJECT",
                "cell": [gx, gy],
                "object": obj_d,
            }),
        )

    def _dm_spawn(self, gx, gy) -> None:
        from dialogs.spawn_object_dialog import SpawnObjectDialog

        def _on_spawn(obj_d):
            self._send({"type": "DM_SPAWN_OBJECT", "cell": [gx, gy], "object": obj_d})
            # Add to session prefabs so it appears in Spawn Prefab list
            self.prefabs.append(dict(obj_d))

        SpawnObjectDialog(
            self.winfo_toplevel(),
            on_spawn=_on_spawn,
            settings=self.state.settings,
            prefabs=self.prefabs,
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
            prefabs=self.prefabs,
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
            multiplier=self.state.settings.hp_base_multiplier,
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
        self._esc_panel = panel

        def _close():
            self._esc_open = False
            self._esc_panel = None
            panel.close()

        tk.Label(panel, text="Menu", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 12))

        flat_btn(panel, "Main Menu",
                 lambda: (_close(), self._go_main_menu()),
                 style="ghost").pack(fill=tk.X, pady=3, ipady=3)
        if self.is_dm:
            flat_btn(panel, "Prefab Objects",
                     lambda: (_close(), self._open_ingame_prefab_builder()),
                     style="ghost").pack(fill=tk.X, pady=3, ipady=3)
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

    def _open_ingame_prefab_builder(self) -> None:
        """Full-window overlay: browse/add session prefabs without touching disk."""
        import uuid as _uuid
        from app.constants import FONTS as _F
        from ui.widgets import flat_btn as _btn, hr as _hr
        from screens.dm_tool import _EmbeddedSpawnForm, _COLS

        root = self.winfo_toplevel()
        # Working copy — Confirm commits it; Discard throws it away
        temp = list(self.prefabs)

        overlay = tk.Frame(root, bg=PALETTE["bg"])
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        overlay.lift()

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(overlay, bg=PALETTE["card2"], height=44)
        hdr.pack(side=tk.TOP, fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Session Prefab Objects",
                 bg=PALETTE["card2"], fg=PALETTE["fg"],
                 font=_F["heading"], padx=20).pack(side=tk.LEFT, pady=6)

        # ── Bottom bar (before content so expand fills middle) ────────────────
        tk.Frame(overlay, bg=PALETTE["border"], height=1).pack(side=tk.BOTTOM, fill=tk.X)
        bar = tk.Frame(overlay, bg=PALETTE["card2"], height=54)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)
        bf = tk.Frame(bar, bg=PALETTE["card2"])
        bf.pack(side=tk.RIGHT, padx=20, pady=8)

        def _confirm():
            self.prefabs[:] = temp
            overlay.destroy()

        def _discard():
            overlay.destroy()

        _btn(bf, "✓  Confirm Changes", _confirm, style="success").pack(
            side=tk.LEFT, padx=(0, 12), ipadx=8, ipady=4)
        _btn(bf, "✕  Discard Changes", _discard, style="danger").pack(
            side=tk.LEFT, ipadx=8, ipady=4)

        # ── Content ───────────────────────────────────────────────────────────
        content = tk.Frame(overlay, bg=PALETTE["bg"])
        content.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=10)

        left = tk.Frame(content, bg=PALETTE["card"],
                        highlightthickness=1, highlightbackground=PALETTE["border"])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        right = tk.Frame(content, bg=PALETTE["card"],
                         highlightthickness=1, highlightbackground=PALETTE["border"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        # ── Left: spawn form using session objects ────────────────────────────
        tk.Label(left, text="Add Object to Prefabs",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=_F["heading"], padx=14, pady=10).pack(anchor="w")
        tk.Frame(left, bg=PALETTE["border"], height=1).pack(fill=tk.X)

        def _on_add(obj_dict):
            obj_dict["id"] = str(_uuid.uuid4())
            temp.append(obj_dict)
            _refresh()

        form = _EmbeddedSpawnForm(
            left, on_add=_on_add,
            get_session_objects=lambda: temp)
        form.pack(fill=tk.BOTH, expand=True)

        # ── Right: live table of temp prefabs ─────────────────────────────────
        tk.Label(right, text="Prefab Objects",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=_F["heading"], padx=14, pady=10).pack(anchor="w")
        tk.Frame(right, bg=PALETTE["border"], height=1).pack(fill=tk.X)

        col_hdr = tk.Frame(right, bg=PALETTE["bg"], padx=6, pady=5)
        col_hdr.pack(fill=tk.X)
        for col, w in _COLS:
            tk.Label(col_hdr, text=col, bg=PALETTE["bg"],
                     fg="#ffffff", font=_F["form_label"],
                     width=w, anchor="w").pack(side=tk.LEFT, padx=2)
        tk.Label(col_hdr, text="", bg=PALETTE["bg"], width=3).pack(side=tk.LEFT)

        list_outer = tk.Frame(right, bg=PALETTE["card"])
        list_outer.pack(fill=tk.BOTH, expand=True)
        vsb = tk.Scrollbar(list_outer, bg=PALETTE["card2"],
                           troughcolor=PALETTE["bg"], width=6)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))
        tbl_canvas = tk.Canvas(list_outer, bg=PALETTE["card"],
                               highlightthickness=0, yscrollcommand=vsb.set)
        tbl_canvas.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=tbl_canvas.yview)
        tbl_inner = tk.Frame(tbl_canvas, bg=PALETTE["card"])
        _win = tbl_canvas.create_window((0, 0), window=tbl_inner, anchor="nw")
        tbl_inner.bind("<Configure>",
                       lambda e: tbl_canvas.configure(
                           scrollregion=tbl_canvas.bbox("all")))
        tbl_canvas.bind("<Configure>",
                        lambda e: tbl_canvas.itemconfig(_win, width=e.width - 8))

        def _refresh():
            for w in tbl_inner.winfo_children():
                w.destroy()
            if not temp:
                tk.Label(tbl_inner, text="No objects added yet.",
                         bg=PALETTE["card"], fg=PALETTE["muted"],
                         font=_F["body"], pady=20).pack()
                return
            for i, obj in enumerate(temp):
                bg = PALETTE["card2"] if i % 2 == 0 else PALETTE["card"]
                row = tk.Frame(tbl_inner, bg=bg, cursor="hand2", pady=4)
                row.pack(fill=tk.X)
                col_vals = {
                    "name":        str(obj.get("Name", obj.get("type", "?")))[:18],
                    "type":        str(obj.get("type", "?"))[:8],
                    "description": str(obj.get("Description", ""))[:24],
                }
                for col_t, w in _COLS:
                    tk.Label(row, text=col_vals.get(col_t.lower(), ""),
                             bg=bg, fg=PALETTE["fg"], font=_F["body"],
                             width=w, anchor="w", padx=6).pack(side=tk.LEFT)
                def _del(idx=i):
                    temp.pop(idx)
                    _refresh()
                tk.Button(row, text="×", command=_del,
                          bg=PALETTE["danger"], fg="#fff",
                          relief=tk.FLAT, font=_F["small"],
                          cursor="hand2", padx=4).pack(side=tk.RIGHT, padx=4)

        _refresh()

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
        """Return True if any text-input widget has keyboard focus."""
        try:
            focused = self.winfo_toplevel().focus_get()
            return isinstance(focused, (tk.Entry, tk.Text))
        except Exception:
            return False

    def _update_hud(self) -> None:
        if self.is_dm and self.server and hasattr(self, "_conn_lbl"):
            n = sum(1 for uid in self.server.clients if uid != self.server.host_uuid)
            ip = self.server.local_ip
            self._conn_lbl.config(
                text=f"🔌 {ip}:{self.server.port}   {n} player(s) online"
            )
