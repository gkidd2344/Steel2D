"""ActionsDialog — view, add and remove player-level actions (K-key hotkey)."""
from __future__ import annotations
import tkinter as tk
from typing import Callable, Optional, TYPE_CHECKING

from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr, styled_entry

if TYPE_CHECKING:
    from game.objects import PlayerObject


# ── tiny buff-hover tooltip (no external dependency) ─────────────────────────

def _bind_buff_tooltip(widget: tk.Widget, buff_def: dict) -> None:
    tip: list = [None]

    def _show(event):
        if tip[0]:
            return
        lines = [buff_def.get("Name", "?")]
        lines.append(f"  Type:  {buff_def.get('Type', '?')}")
        val = buff_def.get("Value", 0)
        sign = "+" if val > 0 else ""
        lines.append(f"  Value: {sign}{val}")
        stat = buff_def.get("Stat")
        if stat:
            lines.append(f"  Stat:  {stat}")
        dur = buff_def.get("Duration", 0)
        if dur and dur < 99999:
            lines.append(f"  Dur:   {int(dur)} min")
        t = tk.Toplevel(widget)
        t.overrideredirect(True)
        t.wm_attributes("-topmost", True)
        t.geometry(f"+{event.x_root + 14}+{event.y_root + 14}")
        tk.Label(t, text="\n".join(lines), bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["small"],
                 justify="left", padx=8, pady=6,
                 relief=tk.SOLID, bd=1).pack()
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


# ── helpers ───────────────────────────────────────────────────────────────────

def _casts_text(adef: dict) -> str:
    casts = adef.get("Casts")
    if not casts:
        return ""
    remaining = casts.get("remaining", 0)
    max_pr = casts.get("max_per_rest", 0)
    return f"{remaining}/{max_pr}"


def _scales_text(adef: dict) -> str:
    sw = adef.get("ScalesWith") or {}
    if not sw:
        return ""
    return ", ".join(f"{stat} ({grade})" for stat, grade in sw.items())


# ── main dialog ───────────────────────────────────────────────────────────────

