from __future__ import annotations
import asyncio
import base64
import struct
import json
import threading
import queue
import uuid
import time
import random
import colorsys
import socket
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Tuple, List

from network.protocol import encode_msg
from game.state import GameState, CombatState, make_initial_state
from game.objects import NPC, Item, Door, Wall, Stairs, PlayerObject, occupant_from_dict
from game.stats import clamp_stats, calc_max_hp, apply_action, effective_stat
from game.combat import build_turn_queue, advance_turn, remove_combatant, roll_initiative
from app.config import STAT_KEYS, load_game_config, get_base_dir
from app.constants import RESERVED_HUES, HUE_EXCLUSION_RADIUS


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ClientConn:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.uuid: Optional[str] = None
        self.alias: str = ""
        self.is_host: bool = False
        self.last_ping: float = time.time()

    async def send(self, msg: dict) -> None:
        try:
            data = encode_msg(msg)
            self.writer.write(data)
            await self.writer.drain()
        except Exception:
            pass

    async def recv_msg(self) -> Optional[dict]:
        try:
            header = await self.reader.readexactly(4)
            length = struct.unpack("<I", header)[0]
            if length > 10_000_000:
                return None
            body = await self.reader.readexactly(length)
            return json.loads(body.decode("utf-8"))
        except (asyncio.IncompleteReadError, ConnectionResetError,
                ConnectionAbortedError, json.JSONDecodeError, OSError):
            return None

    def close(self) -> None:
        try:
            self.writer.close()
        except Exception:
            pass


