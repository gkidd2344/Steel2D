import tkinter as tk
from typing import Callable, TYPE_CHECKING
from app.constants import PALETTE, FONTS, EQUIPMENT_SLOTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr
from dialogs.confirm_dialog import ask_confirm

if TYPE_CHECKING:
    from game.objects import PlayerObject, Item

COLS = 5
CELL_PX = 64


class InventoryDialog(Panel):
    def __init__(self, parent, player: "PlayerObject",
                 on_use: Callable, on_equip: Callable,
                 on_drop: Callable, on_discard: Callable):
        super().__init__(parent, padx=0, pady=0)
        self._player = player
        self._on_use = on_use
        self._on_equip = on_equip
        self._on_drop = on_drop
        self._on_discard = on_discard
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=PALETTE["card"], padx=20, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Inventory — {self._player.Name}",
                 bg=PALETTE["card"], fg=PALETTE["fg"],
                 font=FONTS["heading"]).pack(side=tk.LEFT)
        flat_btn(hdr, "✕", self.close, style="ghost").pack(side=tk.RIGHT)
        hr(self).pack(fill=tk.X)

        # Equipment slots
        equip_lbl = tk.Frame(self, bg=PALETTE["card2"], padx=14, pady=6)
        equip_lbl.pack(fill=tk.X)
        tk.Label(equip_lbl, text="Equipment", bg=PALETTE["card2"],
                 fg=PALETTE["muted"], font=FONTS["small"]).pack(anchor="w")

        equip_grid = tk.Frame(self, bg=PALETTE["card"], padx=14, pady=6)
        equip_grid.pack(fill=tk.X)
        for col, (slot_id, slot_name) in enumerate(EQUIPMENT_SLOTS.items()):
            item = self._player.Equipment.get(slot_id)
            cell = tk.Frame(equip_grid, bg=PALETTE["card2"],
                            relief=tk.FLAT, bd=0,
                            highlightbackground=PALETTE["border"],
                            highlightthickness=1,
                            width=70, height=70)
            cell.grid(row=0, column=col, padx=2)
            cell.pack_propagate(False)
            tk.Label(cell, text=slot_name, bg=PALETTE["card2"],
                     fg=PALETTE["muted"], font=("Segoe UI", 7)).pack(pady=(4, 0))
            if item:
                tk.Label(cell, text=item.Name[:8], bg=PALETTE["card2"],
                         fg="#ff8800", font=FONTS["small"],
                         wraplength=60).pack()

        hr(self).pack(fill=tk.X, pady=4)

        # Inventory grid
        inv_lbl = tk.Frame(self, bg=PALETTE["card2"], padx=14, pady=6)
        inv_lbl.pack(fill=tk.X)
        tk.Label(inv_lbl, text="Backpack", bg=PALETTE["card2"],
                 fg=PALETTE["muted"], font=FONTS["small"]).pack(anchor="w")

        grid_outer = tk.Frame(self, bg=PALETTE["card"],
                              width=COLS * (CELL_PX + 4) + 20, height=200)
        grid_outer.pack(fill=tk.BOTH, padx=12, pady=6)
        grid_outer.pack_propagate(False)

        canvas = tk.Canvas(grid_outer, bg=PALETTE["card"], highlightthickness=0)
        vsb = tk.Scrollbar(grid_outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg=PALETTE["card"])
        canvas.create_window((0, 0), window=inner, anchor="nw")

        items = self._player.Inventory
        rows_needed = max(2, -(-len(items) // COLS) + 1)

        for idx in range(rows_needed * COLS):
            c = idx % COLS
            r = idx // COLS
            cell = tk.Frame(inner, bg=PALETTE["card2"],
                            width=CELL_PX, height=CELL_PX,
                            highlightbackground=PALETTE["border"],
                            highlightthickness=1)
            cell.grid(row=r, column=c, padx=1, pady=1)
            cell.pack_propagate(False)
            if idx < len(items):
                item = items[idx]
                tk.Label(cell, text=item.Name[:8], bg=PALETTE["card2"],
                         fg="#ff8800", font=FONTS["small"],
                         wraplength=58).place(relx=0.5, rely=0.4, anchor="center")
                if item.Quantity > 1:
                    tk.Label(cell, text=f"×{item.Quantity}", bg=PALETTE["card2"],
                             fg=PALETTE["fg_dim"],
                             font=FONTS["small"]).place(relx=1.0, rely=1.0, anchor="se")
                for widget in [cell] + list(cell.winfo_children()):
                    widget.bind("<Button-3>", lambda e, it=item: self._item_menu(e, it))

        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        self._tooltip_lbl = tk.Label(self, bg="#111", fg=PALETTE["fg"],
                                     font=FONTS["small"], relief=tk.FLAT,
                                     justify="left", padx=6, pady=4)

        hr(self).pack(fill=tk.X)
        flat_btn(self, "Close", self.close, style="ghost").pack(pady=8)

    def _item_menu(self, event, item: "Item") -> None:
        menu = tk.Menu(self, tearoff=0, bg=PALETTE["card"],
                       fg=PALETTE["fg"], relief=tk.FLAT)
        if item.Consumable:
            menu.add_command(label="Use", command=lambda: self._use(item))
        else:
            menu.add_command(label="Equip", command=lambda: self._equip(item))
        menu.add_command(label="Drop", command=lambda: self._drop(item))
        menu.add_command(label="Discard", command=lambda: self._discard(item))
        menu.tk_popup(event.x_root, event.y_root)

    def _use(self, item) -> None:
        self._on_use(item.id)
        self.close()

    def _equip(self, item) -> None:
        if item.EquipmentSlot is None:
            from dialogs.confirm_dialog import ask_confirm
            ask_confirm(self, "Cannot Equip",
                        "This item has no equipment slot defined.")
            return
        self._on_equip(item.id)
        self.close()

    def _drop(self, item) -> None:
        self._on_drop(item.id)
        self.close()

    def _discard(self, item) -> None:
        if ask_confirm(self, "Discard",
                       f"Are you sure you want to discard {item.Name}?"):
            self._on_discard(item.id)
            self.close()
