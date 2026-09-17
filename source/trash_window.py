"""
trash_window.py — Deleted products can be restored (U-012).

Delete on the main window now moves a product to the Trash instead of erasing
it.  File → Trash… lists deleted products with Restore, Delete Forever and
Empty Trash.  Deleting forever needs the manager PIN when one is set.

Products in the Trash don't appear in the list, search, scans or the print
queue, but their barcode numbers stay reserved so "Auto" never hands one out
again while it could still be restored.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox


class TrashWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Trash")
        self.geometry("680x420")
        self.minsize(560, 320)
        self.transient(app.root)

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text="Deleted products", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(outer, text="Restore puts a product back in the list exactly as it was.",
                  foreground="gray").pack(anchor=tk.W, pady=(0, 6))

        lf = ttk.Frame(outer)
        lf.pack(fill=tk.BOTH, expand=True)
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)
        cols = [("name", "Product", 220), ("size", "Size", 80), ("barcode", "Barcode", 70),
                ("price", "Price", 60), ("deleted", "Deleted", 140)]
        self.tree = ttk.Treeview(lf, columns=[c for c, _, _ in cols], show="headings",
                                 selectmode="extended")
        for key, text, width in cols:
            self.tree.heading(key, text=text, anchor=tk.W)
            self.tree.column(key, width=width, stretch=key == "name")
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _e: self._restore())

        btns = ttk.Frame(outer)
        btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btns, text="Restore", command=self._restore).pack(side=tk.LEFT)
        ttk.Button(btns, text="Delete Forever…", command=self._purge).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Close", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Empty Trash…", command=self._empty).pack(side=tk.RIGHT, padx=6)
        self._status = tk.StringVar()
        ttk.Label(outer, textvariable=self._status, foreground="#276749").pack(anchor=tk.W, pady=(6, 0))

        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for p in self.app.db.get_trash():
            price = "" if p["price"] is None else f"${p['price']:.2f}"
            self.tree.insert("", tk.END, iid=str(p["id"]), values=(
                p["name"], p["size"], p["barcode_number"], price, p["deleted_at"]))

    def _selected(self) -> list[dict]:
        out = []
        for iid in self.tree.selection():
            p = self.app.db.get_product(int(iid), include_deleted=True)
            if p and p.get("deleted_at"):
                out.append(p)
        return out

    def _restore(self):
        products = self._selected()
        if not products:
            messagebox.showinfo("Trash", "Select a product to restore.", parent=self)
            return
        restored = []
        for p in products:
            conflict = self.app.db.get_barcode_conflict(p["barcode_number"], exclude_id=p["id"])
            if conflict and not conflict.get("deleted_at"):
                if not messagebox.askyesno(
                        "Restore",
                        f"{p['name']} uses barcode {p['barcode_number']}, which "
                        f"{conflict['name']} now also uses.\n\nRestore it anyway?",
                        icon="warning", parent=self):
                    continue
            self.app.db.restore_product(p["id"])
            restored.append(p["name"])
        self.refresh()
        self.app.refresh_products()
        if restored:
            self._status.set("✓ Restored: " + ", ".join(restored))

    def _purge(self):
        products = self._selected()
        if not products:
            messagebox.showinfo("Trash", "Select a product to delete forever.", parent=self)
            return
        if not self.app.lock.require(self, "Deleting products forever"):
            return
        names = "\n".join(f"  {p['name']}" for p in products[:10])
        if not messagebox.askyesno("Delete Forever",
                                   f"Permanently delete:\n\n{names}\n\nThis cannot be undone.",
                                   icon="warning", parent=self):
            return
        for p in products:
            self.app.db.purge_product(p["id"])
        self.refresh()
        self._status.set(f"Deleted {len(products)} product(s) forever.")

    def _empty(self):
        count = len(self.tree.get_children())
        if not count:
            return
        if not self.app.lock.require(self, "Emptying the Trash"):
            return
        if not messagebox.askyesno("Empty Trash",
                                   f"Permanently delete all {count} products in the Trash?\n\n"
                                   "This cannot be undone.", icon="warning", parent=self):
            return
        self.app.db.empty_trash()
        self.refresh()
        self._status.set(f"Trash emptied ({count} products).")
