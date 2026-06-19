import tkinter as tk
import re
from datetime import datetime
from typing import Callable, Optional, List, TYPE_CHECKING

from app.constants import PALETTE, FONTS, TAG_COLOURS

if TYPE_CHECKING:
    from game.state import GameState


class ChatWidget(tk.Frame):
    WIDTH = 300
    HEIGHT = 180

    def __init__(self, parent, on_send: Callable, is_dm: bool = False,
                 game_state=None, **kwargs):
        super().__init__(parent, bg="#000000", width=self.WIDTH, height=self.HEIGHT, **kwargs)
        self.on_send = on_send
        self.is_dm = is_dm
        self.game_state = game_state
        self._auto_scroll = True
        self._npc_impersonate: Optional[str] = None
        self._tab_candidates: List[str] = []
        self._tab_idx = 0

        self.pack_propagate(False)

        self._text = tk.Text(
            self, bg="#000000", fg=PALETTE["fg"],
            font=FONTS["chat"], state=tk.DISABLED,
            relief=tk.FLAT, bd=0, wrap=tk.WORD,
            highlightthickness=0,
            width=1, height=1,
        )
        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL,
                                 command=self._text.yview,
                                 bg=PALETTE["card"], troughcolor="#000000",
                                 bd=0, width=6)
        self._text.configure(yscrollcommand=self._on_scroll_change)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        for tag, color in TAG_COLOURS.items():
            self._text.tag_configure(tag, foreground=color)
        self._text.tag_configure("timestamp", foreground=PALETTE["muted"])

        self._prefix_lbl = tk.Label(self, bg="#000000", fg=PALETTE["muted"],
                                    font=FONTS["small"], text="", anchor="w")
        self._prefix_lbl.pack(side=tk.TOP, fill=tk.X, padx=4)

        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(
            self, textvariable=self._entry_var,
            bg=PALETTE["card2"], fg=PALETTE["fg"],
            insertbackground=PALETTE["fg"],
            relief=tk.FLAT, font=FONTS["chat"],
            bd=0, highlightthickness=1,
            highlightbackground=PALETTE["border"],
            highlightcolor=PALETTE["accent"],
        )
        self._entry.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=2)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<Escape>", self._on_escape)
        self._entry.bind("<Tab>", self._on_tab)
        self._text.bind("<ButtonPress-1>", self._on_text_click)

        scrollbar.configure(command=self._text.yview)

    def focus_input(self) -> None:
        self._entry.focus_set()

    def blur_input(self) -> None:
        self.focus_set()

    def set_npc_impersonate(self, npc_name: Optional[str]) -> None:
        self._npc_impersonate = npc_name
        if npc_name:
            self._prefix_lbl.config(text=f"[As {npc_name}]")
        else:
            self._prefix_lbl.config(text="")

    def add_message(self, msg: dict) -> None:
        msg_type = msg.get("msg_type", "normal")
        alias = msg.get("sender_alias", "")
        content = msg.get("content", "")
        tag = msg_type if msg_type in TAG_COLOURS else "normal"

        if msg_type == "whisper":
            formatted = content
        elif msg_type in ("system", "error"):
            formatted = content
        elif msg_type == "yell":
            formatted = f"{alias} yells: {content}"
        else:
            formatted = f"{alias}: {content}"

        self._text.config(state=tk.NORMAL)
        self._text.insert(tk.END, formatted + "\n", tag)
        self._text.config(state=tk.DISABLED)
        if self._auto_scroll:
            self._text.see(tk.END)

    def add_local(self, text: str, tag: str = "system") -> None:
        self._text.config(state=tk.NORMAL)
        self._text.insert(tk.END, text + "\n", tag)
        self._text.config(state=tk.DISABLED)
        if self._auto_scroll:
            self._text.see(tk.END)

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
            elif rest.startswith("-y "):
                pass
            else:
                parts = rest.split(" ", 1)
                if len(parts) == 2:
                    npc_name, msg_content = parts
                    self.on_send(msg_content, "normal", npc_name.strip())
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
        if text in ("/", ""):
            pass
        prefix = text.lstrip("/")
        if not self._tab_candidates:
            self._tab_candidates = [c for c in commands if c.lstrip("/").startswith(prefix)]
            self._tab_idx = 0
        if self._tab_candidates:
            self._entry_var.set(self._tab_candidates[self._tab_idx])
            self._tab_idx = (self._tab_idx + 1) % len(self._tab_candidates)
            self._entry.icursor(tk.END)
        return "break"

    def _on_text_click(self, event=None) -> None:
        self._auto_scroll = False

    def _on_scroll_change(self, first, last) -> None:
        if float(last) >= 0.999:
            self._auto_scroll = True

    def _show_help(self) -> None:
        lines = [
            "/y <msg>                — Yell (all, burnt orange)",
            "/w <alias> <msg>        — Whisper (private)",
        ]
        if self.is_dm:
            lines += [
                "/as <NPC> <msg>         — Speak as NPC [DM only]",
                "/as <NPC> -y <msg>      — Yell as NPC [DM only]",
                "/as <NPC> -w <a> <msg>  — Whisper as NPC [DM only]",
            ]
        lines.append("/help                   — This help")
        for line in lines:
            self.add_local(line, "system")
