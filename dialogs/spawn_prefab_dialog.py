"""
In-game "Spawn Prefab" dialog (DM only).

Two states within a single Panel:
  1. Table  — lists all loaded prefab objects; clicking a row → detail
  2. Detail — read-only view of one prefab; Spawn / Cancel buttons
"""
from __future__ import annotations
import uuid as _uuid
from typing import Callable, List, Optional

import tkinter as tk
from tkinter import ttk

from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr


class SpawnPrefabDialog(Panel):
    # Types that may be spawned as grid objects; Action prefabs are picked
    # only via the "+Add Prefab Action" button inside the action form.
    _SPAWNABLE_TYPES = {"NPC", "Item"}

    def __init__(self, parent, prefabs: List[dict], on_spawn: Callable):
        super().__init__(parent, padx=0, pady=0)
        # When called from spawn-prefab menu, filter to grid-spawnable types.
        # When called from action picker (_pick_prefab_action), the caller
        # already filtered to Action type, so we honour whatever is passed.
        types = {p.get("type") for p in prefabs}
        if types - {"Action"}:   # contains non-Action → apply spawnable filter
            prefabs = [p for p in prefabs if p.get("type") in self._SPAWNABLE_TYPES]
        self._prefabs = prefabs
        self._on_spawn = on_spawn
        self._selected_idx: Optional[int] = None
        self._build_table()

    # ── table view ────────────────────────────────────────────────────────────

    def _build_table(self) -> None:
        for w in self.winfo_children():
            w.destroy()

        hdr = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Spawn Prefab", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        col_hdr = tk.Frame(self, bg=PALETTE["card2"], padx=10, pady=4)
        col_hdr.pack(fill=tk.X)
        for col, w in [("Name", 18), ("Type", 8), ("Description", 26)]:
            tk.Label(col_hdr, text=col, bg=PALETTE["card2"],
                     fg=PALETTE["muted"], font=FONTS["small"],
                     width=w, anchor="w").pack(side=tk.LEFT, padx=2)

        list_outer = tk.Frame(self, bg=PALETTE["card"],
                              width=440, height=300)
        list_outer.pack(fill=tk.BOTH, expand=True)
        list_outer.pack_propagate(False)

        canvas = tk.Canvas(list_outer, bg=PALETTE["card"], highlightthickness=0)
        vsb = tk.Scrollbar(list_outer, command=canvas.yview,
                           bg=PALETTE["card2"], troughcolor=PALETTE["bg"],
                           width=6)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg=PALETTE["card"])
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))

        self._row_frames: List[tk.Frame] = []

        for i, obj in enumerate(self._prefabs):
            bg = PALETTE["card2"] if i % 2 == 0 else PALETTE["card"]
            row = tk.Frame(inner, bg=bg, cursor="hand2", pady=4)
            row.pack(fill=tk.X)
            self._row_frames.append(row)

            name = str(obj.get("Name", obj.get("type", "?")))[:18]
            otype = str(obj.get("type", "?"))[:8]
            desc = str(obj.get("Description", ""))[:36]
            for val, w in [(name, 18), (otype, 8), (desc, 26)]:
                tk.Label(row, text=val, bg=bg, fg=PALETTE["fg"],
                         font=FONTS["body"], width=w,
                         anchor="w", padx=6).pack(side=tk.LEFT)

            def _click(e, idx=i, r=row):
                self._show_detail(idx)

            row.bind("<Button-1>", _click)
            for child in row.winfo_children():
                child.bind("<Button-1>", _click)

        if not self._prefabs:
            tk.Label(inner, text="No prefab objects loaded.",
                     bg=PALETTE["card"], fg=PALETTE["muted"],
                     font=FONTS["body"], pady=20).pack()

        hr(self).pack(fill=tk.X)
        flat_btn(self, "Cancel", self.close, style="ghost").pack(pady=8)

    # ── detail view ───────────────────────────────────────────────────────────

    def _show_detail(self, idx: int) -> None:
        obj = self._prefabs[idx]
        for w in self.winfo_children():
            w.destroy()

        hdr = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Prefab Detail", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        hr(self).pack(fill=tk.X)

        # Scroll area for detail fields
        canvas = tk.Canvas(self, bg=PALETTE["card"],
                           highlightthickness=0, width=440, height=300)
        vsb = tk.Scrollbar(self, command=canvas.yview, width=6,
                           bg=PALETTE["card2"], troughcolor=PALETTE["bg"])
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg=PALETTE["card"], padx=14, pady=8)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))

        self._render_readonly_fields(inner, obj)

        hr(self).pack(fill=tk.X)
        btn_row = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=8)
        btn_row.pack(fill=tk.X)
        flat_btn(btn_row, "Spawn",
                 lambda: self._do_spawn(obj), style="normal").pack(
            side=tk.LEFT, padx=(0, 8), ipadx=8)
        flat_btn(btn_row, "← Back",
                 self._build_table, style="ghost").pack(side=tk.LEFT)

    def _render_readonly_fields(self, parent: tk.Frame, obj: dict) -> None:
        skip = {"id"}
        for key, val in obj.items():
            if key in skip:
                continue
            row = tk.Frame(parent, bg=PALETTE["card"])
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"{key}:", bg=PALETTE["card"],
                     fg=PALETTE["muted"], font=FONTS["form_label"],
                     anchor="e", width=16).pack(side=tk.LEFT, padx=(0, 8))
            display = str(val)
            if len(display) > 60:
                display = display[:57] + "…"
            tk.Label(row, text=display, bg=PALETTE["card"],
                     fg=PALETTE["fg"], font=FONTS["body"],
                     anchor="w", wraplength=260).pack(side=tk.LEFT, fill=tk.X)

    def _do_spawn(self, obj: dict) -> None:
        # Make a copy with a fresh UUID so it becomes an independent instance
        new_obj = dict(obj)
        new_obj["id"] = str(_uuid.uuid4())
        self.close()
        self._on_spawn(new_obj)
