"""
Store database update (2026-09-17).

The U-006 cleanup and U-013 categories were first run on an old copy of the
database on the development PC.  Meanwhile the cashiers kept adding and editing
products on the store PC.  This script re-runs the same two scripts on the
store's own database, so nothing the cashiers did is lost.

    python data_changes/2026-09-17_store_update/build_store_db.py          build
    python data_changes/2026-09-17_store_update/build_store_db.py --check  only re-run the checks

Input (never changed, read-only):
    store_original_products.db   the store's products.db as copied on 2026-09-17
Output:
    september_store_copy/READY_FOR_STORE/products.db   the file to put on the store PC
    The usual U-006 and U-013 files, in their own folders, so that
    `cleanup.py --undo` and `assign_categories.py --undo` work on the store's database:
      data_changes/2026-09-17_U-006_data_cleanup/changes.csv, products_before_U-006.db
      data_changes/2026-09-17_U-013_categories/changes.csv, products_before_U-013.db
    (The first run, on the old copy, is kept in each folder's first_run_on_old_copy/.)

See UPGRADE_TRACKER.md → "Store database update".
"""

from __future__ import annotations

import csv
import importlib.util
import os
import shutil
import sqlite3
import stat
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ORIGINAL = os.path.join(HERE, "store_original_products.db")
OUT_DIR = os.path.join(ROOT, "september_store_copy", "READY_FOR_STORE")
OUT_DB = os.path.join(OUT_DIR, "products.db")
STORE_SETTINGS = os.path.join(HERE, "store_original_settings.json")
U006 = os.path.join(ROOT, "data_changes", "2026-09-17_U-006_data_cleanup")
U013 = os.path.join(ROOT, "data_changes", "2026-09-17_U-013_categories")
LOG6, BEFORE6 = os.path.join(U006, "changes.csv"), os.path.join(U006, "products_before_U-006.db")
LOG13, BEFORE13 = os.path.join(U013, "changes.csv"), os.path.join(U013, "products_before_U-013.db")
sys.path.insert(0, os.path.join(ROOT, "source"))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build():
    for f in (OUT_DB, OUT_DB + "-wal", OUT_DB + "-shm", LOG6, BEFORE6, LOG13, BEFORE13):
        if os.path.exists(f):
            os.remove(f)
    os.makedirs(OUT_DIR, exist_ok=True)
    shutil.copyfile(ORIGINAL, OUT_DB)
    os.chmod(OUT_DB, stat.S_IREAD | stat.S_IWRITE)

    # U-006: the same rules, pointed at the store's copy
    cleanup = _load("cleanup", os.path.join(U006, "cleanup.py"))
    cleanup.DB_PATH, cleanup.CSV_PATH, cleanup.BACKUP_PATH = OUT_DB, LOG6, BEFORE6
    cleanup.apply()

    # U-013: upgrades the database to schema v2, then fills in categories
    cats = _load("assign_categories", os.path.join(U013, "assign_categories.py"))
    cats.DB_PATH, cats.CSV_PATH, cats.BACKUP_PATH = OUT_DB, LOG13, BEFORE13
    cats.ROOT = os.path.join(HERE, "_tmp")                 # its pre-upgrade copy goes here, then is removed
    sys.argv = [sys.argv[0], "--apply"]
    cats.main()
    shutil.rmtree(cats.ROOT, ignore_errors=True)

    # One self-contained file for the flash drive (no -wal / -shm beside it)
    conn = sqlite3.connect(OUT_DB)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.close()


