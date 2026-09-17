"""
print_history.py — Record of every label print job (U-009).

Each successful print — Print Barcode / Ingredients / Combined, Test Print, or
a Print Queue row — adds one row to the print_history table: when, which
product (name, size, barcode, price at the time), label type and size, how
many copies, the Print Date and the exact date line printed ("Best By :
9/27/2026"), the printer, and where it was printed from.

File → Print History… lists them with a time range and a search, shows the
total labels, and can save the list as a CSV spreadsheet — useful for tracing
a batch if there is ever a problem with a product.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

RANGES = ["Today", "Last 7 days", "Last 30 days", "All"]

EXPORT_COLUMNS = [
    ("printed_at", "Printed at"), ("product_name", "Product"), ("size", "Size"),
    ("barcode_number", "Barcode"), ("price", "Price"), ("label_type", "Label"),
    ("label_size", "Label size"), ("copies", "Copies"), ("print_date", "Print date"),
    ("date_line", "Date on label"), ("printer", "Printer"), ("source", "Printed from"),
]


def range_start(choice: str, now: datetime | None = None) -> str | None:
    now = now or datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = {"Today": midnight,
             "Last 7 days": midnight - timedelta(days=6),
             "Last 30 days": midnight - timedelta(days=29)}.get(choice)
    return start.isoformat(sep=" ", timespec="seconds") if start else None


def export_history(path: str, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([title for _, title in EXPORT_COLUMNS])
        for r in rows:
            w.writerow(["" if r[key] is None else (f"{r[key]:.2f}" if key == "price" else r[key])
                        for key, _ in EXPORT_COLUMNS])


class PrintHistoryWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Print History")
        self.geometry("980x520")
        self.minsize(760, 380)
        self.transient(app.root)
        self._rows: list[dict] = []

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Show:").pack(side=tk.LEFT)
        self._range = tk.StringVar(value="Today")
        rng = ttk.Combobox(top, textvariable=self._range, values=RANGES, state="readonly", width=14)
        rng.pack(side=tk.LEFT, padx=(4, 12))
        rng.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            rng.bind(seq, lambda _e: "break")
        ttk.Label(top, text="Search product or barcode:").pack(side=tk.LEFT)
        self._query = tk.StringVar()
        self._query.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(top, textvariable=self._query, width=24).pack(side=tk.LEFT, padx=4)

        lf = ttk.Frame(outer)
        lf.pack(fill=tk.BOTH, expand=True, pady=6)
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)
        cols = [("printed_at", "Printed at", 130), ("product_name", "Product", 190),
                ("size", "Size", 70), ("barcode_number", "Barcode", 65),
                ("label_type", "Label", 75), ("copies", "Copies", 50),
                ("date_line", "Date on label", 130), ("printer", "Printer", 120),
                ("source", "From", 75)]
        self.tree = ttk.Treeview(lf, columns=[c for c, _, _ in cols], show="headings")
        for key, text, width in cols:
            self.tree.heading(key, text=text, anchor=tk.W)
            self.tree.column(key, width=width, stretch=key == "product_name")
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X)
        self._total = tk.StringVar()
        ttk.Label(bottom, textvariable=self._total, font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Save as Spreadsheet…", command=self._export).pack(side=tk.RIGHT, padx=6)
        ttk.Button(bottom, text="Refresh", command=self.refresh).pack(side=tk.RIGHT)

        self.refresh()

    def refresh(self):
        self._rows = self.app.db.get_print_history(range_start(self._range.get()),
                                                   self._query.get().strip())
        self.tree.delete(*self.tree.get_children())
        for r in self._rows:
            self.tree.insert("", tk.END, values=(
                r["printed_at"], r["product_name"], r["size"], r["barcode_number"],
                r["label_type"], r["copies"], r["date_line"], r["printer"], r["source"]))
        jobs = len(self._rows)
        labels = sum(r["copies"] for r in self._rows)
        self._total.set(f"{jobs} print job{'s' if jobs != 1 else ''}, "
                        f"{labels} label{'s' if labels != 1 else ''}")

    def _export(self):
        if not self._rows:
            messagebox.showinfo("Print History", "Nothing to save.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Save print history", defaultextension=".csv",
            initialfile=f"print_history_{datetime.now():%Y%m%d}.csv",
            filetypes=[("Spreadsheet (CSV)", "*.csv")])
        if path:
            export_history(path, self._rows)
            messagebox.showinfo("Print History", f"Saved {len(self._rows)} rows to:\n{path}",
                                parent=self)