class GameServer:
    def __init__(self, state: GameState, ui_queue: queue.Queue, port: int,
                 host_uuid: str, password: str = "",
                 prefabs: list = None):
        self.state = state
        self.ui_queue = ui_queue
        self.port = port
        self.host_uuid = host_uuid
        self.password  = password
        self._prefabs  = list(prefabs) if prefabs else []
        self._water_ticks: Dict[str, int] = {}   # pid -> consecutive ticks on water
        self.clients: Dict[str, ClientConn] = {}
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server = None
        self._player_cells: Dict[str, Tuple[int, int]] = {}

    @property
    def local_ip(self) -> str:
        return get_local_ip()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._do_stop)

    def _do_stop(self) -> None:
        if self._server:
            self._server.close()
        for conn in list(self.clients.values()):
            conn.close()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception:
            pass
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, "0.0.0.0", self.port
        )
        asyncio.ensure_future(self._buff_tick_loop())
        async with self._server:
            await self._server.serve_forever()

    async def _buff_tick_loop(self) -> None:
        """
        Every 60 s while out of combat:
          1. Apply HP Over Time buffs individually (heals then damage) for every
             player and NPC that carries active buffs.
          2. Tick buff durations by 1 minute; remove expired ones.
          3. Broadcast a single STATE_PATCH covering all changed entities.
        In-combat ticks are handled per-turn by _process_turn_end_buffs.
        """
        while True:
            await asyncio.sleep(60)
            try:
                if self.state.combat and self.state.combat.active:
                    continue

                patches = []

                # ── Players ───────────────────────────────────────────────────
                for pid, player in list(self.state.players.items()):
                    buffs = getattr(player, "Buffs", [])
                    if not isinstance(buffs, list):
                        continue
                    # Water / Drowning tick
                    pc = self._player_cells.get(pid)
                    cd = self.state.grid.get(pc) if pc else None
                    on_water = bool(cd and cd.tile_type == "water")
                    if on_water:
                        self._water_ticks[pid] = self._water_ticks.get(pid, 0) + 1
                        if self._water_ticks[pid] >= 5:
                            if not any(b.get("Name") == "Drowning" for b in player.Buffs):
                                player.Buffs.append({
                                    "Name": "Drowning",
                                    "Type": "HP Over Time",
                                    "Value": -int(self.state.settings.hp_base_multiplier),
                                    "Duration": 99999.0,
                                })
                    else:
                        self._water_ticks[pid] = 0
                        player.Buffs[:] = [b for b in player.Buffs
                                           if b.get("Name") != "Drowning"]
                    if not player.Buffs:
                        patches.append({"op": "set_player", "path": pid,
                                        "value": player.to_dict()})
                        continue
                    await self._apply_hot_buffs(player, player.Name or "Player")
                    for b in player.Buffs:
                        b["Duration"] = max(0.0, b.get("Duration", 0.0) - 1.0)
                    player.Buffs[:] = [b for b in player.Buffs if b.get("Duration", 0) > 0]
                    patches.append({"op": "set_player", "path": pid,
                                    "value": player.to_dict()})

                # ── NPCs in the grid ──────────────────────────────────────────
                for (cx, cy), cell in list(self.state.grid.items()):
                    occ = cell.occupant
                    if not isinstance(occ, NPC):
                        continue
                    buffs = getattr(occ, "Buffs", [])
                    if not isinstance(buffs, list) or not buffs:
                        continue
                    await self._apply_hot_buffs(occ, occ.Name or "NPC")
                    # Handle NPC death from DoT outside combat
                    if occ.CurrentHP <= 0:
                        cell.occupant = None
                        if self.state.combat:
                            if occ.id in (self.state.combat.encounter_npc_ids or []):
                                self.state.combat.encounter_npc_ids.remove(occ.id)
                        patches.append({"op": "set_cell",
                                        "path": f"{cx},{cy}",
                                        "value": cell.to_dict()})
                        continue
                    for b in buffs:
                        b["Duration"] = max(0.0, b.get("Duration", 0.0) - 1.0)
                    occ.Buffs[:] = [b for b in buffs if b.get("Duration", 0) > 0]
                    patches.append({"op": "set_cell",
                                    "path": f"{cx},{cy}",
                                    "value": cell.to_dict()})

                if patches:
                    await self._broadcast({"type": "STATE_PATCH", "patches": patches})
            except Exception:
                pass

    async def _handle_client(self, reader, writer) -> None:
        conn = ClientConn(reader, writer)
        try:
            msg = await asyncio.wait_for(conn.recv_msg(), timeout=15.0)
            if not msg or msg.get("type") != "HELLO":
                conn.close()
                return
            ok = await self._process_hello(conn, msg)
            if not ok:
                conn.close()
                return
            while True:
                msg = await conn.recv_msg()
                if msg is None:
                    break
                await self._dispatch(conn, msg)
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        finally:
            await self._handle_disconnect(conn)

    async def _process_hello(self, conn: ClientConn, msg: dict) -> bool:
        player_uuid = msg.get("uuid", "")
        alias = msg.get("alias", "Unknown")
        avatar_b64 = msg.get("avatar_b64")
        character_data = msg.get("character")  # PlayerObject dict, may be None

        if self._is_banned(player_uuid):
            await conn.send({"type": "REJECT", "reason": "You are banned from this server."})
            return False

        conn.uuid = player_uuid
        conn.alias = alias
        conn.is_host = (player_uuid == self.host_uuid)
        self.clients[player_uuid] = conn

        if conn.is_host:
            # DM has no player object — send full state and return (no password check)
            await conn.send({
                "type": "WELCOME",
                "player_id": player_uuid,
                "game_state": self.state.to_dict(),
                "your_cell": [0, 0],
                "connected_uuids": list(self.clients.keys()),
            })
            self.ui_queue.put(("PLAYER_JOINED", {"uuid": player_uuid, "alias": alias}))
            return True

        # ── Password check (non-DM only) ──────────────────────────────────────
        if self.password:
            if msg.get("password", "") != self.password:
                await conn.send({"type": "REJECT", "reason": "incorrect_password"})
                del self.clients[player_uuid]
                return False

        # ── Regular player ────────────────────────────────────────────────────
        # Best avatar: character image > profile image
        char_img_b64: str = (character_data or {}).get("avatar_png") or ""
        best_avatar_b64: str = char_img_b64 or avatar_b64 or ""

        if player_uuid not in self.state.players:
            color = self._assign_color(player_uuid)
            self.state.assigned_colors[player_uuid] = color
            if character_data:
                player = PlayerObject.from_dict(character_data)
                player.id = player_uuid
                player.Name = alias
                player.color = color
                # PlayerObject.from_dict already decoded character image into avatar_png.
                # Fall back to profile image if character has none.
                if not player.avatar_png and avatar_b64:
                    try:
                        player.avatar_png = base64.b64decode(avatar_b64)
                    except Exception:
                        pass
            else:
                hp = calc_max_hp("Medium", 1, 0, self.state.settings.hp_base_multiplier)
                player = PlayerObject(
                    id=player_uuid, Name=alias, color=color,
                    MaximumHP=hp, CurrentHP=hp,
                )
                if avatar_b64:
                    try:
                        player.avatar_png = base64.b64decode(avatar_b64)
                    except Exception:
                        pass
            self.state.players[player_uuid] = player
            cell = self._find_spawn_cell()
            key = f"{cell[0]},{cell[1]}"
            self.state.players_at.setdefault(key, [])
            if player_uuid not in self.state.players_at[key]:
                self.state.players_at[key].append(player_uuid)
            self._player_cells[player_uuid] = cell
        else:
            # Reconnect — refresh avatar with best available image
            player = self.state.players[player_uuid]
            if best_avatar_b64:
                try:
                    player.avatar_png = base64.b64decode(best_avatar_b64)
                except Exception:
                    pass
            cell = self._find_player_cell(player_uuid)
            if cell is None:
                cell = self._find_spawn_cell()
                key = f"{cell[0]},{cell[1]}"
                self.state.players_at.setdefault(key, [])
                if player_uuid not in self.state.players_at[key]:
                    self.state.players_at[key].append(player_uuid)
            self._player_cells[player_uuid] = cell

        if best_avatar_b64:
            self.state.avatar_cache[player_uuid] = best_avatar_b64

        your_cell = list(self._player_cells.get(player_uuid, (0, 0)))
        await conn.send({
            "type":            "WELCOME",
            "player_id":       player_uuid,
            "game_state":      self.state.to_dict(),
            "your_cell":       your_cell,
            "host_uuid":       self.host_uuid,
            "host_prefabs":    self._prefabs,
            "connected_uuids": list(self.clients.keys()),
        })

        patches = [
            {"op": "set_player", "path": player_uuid,
             "value": self.state.players[player_uuid].to_dict()},
            {"op": "set_players_at", "path": f"{your_cell[0]},{your_cell[1]}",
             "value": self.state.players_at.get(f"{your_cell[0]},{your_cell[1]}", [])},
            # Let other clients know this player is now connected
            {"op": "add_connected", "uuid": player_uuid},
        ]
        await self._broadcast_except(player_uuid, {"type": "STATE_PATCH", "patches": patches})
        self.ui_queue.put(("PLAYER_JOINED", {"uuid": player_uuid, "alias": alias}))
        return True

    async def _handle_disconnect(self, conn: ClientConn) -> None:
        # Send the player their final PlayerObject state for character persistence
        if conn.uuid and conn.uuid in self.state.players and not conn.is_host:
            try:
                await conn.send({"type": "PLAYER_DATA",
                                 "player": self.state.players[conn.uuid].to_dict()})
            except Exception:
                pass
        if conn.uuid and conn.uuid in self.clients:
            del self.clients[conn.uuid]
            alias = conn.alias
            await self._broadcast({"type": "PLAYER_DISCONNECTED", "uuid": conn.uuid, "alias": alias})
            self.ui_queue.put(("PLAYER_DISCONNECTED", {"uuid": conn.uuid, "alias": alias}))

    async def _dispatch(self, conn: ClientConn, msg: dict) -> None:
        t = msg.get("type", "")
        handlers = {
            "PLAYER_MOVE": self._h_player_move,
            "PLAYER_ACTION": self._h_player_action,
            "CHAT_SEND": self._h_chat_send,
            "DOOR_INTERACT": self._h_door_interact,
            "ITEM_PICKUP": self._h_item_pickup,
            "ITEM_DROP": self._h_item_drop,
            "ITEM_DISCARD": self._h_item_discard,
            "ITEM_USE": self._h_item_use,
            "ITEM_EQUIP": self._h_item_equip,
            "STATS_UPDATE": self._h_stats_update,
            "PLAYER_END_TURN": self._h_player_end_turn,
            "DISCONNECT": self._h_disconnect,
            "PING": self._h_ping,
            "DM_TILE_SET": self._h_dm_tile_set,
            "DM_SPAWN_OBJECT": self._h_dm_spawn_object,
            "DM_DELETE_OBJECT": self._h_dm_delete_object,
            "DM_MODIFY_OBJECT": self._h_dm_modify_object,
            "DM_MOVE_OBJECT": self._h_dm_move_object,
            "DM_WARP_PLAYERS": self._h_dm_warp_players,
            "DM_LEVEL_UP_PLAYER": self._h_dm_level_up_player,
            "DM_KICK_PLAYER": self._h_dm_kick_player,
            "DM_BAN_PLAYER": self._h_dm_ban_player,
            "DM_MODIFY_PLAYER": self._h_dm_modify_player,
            "DM_UPDATE_SETTINGS": self._h_dm_update_settings,
            "DM_ADD_TO_ENCOUNTER": self._h_dm_add_to_encounter,
            "DM_REMOVE_FROM_ENCOUNTER": self._h_dm_remove_from_encounter,
            "DM_START_COMBAT": self._h_dm_start_combat,
            "DM_END_COMBAT": self._h_dm_end_combat,
            "DM_NPC_MOVE": self._h_dm_npc_move,
            "DM_NPC_ACTION": self._h_dm_npc_action,
            "DM_NPC_END_TURN": self._h_dm_npc_end_turn,
            "DM_CHAT_AS_NPC": self._h_dm_chat_as_npc,
            "DM_LONG_REST": self._h_dm_long_rest,
            "PLAYER_TAKE_STAIRS": self._h_player_take_stairs,
        }
        h = handlers.get(t)
        if h:
            try:
                await h(conn, msg)
            except Exception:
                # Swallow handler errors — they must not propagate to
                # _handle_client's except block, which would disconnect the client
                pass

    # ── movement ──────────────────────────────────────────────────────────────

    async def _h_player_move(self, conn: ClientConn, msg: dict) -> None:
        from game.state import MOVE_COST, TURN_THRESHOLD
        tc = msg.get("target_cell", [0, 0])
        tx, ty = int(tc[0]), int(tc[1])
        pid = conn.uuid

        if self.state.combat and self.state.combat.active:
            ct = self._current_turn()
            if ct is None or ct.id != pid:
                await conn.send({"type": "CHAT_ERROR", "text": "It is not your turn."})
                return
            if not ct.can_move:
                await conn.send({"type": "CHAT_ERROR", "text": "No movement remaining this turn."})
                return

        cell = self._player_cells.get(pid)
        if cell is None:
            return
        cx, cy = cell
        target = self.state.grid.get((tx, ty))
        if not target or not target.walkable:
            return

        if self.state.combat and self.state.combat.active:
            # In combat: BFS validation up to COMBAT_MOVE_RANGE tiles
            from game.state import find_combat_move_cells
            if (tx, ty) not in find_combat_move_cells(self.state, (cx, cy)):
                return
        else:
            # Out of combat: one adjacent tile only
            if abs(tx - cx) + abs(ty - cy) != 1:
                return
        if target.occupant and not isinstance(target.occupant, (Item, Stairs)):
            if isinstance(target.occupant, (NPC, Wall)):   # Wall added
                return
            if isinstance(target.occupant, Door) and not target.occupant.Open:
                return
        for key, uuids in self.state.players_at.items():
            if pid in uuids and key != f"{tx},{ty}":
                uuids.remove(pid)

        new_key = f"{tx},{ty}"
        self.state.players_at.setdefault(new_key, [])
        if pid not in self.state.players_at[new_key]:
            self.state.players_at[new_key].append(pid)
        self._player_cells[pid] = (tx, ty)
        old_key = f"{cx},{cy}"

        patches = [
            {"op": "set_players_at", "path": old_key,
             "value": self.state.players_at.get(old_key, [])},
            {"op": "set_players_at", "path": new_key,
             "value": self.state.players_at[new_key]},
        ]

        auto_end = False
        if self.state.combat and self.state.combat.active:
            ct = self._current_turn()
            if ct and ct.id == pid:
                from game.state import MOVE_COST, TURN_THRESHOLD
                ct.points_spent += MOVE_COST
                # NOTE: do NOT include set_combat in patches — that causes a race
                # condition where a stale active:True patch arrives after COMBAT_ENDED.
                # points_spent is synced via the COMBAT_RESOURCES_USED broadcast below.
                await self._broadcast({"type": "COMBAT_RESOURCES_USED",
                                       "combatant_id": pid,
                                       "has_acted": ct.has_acted,
                                       "points_spent": ct.points_spent})
                if ct.points_spent >= TURN_THRESHOLD:
                    auto_end = True

        # ── Drowning: remove immediately if player stepped off water ─────────────
        on_water = bool(target and target.tile_type == "water")
        if not on_water:
            player = self.state.players.get(pid)
            if player and isinstance(player.Buffs, list):
                old_len = len(player.Buffs)
                player.Buffs[:] = [b for b in player.Buffs
                                   if b.get("Name") != "Drowning"]
                self._water_ticks[pid] = 0
                if len(player.Buffs) != old_len:
                    patches.append({"op": "set_player", "path": pid,
                                    "value": player.to_dict()})

        await self._broadcast({"type": "STATE_PATCH", "patches": patches})
        if auto_end:
            await self._do_advance_turn()

    # ── player action (combat/interaction) ────────────────────────────────────

    async def _h_player_action(self, conn: ClientConn, msg: dict) -> None:
        from game.state import ACTION_COST, TURN_THRESHOLD
        pid = conn.uuid
        player = self.state.players.get(pid)
        if not player:
            return

        action_name = msg.get("action_name", "")
        item_id = msg.get("item_id")
        target_id = msg.get("target_id")
        tc = msg.get("target_cell", [0, 0])
        tx, ty = int(tc[0]), int(tc[1])

        if self.state.combat and self.state.combat.active:
            ct = self._current_turn()
            if ct is None or ct.id != pid:
                await conn.send({"type": "CHAT_ERROR", "text": "It is not your turn."})
                return
            if not ct.can_act:
                await conn.send({"type": "CHAT_ERROR", "text": "No action remaining this turn."})
                return

        # Resolve target — allow None (fizzle on empty cell)
        target_cell = self.state.grid.get((tx, ty))
        target = None
        if target_cell:
            target = target_cell.occupant if target_cell.occupant else None
        if target_id:
            # Self-targeting (target_id == own uuid)
            if target_id == pid:
                target = player
            elif isinstance(target, NPC) and target.id == target_id:
                pass
            else:
                tp = self.state.players.get(target_id)
                if tp:
                    target = tp

        _UNARMED = {"Range": 1, "BaseDamage": 1, "Hits": 2,
                    "ScalesWith": {"Str": "A", "Dex": "B"}}
        scalars = None
        action = None
        if action_name == "Unarmed Attack":
            action = _UNARMED
            scalars = _UNARMED["ScalesWith"]
        elif item_id:
            item = next((i for i in player.Equipment.values() if i.id == item_id), None)
            if item and item.Actions:
                action = item.Actions.get(action_name)
                scalars = action.get("ScalesWith") if action else None

        # Validate Casts charge
        if action and action.get("Casts"):
            casts = action["Casts"]
            if casts.get("remaining", 0) <= 0:
                await conn.send({"type": "CHAT_ERROR",
                                 "text": f"{action_name} has no uses remaining."})
                return
            casts["remaining"] = max(0, casts["remaining"] - 1)
            await self._broadcast({"type": "STATE_PATCH",
                                   "patches": [{"op": "set_player", "path": pid,
                                                "value": player.to_dict()}]})

        if target is None:
            await self._broadcast_combat_chat(
                f"{player.Name} uses {action_name or 'Unarmed Attack'}. It doesn't do anything...",
                "combat_fizzle")
        else:
            total = apply_action(player, scalars, action, target, self.state.settings)
            await self._apply_damage_and_buffs(
                attacker=player, target=target, total=total,
                action=action, cell=(tx, ty),
                attacker_name=player.Name, action_name=action_name or "Attack")

        auto_end = False
        if self.state.combat and self.state.combat.active:
            ct = self._current_turn()
            if ct and ct.id == pid:
                ct.has_acted = True
                ct.points_spent += ACTION_COST
                await self._broadcast({"type": "COMBAT_RESOURCES_USED",
                                       "combatant_id": pid,
                                       "has_acted": ct.has_acted,
                                       "points_spent": ct.points_spent})
                if ct.points_spent >= TURN_THRESHOLD:
                    auto_end = True
        if auto_end:
            await self._do_advance_turn()

    async def _apply_damage_and_buffs(self, attacker, target, total: int,
                                       action: dict, cell: Tuple[int, int],
                                       attacker_name: str = "", action_name: str = "") -> None:
        """Apply damage/heal (with Defense Modifier) then apply GivesBuffs list."""
        patches = []
        target_name = getattr(target, "Name", "?")

        # ── Defense Modifier (flat damage reduction/increase) ─────────────────
        if total > 0:
            target_buffs = getattr(target, "Buffs", [])
            if isinstance(target_buffs, list):
                def_mod = sum(b.get("Value", 0) for b in target_buffs
                              if b.get("Type") == "Defense Modifier")
                if def_mod:
                    total = max(1, total - def_mod)

        if total > 0:
            target.CurrentHP = max(0, target.CurrentHP - total)
            await self._broadcast_combat_chat(
                f"{attacker_name} deals {total} damage to {target_name} with {action_name}.",
                "combat_damage")
        elif total < 0:
            target.CurrentHP = min(target.MaximumHP, target.CurrentHP + abs(total))
            await self._broadcast_combat_chat(
                f"{attacker_name} heals {target_name} for {abs(total)} HP with {action_name}.",
                "combat_heal")

        # ── Apply GivesBuffs list (supports legacy single-buff too) ──────────
        gives_buffs = []
        if action:
            if action.get("GivesBuffs"):
                gives_buffs = action["GivesBuffs"]
            elif action.get("GivesBuff"):
                gives_buffs = [{
                    "Name":     action.get("BuffName", ""),
                    "Type":     "Stat Modifier",
                    "Value":    action.get("BuffValue", 0),
                    "Duration": float(action.get("BuffDuration", 5)),
                }]
        for buff_def in gives_buffs:
            if buff_def.get("Name"):
                await self._apply_buff_def(target, buff_def, patches)

        cx, cy = cell
        if isinstance(target, NPC):
            if total >= 0 and target.CurrentHP <= 0:
                if (cx, cy) in self.state.grid:
                    self.state.grid[(cx, cy)].occupant = None
                    patches.append({"op": "set_cell", "path": f"{cx},{cy}",
                                    "value": self.state.grid[(cx, cy)].to_dict()})
                if self.state.combat and self.state.combat.active:
                    remove_combatant(self.state.combat, target.id)
                    if target.id in (self.state.combat.encounter_npc_ids or []):
                        self.state.combat.encounter_npc_ids.remove(target.id)
                    patches.append({"op": "set_combat", "value": self.state.combat.to_dict()})
            else:
                if total > 0 and not target.Hostile:
                    target.Hostile = True
                if (cx, cy) in self.state.grid:
                    self.state.grid[(cx, cy)].occupant = target
                    patches.append({"op": "set_cell", "path": f"{cx},{cy}",
                                    "value": self.state.grid[(cx, cy)].to_dict()})
        elif isinstance(target, PlayerObject):
            patches.append({"op": "set_player", "path": target.id, "value": target.to_dict()})

        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _apply_damage(self, target, total: int, cell: Tuple[int, int]) -> None:
        if target is None:
            return
        await self._apply_damage_and_buffs(target, target, total, None, cell)

    async def _apply_buff_def(self, entity, buff_def: dict, patches: list) -> None:
        """Apply a single buff definition dict to entity."""
        buffs = getattr(entity, "Buffs", None)
        if not isinstance(buffs, list):
            return
        name = buff_def.get("Name", "")
        if name == "Dispell":
            entity.Buffs.clear()
            return
        val   = int(buff_def.get("Value", 0))
        dur   = float(buff_def.get("Duration", 1))
        if val == 0 and dur <= 0:
            # Remove matching named buff
            entity.Buffs[:] = [b for b in entity.Buffs if b.get("Name") != name]
            return
        new_buff = {
            "Name":     name,
            "Type":     buff_def.get("Type", "Stat Modifier"),
            "Value":    val,
            "Duration": dur,
        }
        if buff_def.get("Stat"):
            new_buff["Stat"] = buff_def["Stat"]
        # Replace existing same-name entry or append
        for i, b in enumerate(entity.Buffs):
            if b.get("Name") == name:
                entity.Buffs[i] = new_buff
                break
        else:
            entity.Buffs.append(new_buff)
        # Turn Modifier → add extra combat turn slots
        if new_buff["Type"] == "Turn Modifier" and self.state.combat and self.state.combat.active:
            from game.combat import roll_initiative
            from game.state import CombatTurn
            etype = "player" if isinstance(entity, PlayerObject) else "npc"
            for _ in range(val):
                init = roll_initiative(entity)
                turn = CombatTurn(combatant_type=etype, id=entity.id,
                                   name=entity.Name, initiative=init)
                self.state.combat.turn_queue.insert(
                    self.state.combat.current_index + 1, turn)
            patches.append({"op": "set_combat", "value": self.state.combat.to_dict()})

    @staticmethod
    def _attempt_saving_throw(entity, buff: dict) -> Optional[str]:
        """
        Check if entity passes the saving throw for `buff`.
        Returns the stat key used if the throw SUCCEEDS (buff is removed without effect),
        or None if it fails (buff proceeds normally) or no saving throw is defined.

        Roll: stat_mod(StatValue) + randint(1, 20) >= SavingThrow[stat]
        """
        import random
        from game.stats import stat_mod
        if not buff.get("HasSavingThrow"):
            return None
        st: dict = buff.get("SavingThrow") or {}
        for stat, threshold in st.items():
            if not isinstance(threshold, (int, float)) or threshold <= 0:
                continue
            modifier = stat_mod(entity.Stats.get(stat, 0))
            roll = modifier + random.randint(1, 20)
            if roll >= threshold:
                return stat
        return None

    async def _apply_hot_buffs(self, entity, name: str) -> None:
        """
        Apply all HP Over Time buffs to entity in heal-first order, checking
        saving throws first. Buffs that pass their saving throw are removed
        without applying their effect.
        """
        buffs = getattr(entity, "Buffs", [])
        if not isinstance(buffs, list):
            return

        to_remove_via_save: list = []
        hot = [b for b in buffs if b.get("Type") == "HP Over Time"]
        heals   = [b for b in hot if b.get("Value", 0) > 0]
        damages = [b for b in hot if b.get("Value", 0) < 0]

        for buff in heals:
            stat = self._attempt_saving_throw(entity, buff)
            if stat:
                to_remove_via_save.append(buff)
                await self._broadcast_combat_chat(
                    f"{name} succeeded a saving throw for [{buff.get('Name', 'Buff')}].",
                    "system")
                continue
            amt = buff.get("Value", 0)
            entity.CurrentHP = min(entity.MaximumHP, entity.CurrentHP + amt)
            await self._broadcast_combat_chat(
                f"{name} regenerates {amt} HP from [{buff.get('Name', 'Buff')}].",
                "combat_heal")

        for buff in damages:
            stat = self._attempt_saving_throw(entity, buff)
            if stat:
                to_remove_via_save.append(buff)
                await self._broadcast_combat_chat(
                    f"{name} succeeded a saving throw for [{buff.get('Name', 'Buff')}].",
                    "system")
                continue
            amt = abs(buff.get("Value", 0))
            entity.CurrentHP = max(0, entity.CurrentHP - amt)
            await self._broadcast_combat_chat(
                f"{name} takes {amt} damage from [{buff.get('Name', 'Buff')}].",
                "combat_damage")

        for buff in to_remove_via_save:
            try:
                buffs.remove(buff)
            except ValueError:
                pass

    async def _broadcast_combat_chat(self, text: str, msg_type: str = "system") -> None:
        await self._broadcast({"type": "CHAT_RECV", "message": {
            "sender_uuid": "SYSTEM", "sender_alias": "Combat",
            "content": text, "msg_type": msg_type,
            "recipient_uuid": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }})

    async def _process_turn_end_buffs(self, entity_id: str,
                                      entity_type: str) -> None:
        """
        Called at the end of a combatant's turn.
        1. Apply HP Over Time buffs individually (heals then damage).
        2. Tick buff durations by 1 minute; remove expired buffs.
        """
        if entity_type == "player":
            entity = self.state.players.get(entity_id)
            cell = None
        else:
            cell = self.state.find_object_cell(entity_id)
            entity = self.state.grid[cell].occupant if cell else None
        if entity is None:
            return

        buffs: list = getattr(entity, "Buffs", [])
        if not isinstance(buffs, list):
            return

        name = getattr(entity, "Name", "?")

        # ── HP Over Time (heals first, then damage, each individually) ────────
        await self._apply_hot_buffs(entity, name)

        # ── Tick durations ────────────────────────────────────────────────────
        for b in buffs:
            b["Duration"] = max(0.0, b.get("Duration", 0.0) - 1.0)
        entity.Buffs[:] = [b for b in buffs if b.get("Duration", 0) > 0]

        # ── Water / Drowning (players only) ──────────────────────────────────────
        if entity_type == "player":
            pc = self._player_cells.get(entity_id)
            cell_data = self.state.grid.get(pc) if pc else None
            on_water = bool(cell_data and cell_data.tile_type == "water")
            if on_water:
                self._water_ticks[entity_id] = self._water_ticks.get(entity_id, 0) + 1
                if self._water_ticks[entity_id] >= 5:
                    has_drown = any(b.get("Name") == "Drowning" for b in entity.Buffs)
                    if not has_drown:
                        entity.Buffs.append({
                            "Name": "Drowning",
                            "Type": "HP Over Time",
                            "Value": -int(self.state.settings.hp_base_multiplier),
                            "Duration": 99999.0,
                        })
            else:
                self._water_ticks[entity_id] = 0
                entity.Buffs[:] = [b for b in entity.Buffs if b.get("Name") != "Drowning"]

        patches = []
        if entity_type == "player":
            patches.append({"op": "set_player", "path": entity_id,
                             "value": entity.to_dict()})
        else:
            patches.append({"op": "set_cell", "path": f"{cell[0]},{cell[1]}",
                             "value": self.state.grid[cell].to_dict()})
        if patches:
            await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    # ── chat ──────────────────────────────────────────────────────────────────

    async def _h_chat_send(self, conn: ClientConn, msg: dict) -> None:
        content = msg.get("content", "")
        msg_type = msg.get("msg_type", "normal")
        recipient_alias = msg.get("recipient_alias", "")
        pid = conn.uuid
        alias = conn.alias

        chat_msg = {
            "sender_uuid": pid,
            "sender_alias": alias,
            "content": content,
            "msg_type": msg_type,
            "recipient_uuid": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if msg_type == "whisper":
            target_conn = next(
                (c for c in self.clients.values()
                 if c.alias.lower() == recipient_alias.lower() and c.uuid != pid),
                None,
            )
            if not target_conn:
                await conn.send({"type": "CHAT_RECV", "message": {
                    **chat_msg, "msg_type": "error",
                    "content": "That player does not exist.",
                }})
                return
            chat_msg["recipient_uuid"] = target_conn.uuid
            out_msg = {**chat_msg, "content": f"[To {recipient_alias}]: {content}"}
            await conn.send({"type": "CHAT_RECV", "message": out_msg})
            in_msg = {**chat_msg, "content": f"[{alias}]: {content}"}
            await target_conn.send({"type": "CHAT_RECV", "message": in_msg})
        else:
            if msg_type != "whisper":
                self.state.chat_history.append(chat_msg)
            await self._broadcast({"type": "CHAT_RECV", "message": chat_msg})

    # ── door ──────────────────────────────────────────────────────────────────

    async def _h_door_interact(self, conn: ClientConn, msg: dict) -> None:
        dc = msg.get("cell", [0, 0])
        dx, dy = int(dc[0]), int(dc[1])
        action = msg.get("action", "open")
        cell = self.state.grid.get((dx, dy))
        if not cell or not isinstance(cell.occupant, Door):
            return
        door = cell.occupant
        if door.Broken:
            return
        if action == "open" and door.Locked:
            err = {"sender_uuid": "SYSTEM", "sender_alias": "SYSTEM",
                   "content": "The door is locked.", "msg_type": "system",
                   "recipient_uuid": None, "timestamp": datetime.now(timezone.utc).isoformat(),
                   "door_cell": [dx, dy]}
            await conn.send({"type": "CHAT_RECV", "message": err})
            return
        if action == "open":
            door.Open = True
        else:
            door.Open = False
            door.Locked = False
        patches = [{"op": "set_cell", "path": f"{dx},{dy}", "value": cell.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    # ── items ─────────────────────────────────────────────────────────────────

    async def _h_item_pickup(self, conn: ClientConn, msg: dict) -> None:
        ic = msg.get("cell", [0, 0])
        ix, iy = int(ic[0]), int(ic[1])
        item_id = msg.get("item_id", "")
        pid = conn.uuid
        player = self.state.players.get(pid)
        if not player:
            return
        cell = self.state.grid.get((ix, iy))
        if not cell or not isinstance(cell.occupant, Item):
            return
        if cell.occupant.id != item_id:
            return
        item = cell.occupant
        player.Inventory.append(item)
        cell.occupant = None
        patches = [
            {"op": "set_cell", "path": f"{ix},{iy}", "value": cell.to_dict()},
            {"op": "set_player", "path": pid, "value": player.to_dict()},
        ]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_item_drop(self, conn: ClientConn, msg: dict) -> None:
        pid = conn.uuid
        player = self.state.players.get(pid)
        if not player:
            return
        item_id = msg.get("item_id", "")
        item = next((i for i in player.Inventory if i.id == item_id), None)
        if not item:
            return
        pc = self._player_cells.get(pid)
        if not pc:
            return
        drop_cell = self._bfs_drop_cell(pc)
        if not drop_cell:
            return
        player.Inventory.remove(item)
        self.state.grid[drop_cell].occupant = item
        patches = [
            {"op": "set_cell", "path": f"{drop_cell[0]},{drop_cell[1]}",
             "value": self.state.grid[drop_cell].to_dict()},
            {"op": "set_player", "path": pid, "value": player.to_dict()},
        ]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_item_discard(self, conn: ClientConn, msg: dict) -> None:
        pid = conn.uuid
        player = self.state.players.get(pid)
        if not player:
            return
        item_id = msg.get("item_id", "")
        item = next((i for i in player.Inventory if i.id == item_id), None)
        if item:
            player.Inventory.remove(item)
        else:
            for slot, eq_item in list(player.Equipment.items()):
                if eq_item.id == item_id:
                    del player.Equipment[slot]
                    break
        patches = [{"op": "set_player", "path": pid, "value": player.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_item_use(self, conn: ClientConn, msg: dict) -> None:
        pid = conn.uuid
        player = self.state.players.get(pid)
        if not player:
            return
        item_id = msg.get("item_id", "")
        item = next((i for i in player.Inventory if i.id == item_id), None)
        if not item or not item.Consumable:
            return
        player.Inventory.remove(item)
        patches = [{"op": "set_player", "path": pid, "value": player.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_item_equip(self, conn: ClientConn, msg: dict) -> None:
        pid = conn.uuid
        player = self.state.players.get(pid)
        if not player:
            return
        item_id = msg.get("item_id", "")
        item = next((i for i in player.Inventory if i.id == item_id), None)
        if not item:
            return
        if item.EquipmentSlot is None:
            return
        slot = item.EquipmentSlot
        if slot in player.Equipment:
            player.Inventory.append(player.Equipment[slot])
        player.Equipment[slot] = item
        player.Inventory.remove(item)
        patches = [{"op": "set_player", "path": pid, "value": player.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    # ── stats ─────────────────────────────────────────────────────────────────

    async def _h_stats_update(self, conn: ClientConn, msg: dict) -> None:
        pid = conn.uuid
        player = self.state.players.get(pid)
        if not player:
            return
        new_stats = msg.get("stats", {})
        old_con = player.Stats.get("Con", 0)
        clamped = clamp_stats(new_stats, player.Level)
        player.Stats = clamped
        new_con = clamped.get("Con", 0)
        if new_con != old_con:
            old_max = player.MaximumHP
            new_max = calc_max_hp(player.Size, player.Level, new_con,
                                  self.state.settings.hp_base_multiplier)
            player.MaximumHP = new_max
            if new_con > old_con:
                if player.CurrentHP == old_max:
                    player.CurrentHP = new_max
            else:
                player.CurrentHP = max(1, new_max - 1)
        patches = [{"op": "set_player", "path": pid, "value": player.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    # ── combat end-turn ───────────────────────────────────────────────────────

    async def _h_player_end_turn(self, conn: ClientConn, msg: dict) -> None:
        pid = conn.uuid
        if not (self.state.combat and self.state.combat.active):
            return
        ct = self._current_turn()
        if ct is None or ct.id != pid:
            return
        await self._process_turn_end_buffs(pid, "player")
        await self._do_advance_turn()

    async def _do_advance_turn(self) -> None:
        if not (self.state.combat and self.state.combat.active):
            return
        new_turn = advance_turn(self.state.combat)
        if new_turn is None:
            return
        payload = {
            "type": "COMBAT_TURN_ADVANCED",
            "current": new_turn.to_dict(),
            "queue": [t.to_dict() for t in self.state.combat.turn_queue],
            "round": self.state.combat.round_number,
        }
        await self._broadcast(payload)
        if new_turn.combatant_type == "npc":
            npc_cell = self.state.find_object_cell(new_turn.id)
            if npc_cell:
                host_conn = self.clients.get(self.host_uuid)
                if host_conn:
                    await host_conn.send({"type": "CAMERA_CENTER",
                                          "cell": list(npc_cell)})

    async def _h_disconnect(self, conn: ClientConn, msg: dict) -> None:
        await self._handle_disconnect(conn)

    async def _h_ping(self, conn: ClientConn, msg: dict) -> None:
        conn.last_ping = time.time()
        await conn.send({"type": "PONG", "ts": msg.get("ts", 0),
                         "server_ts": time.time()})

    # ── DM handlers ───────────────────────────────────────────────────────────

    async def _h_dm_tile_set(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        cc = msg.get("cell", [0, 0])
        cx, cy = int(cc[0]), int(cc[1])
        walkable = bool(msg.get("walkable", True))
        tile_type = msg.get("tile_type", "ground")
        key = (cx, cy)
        existing = self.state.grid.get(key)

        # Never modify protected cells (initial 4×4 spawn area)
        if existing and existing.protected:
            return

        if not walkable and tile_type != "water":
            # Delete tile (middle-click erase)
            cell = self.state.grid.get(key)
            if cell and cell.protected:
                return
            if key in self.state.grid:
                del self.state.grid[key]
            patches = [{"op": "del_cell", "path": f"{cx},{cy}"}]
        else:
            is_walkable = (tile_type == "ground")
            if key not in self.state.grid:
                self.state.grid[key] = Cell(walkable=is_walkable, tile_type=tile_type)
            else:
                existing = self.state.grid[key]
                existing.walkable = is_walkable
                existing.tile_type = tile_type
            patches = [{"op": "set_cell", "path": f"{cx},{cy}",
                        "value": self.state.grid[key].to_dict()}]

        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_spawn_object(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        cc = msg.get("cell", [0, 0])
        cx, cy = int(cc[0]), int(cc[1])
        cell = self.state.grid.get((cx, cy))
        if not cell or not cell.walkable:
            return
        # Protected cells (initial 4×4) cannot have objects spawned in them
        if cell.protected:
            return
        obj_d = msg.get("object", {})
        obj_d["id"] = str(uuid.uuid4())
        obj = occupant_from_dict(obj_d)
        if obj is None:
            return
        if isinstance(obj, NPC):
            hp = calc_max_hp(obj.Size, obj.Level,
                             obj.Stats.get("Con", 0),
                             self.state.settings.hp_base_multiplier)
            if obj.MaximumHP <= 0:
                obj.MaximumHP = hp
            if obj.CurrentHP <= 0:
                obj.CurrentHP = obj.MaximumHP
        cell.occupant = obj
        patches = [{"op": "set_cell", "path": f"{cx},{cy}", "value": cell.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_delete_object(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        cc = msg.get("cell", [0, 0])
        cx, cy = int(cc[0]), int(cc[1])
        cell = self.state.grid.get((cx, cy))
        if not cell:
            return
        if cell.occupant and isinstance(cell.occupant, NPC):
            npc_id = cell.occupant.id
            if self.state.combat:
                if npc_id in self.state.combat.encounter_npc_ids:
                    self.state.combat.encounter_npc_ids.remove(npc_id)
                remove_combatant(self.state.combat, npc_id)
        cell.occupant = None
        patches = [{"op": "set_cell", "path": f"{cx},{cy}", "value": cell.to_dict()}]
        if self.state.combat:
            patches.append({"op": "set_combat", "value": self.state.combat.to_dict()})
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_modify_object(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        cc = msg.get("cell", [0, 0])
        cx, cy = int(cc[0]), int(cc[1])
        cell = self.state.grid.get((cx, cy))
        if not cell or not cell.occupant:
            return
        obj_d = msg.get("object", {})
        obj_d["id"] = cell.occupant.id
        new_obj = occupant_from_dict(obj_d)
        if new_obj is None:
            return

        patches = []

        # ── Bidirectional Stairs linking ──────────────────────────────────────
        if isinstance(new_obj, Stairs) and isinstance(cell.occupant, Stairs):
            old_link = cell.occupant.LinkedStair
            new_link = new_obj.LinkedStair

            if old_link != new_link:
                # Unlink this stair's previous partner
                if old_link:
                    old_b_pos = self.state.find_object_cell(old_link)
                    if old_b_pos:
                        old_b_cell = self.state.grid.get(old_b_pos)
                        if old_b_cell and isinstance(old_b_cell.occupant, Stairs):
                            old_b_cell.occupant.LinkedStair = ""
                            patches.append({"op": "set_cell",
                                            "path": f"{old_b_pos[0]},{old_b_pos[1]}",
                                            "value": old_b_cell.to_dict()})

                # Link new partner back to this stair
                if new_link:
                    new_b_pos = self.state.find_object_cell(new_link)
                    if new_b_pos:
                        new_b_cell = self.state.grid.get(new_b_pos)
                        if new_b_cell and isinstance(new_b_cell.occupant, Stairs):
                            # Unlink new partner's previous partner first
                            b_old_link = new_b_cell.occupant.LinkedStair
                            if b_old_link and b_old_link != cell.occupant.id:
                                b_old_pos = self.state.find_object_cell(b_old_link)
                                if b_old_pos:
                                    b_old_cell = self.state.grid.get(b_old_pos)
                                    if b_old_cell and isinstance(b_old_cell.occupant, Stairs):
                                        b_old_cell.occupant.LinkedStair = ""
                                        patches.append({"op": "set_cell",
                                                        "path": f"{b_old_pos[0]},{b_old_pos[1]}",
                                                        "value": b_old_cell.to_dict()})
                            # Point new partner back at this stair
                            new_b_cell.occupant.LinkedStair = new_obj.id
                            patches.append({"op": "set_cell",
                                            "path": f"{new_b_pos[0]},{new_b_pos[1]}",
                                            "value": new_b_cell.to_dict()})

        cell.occupant = new_obj
        patches.append({"op": "set_cell", "path": f"{cx},{cy}", "value": cell.to_dict()})
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_move_object(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        fc = msg.get("from_cell", [0, 0])
        tc = msg.get("to_cell", [0, 0])
        fx, fy = int(fc[0]), int(fc[1])
        tx, ty = int(tc[0]), int(tc[1])
        from_cell = self.state.grid.get((fx, fy))
        to_cell = self.state.grid.get((tx, ty))
        if not from_cell or not to_cell or not to_cell.walkable:
            return
        if to_cell.occupant:
            return
        obj = from_cell.occupant
        if not obj:
            return
        from_cell.occupant = None
        to_cell.occupant = obj
        patches = [
            {"op": "set_cell", "path": f"{fx},{fy}", "value": from_cell.to_dict()},
            {"op": "set_cell", "path": f"{tx},{ty}", "value": to_cell.to_dict()},
        ]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_warp_players(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        target_cells = msg.get("target_cells", [])
        connected = list(self.clients.keys())
        patches = []
        for i, pid in enumerate(connected):
            if i >= len(target_cells):
                break
            tc = target_cells[i]
            tx, ty = int(tc[0]), int(tc[1])
            old_cell = self._player_cells.get(pid)
            if old_cell:
                old_key = f"{old_cell[0]},{old_cell[1]}"
                lst = self.state.players_at.get(old_key, [])
                if pid in lst:
                    lst.remove(pid)
                patches.append({"op": "set_players_at", "path": old_key,
                                 "value": self.state.players_at.get(old_key, [])})
            new_key = f"{tx},{ty}"
            self.state.players_at.setdefault(new_key, [])
            if pid not in self.state.players_at[new_key]:
                self.state.players_at[new_key].append(pid)
            self._player_cells[pid] = (tx, ty)
            patches.append({"op": "set_players_at", "path": new_key,
                             "value": self.state.players_at[new_key]})
            pc = self.clients.get(pid)
            if pc:
                await pc.send({"type": "CAMERA_CENTER", "cell": [tx, ty]})
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_level_up_player(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        pid = msg.get("player_uuid", "")
        player = self.state.players.get(pid)
        if not player:
            return
        player.Level += 1
        new_max = calc_max_hp(player.Size, player.Level,
                              player.Stats.get("Con", 0),
                              self.state.settings.hp_base_multiplier)
        player.MaximumHP = new_max
        player.CurrentHP = new_max
        player.Stats = clamp_stats(player.Stats, player.Level)
        patches = [{"op": "set_player", "path": pid, "value": player.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_kick_player(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        pid = msg.get("player_uuid", "")
        target = self.clients.get(pid)
        if not target:
            return
        self._record_ban(pid, target.alias, temporary=True)
        if pid in self.state.players:
            try:
                await target.send({"type": "PLAYER_DATA",
                                   "player": self.state.players[pid].to_dict()})
            except Exception:
                pass
        await target.send({"type": "YOU_WERE_KICKED",
                           "reason": "You were disconnected by the host."})
        target.close()

    async def _h_dm_ban_player(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        pid = msg.get("player_uuid", "")
        target = self.clients.get(pid)
        if not target:
            return
        self._record_ban(pid, target.alias, temporary=False)
        await target.send({"type": "YOU_WERE_KICKED",
                           "reason": "You have been banned from this server."})
        target.close()

    async def _h_dm_modify_player(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        pid = msg.get("player_uuid", "")
        player = self.state.players.get(pid)
        if not player:
            return
        patch = msg.get("patch", {})
        old_con = player.Stats.get("Con", 0)
        for k, v in patch.items():
            if hasattr(player, k):
                setattr(player, k, v)
        if "Stats" in patch:
            new_con = player.Stats.get("Con", 0)
            if new_con != old_con:
                old_max = player.MaximumHP
                new_max = calc_max_hp(player.Size, player.Level, new_con,
                                      self.state.settings.hp_base_multiplier)
                player.MaximumHP = new_max
                if new_con > old_con:
                    if player.CurrentHP == old_max:
                        player.CurrentHP = new_max
                else:
                    player.CurrentHP = max(1, new_max - 1)
        patches = [{"op": "set_player", "path": pid, "value": player.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_update_settings(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        s = msg.get("settings", {})
        from game.state import GameSettings
        for k, v in s.items():
            if hasattr(self.state.settings, k):
                setattr(self.state.settings, k, v)
        mult = self.state.settings.hp_base_multiplier
        patches = []
        for pid, player in self.state.players.items():
            new_max = calc_max_hp(player.Size, player.Level,
                                  player.Stats.get("Con", 0), mult)
            player.MaximumHP = new_max
            player.CurrentHP = min(player.CurrentHP, new_max)
            patches.append({"op": "set_player", "path": pid, "value": player.to_dict()})
        for (cx, cy), cell in self.state.grid.items():
            if isinstance(cell.occupant, NPC):
                npc = cell.occupant
                new_max = calc_max_hp(npc.Size, npc.Level,
                                      npc.Stats.get("Con", 0), mult)
                npc.MaximumHP = new_max
                npc.CurrentHP = min(npc.CurrentHP, new_max)
                patches.append({"op": "set_cell", "path": f"{cx},{cy}",
                                 "value": cell.to_dict()})
        patches.append({"op": "set_settings", "value": self.state.settings.to_dict()})
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_add_to_encounter(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        npc_id = msg.get("npc_id", "")
        if not self.state.combat:
            from game.state import CombatState
            self.state.combat = CombatState()
        if npc_id not in self.state.combat.encounter_npc_ids:
            self.state.combat.encounter_npc_ids.append(npc_id)
        patches = [{"op": "set_combat", "value": self.state.combat.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_remove_from_encounter(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        npc_id = msg.get("npc_id", "")
        if self.state.combat and npc_id in self.state.combat.encounter_npc_ids:
            self.state.combat.encounter_npc_ids.remove(npc_id)
        patches = [{"op": "set_combat",
                    "value": self.state.combat.to_dict() if self.state.combat else None}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_start_combat(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        if not self.state.combat:
            from game.state import CombatState
            self.state.combat = CombatState()
        enc_ids = self.state.combat.encounter_npc_ids[:]
        npc_pairs = []
        for nid in enc_ids:
            cell = self.state.find_object_cell(nid)
            if cell:
                npc = self.state.grid[cell].occupant
                if isinstance(npc, NPC):
                    npc_pairs.append((nid, npc))
        queue_list = build_turn_queue(self.state.players, npc_pairs)
        self.state.combat.turn_queue = queue_list
        self.state.combat.active = True
        self.state.combat.current_index = 0
        self.state.combat.round_number = 1
        if queue_list:
            queue_list[0].has_moved = False
            queue_list[0].has_acted = False
        await self._broadcast({
            "type": "COMBAT_STARTED",
            "turn_queue": [t.to_dict() for t in queue_list],
            "round": 1,
        })
        patches = [{"op": "set_combat", "value": self.state.combat.to_dict()}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_end_combat(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        if self.state.combat:
            self.state.combat.active = False
            self.state.combat.turn_queue = []
            self.state.combat.current_index = 0
        await self._broadcast({"type": "COMBAT_ENDED"})
        patches = [{"op": "set_combat",
                    "value": self.state.combat.to_dict() if self.state.combat else None}]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})

    async def _h_dm_npc_move(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        npc_id = msg.get("npc_id", "")
        tc = msg.get("target_cell", [0, 0])
        tx, ty = int(tc[0]), int(tc[1])
        src = self.state.find_object_cell(npc_id)
        if not src:
            return
        sx, sy = src
        target_cell = self.state.grid.get((tx, ty))
        if not target_cell or not target_cell.walkable:
            return

        if self.state.combat and self.state.combat.active:
            # In combat: BFS validation up to COMBAT_MOVE_RANGE tiles
            from game.state import find_combat_move_cells
            if (tx, ty) not in find_combat_move_cells(self.state, (sx, sy)):
                return
        else:
            # Out of combat: adjacent empty cells only
            if abs(tx - sx) + abs(ty - sy) != 1:
                return
            if target_cell.occupant:
                return
        npc = self.state.grid[src].occupant
        self.state.grid[src].occupant = None
        self.state.grid[(tx, ty)].occupant = npc
        patches = [
            {"op": "set_cell", "path": f"{sx},{sy}",
             "value": self.state.grid[src].to_dict()},
            {"op": "set_cell", "path": f"{tx},{ty}",
             "value": self.state.grid[(tx, ty)].to_dict()},
        ]
        auto_end = False
        if self.state.combat and self.state.combat.active:
            ct = self._current_turn()
            if ct and ct.id == npc_id:
                from game.state import MOVE_COST, TURN_THRESHOLD
                ct.points_spent += MOVE_COST
                # Do NOT append set_combat — avoids stale active:True race condition.
                await self._broadcast({"type": "COMBAT_RESOURCES_USED",
                                       "combatant_id": npc_id,
                                       "has_acted": ct.has_acted,
                                       "points_spent": ct.points_spent})
                if ct.points_spent >= TURN_THRESHOLD:
                    auto_end = True
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})
        if auto_end:
            await self._process_turn_end_buffs(npc_id, "npc")
            await self._do_advance_turn()

    async def _h_dm_npc_action(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        npc_id = msg.get("npc_id", "")
        action_name = msg.get("action_name", "Default Attack")
        target_id = msg.get("target_id", "")
        tc = msg.get("target_cell", [0, 0])
        tx, ty = int(tc[0]), int(tc[1])

        npc_cell = self.state.find_object_cell(npc_id)
        if not npc_cell:
            return
        npc = self.state.grid[npc_cell].occupant
        if not isinstance(npc, NPC):
            return

        target = None
        target_player = self.state.players.get(target_id)
        if target_player:
            target = target_player
        else:
            tc_cell = self.state.grid.get((tx, ty))
            if tc_cell and tc_cell.occupant:
                target = tc_cell.occupant

        _UNARMED = {"Range": 1, "BaseDamage": 1, "Hits": 2,
                    "ScalesWith": {"Str": "A", "Dex": "B"}}
        if action_name == "Unarmed Attack":
            action = _UNARMED
            scalars = _UNARMED["ScalesWith"]
        elif action_name == "Default Attack" or not (npc.Actions and action_name in npc.Actions):
            scalars, action = None, None
        else:
            action = npc.Actions[action_name]
            scalars = action.get("ScalesWith") or getattr(npc, "Scalars", None)

        if target is None:
            await self._broadcast_combat_chat(
                f"{npc.Name} uses {action_name}. It doesn't do anything...",
                "combat_fizzle")
        else:
            total = apply_action(npc, scalars, action, target, self.state.settings)
            await self._apply_damage_and_buffs(
                attacker=npc, target=target, total=total,
                action=action, cell=(tx, ty),
                attacker_name=npc.Name, action_name=action_name)

        auto_end = False
        if self.state.combat and self.state.combat.active:
            ct = self._current_turn()
            if ct and ct.id == npc_id:
                from game.state import ACTION_COST, TURN_THRESHOLD
                ct.has_acted = True
                ct.points_spent += ACTION_COST
                await self._broadcast({"type": "COMBAT_RESOURCES_USED",
                                       "combatant_id": npc_id,
                                       "has_acted": True,
                                       "points_spent": ct.points_spent})
                if ct.points_spent >= TURN_THRESHOLD:
                    auto_end = True
        if auto_end:
            await self._process_turn_end_buffs(npc_id, "npc")
            await self._do_advance_turn()

    async def _h_dm_npc_end_turn(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        npc_id = msg.get("npc_id", "")
        if not (self.state.combat and self.state.combat.active):
            return
        ct = self._current_turn()
        if ct is None or ct.id != npc_id:
            return
        await self._process_turn_end_buffs(npc_id, "npc")
        await self._do_advance_turn()

    async def _h_dm_chat_as_npc(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        npc_id = msg.get("npc_id", "")
        content = msg.get("content", "")
        msg_type = msg.get("msg_type", "normal")
        recipient_alias = msg.get("recipient_alias", "")

        npc_cell = self.state.find_object_cell(npc_id)
        if not npc_cell:
            return
        npc = self.state.grid[npc_cell].occupant
        if not isinstance(npc, NPC):
            return

        chat_msg = {
            "sender_uuid": f"NPC:{npc_id}",
            "sender_alias": npc.Name,
            "content": content,
            "msg_type": msg_type,
            "recipient_uuid": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "npc_cell": list(npc_cell),
        }
        if msg_type == "whisper":
            target_conn = next(
                (c for c in self.clients.values()
                 if c.alias.lower() == recipient_alias.lower()),
                None,
            )
            if target_conn:
                await conn.send({"type": "CHAT_RECV", "message": chat_msg})
                if target_conn.uuid != conn.uuid:
                    await target_conn.send({"type": "CHAT_RECV", "message": chat_msg})
        else:
            self.state.chat_history.append(chat_msg)
            await self._broadcast({"type": "CHAT_RECV", "message": chat_msg})

    async def _h_player_take_stairs(self, conn: ClientConn, msg: dict) -> None:
        pid = conn.uuid
        stair_id = msg.get("stair_id", "")
        # Validate player is on a cell with this stair
        player_cell = self._find_player_cell(pid)
        if not player_cell:
            return
        grid_cell = self.state.grid.get(player_cell)
        if not grid_cell or not isinstance(grid_cell.occupant, Stairs):
            return
        if grid_cell.occupant.id != stair_id:
            return
        linked_id = grid_cell.occupant.LinkedStair
        if not linked_id:
            return
        dest_cell = self.state.find_object_cell(linked_id)
        if not dest_cell:
            return
        lx, ly = dest_cell
        # Move player
        old_key = f"{player_cell[0]},{player_cell[1]}"
        new_key = f"{lx},{ly}"
        lst = self.state.players_at.get(old_key, [])
        if pid in lst:
            lst.remove(pid)
        self.state.players_at.setdefault(new_key, [])
        if pid not in self.state.players_at[new_key]:
            self.state.players_at[new_key].append(pid)
        self._player_cells[pid] = (lx, ly)
        patches = [
            {"op": "set_players_at", "path": old_key,
             "value": self.state.players_at.get(old_key, [])},
            {"op": "set_players_at", "path": new_key,
             "value": self.state.players_at[new_key]},
        ]
        await self._broadcast({"type": "STATE_PATCH", "patches": patches})
        pc = self.clients.get(pid)
        if pc:
            await pc.send({"type": "CAMERA_CENTER", "cell": [lx, ly]})

    async def _h_dm_long_rest(self, conn: ClientConn, msg: dict) -> None:
        if not conn.is_host:
            return
        patches = []
        for pid, player in self.state.players.items():
            changed = False
            for item in list(player.Equipment.values()) + list(player.Inventory):
                if item.Actions:
                    for action in item.Actions.values():
                        casts = action.get("Casts")
                        if casts:
                            casts["remaining"] = casts.get("max_per_rest", 0)
                            changed = True
            if changed:
                patches.append({"op": "set_player", "path": pid,
                                 "value": player.to_dict()})
        for (cx, cy), cell in self.state.grid.items():
            if isinstance(cell.occupant, NPC):
                npc = cell.occupant
                if npc.Actions:
                    changed = False
                    for action in npc.Actions.values():
                        casts = action.get("Casts")
                        if casts:
                            casts["remaining"] = casts.get("max_per_rest", 0)
                            changed = True
                    if changed:
                        patches.append({"op": "set_cell",
                                         "path": f"{cx},{cy}",
                                         "value": cell.to_dict()})
        if patches:
            await self._broadcast({"type": "STATE_PATCH", "patches": patches})
        await self._broadcast({"type": "CHAT_RECV", "message": {
            "sender_uuid": "SYSTEM", "sender_alias": "SYSTEM",
            "content": "🌙 Long Rest — all action charges restored.",
            "msg_type": "system", "recipient_uuid": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }})

    # ── helpers ───────────────────────────────────────────────────────────────

    def _current_turn(self):
        if not self.state.combat or not self.state.combat.turn_queue:
            return None
        idx = self.state.combat.current_index
        if idx >= len(self.state.combat.turn_queue):
            return None
        return self.state.combat.turn_queue[idx]

    async def _broadcast(self, msg: dict) -> None:
        for conn in list(self.clients.values()):
            await conn.send(msg)

    async def _broadcast_except(self, exclude_uuid: str, msg: dict) -> None:
        for uid, conn in list(self.clients.items()):
            if uid != exclude_uuid:
                await conn.send(msg)

    def _find_spawn_cell(self) -> Tuple[int, int]:
        occupied = set()
        for key, uuids in self.state.players_at.items():
            if uuids:
                x, y = map(int, key.split(","))
                occupied.add((x, y))
        for x in range(4):
            for y in range(4):
                if (x, y) not in occupied and (x, y) in self.state.grid:
                    return (x, y)
        for (x, y), cell in self.state.grid.items():
            if cell.walkable and not cell.occupant and (x, y) not in occupied:
                return (x, y)
        return (0, 0)

    def _find_player_cell(self, player_uuid: str) -> Optional[Tuple[int, int]]:
        if player_uuid in self._player_cells:
            return self._player_cells[player_uuid]
        return self.state.find_player_cell(player_uuid)

    def _assign_color(self, player_uuid: str) -> str:
        used_hues = []
        for uid, color in self.state.assigned_colors.items():
            try:
                r = int(color[1:3], 16) / 255
                g = int(color[3:5], 16) / 255
                b = int(color[5:7], 16) / 255
                h, s, v = colorsys.rgb_to_hsv(r, g, b)
                used_hues.append(h)
            except Exception:
                pass

        # Reserved hues: NPC red, NPC green, Item orange, door brown,
        # yell salmon, DM orange, whisper blue/purple, gray/white/black
        reserved = [
            0.000,  # red (NPC hostile)
            0.030,  # salmon/yell
            0.080,  # orange (DM chat, Item)
            0.110,  # orange-yellow
            0.167,  # yellow
            0.333,  # green (NPC friendly)
            0.050,  # red-orange (door-ish)
            0.600,  # cyan-blue area
            0.650,  # blue (whisper)
            0.700,  # blue-purple
            0.750,  # purple
            0.800,  # purple-magenta
        ]
        all_blocked = reserved + used_hues
        exclusion = 0.10  # wider exclusion radius

        best_h = None
        best_dist = -1.0
        for i in range(72):  # 5-degree steps
            candidate_h = i / 72
            min_dist = min(
                min(abs(candidate_h - h), 1.0 - abs(candidate_h - h))
                for h in all_blocked
            ) if all_blocked else 1.0
            if min_dist < exclusion:
                continue
            if min_dist > best_dist:
                best_dist = min_dist
                best_h = candidate_h

        if best_h is None:
            # Fallback: use deterministic hue from UUID
            best_h = (sum(ord(c) for c in player_uuid) % 360) / 360.0

        # Full brightness, high saturation — never dark or washed out
        r, g, b = colorsys.hsv_to_rgb(best_h, 0.85, 1.0)
        return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))

    def _bfs_drop_cell(self, origin: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        from collections import deque
        visited = {origin}
        q = deque([origin])
        while q:
            cx, cy = q.popleft()
            cell = self.state.grid.get((cx, cy))
            if cell and cell.walkable and cell.occupant is None:
                occupied_by_players = any(
                    (cx, cy) == self._player_cells.get(pid)
                    for pid in self.clients
                )
                if not occupied_by_players:
                    return (cx, cy)
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nb = (cx + dx, cy + dy)
                if nb not in visited:
                    visited.add(nb)
                    q.append(nb)
            if len(visited) > 500:
                break
        return None

    def _is_banned(self, player_uuid: str) -> bool:
        banlist = self._load_banlist()
        now = datetime.now(timezone.utc)
        for record in banlist:
            if record.get("uuid") == player_uuid:
                expires = record.get("expires_at")
                if expires is None:
                    return True
                try:
                    exp_dt = datetime.fromisoformat(expires)
                    if exp_dt.tzinfo is None:
                        import pytz
                        exp_dt = pytz.utc.localize(exp_dt)
                    if now < exp_dt:
                        return True
                except Exception:
                    return True
        return False

    def _record_ban(self, player_uuid: str, alias: str, temporary: bool) -> None:
        banlist = self._load_banlist()
        now = datetime.now(timezone.utc)
        expires = None
        reason = "ban"
        if temporary:
            from datetime import timedelta
            expires = (now + timedelta(seconds=60)).isoformat()
            reason = "temp_disconnect"
        banlist = [r for r in banlist if r.get("uuid") != player_uuid]
        banlist.append({
            "uuid": player_uuid,
            "alias": alias,
            "banned_at": now.isoformat(),
            "expires_at": expires,
            "reason": reason,
        })
        self._save_banlist(banlist)

    def _load_banlist(self) -> list:
        path = get_base_dir() / "banlist.json"
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_banlist(self, banlist: list) -> None:
        path = get_base_dir() / "banlist.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(banlist, f, indent=2)

    def send_to_all(self, msg: dict) -> None:
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)

    def kick_all_with_message(self, reason: str) -> None:
        async def _kick():
            for pid, conn in list(self.clients.items()):
                # Send character data before kicking
                if pid in self.state.players and not conn.is_host:
                    try:
                        await conn.send({"type": "PLAYER_DATA",
                                         "player": self.state.players[pid].to_dict()})
                    except Exception:
                        pass
                await conn.send({"type": "YOU_WERE_KICKED", "reason": reason})
                conn.close()
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(_kick(), self._loop)


from game.state import Cell
