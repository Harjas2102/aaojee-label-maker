"""
price_tools.py — Change many prices at once, and export prices for the POS (U-011).

Tools → Change Prices…   (needs the manager PIN when one is set)
    Pick which products (the list as currently searched / filtered, a
    category, or everything), raise or lower by a percent or a dollar amount,
    choose rounding, untick any rows to leave alone, and Apply.  Every change
    is recorded in the price_history table; "Undo Last Change" puts the old
    prices back.  After applying, the changes can be exported to a spreadsheet
    to type into the POS (which this program cannot update).

Tools → Export Price List…
    Every product's barcode, name, size and price as a CSV spreadsheet.
"""

from __future__ import annotations

import csv
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, InvalidOperation

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

ROUNDING = {
    "Nearest cent":            "cent",
    "Up to .49 or .99":        "49_99",
    "Up to .99":               "99",
}


def round_price(value: Decimal, mode: str) -> Decimal:
    """Round a price.  'cent' → nearest cent; '49_99' → up to the next .49 or
    .99; '99' → up to the next .99.  Never goes below 0.01."""
    value = max(value, Decimal("0.01"))
    if mode == "cent":
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cents = int((value * 100).to_integral_value(rounding=ROUND_CEILING))
    dollars, rem = divmod(cents, 100)
    if mode == "49_99":
        rem = 49 if rem <= 49 else 99
    else:
        rem = 99
    return Decimal(dollars) + Decimal(rem) / 100


def new_price(old: float, kind: str, amount: Decimal, rounding: str) -> Decimal:
    """*kind* is 'percent' or 'dollars'; *amount* may be negative."""
    old_d = Decimal(str(old))
    raw = old_d * (1 + amount / 100) if kind == "percent" else old_d + amount
    return round_price(raw, rounding)


def export_price_list(path: str, products: list[dict]):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Barcode", "Name", "Size", "Price", "Category"])
        for p in products:
            price = "" if p.get("price") is None else f"{p['price']:.2f}"
            w.writerow([p.get("barcode_number") or "", p["name"], p.get("size") or "",
                        price, p.get("category") or ""])


