"""
Read-only inventory and actions panels used by the Character Editor screen.

Both are view-only: hover tooltips and a click-through action detail window,
but no dragging, right-click menus, or mutation.
"""
from __future__ import annotations
import tkinter as tk
from typing import List, Tuple

from app.constants import PALETTE, FONTS, EQUIPMENT_SLOTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr, styled_entry
from dialogs.actions_dialog import _bind_buff_tooltip, _casts_text, _scales_text

PAGE_SIZE = 20
ITEM_COLOR = "#ff8800"


# ── hover tooltip ─────────────────────────────────────────────────────────────

def _bind_text_tooltip(widget: tk.Widget, lines: List[str]) -> None:
    tip: list = [None]

    def _show(event):
        if tip[0] or not lines:
            return
        t = tk.Toplevel(widget)
        t.overrideredirect(True)
        t.wm_attributes("-topmost", True)
        t.geometry(f"+{event.x_root + 14}+{event.y_root + 14}")
        tk.Label(t, text="\n".join(lines), bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["small"],
                 justify="left", padx=8, pady=6,
                 relief=tk.SOLID, bd=1, wraplength=260).pack()
        tip[0] = t

    def _hide(event):
        if tip[0]:
            try:
                tip[0].destroy()
            except Exception:
                pass
            tip[0] = None

    widget.bind("<Enter>", _show, add=True)
    widget.bind("<Leave>", _hide, add=True)


def _item_tooltip_lines(item: dict) -> List[str]:
    lines = [item.get("Name", "Item")]
    desc = item.get("Description")
    if desc:
        lines.append(desc)
    lines.append(f"Level: {item.get('Level', 1)}")
    lines.append(f"Qty: {item.get('Quantity', 1)}    Value: {item.get('Value', 0)}g")
    if item.get("Consumable"):
        lines.append("Consumable")
    slot = item.get("EquipmentSlot")
    if slot:
        lines.append(f"Slot: {EQUIPMENT_SLOTS.get(slot, slot)}")
    if item.get("ThrownDamage"):
        lines.append(f"Thrown Damage: {item.get('ThrownDamage')}")
    acts = item.get("Actions") or {}
    if acts:
        lines.append("Actions: " + ", ".join(acts.keys()))
    return lines


# ── readonly action detail window ─────────────────────────────────────────────

