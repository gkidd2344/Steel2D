"""
In-app floating panel — replaces tk.Toplevel throughout the project.
Panels appear on the right side of the root window so they don't
obscure the game canvas. They have no full-screen dark backdrop.

Usage:
    class MyDialog(Panel):
        def __init__(self, parent, ...):
            super().__init__(parent)
            tk.Label(self, text="Hello").pack()
            flat_btn(self, "OK", self.close).pack()

For synchronous confirm dialogs:
    panel = MyDialog(parent)
    panel.wait()   # blocks until self.close() is called
"""
import tkinter as tk
from app.constants import PALETTE


class Panel(tk.Frame):
    _closing = False

    def __init__(self, parent, padx: int = 0, pady: int = 0, **kwargs):
        root = parent.winfo_toplevel()

        # Remove keys Panel shouldn't forward to Frame
        kwargs.pop("bg", None)

        super().__init__(
            root,
            bg=PALETTE["card"],
            padx=padx,
            pady=pady,
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
            **kwargs,
        )

        # Float on the right side, vertically centred
        self.place(relx=1.0, x=-10, rely=0.5, anchor="e")
        self.lift()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            tk.Frame.destroy(self)
        except Exception:
            pass

    def destroy(self) -> None:
        self.close()

    def wait(self) -> None:
        """Block the event loop until close() is called."""
        try:
            self.winfo_toplevel().wait_window(self)
        except Exception:
            pass

    # ── compat stubs (so code ported from Toplevel keeps working) ────────────

    def grab_set(self) -> None: pass
    def transient(self, *a) -> None: pass
    def resizable(self, *a) -> None: pass
    def attributes(self, *a, **kw) -> None: pass
    def overrideredirect(self, *a) -> None: pass
    def geometry(self, *a) -> None: pass
    def protocol(self, *a, **kw) -> None: pass

    def title(self, t: str = None) -> str:
        if t is not None:
            self._wm_title = t
        return getattr(self, "_wm_title", "")
