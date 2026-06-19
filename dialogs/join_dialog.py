import tkinter as tk
from typing import Callable
from app.constants import PALETTE, FONTS, DEFAULT_PORT
from ui.panel import Panel
from ui.widgets import flat_btn, styled_entry, hr


class JoinDialog(Panel):
    def __init__(self, parent, on_join: Callable):
        super().__init__(parent, padx=28, pady=20)
        self._on_join = on_join
        self._build()

    def _build(self) -> None:
        tk.Label(self, text="Join a Game", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 14))

        form = tk.Frame(self, bg=PALETTE["card"])
        form.pack(fill=tk.X)

        tk.Label(form, text="Host IP / Address", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"]).grid(
            row=0, column=0, sticky="w", pady=5)
        self._host_var = tk.StringVar(value="127.0.0.1")
        styled_entry(form, textvariable=self._host_var, width=26).grid(
            row=0, column=1, pady=5, padx=(10, 0))

        tk.Label(form, text="Port", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"]).grid(
            row=1, column=0, sticky="w", pady=5)
        self._port_var = tk.StringVar(value=str(DEFAULT_PORT))
        styled_entry(form, textvariable=self._port_var, width=8).grid(
            row=1, column=1, sticky="w", pady=5, padx=(10, 0))

        self._err_var = tk.StringVar()
        tk.Label(self, textvariable=self._err_var, bg=PALETTE["card"],
                 fg=PALETTE["danger"], font=FONTS["small"]).pack(pady=(6, 0))

        hr(self).pack(fill=tk.X, pady=(10, 8))
        btn_row = tk.Frame(self, bg=PALETTE["card"])
        btn_row.pack(anchor="e")
        flat_btn(btn_row, "Join", self._do_join, style="normal").pack(side=tk.LEFT, padx=(0, 8))
        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT)

        self.bind("<Return>", lambda e: self._do_join())

    def _do_join(self) -> None:
        host = self._host_var.get().strip()
        try:
            port = int(self._port_var.get().strip())
        except ValueError:
            self._err_var.set("Invalid port number.")
            return
        if not host:
            self._err_var.set("Please enter a host address.")
            return
        self.close()
        self._on_join(host, port)