def open_action_detail(parent, action_name: str, adef: dict, source: str = "") -> None:
    detail = Panel(parent.winfo_toplevel(), padx=24, pady=18)

    hdr = tk.Frame(detail, bg=PALETTE["card"])
    hdr.pack(fill=tk.X, pady=(0, 8))
    tk.Label(hdr, text=action_name, bg=PALETTE["card"],
             fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
    flat_btn(hdr, "✕", detail.close, style="ghost").pack(side=tk.RIGHT)
    hr(detail).pack(fill=tk.X, pady=(0, 10))

    def _row(label: str, value: str) -> None:
        f = tk.Frame(detail, bg=PALETTE["card"])
        f.pack(fill=tk.X, pady=2)
        tk.Label(f, text=label, bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"], width=16, anchor="e").pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(f, text=value, bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["body"], anchor="w", wraplength=240,
                 justify="left").pack(side=tk.LEFT)

    if source:
        _row("From item:", source)
    _row("Description:", adef.get("Description") or "—")
    _row("Range:", f"{adef.get('Range', 1)} tile(s)")
    _row("Base Damage:", str(adef.get("BaseDamage", 0)))
    _row("Hits:", str(adef.get("Hits", 1)))

    casts = adef.get("Casts")
    if casts:
        _row("Casts / rest:", f"{casts.get('remaining', 0)} / {casts.get('max_per_rest', 0)}")
    scales = _scales_text(adef)
    if scales:
        _row("Scales With:", scales)

    # "Use" effect metadata
    fx = [k for k, lbl in (("UnlocksDoor", "Unlocks Door"),
                           ("FreezesWater", "Freezes Water"),
                           ("BreaksWall", "Breaks Wall")) if adef.get(k)]
    if fx:
        names = {"UnlocksDoor": "Unlocks Door", "FreezesWater": "Freezes Water",
                 "BreaksWall": "Breaks Wall"}
        _row("Use effects:", ", ".join(names[k] for k in fx))

    buffs = adef.get("GivesBuffs") or []
    if not buffs and adef.get("GivesBuff") and adef.get("BuffName"):
        buffs = [{"Name": adef.get("BuffName"), "Type": "Stat Modifier",
                  "Value": adef.get("BuffValue", 0), "Duration": adef.get("BuffDuration", 0)}]
    if buffs:
        hr(detail).pack(fill=tk.X, pady=6)
        tk.Label(detail, text="Applies Buffs:", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(anchor="w", pady=(0, 4))
        for buff_def in buffs:
            blbl = tk.Label(detail, text=f"  • {buff_def.get('Name', '?')}",
                            bg=PALETTE["card"], fg=PALETTE["accent"],
                            font=FONTS["body"], anchor="w", cursor="hand2")
            blbl.pack(anchor="w")
            _bind_buff_tooltip(blbl, buff_def)

    hr(detail).pack(fill=tk.X, pady=8)
    flat_btn(detail, "Close", detail.close, style="ghost").pack(fill=tk.X, ipady=3)


# ── readonly inventory ─────────────────────────────────────────────────────────

class ReadonlyInventoryPanel(Panel):
    """View-only equipment + backpack with item hover tooltips (no interaction)."""

    def __init__(self, parent, player: dict):
        super().__init__(parent, padx=0, pady=0, placement="right")
        self._player = player or {}
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=16, pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Inventory  (read-only)", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        hr(self).pack(fill=tk.X)

        equipment = self._player.get("Equipment", {}) or {}
        inventory = self._player.get("Inventory", []) or []

        # ── Equipment ─────────────────────────────────────────────────────────
        tk.Label(self, text="Equipment", bg=PALETTE["card2"],
                 fg=PALETTE["muted"], font=FONTS["small"],
                 anchor="w", padx=12, pady=4).pack(fill=tk.X)
        eq_grid = tk.Frame(self, bg=PALETTE["card"], padx=10, pady=6)
        eq_grid.pack(fill=tk.X)
        for col, (slot_id, slot_name) in enumerate(EQUIPMENT_SLOTS.items()):
            item = equipment.get(str(slot_id)) or equipment.get(slot_id)
            cell = tk.Frame(eq_grid, bg=PALETTE["card2"],
                            highlightbackground=PALETTE["border"],
                            highlightthickness=1, width=64, height=58)
            cell.grid(row=col // 5, column=col % 5, padx=2, pady=2)
            cell.pack_propagate(False)
            tk.Label(cell, text=slot_name, bg=PALETTE["card2"],
                     fg=PALETTE["muted"], font=("Segoe UI", 7)).pack(pady=(3, 0))
            if item:
                lbl = tk.Label(cell, text=str(item.get("Name", ""))[:8],
                               bg=PALETTE["card2"], fg=ITEM_COLOR,
                               font=FONTS["small"], wraplength=58)
                lbl.pack()
                _bind_text_tooltip(lbl, _item_tooltip_lines(item))
                _bind_text_tooltip(cell, _item_tooltip_lines(item))

        hr(self).pack(fill=tk.X, pady=2)

        # ── Backpack (scrollable) ─────────────────────────────────────────────
        tk.Label(self, text="Backpack", bg=PALETTE["card2"],
                 fg=PALETTE["muted"], font=FONTS["small"],
                 anchor="w", padx=12, pady=4).pack(fill=tk.X)

        outer = tk.Frame(self, bg=PALETTE["card"], width=320, height=220)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.pack_propagate(False)
        vsb = tk.Scrollbar(outer, bg=PALETTE["card2"], troughcolor=PALETTE["bg"], width=6)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))
        canvas = tk.Canvas(outer, bg=PALETTE["card"], highlightthickness=0,
                           yscrollcommand=vsb.set)
        canvas.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=canvas.yview)
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        inner = tk.Frame(canvas, bg=PALETTE["card"])
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))

        if not inventory:
            tk.Label(inner, text="Empty", bg=PALETTE["card"], fg=PALETTE["muted"],
                     font=FONTS["small"], pady=12).pack()
        else:
            for idx, item in enumerate(inventory):
                row_bg = PALETTE["card"] if idx % 2 == 0 else PALETTE["card2"]
                row = tk.Frame(inner, bg=row_bg)
                row.pack(fill=tk.X, pady=1)
                qty = item.get("Quantity", 1)
                name = str(item.get("Name", "?"))
                txt = f"{name}   ×{qty}" if qty > 1 else name
                lbl = tk.Label(row, text=txt, bg=row_bg, fg=PALETTE["fg"],
                               font=FONTS["body"], anchor="w", padx=8, pady=3)
                lbl.pack(fill=tk.X)
                _bind_text_tooltip(row, _item_tooltip_lines(item))
                _bind_text_tooltip(lbl, _item_tooltip_lines(item))

        hr(self).pack(fill=tk.X)
        flat_btn(self, "Close", self.close, style="ghost").pack(pady=6)


