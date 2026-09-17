"""
U-006 — One-time product data cleanup (2026-09-17).

Usage (from the project folder, with the program CLOSED):
    python data_changes/2026-09-17_U-006_data_cleanup/cleanup.py            dry run: show changes
    python data_changes/2026-09-17_U-006_data_cleanup/cleanup.py --apply    make the changes
    python data_changes/2026-09-17_U-006_data_cleanup/cleanup.py --undo     put the old values back

--apply first saves a permanent copy of products.db in this folder
(products_before_U-006.db) and writes every change to changes.csv.
--undo reads changes.csv and restores each old value, but only where the
field still holds the value this script wrote (so later hand edits are kept),
and deletes the products this script added if nobody has edited them since.

See UPGRADE_TRACKER.md → U-006 for what each change is and why.
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(ROOT, "products.db")
CSV_PATH = os.path.join(HERE, "changes.csv")
BACKUP_PATH = os.path.join(HERE, "products_before_U-006.db")
STAMP = datetime.now().isoformat(sep=" ", timespec="seconds")
TODAY = "2026-09-17"

# ── 1. Size spellings ─────────────────────────────────────────────────────────
_UNITS = {
    "LB": "LB", "LBS": "LB",
    "OZ": "OZ",
    "G": "GM", "GM": "GM", "GMS": "GM", "GRAMS": "GM",
    "ML": "ML",
    "PCS": "PCS", "PIECES": "PCS",
    "PACKS": "PACKS",
}
_QTY = re.compile(r"(\d+(?:\.\d+)?)\s*(LBS|LB|OZ|GRAMS|GMS|GM|G|ML|PCS|PIECES|PACKS)\.?")


def normalize_size(size: str) -> str:
    """'2Lb' / '2.00 lb' / '2LBS' → '2 LB';  '14  OZ(400 GM)' → '14 OZ (400 GM)'.
    Returns the input unchanged if it isn't a recognisable size."""
    t = size.upper().strip()
    t = re.sub(r"(\d)\s+\.(\d)", r"\1.\2", t)            # '14 .1OZ'  → '14.1OZ'
    t = re.sub(r"(?<=\d)\s*0Z\b", "OZ", t)               # '14 0Z'    → '14OZ'  (zero typed for O)
    t = re.sub(r"^(\d+(?:\.\d+)?)\s*IB\.?$", r"\1LB", t) # '1IB.'     → '1LB'   (I typed for L)
    parts = []
    rest = t
    for m in _QTY.finditer(t):
        num = m.group(1)
        if "." in num:
            num = num.rstrip("0").rstrip(".")
        parts.append(f"{num} {_UNITS[m.group(2)]}")
        rest = rest.replace(m.group(0), "", 1)
    if not parts or len(parts) > 2 or re.sub(r"[\s()]", "", rest):
        return size
    return parts[0] if len(parts) == 1 else f"{parts[0]} ({parts[1]})"


