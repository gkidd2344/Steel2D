"""
DM Workshop screen — accessible from the main menu by any player.

Landing: Create / Load Prefab Objects / Back
Builder: left form | right table | bottom bar (Save / Exit)
"""
from __future__ import annotations
import json
import re as _re
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, List

import tkinter as tk
from tkinter import ttk, messagebox

from app.constants import PALETTE, FONTS
from app.config import get_prefabs_dir, STAT_KEYS, SCALAR_WEIGHT_LOOKUP
from ui.widgets import flat_btn, hr, styled_entry, styled_check
from game.objects import BUFF_TYPES


# ── helpers ────────────────────────────────────────────────────────────────────

def _sanitize(name: str) -> str:
    return _re.sub(r"[^A-Za-z0-9_\- ]", "_", name).strip() or "prefab"


def _save_prefab_file(name: str, objects: List[dict]) -> Path:
    path = get_prefabs_dir() / f"{_sanitize(name)}.json"
    data = {
        "name": name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "objects": objects,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def _load_prefab_file(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_all_action_prefabs() -> List[dict]:
    """Load Action-type objects from every prefab file in the prefabs directory."""
    result = []
    for path in sorted(get_prefabs_dir().glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for obj in data.get("objects", []):
                if obj.get("type") == "Action":
                    result.append(dict(obj))
        except Exception:
            pass
    return result


# Column spec — shared between header and data rows for exact alignment
_COLS = [("Name", 18), ("Type", 8), ("Description", 24)]


# ── DmToolScreen ──────────────────────────────────────────────────────────────

class DmToolScreen(tk.Frame):
    def __init__(self, parent, on_exit: Callable, **kwargs):
        super().__init__(parent, bg=PALETTE["bg"], **kwargs)
        self._on_exit = on_exit
        self._show_landing()

    def _clear(self) -> None:
        for w in self.winfo_children():
            w.destroy()

    # ── landing ───────────────────────────────────────────────────────────────

    def _show_landing(self) -> None:
        self._clear()
        card = tk.Frame(self, bg=PALETTE["card"], padx=52, pady=40)
        card.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(card, text="DM Workshop", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["title"]).pack()
        tk.Label(card, text="Create and manage prefab object libraries",
                 bg=PALETTE["card"], fg=PALETTE["muted"],
                 font=FONTS["small"]).pack(pady=(2, 10))
        hr(card).pack(fill=tk.X, pady=8)

        flat_btn(card, "✚  Create Prefab Objects",
                 self._open_new_builder, style="normal").pack(
            fill=tk.X, pady=4, ipady=8)
        flat_btn(card, "📂  Load Prefab Objects",
                 self._open_load_dialog, style="ghost").pack(
            fill=tk.X, pady=4, ipady=8)
        hr(card).pack(fill=tk.X, pady=8)
        flat_btn(card, "← Back to Menu",
                 self._on_exit, style="muted").pack(fill=tk.X, ipady=5)

    def _open_new_builder(self) -> None:
        self._show_builder(objects=[], file_name=None)

    def _open_load_dialog(self) -> None:
        from dialogs.prefab_load_dialog import PrefabLoadDialog
        PrefabLoadDialog(self, on_load=self._load_and_open)

    def _load_and_open(self, path: Path) -> None:
        try:
            data = _load_prefab_file(path)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        self._show_builder(
            objects=list(data.get("objects", [])),
            file_name=data.get("name", path.stem),
        )

    # ── builder ───────────────────────────────────────────────────────────────

    def _show_builder(self, objects: List[dict], file_name: Optional[str]) -> None:
        self._clear()
        self._objects: List[dict] = list(objects)
        self._file_name: Optional[str] = file_name

        # 1) Header — TOP
        hdr = tk.Frame(self, bg=PALETTE["card2"], height=44)
        hdr.pack(side=tk.TOP, fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Prefab Builder",
                 bg=PALETTE["card2"], fg=PALETTE["fg"],
                 font=FONTS["heading"], padx=20).pack(side=tk.LEFT, pady=6)
        if file_name:
            tk.Label(hdr, text=f"— {file_name}",
                     bg=PALETTE["card2"], fg=PALETTE["muted"],
                     font=FONTS["body"]).pack(side=tk.LEFT)

        # 2) Bottom bar — BOTTOM (before content so expand leaves room)
        hr(self).pack(side=tk.BOTTOM, fill=tk.X)
        bar = tk.Frame(self, bg=PALETTE["card2"], height=54)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)
        btn_frame = tk.Frame(bar, bg=PALETTE["card2"])
        btn_frame.pack(side=tk.RIGHT, padx=20, pady=8)
        flat_btn(btn_frame, "💾  Save Prefabs",
                 self._do_save, style="success").pack(
            side=tk.LEFT, padx=(0, 12), ipadx=10, ipady=4)
        flat_btn(btn_frame, "✕  Exit Prefab Builder",
                 self._confirm_exit, style="danger").pack(
            side=tk.LEFT, ipadx=10, ipady=4)

        # 3) Content — fills remaining middle
        content = tk.Frame(self, bg=PALETTE["bg"])
        content.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=10)

        left = tk.Frame(content, bg=PALETTE["card"],
                        highlightthickness=1,
                        highlightbackground=PALETTE["border"])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        right = tk.Frame(content, bg=PALETTE["card"],
                         highlightthickness=1,
                         highlightbackground=PALETTE["border"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        self._build_spawn_panel(left)
        self._build_object_table(right)

    # ── left panel: spawn form ─────────────────────────────────────────────────

    def _build_spawn_panel(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="Add Object to Prefabs",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["heading"], padx=14, pady=10).pack(anchor="w")
        hr(parent).pack(fill=tk.X)
        form = _EmbeddedSpawnForm(
            parent,
            on_add=self._on_add_object,
            get_session_objects=lambda: self._objects,
        )
        form.pack(fill=tk.BOTH, expand=True)

    def _on_add_object(self, obj_dict: dict) -> None:
        obj_dict["id"] = str(_uuid.uuid4())
        self._objects.append(obj_dict)
        self._refresh_table()

    # ── right panel: object table ──────────────────────────────────────────────

    def _build_object_table(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="Prefab Objects",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["heading"], padx=14, pady=10).pack(anchor="w")
        hr(parent).pack(fill=tk.X)

        # Header row — darker bg, bold white, exactly matching _COLS widths
        col_hdr = tk.Frame(parent, bg=PALETTE["bg"], padx=6, pady=5)
        col_hdr.pack(fill=tk.X)
        for col, w in _COLS:
            tk.Label(col_hdr, text=col, bg=PALETTE["bg"],
                     fg="#ffffff", font=FONTS["form_label"],
                     width=w, anchor="w").pack(side=tk.LEFT, padx=2)
        # Reserve space for the × delete button column
        tk.Label(col_hdr, text="", bg=PALETTE["bg"],
                 width=3).pack(side=tk.LEFT)

        list_outer = tk.Frame(parent, bg=PALETTE["card"])
        list_outer.pack(fill=tk.BOTH, expand=True)

        vsb = tk.Scrollbar(list_outer, bg=PALETTE["card2"],
                           troughcolor=PALETTE["bg"], width=6)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))   # slight inset

        self._tbl_canvas = tk.Canvas(list_outer, bg=PALETTE["card"],
                                     highlightthickness=0,
                                     yscrollcommand=vsb.set)
        self._tbl_canvas.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._tbl_canvas.yview)

        self._tbl_inner = tk.Frame(self._tbl_canvas, bg=PALETTE["card"])
        _win = self._tbl_canvas.create_window(
            (0, 0), window=self._tbl_inner, anchor="nw")
        self._tbl_inner.bind("<Configure>", lambda e:
                             self._tbl_canvas.configure(
                                 scrollregion=self._tbl_canvas.bbox("all")))
        self._tbl_canvas.bind("<Configure>", lambda e:
                              self._tbl_canvas.itemconfig(
                                  _win, width=e.width - 8))
        self._tbl_canvas.bind("<MouseWheel>", lambda e:
                              self._tbl_canvas.yview_scroll(
                                  int(-1 * (e.delta / 120)), "units"))

        self._row_frames: List[tk.Frame] = []
        self._refresh_table()

    def _refresh_table(self) -> None:
        if not hasattr(self, "_tbl_inner"):
            return
        for w in self._tbl_inner.winfo_children():
            w.destroy()
        self._row_frames = []

        if not self._objects:
            tk.Label(self._tbl_inner, text="No objects added yet.",
                     bg=PALETTE["card"], fg=PALETTE["muted"],
                     font=FONTS["body"], pady=20).pack()
            return

        for i, obj in enumerate(self._objects):
            bg = PALETTE["card2"] if i % 2 == 0 else PALETTE["card"]
            row = tk.Frame(self._tbl_inner, bg=bg, cursor="hand2", pady=4)
            row.pack(fill=tk.X)
            self._row_frames.append(row)

            name = str(obj.get("Name", obj.get("type", "?")))
            otype = str(obj.get("type", "?"))
            desc = str(obj.get("Description", ""))
            for val, w in _COLS:
                # truncate to column width (approx char budget)
                display = locals()[val.lower().replace(" ", "")][:w]
                tk.Label(row, text=display, bg=bg, fg=PALETTE["fg"],
                         font=FONTS["body"], width=w,
                         anchor="w", padx=6).pack(side=tk.LEFT)

            tk.Button(row, text="×", bg=PALETTE["danger"], fg="#fff",
                      relief=tk.FLAT, font=FONTS["small"], cursor="hand2",
                      command=lambda idx=i: self._delete_object(idx),
                      padx=4).pack(side=tk.RIGHT, padx=4)

            def _click(e, idx=i):
                self._edit_object(idx)
            row.bind("<Button-1>", _click)
            for child in row.winfo_children():
                if not isinstance(child, tk.Button):
                    child.bind("<Button-1>", _click)

    def _delete_object(self, idx: int) -> None:
        if 0 <= idx < len(self._objects):
            self._objects.pop(idx)
            self._refresh_table()

    def _edit_object(self, idx: int) -> None:
        obj = self._objects[idx]
        from game.objects import occupant_from_dict
        from dialogs.spawn_object_dialog import SpawnObjectDialog

        action_pf = _load_all_action_prefabs()

        if obj.get("type") == "Action":
            self._edit_action_prefab(idx, obj)
            return

        existing = occupant_from_dict(obj)

        def _on_save(new_dict: dict) -> None:
            new_dict["id"] = obj.get("id", str(_uuid.uuid4()))
            self._objects[idx] = new_dict
            self._refresh_table()

        SpawnObjectDialog(
            self, on_spawn=_on_save,
            existing=existing, title="Modify Prefab Object",
            prefabs=action_pf,
        )

    def _edit_action_prefab(self, idx: int, obj: dict) -> None:
        """Open a simple editor for a standalone Action prefab."""
        def _on_save(new_obj: dict) -> None:
            new_obj["id"] = obj.get("id", str(_uuid.uuid4()))
            self._objects[idx] = new_obj
            self._refresh_table()

        _ActionPrefabEditor(self, obj, on_save=_on_save,
                            get_session_objects=lambda: self._objects)

    # ── save / exit ───────────────────────────────────────────────────────────

    def _do_save(self) -> None:
        if self._file_name:
            _save_prefab_file(self._file_name, self._objects)
            messagebox.showinfo("Saved", f'Saved as "{self._file_name}".')
        else:
            self._prompt_save_name()

    def _prompt_save_name(self) -> None:
        from ui.panel import Panel
        panel = Panel(self, padx=28, pady=20)
        tk.Label(panel, text="Name this prefab set", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 10))
        name_var = tk.StringVar()
        styled_entry(panel, textvariable=name_var, width=26).pack(pady=(0, 10))

        def _confirm():
            name = name_var.get().strip()
            if not name:
                return
            self._file_name = name
            _save_prefab_file(name, self._objects)
            panel.close()
            messagebox.showinfo("Saved", f'Saved as "{name}".')

        flat_btn(panel, "Save", _confirm, style="success").pack(fill=tk.X, ipady=4)

    def _confirm_exit(self) -> None:
        from ui.panel import Panel
        panel = Panel(self, padx=32, pady=24)
        tk.Label(
            panel,
            text="Would you like to exit?\nAnything not saved will be lost.",
            bg=PALETTE["card"], fg=PALETTE["fg"],
            font=FONTS["body"], justify="center", wraplength=300,
        ).pack(pady=(0, 18))
        btn_row = tk.Frame(panel, bg=PALETTE["card"])
        btn_row.pack()
        flat_btn(btn_row, "Exit",
                 lambda: (panel.close(), self._on_exit()),
                 style="danger").pack(side=tk.LEFT, padx=(0, 10), ipadx=10, ipady=4)
        flat_btn(btn_row, "Go Back",
                 panel.close, style="normal").pack(side=tk.LEFT, ipadx=10, ipady=4)