class ActionsDialog(Panel):
    """Floating panel listing a player's personal Actions with search and CRUD."""

    WIDTH = 540

    def __init__(self, parent, player: "PlayerObject",
                 prefabs: list,
                 on_actions_change: Callable[[Optional[dict]], None]):
        super().__init__(parent, padx=0, pady=0)
        self._player = player
        self._prefabs = prefabs
        self._on_change = on_actions_change
        # Working copy — updated locally and pushed to server on each mutation
        self._actions: dict = dict(player.Actions or {})
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_table())
        self._build()

    # ── layout ───────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Actions — {self._player.Name}",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        # Search bar
        search_row = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=6)
        search_row.pack(fill=tk.X)
        tk.Label(search_row, text="🔍", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"]).pack(side=tk.LEFT, padx=(0, 6))
        styled_entry(search_row, textvariable=self._search_var,
                     width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        hr(self).pack(fill=tk.X)

        # Column header
        col_hdr = tk.Frame(self, bg=PALETTE["bg"], pady=3, padx=12)
        col_hdr.pack(fill=tk.X)
        col_hdr.grid_columnconfigure(0, weight=3)
        col_hdr.grid_columnconfigure(1, weight=4)
        col_hdr.grid_columnconfigure(2, weight=1)
        col_hdr.grid_columnconfigure(3, minsize=28)
        for col_txt, col_i in (("Name", 0), ("Description", 1), ("Casts", 2), ("", 3)):
            tk.Label(col_hdr, text=col_txt, bg=PALETTE["bg"],
                     fg=PALETTE["muted"], font=FONTS["small"],
                     anchor="w", padx=2).grid(row=0, column=col_i, sticky="ew")
        hr(self).pack(fill=tk.X)

        # Scrollable table area
        list_outer = tk.Frame(self, bg=PALETTE["card"], height=240)
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
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(self._win, width=e.width))

        hr(self).pack(fill=tk.X)

        # Footer buttons
        footer = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=8)
        footer.pack(fill=tk.X)
        flat_btn(footer, "＋  Add Action", self._open_add_picker,
                 style="normal").pack(side=tk.LEFT, ipady=3)
        flat_btn(footer, "Close", self.close,
                 style="ghost").pack(side=tk.RIGHT, ipady=3)

        self._refresh_table()

    # ── table rendering ───────────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()

        query = self._search_var.get().lower()
        items = [(name, adef) for name, adef in self._actions.items()
                 if not query
                 or query in name.lower()
                 or query in (adef.get("Description") or "").lower()]

        if not items:
            tk.Label(self._inner, text="No actions." if not query else "No results.",
                     bg=PALETTE["card"], fg=PALETTE["muted"],
                     font=FONTS["body"], pady=20).pack()
            return

        for i, (aname, adef) in enumerate(items):
            row_bg = PALETTE["card"] if i % 2 == 0 else PALETTE["card2"]
            row = tk.Frame(self._inner, bg=row_bg, pady=4, padx=10, cursor="hand2")
            row.pack(fill=tk.X)
            row.grid_columnconfigure(0, weight=3)
            row.grid_columnconfigure(1, weight=4)
            row.grid_columnconfigure(2, weight=1)
            row.grid_columnconfigure(3, minsize=28)

            tk.Label(row, text=aname, bg=row_bg, fg=PALETTE["fg"],
                     font=FONTS["body"], anchor="w", padx=2).grid(
                row=0, column=0, sticky="ew")
            desc = (adef.get("Description") or "")[:60]
            tk.Label(row, text=desc, bg=row_bg, fg=PALETTE["fg_dim"],
                     font=FONTS["small"], anchor="w", padx=2, wraplength=180).grid(
                row=0, column=1, sticky="ew")
            casts_txt = _casts_text(adef)
            tk.Label(row, text=casts_txt, bg=row_bg, fg=PALETTE["fg_dim"],
                     font=FONTS["small"], anchor="w", padx=2).grid(
                row=0, column=2, sticky="ew")
            del_btn = tk.Button(row, text="✕", bg=PALETTE["danger"],
                                fg="#fff", relief=tk.FLAT,
                                font=FONTS["small"], padx=4,
                                cursor="hand2",
                                command=lambda n=aname: self._remove_action(n))
            del_btn.grid(row=0, column=3, padx=(4, 0))

            # Click row (not delete button) → detail view
            def _click_row(event, n=aname, d=adef):
                self._open_detail(n, d)

            def _enter(event, r=row, bg=row_bg):
                r.config(bg=PALETTE["accent"])
                for c in r.grid_slaves():
                    if c is not del_btn:
                        try:
                            c.config(bg=PALETTE["accent"])
                        except Exception:
                            pass

            def _leave(event, r=row, bg=row_bg):
                r.config(bg=bg)
                for c in r.grid_slaves():
                    if c is not del_btn:
                        try:
                            c.config(bg=bg)
                        except Exception:
                            pass

            row.bind("<Button-1>", _click_row)
            row.bind("<Enter>", _enter)
            row.bind("<Leave>", _leave)
            for child in row.grid_slaves():
                if child is not del_btn:
                    child.bind("<Button-1>", _click_row)
                    child.bind("<Enter>", _enter)
                    child.bind("<Leave>", _leave)

    # ── mutation helpers ──────────────────────────────────────────────────────

    def _remove_action(self, action_name: str) -> None:
        self._actions.pop(action_name, None)
        self._on_change(self._actions or None)
        self._refresh_table()

    def _add_action(self, action_name: str, adef: dict) -> None:
        self._actions[action_name] = adef
        self._on_change(self._actions or None)
        self._refresh_table()

    # ── detail view ───────────────────────────────────────────────────────────

    def _open_detail(self, action_name: str, adef: dict) -> None:
        detail = Panel(self.winfo_toplevel(), padx=24, pady=18)

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
                     font=FONTS["body"], anchor="w").pack(side=tk.LEFT)

        desc = adef.get("Description") or "—"
        _row("Description:", desc)
        _row("Range:", f"{adef.get('Range', 1)} tile(s)")
        _row("Base Damage:", str(adef.get("BaseDamage", 0)))
        _row("Hits:", str(adef.get("Hits", 1)))

        casts = adef.get("Casts")
        if casts:
            _row("Casts / rest:", f"{casts.get('remaining', 0)} / {casts.get('max_per_rest', 0)}")

        scales = _scales_text(adef)
        if scales:
            _row("Scales With:", scales)

        buffs = adef.get("GivesBuffs") or []
        if buffs:
            hr(detail).pack(fill=tk.X, pady=6)
            tk.Label(detail, text="Applies Buffs:", bg=PALETTE["card"],
                     fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(anchor="w", pady=(0, 4))
            for buff_def in buffs:
                bname = buff_def.get("Name", "?")
                blbl = tk.Label(detail, text=f"  • {bname}",
                                bg=PALETTE["card"], fg=PALETTE["accent"],
                                font=FONTS["body"], anchor="w", cursor="hand2")
                blbl.pack(anchor="w")
                _bind_buff_tooltip(blbl, buff_def)

        hr(detail).pack(fill=tk.X, pady=8)
        flat_btn(detail, "Close", detail.close, style="ghost").pack(fill=tk.X, ipady=3)

    # ── add-action picker ─────────────────────────────────────────────────────

    def _open_add_picker(self) -> None:
        action_prefabs = [p for p in self._prefabs
                          if p.get("type") == "Action" and p.get("Name")]
        # Sort alphabetically by Name (case-insensitive)
        action_prefabs.sort(key=lambda p: str(p.get("Name", "")).lower())
        if not action_prefabs:
            from tkinter import messagebox
            messagebox.showinfo("No Action Prefabs",
                                "No Action prefabs are loaded.\n"
                                "Create some in the DM Workshop first.",
                                parent=self.winfo_toplevel())
            return

        picker = Panel(self.winfo_toplevel(), padx=0, pady=0)

        hdr = tk.Frame(picker, bg=PALETTE["card"], padx=20, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Add Action", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", picker.close, style="ghost").pack(side=tk.RIGHT)
        hr(picker).pack(fill=tk.X)

        search_var = tk.StringVar()
        search_row = tk.Frame(picker, bg=PALETTE["card"], padx=14, pady=6)
        search_row.pack(fill=tk.X)
        tk.Label(search_row, text="🔍", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"]).pack(side=tk.LEFT, padx=(0, 6))
        styled_entry(search_row, textvariable=search_var,
                     width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        hr(picker).pack(fill=tk.X)

        # Column header
        col_hdr = tk.Frame(picker, bg=PALETTE["bg"], pady=3, padx=12)
        col_hdr.pack(fill=tk.X)
        col_hdr.grid_columnconfigure(0, weight=2)
        col_hdr.grid_columnconfigure(1, weight=4)
        for col_txt, col_i in (("Name", 0), ("Description", 1)):
            tk.Label(col_hdr, text=col_txt, bg=PALETTE["bg"],
                     fg=PALETTE["muted"], font=FONTS["small"],
                     anchor="w", padx=2).grid(row=0, column=col_i, sticky="ew")
        hr(picker).pack(fill=tk.X)

        list_outer = tk.Frame(picker, bg=PALETTE["card"], height=220)
        list_outer.pack(fill=tk.BOTH, expand=True)
        list_outer.pack_propagate(False)

        vsb = tk.Scrollbar(list_outer, bg=PALETTE["card2"],
                           troughcolor=PALETTE["bg"], width=6)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))
        p_canvas = tk.Canvas(list_outer, bg=PALETTE["card"],
                             highlightthickness=0, yscrollcommand=vsb.set)
        p_canvas.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=p_canvas.yview)
        p_inner = tk.Frame(p_canvas, bg=PALETTE["card"])
        p_win = p_canvas.create_window((0, 0), window=p_inner, anchor="nw")
        p_inner.bind("<Configure>",
                     lambda e: p_canvas.configure(
                         scrollregion=p_canvas.bbox("all")))
        p_canvas.bind("<Configure>",
                      lambda e: p_canvas.itemconfig(p_win, width=e.width))

        def _refresh_picker(*_):
            for w in p_inner.winfo_children():
                w.destroy()
            q = search_var.get().lower()
            filtered = [p for p in action_prefabs
                        if not q
                        or q in (p.get("Name") or "").lower()
                        or q in (p.get("Description") or "").lower()]
            if not filtered:
                tk.Label(p_inner, text="No results.", bg=PALETTE["card"],
                         fg=PALETTE["muted"], font=FONTS["body"], pady=20).pack()
                return
            for j, prefab in enumerate(filtered):
                pname = prefab.get("Name", "?")
                pdesc = (prefab.get("Description") or "")[:70]
                # Build action def (everything except type, id, Name)
                pdef = {k: v for k, v in prefab.items()
                        if k not in ("type", "id", "Name")}
                row_bg = PALETTE["card"] if j % 2 == 0 else PALETTE["card2"]
                row = tk.Frame(p_inner, bg=row_bg, pady=5, padx=10, cursor="hand2")
                row.pack(fill=tk.X)
                row.grid_columnconfigure(0, weight=2)
                row.grid_columnconfigure(1, weight=4)
                tk.Label(row, text=pname, bg=row_bg, fg=PALETTE["fg"],
                         font=FONTS["body"], anchor="w", padx=2).grid(
                    row=0, column=0, sticky="ew")
                tk.Label(row, text=pdesc, bg=row_bg, fg=PALETTE["fg_dim"],
                         font=FONTS["small"], anchor="w", padx=2,
                         wraplength=200).grid(row=0, column=1, sticky="ew")

                def _pick(n=pname, d=pdef):
                    # Check if already assigned
                    if n in self._actions:
                        from tkinter import messagebox
                        if not messagebox.askyesno(
                                "Already Assigned",
                                f'"{n}" is already in your actions. Overwrite?',
                                parent=picker.winfo_toplevel()):
                            return
                    self._add_action(n, d)
                    picker.close()

                def _enter(event, r=row, bg=row_bg):
                    r.config(bg=PALETTE["accent"])
                    for c in r.grid_slaves():
                        try:
                            c.config(bg=PALETTE["accent"])
                        except Exception:
                            pass

                def _leave(event, r=row, bg=row_bg):
                    r.config(bg=bg)
                    for c in r.grid_slaves():
                        try:
                            c.config(bg=bg)
                        except Exception:
                            pass

                row.bind("<Button-1>", lambda e, fn=_pick: fn())
                row.bind("<Enter>", _enter)
                row.bind("<Leave>", _leave)
                for child in row.grid_slaves():
                    child.bind("<Button-1>", lambda e, fn=_pick: fn())
                    child.bind("<Enter>", _enter)
                    child.bind("<Leave>", _leave)

        search_var.trace_add("write", _refresh_picker)
        _refresh_picker()

        hr(picker).pack(fill=tk.X)
        flat_btn(picker, "Cancel", picker.close,
                 style="ghost").pack(padx=14, pady=8, ipady=3, fill=tk.X)
