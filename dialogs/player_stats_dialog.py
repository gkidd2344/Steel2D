import tkinter as tk
from typing import Callable, Optional, TYPE_CHECKING
from app.constants import PALETTE, FONTS
from app.config import STAT_KEYS
from game.stats import effective_stat, clamp_stats, max_individual, max_total
from ui.panel import Panel
from ui.widgets import flat_btn, hr

if TYPE_CHECKING:
    from game.objects import PlayerObject


class PlayerStatsDialog(Panel):
    def __init__(self, parent, player: "PlayerObject",
                 on_save_stats: Optional[Callable] = None,
                 read_only: bool = False):
        super().__init__(parent, padx=0, pady=0)
        self._player = player
        self._on_save = on_save_stats
        self._read_only = read_only
        self._editing = False
        self._spin_vars: dict = {}
        self._total_var = tk.StringVar()
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"{self._player.Name} — Level {self._player.Level}",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)

        info = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=6)
        info.pack(fill=tk.X)
        tk.Label(info, text=f"HP: {self._player.CurrentHP} / {self._player.MaximumHP}",
                 bg=PALETTE["card"], fg=PALETTE["fg"], font=FONTS["body"]).pack(anchor="w")
        tk.Label(info, text=f"Size: {self._player.Size}",
                 bg=PALETTE["card"], fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(anchor="w")
        hr(self).pack(fill=tk.X)

        self._stat_frame = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=8)
        self._stat_frame.pack(fill=tk.X)
        self._render_stats()

        hr(self).pack(fill=tk.X)
        tk.Label(self, textvariable=self._total_var, bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"],
                 padx=20).pack(anchor="w", pady=4)

        btn_row = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=10)
        btn_row.pack(fill=tk.X)
        if not self._read_only and self._on_save:
            self._edit_btn = flat_btn(btn_row, "Edit Stats",
                                      self._toggle_edit, style="ghost")
            self._edit_btn.pack(side=tk.LEFT, padx=(0, 6))
            self._confirm_btn = flat_btn(btn_row, "Confirm",
                                         self._confirm, style="normal")
            self._confirm_btn.pack(side=tk.LEFT, padx=(0, 6))
            self._confirm_btn.config(state=tk.DISABLED)
            flat_btn(btn_row, "Reset", self._reset,
                     style="muted").pack(side=tk.LEFT, padx=(0, 6))
        flat_btn(btn_row, "Close", self.close, style="ghost").pack(side=tk.LEFT)
        self._update_total()

    def _render_stats(self) -> None:
        for w in self._stat_frame.winfo_children():
            w.destroy()
        for k in STAT_KEYS:
            row = tk.Frame(self._stat_frame, bg=PALETTE["card"])
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=k, bg=PALETTE["card"], fg=PALETTE["fg"],
                     font=FONTS["body"], width=6, anchor="w").pack(side=tk.LEFT)
            base = self._player.Stats.get(k, 0)
            bonus = sum(item.Stats.get(k, 0) for item in self._player.Equipment.values()
                        if item.Stats)
            if self._editing:
                var = self._spin_vars.get(k, tk.IntVar(value=base))
                self._spin_vars[k] = var
                sp = tk.Spinbox(row, from_=0, to=max_individual(self._player.Level),
                                textvariable=var, width=5,
                                bg=PALETTE["card2"], fg=PALETTE["fg"],
                                insertbackground=PALETTE["fg"],
                                relief=tk.FLAT, bd=0,
                                command=self._update_total)
                var.trace_add("write", lambda *_: self._update_total())
                sp.pack(side=tk.LEFT, padx=4)
            else:
                tk.Label(row, text=str(base), bg=PALETTE["card"],
                         fg=PALETTE["fg"], font=FONTS["body"],
                         width=4).pack(side=tk.LEFT)
            if bonus:
                tk.Label(row, text=f"(+{bonus} equip) = {base + bonus}",
                         bg=PALETTE["card"], fg=PALETTE["accent"],
                         font=FONTS["small"]).pack(side=tk.LEFT, padx=4)

    def _update_total(self, *_) -> None:
        if self._editing:
            total = sum(self._spin_vars[k].get() for k in STAT_KEYS if k in self._spin_vars)
        else:
            total = sum(self._player.Stats.get(k, 0) for k in STAT_KEYS)
        mt = max_total(self._player.Level)
        self._total_var.set(f"Base total: {total} / {mt} (max at Level {self._player.Level})")

    def _toggle_edit(self) -> None:
        self._editing = not self._editing
        if self._editing:
            for k in STAT_KEYS:
                self._spin_vars[k] = tk.IntVar(value=self._player.Stats.get(k, 0))
            self._edit_btn.config(text="Cancel Edit")
            self._confirm_btn.config(state=tk.NORMAL)
        else:
            self._spin_vars.clear()
            self._edit_btn.config(text="Edit Stats")
            self._confirm_btn.config(state=tk.DISABLED)
        self._render_stats()
        self._update_total()

    def _confirm(self) -> None:
        new_stats = {k: self._spin_vars[k].get() for k in STAT_KEYS}
        clamped = clamp_stats(new_stats, self._player.Level)
        if self._on_save:
            self._on_save(clamped)
        self.close()

    def _reset(self) -> None:
        for k in STAT_KEYS:
            if k in self._spin_vars:
                self._spin_vars[k].set(self._player.Stats.get(k, 0))
        self._update_total()


class PlayerStatsTooltip(Panel):
    def __init__(self, parent, player: "PlayerObject"):
        super().__init__(parent, padx=24, pady=18)
        self._build(player)

    def _build(self, player) -> None:
        tk.Label(self, text=player.Name, bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 4))
        tk.Label(self, text=f"HP: {player.CurrentHP} / {player.MaximumHP}",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["body"]).pack(anchor="w")
        hr(self).pack(fill=tk.X, pady=8)
        for k in STAT_KEYS:
            eff = effective_stat(player, k)
            tk.Label(self, text=f"{k}: {eff}", bg=PALETTE["card"],
                     fg=PALETTE["fg"], font=FONTS["body"]).pack(anchor="w")
        hr(self).pack(fill=tk.X, pady=8)
        flat_btn(self, "Close", self.close, style="ghost").pack()
