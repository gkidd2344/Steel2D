import tkinter as tk
from typing import Callable, Tuple
from app.constants import PALETTE, FONTS, DEFAULT_PORT
from ui.panel import Panel
from ui.widgets import flat_btn, styled_entry, hr

# Port used when an address carries no explicit ":port".
IMPLICIT_PORT = 80           # plain IP / host address
IMPLICIT_HTTPS_PORT = 443    # https:// address


def _parse_address(raw: str) -> Tuple[str, int]:
    """Parse a connection string into (host, port), or raise ValueError.

    Accepts: ``IP``, ``IP:port``, ``host``, ``host:port``,
    ``http://host[:port]``, ``https://host[:port]`` (a path after the host is
    ignored). An explicit ``:port`` always wins; otherwise the default is 80,
    or 443 for an ``https://`` URL.
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Please enter a host address.")

    default_port = IMPLICIT_PORT
    low = raw.lower()
    if low.startswith("https://"):
        default_port = IMPLICIT_HTTPS_PORT
        raw = raw[len("https://"):]
    elif low.startswith("http://"):
        default_port = IMPLICIT_PORT
        raw = raw[len("http://"):]

    # Drop any path / query / fragment after the host[:port]
    for sep in ("/", "?", "#"):
        if sep in raw:
            raw = raw.split(sep, 1)[0]
    raw = raw.strip()
    if not raw:
        raise ValueError("Please enter a host address.")

    if ":" in raw:
        host, port_str = raw.rsplit(":", 1)
        host = host.strip()
        try:
            port = int(port_str.strip())
        except ValueError:
            raise ValueError("Invalid port number.")
    else:
        host = raw
        port = default_port

    if not host:
        raise ValueError("Please enter a host address.")
    if not (1 <= port <= 65535):
        raise ValueError("Port must be between 1 and 65535.")
    return host, port


def _bind_tooltip(widget: tk.Widget, text: str) -> None:
    """Show a small floating tooltip while the pointer is over `widget`."""
    tip: list = [None]

    def _show(event):
        if tip[0]:
            return
        t = tk.Toplevel(widget)
        t.overrideredirect(True)
        t.wm_attributes("-topmost", True)
        t.geometry(f"+{event.x_root + 12}+{event.y_root + 16}")
        tk.Label(t, text=text, bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["small"], justify="left", padx=8, pady=6,
                 relief=tk.SOLID, bd=1, wraplength=260).pack()
        tip[0] = t

    def _hide(event):
        if tip[0]:
            try:
                tip[0].destroy()
            except Exception:
                pass
            tip[0] = None

    widget.bind("<Enter>", _show)
    widget.bind("<Leave>", _hide)


class JoinDialog(Panel):
    def __init__(self, parent, on_join: Callable,
                 prefill_host: str = "127.0.0.1",
                 prefill_port: int = DEFAULT_PORT,
                 error: str = ""):
        super().__init__(parent, padx=28, pady=20)
        self._on_join = on_join
        self._prefill_host = prefill_host
        self._prefill_port = prefill_port
        self._error = error
        self._build()

    def _build(self) -> None:
        tk.Label(self, text="Join a Game", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 14))

        form = tk.Frame(self, bg=PALETTE["card"])
        form.pack(fill=tk.X)

        # ── Host Address (single field) ───────────────────────────────────────
        lbl_frame = tk.Frame(form, bg=PALETTE["card"])
        lbl_frame.grid(row=0, column=0, sticky="w", pady=5)
        tk.Label(lbl_frame, text="Host Address", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(side=tk.LEFT)
        hint = tk.Label(lbl_frame, text=" ⓘ", bg=PALETTE["card"],
                        fg=PALETTE["accent"], font=FONTS["small"],
                        cursor="question_arrow")
        hint.pack(side=tk.LEFT)
        _bind_tooltip(
            hint,
            "Accepts an IP, IP:Port, or a host address (like a website). "
            "If only an IP or plain address is supplied it connects over port 80; "
            "an https:// address uses 443. Add :PORT (e.g. 10.0.0.5:5000) to use a "
            "specific port.")

        # Prefill as a full "host:port" string
        if self._prefill_port:
            initial = f"{self._prefill_host}:{self._prefill_port}"
        else:
            initial = self._prefill_host
        self._addr_var = tk.StringVar(value=initial)
        styled_entry(form, textvariable=self._addr_var, width=26).grid(
            row=0, column=1, pady=5, padx=(10, 0))

        # ── Password ──────────────────────────────────────────────────────────
        tk.Label(form, text="Password", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"]).grid(
            row=1, column=0, sticky="w", pady=5)
        self._pwd_var = tk.StringVar()   # always blank (cleared on re-open)
        styled_entry(form, textvariable=self._pwd_var, width=22,
                     show="•").grid(
            row=1, column=1, sticky="w", pady=5, padx=(10, 0))

        # Error label (shown when password was wrong / parse failed)
        self._err_var = tk.StringVar(value=self._error)
        tk.Label(self, textvariable=self._err_var, bg=PALETTE["card"],
                 fg=PALETTE["danger"], font=FONTS["small"]).pack(pady=(6, 0))

        hr(self).pack(fill=tk.X, pady=(10, 8))
        btn_row = tk.Frame(self, bg=PALETTE["card"])
        btn_row.pack(anchor="e")
        flat_btn(btn_row, "Join", self._do_join, style="normal").pack(
            side=tk.LEFT, padx=(0, 8))
        flat_btn(btn_row, "Cancel", self.close, style="ghost").pack(side=tk.LEFT)

        self.bind("<Return>", lambda e: self._do_join())

    def _do_join(self) -> None:
        try:
            host, port = _parse_address(self._addr_var.get())
        except ValueError as e:
            self._err_var.set(str(e))
            return
        pwd = self._pwd_var.get()
        self.close()
        self._on_join(host, port, pwd)
