"""
Character Editor — full-screen frame accessible from the main menu.

Saves to <appdata>/Steel2D/character.sav (msgpack + zlib, same as game saves).
"""
from __future__ import annotations
import io
import base64
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable

from app.constants import PALETTE, FONTS
from app.config import (
    STAT_KEYS, HEALTH_SIZE_LOOKUP, load_character, save_character,
)
from game.stats import calc_max_hp
from game.stats import max_individual, max_total, calc_max_hp
from ui.widgets import flat_btn, hr, styled_entry

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class CharacterEditorScreen(tk.Frame):
    def __init__(self, parent, on_save: Callable, on_cancel: Callable, **kwargs):
        super().__init__(parent, bg=PALETTE["bg"], **kwargs)
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._avatar_b64: str | None = None
        self._avatar_img_ref = None
        self._stat_warn_var = tk.StringVar()
        self._existing: dict | None = load_character()
        self._build()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Scrollable outer card
        outer = tk.Frame(self, bg=PALETTE["bg"])
        outer.place(relx=0.5, rely=0.5, anchor="center")

        card = tk.Frame(outer, bg=PALETTE["card"], padx=32, pady=24)
        card.pack()

        tk.Label(card, text="Character", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["title"]).pack()
        hr(card).pack(fill=tk.X, pady=8)

        # ── Identity ──────────────────────────────────────────────────────────
        form = tk.Frame(card, bg=PALETTE["card"])
        form.pack(fill=tk.X, pady=(0, 8))
        form.columnconfigure(1, weight=1)

        row = 0
        for label, attr in [
            ("Character Name *", "char_name"),
            ("Class",            "char_class"),
        ]:
            tk.Label(form, text=label, bg=PALETTE["card"],
                     fg=PALETTE["fg"], font=FONTS["body"],
                     anchor="e", width=16).grid(row=row, column=0, sticky="e",
                                                pady=5, padx=(0, 8))
            var = tk.StringVar()
            setattr(self, f"_{attr}_var", var)
            styled_entry(form, textvariable=var, width=28).grid(
                row=row, column=1, sticky="w", pady=5)
            row += 1

        # Backstory textarea
        tk.Label(form, text="Backstory", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"],
                 anchor="ne", width=16).grid(row=row, column=0, sticky="ne",
                                             pady=5, padx=(0, 8))
        self._backstory_text = tk.Text(
            form, height=4, width=30,
            bg=PALETTE["card2"], fg=PALETTE["fg"],
            insertbackground=PALETTE["fg"],
            relief=tk.FLAT, bd=1,
            highlightthickness=1, highlightbackground=PALETTE["border"])
        self._backstory_text.grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        hr(card).pack(fill=tk.X, pady=8)

        # ── Game stats ────────────────────────────────────────────────────────
        stats_row = tk.Frame(card, bg=PALETTE["card"])
        stats_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(stats_row, text="Level", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"]).pack(side=tk.LEFT, padx=(0, 4))
        self._level_var = tk.IntVar(value=1)
        tk.Spinbox(stats_row, from_=1, to=99, textvariable=self._level_var,
                   width=4, bg=PALETTE["card2"], fg=PALETTE["fg"],
                   insertbackground=PALETTE["fg"], relief=tk.FLAT, bd=0,
                   buttonbackground=PALETTE["muted"],
                   # command fires on arrow clicks; trace fires on typing
                   command=self._on_level_change).pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(stats_row, text="Size", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"]).pack(side=tk.LEFT, padx=(0, 4))
        self._size_var = tk.StringVar(value="Medium")
        _size_cb = ttk.Combobox(stats_row, textvariable=self._size_var,
                                 values=list(HEALTH_SIZE_LOOKUP.keys()),
                                 state="readonly", width=10)
        _size_cb.pack(side=tk.LEFT)
        # Combobox selection fires <<ComboboxSelected>>, not a variable write trace
        _size_cb.bind("<<ComboboxSelected>>",
                      lambda e: self._update_char_maxhp())

        # Stats grid — Con spinbox also updates Max HP
        stat_frame = tk.Frame(card, bg=PALETTE["card"])
        stat_frame.pack(fill=tk.X, pady=4)
        self._stat_vars = {k: tk.IntVar(value=10) for k in STAT_KEYS}
        for i, k in enumerate(STAT_KEYS):
            col_f = tk.Frame(stat_frame, bg=PALETTE["card"])
            col_f.grid(row=0, column=i, padx=8, pady=4)
            tk.Label(col_f, text=k, bg=PALETTE["card"],
                     fg=PALETTE["fg"], font=FONTS["small"]).pack()
            if k == "Con":
                def _con_cmd():
                    self._validate_stats()
                    self._update_char_maxhp()
                sp = tk.Spinbox(col_f, from_=0, to=9999,
                                textvariable=self._stat_vars["Con"], width=5,
                                bg=PALETTE["card2"], fg=PALETTE["fg"],
                                insertbackground=PALETTE["fg"],
                                relief=tk.FLAT, bd=0,
                                buttonbackground=PALETTE["muted"],
                                command=_con_cmd)
                self._stat_vars["Con"].trace_add(
                    "write", lambda *_: (self._validate_stats(),
                                         self._update_char_maxhp()))
            else:
                sp = tk.Spinbox(col_f, from_=0, to=9999,
                                textvariable=self._stat_vars[k], width=5,
                                bg=PALETTE["card2"], fg=PALETTE["fg"],
                                insertbackground=PALETTE["fg"],
                                relief=tk.FLAT, bd=0,
                                buttonbackground=PALETTE["muted"],
                                command=self._validate_stats)
                self._stat_vars[k].trace_add("write",
                                              lambda *_: self._validate_stats())
            sp.pack()

        tk.Label(card, textvariable=self._stat_warn_var, bg=PALETTE["card"],
                 fg="#ff8c00", font=FONTS["small"]).pack(pady=(2, 4))

        # ── Readonly Max HP (auto-calculated) ─────────────────────────────────
        self._maxhp_disp = tk.StringVar(value="—")
        maxhp_row = tk.Frame(card, bg=PALETTE["card"])
        maxhp_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(maxhp_row, text="Max HP:", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"],
                 width=6, anchor="w").pack(side=tk.LEFT)
        tk.Label(maxhp_row, textvariable=self._maxhp_disp, bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["sub"]).pack(side=tk.LEFT, padx=(4, 10))
        tk.Label(maxhp_row, text="(readonly — auto-calculated from Size + Con)",
                 bg=PALETTE["card"], fg=PALETTE["muted"],
                 font=FONTS["small"]).pack(side=tk.LEFT)

        # Level trace for typing (command already bound to arrow clicks)
        self._level_var.trace_add("write", lambda *_: self._update_char_maxhp())

        self._update_char_maxhp()   # initialise display

        # ── Avatar ────────────────────────────────────────────────────────────
        hr(card).pack(fill=tk.X, pady=8)
        pic_row = tk.Frame(card, bg=PALETTE["card"])
        pic_row.pack(pady=(0, 8))
        self._preview_canvas = tk.Canvas(
            pic_row, width=80, height=80,
            bg=PALETTE["card2"], highlightthickness=1,
            highlightbackground=PALETTE["border"])
        self._preview_canvas.pack(side=tk.LEFT, padx=(0, 14))
        btn_col = tk.Frame(pic_row, bg=PALETTE["card"])
        btn_col.pack(side=tk.LEFT, anchor="n")
        flat_btn(btn_col, "Upload Avatar", self._upload_avatar,
                 style="ghost").pack(fill=tk.X, pady=(0, 6))
        flat_btn(btn_col, "Remove Avatar", self._remove_avatar,
                 style="muted").pack(fill=tk.X)

        # ── Save / Cancel ─────────────────────────────────────────────────────
        hr(card).pack(fill=tk.X, pady=8)
        btn_row = tk.Frame(card, bg=PALETTE["card"])
        btn_row.pack(anchor="e")
        flat_btn(btn_row, "Save Character", self._save,
                 style="normal").pack(side=tk.LEFT, padx=(0, 8), ipadx=8)
        flat_btn(btn_row, "Cancel", self._on_cancel,
                 style="ghost").pack(side=tk.LEFT)

        # Pre-fill from existing character file
        if self._existing:
            self._prefill(self._existing)

    # ── pre-fill ──────────────────────────────────────────────────────────────

    def _prefill(self, d: dict) -> None:
        self._char_name_var.set(d.get("CharacterName", ""))
        self._char_class_var.set(d.get("Class", ""))
        bs = d.get("Backstory", "")
        if bs:
            self._backstory_text.insert("1.0", bs)
        self._level_var.set(d.get("Level", 1))
        self._size_var.set(d.get("Size", "Medium"))
        for k in STAT_KEYS:
            if k in (d.get("Stats") or {}):
                self._stat_vars[k].set(d["Stats"][k])
        if d.get("avatar_png"):
            try:
                self._avatar_b64 = d["avatar_png"]
                self._load_preview(self._avatar_b64)
            except Exception:
                pass
        self._validate_stats()

    # ── avatar ────────────────────────────────────────────────────────────────

    def _upload_avatar(self) -> None:
        if not HAS_PIL:
            messagebox.showerror("Missing Library", "Pillow is required.")
            return
        path = filedialog.askopenfilename(
            title="Select Avatar",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp")])
        if not path:
            return
        try:
            img = Image.open(path)
            w, h = img.size
            s = min(w, h)
            scale = 128 / s
            nw, nh = int(w * scale), int(h * scale)
            img = img.resize((nw, nh), Image.LANCZOS)
            if nw > 128:
                left = (nw - 128) // 2
                img = img.crop((left, 0, left + 128, 128))
            elif nh > 128:
                top = (nh - 128) // 2
                img = img.crop((0, top, 128, top + 128))
            img = img.convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            self._avatar_b64 = base64.b64encode(buf.getvalue()).decode()
            self._load_preview(self._avatar_b64)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _remove_avatar(self) -> None:
        self._avatar_b64 = None
        self._preview_canvas.delete("all")
        self._preview_canvas.create_text(40, 40, text="No Image",
                                          fill=PALETTE["muted"],
                                          font=FONTS["small"])

    def _load_preview(self, b64: str | None) -> None:
        self._preview_canvas.delete("all")
        if not b64 or not HAS_PIL:
            self._preview_canvas.create_text(40, 40, text="No Image",
                                              fill=PALETTE["muted"],
                                              font=FONTS["small"])
            return
        try:
            data = base64.b64decode(b64)
            img = Image.open(io.BytesIO(data)).resize((80, 80), Image.LANCZOS)
            self._avatar_img_ref = ImageTk.PhotoImage(img)
            self._preview_canvas.create_image(0, 0, anchor="nw",
                                               image=self._avatar_img_ref)
        except Exception:
            pass

    # ── validation ────────────────────────────────────────────────────────────

    def _on_level_change(self) -> None:
        self._validate_stats()
        self._update_char_maxhp()

    def _update_char_maxhp(self, *_) -> None:
        """Recompute Max HP from Size + Con and update the readonly display label."""
        try:
            hp = calc_max_hp(
                self._size_var.get(),
                self._level_var.get(),
                self._stat_vars.get("Con", tk.IntVar()).get(),
                4.0,
            )
            self._maxhp_disp.set(str(hp))
        except Exception:
            pass

    def _validate_stats(self) -> None:
        try:
            level = self._level_var.get()
            mi = max_individual(level)
            mt = max_total(level)
            total = sum(v.get() for v in self._stat_vars.values())
            warn = ""
            for k, v in self._stat_vars.items():
                if v.get() > mi:
                    warn = f"Stat exceeds maximum of {mi} for lv.{level}"
                    break
            if not warn and total > mt:
                warn = f"Stat total exceeds maximum of {mt} for lv.{level}"
            self._stat_warn_var.set(warn)
        except Exception:
            pass

    # ── save ─────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        char_name = self._char_name_var.get().strip()
        if not char_name:
            messagebox.showerror("Required", "Character Name is required.")
            return

        # Build a PlayerObject dict
        from app.config import load_user_config
        user_cfg = load_user_config()
        uid = user_cfg.get("uuid", "")

        level = self._level_var.get()
        size = self._size_var.get()
        stats = {k: v.get() for k, v in self._stat_vars.items()}
        con = stats.get("Con", 0)

        # If existing character has Equipment/Inventory/Buffs, preserve them
        existing = self._existing or {}
        d = {
            "id":            uid,
            "type":          "Player",
            "Name":          user_cfg.get("alias", "Player"),
            "CharacterName": char_name,
            "Class":         self._char_class_var.get().strip(),
            "Backstory":     self._backstory_text.get("1.0", "end-1c").strip(),
            "Size":          size,
            "Level":         level,
            "MaximumHP":     existing.get("MaximumHP",
                                          calc_max_hp(size, level, con, 4.0)),
            "CurrentHP":     existing.get("CurrentHP",
                                          calc_max_hp(size, level, con, 4.0)),
            "color":         existing.get("color", "#ffffff"),
            "Stats":         stats,
            "Equipment":     existing.get("Equipment", {}),
            "Inventory":     existing.get("Inventory", []),
            "avatar_png":    self._avatar_b64,
            "Buffs":         existing.get("Buffs", []),
        }

        try:
            save_character(d)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
            return

        self._on_save()