# ── Shared Action form builder (used by _EmbeddedSpawnForm and editor) ────────

def _sp_widget(parent, var, mn, mx, w=7, bg=None):
    return tk.Spinbox(parent, from_=mn, to=mx, textvariable=var, width=w,
                      bg=PALETTE["card2"], fg="#ffffff",
                      insertbackground="#ffffff",
                      relief=tk.FLAT, bd=0,
                      buttonbackground=PALETTE["muted"])


def _add_buff_entry(list_frame: tk.Frame, buff_rows: list,
                     bg: str, prefill: dict = None) -> None:
    """Append one buff entry row to list_frame and buff_rows."""
    p = prefill or {}
    bv = {
        "name":     tk.StringVar(value=p.get("Name", "")),
        "type":     tk.StringVar(value=p.get("Type", list(BUFF_TYPES)[0])),
        "stat":     tk.StringVar(value=p.get("Stat", list(STAT_KEYS)[0])),
        "value":    tk.IntVar(value=p.get("Value", 1)),
        "duration": tk.IntVar(value=int(p.get("Duration", 1))),
    }
    buff_rows.append(bv)

    row_bg = PALETTE["card2"] if bg == PALETTE["card"] else PALETTE["card"]
    row_f = tk.Frame(list_frame, bg=row_bg, pady=3, padx=4,
                     highlightthickness=1,
                     highlightbackground=PALETTE["border"])
    row_f.pack(fill=tk.X, pady=2)
    bv["frame"] = row_f

    # Row A: Name + Type + delete
    ra = tk.Frame(row_f, bg=row_bg)
    ra.pack(fill=tk.X)
    tk.Label(ra, text="Name", bg=row_bg, fg="#ffffff",
             font=FONTS["small"]).pack(side=tk.LEFT, padx=(0, 2))
    styled_entry(ra, textvariable=bv["name"], width=12).pack(side=tk.LEFT, padx=(0, 8))
    tk.Label(ra, text="Type", bg=row_bg, fg="#ffffff",
             font=FONTS["small"]).pack(side=tk.LEFT, padx=(0, 2))
    type_cb = ttk.Combobox(ra, textvariable=bv["type"],
                            values=list(BUFF_TYPES), state="readonly", width=16)
    type_cb.pack(side=tk.LEFT, padx=2)
    def _rm(r=row_f, bvv=bv):
        buff_rows.remove(bvv)
        r.destroy()
    tk.Button(ra, text="×", command=_rm, bg=PALETTE["danger"], fg="#fff",
              relief=tk.FLAT, font=FONTS["small"], padx=3,
              cursor="hand2").pack(side=tk.RIGHT, padx=2)

    # Row B: Stat (conditional) + Value + Duration
    rb = tk.Frame(row_f, bg=row_bg)
    rb.pack(fill=tk.X, pady=(2, 0))
    stat_lbl = tk.Label(rb, text="Stat", bg=row_bg, fg="#ffffff", font=FONTS["small"])
    stat_cb  = ttk.Combobox(rb, textvariable=bv["stat"],
                             values=list(STAT_KEYS), state="readonly", width=6)

    def _update_stat(*_):
        if bv["type"].get() == "Stat Modifier":
            stat_lbl.pack(side=tk.LEFT, padx=(0, 2))
            stat_cb.pack(side=tk.LEFT, padx=(0, 8))
        else:
            stat_lbl.pack_forget()
            stat_cb.pack_forget()
    bv["type"].trace_add("write", _update_stat)
    _update_stat()

    for label, var, mn, mx, w in [
        ("Value",   bv["value"],    -9999, 9999, 6),
        ("Dur(min)", bv["duration"],    0, 9999, 5),
    ]:
        tk.Label(rb, text=label, bg=row_bg, fg="#ffffff",
                 font=FONTS["small"]).pack(side=tk.LEFT, padx=(0, 2))
        _sp_widget(rb, var, mn, mx, w).pack(side=tk.LEFT, padx=(0, 6))


