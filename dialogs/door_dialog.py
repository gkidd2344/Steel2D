import tkinter as tk
from typing import Callable
from app.constants import PALETTE, FONTS
from game.objects import Door
from ui.panel import Panel
from ui.widgets import flat_btn


class DoorInteractionDialog(Panel):
    def __init__(self, parent, door: Door, on_action: Callable):
        super().__init__(parent, padx=28, pady=20)
        self._door = door
        self._on_action = on_action
        self._build()

    def _build(self) -> None:
        tk.Label(self, text="Door", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 4))

        is_open = self._door.Open
        broken = self._door.Broken
        parts = ["Open" if is_open else "Closed"]
        if self._door.Locked and not is_open:
            parts.append("Locked")
        if broken:
            parts.append("Broken")
        tk.Label(self, text=" · ".join(parts), bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["body"]).pack(anchor="w", pady=(0, 14))

        btn_row = tk.Frame(self, bg=PALETTE["card"])
        btn_row.pack(anchor="center")

        label = "Close" if is_open else "Open"
        action = "close" if is_open else "open"
        btn = flat_btn(btn_row, label, lambda: self._do_action(action), style="normal")
        btn.pack(side=tk.LEFT, padx=(0, 8))
        if broken:
            btn.config(state=tk.DISABLED)

        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT)

    def _do_action(self, action: str) -> None:
        self._on_action(action)
        self.close()
