import colorsys
import tkinter as tk
from typing import Callable, Optional, List, TYPE_CHECKING

from app.constants import PALETTE, FONTS

if TYPE_CHECKING:
    from game.state import GameState

CHAT_BG      = "#141420"   # dark, semi-transparent looking (65% black feel)
ENTRY_BG_OFF = "#141420"   # matches chat when unfocused
ENTRY_BG_ON  = "#ffffff"   # white when focused
ENTRY_FG_ON  = "#000000"

DM_COLOR    = "#ff9500"    # orange for [DM] tag
YELL_COLOR  = "#f07060"    # salmon for /y
WHISPER_COLOR = "#9090cc"

TAG_COLOURS = {
    "normal":         "#e6e6f0",
    "yell":           YELL_COLOR,
    "whisper_out":    WHISPER_COLOR,
    "whisper_in":     WHISPER_COLOR,
    "system":         "#888888",
    "error":          "#cc3333",
    "dm":             DM_COLOR,
    "combat_damage":  "#ff4444",
    "combat_heal":    "#44ff88",
    "combat_fizzle":  "#888888",
}


def _boosted_color(hex_color: str) -> str:
    """Return a higher-contrast version of `hex_color` for chat display."""
    try:
        r = int(hex_color[1:3], 16) / 255
        g = int(hex_color[3:5], 16) / 255
        b = int(hex_color[5:7], 16) / 255
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        r2, g2, b2 = colorsys.hsv_to_rgb(h, min(s + 0.1, 1.0), 1.0)
        return "#{:02x}{:02x}{:02x}".format(
            int(r2 * 255), int(g2 * 255), int(b2 * 255))
    except Exception:
        return hex_color


