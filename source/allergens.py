"""
allergens.py — Allergen list and picker for the "Contains:" label line (U-007).

The product's allergens are stored as plain text ("Milk, Tree Nuts") and
printed on ingredient and combined labels as a bold line:
    Contains: Milk, Tree Nuts
The picker offers the nine major US food allergens; anything else can be typed
into the field directly.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

MAJOR_ALLERGENS = ["Milk", "Eggs", "Fish", "Shellfish", "Tree Nuts",
                   "Peanuts", "Wheat", "Soybeans", "Sesame"]


def split_allergens(text: str) -> list[str]:
    return [a.strip() for a in (text or "").split(",") if a.strip()]


class AllergenPicker(tk.Toplevel):
    """Checkbox list of the major allergens.  Calls on_done(text) on OK."""

    def __init__(self, parent, current: str, on_done):
        super().__init__(parent)
        self.title("Allergens")
        self.resizable(False, False)
        self.transient(parent)
        self._on_done = on_done

        chosen = split_allergens(current)
        chosen_lower = {a.lower() for a in chosen}
        # Anything typed that isn't in the standard list is kept as-is.
        self._extras = [a for a in chosen if a.lower() not in {m.lower() for m in MAJOR_ALLERGENS}]

        f = ttk.Frame(self, padding=12)
        f.pack()
        ttk.Label(f, text="Tick every allergen this product contains:",
                  font=("Arial", 9, "bold")).grid(row=0, column=0, columnspan=3, sticky=tk.W,
                                                  pady=(0, 6))
        self._vars: dict[str, tk.BooleanVar] = {}
        for i, name in enumerate(MAJOR_ALLERGENS):
            var = tk.BooleanVar(value=name.lower() in chosen_lower)
            self._vars[name] = var
            ttk.Checkbutton(f, text=name, variable=var).grid(
                row=1 + i // 3, column=i % 3, sticky=tk.W, padx=(0, 16), pady=2)
        if self._extras:
            ttk.Label(f, text="Also kept: " + ", ".join(self._extras), foreground="gray").grid(
                row=5, column=0, columnspan=3, sticky=tk.W, pady=(6, 0))
        ttk.Label(f, text='Printed as a bold "Contains:" line on ingredient and combined labels.',
                  foreground="gray").grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=(8, 0))

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=4)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._ok())
        self.grab_set()
        self.focus_set()

    def _ok(self):
        picked = [name for name, var in self._vars.items() if var.get()]
        self._on_done(", ".join(picked + self._extras))
        self.destroy()
