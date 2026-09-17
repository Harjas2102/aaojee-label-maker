"""
print_queue.py — Batch printing for Aaojee Label Maker.

Staff add products to the queue from the main window ("Add to Print Queue"),
each with a quantity and which labels to print, then print the whole batch
with one click.  The queue is saved to print_queue.json beside the database,
so it survives closing the program and can be reused day after day; it is
only emptied when someone clicks "Clear All".

Printing uses the product as saved in the database, and the Print Date and
Show / Hide options currently set on the main window.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox

# What each queue choice prints, in order.
LABEL_CHOICES: dict[str, list[str]] = {
    "Barcode":               ["Barcode"],
    "Ingredients":           ["Ingredient"],
    "Barcode + Ingredients": ["Barcode", "Ingredient"],
    "Combined":              ["Combined"],
}
MAX_QTY = 999


def default_choice(product: dict) -> str:
    """Cooked food (has ingredients) gets both labels; everything else a barcode."""
    return "Barcode + Ingredients" if (product.get("ingredients") or "").strip() else "Barcode"


class PrintQueue:
    """The list of queued items: {"product_id", "label", "qty", "last_printed"}."""

    def __init__(self, path: str):
        self.path = path
        self.items: list[dict] = []
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = []
        for it in raw if isinstance(raw, list) else []:
            try:
                item = {
                    "product_id":   int(it["product_id"]),
                    "label":        it["label"] if it.get("label") in LABEL_CHOICES else "Barcode",
                    "qty":          max(1, min(MAX_QTY, int(it.get("qty", 1)))),
                    "last_printed": str(it.get("last_printed") or ""),
                }
            except (KeyError, TypeError, ValueError):
                continue
            self.items.append(item)

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=2)
        os.replace(tmp, self.path)

    def add(self, product_id: int, label: str, qty: int) -> dict:
        """Add *qty* of a product; merges with an existing row for the same
        product and label choice."""
        qty = max(1, min(MAX_QTY, int(qty)))
        for it in self.items:
            if it["product_id"] == product_id and it["label"] == label:
                it["qty"] = min(MAX_QTY, it["qty"] + qty)
                self.save()
                return it
        it = {"product_id": product_id, "label": label, "qty": qty, "last_printed": ""}
        self.items.append(it)
        self.save()
        return it

    def remove(self, index: int):
        del self.items[index]
        self.save()

    def clear(self):
        self.items.clear()
        self.save()

    def total_labels(self) -> int:
        return sum(it["qty"] * len(LABEL_CHOICES[it["label"]]) for it in self.items)


class PrintQueueWindow(tk.Toplevel):
    """Non-modal window listing the queue, with Print All."""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.queue: PrintQueue = app.print_queue
        self.title("Print Queue")
        self.geometry("640x460")
        self.minsize(560, 380)
        self.transient(app.root)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Print Queue", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        self._info_var = tk.StringVar()
        ttk.Label(outer, textvariable=self._info_var, foreground="gray",
                  wraplength=600).pack(anchor=tk.W, pady=(0, 6))

        # List
        list_frame = ttk.Frame(outer)
        list_frame.pack(fill=tk.BOTH, expand=True)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        cols = ("name", "size", "label", "qty", "printed")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        for col, text, width, stretch in [
                ("name", "Product", 220, True), ("size", "Size", 60, False),
                ("label", "Labels", 150, False), ("qty", "Qty", 45, False),
                ("printed", "Last printed", 110, False)]:
            self.tree.heading(col, text=text, anchor=tk.W)
            self.tree.column(col, width=width, stretch=stretch)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Delete>", lambda _e: self._remove())

        # Editor for the selected row
        edit = ttk.Frame(outer)
        edit.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(edit, text="Selected:").pack(side=tk.LEFT)
        ttk.Button(edit, text="−", width=3, command=lambda: self._change_qty(-1)).pack(side=tk.LEFT, padx=(6, 0))
        self._qty_var = tk.StringVar()
        qty_entry = ttk.Entry(edit, textvariable=self._qty_var, width=5, justify=tk.CENTER)
        qty_entry.pack(side=tk.LEFT, padx=3)
        qty_entry.bind("<Return>", lambda _e: self._apply_qty())
        qty_entry.bind("<FocusOut>", lambda _e: self._apply_qty())
        ttk.Button(edit, text="+", width=3, command=lambda: self._change_qty(1)).pack(side=tk.LEFT)
        ttk.Label(edit, text="Labels:").pack(side=tk.LEFT, padx=(12, 4))
        self._label_var = tk.StringVar()
        self._label_combo = ttk.Combobox(edit, textvariable=self._label_var, state="readonly",
                                         width=20, values=self._label_values())
        self._label_combo.pack(side=tk.LEFT)
        self._label_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_label())
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._label_combo.bind(seq, lambda _e: "break")
        ttk.Button(edit, text="Remove", command=self._remove).pack(side=tk.LEFT, padx=(12, 0))

        # Bottom buttons
        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(6, 0))
        self._print_btn = tk.Button(
            bottom, text="Print All", font=("Arial", 12, "bold"), fg="white",
            bg="#276749", activebackground="#1e5037", activeforeground="white",
            relief=tk.RAISED, bd=2, cursor="hand2", padx=14, pady=6,
            command=self._print_all)
        self._print_btn.pack(side=tk.LEFT)
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Clear All", command=self._clear).pack(side=tk.RIGHT, padx=6)
        self._status_var = tk.StringVar()
        ttk.Label(outer, textvariable=self._status_var, foreground="#276749").pack(anchor=tk.W, pady=(6, 0))

        self.refresh()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _label_values(self) -> list[str]:
        values = ["Barcode", "Ingredients", "Barcode + Ingredients"]
        if self.app.settings.get("show_combined_button", False):
            values.append("Combined")
        return values

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        return self.tree.index(sel[0]) if sel else None

    def refresh(self, keep_index: int | None = None):
        if keep_index is None:
            keep_index = self._selected_index()
        self.tree.delete(*self.tree.get_children())
        for it in self.queue.items:
            p = self.app.db.get_product(it["product_id"])
            name = p["name"] if p else "(deleted product — will be skipped)"
            size = (p.get("size") or "") if p else ""
            self.tree.insert("", tk.END, values=(name, size, it["label"], it["qty"],
                                                 it.get("last_printed", "")))
        n = len(self.queue.items)
        total = self.queue.total_labels()
        self._print_btn.config(text=f"Print All  ({total} label{'s' if total != 1 else ''})",
                               state=tk.NORMAL if n else tk.DISABLED)
        self._info_var.set(
            f"{n} item{'s' if n != 1 else ''}.  Prints the saved products using the Print Date "
            f"({self.app.print_date_text()}) and Show / Hide options on the main window.  "
            "The list stays here until you click Clear All.")
        children = self.tree.get_children()
        if children:
            keep_index = 0 if keep_index is None else keep_index
            iid = children[min(keep_index, len(children) - 1)]
            self.tree.selection_set(iid)
            self.tree.see(iid)
        self._on_select()
        self.app.on_print_queue_changed()

    def _on_select(self, _e=None):
        i = self._selected_index()
        if i is None or i >= len(self.queue.items):
            self._qty_var.set("")
            self._label_var.set("")
            return
        it = self.queue.items[i]
        self._qty_var.set(str(it["qty"]))
        self._label_var.set(it["label"])

    def _change_qty(self, delta: int):
        i = self._selected_index()
        if i is None:
            return
        it = self.queue.items[i]
        it["qty"] = max(1, min(MAX_QTY, it["qty"] + delta))
        self.queue.save()
        self.refresh(i)

    def _apply_qty(self):
        i = self._selected_index()
        if i is None:
            return
        try:
            qty = max(1, min(MAX_QTY, int(self._qty_var.get())))
        except ValueError:
            self._on_select()
            return
        if qty != self.queue.items[i]["qty"]:
            self.queue.items[i]["qty"] = qty
            self.queue.save()
            self.refresh(i)

    def _apply_label(self):
        i = self._selected_index()
        if i is None or self._label_var.get() not in LABEL_CHOICES:
            return
        self.queue.items[i]["label"] = self._label_var.get()
        self.queue.save()
        self.refresh(i)

    def _remove(self):
        i = self._selected_index()
        if i is None:
            return
        self.queue.remove(i)
        self.refresh(i)

    def _clear(self):
        if not self.queue.items:
            return
        if messagebox.askyesno("Clear Print Queue", "Remove every item from the print queue?",
                               parent=self):
            self.queue.clear()
            self.refresh()

    def set_status(self, text: str):
        self._status_var.set(text)
        self.update_idletasks()

    def _print_all(self):
        self._apply_qty()
        printed_indexes = self.app.print_queue_items(self)
        now = datetime.now()
        stamp = (f"{now.month}/{now.day} {now.hour % 12 or 12}:{now.minute:02d} "
                 f"{'AM' if now.hour < 12 else 'PM'}")
        for i in printed_indexes:
            self.queue.items[i]["last_printed"] = stamp
        if printed_indexes:
            self.queue.save()
        self.refresh()
