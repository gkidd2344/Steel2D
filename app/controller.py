import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Optional, List

from app.constants import PALETTE, FONTS
from app.config import load_user_config, save_user_config


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Steel2D")
        self.geometry("1280x720")
        self.minsize(900, 600)
        self.configure(bg=PALETTE["bg"])
        self._user_config = load_user_config()
        self._current_screen = None
        self._ui_queue: Optional[queue.Queue] = None
        self._client = None
        self._server = None
        self._host_dialog = None        # HostDialog kept open behind New/Load submenus
        self.prefabs: List[dict] = []   # loaded prefab objects (DM-hosted games only)
        self.protocol("WM_DELETE_WINDOW", self.on_quit)
        self.bind("<<GoMainMenu>>", lambda e: self.show_main_menu())
        self.show_main_menu()

    # ── screens ───────────────────────────────────────────────────────────────

    def show_main_menu(self) -> None:
        self._close_host_dialog()
        self._cleanup_session()
        self._swap_screen(lambda p: self._make_main_menu(p))

    def _make_main_menu(self, parent):
        from screens.main_menu import MainMenuScreen
        return MainMenuScreen(
            parent,
            user_config=self._user_config,
            on_profile=self.show_profile,
            on_character=self.show_character_editor,
            on_dm_tool=self.show_dm_tool,
            on_host=self._host_flow,
            on_join=self._join_flow,
            on_quit=self.on_quit,
        )

    def show_profile(self) -> None:
        self._swap_screen(lambda p: self._make_profile(p))

    def _make_profile(self, parent):
        from screens.profile import ProfileScreen
        return ProfileScreen(
            parent,
            user_config=self._user_config,
            on_save=self._on_profile_saved,
            on_cancel=self.show_main_menu,
        )

    def _on_profile_saved(self, updated_config: dict) -> None:
        self._user_config = updated_config
        self.show_main_menu()

    def show_dm_tool(self) -> None:
        self._swap_screen(lambda p: self._make_dm_tool(p))

    def _make_dm_tool(self, parent):
        from screens.dm_tool import DmToolScreen
        return DmToolScreen(parent, on_exit=self.show_main_menu)

    # ── character editor ──────────────────────────────────────────────────────

    def show_character_editor(self) -> None:
        self._swap_screen(lambda p: self._make_character_editor(p))

    def _make_character_editor(self, parent):
        from screens.character_editor import CharacterEditorScreen
        return CharacterEditorScreen(parent, on_save=self._on_character_saved,
                                     on_cancel=self.show_main_menu)

    def _on_character_saved(self) -> None:
        self.show_main_menu()

    # ── host / join flows ─────────────────────────────────────────────────────

    def _host_flow(self) -> None:
        from dialogs.host_dialog import HostDialog
        # Kept open behind the New/Load submenus so cancelling a submenu returns
        # here with all fields intact. Closed for real in _do_launch_dm_game.
        self._host_dialog = HostDialog(
            self,
            on_new_game=self._new_game_flow,
            on_load_game=self._load_game_flow,
        )

    def _close_host_dialog(self) -> None:
        dlg = self._host_dialog
        self._host_dialog = None
        if dlg is not None:
            try:
                dlg.close()
            except Exception:
                pass

    def _new_game_flow(self, password: str = "", port: int = 5000,
                       display_ip: str = "", network_play: bool = False) -> None:
        from app.config import load_game_config
        from game.state import GameSettings, make_initial_state
        cfg = load_game_config()
        settings = GameSettings(
            hp_base_multiplier=float(cfg.get("hp_base_multiplier", 4.0)),
            enemy_damage_multiplier=float(cfg.get("enemy_damage_multiplier", 1.0)),
            los_max_distance=int(cfg.get("los_max_distance", 20)),
        )
        state = make_initial_state("Untitled", settings)
        self._launch_dm_game(state, password=password, port=port,
                             display_ip=display_ip, network_play=network_play)

    def _load_game_flow(self, password: str = "", port: int = 5000,
                        display_ip: str = "", network_play: bool = False) -> None:
        from dialogs.load_game_dialog import LoadGameDialog
        LoadGameDialog(self, on_load=lambda state: self._launch_dm_game(
            state, password=password, port=port, display_ip=display_ip,
            network_play=network_play))

    def _launch_dm_game(self, state, password: str = "", port: int = 5000,
                        display_ip: str = "", network_play: bool = False) -> None:
        # Let the host pick which prefab files to load before the game starts.
        from app.config import list_prefab_files
        files = list_prefab_files()
        if not files:
            self.prefabs = []
            self._do_launch_dm_game(state, password, port, display_ip, network_play)
            return

        from dialogs.prefab_select_dialog import PrefabSelectDialog

        def _on_confirm(selected_paths: list) -> None:
            from app.config import load_prefabs_from_files
            self.prefabs = load_prefabs_from_files(selected_paths)
            self._do_launch_dm_game(state, password, port, display_ip, network_play)

        PrefabSelectDialog(self, files, on_confirm=_on_confirm)

    def _do_launch_dm_game(self, state, password: str = "", port: int = 5000,
                          display_ip: str = "", network_play: bool = False) -> None:
        # Committed to launching — the Host dialog is no longer needed.
        self._close_host_dialog()
        self._ui_queue = queue.Queue()
        uid = self._user_config["uuid"]
        alias = self._user_config.get("alias", "DM")

        from network.server import GameServer
        server = GameServer(state, self._ui_queue, port, host_uuid=uid,
                            password=password, prefabs=list(self.prefabs),
                            display_ip=display_ip, lan_only=not network_play)
        server.start()
        self._server = server

        time.sleep(0.3)

        from network.client import GameClient
        client = GameClient(
            "127.0.0.1", port, self._ui_queue,
            player_uuid=uid,
            alias=alias,
            avatar_b64=self._user_config.get("avatar_b64"),
            # DM does not send character data; they have no player object
        )
        client.start()
        self._client = client

        connected = client.wait_connected(timeout=10.0)
        if not connected:
            messagebox.showerror("Error", "Could not connect to local server.")
            server.stop()
            self.show_main_menu()
            return

        try:
            _, welcome = self._ui_queue.get(timeout=5.0)
        except queue.Empty:
            messagebox.showerror("Error", "Server did not respond.")
            server.stop()
            self.show_main_menu()
            return

        connected_uuids = set(welcome.get("connected_uuids", []))

        from screens.game import GameScreen
        self._swap_screen(lambda p: GameScreen(
            p, state, client, server, self._ui_queue,
            local_uuid=uid, is_dm=True,
            prefabs=list(self.prefabs),
            connected_uuids=connected_uuids,
        ))

    def _join_flow(self) -> None:
        from dialogs.join_dialog import JoinDialog
        JoinDialog(self, on_join=self._connect_as_player)

    def _connect_as_player(self, host: str, port: int, password: str = "") -> None:
        # Remember join params in case we need to re-open on wrong password
        self._last_join_host = host
        self._last_join_port = port

        self._ui_queue = queue.Queue()
        uid = self._user_config["uuid"]
        alias = self._user_config.get("alias", "Player")

        from app.config import load_character
        character_data = load_character()   # None if no character file yet

        from network.client import GameClient
        client = GameClient(
            host, port, self._ui_queue,
            player_uuid=uid,
            alias=alias,
            avatar_b64=self._user_config.get("avatar_b64"),
            password=password,
            character_data=character_data,
        )
        client.start()
        self._client = client

        connecting_label = tk.Label(self, text="Connecting…",
                                    bg=PALETTE["bg"], fg=PALETTE["fg"],
                                    font=FONTS["heading"])
        connecting_label.place(relx=0.5, rely=0.5, anchor="center")
        self.update()

        def _wait():
            try:
                event_type, payload = self._ui_queue.get(timeout=12.0)
            except queue.Empty:
                self.after(0, lambda: self._join_failed("Connection timed out."))
                return
            self.after(0, lambda et=event_type, p=payload:
                       self._handle_connect(et, p, connecting_label))

        threading.Thread(target=_wait, daemon=True).start()

    def _handle_connect(self, event_type: str, payload: dict, loading_lbl) -> None:
        try:
            loading_lbl.destroy()
        except Exception:
            pass

        if event_type == "REJECT":
            reason = payload.get("reason", "")
            if reason == "incorrect_password":
                # Re-open join dialog with same host/port, cleared password, error shown
                from dialogs.join_dialog import JoinDialog
                JoinDialog(
                    self,
                    on_join=self._connect_as_player,
                    prefill_host=getattr(self, "_last_join_host", "127.0.0.1"),
                    prefill_port=getattr(self, "_last_join_port", 5000),
                    error="Provided password was incorrect.",
                )
                return
            messagebox.showerror("Rejected", reason or "Connection refused.")
            self.show_main_menu()
            return
        if event_type in ("CONNECTION_FAILED", "DISCONNECTED"):
            messagebox.showerror("Error", payload.get("reason", "Could not connect."))
            self.show_main_menu()
            return
        if event_type != "WELCOME":
            messagebox.showerror("Error", f"Unexpected response: {event_type}")
            self.show_main_menu()
            return

        from game.state import GameState
        state = GameState.from_dict(payload["game_state"])
        uid = self._user_config["uuid"]

        # ── Persist host prefabs locally (merge, never delete old entries) ────
        host_uuid    = payload.get("host_uuid", "")
        host_prefabs = payload.get("host_prefabs") or []
        if host_uuid and host_prefabs:
            try:
                from app.config import merge_host_prefabs
                merge_host_prefabs(host_uuid, host_prefabs)
            except Exception:
                pass   # non-fatal: game still works without local prefab cache

        connected_uuids = set(payload.get("connected_uuids", []))

        from screens.game import GameScreen
        self._swap_screen(lambda p: GameScreen(
            p, state, self._client, None, self._ui_queue,
            local_uuid=uid, is_dm=False,
            host_uuid=host_uuid,
            connected_uuids=connected_uuids,
        ))

    def _join_failed(self, reason: str) -> None:
        messagebox.showerror("Error", reason)
        self.show_main_menu()

    # ── utilities ─────────────────────────────────────────────────────────────

    def _swap_screen(self, factory) -> None:
        if self._current_screen:
            self._current_screen.destroy()
        screen = factory(self)
        screen.pack(fill=tk.BOTH, expand=True)
        self._current_screen = screen

    def _cleanup_session(self) -> None:
        if self._client:
            try:
                self._client.send({"type": "DISCONNECT"})
                self._client.stop()
            except Exception:
                pass
            self._client = None
        if self._server:
            try:
                self._server.stop()
            except Exception:
                pass
            self._server = None
        if self._ui_queue:
            try:
                while not self._ui_queue.empty():
                    self._ui_queue.get_nowait()
            except Exception:
                pass
            self._ui_queue = None

    def on_quit(self) -> None:
        self._cleanup_session()
        self.destroy()