# ── 2. Stray spacing ──────────────────────────────────────────────────────────
def tidy_spaces(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip()


def tidy_ingredients(text: str) -> str:
    """Spacing and punctuation only — words and spelling are left as written."""
    t = re.sub(r"\s*,\s*", ", ", text)          # 'a,b' / 'a ,b' → 'a, b'
    t = re.sub(r"(,\s*)+,", ",", t)             # 'Salt, , Oil'  → 'Salt, Oil'
    # 'salt &oil' → 'salt & oil', but leave names like 'FD&C' alone
    # (an '&' squeezed between capitals, as in 'FD&C', is part of a name)
    t = re.sub(r"(?<![A-Z])\s*&\s*|\s*&\s*(?![A-Z]\b)", " & ", t) \
        if not re.search(r"[A-Z]&[A-Z]\b", t) else t
    t = tidy_spaces(t)
    return t.rstrip(", ").strip()


# ── 3. Spelling of product names ──────────────────────────────────────────────
NAME_FIXES = {"MANGO MOOSE": "MANGO MOUSSE"}

# ── 4. Duplicate name + size (flag only — the POS decides which barcode is live)
DUPLICATE_NOTE_SAME = ("CHECK (data cleanup {today}): another product has the same name, size "
                       "and price (barcode {other}). Look both barcodes up in the POS and delete "
                       "the one the POS does not use.")
DUPLICATE_NOTE_PRICE = ("CHECK (data cleanup {today}): another product has the same name and size "
                        "but costs ${other_price:.2f} (barcode {other}). Probably a different "
                        "size — add the size to both.")

# ── 5. Date modes ─────────────────────────────────────────────────────────────
# Cooked items that have ingredient labels but were left as "Packed".
DATE_MODE_TO_BEST_BY = ["MAKHANI SAUCE", "POTATO POHA"]
# Cooked items with no ingredient text and no usable source document.
NEEDS_INGREDIENTS = {
    "GOBHI MUTTAR":            "GOBI MATTAR.docx actually contains the GOBHI ALOO label",
    "SABUDANA KHICHDI":        "SABUDANA KHICHDI.docx is empty",
    "WASABI FRIED GREEN PEAS": "WASABI _FRIED _GREENPEAS.docx only says \"29Month\"",
}
NEEDS_INGREDIENTS_NOTE = ("CHECK (data cleanup {today}): ingredients and subtitle still need to "
                          "be typed in — no source document ({why}).")

# ── 6. New products from the unmatched .docx ingredient labels ────────────────
# Text copied from import_source/ingredient_docs/<file>; spacing and punctuation
# tidied, spelling left exactly as on the original labels.
NEW_PRODUCTS = [
    dict(doc="ALSI PINNI.docx", name="ALSI PINNI", subtitle="", size="", date_mode="Best By",
         ingredients="Flex Seed, Chickpea Flour, Clarified Butter, Almonds, Raisins, Cashews, "
                     "Coconut Powder, Fennel Powder, Oil & Sugar"),
    dict(doc="ASSORTED NUTS.docx", name="ASSORTED NUTS", subtitle="", size="1.5 LB", date_mode="Packed",
         ingredients="Roasted Salted Almonds, Pistachios, Roasted Salted Cashews, Raisins"),
    dict(doc="LOBIA.docx", name="LOBIA RASMISSA", subtitle="BLACK EYE BEANS", size="", date_mode="Best By",
         ingredients="Black eye beans, ginger, Garlic, onions, spieces, salt tomatoes & oil"),
    dict(doc="MORIYO.docx", name="MORIYO", subtitle="SAMO", size="", date_mode="Best By",
         ingredients="Moriyo (Samo), Potatoes, Curry Leaves, Cumin Seeds, Cilantro, Red Whole "
                     "Chilli, Salt, Sugar, Cashews, Lemon Juice, Ginger, Green Chilli & Oil"),
    dict(doc="STRAWBERRY MOUSSE.docx", name="STRAWBERRY MOUSSE", subtitle="", size="", date_mode="Best By",
         ingredients="Strawberry, Sugar, Yogurt, Gelatin, Heavy Cream"),
    dict(doc="URAD CHANA DAL.docx", name="URAD CHANA DAL",
         subtitle="SPLIT MATPE BEANS & CHICKPEA LENTILS", size="", date_mode="Best By",
         ingredients="Split Matpe Beans, Chickpea Lentils, Ginger, Garlic, Cumin, Tomatoes, "
                     "Cilantro, Salt, Oil & Spices"),
]
NEW_PRODUCT_NOTE = ("Added from {doc} (data cleanup {today}). Needs its price and the barcode "
                    "number from the POS before printing barcode labels.")


def add_note(existing: str, note: str) -> str:
    if note in existing:
        return existing
    return f"{existing} | {note}" if existing else note


def plan(conn) -> tuple[list[dict], list[dict]]:
    """Return (field changes, products to insert)."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM products ORDER BY id")]
    changes: list[dict] = []
    pending: dict[tuple[int, str], str] = {}

    def change(row, field, new, reason):
        key = (row["id"], field)
        if new == pending.get(key, row[field]):
            return
        pending[key] = new
        # One log entry per field (original → final), so --undo restores cleanly
        for c in changes:
            if (c["id"], c["field"]) == key:
                c["new"], c["reason"] = new, f"{c['reason']}; {reason}"
                return
        changes.append(dict(id=row["id"], name=row["name"], field=field,
                            old=row[field], new=new, reason=reason))

    def current(row, field):
        return pending.get((row["id"], field), row[field])

    for r in rows:
        # 1. sizes
        new_size = normalize_size(tidy_spaces(r["size"] or ""))
        change(r, "size", new_size, "1 size spelling")
        # 2. spacing
        change(r, "name", tidy_spaces(r["name"]), "2 stray spaces")
        change(r, "subtitle", tidy_spaces(r["subtitle"] or ""), "2 stray spaces")
        if r["ingredients"]:
            change(r, "ingredients", tidy_ingredients(r["ingredients"]), "2 ingredient spacing/punctuation")
        # 3. spelling
        if current(r, "name") in NAME_FIXES:
            change(r, "name", NAME_FIXES[current(r, "name")], "3 name spelling")
        # 5. date modes
        if current(r, "name") in DATE_MODE_TO_BEST_BY and r["date_mode"] != "Best By":
            change(r, "date_mode", "Best By", "5 cooked item with ingredients set to Best By")
        if current(r, "name") in NEEDS_INGREDIENTS and not r["ingredients"]:
            note = NEEDS_INGREDIENTS_NOTE.format(today=TODAY, why=NEEDS_INGREDIENTS[current(r, "name")])
            change(r, "notes", add_note(current(r, "notes") or "", note), "5 flagged: needs ingredients")

    # 4. duplicates (after name/size fixes)
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((current(r, "name"), current(r, "size")), []).append(r)
    for (name, size), grp in groups.items():
        if len(grp) < 2:
            continue
        for r in grp:
            for o in grp:
                if o is r:
                    continue
                if o["price"] == r["price"]:
                    note = DUPLICATE_NOTE_SAME.format(today=TODAY, other=o["barcode_number"])
                else:
                    note = DUPLICATE_NOTE_PRICE.format(today=TODAY, other=o["barcode_number"],
                                                       other_price=o["price"] or 0)
                change(r, "notes", add_note(current(r, "notes") or "", note), "4 flagged: duplicate name+size")

    # 6. new products (skip any that already exist by name)
    existing = {current(r, "name") for r in rows}
    inserts = []
    for p in NEW_PRODUCTS:
        if p["name"] in existing:
            continue
        inserts.append(dict(name=p["name"], subtitle=p["subtitle"], ingredients=p["ingredients"],
                            size=p["size"], date_mode=p["date_mode"],
                            notes=NEW_PRODUCT_NOTE.format(doc=p["doc"], today=TODAY)))
    return changes, inserts


def backup(dst_path: str):
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
    finally:
        dst.close()
        src.close()


def apply():
    if os.path.exists(CSV_PATH):
        sys.exit("changes.csv already exists - U-006 was already applied. Run --undo first to re-apply.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    changes, inserts = plan(conn)
    conn.close()
    backup(BACKUP_PATH)
    conn = sqlite3.connect(DB_PATH)
    log = []
    with conn:
        for c in changes:
            conn.execute(f"UPDATE products SET {c['field']} = ?, updated_at = ? WHERE id = ?",
                         (c["new"], STAMP, c["id"]))
            log.append(dict(action="update", **c))
        for p in inserts:
            cur = conn.execute(
                "INSERT INTO products (name, subtitle, ingredients, size, price, barcode_number, "
                "date_mode, notes, created_at, updated_at) VALUES (?, ?, ?, ?, NULL, '', ?, ?, ?, ?)",
                (p["name"], p["subtitle"], p["ingredients"], p["size"], p["date_mode"], p["notes"],
                 STAMP, STAMP))
            log.append(dict(action="insert", id=cur.lastrowid, name=p["name"], field="(new product)",
                            old="", new=p["ingredients"], reason="6 added from unmatched .docx"))
    conn.close()
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["action", "id", "name", "field", "old", "new", "reason"])
        w.writeheader()
        w.writerows(log)
    print(f"Applied {len(changes)} field changes and added {len(inserts)} products.")
    print(f"Backup: {BACKUP_PATH}\nLog:    {CSV_PATH}")


def undo():
    if not os.path.exists(CSV_PATH):
        sys.exit("No changes.csv - nothing to undo.")
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        log = list(csv.DictReader(f))
    conn = sqlite3.connect(DB_PATH)
    kept = 0
    with conn:
        for c in reversed(log):
            if c["action"] == "insert":
                row = conn.execute("SELECT created_at, updated_at FROM products WHERE id = ?",
                                   (int(c["id"]),)).fetchone()
                if row and row[0] == row[1]:
                    conn.execute("DELETE FROM products WHERE id = ?", (int(c["id"]),))
                elif row:
                    kept += 1
                    print(f"  kept {c['name']} (edited since it was added)")
                continue
            cur = conn.execute(f"UPDATE products SET {c['field']} = ? WHERE id = ? AND {c['field']} = ?",
                               (c["old"], int(c["id"]), c["new"]))
            if cur.rowcount == 0:
                kept += 1
                print(f"  kept id {c['id']} {c['field']} (changed since cleanup)")
    conn.close()
    os.replace(CSV_PATH, CSV_PATH.replace(".csv", f"_undone_{datetime.now():%Y%m%d_%H%M%S}.csv"))
    print(f"Undo finished. {kept} item(s) left as they are because they were edited afterwards.")


def dry_run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    changes, inserts = plan(conn)
    conn.close()
    for c in changes:
        print(f"[{c['reason']}] #{c['id']} {c['name']} · {c['field']}: {c['old']!r} → {c['new']!r}")
    for p in inserts:
        print(f"[6 new product] {p}")
    print(f"\n{len(changes)} field changes, {len(inserts)} new products.  Run with --apply to make them.")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    {"--apply": apply, "--undo": undo}.get(arg, dry_run)()
