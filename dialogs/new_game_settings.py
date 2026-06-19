import tkinter as tk
from typing import Callable
from app.constants import PALETTE, FONTS
from app.config import load_game_config
from game.state import GameSettings
from ui.panel import Panel
from ui.widgets import flat_btn, styled_entry, hr


class NewGameSettingsDialog(Panel):
    def __init__(self, parent, on_start: Callable):
        super().__init__(parent, padx=28, pady=20)
        self._on_start = on_start
        self._build()

    def _build(self) -> None:
        cfg = load_game_config()
        tk.Label(self, text="New Game Settings", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 12))

        form = tk.Frame(self, bg=PALETTE["card"])
        form.pack(fill=tk.X)

        tk.Label(form, text="Game Name", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"]).grid(
            row=0, column=0, sticky="w", pady=5)
        self._name_var = tk.StringVar(value="Untitled")
        styled_entry(form, textvariable=self._name_var, width=22).grid(
            row=0, column=1, pady=5, padx=(10, 0), sticky="w")

        fields = [
            ("HP Base Multiplier",  "hp_base_multiplier",      cfg.get("hp_base_multiplier", 6.0)),
            ("Enemy Damage Mult.",  "enemy_damage_multiplier", cfg.get("enemy_damage_multiplier", 1.0)),
            ("LOS Max Distance",    "los_max_distance",        cfg.get("los_max_distance", 20)),
        ]
        self._vars = {}
        for i, (label, key, default) in enumerate(fields, start=1):
            tk.Label(form, text=label, bg=PALETTE["card"],
                     fg=PALETTE["fg_dim"], font=FONTS["small"]).grid(
                row=i, column=0, sticky="w", pady=5)
            var = tk.StringVar(value=str(default))
            self._vars[key] = var
            styled_entry(form, textvariable=var, width=10).grid(
                row=i, column=1, pady=5, padx=(10, 0), sticky="w")

        self._err_var = tk.StringVar()
        tk.Label(self, textvariable=self._err_var, bg=PALETTE["card"],
                 fg=PALETTE["danger"], font=FONTS["small"]).pack(pady=(6, 0))

        hr(self).pack(fill=tk.X, pady=(10, 8))
        btn_row = tk.Frame(self, bg=PALETTE["card"])
        btn_row.pack(anchor="e")
        flat_btn(btn_row, "Start", self._do_start, style="normal").pack(side=tk.LEFT, padx=(0, 8))
        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT)

    def _do_start(self) -> None:
        name = self._name_var.get().strip() or "Untitled"
        try:
            settings = GameSettings(
                hp_base_multiplier=float(self._vars["hp_base_multiplier"].get()),
                enemy_damage_multiplier=float(self._vars["enemy_damage_multiplier"].get()),
                los_max_distance=int(self._vars["los_max_distance"].get()),
            )
        except ValueError:
            self._err_var.set("Invalid numeric value.")
            return
        self.close()
        self._on_start(name, settings)
