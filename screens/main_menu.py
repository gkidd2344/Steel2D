import io
import base64
import tkinter as tk
from typing import Callable

from app.constants import PALETTE, FONTS
from ui.widgets import flat_btn, hr

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class MainMenuScreen(tk.Frame):
    def __init__(self, parent, user_config: dict,
                 on_profile: Callable,
                 on_host: Callable,
                 on_join: Callable,
                 on_quit: Callable,
                 on_dm_tool: Callable = None,
                 on_character: Callable = None,
                 **kwargs):
        super().__init__(parent, bg=PALETTE["bg"], **kwargs)
        self._user_config = user_config
        self._on_profile = on_profile
        self._on_host = on_host
        self._on_join = on_join
        self._on_quit = on_quit
        self._on_dm_tool = on_dm_tool
        self._on_character = on_character
        self._avatar_img = None
        self._build()

    def _has_profile(self) -> bool:
        return bool(self._user_config.get("alias", "").strip())

    def _build(self) -> None:
        # ── Gear icon (top-right, fixed position) ─────────────────────────────
        gear_btn = tk.Button(self, text="⚙", bg=PALETTE["bg"],
                             fg=PALETTE["fg"], relief=tk.FLAT,
                             font=FONTS["icon"], cursor="hand2",
                             command=self._open_banlist,
                             activebackground=PALETTE["bg"])
        gear_btn.place(relx=1.0, x=-14, y=10, anchor="ne")

        # ── Centred card ──────────────────────────────────────────────────────
        card = tk.Frame(self, bg=PALETTE["card"], padx=36, pady=28)
        card.place(relx=0.5, rely=0.5, anchor="center")

        # Title
        tk.Label(card, text="STEEL2D", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["title"]).pack()
        tk.Label(card, text="v0.19  ·  multiplayer tabletop lobby",
                 bg=PALETTE["card"], fg=PALETTE["muted"],
                 font=FONTS["small"]).pack(pady=(0, 6))
        hr(card).pack(fill=tk.X, pady=8)

        # Avatar + signed-in row
        avatar_row = tk.Frame(card, bg=PALETTE["card"])
        avatar_row.pack(pady=(0, 6))
        self._avatar_label = tk.Label(avatar_row, bg=PALETTE["card"])
        self._avatar_label.pack(side=tk.LEFT, padx=(0, 10))
        self._load_avatar()
        alias = self._user_config.get("alias") or "(no alias)"
        tk.Label(avatar_row, text=f"Signed in as  {alias}",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["body"]).pack(side=tk.LEFT)

        hr(card).pack(fill=tk.X, pady=8)

        # ── Profile button row (label changes, hint appears if no alias) ──────
        has_profile = self._has_profile()
        profile_label = "Edit Profile" if has_profile else "Create Profile"

        profile_row = tk.Frame(card, bg=PALETTE["card"])
        profile_row.pack(fill=tk.X, pady=(0, 4))

        profile_row.grid_columnconfigure(0, weight=1)
        profile_row.grid_columnconfigure(1, weight=1)

        flat_btn(
            profile_row,
            f"👤  {profile_label}",
            self._on_profile,
            style="ghost"
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), ipady=4)

        if self._on_character:
            from app.config import get_character_path
            has_char = get_character_path().exists()
            char_label = "Edit Character" if has_char else "Create Character"
            flat_btn(
                profile_row,
                f"⚔  {char_label}",
                self._on_character,
                style="ghost"
            ).grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=4)

        # ── Hint row ──────────────────────────────────────────────────────────
        if not has_profile:
            tk.Label(
                card,
                text="← Set up your player to continue",
                bg=PALETTE["card"],
                fg=PALETTE["warning"],
                font=FONTS["small"]
            ).pack(pady=(0, 8))

        # ── DM Workshop ───────────────────────────────────────────────────────
        if self._on_dm_tool:
            flat_btn(card, "🛠  DM Workshop", self._on_dm_tool,
                     style="spectre").pack(fill=tk.X, pady=(0, 4), ipady=4)

        # ── Host / Join inline ────────────────────────────────────────────────
        hj_row = tk.Frame(card, bg=PALETTE["card"])
        hj_row.pack(fill=tk.X, pady=4)

        hj_row.grid_columnconfigure(0, weight=1)
        hj_row.grid_columnconfigure(1, weight=1)

        state = tk.NORMAL if has_profile else tk.DISABLED

        host_btn = flat_btn(
            hj_row,
            "🖥  Host",
            self._on_host,
            style="normal"
        )
        host_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4), ipady=4)

        join_btn = flat_btn(
            hj_row,
            "🌐  Join",
            self._on_join,
            style="normal"  # use normal instead of ghost
        )
        join_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=4)

        host_btn.config(state=state)
        join_btn.config(state=state)

        # ── Quit ──────────────────────────────────────────────────────────────
        hr(card).pack(fill=tk.X, pady=8)
        flat_btn(card, "✕   Quit", self._on_quit, style="danger").pack(
            fill=tk.X, ipady=3)

    def _load_avatar(self) -> None:
        b64 = self._user_config.get("avatar_b64")
        if not b64 or not HAS_PIL:
            self._avatar_label.config(text="?", fg=PALETTE["muted"],
                                      bg=PALETTE["card2"],
                                      font=FONTS["body"], width=4, height=2)
            return
        try:
            data = base64.b64decode(b64)
            img = Image.open(io.BytesIO(data)).resize((40, 40), Image.LANCZOS)
            self._avatar_img = ImageTk.PhotoImage(img)
            self._avatar_label.config(image=self._avatar_img,
                                      width=40, height=40, text="")
        except Exception:
            pass

    def _open_banlist(self) -> None:
        from dialogs.banlist_dialog import BanlistDialog
        BanlistDialog(self)
