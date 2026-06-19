import tkinter as tk
from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn


def ask_confirm(parent, title: str, message: str) -> bool:
    result = [False]
    panel = Panel(parent, padx=28, pady=20)

    tk.Label(panel, text=title, bg=PALETTE["card"],
             fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 6))
    tk.Label(panel, text=message, bg=PALETTE["card"],
             fg=PALETTE["fg"], font=FONTS["body"],
             wraplength=320, justify="left").pack(anchor="w", pady=(0, 14))

    btn_row = tk.Frame(panel, bg=PALETTE["card"])
    btn_row.pack(anchor="e")

    def yes():
        result[0] = True
        panel.close()

    flat_btn(btn_row, "Yes", yes, style="danger", width=8).pack(side=tk.LEFT, padx=(0, 6))
    flat_btn(btn_row, "No", panel.close, style="ghost", width=8).pack(side=tk.LEFT)

    panel.wait()
    return result[0]
