"""Prefab file list — shown when DM Tool → "Load Prefab Objects" is clicked."""
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, List

import tkinter as tk

from app.constants import PALETTE, FONTS
from app.config import get_prefabs_dir
from ui.panel import Panel
from ui.widgets import flat_btn, hr
from dialogs.confirm_dialog import ask_confirm


def _all_prefab_files() -> List[Path]:
    return sorted(get_prefabs_dir().glob("*.json"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def _prefab_meta(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "name": data.get("name", path.stem),
            "updated_at": data.get("updated_at", ""),
            "count": len(data.get("objects", [])),
            "path": path,
        }
    except Exception:
        return {"name": path.stem, "updated_at": "", "count": 0, "path": path}


class PrefabLoadDialog(Panel):
    def __init__(self, parent, on_load: Callable):
        super().__init__(parent, padx=0, pady=0)
        self._on_load = on_load
        self._selected: Optional[Path] = None
        self._metas: List[dict] = []
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=16, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Load Prefab Objects", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        # Column headers — Name and Date at equal 50 % widths
        col_hdr = tk.Frame(self, bg=PALETTE["card2"], padx=10, pady=4)
        col_hdr.pack(fill=tk.X)
        for col in ("Name", "Date"):
            tk.Label(col_hdr, text=col, bg=PALETTE["card2"],
                     fg="#ffffff", font=FONTS["form_label"],
                     anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        list_frame = tk.Frame(self, bg=PALETTE["card"],
                              width=420, height=300)
        list_frame.pack(fill=tk.BOTH, padx=0, pady=0)
        list_frame.pack_propagate(False)

        canvas = tk.Canvas(list_frame, bg=PALETTE["card"], highlightthickness=0)
        vsb = tk.Scrollbar(list_frame, command=canvas.yview,
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

        self._metas = [_prefab_meta(p) for p in _all_prefab_files()]
        self._row_frames: List[tk.Frame] = []

        for i, meta in enumerate(self._metas):
            bg = PALETTE["card2"] if i % 2 == 0 else PALETTE["card"]
            row = tk.Frame(inner, bg=bg, cursor="hand2", pady=5)
            row.pack(fill=tk.X)
            self._row_frames.append(row)

            updated = meta["updated_at"][:19].replace("T", " ") if meta["updated_at"] else "—"
            for val in (meta["name"], updated):
                tk.Label(row, text=val, bg=bg, fg=PALETTE["fg"],
                         font=FONTS["body"], anchor="w",
                         padx=8).pack(side=tk.LEFT, fill=tk.X, expand=True)

            def _select(e, idx=i, r=row):
                self._select_row(idx, r)

            row.bind("<Button-1>", _select)
            for child in row.winfo_children():
                child.bind("<Button-1>", _select)

        if not self._metas:
            tk.Label(inner, text="No prefab files found.",
                     bg=PALETTE["card"], fg=PALETTE["muted"],
                     font=FONTS["body"], pady=20).pack()

        hr(self).pack(fill=tk.X)
        btn_row = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=8)
        btn_row.pack(fill=tk.X)
        self._open_btn = flat_btn(btn_row, "Open", self._do_open, style="normal")
        self._open_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._open_btn.config(state=tk.DISABLED)
        self._del_btn = flat_btn(btn_row, "Delete", self._do_delete, style="danger")
        self._del_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._del_btn.config(state=tk.DISABLED)
        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT)

    def _select_row(self, idx: int, clicked_row: tk.Frame) -> None:
        for row in self._row_frames:
            row.configure(bg=PALETTE["card2"] if self._row_frames.index(row) % 2 == 0
                          else PALETTE["card"])
            for child in row.winfo_children():
                child.configure(bg=row.cget("bg"))
        clicked_row.configure(bg=PALETTE["accent"])
        for child in clicked_row.winfo_children():
            child.configure(bg=PALETTE["accent"])
        if idx < len(self._metas):
            self._selected = self._metas[idx]["path"]
        self._open_btn.config(state=tk.NORMAL)
        self._del_btn.config(state=tk.NORMAL)

    def _do_open(self) -> None:
        if not self._selected:
            return
        path = self._selected
        self.close()
        self._on_load(path)

    def _do_delete(self) -> None:
        if not self._selected:
            return
        name = self._selected.stem
        if ask_confirm(self, "Delete Prefab", f'Delete "{name}"? This cannot be undone.'):
            self._selected.unlink(missing_ok=True)
            self.close()
