import tkinter as tk
from typing import Dict, TYPE_CHECKING
from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn

if TYPE_CHECKING:
    from game.state import GameState


class PlayerListOverlay(Panel):
    def __init__(self, parent, state: "GameState", host_uuid: str,
                 local_uuid: str, latencies: Dict[str, float]):
        super().__init__(parent, padx=0, pady=0)
        self._build(state, host_uuid, local_uuid, latencies)

    def _build(self, state, host_uuid, local_uuid, latencies) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=16, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Connected Players ({len(state.players)})",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["sub"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)

        tk.Frame(self, bg=PALETTE["border"], height=1).pack(fill=tk.X)

        for uid, player in state.players.items():
            row = tk.Frame(self, bg=PALETTE["card2"] if uid == local_uuid else PALETTE["card"],
                           pady=5, padx=14)
            row.pack(fill=tk.X)

            tk.Frame(row, bg=player.color, width=14, height=14).pack(side=tk.LEFT, padx=(0, 8))

            name = player.Name or uid[:8]
            tk.Label(row, text=name, bg=row.cget("bg"),
                     fg=PALETTE["fg"], font=FONTS["body"]).pack(side=tk.LEFT)

            if uid == host_uuid:
                tag, tag_color = "HOST", PALETTE["accent"]
            else:
                ms = latencies.get(uid, 0)
                tag, tag_color = f"{int(ms)}ms", PALETTE["fg_dim"]

            tk.Label(row, text=tag, bg=row.cget("bg"),
                     fg=tag_color, font=FONTS["small"]).pack(side=tk.RIGHT)
