import tkinter as tk
from typing import Callable, Optional, TYPE_CHECKING
from app.constants import PALETTE, FONTS, EQUIPMENT_SLOTS
from ui.panel import Panel
from ui.widgets import flat_btn, hr
from dialogs.confirm_dialog import ask_confirm

if TYPE_CHECKING:
    from game.objects import PlayerObject, Item

COLS = 5
CELL_PX = 68


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

        # ── Equipment slots ───────────────────────────────────────────────────
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
                name_lbl = tk.Label(cell, text=item.Name[:8], bg=PALETTE["card2"],
                                    fg="#ff8800", font=FONTS["small"],
                                    wraplength=60, cursor="hand2")
                name_lbl.pack()
                # Left-click → inspect; right-click → action menu
                for widget in [cell, name_lbl]:
                    widget.bind("<Button-1>",
                                lambda e, it=item: self._inspect(it))
                    widget.bind("<Button-3>",
                                lambda e, it=item, sid=slot_id: self._equip_slot_menu(e, it, sid))

        hr(self).pack(fill=tk.X, pady=4)

        # ── Backpack ──────────────────────────────────────────────────────────
        inv_lbl = tk.Frame(self, bg=PALETTE["card2"], padx=14, pady=6)
        inv_lbl.pack(fill=tk.X)
        tk.Label(inv_lbl, text="Backpack", bg=PALETTE["card2"],
                 fg=PALETTE["muted"], font=FONTS["small"]).pack(anchor="w")

        items = self._player.Inventory
        # Each row: item cell (square icon) + action buttons side-by-side
        list_frame = tk.Frame(self, bg=PALETTE["card"], padx=10, pady=4)
        list_frame.pack(fill=tk.BOTH, expand=True)

        if not items:
            tk.Label(list_frame, text="Empty", bg=PALETTE["card"],
                     fg=PALETTE["muted"], font=FONTS["small"],
                     pady=12).pack()
        else:
            for idx, item in enumerate(items):
                row_bg = PALETTE["card"] if idx % 2 == 0 else PALETTE["card2"]
                row = tk.Frame(list_frame, bg=row_bg)
                row.pack(fill=tk.X, pady=1)

                # Small icon cell
                icon = tk.Frame(row, bg=PALETTE["card2"],
                                width=44, height=44,
                                highlightbackground=PALETTE["border"],
                                highlightthickness=1)
                icon.pack(side=tk.LEFT, padx=(0, 8), pady=2)
                icon.pack_propagate(False)
                icon_lbl = tk.Label(icon, text=item.Name[:4], bg=PALETTE["card2"],
                                    fg="#ff8800", font=("Segoe UI", 7),
                                    wraplength=40, cursor="hand2")
                icon_lbl.place(relx=0.5, rely=0.5, anchor="center")
                if item.Quantity > 1:
                    tk.Label(icon, text=f"×{item.Quantity}", bg=PALETTE["card2"],
                             fg=PALETTE["fg_dim"],
                             font=("Segoe UI", 6)).place(relx=1.0, rely=1.0,
                                                          anchor="se")

                # Name + action buttons
                info = tk.Frame(row, bg=row_bg)
                info.pack(side=tk.LEFT, fill=tk.X, expand=True)
                name_lbl = tk.Label(info, text=item.Name, bg=row_bg,
                                    fg=PALETTE["fg"], font=FONTS["body"],
                                    anchor="w", cursor="hand2")
                name_lbl.pack(anchor="w")

                btn_row = tk.Frame(info, bg=row_bg)
                btn_row.pack(anchor="w")

                # Inline quick-action buttons shown directly next to item
                inspect_btn = tk.Button(
                    btn_row, text="Inspect",
                    bg=PALETTE["card2"], fg=PALETTE["fg"],
                    relief=tk.FLAT, font=FONTS["small"], padx=6, pady=1,
                    cursor="hand2",
                    command=lambda it=item: self._inspect(it))
                inspect_btn.pack(side=tk.LEFT, padx=(0, 4))

                if item.Consumable:
                    use_btn = tk.Button(
                        btn_row, text="Use",
                        bg=PALETTE["card2"], fg=PALETTE["fg"],
                        relief=tk.FLAT, font=FONTS["small"], padx=6, pady=1,
                        cursor="hand2",
                        command=lambda it=item: self._use(it))
                    use_btn.pack(side=tk.LEFT, padx=(0, 4))
                elif item.EquipmentSlot is not None:
                    eq_btn = tk.Button(
                        btn_row, text="Equip",
                        bg=PALETTE["card2"], fg=PALETTE["fg"],
                        relief=tk.FLAT, font=FONTS["small"], padx=6, pady=1,
                        cursor="hand2",
                        command=lambda it=item: self._equip(it))
                    eq_btn.pack(side=tk.LEFT, padx=(0, 4))

                drop_btn = tk.Button(
                    btn_row, text="Drop",
                    bg=PALETTE["card2"], fg=PALETTE["fg"],
                    relief=tk.FLAT, font=FONTS["small"], padx=6, pady=1,
                    cursor="hand2",
                    command=lambda it=item: self._drop(it))
                drop_btn.pack(side=tk.LEFT, padx=(0, 4))

                # Left-click icon or name → inspect
                for widget in [icon, icon_lbl, name_lbl]:
                    widget.bind("<Button-1>", lambda e, it=item: self._inspect(it))
                # Right-click → context menu
                for widget in [row, icon, icon_lbl, name_lbl, btn_row]:
                    widget.bind("<Button-3>",
                                lambda e, it=item: self._item_menu(e, it))

        hr(self).pack(fill=tk.X)
        flat_btn(self, "Close", self.close, style="ghost").pack(pady=8)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _inspect(self, item: "Item") -> None:
        from dialogs.object_tooltip import ObjectTooltip
        ObjectTooltip(self.winfo_toplevel(), item)

    def _item_menu(self, event, item: "Item") -> None:
        menu = tk.Menu(self, tearoff=0, bg=PALETTE["card"],
                       fg=PALETTE["fg"], relief=tk.FLAT)
        menu.add_command(label="Inspect", command=lambda: self._inspect(item))
        menu.add_separator()
        if item.Consumable:
            menu.add_command(label="Use", command=lambda: self._use(item))
        else:
            menu.add_command(label="Equip", command=lambda: self._equip(item))
        menu.add_command(label="Drop", command=lambda: self._drop(item))
        menu.add_command(label="Discard", command=lambda: self._discard(item))
        menu.tk_popup(event.x_root, event.y_root)

    def _equip_slot_menu(self, event, item: "Item", slot_id: int) -> None:
        menu = tk.Menu(self, tearoff=0, bg=PALETTE["card"],
                       fg=PALETTE["fg"], relief=tk.FLAT)
        menu.add_command(label="Inspect", command=lambda: self._inspect(item))
        menu.add_separator()
        menu.add_command(label="Unequip → Backpack",
                         command=lambda: self._unequip(slot_id))
        menu.tk_popup(event.x_root, event.y_root)

    def _unequip(self, slot_id: int) -> None:
        item = self._player.Equipment.get(slot_id)
        if item:
            self._on_drop(item.id)
            self.close()

    def _use(self, item) -> None:
        self._on_use(item.id)
        self.close()

    def _equip(self, item) -> None:
        if item.EquipmentSlot is None:
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
