"""
StairModifyDialog  — DM panel to edit a Stairs object's Name, Direction, LinkedStair.
StairPromptDialog  — Centered player confirmation: "Proceed up/down the stairs?"
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Tuple, TYPE_CHECKING

from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr, styled_entry

if TYPE_CHECKING:
    from game.objects import Stairs
    from game.state import GameState


class StairModifyDialog(Panel):
    def __init__(self, parent, stair: "Stairs", cell: Tuple[int, int],
                 game_state: "GameState", on_save: Callable):
        super().__init__(parent, padx=0, pady=0)
        self._stair = stair
        self._cell = cell
        self._state = game_state
        self._on_save = on_save
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=16, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Modify Stairs", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        form = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=12)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)

        def _lbl(text, row, anchor="e"):
            tk.Label(form, text=text, bg=PALETTE["card"],
                     fg="#ffffff", font=FONTS["form_label"],
                     anchor=anchor, width=14).grid(
                row=row, column=0, sticky="e", pady=5, padx=4)

        row = 0

        # Name
        _lbl("Name", row)
        self._name_var = tk.StringVar(value=self._stair.Name)
        styled_entry(form, textvariable=self._name_var, width=22).grid(
            row=row, column=1, sticky="w", pady=5, padx=4)
        row += 1

        # Direction
        _lbl("Direction", row)
        self._dir_var = tk.StringVar(value=self._stair.Direction)
        ttk.Combobox(form, textvariable=self._dir_var,
                     values=["Up", "Down"],
                     state="readonly", width=10).grid(
            row=row, column=1, sticky="w", pady=5, padx=4)
        row += 1

        # LinkedStair dropdown — all OTHER stairs by Name:(x,y)
        _lbl("Linked Stair", row)
        all_stairs = []
        for (gx, gy), cell in self._state.grid.items():
            from game.objects import Stairs as _S
            if isinstance(cell.occupant, _S) and cell.occupant.id != self._stair.id:
                all_stairs.append((cell.occupant, (gx, gy)))

        stair_labels = ["(none)"] + [
            f"{s.Name}:({gx},{gy})" for s, (gx, gy) in all_stairs
        ]
        self._stair_uuid_map = {
            f"{s.Name}:({gx},{gy})": s.id
            for s, (gx, gy) in all_stairs
        }
        # Pre-select current linked stair if any
        current_label = "(none)"
        if self._stair.LinkedStair:
            for s, (gx, gy) in all_stairs:
                if s.id == self._stair.LinkedStair:
                    current_label = f"{s.Name}:({gx},{gy})"
                    break
        self._linked_var = tk.StringVar(value=current_label)
        ttk.Combobox(form, textvariable=self._linked_var,
                     values=stair_labels,
                     state="readonly", width=20).grid(
            row=row, column=1, sticky="w", pady=5, padx=4)
        row += 1

        # Read-only Coords
        _lbl("Coords", row)
        tk.Label(form, text=f"{self._cell}", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["body"]).grid(
            row=row, column=1, sticky="w", pady=5, padx=4)
        row += 1

        # Read-only UUID
        _lbl("UUID", row)
        tk.Label(form, text=self._stair.id, bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=("Consolas", 8)).grid(
            row=row, column=1, sticky="w", pady=5, padx=4)
        row += 1

        hr(self).pack(fill=tk.X)
        btn_row = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=10)
        btn_row.pack(fill=tk.X)
        flat_btn(btn_row, "Save", self._save, style="normal").pack(
            side=tk.LEFT, padx=(0, 8))
        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT)

    def _save(self) -> None:
        linked_label = self._linked_var.get()
        linked_uuid = self._stair_uuid_map.get(linked_label, "") \
            if linked_label != "(none)" else ""
        obj_d = {
            "type": "Stairs",
            "id": self._stair.id,
            "Name": self._name_var.get().strip() or "Stairs",
            "Direction": self._dir_var.get(),
            "LinkedStair": linked_uuid,
        }
        self.close()
        self._on_save(obj_d)


class StairPromptDialog(Panel):
    """
    Top-centre confirmation for stair traversal.
    No dark backdrop — background stays fully visible.
    """

    def __init__(self, parent, stair: "Stairs",
                 on_yes: Callable, on_no: Callable):
        super().__init__(parent, padx=32, pady=24, placement="top")
        self._on_yes = on_yes
        self._on_no  = on_no

        direction = stair.Direction.lower()
        tk.Label(self, text=f"Proceed {direction} the stairs?",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["heading"]).pack(pady=(0, 20))

        btn_row = tk.Frame(self, bg=PALETTE["card"])
        btn_row.pack()
        flat_btn(btn_row, "Yes", self._yes, style="normal").pack(
            side=tk.LEFT, padx=(0, 10), ipadx=8)
        flat_btn(btn_row, "No", self._no, style="ghost").pack(
            side=tk.LEFT, ipadx=8)

    def _yes(self) -> None:
        self.close()
        self._on_yes()

    def _no(self) -> None:
        self.close()
        self._on_no()