def _build_action_flat_form(parent: tk.Frame, bg: str,
                            prefill: dict = None,
                            get_session_objects: "Callable" = None) -> dict:
    """
    Flat action form mirroring NPC/Item action row layout.
    Returns a variable dict for use with _collect_action_flat().
    """
    p = prefill or {}
    casts_p = p.get("Casts") or {}
    sw_p    = p.get("ScalesWith") or {}

    v = {
        "name":        tk.StringVar(value=p.get("Name", "")),
        "desc_widget": None,
        "desc_init":   p.get("Description", ""),
        "range":       tk.IntVar(value=p.get("Range", 1)),
        "damage":      tk.IntVar(value=p.get("BaseDamage", 0)),
        "hits":        tk.IntVar(value=p.get("Hits", 1)),
        "has_casts":   tk.BooleanVar(value=bool(casts_p)),
        "casts_max":   tk.IntVar(value=casts_p.get("max_per_rest", 3)),
        "casts_rem":   tk.IntVar(value=casts_p.get("remaining", 3)),
        "has_buffs":   tk.BooleanVar(value=bool(
            p.get("GivesBuffs") or p.get("GivesBuff"))),
        "buff_rows":   [],   # list of bv dicts from _add_buff_entry
        "has_scales":  tk.BooleanVar(value=bool(sw_p)),
        "scales_with": {k: tk.StringVar(value=sw_p.get(k, "")) for k in STAT_KEYS},
    }

    def _lbl(r, text, anchor="e"):
        tk.Label(r, text=text, bg=bg, fg="#ffffff",
                 font=FONTS["form_label"], anchor=anchor,
                 width=14).pack(side=tk.LEFT, padx=(0, 6))

    # ── Name ──────────────────────────────────────────────────────────────────
    nr = tk.Frame(parent, bg=bg); nr.pack(fill=tk.X, pady=2)
    _lbl(nr, "Name *")
    styled_entry(nr, textvariable=v["name"],
                 width=22).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ── Description ───────────────────────────────────────────────────────────
    dr = tk.Frame(parent, bg=bg); dr.pack(fill=tk.X, pady=2)
    _lbl(dr, "Description", anchor="nw")
    desc_txt = tk.Text(dr, height=2, width=24,
                        bg=PALETTE["card2"], fg="#ffffff",
                        insertbackground="#ffffff",
                        relief=tk.FLAT, bd=1,
                        highlightthickness=1,
                        highlightbackground=PALETTE["border"])
    desc_txt.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
    if p.get("Description"):
        desc_txt.insert("1.0", p["Description"])
    v["desc_widget"] = desc_txt

    # ── Range / Dmg / Hits ────────────────────────────────────────────────────
    for label, var, mn, mx in [
        ("Range", v["range"],  0, 99),
        ("Dmg",   v["damage"], -99999, 99999),
        ("Hits",  v["hits"],   1, 99),
    ]:
        r = tk.Frame(parent, bg=bg); r.pack(fill=tk.X, pady=2)
        _lbl(r, label)
        _sp_widget(r, var, mn, mx).pack(side=tk.LEFT)

    # ── Limited Uses ──────────────────────────────────────────────────────────
    co = tk.Frame(parent, bg=bg); co.pack(fill=tk.X, pady=(6, 0))
    cc = tk.Frame(co, bg=bg);     cc.pack(fill=tk.X)
    cs = tk.Frame(co, bg=bg)
    def _tog_c():
        (cs.pack if v["has_casts"].get() else cs.pack_forget)(fill=tk.X, pady=(2, 0))
    styled_check(cc, "Limited Uses (Casts)", v["has_casts"],
                 command=_tog_c, bg=bg).pack(side=tk.LEFT, padx=4)
    for lbl, var in [("Max/rest", v["casts_max"]), ("Remaining", v["casts_rem"])]:
        tk.Label(cs, text=lbl, bg=bg, fg="#ffffff",
                 font=FONTS["form_label"]).pack(side=tk.LEFT, padx=(8, 2))
        _sp_widget(cs, var, 0, 99, 4).pack(side=tk.LEFT, padx=1)
    if v["has_casts"].get():
        cs.pack(fill=tk.X, pady=(2, 0))

    # ── Applies Buffs (multi-buff list) ───────────────────────────────────────
    bo = tk.Frame(parent, bg=bg); bo.pack(fill=tk.X, pady=(4, 0))
    bc = tk.Frame(bo, bg=bg);     bc.pack(fill=tk.X)
    bs = tk.Frame(bo, bg=bg)
    buff_list = tk.Frame(bs, bg=bg); buff_list.pack(fill=tk.X)

    # Pre-fill existing buffs
    for bdef in (p.get("GivesBuffs") or []):
        _add_buff_entry(buff_list, v["buff_rows"], bg, bdef)
    if p.get("GivesBuff") and not p.get("GivesBuffs"):
        _add_buff_entry(buff_list, v["buff_rows"], bg, {
            "Name": p.get("BuffName", ""),
            "Type": "Stat Modifier",
            "Value": p.get("BuffValue", 1),
            "Duration": p.get("BuffDuration", 5),
        })

    add_r = tk.Frame(bs, bg=bg); add_r.pack(anchor="w", pady=(4, 0))
    flat_btn(add_r, "+  New Buff",
             lambda: _add_buff_entry(buff_list, v["buff_rows"], bg),
             style="ghost").pack(side=tk.LEFT, padx=(0, 6))

    def _pick_prefab_buff():
        # Session buffs (created this session, not yet saved to disk)
        sess = get_session_objects() if get_session_objects else []
        sess_buffs = [x for x in sess if x.get("type") == "Buff"]
        # Disk buffs (from saved prefab files)
        disk_buffs = [x for x in _load_all_action_prefabs() if x.get("type") == "Buff"]
        # Merge: prefer session copies; avoid duplicating same Name
        sess_names = {b.get("Name", "") for b in sess_buffs}
        all_buffs = sess_buffs + [d for d in disk_buffs
                                   if d.get("Name", "") not in sess_names]
        if not all_buffs:
            messagebox.showinfo("No Buff Prefabs",
                                "No Buff-type objects found in this session or on disk.")
            return
        from dialogs.spawn_prefab_dialog import SpawnPrefabDialog
        SpawnPrefabDialog(bo, prefabs=all_buffs,
                          on_spawn=lambda bd: _add_buff_entry(
                              buff_list, v["buff_rows"], bg, bd))
    flat_btn(add_r, "+  Prefab Buff", _pick_prefab_buff,
             style="muted").pack(side=tk.LEFT)

    def _tog_b():
        (bs.pack if v["has_buffs"].get() else bs.pack_forget)(fill=tk.X, pady=(2, 0))
    styled_check(bc, "Applies Buffs", v["has_buffs"],
                 command=_tog_b, bg=bg).pack(side=tk.LEFT, padx=4)
    if v["has_buffs"].get():
        bs.pack(fill=tk.X, pady=(2, 0))

    # ── Scales With Stat ──────────────────────────────────────────────────────
    so = tk.Frame(parent, bg=bg); so.pack(fill=tk.X, pady=(4, 0))
    sc = tk.Frame(so, bg=bg);     sc.pack(fill=tk.X)
    ss = tk.Frame(so, bg=bg)
    def _tog_s():
        (ss.pack if v["has_scales"].get() else ss.pack_forget)(fill=tk.X, pady=(2, 0))
    styled_check(sc, "Scales With Stat", v["has_scales"],
                 command=_tog_s, bg=bg).pack(side=tk.LEFT, padx=4)
    for k in STAT_KEYS:
        cf = tk.Frame(ss, bg=bg); cf.pack(side=tk.LEFT, padx=(4, 2))
        tk.Label(cf, text=k, bg=bg, fg="#ffffff",
                 font=FONTS["small"]).pack(side=tk.LEFT)
        ttk.Combobox(cf, textvariable=v["scales_with"][k],
                     values=[""] + list(SCALAR_WEIGHT_LOOKUP.keys()),
                     state="readonly", width=4).pack(side=tk.LEFT, padx=1)
    if v["has_scales"].get():
        ss.pack(fill=tk.X, pady=(2, 0))

    return v


