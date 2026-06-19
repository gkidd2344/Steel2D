import json
import tkinter as tk
from datetime import datetime, timezone
from typing import List

from app.constants import PALETTE, FONTS
from app.config import get_base_dir
from ui.panel import Panel
from ui.widgets import flat_btn
from dialogs.confirm_dialog import ask_confirm


def _load_banlist() -> List[dict]:
    path = get_base_dir() / "banlist.json"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_banlist(data: List[dict]) -> None:
    path = get_base_dir() / "banlist.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class BanlistDialog(Panel):
    def __init__(self, parent):
        super().__init__(parent, padx=0, pady=0)
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Manage Banlist", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)

        tk.Frame(self, bg=PALETTE["border"], height=1).pack(fill=tk.X)

        cols = tk.Frame(self, bg=PALETTE["card2"], padx=12, pady=4)
        cols.pack(fill=tk.X)
        for col, w in [("Alias", 12), ("UUID", 10), ("Banned At", 20), ("Status", 10), ("", 4)]:
            tk.Label(cols, text=col, bg=PALETTE["card2"],
                     fg=PALETTE["muted"], font=FONTS["small"],
                     width=w, anchor="w").pack(side=tk.LEFT, padx=2)

        self._list_outer = tk.Frame(self, bg=PALETTE["card"],
                                    width=460, height=260)
        self._list_outer.pack(fill=tk.BOTH, padx=0, pady=0)
        self._list_outer.pack_propagate(False)

        self._canvas = tk.Canvas(self._list_outer, bg=PALETTE["card"],
                                 highlightthickness=0)
        vsb = tk.Scrollbar(self._list_outer, orient=tk.VERTICAL,
                           command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, bg=PALETTE["card"])
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))

        tk.Frame(self, bg=PALETTE["border"], height=1).pack(fill=tk.X)
        flat_btn(self, "Close", self.close, style="ghost").pack(pady=10)

        self._refresh()

    def _refresh(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        records = _load_banlist()
        now = datetime.now(timezone.utc)

        for record in records:
            expired = False
            expires = record.get("expires_at")
            if expires:
                try:
                    exp_dt = datetime.fromisoformat(expires)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    expired = now >= exp_dt
                except Exception:
                    pass

            color = PALETTE["muted"] if expired else PALETTE["fg"]
            row_bg = PALETTE["card2"] if not expired else PALETTE["card"]
            row = tk.Frame(self._inner, bg=row_bg, pady=3)
            row.pack(fill=tk.X, padx=8, pady=1)

            alias = record.get("alias", "?")
            uid = record.get("uuid", "")[:8] + "…"
            banned_at = record.get("banned_at", "")[:19]
            status = "(Expired)" if expired else "Active"

            for txt, w in [(alias, 12), (uid, 10), (banned_at, 20), (status, 10)]:
                tk.Label(row, text=txt, bg=row_bg, fg=color,
                         font=FONTS["small"], width=w, anchor="w").pack(side=tk.LEFT, padx=2)

            def _del(r=record):
                if ask_confirm(self, "Remove Ban",
                               f"Remove ban for {r.get('alias', '?')}?"):
                    bl = _load_banlist()
                    bl = [x for x in bl if x.get("uuid") != r.get("uuid")]
                    _save_banlist(bl)
                    self._refresh()

            tk.Button(row, text="🗑", command=_del, bg=PALETTE["danger"],
                      fg="#fff", relief=tk.FLAT, cursor="hand2",
                      font=FONTS["small"]).pack(side=tk.LEFT, padx=2)
