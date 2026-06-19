import tkinter as tk
from typing import Callable, Optional
from app.constants import PALETTE, FONTS


def flat_btn(parent, text: str, command=None, style: str = "normal",
             width: int = 0, **kwargs) -> tk.Button:
    colours = {
        "normal":  (PALETTE["accent"],  "#ffffff"),
        "danger":  (PALETTE["danger"],  "#ffffff"),
        "success": (PALETTE["success"], "#ffffff"),
        "ghost":   (PALETTE["card2"],   PALETTE["fg"]),
        "muted":   (PALETTE["card"],    PALETTE["fg_dim"]),
    }
    bg, fg = colours.get(style, colours["normal"])
    opts = dict(
        text=text,
        command=command,
        bg=bg, fg=fg,
        relief=tk.FLAT,
        font=FONTS["body"],
        cursor="hand2",
        padx=12, pady=6,
        activebackground=_darken(bg, 0.85),
        activeforeground=fg,
        bd=0,
    )
    if width:
        opts["width"] = width
    opts.update(kwargs)
    return tk.Button(parent, **opts)


def hr(parent, color: str = None, **kwargs) -> tk.Frame:
    return tk.Frame(parent, bg=color or PALETTE["border"], height=1, **kwargs)


def styled_entry(parent, textvariable=None, width: int = 24, **kwargs) -> tk.Entry:
    opts = dict(
        textvariable=textvariable,
        bg=PALETTE["card2"],
        fg=PALETTE["fg"],
        insertbackground=PALETTE["fg"],
        relief=tk.FLAT,
        font=FONTS["body"],
        width=width,
        bd=0,
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        highlightcolor=PALETTE["accent"],
    )
    opts.update(kwargs)
    return tk.Entry(parent, **opts)


def styled_label(parent, text: str = "", style: str = "body",
                 color: str = None, **kwargs) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        bg=kwargs.pop("bg", PALETTE["card"]),
        fg=color or PALETTE["fg"],
        font=FONTS.get(style, FONTS["body"]),
        **kwargs,
    )


def card_frame(parent, **kwargs) -> tk.Frame:
    opts = dict(bg=PALETTE["card"], padx=20, pady=20)
    opts.update(kwargs)
    return tk.Frame(parent, **opts)


def styled_check(parent, text: str, variable: tk.BooleanVar,
                 command: Optional[Callable] = None,
                 bg: str = None, **kwargs) -> tk.Frame:
    """
    Custom checkbutton with a visible white ✓ on accent background when
    checked — looks correct on dark themes where OS-native checkmarks are
    invisible.
    """
    frame_bg = bg or parent.cget("bg")
    frame = tk.Frame(parent, bg=frame_bg, cursor="hand2")

    indicator = tk.Label(
        frame, width=2,
        bg=PALETTE["card2"], fg="#ffffff",
        font=FONTS["body"], relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
    )
    indicator.pack(side=tk.LEFT)

    if text:
        lbl = tk.Label(frame, text=text, bg=frame_bg,
                       fg=PALETTE["fg"], font=FONTS["body"])
        lbl.pack(side=tk.LEFT, padx=(6, 0))

    def _update(*_) -> None:
        checked = variable.get()
        indicator.config(
            text="✓" if checked else " ",
            bg=PALETTE["accent"] if checked else PALETTE["card2"],
        )

    def _toggle(e=None) -> None:
        variable.set(not variable.get())
        if command:
            frame.after_idle(command)

    indicator.bind("<Button-1>", _toggle)
    frame.bind("<Button-1>", lambda e: _toggle())
    for child in frame.winfo_children():
        child.bind("<Button-1>", lambda e: _toggle())

    variable.trace_add("write", _update)
    _update()
    return frame


def _darken(hex_color: str, factor: float) -> str:
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return "#{:02x}{:02x}{:02x}".format(
            int(r * factor), int(g * factor), int(b * factor)
        )
    except Exception:
        return hex_color