def _collect_action_flat(v: dict, existing_id: str = None) -> dict:
    """Assemble an Action prefab dict from variables returned by _build_action_flat_form."""
    desc_w = v.get("desc_widget")
    desc   = desc_w.get("1.0", "end-1c") if desc_w else v.get("desc_init", "")
    result = {
        "type":        "Action",
        "id":          existing_id or str(_uuid.uuid4()),
        "Name":        v["name"].get().strip() or "Action",
        "Description": desc,
        "Range":       v["range"].get(),
        "BaseDamage":  v["damage"].get(),
        "Hits":        v["hits"].get(),
    }
    if v["has_casts"].get():
        result["Casts"] = {
            "max_per_rest": v["casts_max"].get(),
            "remaining":    v["casts_rem"].get(),
        }
    if v["has_buffs"].get():
        gives = []
        for bv in v.get("buff_rows", []):
            bd = {
                "Name":     bv["name"].get().strip(),
                "Type":     bv["type"].get(),
                "Value":    bv["value"].get(),
                "Duration": bv["duration"].get(),
            }
            if bd["Type"] == "Stat Modifier":
                bd["Stat"] = bv["stat"].get()
            if bd["Name"]:
                gives.append(bd)
        if gives:
            result["GivesBuffs"] = gives
    if v["has_scales"].get():
        sw = {k: var.get() for k, var in v["scales_with"].items() if var.get()}
        if sw:
            result["ScalesWith"] = sw
    return result


