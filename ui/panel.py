"""
In-app modal panel — replaces tk.Toplevel throughout the project.

Usage:
    class MyDialog(Panel):
        def __init__(self, parent, ...):
            super().__init__(parent)
            tk.Label(self, text="Hello", ...).pack()
            flat_btn(self, "OK", self.close, ...).pack()

    MyDialog(some_widget)

For synchronous confirm dialogs use Panel.wait():
    panel = MyDialog(parent)
    panel.wait()   # blocks until self.close() is called
"""
import tkinter as tk
from app.constants import PALETTE


class Panel(tk.Frame):
    _closing = False

    def __init__(self, parent, padx: int = 0, pady: int = 0, **kwargs):
        root = parent.winfo_toplevel()

        # Dark backdrop covers entire root window
        self._backdrop = tk.Frame(root, bg="#000000")
        self._backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        self._backdrop.lift()

        # Bind click on bare backdrop to do nothing (swallow events)
        self._backdrop.bind("<Button-1>", lambda e: None)

        super().__init__(self._backdrop, bg=PALETTE["card"],
                         padx=padx, pady=pady, **kwargs)
        self.place(relx=0.5, rely=0.5, anchor="center")
        self.lift()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self._backdrop.destroy()
        except Exception:
            pass

    def destroy(self) -> None:
        self.close()

    def wait(self) -> None:
        """Block until close() is called (for synchronous dialogs)."""
        try:
            self.winfo_toplevel().wait_window(self._backdrop)
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