def check() -> int:
    problems: list[str] = []

    def ok(cond, msg):
        print(("  ok    " if cond else "  FAIL  ") + msg)
        if not cond:
            problems.append(msg)

    def rows(path):
        c = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        c.row_factory = sqlite3.Row
        out = {r["id"]: dict(r) for r in c.execute("SELECT * FROM products")}
        c.close()
        return out

    before, after = rows(ORIGINAL), rows(OUT_DB)
    conn = sqlite3.connect(f"file:{OUT_DB}?mode=ro&immutable=1", uri=True)
    ok(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity check")
    ok(conn.execute("PRAGMA user_version").fetchone()[0] == 2, "schema version 2")
    conn.close()
    ok(not os.path.exists(OUT_DB + "-wal"), "single file (no -wal beside it)")

    missing = [i for i in before if i not in after or after[i]["deleted_at"]]
    ok(not missing, f"all {len(before)} store products still there, none in Trash {missing or ''}")
    moved = [(i, k) for i in before if i in after for k in ("barcode_number", "price")
             if before[i][k] != after[i][k]]
    ok(not moved, f"every barcode number and price unchanged {moved or ''}")
    for k in ("created_at",):
        ok(all(before[i][k] == after[i][k] for i in before), f"{k} unchanged")

    # Every other difference must be written in one of the change logs
    with open(LOG6, encoding="utf-8-sig") as f:
        log6 = list(csv.DictReader(f))
    with open(LOG13, encoding="utf-8-sig") as f:
        log13 = {int(r["id"]): r["new"] for r in csv.DictReader(f)}
    logged = {(int(r["id"]), r["field"]): r["new"] for r in log6 if r["action"] == "update"}
    inserted = {int(r["id"]) for r in log6 if r["action"] == "insert"}
    unexplained = []
    for i, a in after.items():
        if i in inserted:
            continue
        for k, v in a.items():
            if k in ("updated_at",):
                continue
            old = before[i].get(k, None if k == "deleted_at" else "")
            if v == old:
                continue
            if (k == "category" and log13.get(i) == v) or logged.get((i, k)) == v:
                continue
            unexplained.append((i, k, old, v))
    ok(not unexplained, f"every change is in the logs {unexplained or ''}")
    ok(set(after) - set(before) == inserted, f"{len(inserted)} products added, all logged")
    ok(all(after[i]["barcode_number"] == "" and after[i]["price"] is None for i in inserted),
       "added products have no barcode or price (as in U-006)")
    codes = [a["barcode_number"] for a in after.values() if a["barcode_number"]]
    ok(len(codes) == len(set(codes)), "no barcode number used twice")

    # The new program opens the file and renders every label for every product
    import json
    import label_renderer as lr
    from database import Database
    tmp = os.path.join(HERE, "_check_copy.db")
    shutil.copyfile(OUT_DB, tmp)
    try:
        db = Database(tmp)
        products = db.get_all_products()
        ok(len(products) == len(after), f"program lists {len(products)} products")
        with open(STORE_SETTINGS, encoding="utf-8") as f:
            s = json.load(f)
        flags = dict(barcode=True, price=True, dollar_sign=True, date=True, address=True)
        errors, count = [], 0
        for p in products:
            for lt, size in [("Barcode", "2.25x1.25"), ("Barcode", "2.25x3.00"), ("Ingredient", "2.25x1.25"),
                             ("Ingredient", "2.25x3.00"), ("Combined", "2.25x3.00")]:
                if lt == "Barcode" and not p["barcode_number"]:
                    continue
                try:
                    lr.render_label(p, lt, size, date.today(), flags, s, s.get("address_line", ""), 10,
                                    203, s.get("label_spacing", 1.0), s.get("label_margin_in", 0.0),
                                    min_module_in=0.013)
                    count += 1
                except Exception as e:
                    errors.append((p["id"], p["name"], lt, size, f"{type(e).__name__}: {e}"))
        ok(not errors, f"{count} labels rendered at 203 DPI with the store's settings {errors[:5] or ''}")
    finally:
        for f in (tmp, tmp + "-wal", tmp + "-shm"):
            if os.path.exists(f):
                os.remove(f)

    print("\nALL CHECKS PASSED" if not problems else f"\n{len(problems)} CHECK(S) FAILED")
    return 1 if problems else 0


if __name__ == "__main__":
    if "--check" not in sys.argv:
        build()
    sys.exit(check())