class ChatWidget(tk.Frame):
    WIDTH = 380
    HEIGHT = 180

    def __init__(self, parent, on_send: Callable, is_dm: bool = False,
                 game_state=None, host_uuid: str = "", **kwargs):
        super().__init__(parent, bg=CHAT_BG,
                         width=self.WIDTH, height=self.HEIGHT, **kwargs)
        self.on_send = on_send
        self.is_dm = is_dm
        self.game_state = game_state
        self.host_uuid = host_uuid
        self._auto_scroll = True
        self._npc_impersonate: Optional[str] = None
        self._tab_idx = 0

        self.pack_propagate(False)
        self._build()

    def _build(self) -> None:
        # ── scrollable text area ──────────────────────────────────────────────
        text_outer = tk.Frame(self, bg=CHAT_BG)
        text_outer.pack(fill=tk.BOTH, expand=True)

        self._text = tk.Text(
            text_outer, bg=CHAT_BG, fg=TAG_COLOURS["normal"],
            font=FONTS["chat"], state=tk.DISABLED,
            relief=tk.FLAT, bd=0, wrap=tk.WORD,
            highlightthickness=0, padx=6, pady=4,
            width=1, height=1,
        )
        self._text.pack(fill=tk.BOTH, expand=True)

        # Scrollbar overlaid inside the text area (right edge, 6px wide, dark)
        vsb = tk.Scrollbar(text_outer, orient=tk.VERTICAL,
                           command=self._text.yview,
                           bg="#2a2a2a", troughcolor="#1a1a1a",
                           bd=0, relief=tk.FLAT, width=2,
                           activebackground="#3a3a3a")
        vsb.place(relx=1.0, rely=0.0, relheight=1.0, width=2, anchor="ne")
        self._text.configure(yscrollcommand=self._on_scroll_change)
        # Store vsb ref so we can call it in _on_scroll_change
        self._vsb = vsb
        self._text.configure(yscrollcommand=lambda f, l: (
            vsb.set(f, l), self._on_scroll_change(f, l)))

        # Configure tags
        for tag, color in TAG_COLOURS.items():
            self._text.tag_configure(tag, foreground=color)

        # ── NPC impersonation prefix ──────────────────────────────────────────
        self._prefix_lbl = tk.Label(self, bg=CHAT_BG, fg=PALETTE["muted"],
                                    font=FONTS["small"], text="", anchor="w")
        self._prefix_lbl.pack(fill=tk.X, padx=4)

        # ── Text entry ────────────────────────────────────────────────────────
        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(
            self, textvariable=self._entry_var,
            bg=ENTRY_BG_OFF, fg=PALETTE["fg_dim"],
            insertbackground=PALETTE["fg"],
            relief=tk.FLAT, font=FONTS["chat"],
            bd=0, highlightthickness=1,
            highlightbackground=PALETTE["border"],
            highlightcolor=PALETTE["accent"],
        )
        self._entry.pack(fill=tk.X, padx=2, pady=2)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<Escape>", self._on_escape)
        self._entry.bind("<Tab>", self._on_tab)
        self._entry.bind("<FocusIn>", self._on_entry_focus)
        self._entry.bind("<FocusOut>", self._on_entry_blur)
        self._text.bind("<ButtonPress-1>", self._on_text_click)

    # ── public API ────────────────────────────────────────────────────────────

    def focus_input(self) -> None:
        self._entry.focus_set()

    def blur_input(self) -> None:
        self.focus_set()

    def set_npc_impersonate(self, npc_name: Optional[str]) -> None:
        self._npc_impersonate = npc_name
        self._prefix_lbl.config(
            text=f"[As {npc_name}]" if npc_name else "")

    def add_message(self, msg: dict) -> None:
        msg_type = msg.get("msg_type", "normal")
        sender_uuid = msg.get("sender_uuid", "")
        alias = msg.get("sender_alias", "")
        content = msg.get("content", "")

        # Determine sender display
        is_npc = sender_uuid.startswith("NPC:")
        is_dm_sender = (sender_uuid == self.host_uuid) and not is_npc
        if is_dm_sender:
            display_name = f"[DM] {alias}"
            name_tag = "dm"
        else:
            display_name = alias
            name_tag = "normal"
            if self.game_state and not is_npc:
                raw = self.game_state.assigned_colors.get(sender_uuid)
                if raw:
                    bright = _boosted_color(raw)
                    tag_id = f"_player_{sender_uuid}"
                    self._text.tag_configure(tag_id, foreground=bright)
                    name_tag = tag_id

        self._text.config(state=tk.NORMAL)

        if msg_type in ("system", "error", "combat_damage", "combat_heal", "combat_fizzle"):
            tag = msg_type if msg_type in TAG_COLOURS else "system"
            self._text.insert(tk.END, content + "\n", tag)
        elif msg_type == "whisper":
            self._text.insert(tk.END, content + "\n", "whisper_in")
        elif msg_type == "yell":
            self._text.insert(tk.END, display_name, name_tag)
            self._text.insert(tk.END, f" yells: {content}\n", "yell")
        else:
            self._text.insert(tk.END, f"{display_name}: ", name_tag)
            self._text.insert(tk.END, f"{content}\n", "normal")

        self._text.config(state=tk.DISABLED)
        if self._auto_scroll:
            self._text.see(tk.END)

    def add_local(self, text: str, tag: str = "system") -> None:
        self._text.config(state=tk.NORMAL)
        self._text.insert(tk.END, text + "\n", tag)
        self._text.config(state=tk.DISABLED)
        if self._auto_scroll:
            self._text.see(tk.END)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_entry_focus(self, event=None) -> None:
        self._entry.config(bg=ENTRY_BG_ON, fg=ENTRY_FG_ON,
                           insertbackground=ENTRY_FG_ON)

    def _on_entry_blur(self, event=None) -> None:
        self._entry.config(bg=ENTRY_BG_OFF, fg=PALETTE["fg_dim"],
                           insertbackground=PALETTE["fg"])

    def _on_enter(self, event=None) -> str:
        text = self._entry_var.get().strip()
        if not text:
            self.blur_input()
            return "break"

        if text == "/help":
            self._show_help()
            self._entry_var.set("")
            return "break"

        if self._npc_impersonate:
            if text.startswith("/y "):
                self.on_send(text[3:], "yell", self._npc_impersonate)
            elif text.startswith("/w "):
                parts = text[3:].split(" ", 1)
                if len(parts) == 2:
                    self.on_send(parts[1], "whisper", self._npc_impersonate,
                                 recipient_alias=parts[0])
            else:
                self.on_send(text, "normal", self._npc_impersonate)
            self._entry_var.set("")
            return "break"

        if text.startswith("/as ") and self.is_dm:
            rest = text[4:]
            if " -w " in rest:
                npc_name, rest2 = rest.split(" -w ", 1)
                parts = rest2.split(" ", 1)
                if len(parts) == 2:
                    self.on_send(parts[1], "whisper", npc_name.strip(),
                                 recipient_alias=parts[0])
            else:
                parts = rest.split(" ", 1)
                if len(parts) == 2:
                    self.on_send(parts[1], "normal", parts[0].strip())
                elif len(parts) == 1:
                    self.on_send("", "normal", parts[0].strip())
            self._entry_var.set("")
            return "break"

        if text.startswith("/y "):
            self.on_send(text[3:], "yell")
        elif text.startswith("/w "):
            parts = text[3:].split(" ", 1)
            if len(parts) == 2:
                self.on_send(parts[1], "whisper", recipient_alias=parts[0])
        else:
            self.on_send(text, "normal")

        self._entry_var.set("")
        return "break"

    def _on_escape(self, event=None) -> str:
        self.blur_input()
        return "break"

    def _on_tab(self, event=None) -> str:
        text = self._entry_var.get()
        if not text.startswith("/"):
            return "break"
        commands = ["/y ", "/w ", "/as ", "/help"]
        prefix = text.lstrip("/")
        candidates = [c for c in commands if c.lstrip("/").startswith(prefix)]
        if candidates:
            self._entry_var.set(candidates[self._tab_idx % len(candidates)])
            self._tab_idx = (self._tab_idx + 1) % len(candidates)
            self._entry.icursor(tk.END)
        return "break"

    def _on_text_click(self, event=None) -> None:
        self._auto_scroll = False

    def _on_scroll_change(self, first, last) -> None:
        if float(last) >= 0.999:
            self._auto_scroll = True

    def _show_help(self) -> None:
        lines = ["/y <msg>  — Yell", "/w <alias> <msg>  — Whisper"]
        if self.is_dm:
            lines += ["/as <NPC> <msg>  — Speak as NPC [DM only]",
                      "/as <NPC> -w <a> <msg>  — Whisper as NPC [DM only]"]
        lines.append("/help  — This help")
        for line in lines:
            self.add_local(line, "system")
