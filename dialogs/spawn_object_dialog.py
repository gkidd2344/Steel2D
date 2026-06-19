from __future__ import annotations
import uuid as _uuid
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, TYPE_CHECKING
from app.constants import PALETTE, FONTS, EQUIPMENT_SLOTS
from app.config import STAT_KEYS, HEALTH_SIZE_LOOKUP, SCALAR_WEIGHT_LOOKUP
from game.stats import calc_max_hp, max_individual, max_total
from ui.panel import Panel
from ui.widgets import flat_btn, hr, styled_entry, styled_check

if TYPE_CHECKING:
    from game.state import GameSettings


class SpawnObjectDialog(Panel):
    def __init__(self, parent, on_spawn: Callable,
                 settings: Optional["GameSettings"] = None,
                 existing=None, title: str = "Spawn Object"):
        super().__init__(parent, padx=0, pady=0)
        self._wm_title = title
        self._on_spawn = on_spawn
        self._settings = settings
        self._existing = existing
        self._type_var = tk.StringVar(value="NPC")
        self._err_var = tk.StringVar()
        self._action_rows: list = []
        self._build()
        if existing:
            self._pre_fill(existing)

    # ── outer chrome ──────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=self._wm_title, bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        # Type selector
        type_row = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=6)
        type_row.pack(fill=tk.X)
        for t in ("NPC", "Item", "Door"):
            tk.Radiobutton(
                type_row, text=t, variable=self._type_var, value=t,
                bg=PALETTE["card"], fg=PALETTE["fg"],
                selectcolor=PALETTE["accent"],
                activebackground=PALETTE["card"],
                command=self._on_type_change,
            ).pack(side=tk.LEFT, padx=10)

        if self._existing:
            from game.objects import NPC, Item, Door
            if isinstance(self._existing, NPC):
                self._type_var.set("NPC")
            elif isinstance(self._existing, Item):
                self._type_var.set("Item")
            elif isinstance(self._existing, Door):
                self._type_var.set("Door")

        hr(self).pack(fill=tk.X)

        # Scrollable body
        self._scroll_canvas = tk.Canvas(
            self, bg=PALETTE["card"], highlightthickness=0,
            width=440, height=440)
        vsb = tk.Scrollbar(self, orient="vertical",
                           command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._scroll_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._body_frame = tk.Frame(self._scroll_canvas, bg=PALETTE["card"])
        self._canvas_window = self._scroll_canvas.create_window(
            (0, 0), window=self._body_frame, anchor="nw")
        self._body_frame.bind("<Configure>", self._on_body_configure)
        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Footer
        hr(self).pack(fill=tk.X)
        tk.Label(self, textvariable=self._err_var, bg=PALETTE["card"],
                 fg=PALETTE["danger"], font=FONTS["small"]).pack()
        btn_row = tk.Frame(self, bg=PALETTE["card"], pady=8)
        btn_row.pack()
        flat_btn(btn_row, "Spawn" if not self._existing else "Apply",
                 self._do_spawn, style="normal").pack(side=tk.LEFT, padx=6)
        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT, padx=6)

        self._render_body()

    def _on_body_configure(self, event=None) -> None:
        self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all"))

    def _on_canvas_configure(self, event=None) -> None:
        self._scroll_canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event) -> None:
        self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_type_change(self) -> None:
        self.after_idle(self._render_body)

    def _render_body(self) -> None:
        for w in self._body_frame.winfo_children():
            w.destroy()
        self._action_rows = []
        t = self._type_var.get()
        if t == "NPC":
            self._build_npc_form()
        elif t == "Item":
            self._build_item_form()
        else:
            self._build_door_form()
        self._body_frame.update_idletasks()
        self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all"))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _lbl_entry(self, parent, label: str, var: tk.Variable, row: int,
                   width: int = 24) -> None:
        tk.Label(parent, text=label, bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], anchor="e", width=15).grid(
            row=row, column=0, sticky="e", pady=3, padx=4)
        styled_entry(parent, textvariable=var, width=width).grid(
            row=row, column=1, sticky="w", pady=3, padx=4)

    def _spinbox(self, parent, var, mn, mx, row=None, col=1, w=8, command=None) -> tk.Spinbox:
        sp = tk.Spinbox(
            parent, from_=mn, to=mx, textvariable=var, width=w,
            bg=PALETTE["card2"], fg=PALETTE["fg"],
            insertbackground=PALETTE["fg"], relief=tk.FLAT, bd=0,
            command=command,
        )
        if row is not None:
            sp.grid(row=row, column=col, sticky="w", pady=3, padx=4)
        return sp

    def _warn_label(self, parent) -> tk.StringVar:
        var = tk.StringVar()
        tk.Label(parent, textvariable=var, bg=PALETTE["card"],
                 fg="#ff8c00", font=FONTS["small"],
                 wraplength=380, justify="left").grid(
            row=999, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 0))
        return var

    # ── NPC form ──────────────────────────────────────────────────────────────

    def _build_npc_form(self) -> None:
        f = tk.Frame(self._body_frame, bg=PALETTE["card"], padx=8, pady=4)
        f.pack(fill=tk.X)
        f.columnconfigure(1, weight=1)

        self._npc_name = tk.StringVar()
        self._npc_level = tk.IntVar(value=1)
        self._npc_size = tk.StringVar(value="Medium")
        self._npc_hostile = tk.BooleanVar(value=True)
        self._npc_maxhp = tk.IntVar(value=10)
        self._npc_curhp = tk.IntVar(value=10)
        # Default stats 10 per spec
        self._npc_stats = {k: tk.IntVar(value=10) for k in STAT_KEYS}
        self._npc_has_actions = tk.BooleanVar(value=True)  # default on
        self._npc_stat_warn = None  # assigned after form built

        row = 0
        self._lbl_entry(f, "Name *", self._npc_name, row); row += 1

        tk.Label(f, text="Description", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"],
                 anchor="e", width=15).grid(row=row, column=0, sticky="ne",
                                            pady=3, padx=4)
        self._npc_desc = tk.Text(
            f, height=3, width=26, bg=PALETTE["card2"],
            fg=PALETTE["fg"], insertbackground=PALETTE["fg"],
            relief=tk.FLAT, bd=0)
        self._npc_desc.grid(row=row, column=1, sticky="w", pady=3, padx=4)
        row += 1

        tk.Label(f, text="Level", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], anchor="e", width=15).grid(
            row=row, column=0, sticky="e", pady=3, padx=4)
        self._spinbox(f, self._npc_level, 1, 99, row, command=self._recalc_npc_hp)
        self._npc_level.trace_add("write", lambda *_: self._recalc_npc_hp())
        row += 1

        tk.Label(f, text="Size", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], anchor="e", width=15).grid(
            row=row, column=0, sticky="e", pady=3, padx=4)
        cb = ttk.Combobox(f, textvariable=self._npc_size,
                          values=list(HEALTH_SIZE_LOOKUP.keys()),
                          state="readonly", width=12)
        cb.grid(row=row, column=1, sticky="w", pady=3, padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self._recalc_npc_hp())
        row += 1

        tk.Label(f, text="Hostile", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], anchor="e", width=15).grid(
            row=row, column=0, sticky="e", pady=3, padx=4)
        tk.Checkbutton(f, variable=self._npc_hostile,
                       bg=PALETTE["card"], selectcolor=PALETTE["accent"],
                       fg=PALETTE["fg"], activebackground=PALETTE["card"]).grid(
            row=row, column=1, sticky="w")
        row += 1

        tk.Label(f, text="Maximum HP", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], anchor="e", width=15).grid(
            row=row, column=0, sticky="e", pady=3, padx=4)
        self._spinbox(f, self._npc_maxhp, 1, 99999, row)
        row += 1

        tk.Label(f, text="Current HP", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], anchor="e", width=15).grid(
            row=row, column=0, sticky="e", pady=3, padx=4)
        self._spinbox(f, self._npc_curhp, 1, 99999, row)
        row += 1

        # Stats section
        tk.Label(f, text="Stats", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"]).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(8, 2), padx=4)
        row += 1
        for k in STAT_KEYS:
            tk.Label(f, text=k, bg=PALETTE["card"], fg=PALETTE["fg"],
                     font=FONTS["small"], anchor="e", width=15).grid(
                row=row, column=0, sticky="e", pady=2, padx=4)
            sp = self._spinbox(f, self._npc_stats[k], 0, 9999, row, w=6,
                               command=self._validate_npc_stats)
            self._npc_stats[k].trace_add("write", lambda *_: self._validate_npc_stats())
            row += 1

        # Stat validation warning
        self._npc_stat_warn = tk.StringVar()
        tk.Label(f, textvariable=self._npc_stat_warn, bg=PALETTE["card"],
                 fg="#ff8c00", font=FONTS["small"],
                 wraplength=380, justify="left").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        row += 1

        # Actions (checked by default, pre-seeded with Unarmed Attack)
        sc = styled_check(f, "Has Actions", self._npc_has_actions,
                          command=lambda: self.after_idle(self._render_body),
                          bg=PALETTE["card"])
        sc.grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        row += 1

        if self._npc_has_actions.get():
            self._action_frame = tk.Frame(f, bg=PALETTE["card"])
            self._action_frame.grid(row=row, column=0, columnspan=2,
                                    sticky="ew", padx=4)
            row += 1
            add_row = tk.Frame(f, bg=PALETTE["card"])
            add_row.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
            flat_btn(add_row, "+ Add Action",
                     self._add_action_row, style="ghost").pack(side=tk.LEFT)
            row += 1
            # Pre-seed Unarmed Attack if new NPC
            if not self._existing:
                self._add_action_row(preset={
                    "name": "Unarmed Attack",
                    "desc": "A basic unarmed strike using Str.",
                    "range": 1, "damage": 0, "hits": 1,
                })

        self._recalc_npc_hp()
        self._validate_npc_stats()

    def _recalc_npc_hp(self) -> None:
        if not hasattr(self, "_npc_level"):
            return
        try:
            level = self._npc_level.get()
            size = self._npc_size.get()
            con = self._npc_stats.get("Con", tk.IntVar()).get()
            mult = self._settings.hp_base_multiplier if self._settings else 6.0
            hp = calc_max_hp(size, level, con, mult)
            self._npc_maxhp.set(hp)
            self._npc_curhp.set(hp)
        except Exception:
            pass
        self._validate_npc_stats()

    def _validate_npc_stats(self) -> None:
        if not hasattr(self, "_npc_stat_warn") or not self._npc_stat_warn:
            return
        try:
            level = self._npc_level.get()
            mi = max_individual(level)
            mt = max_total(level)
            total = sum(v.get() for v in self._npc_stats.values())
            warn = ""
            for k, v in self._npc_stats.items():
                if v.get() > mi:
                    warn = f"Stat exceeds maximum of {mi} for lv.{level}"
                    break
            if not warn and total > mt:
                warn = f"Stat total exceeds maximum of {mt} for lv.{level}"
            self._npc_stat_warn.set(warn)
        except Exception:
            pass

    # ── Item form ─────────────────────────────────────────────────────────────

    def _build_item_form(self) -> None:
        f = tk.Frame(self._body_frame, bg=PALETTE["card"], padx=8, pady=4)
        f.pack(fill=tk.X)
        f.columnconfigure(1, weight=1)

        self._item_name = tk.StringVar()
        self._item_level = tk.IntVar(value=1)
        self._item_consumable = tk.BooleanVar(value=False)
        self._item_quantity = tk.IntVar(value=1)
        self._item_value = tk.IntVar(value=0)
        self._item_slot = tk.StringVar(value="(none)")
        self._item_has_stats = tk.BooleanVar(value=False)
        self._item_stats = {k: tk.IntVar(value=0) for k in STAT_KEYS}
        self._item_has_scalars = tk.BooleanVar(value=False)
        self._item_scalar_vars: dict = {}
        self._item_has_actions = tk.BooleanVar(value=False)

        row = 0
        self._lbl_entry(f, "Name *", self._item_name, row); row += 1

        tk.Label(f, text="Description", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"],
                 anchor="e", width=15).grid(row=row, column=0, sticky="ne",
                                            pady=3, padx=4)
        self._item_desc = tk.Text(
            f, height=3, width=26, bg=PALETTE["card2"], fg=PALETTE["fg"],
            insertbackground=PALETTE["fg"], relief=tk.FLAT, bd=0)
        self._item_desc.grid(row=row, column=1, sticky="w", pady=3, padx=4)
        row += 1

        for label, var, mn, mx in [
            ("Level", self._item_level, 1, 99),
            ("Quantity", self._item_quantity, 1, 9999),
            ("Value (g)", self._item_value, 0, 999999),
        ]:
            tk.Label(f, text=label, bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                     font=FONTS["small"], anchor="e", width=15).grid(
                row=row, column=0, sticky="e", pady=3, padx=4)
            self._spinbox(f, var, mn, mx, row)
            row += 1

        tk.Label(f, text="Consumable", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], anchor="e", width=15).grid(
            row=row, column=0, sticky="e", pady=3, padx=4)
        tk.Checkbutton(
            f, variable=self._item_consumable,
            bg=PALETTE["card"], selectcolor=PALETTE["accent"], fg=PALETTE["fg"], 
            activebackground=PALETTE["card"]).grid(row=row, column=1, sticky="w")
        row += 1

        tk.Label(f, text="Equipment Slot", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], anchor="e", width=15).grid(
            row=row, column=0, sticky="e", pady=3, padx=4)
        slot_opts = ["(none)"] + [f"{k}: {v}" for k, v in EQUIPMENT_SLOTS.items()]
        ttk.Combobox(f, textvariable=self._item_slot,
                     values=slot_opts, state="readonly", width=16).grid(
            row=row, column=1, sticky="w", pady=3, padx=4)
        row += 1

        # Has Stats
        sc_stats = styled_check(f, "Has Stats", self._item_has_stats,
                                command=lambda: self.after_idle(self._render_body),
                                bg=PALETTE["card"])
        sc_stats.grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        row += 1
        if self._item_has_stats.get():
            self._item_stat_warn = tk.StringVar()
            for k in STAT_KEYS:
                tk.Label(f, text=k, bg=PALETTE["card"], fg=PALETTE["fg"],
                         font=FONTS["small"], anchor="e", width=15).grid(
                    row=row, column=0, sticky="e", pady=2, padx=4)
                self._spinbox(f, self._item_stats[k], -999, 999, row, w=6,
                              command=self._validate_item_stats)
                self._item_stats[k].trace_add(
                    "write", lambda *_: self._validate_item_stats())
                row += 1
            tk.Label(f, textvariable=self._item_stat_warn, bg=PALETTE["card"],
                     fg="#ff8c00", font=FONTS["small"],
                     wraplength=380, justify="left").grid(
                row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
            row += 1
        else:
            self._item_stat_warn = tk.StringVar()

        # Has Scalars
        sc_scalars = styled_check(f, "Has Scalars", self._item_has_scalars,
                                  command=lambda: self.after_idle(self._render_body),
                                  bg=PALETTE["card"])
        sc_scalars.grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        row += 1
        if self._item_has_scalars.get():
            for k in STAT_KEYS:
                sr = tk.Frame(f, bg=PALETTE["card"])
                sr.grid(row=row, column=0, columnspan=2, sticky="w")
                row += 1
                tk.Label(sr, text=k, bg=PALETTE["card"], fg=PALETTE["fg"],
                         font=FONTS["small"], width=8).pack(side=tk.LEFT)
                v = tk.StringVar(value="None")
                self._item_scalar_vars[k] = v
                ttk.Combobox(sr, textvariable=v,
                             values=["None"] + list(SCALAR_WEIGHT_LOOKUP.keys()),
                             state="readonly", width=6).pack(side=tk.LEFT, padx=4)

        # Has Actions
        sc_actions = styled_check(f, "Has Actions", self._item_has_actions,
                                  command=lambda: self.after_idle(self._render_body),
                                  bg=PALETTE["card"])
        sc_actions.grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        row += 1
        if self._item_has_actions.get():
            self._action_frame = tk.Frame(f, bg=PALETTE["card"])
            self._action_frame.grid(row=row, column=0, columnspan=2,
                                    sticky="ew", padx=4)
            row += 1
            add_row = tk.Frame(f, bg=PALETTE["card"])
            add_row.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
            flat_btn(add_row, "+ Add Action",
                     self._add_action_row, style="ghost").pack(side=tk.LEFT)
            row += 1

    def _validate_item_stats(self) -> None:
        if not hasattr(self, "_item_stat_warn"):
            return
        if not self._item_has_stats.get():
            return
        try:
            level = self._item_level.get() if hasattr(self, "_item_level") else 1
            mi = max_individual(level)
            mt = max_total(level)
            total = sum(v.get() for v in self._item_stats.values())
            warn = ""
            for k, v in self._item_stats.items():
                if abs(v.get()) > mi:
                    warn = f"Stat exceeds maximum of {mi} for lv.{level}"
                    break
            if not warn and total > mt:
                warn = f"Stat total exceeds maximum of {mt} for lv.{level}"
            self._item_stat_warn.set(warn)
        except Exception:
            pass

    # ── Door form ─────────────────────────────────────────────────────────────

    def _build_door_form(self) -> None:
        f = tk.Frame(self._body_frame, bg=PALETTE["card"], padx=8, pady=4)
        f.pack(fill=tk.X)
        self._door_open = tk.BooleanVar(value=False)
        self._door_broken = tk.BooleanVar(value=False)
        self._door_locked = tk.BooleanVar(value=False)
        for text, var in [("Open", self._door_open),
                           ("Broken", self._door_broken),
                           ("Locked", self._door_locked)]:
            r = tk.Frame(f, bg=PALETTE["card"])
            r.pack(fill=tk.X, pady=3)
            tk.Label(r, text=text, bg=PALETTE["card"], fg=PALETTE["fg"],
                     font=FONTS["body"], width=12, anchor="e").pack(
                side=tk.LEFT, padx=4)
            tk.Checkbutton(r, variable=var, bg=PALETTE["card"],
                           selectcolor=PALETTE["accent"], fg=PALETTE["fg"], 
                           activebackground=PALETTE["card"]).pack(side=tk.LEFT)

    # ── Action row ────────────────────────────────────────────────────────────

    def _add_action_row(self, preset: dict = None) -> None:
        if not hasattr(self, "_action_frame"):
            return
        preset = preset or {}
        row_data = {
            "name":           tk.StringVar(value=preset.get("name", "")),
            "desc":           tk.StringVar(value=preset.get("desc", "")),
            "range":          tk.IntVar(value=preset.get("range", 1)),
            "damage":         tk.IntVar(value=preset.get("damage", 0)),
            "hits":           tk.IntVar(value=preset.get("hits", 1)),
            "has_casts":      tk.BooleanVar(value=bool(preset.get("casts"))),
            "casts_max":      tk.IntVar(value=(preset.get("casts") or {}).get("max_per_rest", 3)),
            "casts_rem":      tk.IntVar(value=(preset.get("casts") or {}).get("remaining", 3)),
        }
        self._action_rows.append(row_data)

        outer = tk.Frame(self._action_frame, bg=PALETTE["card2"],
                         pady=4, padx=4, relief=tk.FLAT)
        outer.pack(fill=tk.X, pady=2, padx=2)

        line1 = tk.Frame(outer, bg=PALETTE["card2"])
        line1.pack(fill=tk.X)
        for label, var, w in [
            ("Name", row_data["name"], 13),
            ("Desc", row_data["desc"], 13),
        ]:
            tk.Label(line1, text=label, bg=PALETTE["card2"],
                     fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(side=tk.LEFT)
            styled_entry(line1, textvariable=var, width=w).pack(side=tk.LEFT, padx=2)

        def _remove(r=row_data, f=outer):
            self._action_rows.remove(r)
            f.destroy()
        tk.Button(line1, text="×", command=_remove,
                  bg=PALETTE["danger"], fg="#fff",
                  relief=tk.FLAT, font=FONTS["small"],
                  cursor="hand2").pack(side=tk.RIGHT, padx=2)

        line2 = tk.Frame(outer, bg=PALETTE["card2"])
        line2.pack(fill=tk.X, pady=(2, 0))
        for label, var, mn, mx in [
            ("Range", row_data["range"], 0, 99),
            ("Dmg",   row_data["damage"], -99999, 99999),
            ("Hits",  row_data["hits"], 1, 99),
        ]:
            tk.Label(line2, text=label, bg=PALETTE["card2"],
                     fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(side=tk.LEFT, padx=(4, 1))
            tk.Spinbox(line2, from_=mn, to=mx, textvariable=var, width=5,
                       bg=PALETTE["card2"], fg=PALETTE["fg"],
                       insertbackground=PALETTE["fg"],
                       relief=tk.FLAT, bd=0).pack(side=tk.LEFT, padx=1)

        # Casts row
        casts_frame = tk.Frame(outer, bg=PALETTE["card2"])
        casts_frame.pack(fill=tk.X, pady=(2, 0))

        casts_sub = tk.Frame(outer, bg=PALETTE["card2"])

        def _toggle_casts():
            if row_data["has_casts"].get():
                casts_sub.pack(fill=tk.X, pady=(2, 0))
            else:
                casts_sub.pack_forget()
            self.after_idle(self._update_scroll)

        sc = styled_check(casts_frame, "Limited Uses (Casts)", row_data["has_casts"],
                          command=_toggle_casts, bg=PALETTE["card2"])
        sc.pack(side=tk.LEFT, padx=4)

        for label, var in [("Max/rest", row_data["casts_max"]),
                            ("Remaining", row_data["casts_rem"])]:
            tk.Label(casts_sub, text=label, bg=PALETTE["card2"],
                     fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(side=tk.LEFT, padx=(6, 1))
            tk.Spinbox(casts_sub, from_=0, to=99, textvariable=var, width=4,
                       bg=PALETTE["card2"], fg=PALETTE["fg"],
                       insertbackground=PALETTE["fg"],
                       relief=tk.FLAT, bd=0).pack(side=tk.LEFT, padx=1)

        if row_data["has_casts"].get():
            casts_sub.pack(fill=tk.X, pady=(2, 0))

        self._update_scroll()

    def _update_scroll(self) -> None:
        self._body_frame.update_idletasks()
        self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all"))

    # ── pre-fill existing object ───────────────────────────────────────────────

    def _pre_fill(self, obj) -> None:
        from game.objects import NPC, Item, Door
        if isinstance(obj, NPC):
            self._npc_name.set(obj.Name)
            if self._npc_desc:
                self._npc_desc.insert("1.0", obj.Description)
            self._npc_level.set(obj.Level)
            self._npc_size.set(obj.Size)
            self._npc_hostile.set(obj.Hostile)
            self._npc_maxhp.set(obj.MaximumHP)
            self._npc_curhp.set(obj.CurrentHP)
            for k in STAT_KEYS:
                if k in self._npc_stats:
                    self._npc_stats[k].set(obj.Stats.get(k, 0))
            if obj.Actions:
                self._npc_has_actions.set(True)
                self.after_idle(self._render_body)
                self.after(50, lambda: self._fill_actions(obj.Actions))
        elif isinstance(obj, Item):
            self._item_name.set(obj.Name)
            if self._item_desc:
                self._item_desc.insert("1.0", obj.Description)
            self._item_level.set(obj.Level)
            self._item_consumable.set(obj.Consumable)
            self._item_quantity.set(obj.Quantity)
            self._item_value.set(obj.Value)
            if obj.EquipmentSlot:
                slot_name = EQUIPMENT_SLOTS.get(obj.EquipmentSlot, "")
                self._item_slot.set(f"{obj.EquipmentSlot}: {slot_name}")
            if obj.Stats:
                self._item_has_stats.set(True)
                self.after_idle(self._render_body)
        elif isinstance(obj, Door):
            self._door_open.set(obj.Open)
            self._door_broken.set(obj.Broken)
            self._door_locked.set(obj.Locked)

    def _fill_actions(self, actions: dict) -> None:
        for name, action in actions.items():
            casts = action.get("Casts")
            self._add_action_row(preset={
                "name": name,
                "desc": action.get("Description", ""),
                "range": action.get("Range", 1),
                "damage": action.get("BaseDamage", 0),
                "hits": action.get("Hits", 1),
                "casts": casts,
            })

    # ── result collection ─────────────────────────────────────────────────────

    def _collect_actions(self) -> Optional[dict]:
        if not self._action_rows:
            return None
        result = {}
        for row in self._action_rows:
            name = row["name"].get().strip()
            if not name:
                continue
            action = {
                "Description": row["desc"].get(),
                "Range": row["range"].get(),
                "BaseDamage": row["damage"].get(),
                "Hits": row["hits"].get(),
            }
            if row["has_casts"].get():
                action["Casts"] = {
                    "max_per_rest": row["casts_max"].get(),
                    "remaining": row["casts_rem"].get(),
                }
            result[name] = action
        return result or None

    def _build_result_dict(self) -> Optional[dict]:
        t = self._type_var.get()
        if t == "NPC":
            name = self._npc_name.get().strip()
            if not name:
                self._err_var.set("Name is required.")
                return None
            actions = self._collect_actions()
            return {
                "type": "NPC", "id": str(_uuid.uuid4()),
                "Name": name,
                "Description": self._npc_desc.get("1.0", "end-1c") if self._npc_desc else "",
                "Level": self._npc_level.get(),
                "Size": self._npc_size.get(),
                "Hostile": self._npc_hostile.get(),
                "MaximumHP": self._npc_maxhp.get(),
                "CurrentHP": self._npc_curhp.get(),
                "Stats": {k: v.get() for k, v in self._npc_stats.items()},
                "Actions": actions,
            }
        elif t == "Item":
            name = self._item_name.get().strip()
            if not name:
                self._err_var.set("Name is required.")
                return None
            slot_str = self._item_slot.get()
            slot = None
            if slot_str and slot_str != "(none)":
                try:
                    slot = int(slot_str.split(":")[0])
                except Exception:
                    pass
            stats = None
            if self._item_has_stats.get():
                stats = {k: v.get() for k, v in self._item_stats.items()}
            scalars = None
            if self._item_has_scalars.get() and self._item_scalar_vars:
                scalars = {k: v.get() for k, v in self._item_scalar_vars.items()
                           if v.get() != "None"} or None
            actions = self._collect_actions()
            return {
                "type": "Item", "id": str(_uuid.uuid4()),
                "Name": name,
                "Description": self._item_desc.get("1.0", "end-1c") if self._item_desc else "",
                "Level": self._item_level.get(),
                "Consumable": self._item_consumable.get(),
                "Quantity": self._item_quantity.get(),
                "Value": self._item_value.get(),
                "Stats": stats,
                "Scalars": scalars,
                "Actions": actions,
                "EquipmentSlot": slot,
            }
        else:
            return {
                "type": "Door", "id": str(_uuid.uuid4()),
                "Open": self._door_open.get(),
                "Broken": self._door_broken.get(),
                "Locked": self._door_locked.get(),
            }

    def _do_spawn(self) -> None:
        self._err_var.set("")
        obj_dict = self._build_result_dict()
        if obj_dict is None:
            return
        self.close()
        self._on_spawn(obj_dict)