# ── readonly actions ───────────────────────────────────────────────────────────

class ReadonlyActionsPanel(Panel):
    """View-only actions with Known / Item tabs, search, pagination, detail view."""

    def __init__(self, parent, player: dict):
        super().__init__(parent, padx=0, pady=0, placement="left")
        self._player = player or {}
        self._tab = "Known Actions"
        self._page = 0
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search())
        self._build()

    # data ----------------------------------------------------------------------

    def _all_actions(self) -> List[Tuple[str, dict, str]]:
        """Return (name, adef, source) for the current tab."""
        out = []
        if self._tab == "Known Actions":
            for name, adef in (self._player.get("Actions") or {}).items():
                out.append((name, adef, ""))
        else:  # Item Actions — from equipped items
            equipment = self._player.get("Equipment", {}) or {}
            for item in equipment.values():
                iname = item.get("Name", "Item")
                for name, adef in (item.get("Actions") or {}).items():
                    out.append((name, adef, iname))
        return out

    def _filtered(self) -> List[Tuple[str, dict, str]]:
        q = self._search_var.get().lower()
        rows = self._all_actions()
        if q:
            rows = [r for r in rows
                    if q in r[0].lower()
                    or q in (r[1].get("Description") or "").lower()]
        rows.sort(key=lambda r: r[0].lower())
        return rows

    # layout --------------------------------------------------------------------

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=16, pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Actions  (read-only)", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        hr(self).pack(fill=tk.X)

        # Tabs
        tab_bar = tk.Frame(self, bg=PALETTE["card2"], padx=8, pady=6)
        tab_bar.pack(fill=tk.X)
        self._tab_btns = {}
        for tab in ("Known Actions", "Item Actions"):
            b = tk.Button(tab_bar, text=tab,
                          bg=PALETTE["accent"] if tab == self._tab else PALETTE["card"],
                          fg="#ffffff", font=FONTS["small"], relief=tk.FLAT,
                          cursor="hand2", padx=10, pady=3,
                          command=lambda t=tab: self._switch_tab(t))
            b.pack(side=tk.LEFT, padx=2)
            self._tab_btns[tab] = b

        # Search
        sf = tk.Frame(self, bg=PALETTE["card"], padx=10, pady=6)
        sf.pack(fill=tk.X)
        tk.Label(sf, text="🔍", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["body"]).pack(side=tk.LEFT, padx=(0, 6))
        styled_entry(sf, textvariable=self._search_var, width=24).pack(
            side=tk.LEFT, fill=tk.X, expand=True)

        # Column header
        col_hdr = tk.Frame(self, bg=PALETTE["bg"], padx=10, pady=3)
        col_hdr.pack(fill=tk.X)
        col_hdr.grid_columnconfigure(0, weight=3)
        col_hdr.grid_columnconfigure(1, weight=4)
        col_hdr.grid_columnconfigure(2, weight=1)
        for txt, c in (("Name", 0), ("Description", 1), ("Casts", 2)):
            tk.Label(col_hdr, text=txt, bg=PALETTE["bg"], fg=PALETTE["muted"],
                     font=FONTS["small"], anchor="w").grid(row=0, column=c, sticky="ew", padx=2)
        hr(self).pack(fill=tk.X)

        # Scrollable list
        outer = tk.Frame(self, bg=PALETTE["card"], width=340, height=240)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.pack_propagate(False)
        vsb = tk.Scrollbar(outer, bg=PALETTE["card2"], troughcolor=PALETTE["bg"], width=6)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))
        self._canvas = tk.Canvas(outer, bg=PALETTE["card"], highlightthickness=0,
                                 yscrollcommand=vsb.set)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._canvas.yview)
        self._canvas.bind("<MouseWheel>",
                          lambda e: self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self._inner = tk.Frame(self._canvas, bg=PALETTE["card"])
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(self._win, width=e.width))

        hr(self).pack(fill=tk.X)
        page_bar = tk.Frame(self, bg=PALETTE["card"], padx=10, pady=4)
        page_bar.pack(fill=tk.X)
        self._prev_btn = tk.Button(page_bar, text="‹ Prev", command=self._prev,
                                   bg=PALETTE["card2"], fg=PALETTE["fg"],
                                   relief=tk.FLAT, cursor="hand2", font=FONTS["small"], padx=8)
        self._prev_btn.pack(side=tk.LEFT)
        self._page_lbl = tk.Label(page_bar, text="", bg=PALETTE["card"],
                                  fg=PALETTE["muted"], font=FONTS["small"])
        self._page_lbl.pack(side=tk.LEFT, expand=True)
        self._next_btn = tk.Button(page_bar, text="Next ›", command=self._next,
                                   bg=PALETTE["card2"], fg=PALETTE["fg"],
                                   relief=tk.FLAT, cursor="hand2", font=FONTS["small"], padx=8)
        self._next_btn.pack(side=tk.RIGHT)

        flat_btn(self, "Close", self.close, style="ghost").pack(pady=6)
        self._refresh()

    # behaviour -----------------------------------------------------------------

    def _switch_tab(self, tab: str) -> None:
        self._tab = tab
        self._page = 0
        self._search_var.set("")
        for t, b in self._tab_btns.items():
            b.config(bg=PALETTE["accent"] if t == tab else PALETTE["card"])
        self._refresh()

    def _on_search(self) -> None:
        self._page = 0
        self._refresh()

    def _prev(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._refresh()

    def _next(self) -> None:
        if (self._page + 1) * PAGE_SIZE < len(self._filtered()):
            self._page += 1
            self._refresh()

    def _refresh(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        rows = self._filtered()
        total = len(rows)
        max_page = max(0, (total - 1) // PAGE_SIZE) if total else 0
        if self._page > max_page:
            self._page = max_page

        if not rows:
            tk.Label(self._inner, text="No actions.", bg=PALETTE["card"],
                     fg=PALETTE["muted"], font=FONTS["body"], pady=20).pack()
        else:
            start = self._page * PAGE_SIZE
            for i, (name, adef, source) in enumerate(rows[start:start + PAGE_SIZE]):
                bg = PALETTE["card"] if i % 2 == 0 else PALETTE["card2"]
                row = tk.Frame(self._inner, bg=bg, cursor="hand2", pady=4, padx=10)
                row.pack(fill=tk.X)
                row.grid_columnconfigure(0, weight=3)
                row.grid_columnconfigure(1, weight=4)
                row.grid_columnconfigure(2, weight=1)
                tk.Label(row, text=name, bg=bg, fg=PALETTE["fg"], font=FONTS["body"],
                         anchor="w", padx=2).grid(row=0, column=0, sticky="ew")
                desc = (adef.get("Description") or "")[:50]
                if source:
                    desc = (f"[{source}] " + desc).strip()
                tk.Label(row, text=desc, bg=bg, fg=PALETTE["fg_dim"], font=FONTS["small"],
                         anchor="w", padx=2, wraplength=150).grid(row=0, column=1, sticky="ew")
                tk.Label(row, text=_casts_text(adef), bg=bg, fg=PALETTE["fg_dim"],
                         font=FONTS["small"], anchor="w", padx=2).grid(row=0, column=2, sticky="ew")

                def _click(e, n=name, d=adef, s=source):
                    open_action_detail(self, n, d, s)

                def _enter(e, r=row):
                    r.config(bg=PALETTE["accent"])
                    for c in r.grid_slaves():
                        try: c.config(bg=PALETTE["accent"])
                        except Exception: pass

                def _leave(e, r=row, _bg=bg):
                    r.config(bg=_bg)
                    for c in r.grid_slaves():
                        try: c.config(bg=_bg)
                        except Exception: pass

                row.bind("<Button-1>", _click)
                row.bind("<Enter>", _enter)
                row.bind("<Leave>", _leave)
                for c in row.grid_slaves():
                    c.bind("<Button-1>", _click)
                    c.bind("<Enter>", _enter)
                    c.bind("<Leave>", _leave)

        # page bar
        if total == 0:
            self._page_lbl.config(text="0 results")
            self._prev_btn.config(state=tk.DISABLED)
            self._next_btn.config(state=tk.DISABLED)
        else:
            self._page_lbl.config(text=f"Page {self._page + 1} / {max_page + 1}   ({total})")
            self._prev_btn.config(state=tk.NORMAL if self._page > 0 else tk.DISABLED)
            self._next_btn.config(state=tk.NORMAL if self._page < max_page else tk.DISABLED)
