from __future__ import annotations
import uuid as _uuid
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Tuple, TYPE_CHECKING
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
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=self._wm_title, bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        type_row = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=6)
        type_row.pack(fill=tk.X)
        for t in ("NPC", "Item"):
            tk.Radiobutton(
                type_row, text=t, variable=self._type_var, value=t,
                bg=PALETTE["card"], fg=PALETTE["fg"],
                font=FONTS["form_label"],
                selectcolor=PALETTE["accent"],
                activebackground=PALETTE["card"],
                command=self._on_type_change,
            ).pack(side=tk.LEFT, padx=10)

        if self._existing:
            from game.objects import NPC, Item
            if isinstance(self._existing, NPC):
                self._type_var.set("NPC")
            elif isinstance(self._existing, Item):
                self._type_var.set("Item")

        hr(self).pack(fill=tk.X)

        self._scroll_canvas = tk.Canvas(
            self, bg=PALETTE["card"], highlightthickness=0,
            width=460, height=460)
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
        if self._type_var.get() == "NPC":
            self._build_npc_form()
        else:
            self._build_item_form()
        self._update_scroll()

    def _update_scroll(self) -> None:
        self._body_frame.update_idletasks()
        self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all"))

    # ── collapsible section ───────────────────────────────────────────────────

    def _make_section(self, parent: tk.Frame, title: str,
                      expanded: bool = False) -> Tuple[tk.Frame, tk.Frame]:
        outer = tk.Frame(parent, bg=PALETTE["card"])
        outer.pack(fill=tk.X, pady=(4, 0))
        state = [expanded]
        hdr = tk.Button(
            outer,
            text=("  ▼  " if expanded else "  ▶  ") + title,
            bg=PALETTE["card2"], fg="#ffffff",
            font=FONTS["form_label"], anchor="w",
            relief=tk.FLAT, cursor="hand2", padx=6,
            activebackground=PALETTE["border"],
            activeforeground="#ffffff",
        )
        hdr.pack(fill=tk.X)
        content = tk.Frame(outer, bg=PALETTE["card"], padx=12, pady=4)
        if expanded:
            content.pack(fill=tk.X)

        def _toggle():
            state[0] = not state[0]
            hdr.config(text=("  ▼  " if state[0] else "  ▶  ") + title)
            if state[0]:
                content.pack(fill=tk.X)
            else:
                content.pack_forget()
            self._update_scroll()

        hdr.config(command=_toggle)
        return outer, content

    # ── shared helpers ────────────────────────────────────────────────────────

    def _lbl(self, parent, text, anchor="e", width=14) -> tk.Label:
        return tk.Label(parent, text=text, bg=PALETTE["card"],
                        fg="#ffffff", font=FONTS["form_label"],
                        anchor=anchor, width=width)

    def _spinbox(self, parent, var, mn, mx,
                 row=None, col=1, w=8, command=None) -> tk.Spinbox:
        sp = tk.Spinbox(
            parent, from_=mn, to=mx, textvariable=var, width=w,
            bg=PALETTE["card2"], fg="#ffffff",
            insertbackground="#ffffff",
            relief=tk.FLAT, bd=0,
            command=command,
            buttonbackground=PALETTE["muted"],
        )
        if row is not None:
            sp.grid(row=row, column=col, sticky="w", pady=3, padx=4)
        return sp

    def _field_row(self, parent, label_text, widget_factory):
        """Pack a label+widget pair as one horizontal row."""
        row = tk.Frame(parent, bg=PALETTE["card"])
        row.pack(fill=tk.X, pady=2)
        self._lbl(row, label_text).pack(side=tk.LEFT, padx=(4, 4))
        widget_factory(row)
        return row

    # ── NPC form ──────────────────────────────────────────────────────────────

    def _build_npc_form(self) -> None:
        self._npc_name = tk.StringVar()
        self._npc_level = tk.IntVar(value=1)
        self._npc_size = tk.StringVar(value="Medium")
        self._npc_hostile = tk.BooleanVar(value=True)
        self._npc_maxhp = tk.IntVar(value=10)
        self._npc_curhp = tk.IntVar(value=10)
        self._npc_stats = {k: tk.IntVar(value=10) for k in STAT_KEYS}
        self._npc_turns_allowed = tk.IntVar(value=1)
        self._npc_stat_warn = tk.StringVar()

        # ── General ──────────────────────────────────────────────────────────
        _, gen = self._make_section(self._body_frame, "General", expanded=False)

        self._field_row(gen, "Name *",
                        lambda p: styled_entry(p, textvariable=self._npc_name,
                                               width=24).pack(side=tk.LEFT, fill=tk.X, expand=True))

        # Description
        desc_row = tk.Frame(gen, bg=PALETTE["card"])
        desc_row.pack(fill=tk.X, pady=2)
        self._lbl(desc_row, "Description", anchor="nw").pack(side=tk.LEFT, padx=(4, 4))
        self._npc_desc = tk.Text(desc_row, height=3, width=26,
                                 bg=PALETTE["card2"], fg="#ffffff",
                                 insertbackground="#ffffff",
                                 relief=tk.FLAT, bd=0)
        self._npc_desc.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _level_row(p):
            sp = self._spinbox(p, self._npc_level, 1, 99, w=6,
                               command=self._recalc_npc_hp)
            sp.pack(side=tk.LEFT)
            self._npc_level.trace_add("write", lambda *_: self._recalc_npc_hp())
        self._field_row(gen, "Level", _level_row)

        def _size_row(p):
            cb = ttk.Combobox(p, textvariable=self._npc_size,
                              values=list(HEALTH_SIZE_LOOKUP.keys()),
                              state="readonly", width=12)
            cb.pack(side=tk.LEFT)
            cb.bind("<<ComboboxSelected>>", lambda e: self._recalc_npc_hp())
        self._field_row(gen, "Size", _size_row)

        def _hostile_row(p):
            tk.Checkbutton(p, variable=self._npc_hostile,
                           bg=PALETTE["card"], selectcolor=PALETTE["accent"],
                           fg="#ffffff", activebackground=PALETTE["card"]).pack(side=tk.LEFT)
        self._field_row(gen, "Hostile", _hostile_row)

        def _turns_row(p):
            self._spinbox(p, self._npc_turns_allowed, 1, 10, w=4).pack(side=tk.LEFT)
        self._field_row(gen, "Turns Allowed", _turns_row)

        # Current HP BEFORE Maximum HP
        def _curhp_row(p):
            self._spinbox(p, self._npc_curhp, 1, 99999, w=8).pack(side=tk.LEFT)
        self._field_row(gen, "Current HP", _curhp_row)

        def _maxhp_row(p):
            self._spinbox(p, self._npc_maxhp, 1, 99999, w=8).pack(side=tk.LEFT)
        self._field_row(gen, "Maximum HP", _maxhp_row)

        # ── Stats ─────────────────────────────────────────────────────────────
        _, stats_sec = self._make_section(self._body_frame, "Stats", expanded=False)

        for k in STAT_KEYS:
            def _stat_row(p, _k=k):
                sp = self._spinbox(p, self._npc_stats[_k], 0, 9999, w=6,
                                   command=self._validate_npc_stats)
                sp.pack(side=tk.LEFT)
                self._npc_stats[_k].trace_add("write",
                                               lambda *_: self._validate_npc_stats())
            self._field_row(stats_sec, k, _stat_row)

        tk.Label(stats_sec, textvariable=self._npc_stat_warn,
                 bg=PALETTE["card"], fg="#ff8c00", font=FONTS["small"],
                 wraplength=380, justify="left").pack(anchor="w", padx=4, pady=(0, 4))

        # ── Actions ───────────────────────────────────────────────────────────
        _, act_sec = self._make_section(self._body_frame, "Actions", expanded=False)
        self._action_frame = tk.Frame(act_sec, bg=PALETTE["card"])
        self._action_frame.pack(fill=tk.X)
        flat_btn(act_sec, "+ Add Action", self._add_action_row,
                 style="ghost").pack(anchor="w", pady=(6, 0))

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
        self._item_name = tk.StringVar()
        self._item_level = tk.IntVar(value=1)
        self._item_consumable = tk.BooleanVar(value=False)
        self._item_quantity = tk.IntVar(value=1)
        self._item_value = tk.IntVar(value=0)
        self._item_slot = tk.StringVar(value="(none)")

        # ── General ──────────────────────────────────────────────────────────
        _, gen = self._make_section(self._body_frame, "General", expanded=False)

        self._field_row(gen, "Name *",
                        lambda p: styled_entry(p, textvariable=self._item_name,
                                               width=24).pack(side=tk.LEFT, fill=tk.X, expand=True))

        desc_row = tk.Frame(gen, bg=PALETTE["card"])
        desc_row.pack(fill=tk.X, pady=2)
        self._lbl(desc_row, "Description", anchor="nw").pack(side=tk.LEFT, padx=(4, 4))
        self._item_desc = tk.Text(desc_row, height=3, width=26,
                                  bg=PALETTE["card2"], fg="#ffffff",
                                  insertbackground="#ffffff",
                                  relief=tk.FLAT, bd=0)
        self._item_desc.pack(side=tk.LEFT, fill=tk.X, expand=True)

        for label, var, mn, mx in [
            ("Level",    self._item_level,    1, 99),
            ("Quantity", self._item_quantity, 1, 9999),
            ("Value (g)", self._item_value,   0, 999999),
        ]:
            def _make_sp_row(p, _v=var, _mn=mn, _mx=mx):
                self._spinbox(p, _v, _mn, _mx, w=8).pack(side=tk.LEFT)
            self._field_row(gen, label, _make_sp_row)

        def _consumable_row(p):
            tk.Checkbutton(p, variable=self._item_consumable,
                           bg=PALETTE["card"], selectcolor=PALETTE["accent"],
                           activebackground=PALETTE["card"]).pack(side=tk.LEFT)
        self._field_row(gen, "Consumable", _consumable_row)

        def _slot_row(p):
            slot_opts = ["(none)"] + [f"{k}: {v}" for k, v in EQUIPMENT_SLOTS.items()]
            ttk.Combobox(p, textvariable=self._item_slot,
                         values=slot_opts, state="readonly", width=16).pack(side=tk.LEFT)
        self._field_row(gen, "Equipment Slot", _slot_row)

        # ── Scalars ───────────────────────────────────────────────────────────
        _, sc_sec = self._make_section(self._body_frame, "Scalars", expanded=False)
        self._item_scalar_vars = {}
        for k in STAT_KEYS:
            v = tk.StringVar(value="")
            self._item_scalar_vars[k] = v
            def _sc_row(p, _k=k, _v=v):
                ttk.Combobox(p, textvariable=_v,
                             values=[""] + list(SCALAR_WEIGHT_LOOKUP.keys()),
                             state="readonly", width=8).pack(side=tk.LEFT, padx=4)
            self._field_row(sc_sec, k, _sc_row)

        # ── Stat Modifiers ────────────────────────────────────────────────────
        _, sm_sec = self._make_section(self._body_frame, "Stat Modifiers",
                                       expanded=False)
        self._item_stat_vars = {k: tk.IntVar(value=0) for k in STAT_KEYS}
        self._item_stat_warn = tk.StringVar()
        for k in STAT_KEYS:
            def _sm_row(p, _k=k):
                sp = self._spinbox(p, self._item_stat_vars[_k], -999, 999, w=6,
                                   command=self._validate_item_stats)
                sp.pack(side=tk.LEFT)
                self._item_stat_vars[_k].trace_add(
                    "write", lambda *_: self._validate_item_stats())
            self._field_row(sm_sec, k, _sm_row)
        tk.Label(sm_sec, textvariable=self._item_stat_warn,
                 bg=PALETTE["card"], fg="#ff8c00", font=FONTS["small"],
                 wraplength=380, justify="left").pack(anchor="w", padx=4, pady=(0, 4))

        # ── Actions ───────────────────────────────────────────────────────────
        _, act_sec = self._make_section(self._body_frame, "Actions", expanded=False)
        self._action_frame = tk.Frame(act_sec, bg=PALETTE["card"])
        self._action_frame.pack(fill=tk.X)
        flat_btn(act_sec, "+ Add Action", self._add_action_row,
                 style="ghost").pack(anchor="w", pady=(6, 0))

    def _validate_item_stats(self) -> None:
        if not hasattr(self, "_item_stat_warn") or not self._item_stat_warn:
            return
        try:
            level = self._item_level.get() if hasattr(self, "_item_level") else 1
            mi = max_individual(level)
            mt = max_total(level)
            total = sum(v.get() for v in self._item_stat_vars.values())
            warn = ""
            for k, v in self._item_stat_vars.items():
                if abs(v.get()) > mi:
                    warn = f"Stat exceeds maximum of {mi} for lv.{level}"
                    break
            if not warn and total > mt:
                warn = f"Stat total exceeds maximum of {mt} for lv.{level}"
            self._item_stat_warn.set(warn)
        except Exception:
            pass

    # ── Action row ────────────────────────────────────────────────────────────

    def _add_action_row(self, preset: dict = None) -> None:
        if not hasattr(self, "_action_frame"):
            return
        preset = preset or {}
        pb = preset.get("gives_buff") or {}
        row_data = {
            "name":          tk.StringVar(value=preset.get("name", "")),
            "desc_widget":   None,          # set below
            "desc_init":     preset.get("desc", ""),
            "range":         tk.IntVar(value=preset.get("range", 1)),
            "damage":        tk.IntVar(value=preset.get("damage", 0)),
            "hits":          tk.IntVar(value=preset.get("hits", 1)),
            "has_casts":     tk.BooleanVar(value=bool(preset.get("casts"))),
            "casts_max":     tk.IntVar(value=(preset.get("casts") or {}).get("max_per_rest", 3)),
            "casts_rem":     tk.IntVar(value=(preset.get("casts") or {}).get("remaining", 3)),
            "gives_buff":    tk.BooleanVar(value=bool(pb)),
            "buff_name":     tk.StringVar(value=pb.get("BuffName", "")),
            "buff_value":    tk.IntVar(value=pb.get("BuffValue", 1)),
            "buff_duration": tk.IntVar(value=pb.get("BuffDuration", 5)),
        }
        self._action_rows.append(row_data)

        outer = tk.Frame(self._action_frame, bg=PALETTE["card2"],
                         pady=6, padx=6, relief=tk.FLAT,
                         highlightthickness=1,
                         highlightbackground=PALETTE["border"])
        outer.pack(fill=tk.X, pady=4, padx=2)

        def _frow(label_text, widget_factory):
            """One label-value row inside outer."""
            r = tk.Frame(outer, bg=PALETTE["card2"])
            r.pack(fill=tk.X, pady=2)
            tk.Label(r, text=label_text, bg=PALETTE["card2"],
                     fg="#ffffff", font=FONTS["form_label"],
                     anchor="e", width=14).pack(side=tk.LEFT, padx=(4, 4))
            widget_factory(r)
            return r

        def _sp(p, var, mn, mx, w=7):
            tk.Spinbox(p, from_=mn, to=mx, textvariable=var, width=w,
                       bg=PALETTE["card2"], fg="#ffffff",
                       insertbackground="#ffffff",
                       relief=tk.FLAT, bd=0,
                       buttonbackground=PALETTE["muted"]).pack(side=tk.LEFT, padx=2)

        # Name (+ delete button on right)
        name_row = tk.Frame(outer, bg=PALETTE["card2"])
        name_row.pack(fill=tk.X, pady=2)
        tk.Label(name_row, text="Name", bg=PALETTE["card2"],
                 fg="#ffffff", font=FONTS["form_label"],
                 anchor="e", width=14).pack(side=tk.LEFT, padx=(4, 4))
        styled_entry(name_row, textvariable=row_data["name"],
                     width=18).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        def _remove(r=row_data, f=outer):
            self._action_rows.remove(r)
            f.destroy()
            self._update_scroll()
        tk.Button(name_row, text="×", command=_remove,
                  bg=PALETTE["danger"], fg="#fff",
                  relief=tk.FLAT, font=FONTS["body"],
                  cursor="hand2", padx=6).pack(side=tk.RIGHT, padx=2)

        # Description (2-line textarea)
        desc_row = tk.Frame(outer, bg=PALETTE["card2"])
        desc_row.pack(fill=tk.X, pady=2)
        tk.Label(desc_row, text="Description", bg=PALETTE["card2"],
                 fg="#ffffff", font=FONTS["form_label"],
                 anchor="nw", width=14).pack(side=tk.LEFT, padx=(4, 4))
        desc_text = tk.Text(desc_row, height=2, width=24,
                             bg=PALETTE["card2"], fg="#ffffff",
                             insertbackground="#ffffff",
                             relief=tk.FLAT, bd=1,
                             highlightthickness=1,
                             highlightbackground=PALETTE["border"])
        desc_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        if row_data["desc_init"]:
            desc_text.insert("1.0", row_data["desc_init"])
        row_data["desc_widget"] = desc_text

        # Range / Dmg / Hits — each on own line
        _frow("Range", lambda p: _sp(p, row_data["range"], 0, 99))
        _frow("Dmg",   lambda p: _sp(p, row_data["damage"], -99999, 99999))
        _frow("Hits",  lambda p: _sp(p, row_data["hits"], 1, 99))

        # ── Casts: checkbox + hidden sub-fields directly below ────────────────
        casts_outer = tk.Frame(outer, bg=PALETTE["card2"])
        casts_outer.pack(fill=tk.X, pady=(4, 0))
        casts_chk = tk.Frame(casts_outer, bg=PALETTE["card2"])
        casts_chk.pack(fill=tk.X)
        casts_sub = tk.Frame(casts_outer, bg=PALETTE["card2"])

        def _toggle_casts():
            if row_data["has_casts"].get():
                casts_sub.pack(fill=tk.X, pady=(2, 0))
            else:
                casts_sub.pack_forget()
            self.after_idle(self._update_scroll)

        styled_check(casts_chk, "Limited Uses (Casts)",
                     row_data["has_casts"], command=_toggle_casts,
                     bg=PALETTE["card2"]).pack(side=tk.LEFT, padx=4)

        for label, var in [("Max/rest", row_data["casts_max"]),
                            ("Remaining", row_data["casts_rem"])]:
            tk.Label(casts_sub, text=label, bg=PALETTE["card2"],
                     fg="#ffffff", font=FONTS["form_label"]).pack(side=tk.LEFT, padx=(8, 2))
            tk.Spinbox(casts_sub, from_=0, to=99, textvariable=var, width=4,
                       bg=PALETTE["card2"], fg="#ffffff",
                       insertbackground="#ffffff",
                       relief=tk.FLAT, bd=0,
                       buttonbackground=PALETTE["muted"]).pack(side=tk.LEFT, padx=2)

        if row_data["has_casts"].get():
            casts_sub.pack(fill=tk.X, pady=(2, 0))

        # ── Applies Buff: checkbox + hidden sub-fields directly below ─────────
        buff_outer = tk.Frame(outer, bg=PALETTE["card2"])
        buff_outer.pack(fill=tk.X, pady=(4, 0))
        buff_chk = tk.Frame(buff_outer, bg=PALETTE["card2"])
        buff_chk.pack(fill=tk.X)
        buff_sub = tk.Frame(buff_outer, bg=PALETTE["card2"])

        def _toggle_buff():
            if row_data["gives_buff"].get():
                buff_sub.pack(fill=tk.X, pady=(2, 0))
            else:
                buff_sub.pack_forget()
            self.after_idle(self._update_scroll)

        styled_check(buff_chk, "Applies Buff",
                     row_data["gives_buff"], command=_toggle_buff,
                     bg=PALETTE["card2"]).pack(side=tk.LEFT, padx=4)

        for label, var, w in [("Buff Name", row_data["buff_name"], 10)]:
            tk.Label(buff_sub, text=label, bg=PALETTE["card2"],
                     fg="#ffffff", font=FONTS["form_label"]).pack(side=tk.LEFT, padx=(8, 2))
            styled_entry(buff_sub, textvariable=var, width=w).pack(side=tk.LEFT, padx=2)
        for label, var in [("Value", row_data["buff_value"]),
                            ("Duration(min)", row_data["buff_duration"])]:
            tk.Label(buff_sub, text=label, bg=PALETTE["card2"],
                     fg="#ffffff", font=FONTS["form_label"]).pack(side=tk.LEFT, padx=(8, 2))
            tk.Spinbox(buff_sub, from_=-999, to=999, textvariable=var, width=5,
                       bg=PALETTE["card2"], fg="#ffffff",
                       insertbackground="#ffffff",
                       relief=tk.FLAT, bd=0,
                       buttonbackground=PALETTE["muted"]).pack(side=tk.LEFT, padx=2)

        if row_data["gives_buff"].get():
            buff_sub.pack(fill=tk.X, pady=(2, 0))

        self._update_scroll()

    # ── pre-fill ──────────────────────────────────────────────────────────────

    def _pre_fill(self, obj) -> None:
        from game.objects import NPC, Item
        if isinstance(obj, NPC):
            self._npc_name.set(obj.Name)
            if self._npc_desc:
                self._npc_desc.insert("1.0", obj.Description)
            self._npc_level.set(obj.Level)
            self._npc_size.set(obj.Size)
            self._npc_hostile.set(obj.Hostile)
            self._npc_maxhp.set(obj.MaximumHP)
            self._npc_curhp.set(obj.CurrentHP)
            self._npc_turns_allowed.set(max(1, getattr(obj, "TurnsAllowed", 1)))
            for k in STAT_KEYS:
                if k in self._npc_stats:
                    self._npc_stats[k].set(obj.Stats.get(k, 0))
            if obj.Actions:
                self._fill_actions(obj.Actions)
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
                for k, v in obj.Stats.items():
                    if k in self._item_stat_vars:
                        self._item_stat_vars[k].set(v)
            if obj.Scalars:
                for k, v in obj.Scalars.items():
                    if k in self._item_scalar_vars:
                        self._item_scalar_vars[k].set(v)
            if obj.Actions:
                self._fill_actions(obj.Actions)

    def _fill_actions(self, actions: dict) -> None:
        for name, action in actions.items():
            casts = action.get("Casts")
            pb = {}
            if action.get("GivesBuff"):
                pb = {
                    "BuffName":     action.get("BuffName", ""),
                    "BuffValue":    action.get("BuffValue", 1),
                    "BuffDuration": action.get("BuffDuration", 5),
                }
            self._add_action_row(preset={
                "name":       name,
                "desc":       action.get("Description", ""),
                "range":      action.get("Range", 1),
                "damage":     action.get("BaseDamage", 0),
                "hits":       action.get("Hits", 1),
                "casts":      casts,
                "gives_buff": pb,
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
            desc_w = row.get("desc_widget")
            desc = desc_w.get("1.0", "end-1c") if desc_w else ""
            action = {
                "Description": desc,
                "Range":       row["range"].get(),
                "BaseDamage":  row["damage"].get(),
                "Hits":        row["hits"].get(),
            }
            if row["has_casts"].get():
                action["Casts"] = {
                    "max_per_rest": row["casts_max"].get(),
                    "remaining":    row["casts_rem"].get(),
                }
            if row["gives_buff"].get():
                action["GivesBuff"]    = True
                action["BuffName"]     = row["buff_name"].get().strip()
                action["BuffValue"]    = row["buff_value"].get()
                action["BuffDuration"] = row["buff_duration"].get()
            result[name] = action
        return result or None

    def _build_result_dict(self) -> Optional[dict]:
        t = self._type_var.get()
        if t == "NPC":
            name = self._npc_name.get().strip()
            if not name:
                self._err_var.set("Name is required.")
                return None
            return {
                "type": "NPC", "id": str(_uuid.uuid4()),
                "Name":         name,
                "Description":  self._npc_desc.get("1.0", "end-1c") if self._npc_desc else "",
                "Level":        self._npc_level.get(),
                "Size":         self._npc_size.get(),
                "Hostile":      self._npc_hostile.get(),
                "MaximumHP":    self._npc_maxhp.get(),
                "CurrentHP":    self._npc_curhp.get(),
                "Stats":        {k: v.get() for k, v in self._npc_stats.items()},
                "Actions":      self._collect_actions(),
                "TurnsAllowed": max(1, self._npc_turns_allowed.get()),
            }
        else:   # Item
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
            stats_raw = {k: v.get() for k, v in self._item_stat_vars.items()
                         if v.get() != 0}
            scalars_raw = {k: v.get() for k, v in self._item_scalar_vars.items()
                           if v.get()}
            return {
                "type": "Item", "id": str(_uuid.uuid4()),
                "Name":         name,
                "Description":  self._item_desc.get("1.0", "end-1c") if self._item_desc else "",
                "Level":        self._item_level.get(),
                "Consumable":   self._item_consumable.get(),
                "Quantity":     self._item_quantity.get(),
                "Value":        self._item_value.get(),
                "Stats":        stats_raw if stats_raw else None,
                "Scalars":      scalars_raw if scalars_raw else None,
                "Actions":      self._collect_actions(),
                "EquipmentSlot": slot,
            }

    def _do_spawn(self) -> None:
        self._err_var.set("")
        obj_dict = self._build_result_dict()
        if obj_dict is None:
            return
        self.close()
        self._on_spawn(obj_dict)
