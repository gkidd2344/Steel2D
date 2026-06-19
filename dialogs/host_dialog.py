import tkinter as tk
from typing import Callable
from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn


class HostDialog(Panel):
    def __init__(self, parent, on_new_game: Callable, on_load_game: Callable):
        super().__init__(parent, padx=32, pady=24)
        self._build(on_new_game, on_load_game)

    def _build(self, on_new, on_load) -> None:
        tk.Label(self, text="Host a Game", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 16))

        flat_btn(self, "🆕  New Game",
                 lambda: (self.close(), on_new()),
                 style="normal").pack(fill=tk.X, pady=4, ipady=4)
        flat_btn(self, "📂  Load Game",
                 lambda: (self.close(), on_load()),
                 style="ghost").pack(fill=tk.X, pady=4, ipady=4)
        flat_btn(self, "Cancel", self.close,
                 style="muted").pack(fill=tk.X, pady=(10, 0), ipady=4)
