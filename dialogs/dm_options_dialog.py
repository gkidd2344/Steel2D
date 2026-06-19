import tkinter as tk
from typing import Callable
from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn
from dialogs.confirm_dialog import ask_confirm


class DmOptionsDialog(Panel):
    def __init__(self, parent, player_name: str,
                 on_kick: Callable, on_ban: Callable):
        super().__init__(parent, padx=28, pady=20)
        self._player_name = player_name
        self._on_kick = on_kick
        self._on_ban = on_ban
        self._build()

    def _build(self) -> None:
        tk.Label(self, text=self._player_name, bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 12))

        flat_btn(self, "Disconnect (1 min temp ban)",
                 self._kick, style="warning").pack(fill=tk.X, pady=3)
        flat_btn(self, "Ban (permanent)",
                 self._ban, style="danger").pack(fill=tk.X, pady=3)
        flat_btn(self, "Cancel",
                 self.close, style="ghost").pack(fill=tk.X, pady=(10, 0))

    def _kick(self) -> None:
        if ask_confirm(self, "Disconnect",
                       f"Temporarily disconnect {self._player_name}?"):
            self.close()
            self._on_kick()

    def _ban(self) -> None:
        if ask_confirm(self, "Ban Player",
                       f"Permanently ban {self._player_name}?"):
            self.close()
            self._on_ban()
