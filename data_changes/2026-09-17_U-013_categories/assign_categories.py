"""
U-013 — Give existing products a starting category (2026-09-17).

Usage (from the project folder, with the program CLOSED):
    python data_changes/2026-09-17_U-013_categories/assign_categories.py           dry run
    python data_changes/2026-09-17_U-013_categories/assign_categories.py --apply   assign
    python data_changes/2026-09-17_U-013_categories/assign_categories.py --undo    clear them again

The guesses come from source/categories.py (suggest_category), which looks at
each product's name, size and date mode.  Products it can't place are left
with no category (Show: "No category" lists them).  Categories only filter the
product list and are never printed, so a wrong guess is harmless — fix it on
the product form.

--apply first upgrades the database if needed (the program does the same on
start-up), saves products_before_U-013.db in this folder, only fills in
products that have no category yet, and writes changes.csv.
--undo clears a category only if it still holds the value set here.
"""

from __future__ import annotations

import csv
import os
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "source"))

from categories import suggest_category          # noqa: E402
from database import Database                    # noqa: E402

DB_PATH = os.path.join(ROOT, "products.db")
CSV_PATH = os.path.join(HERE, "changes.csv")
BACKUP_PATH = os.path.join(HERE, "products_before_U-013.db")


def plan(db: Database) -> list[dict]:
    out = []
    for p in db.get_all_products():
        if p["category"]:
            continue
        guess = suggest_category(p["name"], p["size"], p["date_mode"])
        if guess:
            out.append(dict(id=p["id"], name=p["name"], size=p["size"], old="", new=guess))
    return out


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    db = Database(DB_PATH, backup_dir=os.path.join(ROOT, "backups"))

    if arg == "--undo":
        if not os.path.exists(CSV_PATH):
            sys.exit("No changes.csv - nothing to undo.")
        with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        conn = sqlite3.connect(DB_PATH)
        with conn:
            done = sum(conn.execute("UPDATE products SET category = ? WHERE id = ? AND category = ?",
                                    (r["old"], int(r["id"]), r["new"])).rowcount for r in rows)
        conn.close()
        os.replace(CSV_PATH, CSV_PATH.replace(".csv", "_undone.csv"))
        print(f"Cleared {done} of {len(rows)} categories (others were changed by hand since).")
        return

    changes = plan(db)
    counts = Counter(c["new"] for c in changes)
    if arg != "--apply":
        for c in changes:
            print(f"{c['new']:10} {c['name']} {c['size']}")
        print(f"\n{len(changes)} products would get a category: {dict(counts)}.  Run with --apply.")
        return

    if os.path.exists(CSV_PATH):
        sys.exit("changes.csv already exists - U-013 was already applied. Run --undo first.")
    db._copy_to(BACKUP_PATH)
    for c in changes:
        db.save_product({"id": c["id"], "category": c["new"]})
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "size", "old", "new"])
        w.writeheader()
        w.writerows(changes)
    print(f"Assigned {len(changes)} categories: {dict(counts)}.\nBackup: {BACKUP_PATH}\nLog: {CSV_PATH}")


if __name__ == "__main__":
    main()
