import tkinter as tk
from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr


class ObjectTooltip(Panel):
    def __init__(self, parent, obj):
        super().__init__(parent, padx=24, pady=18)
        self._build(obj)

    def _build(self, obj) -> None:
        from game.objects import NPC, Item, Door
        name = getattr(obj, "Name", "Object") or "Object"
        tk.Label(self, text=name, bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 4))
        hr(self).pack(fill=tk.X, pady=(0, 8))

        rows = []
        if isinstance(obj, NPC):
            rows = [
                ("Description", obj.Description),
                ("Size", obj.Size),
                ("Level", str(obj.Level)),
                ("Hostile", "Yes" if obj.Hostile else "No"),
                ("HP", f"{obj.CurrentHP} / {obj.MaximumHP}"),
                *[(k, str(obj.Stats.get(k, 0)))
                  for k in ("Str", "Dex", "Con", "Int", "Wis", "Cha")],
            ]
        elif isinstance(obj, Item):
            rows = [
                ("Description", obj.Description),
                ("Level", str(obj.Level)),
                ("Quantity", str(obj.Quantity)),
                ("Value", f"{obj.Value}g"),
                ("Consumable", "Yes" if obj.Consumable else "No"),
            ]
        elif isinstance(obj, Door):
            rows = [
                ("State", "Open" if obj.Open else "Closed"),
                ("Locked", "Yes" if obj.Locked else "No"),
                ("Broken", "Yes" if obj.Broken else "No"),
            ]

        for label, value in rows:
            row = tk.Frame(self, bg=PALETTE["card"])
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label + ":", bg=PALETTE["card"],
                     fg=PALETTE["muted"], font=FONTS["small"],
                     width=13, anchor="e").pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=PALETTE["card"],
                     fg=PALETTE["fg"], font=FONTS["body"],
                     wraplength=240, anchor="w").pack(side=tk.LEFT, padx=6)

        hr(self).pack(fill=tk.X, pady=(8, 0))
        flat_btn(self, "Close", self.close, style="ghost").pack(pady=(8, 0))
