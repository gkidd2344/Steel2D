"""
PrefabSelectDialog — shown when hosting a game (new or loaded).

Lists every prefab JSON file (filename + record count) with a checkbox per row.
Only the ticked files are loaded into the hosted session. If no prefab files
exist, the caller skips this dialog entirely.
"""
from __future__ import annotations
import tkinter as tk
from typing import Callable, List

from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr


class PrefabSelectDialog(Panel):
    def __init__(self, parent, files: List[dict], on_confirm: Callable[[list], None]):
        """
        files: list of {"path": Path, "filename": str, "count": int}
        on_confirm: called with the list of selected Path objects.
        """
        super().__init__(parent, padx=0, pady=0)
        self._files = files
        self._on_confirm = on_confirm
        # Default: every file ticked
        self._vars = [tk.BooleanVar(value=True) for _ in files]
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Select Prefab Packs", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        tk.Label(self, text="Choose which prefab files to load into this game.",
                 bg=PALETTE["card"], fg=PALETTE["muted"],
                 font=FONTS["small"], padx=14, pady=6,
                 anchor="w").pack(fill=tk.X)

        # Select-all / none controls
        ctrl = tk.Frame(self, bg=PALETTE["card"], padx=14)
        ctrl.pack(fill=tk.X)
        flat_btn(ctrl, "Select All", lambda: self._set_all(True),
                 style="ghost").pack(side=tk.LEFT, padx=(0, 6))
        flat_btn(ctrl, "Select None", lambda: self._set_all(False),
                 style="ghost").pack(side=tk.LEFT)

        # Column header (2 columns: Filename | Records)
        col_hdr = tk.Frame(self, bg=PALETTE["bg"], padx=12, pady=4)
        col_hdr.pack(fill=tk.X, pady=(8, 0))
        col_hdr.grid_columnconfigure(0, weight=4)
        col_hdr.grid_columnconfigure(1, weight=1)
        tk.Label(col_hdr, text="Prefab File", bg=PALETTE["bg"],
                 fg=PALETTE["muted"], font=FONTS["small"],
                 anchor="w").grid(row=0, column=0, sticky="ew", padx=2)
        tk.Label(col_hdr, text="Records", bg=PALETTE["bg"],
                 fg=PALETTE["muted"], font=FONTS["small"],
                 anchor="e").grid(row=0, column=1, sticky="ew", padx=2)
        hr(self).pack(fill=tk.X)

        # Scrollable file list
        list_outer = tk.Frame(self, bg=PALETTE["card"], width=460, height=280)
        list_outer.pack(fill=tk.BOTH, expand=True)
        list_outer.pack_propagate(False)

        vsb = tk.Scrollbar(list_outer, bg=PALETTE["card2"],
                           troughcolor=PALETTE["bg"], width=6)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))
        canvas = tk.Canvas(list_outer, bg=PALETTE["card"],
                           highlightthickness=0, yscrollcommand=vsb.set)
        canvas.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=canvas.yview)
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        inner = tk.Frame(canvas, bg=PALETTE["card"])
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))

        if not self._files:
            tk.Label(inner, text="No prefab files found.",
                     bg=PALETTE["card"], fg=PALETTE["muted"],
                     font=FONTS["body"], pady=24).pack()
        else:
            for i, finfo in enumerate(self._files):
                bg = PALETTE["card2"] if i % 2 == 0 else PALETTE["card"]
                row = tk.Frame(inner, bg=bg, pady=4, padx=10, cursor="hand2")
                row.pack(fill=tk.X)
                row.grid_columnconfigure(0, weight=4)
                row.grid_columnconfigure(1, weight=1)

                chk = tk.Checkbutton(
                    row, variable=self._vars[i], bg=bg,
                    fg=PALETTE["fg"], selectcolor=PALETTE["card2"],
                    activebackground=bg, font=FONTS["body"],
                    anchor="w", text=finfo["filename"],
                )
                chk.grid(row=0, column=0, sticky="ew")
                tk.Label(row, text=str(finfo["count"]), bg=bg,
                         fg=PALETTE["fg_dim"], font=FONTS["body"],
                         anchor="e").grid(row=0, column=1, sticky="ew", padx=2)

                # Clicking anywhere on the row toggles the checkbox
                def _toggle(e, idx=i):
                    self._vars[idx].set(not self._vars[idx].get())
                row.bind("<Button-1>", _toggle)

        hr(self).pack(fill=tk.X)
        btn_row = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=10)
        btn_row.pack(fill=tk.X)
        flat_btn(btn_row, "Start Game", self._confirm, style="normal").pack(
            side=tk.LEFT, padx=(0, 8), ipadx=8)
        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT)

    def _set_all(self, value: bool) -> None:
        for v in self._vars:
            v.set(value)

    def _confirm(self) -> None:
        selected = [f["path"] for f, v in zip(self._files, self._vars) if v.get()]
        self.close()
        self._on_confirm(selected)
