import tkinter as tk
from typing import Callable, Optional, TYPE_CHECKING
from app.constants import PALETTE, FONTS
from ui.widgets import flat_btn

if TYPE_CHECKING:
    from game.state import GameState, CombatState


class TurnOrderPanel(tk.Frame):
    WIDTH = 165

    def __init__(self, parent, state: "GameState", local_uuid: str,
                 is_dm: bool, on_end_turn: Callable, **kwargs):
        super().__init__(parent, bg=PALETTE["card"],
                         width=self.WIDTH, **kwargs)
        self.pack_propagate(False)
        self._state = state
        self._local_uuid = local_uuid
        self._is_dm = is_dm
        self._on_end_turn = on_end_turn
        self._build()

    def _build(self) -> None:
        for w in self.winfo_children():
            w.destroy()
        combat = self._state.combat
        if not combat or not combat.active:
            return

        hdr = tk.Frame(self, bg=PALETTE["card"], padx=6, pady=6)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"⚔ COMBAT  Rd {combat.round_number}",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["sub"]).pack(anchor="w")

        tk.Frame(self, bg=PALETTE["border"], height=1).pack(fill=tk.X)

        list_frame = tk.Frame(self, bg=PALETTE["card"])
        list_frame.pack(fill=tk.BOTH, expand=True)

        for i, turn in enumerate(combat.turn_queue):
            is_active = (i == combat.current_index)
            row_bg = PALETTE["accent"] if is_active else PALETTE["card"]
            row = tk.Frame(list_frame, bg=row_bg, pady=3, padx=6)
            row.pack(fill=tk.X)

            if turn.combatant_type == "player":
                p = self._state.players.get(turn.id)
                color = p.color if p else "#ffffff"
            else:
                color = "#cc2222"

            tk.Frame(row, bg=color, width=12, height=12).pack(side=tk.LEFT, padx=(0, 4))

            marker = "▶ " if is_active else "  "
            name = (turn.name or "?")[:10]
            tk.Label(row, text=marker + name, bg=row_bg,
                     fg=PALETTE["fg"], font=FONTS["small"],
                     width=12, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=str(turn.initiative), bg=row_bg,
                     fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(side=tk.RIGHT)

        tk.Frame(self, bg=PALETTE["border"], height=1).pack(fill=tk.X)

        current_turn = None
        if combat.turn_queue and combat.current_index < len(combat.turn_queue):
            current_turn = combat.turn_queue[combat.current_index]

        show_btn = False
        if current_turn:
            if current_turn.combatant_type == "player" and current_turn.id == self._local_uuid:
                show_btn = True
            elif current_turn.combatant_type == "npc" and self._is_dm:
                show_btn = True

        if show_btn:
            flat_btn(self, "End Turn", self._on_end_turn,
                     style="normal").pack(fill=tk.X, padx=6, pady=6)

    def refresh(self) -> None:
        self._build()
