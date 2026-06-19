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


def _player_names_from_save(path: Path) -> str:
    try:
        from game.serialise import load_state
        with open(path, "rb") as f:
            state = load_state(f.read())
        names = [p.Name or uid[:6] for uid, p in state.players.items()]
        return ", ".join(names[:4]) or "—"
    except Exception:
        return "?"


class LoadGameDialog(Panel):
    def __init__(self, parent, on_load: Callable):
        super().__init__(parent, padx=0, pady=0)
        self._on_load = on_load
        self._selected: Optional[Path] = None
        self._saves: list = []
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Load Game", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)

        hr(self).pack(fill=tk.X)

        list_frame = tk.Frame(self, bg=PALETTE["card"],
                              width=500, height=280)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        list_frame.pack_propagate(False)

        vsb = tk.Scrollbar(list_frame)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox = tk.Listbox(
            list_frame, bg=PALETTE["card2"], fg=PALETTE["fg"],
            selectbackground=PALETTE["accent"], selectforeground="#fff",
            font=FONTS["body"], relief=tk.FLAT, bd=0,
            yscrollcommand=vsb.set, activestyle="none",
        )
        self._listbox.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)
        self._listbox.bind("<Double-Button-1>", lambda e: self._do_load())

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
        self._listbox.delete(0, tk.END)
        saves_dir = get_saves_dir()
        paths = sorted(saves_dir.glob("*.sav"), key=_save_sort_key, reverse=True)
        self._saves = paths
        for path in paths:
            game_name = re.sub(r"_\d{8}_\d{6}$", "", path.stem)
            players = _player_names_from_save(path)
            self._listbox.insert(tk.END, f"  {game_name:<22} {players}")
        self._selected = None
        self._start_btn.config(state=tk.DISABLED)
        self._del_btn.config(state=tk.DISABLED)

    def _on_select(self, event=None) -> None:
        sel = self._listbox.curselection()
        if sel and sel[0] < len(self._saves):
            self._selected = self._saves[sel[0]]
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
