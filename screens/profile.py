import io
import base64
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable

from app.constants import PALETTE, FONTS
from app.config import save_user_config
from ui.widgets import flat_btn, hr, styled_entry

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ProfileScreen(tk.Frame):
    def __init__(self, parent, user_config: dict,
                 on_save: Callable, on_cancel: Callable, **kwargs):
        super().__init__(parent, bg=PALETTE["bg"], **kwargs)
        self._user_config = dict(user_config)
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._preview_img_ref = None
        self._pending_b64: str | None = user_config.get("avatar_b64")
        self._build()

    def _build(self) -> None:
        card = tk.Frame(self, bg=PALETTE["card"], padx=36, pady=28)
        card.place(relx=0.5, rely=0.5, anchor="center")

        # ── Title ─────────────────────────────────────────────────────────────
        tk.Label(card, text="Configure Profile", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w")
        hr(card).pack(fill=tk.X, pady=(8, 14))

        # ── Player Name ───────────────────────────────────────────────────────
        name_row = tk.Frame(card, bg=PALETTE["card"])
        name_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(name_row, text="Player Name", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"],
                 width=14, anchor="w").pack(side=tk.LEFT)
        self._alias_var = tk.StringVar(value=self._user_config.get("alias", ""))
        styled_entry(name_row, textvariable=self._alias_var, width=24).pack(side=tk.LEFT)

        # ── UUID (small, single-line, doesn't wrap) ───────────────────────────
        uid = self._user_config.get("uuid", "")
        tk.Label(card, text=f"UUID: {uid}", bg=PALETTE["card"],
                 fg=PALETTE["muted"], font=("Consolas", 7),
                 anchor="w", wraplength=0).pack(fill=tk.X, pady=(0, 10))

        hr(card).pack(fill=tk.X, pady=(0, 12))

        # ── Profile Picture ───────────────────────────────────────────────────
        tk.Label(card, text="Profile Picture", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"]).pack(anchor="w", pady=(0, 8))

        pic_row = tk.Frame(card, bg=PALETTE["card"])
        pic_row.pack(anchor="w", pady=(0, 14))

        # Canvas gives pixel-exact 128×128 preview (Labels use char units)
        self._preview_canvas = tk.Canvas(
            pic_row, width=128, height=128,
            bg=PALETTE["card2"], highlightthickness=1,
            highlightbackground=PALETTE["border"])
        self._preview_canvas.pack(side=tk.LEFT, padx=(0, 18))

        btn_col = tk.Frame(pic_row, bg=PALETTE["card"])
        btn_col.pack(side=tk.LEFT, anchor="n")
        flat_btn(btn_col, "Upload Image", self._upload, style="ghost").pack(
            fill=tk.X, pady=(0, 6))
        flat_btn(btn_col, "Remove Image", self._remove, style="muted").pack(fill=tk.X)

        self._load_preview(self._pending_b64)

        # ── Buttons ───────────────────────────────────────────────────────────
        hr(card).pack(fill=tk.X, pady=(0, 12))
        btn_row = tk.Frame(card, bg=PALETTE["card"])
        btn_row.pack(anchor="e")
        flat_btn(btn_row, "Save", self._save, style="normal").pack(
            side=tk.LEFT, padx=(0, 8))
        flat_btn(btn_row, "Cancel", self._on_cancel, style="ghost").pack(side=tk.LEFT)

    def _load_preview(self, b64: str | None) -> None:
        self._preview_canvas.delete("all")
        self._preview_img_ref = None
        if not b64 or not HAS_PIL:
            self._preview_canvas.create_text(
                64, 64, text="No Image",
                fill=PALETTE["muted"], font=FONTS["small"])
            return
        try:
            data = base64.b64decode(b64)
            img = Image.open(io.BytesIO(data)).resize((128, 128), Image.LANCZOS)
            self._preview_img_ref = ImageTk.PhotoImage(img)
            self._preview_canvas.create_image(0, 0, anchor="nw",
                                               image=self._preview_img_ref)
        except Exception as e:
            self._preview_canvas.create_text(
                64, 64, text=f"Error\n{e}",
                fill=PALETTE["danger"], font=FONTS["small"])

    def _upload(self) -> None:
        if not HAS_PIL:
            messagebox.showerror("Missing Library",
                                 "Pillow is required for image upload.")
            return
        path = filedialog.askopenfilename(
            title="Select Profile Picture",
            filetypes=[("Image files",
                        "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp")],
        )
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
            self._pending_b64 = base64.b64encode(buf.getvalue()).decode()
            self._load_preview(self._pending_b64)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _remove(self) -> None:
        self._pending_b64 = None
        self._load_preview(None)

    def _save(self) -> None:
        alias = self._alias_var.get().strip()[:32]
        self._user_config["alias"] = alias
        self._user_config["avatar_b64"] = self._pending_b64
        save_user_config(self._user_config)
        self._on_save(self._user_config)
