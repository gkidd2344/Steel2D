import socket
import threading
import tkinter as tk
from typing import Callable
from app.constants import PALETTE, FONTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr, styled_entry


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_external_ip() -> str:
    """Best-effort public IP lookup via a few plain-text services."""
    import urllib.request
    services = (
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://ipinfo.io/ip",
        "https://ifconfig.me/ip",
    )
    for url in services:
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                ip = resp.read().decode("utf-8").strip()
                if ip:
                    return ip
        except Exception:
            continue
    return ""


class HostDialog(Panel):
    def __init__(self, parent, on_new_game: Callable, on_load_game: Callable):
        super().__init__(parent, padx=32, pady=24)
        self._on_new = on_new_game
        self._on_load = on_load_game
        self._network_var = tk.BooleanVar(value=False)
        self._port_var = tk.StringVar(value="5000")
        self._ip_var = tk.StringVar(value=_get_local_ip())
        self._external_ip: str = ""   # cached once fetched
        self._build()

    def _build(self) -> None:
        tk.Label(self, text="Host a Game", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["heading"]).pack(anchor="w", pady=(0, 14))
        
        # ── IP : Port (always visible; IP readonly, Port editable) ────────────
        tk.Label(self, text="IP : Port", bg=PALETTE["card"],
                 fg=PALETTE["fg_dim"], font=FONTS["small"]).pack(anchor="w", pady=(0, 4))

        ipport_row = tk.Frame(self, bg=PALETTE["card"])
        ipport_row.pack(fill=tk.X, pady=(0, 10))

        ip_entry = styled_entry(
            ipport_row, textvariable=self._ip_var, width=16,
            state="readonly",
            readonlybackground=PALETTE["card2"],
        )
        ip_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(ipport_row, text=":", bg=PALETTE["card"],
                 fg=PALETTE["fg"], font=FONTS["body"]).pack(side=tk.LEFT, padx=6)

        styled_entry(ipport_row, textvariable=self._port_var,
                     width=7).pack(side=tk.LEFT)

        # ── Enable Network Play ───────────────────────────────────────────────
        tk.Checkbutton(
            self, text="Enable Network Play",
            variable=self._network_var,
            bg=PALETTE["card"], fg=PALETTE["fg"],
            selectcolor=PALETTE["card2"],
            activebackground=PALETTE["card"],
            activeforeground=PALETTE["fg"],
            font=FONTS["body"],
            command=self._on_network_toggle,
        ).pack(anchor="w", pady=(0, 10))

        # ── Session Password ──────────────────────────────────────────────────
        tk.Label(self, text="Session Password (optional)",
                 bg=PALETTE["card"], fg=PALETTE["fg_dim"],
                 font=FONTS["small"]).pack(anchor="w", pady=(0, 4))
        self._pwd_var = tk.StringVar()
        styled_entry(self, textvariable=self._pwd_var, width=26,
                     show="•").pack(fill=tk.X, pady=(0, 12))

        hr(self).pack(fill=tk.X, pady=(12, 10))

        # New / Load do NOT close this dialog — the submenu opens on top of it
        # and the controller closes it only when a game actually launches, so
        # cancelling the submenu reveals this window with its fields intact.
        flat_btn(self, "🆕  New Game",
                 lambda: self._on_new(self._password(), self._port(),
                                      self._display_ip(), self._network_var.get()),
                 style="normal").pack(fill=tk.X, pady=4, ipady=4)
        flat_btn(self, "📂  Load Game",
                 lambda: self._on_load(self._password(), self._port(),
                                       self._display_ip(), self._network_var.get()),
                 style="ghost").pack(fill=tk.X, pady=4, ipady=4)

        flat_btn(self, "Cancel", self.close,
                 style="muted").pack(fill=tk.X, ipady=4)

    def _on_network_toggle(self) -> None:
        if not self._network_var.get():
            # Local play — use the LAN IP
            self._ip_var.set(_get_local_ip())
            return
        # Network play — use the external/public IP (cached after first lookup)
        if self._external_ip:
            self._ip_var.set(self._external_ip)
            return
        self._ip_var.set("Fetching…")
        threading.Thread(target=self._fetch_external_ip, daemon=True).start()

    def _fetch_external_ip(self) -> None:
        ip = _get_external_ip()

        def _apply():
            if not self.winfo_exists():
                return
            # Ignore if the user unticked the box while we were fetching
            if not self._network_var.get():
                return
            if ip:
                self._external_ip = ip
                self._ip_var.set(ip)
            else:
                # Lookup failed — fall back to the LAN IP
                self._ip_var.set(_get_local_ip())

        try:
            self.after(0, _apply)
        except Exception:
            pass

    def _display_ip(self) -> str:
        """The IP the game should advertise — matches what's shown in the field.

        Network play → the cached external IP (LAN fallback if it hasn't
        resolved yet); local play → the LAN IP.
        """
        if self._network_var.get():
            return self._external_ip or _get_local_ip()
        return _get_local_ip()

    def _password(self) -> str:
        return self._pwd_var.get()

    def _port(self) -> int:
        try:
            p = int(self._port_var.get())
            if 1 <= p <= 65535:
                return p
        except ValueError:
            pass
        return 5000
