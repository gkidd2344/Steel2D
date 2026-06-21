import re
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional
from app.constants import PALETTE, FONTS
from app.config import get_saves_dir
from ui.panel import Panel
from ui.widgets import flat_btn, hr
from dialogs.confirm_dialog import ask_confirm


def _save_sort_key(path: Path):
    m = re.search(r"_(\d{8}_\d{6})\.sav$", path.name)
    if m:
        return m.group(1)
    return str(path.stat().st_mtime)


def _parse_save_info(path: Path) -> tuple:
    """Return (game_name, datetime_str, players_str) from a save file path."""
    # Game name — strip trailing _YYYYMMDD_HHMMSS timestamp if present
    stem = path.stem
    m = re.search(r"^(.+?)_(\d{8})_(\d{6})$", stem)
    if m:
        game_name = m.group(1)
        d, t = m.group(2), m.group(3)
        dt_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}  {t[:2]}:{t[2:4]}"
    else:
        game_name = stem
        import datetime
        mtime = path.stat().st_mtime
        dt_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d  %H:%M")

    # Player list — read from save file
    try:
        from game.serialise import load_state
        with open(path, "rb") as f:
            state = load_state(f.read())
        names = [p.Name or uid[:6] for uid, p in state.players.items()]
        players_str = ", ".join(names[:4]) or "—"
        if len(names) > 4:
            players_str += f" +{len(names)-4}"
    except Exception:
        players_str = "?"

    return game_name, dt_str, players_str


_COLS = [("Game Name", 0, 3), ("Date / Time", 1, 2), ("Players", 2, 3)]


class LoadGameDialog(Panel):
    def __init__(self, parent, on_load: Callable):
        super().__init__(parent, padx=0, pady=0)
        self._on_load = on_load
        self._selected: Optional[Path] = None
        self._saves: list = []
        self._row_frames: list = []
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Load Game", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)

        hr(self).pack(fill=tk.X)

        # ── Column header ─────────────────────────────────────────────────────
        col_hdr = tk.Frame(self, bg=PALETTE["bg"], pady=4, padx=10)
        col_hdr.pack(fill=tk.X)
        col_hdr.grid_columnconfigure(0, weight=3)
        col_hdr.grid_columnconfigure(1, weight=2)
        col_hdr.grid_columnconfigure(2, weight=3)
        for label, col_idx, _ in _COLS:
            tk.Label(col_hdr, text=label, bg=PALETTE["bg"],
                     fg=PALETTE["muted"], font=FONTS["small"],
                     anchor="w").grid(row=0, column=col_idx, sticky="ew", padx=4)

        hr(self).pack(fill=tk.X)

        # ── Scrollable list ───────────────────────────────────────────────────
        list_outer = tk.Frame(self, bg=PALETTE["card"], width=520, height=260)
        list_outer.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        list_outer.pack_propagate(False)

        vsb = tk.Scrollbar(list_outer, bg=PALETTE["card2"],
                           troughcolor=PALETTE["bg"], width=6)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))

        self._canvas = tk.Canvas(list_outer, bg=PALETTE["card"],
                                 highlightthickness=0,
                                 yscrollcommand=vsb.set)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._canvas.yview)

        self._list_frame = tk.Frame(self._canvas, bg=PALETTE["card"])
        self._win = self._canvas.create_window((0, 0), window=self._list_frame,
                                                anchor="nw")
        self._list_frame.bind("<Configure>",
                              lambda e: self._canvas.configure(
                                  scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(
                              self._win, width=e.width))

        hr(self).pack(fill=tk.X)

        btn_row = tk.Frame(self, bg=PALETTE["card"], padx=16, pady=10)
        btn_row.pack(fill=tk.X)
        self._start_btn = flat_btn(btn_row, "Start", self._do_load, style="normal")
        self._start_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._start_btn.config(state=tk.DISABLED)
        self._del_btn = flat_btn(btn_row, "Delete", self._do_delete, style="danger")
        self._del_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._del_btn.config(state=tk.DISABLED)
        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT)

        self._refresh()

    def _refresh(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._row_frames = []
        self._selected = None
        self._start_btn.config(state=tk.DISABLED)
        self._del_btn.config(state=tk.DISABLED)

        saves_dir = get_saves_dir()
        paths = sorted(saves_dir.glob("*.sav"), key=_save_sort_key, reverse=True)
        self._saves = paths

        if not paths:
            tk.Label(self._list_frame, text="No save files found.",
                     bg=PALETTE["card"], fg=PALETTE["muted"],
                     font=FONTS["body"], pady=20).pack()
            return

        for i, path in enumerate(paths):
            game_name, dt_str, players_str = _parse_save_info(path)
            row_bg = PALETTE["card2"] if i % 2 == 0 else PALETTE["card"]
            row = tk.Frame(self._list_frame, bg=row_bg, pady=6, padx=10,
                           cursor="hand2")
            row.pack(fill=tk.X)
            row.grid_columnconfigure(0, weight=3)
            row.grid_columnconfigure(1, weight=2)
            row.grid_columnconfigure(2, weight=3)

            tk.Label(row, text=game_name[:26], bg=row_bg, fg=PALETTE["fg"],
                     font=FONTS["body"], anchor="w").grid(
                row=0, column=0, sticky="ew", padx=4)
            tk.Label(row, text=dt_str, bg=row_bg, fg=PALETTE["fg_dim"],
                     font=FONTS["small"], anchor="w").grid(
                row=0, column=1, sticky="ew", padx=4)
            tk.Label(row, text=players_str[:28], bg=row_bg, fg=PALETTE["fg_dim"],
                     font=FONTS["small"], anchor="w").grid(
                row=0, column=2, sticky="ew", padx=4)

            def _select(event=None, p=path, r=row, bg=row_bg, idx=i):
                self._select_row(p, r, bg, idx)

            def _dbl(event=None, p=path, r=row, bg=row_bg, idx=i):
                self._select_row(p, r, bg, idx)
                self._do_load()

            row.bind("<Button-1>", _select)
            row.bind("<Double-Button-1>", _dbl)
            for child in row.grid_slaves():
                child.bind("<Button-1>", _select)
                child.bind("<Double-Button-1>", _dbl)

            self._row_frames.append((row, row_bg))

    def _select_row(self, path: Path, row: tk.Frame, orig_bg: str, idx: int) -> None:
        # Deselect all rows
        for r, bg in self._row_frames:
            r.config(bg=bg)
            for child in r.grid_slaves():
                try:
                    child.config(bg=bg)
                except Exception:
                    pass
        # Highlight selected row
        row.config(bg=PALETTE["accent"])
        for child in row.grid_slaves():
            try:
                child.config(bg=PALETTE["accent"])
            except Exception:
                pass
        self._selected = path
        self._start_btn.config(state=tk.NORMAL)
        self._del_btn.config(state=tk.NORMAL)

    def _do_load(self) -> None:
        if not self._selected:
            return
        try:
            from game.serialise import load_state
            with open(self._selected, "rb") as f:
                state = load_state(f.read())
        except Exception as e:
            tk.messagebox.showerror("Load Error", str(e))
            return
        self.close()
        self._on_load(state)

    def _do_delete(self) -> None:
        if not self._selected:
            return
        name = re.sub(r"_\d{8}_\d{6}$", "", self._selected.stem)
        if ask_confirm(self, "Delete Save",
                       f"Delete '{name}'? This cannot be undone."):
            self._selected.unlink(missing_ok=True)
            self._refresh()