def export_price_changes(path: str, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Barcode", "Name", "Size", "Old Price", "New Price", "Changed"])
        for r in rows:
            w.writerow([r["barcode_number"], r["product_name"], r["size"],
                        "" if r["old_price"] is None else f"{r['old_price']:.2f}",
                        "" if r["new_price"] is None else f"{r['new_price']:.2f}",
                        r["changed_at"]])


class PriceChangeDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Change Prices")
        self.geometry("720x600")
        self.minsize(640, 500)
        self.transient(app.root)
        self._excluded: set[int] = set()
        self._rows: list[dict] = []

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # Which products
        which = ttk.LabelFrame(outer, text="Which products", padding=6)
        which.pack(fill=tk.X)
        self._scope = tk.StringVar(value="list")
        visible = app.visible_products()
        ttk.Radiobutton(which, text=f"Products in the list right now ({len(visible)})",
                        value="list", variable=self._scope,
                        command=self._refresh).grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(which, text="Category:", value="category", variable=self._scope,
                        command=self._refresh).grid(row=1, column=0, sticky=tk.W)
        self._category = tk.StringVar(value=app.category_names()[0])
        cat = ttk.Combobox(which, textvariable=self._category, state="readonly",
                           values=app.category_names(), width=24)
        cat.grid(row=1, column=1, sticky=tk.W, padx=4)
        cat.bind("<<ComboboxSelected>>", lambda _e: (self._scope.set("category"), self._refresh()))
        ttk.Radiobutton(which, text="All products", value="all", variable=self._scope,
                        command=self._refresh).grid(row=2, column=0, sticky=tk.W)

        # How much
        how = ttk.LabelFrame(outer, text="Change", padding=6)
        how.pack(fill=tk.X, pady=6)
        self._kind = tk.StringVar(value="percent")
        self._amount = tk.StringVar(value="5")
        ttk.Radiobutton(how, text="By percent", value="percent", variable=self._kind,
                        command=self._refresh).grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(how, text="By dollars", value="dollars", variable=self._kind,
                        command=self._refresh).grid(row=0, column=1, sticky=tk.W, padx=(12, 0))
        ttk.Label(how, text="Amount:").grid(row=0, column=2, sticky=tk.W, padx=(18, 4))
        amt = ttk.Entry(how, textvariable=self._amount, width=8)
        amt.grid(row=0, column=3, sticky=tk.W)
        self._amount.trace_add("write", lambda *_: self._refresh())
        ttk.Label(how, text="(use a minus sign to lower prices, e.g. -5)",
                  foreground="gray").grid(row=0, column=4, sticky=tk.W, padx=6)
        ttk.Label(how, text="Rounding:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self._rounding = tk.StringVar(value="Up to .49 or .99")
        rnd = ttk.Combobox(how, textvariable=self._rounding, state="readonly",
                           values=list(ROUNDING), width=18)
        rnd.grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=(6, 0))
        rnd.bind("<<ComboboxSelected>>", lambda _e: self._refresh())
        for combo in (cat, rnd):
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                combo.bind(seq, lambda _e: "break")

        # Preview
        ttk.Label(outer, text="Preview — double-click a row to leave that product out:",
                  font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(4, 2))
        lf = ttk.Frame(outer)
        lf.pack(fill=tk.BOTH, expand=True)
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)
        cols = ("use", "name", "size", "barcode", "old", "new")
        self.tree = ttk.Treeview(lf, columns=cols, show="headings", selectmode="browse")
        for col, text, width, stretch in [("use", "Change", 55, False), ("name", "Product", 220, True),
                                          ("size", "Size", 90, False), ("barcode", "Barcode", 70, False),
                                          ("old", "Old", 60, False), ("new", "New", 60, False)]:
            self.tree.heading(col, text=text, anchor=tk.W)
            self.tree.column(col, width=width, stretch=stretch)
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self._toggle_row)
        self.tree.bind("<space>", self._toggle_row)

        self._summary = tk.StringVar()
        ttk.Label(outer, textvariable=self._summary).pack(anchor=tk.W, pady=(4, 0))

        btns = ttk.Frame(outer)
        btns.pack(fill=tk.X, pady=(6, 0))
        tk.Button(btns, text="Apply Price Changes", font=("Arial", 10, "bold"), fg="white",
                  bg="#276749", activebackground="#1e5037", activeforeground="white",
                  relief=tk.RAISED, bd=2, padx=10, pady=4, command=self._apply).pack(side=tk.LEFT)
        ttk.Button(btns, text="Close", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Export Last Change for POS…",
                   command=self._export_last).pack(side=tk.RIGHT, padx=6)
        ttk.Button(btns, text="Undo Last Change…", command=self._undo_last).pack(side=tk.RIGHT)

        self._refresh()

    # ── data ─────────────────────────────────────────────────────────────────

    def _scope_products(self) -> list[dict]:
        scope = self._scope.get()
        if scope == "list":
            products = self.app.visible_products()
        elif scope == "category":
            pred = self.app.category_predicate(self._category.get())
            products = [p for p in self.app.db.get_all_products() if pred(p)]
        else:
            products = self.app.db.get_all_products()
        return [p for p in products if p.get("price") is not None]

    def _amount_value(self) -> Decimal | None:
        try:
            return Decimal(self._amount.get().strip().replace("$", "").replace("%", ""))
        except InvalidOperation:
            return None

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        amount = self._amount_value()
        rounding = ROUNDING[self._rounding.get()]
        self._rows = []
        for p in self._scope_products():
            new = (new_price(p["price"], self._kind.get(), amount, rounding)
                   if amount is not None else None)
            self._rows.append({"product": p, "new": new})
            use = p["id"] not in self._excluded
            self.tree.insert("", tk.END, iid=str(p["id"]), values=(
                "✓" if use else "—", p["name"], p.get("size") or "", p.get("barcode_number") or "",
                f"{p['price']:.2f}", "" if new is None else f"{new:.2f}"))
        n = len(self._changes())
        self._summary.set("Type an amount to see the new prices." if amount is None else
                          f"{n} price{'s' if n != 1 else ''} will change.")

    def _changes(self) -> list[dict]:
        return [{"id": r["product"]["id"], "new_price": float(r["new"]), "product": r["product"]}
                for r in self._rows
                if r["new"] is not None and r["product"]["id"] not in self._excluded
                and float(r["new"]) != r["product"]["price"]]

    def _toggle_row(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        self._excluded.symmetric_difference_update({pid})
        self._refresh()
        if self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
            self.tree.see(sel[0])

    # ── actions ──────────────────────────────────────────────────────────────

    def _apply(self):
        changes = self._changes()
        if not changes:
            messagebox.showinfo("Change Prices", "No prices would change.", parent=self)
            return
        kind = "%" if self._kind.get() == "percent" else "$"
        desc = (f"{self._amount.get().strip()}{kind} ({self._rounding.get()}) on "
                f"{len(changes)} products")
        if not messagebox.askyesno(
                "Change Prices",
                f"Change {len(changes)} prices?\n\n{desc}\n\n"
                "A backup of the database is saved first, and this can be undone with "
                "\"Undo Last Change\".", parent=self):
            return
        try:
            self.app.backup_now()
        except Exception as e:
            messagebox.showerror("Change Prices", f"Could not back up the database, so no "
                                                  f"prices were changed:\n{e}", parent=self)
            return
        self.app.db.apply_price_batch(changes, desc)
        self._excluded.clear()
        self.app.refresh_products()
        self._refresh()
        if messagebox.askyesno(
                "Change Prices",
                f"{len(changes)} prices changed.\n\nRemember to change them in the POS too.\n\n"
                "Save a spreadsheet of the changes to help with that?", parent=self):
            self._export_last()

    def _undo_last(self):
        rows = self.app.db.get_last_price_batch()
        if not rows:
            messagebox.showinfo("Undo Price Change", "There is no price change to undo.", parent=self)
            return
        if not messagebox.askyesno(
                "Undo Price Change",
                f"Put back the old prices from this change?\n\n{rows[0]['description']}\n"
                f"made {rows[0]['changed_at']}", parent=self):
            return
        restored, kept = self.app.db.undo_price_batch(rows[0]["batch_id"])
        msg = f"{restored} price{'s' if restored != 1 else ''} put back."
        if kept:
            msg += ("\n\nThese were changed again afterwards and were left as they are:\n"
                    + "\n".join(kept[:15]) + ("\n…" if len(kept) > 15 else ""))
        msg += "\n\nRemember to change them back in the POS too."
        messagebox.showinfo("Undo Price Change", msg, parent=self)
        self.app.refresh_products()
        self._refresh()

    def _export_last(self):
        rows = self.app.db.get_last_price_batch()
        if not rows:
            messagebox.showinfo("Export", "There is no price change to export.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Save price changes", defaultextension=".csv",
            initialfile=f"price_changes_{rows[0]['batch_id'][:15]}.csv",
            filetypes=[("Spreadsheet (CSV)", "*.csv")])
        if path:
            export_price_changes(path, rows)
            messagebox.showinfo("Export", f"Saved {len(rows)} price changes to:\n{path}", parent=self)
