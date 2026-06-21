import tkinter as tk
from typing import Callable
from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr, styled_entry


class HostDialog(Panel):
    def __init__(self, parent, on_new_game: Callable, on_load_game: Callable):
        super().__init__(parent, padx=32, pady=24)
        self._on_new = on_new_game
        self._on_load = on_load_game
        self._build()

    def _build(self) -> None:
        tk.Label(self, text="Host a Game", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 14))

        flat_btn(self, "🆕  New Game",
                 lambda: (self.close(), self._on_new(self._pwd_var.get())),
                 style="normal").pack(fill=tk.X, pady=4, ipady=4)
        flat_btn(self, "📂  Load Game",
                 lambda: (self.close(), self._on_load(self._pwd_var.get())),
                 style="ghost").pack(fill=tk.X, pady=4, ipady=4)

        hr(self).pack(fill=tk.X, pady=(12, 8))

        pwd_row = tk.Frame(self, bg=PALETTE["card"])
        pwd_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(pwd_row, text="Session Password (optional)",
                 bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"]).pack(anchor="w", pady=(0, 4))
        self._pwd_var = tk.StringVar()
        styled_entry(pwd_row, textvariable=self._pwd_var, width=26,
                     show="•").pack(fill=tk.X)

        flat_btn(self, "Cancel", self.close,
                 style="muted").pack(fill=tk.X, ipady=4)