# ── Standalone Action Prefab Editor ──────────────────────────────────────────

class _ActionPrefabEditor:
    """Panel editor for an existing Action prefab — mirrors the action row form."""

    def __init__(self, parent, obj: dict, on_save: Callable,
                 get_session_objects: "Callable" = None):
        from ui.panel import Panel
        self._panel = Panel(parent, padx=0, pady=0)
        self._obj = obj
        self._on_save = on_save
        self._get_session_objects = get_session_objects
        self._vars: dict = {}
        self._build()

    def _build(self) -> None:
        p = self._panel
        hdr = tk.Frame(p, bg=PALETTE["card"], padx=14, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Edit Action Prefab", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self._panel.close, style="ghost").pack(side=tk.RIGHT)
        hr(p).pack(fill=tk.X)

        form = tk.Frame(p, bg=PALETTE["card"], padx=16, pady=10)
        form.pack(fill=tk.X)

        # Build the flat form pre-filled with existing data
        self._vars = _build_action_flat_form(
            form, PALETTE["card"], prefill=self._obj,
            get_session_objects=self._get_session_objects)

        hr(p).pack(fill=tk.X)
        btn_row = tk.Frame(p, bg=PALETTE["card"], padx=14, pady=8)
        btn_row.pack(fill=tk.X)
        flat_btn(btn_row, "Save", self._save, style="success").pack(
            side=tk.LEFT, padx=(0, 8), ipadx=8)
        flat_btn(btn_row, "Cancel", self._panel.close, style="ghost").pack(side=tk.LEFT)

    def _save(self) -> None:
        result = _collect_action_flat(self._vars,
                                       existing_id=self._obj.get("id"))
        self._panel.close()
        self._on_save(result)


# ── Embedded spawn form ────────────────────────────────────────────────────────

class _EmbeddedSpawnForm(tk.Frame):
    """
    SpawnObjectDialog form logic reused inside a plain Frame.
    Type selector includes NPC, Item, and Action (prefab-only).
    """

    def __init__(self, parent: tk.Frame, on_add: Callable,
                 get_session_objects: "Callable" = None, **kwargs):
        super().__init__(parent, bg=PALETTE["card"], **kwargs)
        self._on_add = on_add
        self._get_session_objects = get_session_objects or (lambda: [])
        self._type_var = tk.StringVar(value="NPC")
        self._err_var = tk.StringVar()
        self._action_rows: list = []
        self._settings = None
        self._existing = None
        self._prefabs: list = _load_all_action_prefabs()
        self._build()

    def _build(self) -> None:
        type_row = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=6)
        type_row.pack(fill=tk.X)
        for t in ("NPC", "Item", "Action", "Buff"):
            tk.Radiobutton(
                type_row, text=t, variable=self._type_var, value=t,
                bg=PALETTE["card"], fg=PALETTE["fg"],
                font=FONTS["form_label"],
                selectcolor=PALETTE["accent"],
                activebackground=PALETTE["card"],
                command=self._on_type_change,
            ).pack(side=tk.LEFT, padx=10)
        hr(self).pack(fill=tk.X)

        # Scrollable body — _body_frame is the name expected by SpawnObjectDialog
        self._scroll_canvas = tk.Canvas(
            self, bg=PALETTE["card"], highlightthickness=0)
        vsb = tk.Scrollbar(self, orient="vertical",
                            command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._scroll_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Bind scroll on the canvas itself
        self._scroll_canvas.bind(
            "<MouseWheel>",
            lambda e: self._scroll_canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"))

        self._body_frame = tk.Frame(self._scroll_canvas, bg=PALETTE["card"])
        self._canvas_window = self._scroll_canvas.create_window(
            (0, 0), window=self._body_frame, anchor="nw")
        self._body_frame.bind("<Configure>", self._on_body_configure)
        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)

        hr(self).pack(fill=tk.X)
        tk.Label(self, textvariable=self._err_var, bg=PALETTE["card"],
                 fg=PALETTE["danger"], font=FONTS["small"]).pack()
        flat_btn(self, "✚  Add to Prefabs", self._do_add, style="normal").pack(
            pady=8, ipadx=14, ipady=5)

        self._render_body()

    def _on_body_configure(self, event=None) -> None:
        self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all"))

    def _on_canvas_configure(self, event=None) -> None:
        self._scroll_canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_type_change(self) -> None:
        self.after_idle(self._render_body)

    # Override _render_body to handle Action type and bind scroll to children
    def _render_body(self) -> None:
        for w in self._body_frame.winfo_children():
            w.destroy()
        self._action_rows = []
        t = self._type_var.get()
        if t == "NPC":
            self._build_npc_form()
        elif t == "Item":
            self._build_item_form()
        elif t == "Action":
            self._build_action_form()
        else:
            self._build_buff_form_embedded()
        self._update_scroll()
        self.after_idle(lambda: self._bind_scroll_children(self._body_frame))

    def _bind_scroll_children(self, widget) -> None:
        """Propagate MouseWheel from any child up to the scroll canvas."""
        try:
            widget.bind("<MouseWheel>",
                        lambda e: self._scroll_canvas.yview_scroll(
                            int(-1 * (e.delta / 120)), "units"), "+")
            for child in widget.winfo_children():
                self._bind_scroll_children(child)
        except Exception:
            pass

    # ── Action form (standalone Action prefab) ───────────────────────────────

    def _build_action_form(self) -> None:
        """Flat form matching NPC/Item action row layout — no collapsible sections."""
        f = tk.Frame(self._body_frame, bg=PALETTE["card"], padx=10, pady=6)
        f.pack(fill=tk.X)
        self._action_vars = _build_action_flat_form(
            f, PALETTE["card"],
            get_session_objects=self._get_session_objects)

    def _build_action_result(self) -> Optional[dict]:
        v = self._action_vars
        if not v["name"].get().strip():
            self._err_var.set("Name is required.")
            return None
        return _collect_action_flat(v)

    # ── Buff form (standalone Buff prefab) ───────────────────────────────────

    def _build_buff_form_embedded(self) -> None:
        f = tk.Frame(self._body_frame, bg=PALETTE["card"], padx=10, pady=8)
        f.pack(fill=tk.X)

        self._buff_name_var     = tk.StringVar()
        self._buff_desc_var     = tk.StringVar()
        self._buff_type_var     = tk.StringVar(value=list(BUFF_TYPES)[0])
        self._buff_stat_var     = tk.StringVar(value=list(STAT_KEYS)[0])
        self._buff_value_var    = tk.IntVar(value=1)
        self._buff_duration_var = tk.IntVar(value=1)

        def _frow(label, factory):
            r = tk.Frame(f, bg=PALETTE["card"])
            r.pack(fill=tk.X, pady=3)
            self._lbl(r, label).pack(side=tk.LEFT, padx=(0, 6))
            factory(r)

        _frow("Name *",      lambda r: styled_entry(r, textvariable=self._buff_name_var,
                                                     width=22).pack(side=tk.LEFT))
        _frow("Description", lambda r: styled_entry(r, textvariable=self._buff_desc_var,
                                                     width=22).pack(side=tk.LEFT))

        # Type
        type_row = tk.Frame(f, bg=PALETTE["card"]); type_row.pack(fill=tk.X, pady=3)
        self._lbl(type_row, "Type").pack(side=tk.LEFT, padx=(0, 6))
        type_cb = ttk.Combobox(type_row, textvariable=self._buff_type_var,
                                values=list(BUFF_TYPES), state="readonly", width=20)
        type_cb.pack(side=tk.LEFT)

        # Stat (only for Stat Modifier)
        stat_row = tk.Frame(f, bg=PALETTE["card"]); stat_row.pack(fill=tk.X, pady=3)
        self._lbl(stat_row, "Stat").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Combobox(stat_row, textvariable=self._buff_stat_var,
                     values=list(STAT_KEYS), state="readonly", width=8).pack(side=tk.LEFT)

        def _update_stat(*_):
            if self._buff_type_var.get() == "Stat Modifier":
                stat_row.pack(fill=tk.X, pady=3)
            else:
                stat_row.pack_forget()
            self.after_idle(self._update_scroll)
        self._buff_type_var.trace_add("write", _update_stat)
        _update_stat()

        def _sp_row(lbl, var, mn, mx):
            r = tk.Frame(f, bg=PALETTE["card"]); r.pack(fill=tk.X, pady=3)
            self._lbl(r, lbl).pack(side=tk.LEFT, padx=(0, 6))
            _sp_widget(r, var, mn, mx, w=8).pack(side=tk.LEFT)
        _sp_row("Value",        self._buff_value_var,    -9999, 9999)
        _sp_row("Duration(min)", self._buff_duration_var,    0, 9999)

    def _build_buff_result(self) -> Optional[dict]:
        name = self._buff_name_var.get().strip()
        if not name:
            self._err_var.set("Name is required.")
            return None
        result = {
            "type":        "Buff",
            "id":          str(_uuid.uuid4()),
            "Name":        name,
            "Description": self._buff_desc_var.get(),
            "Type":        self._buff_type_var.get(),
            "Value":       self._buff_value_var.get(),
            "Duration":    self._buff_duration_var.get(),
        }
        if self._buff_type_var.get() == "Stat Modifier":
            result["Stat"] = self._buff_stat_var.get()
        return result

    # ── add button ────────────────────────────────────────────────────────────

    # Object types where names must be unique within the session
    _UNIQUE_NAME_TYPES = {"NPC", "Item", "Action", "Buff"}

    def _do_add(self) -> None:
        self._err_var.set("")
        t = self._type_var.get()
        if t == "Action":
            obj = self._build_action_result()
        elif t == "Buff":
            obj = self._build_buff_result()
        else:
            obj = self._build_result_dict()
        if obj is None:
            return

        # Unique name check (NPC/Item/Action/Buff)
        if obj.get("type") in self._UNIQUE_NAME_TYPES:
            name_lower = obj.get("Name", "").strip().lower()
            for existing in self._get_session_objects():
                if (existing.get("type") in self._UNIQUE_NAME_TYPES and
                        existing.get("Name", "").strip().lower() == name_lower):
                    self._err_var.set(
                        f"An object named '{obj.get('Name')}' already exists.")
                    return

        self._on_add(obj)
        self.after_idle(self._render_body)

    # ── borrow SpawnObjectDialog form methods ─────────────────────────────────

    from dialogs.spawn_object_dialog import SpawnObjectDialog as _S
    _update_scroll       = _S._update_scroll
    _make_section        = _S._make_section
    _lbl                 = _S._lbl
    _spinbox             = _S._spinbox
    _field_row           = _S._field_row
    _build_npc_form      = _S._build_npc_form
    _build_item_form     = _S._build_item_form
    _recalc_npc_hp       = _S._recalc_npc_hp
    _validate_npc_stats  = _S._validate_npc_stats
    _validate_item_stats = _S._validate_item_stats
    _add_action_row      = _S._add_action_row
    _build_action_buttons= _S._build_action_buttons
    _pick_prefab_action  = _S._pick_prefab_action
    _collect_actions     = _S._collect_actions
    _build_result_dict   = _S._build_result_dict
    _fill_actions        = _S._fill_actions
    del _S
