"""
Spawn-from-prefabs dialog — replaces SpawnObjectDialog in the DM right-click menu.

Shows tabbed NPC / Item tables sourced from the session prefab list.
A live search bar at the top of each tab filters on Name and Description.
Clicking (or double-clicking) a row spawns an instance at the target cell.
"""
import uuid as _uuid
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr, styled_entry


def _obj_level(o: dict) -> int:
    try:
        return int(o.get("Level", 1))
    except (TypeError, ValueError):
        return 1


# Per-tab column definitions: (header, width, extractor_fn)
_TAB_COLS = {
    "NPC": [
        ("Name",        20, lambda o: str(o.get("Name", ""))[:20]),
        ("Lv / Size",   12, lambda o: f"Lv{o.get('Level',1)} {o.get('Size','Medium')}"),
        ("Description", 22, lambda o: str(o.get("Description", ""))[:22]),
    ],
    "Item": [
        ("Name",        20, lambda o: str(o.get("Name", ""))[:20]),
        ("Lv / Value",  12, lambda o: f"Lv{o.get('Level',1)}  {o.get('Value',0)}g"),
        ("Description", 22, lambda o: str(o.get("Description", ""))[:22]),
    ],
}


PAGE_SIZE = 25


class SpawnFromPrefabsDialog(Panel):
    def __init__(self, parent, prefabs: List[dict], on_spawn: Callable):
        super().__init__(parent, padx=0, pady=0)
        self._prefabs   = prefabs
        self._on_spawn  = on_spawn
        self._tab       = "NPC"
        self._page      = 0
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search_changed())
        self._level_var = tk.StringVar(value="All")   # level filter
        self._row_frames: list = []
        self._build()

    # ── chrome ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Spawn Object", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        # ── Tab buttons ───────────────────────────────────────────────────────
        tab_bar = tk.Frame(self, bg=PALETTE["card2"], padx=8, pady=6)
        tab_bar.pack(fill=tk.X)
        self._tab_btns: dict = {}
        for tab in ("NPC", "Item"):
            btn = tk.Button(
                tab_bar, text=tab,
                bg=PALETTE["accent"] if tab == self._tab else PALETTE["card"],
                fg="#ffffff",
                font=FONTS["body"], relief=tk.FLAT, cursor="hand2",
                padx=14, pady=4,
                command=lambda t=tab: self._switch_tab(t),
            )
            btn.pack(side=tk.LEFT, padx=2)
            self._tab_btns[tab] = btn

        # ── Search bar + Level filter ─────────────────────────────────────────
        sf = tk.Frame(self, bg=PALETTE["card"], padx=12, pady=8)
        sf.pack(fill=tk.X)
        tk.Label(sf, text="🔍", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["body"]).pack(side=tk.LEFT, padx=(0, 6))
        styled_entry(sf, textvariable=self._search_var, width=20).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(sf, text="✕",
                  command=lambda: self._search_var.set(""),
                  bg=PALETTE["card"], fg=PALETTE["muted"],
                  relief=tk.FLAT, cursor="hand2",
                  font=FONTS["small"]).pack(side=tk.LEFT, padx=(4, 8))
        tk.Label(sf, text="Lv", bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"]).pack(side=tk.LEFT, padx=(0, 4))
        self._level_cb = ttk.Combobox(
            sf, textvariable=self._level_var, values=["All"],
            state="readonly", width=5)
        self._level_cb.pack(side=tk.LEFT)
        self._level_cb.bind("<<ComboboxSelected>>",
                            lambda e: self._on_level_changed())

        # ── Column header ─────────────────────────────────────────────────────
        self._col_hdr = tk.Frame(self, bg=PALETTE["bg"], padx=10, pady=4)
        self._col_hdr.pack(fill=tk.X)

        # ── Scrollable list ───────────────────────────────────────────────────
        list_outer = tk.Frame(self, bg=PALETTE["card"], width=480, height=360)
        list_outer.pack(fill=tk.BOTH, expand=True)
        list_outer.pack_propagate(False)

        vsb = tk.Scrollbar(list_outer, bg=PALETTE["card2"],
                           troughcolor=PALETTE["bg"], width=6)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))

        self._canvas = tk.Canvas(list_outer, bg=PALETTE["card"],
                                 highlightthickness=0,
                                 yscrollcommand=vsb.set)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._canvas.yview)

        self._inner = tk.Frame(self._canvas, bg=PALETTE["card"])
        self._win   = self._canvas.create_window((0,0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(
                              self._win, width=e.width - 8))

        hr(self).pack(fill=tk.X)

        # ── Pagination bar ────────────────────────────────────────────────────
        page_bar = tk.Frame(self, bg=PALETTE["card"], padx=10, pady=4)
        page_bar.pack(fill=tk.X)
        self._prev_btn = tk.Button(page_bar, text="‹ Prev",
                                   command=self._prev_page,
                                   bg=PALETTE["card2"], fg=PALETTE["fg"],
                                   relief=tk.FLAT, cursor="hand2",
                                   font=FONTS["small"], padx=8)
        self._prev_btn.pack(side=tk.LEFT)
        self._page_lbl = tk.Label(page_bar, text="", bg=PALETTE["card"],
                                  fg=PALETTE["muted"], font=FONTS["small"])
        self._page_lbl.pack(side=tk.LEFT, expand=True)
        self._next_btn = tk.Button(page_bar, text="Next ›",
                                   command=self._next_page,
                                   bg=PALETTE["card2"], fg=PALETTE["fg"],
                                   relief=tk.FLAT, cursor="hand2",
                                   font=FONTS["small"], padx=8)
        self._next_btn.pack(side=tk.RIGHT)

        tk.Label(self, text="Click a row to spawn · search filters Name & Description",
                 bg=PALETTE["card"], fg=PALETTE["muted"],
                 font=FONTS["small"], pady=4).pack()

        # Mousewheel scrolls the table from anywhere in the dialog
        self._bind_wheel_recursive(self)
        self._switch_tab("NPC")

    # ── mousewheel ──────────────────────────────────────────────────────────────

    def _on_mousewheel(self, event) -> str:
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _bind_wheel_recursive(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child)

    # ── tab / search ──────────────────────────────────────────────────────────

    def _switch_tab(self, tab: str) -> None:
        self._tab = tab
        self._page = 0
        self._search_var.set("")
        # Repopulate the Level dropdown with the levels present in this tab
        self._level_var.set("All")
        self._level_cb.config(values=self._levels_for_tab())
        for t, btn in self._tab_btns.items():
            btn.config(bg=PALETTE["accent"] if t == tab else PALETTE["card"])
        self._rebuild_col_header()
        self._refresh()

    def _levels_for_tab(self) -> List[str]:
        levels = sorted({_obj_level(p) for p in self._prefabs
                         if p.get("type") == self._tab})
        return ["All"] + [str(l) for l in levels]

    def _on_level_changed(self) -> None:
        self._page = 0
        self._refresh()

    def _on_search_changed(self) -> None:
        # Any search edit resets to the first page
        self._page = 0
        self._refresh()

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._refresh()

    def _next_page(self) -> None:
        total = len(self._filtered())
        if (self._page + 1) * PAGE_SIZE < total:
            self._page += 1
            self._refresh()

    def _rebuild_col_header(self) -> None:
        for w in self._col_hdr.winfo_children():
            w.destroy()
        for header, width, _ in _TAB_COLS[self._tab]:
            tk.Label(self._col_hdr, text=header,
                     bg=PALETTE["bg"], fg="#ffffff",
                     font=FONTS["form_label"],
                     width=width, anchor="w").pack(side=tk.LEFT, padx=2)

    def _filtered(self) -> List[dict]:
        q = self._search_var.get().lower()
        rows = [p for p in self._prefabs if p.get("type") == self._tab]
        if q:
            rows = [r for r in rows
                    if q in r.get("Name", "").lower()
                    or q in r.get("Description", "").lower()]
        # Level filter
        lvl = self._level_var.get()
        if lvl and lvl != "All":
            try:
                want = int(lvl)
                rows = [r for r in rows if _obj_level(r) == want]
            except ValueError:
                pass
        # Sort alphabetically by Name (case-insensitive)
        rows.sort(key=lambda r: str(r.get("Name", "")).lower())
        return rows

    # ── table rendering ───────────────────────────────────────────────────────

    def _refresh(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        self._row_frames = []

        all_rows = self._filtered()
        total = len(all_rows)

        if not all_rows:
            q = self._search_var.get()
            msg = ("No prefabs found." if not q
                   else f'No {self._tab} prefabs match "{q}".')
            tk.Label(self._inner, text=msg, bg=PALETTE["card"],
                     fg=PALETTE["muted"], font=FONTS["body"],
                     pady=24).pack()
            self._update_page_bar(0, 0)
            return

        # Clamp page in case the filtered set shrank
        max_page = max(0, (total - 1) // PAGE_SIZE)
        if self._page > max_page:
            self._page = max_page

        start = self._page * PAGE_SIZE
        rows = all_rows[start:start + PAGE_SIZE]
        self._update_page_bar(total, max_page)

        cols = _TAB_COLS[self._tab]
        for i, obj in enumerate(rows):
            bg = PALETTE["card2"] if i % 2 == 0 else PALETTE["card"]
            row = tk.Frame(self._inner, bg=bg, cursor="hand2", pady=5)
            row.pack(fill=tk.X)
            self._row_frames.append(row)

            for _, width, extractor in cols:
                tk.Label(row, text=extractor(obj),
                         bg=bg, fg=PALETTE["fg"], font=FONTS["body"],
                         width=width, anchor="w", padx=8).pack(side=tk.LEFT)

            # Hover highlight
            def _enter(e, r=row, _bg=bg):
                r.config(bg=PALETTE["accent"])
                for c in r.winfo_children():
                    c.config(bg=PALETTE["accent"])
            def _leave(e, r=row, _bg=bg):
                r.config(bg=_bg)
                for c in r.winfo_children():
                    c.config(bg=_bg)

            row.bind("<Enter>", _enter)
            row.bind("<Leave>", _leave)
            for child in row.winfo_children():
                child.bind("<Enter>", _enter)
                child.bind("<Leave>", _leave)

            # Click spawns
            def _click(e, o=obj):
                self._do_spawn(o)
            row.bind("<Button-1>", _click)
            for child in row.winfo_children():
                child.bind("<Button-1>", _click)

        # Newly-created rows also need the wheel handler
        self._bind_wheel_recursive(self._inner)

    def _update_page_bar(self, total: int, max_page: int) -> None:
        if total == 0:
            self._page_lbl.config(text="0 results")
            self._prev_btn.config(state=tk.DISABLED)
            self._next_btn.config(state=tk.DISABLED)
            return
        self._page_lbl.config(
            text=f"Page {self._page + 1} / {max_page + 1}   ({total} items)")
        self._prev_btn.config(state=tk.NORMAL if self._page > 0 else tk.DISABLED)
        self._next_btn.config(
            state=tk.NORMAL if self._page < max_page else tk.DISABLED)

    # ── spawn ─────────────────────────────────────────────────────────────────

    def _do_spawn(self, obj: dict) -> None:
        new_obj = dict(obj)
        new_obj["id"] = str(_uuid.uuid4())
        self.close()
        self._on_spawn(new_obj)
