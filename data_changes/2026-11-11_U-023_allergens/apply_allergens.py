"""
U-023 — Fill in the allergens ("CONTAINS:" line) for every product that has an
ingredient list (2026-11-11), for New York Agriculture and Markets Law § 199-g,
which takes effect on 2026-11-12.

Usage (with the program CLOSED):
    python apply_allergens.py                   dry run: shows what would change
    python apply_allergens.py --apply           fill in the Allergens field
    python apply_allergens.py --check           confirm the database matches this review
    python apply_allergens.py --undo            put the old (blank) values back
Add  --db "C:\\path\\to\\products.db"  to work on a database other than the one in
the project folder (on the store PC: the program folder's products.db).

How the allergens were decided (every product's reason is in REVIEW below):
  • Each of the 68 products that had ingredient text on 2026-11-11 was read word
    by word against the nine major food allergens, using FDA's rules (Q&A
    Edition 5; see source/allergens.py).  The program's own suggestion check
    (allergen_hints) was run as an independent second pass.  It agrees with
    this table on 65 of 68; the other 3 are hidden allergens the owner confirmed.
  • Owner's answers (2026-11-11):
      - the store's hing (asafoetida) contains wheat flour → Wheat (7 dishes);
      - Hakka Noodles are made with egg noodles → Eggs;
      - Sooji Halwa is made with ghee and Pav Bhaji with butter, though their
        ingredient lists don't show it → Milk;
      - the cooking oil is Laxmi Canola Oil about 99% of the time (not an
        allergen).  Laxmi Vegetable Oil (soybean oil) is used once or twice a
        year; highly refined soybean oil is exempt, and written confirmation
        is to be asked of the supplier (label photos checked 2026-11-11).
  • Coconut, makhana, nutmeg and poppy seeds are not major allergens and are left
    off.  The ingredient text itself is not changed ("Method 2").
  • 22 products contain none of the nine.  Their Allergens field stays empty, so
    no CONTAINS line prints for them.

Later changes: U-024 and U-025 (same day) corrected the ingredient text of 56 of these products
on the owner's instructions (canola oil, hing with wheat flour shown, bought-in sauces written
out, and others).  The --check here skips products a later change corrected; run the latest
change's --check (U-025) for the full current state.

Safety:
  • A product is changed only if its ingredient text is still exactly the text
    that was reviewed (checked with a fingerprint).  If anyone has edited the
    ingredients since, or added a product with ingredients that isn't in the
    table, the script stops and lists them: a person must review them first.
  • An Allergens field that someone already filled in is never overwritten.
  • --apply saves products_before_U-023.db in this folder first, and writes
    changes.csv (every value changed) and allergen_review.csv (all 68 products:
    what prints and why).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "source"))

from allergens import (allergen_hints, contains_line, format_allergens,  # noqa: E402
                       missing_allergens, parse_allergens, unknown_names)
from database import Database                                              # noqa: E402

CSV_PATH = os.path.join(HERE, "changes.csv")
REVIEW_CSV = os.path.join(HERE, "allergen_review.csv")
BACKUP_PATH = os.path.join(HERE, "products_before_U-023.db")

NONE = "None of the 9 major allergens in the ingredients"
HING = "asafoetida (the store's hing contains wheat flour - owner)"

REVIEW = [
    # (id, name, allergens to store, fingerprint of the ingredient text reviewed, why)
    (139, 'ALOO MATTAR', '', '527170f84590', NONE),
    (217, 'ALOO SABZI', 'Wheat', '5899327b55c7', f"Wheat: {HING}"),
    (442, 'ALSI PINNI', 'Milk, Almonds, Cashews', '7271336807a3',
     'Milk: clarified butter (ghee); Almonds: almonds; Cashews: cashews'),
    (443, 'ASSORTED NUTS', 'Almonds, Cashews, Pistachios', 'ff6368c7fb64',
     'Almonds: almonds; Cashews: cashews; Pistachios: pistachios'),
    (122, 'BAINGAN ALOO', '', '28ea1b1cb15c', NONE),
    (11, 'BAINGAN BHARTHA', '', '54c4374331ba', NONE),
    (255, 'BESAN BURFI', 'Milk, Almonds', 'c072b42971bb',
     'Milk: clarified butter (ghee); Almonds: almonds'),
    (211, 'BESAN PINNI', 'Milk, Almonds, Cashews', '208acfe40a7e',
     'Milk: clarified butter (ghee); Almonds: almonds; Cashews: cashews'),
    (121, 'BHINDI ALOO', '', 'aaf510fefeab', NONE),
    (126, 'BHINDI MASALA', '', 'd6f615f044df', NONE),
    (116, 'CHANA MASALA', '', 'a00eef4294f0', NONE),
    (105, 'CHANNA DAL COOKED', '', '318cb12fd1e3', NONE),
    (182, 'FENNEL CANDY', '', 'af83acc1562f', NONE),
    (178, 'FRUIT CUSTARD', 'Milk', '149a30dd9391', 'Milk: milk'),
    (119, 'GAJJAR HALWA', 'Milk, Cashews, Pistachios', 'cbd70bb8fc1c',
     'Milk: milk, clarified butter (ghee); Cashews: cashews; Pistachios: pistachio'),
    (106, 'GOBHI ALOO', '', 'f1d32c3aaf63', NONE),
    (433, 'GOLGAPPA PANI', '', '66555908ab79', NONE),
    (201, 'GUJARATI BATATA RINGER', 'Wheat', 'e1eaebc3f5c3', f"Wheat: {HING}"),
    (144, 'GUJRATI DAL', 'Wheat', '05b15a671e84', f"Wheat: {HING}"),
    (292, 'GUJRATI KHICHDI', 'Wheat', '5e81f0fd35f3', f"Wheat: {HING}"),
    (162, 'GULAB JAMUN', 'Milk, Wheat', '3ffd8c3edd10',
     'Milk: milk solids, paneer; Wheat: flour (wheat flour)'),
    (118, 'HAKKA NOODLES', 'Eggs, Wheat, Soybeans', '7e2fcb605579',
     'Eggs: the noodles are egg noodles (owner); Wheat: noodles (wheat), soy sauce '
     '(brewed with wheat); Soybeans: soy sauce'),
    (156, 'IDLI', '', '34d03804b771', NONE),
    (163, 'KADAHI PANEER', 'Milk', 'c50635769fde', 'Milk: panir (paneer)'),
    (360, 'KADHAI MUSHROOM', '', 'a7bd5d1519fb', NONE),
    (152, 'KADHI PAKORA', 'Milk, Wheat', '2c8bc0acf088', f"Milk: yogurt; Wheat: {HING}"),
    (250, 'KAJU KATLI', 'Milk, Cashews', '14a5eb51fc07', 'Milk: milk, butter; Cashews: cashew'),
    (115, 'KALA CHANNA COOKED', '', '1cc10cabcbc1', NONE),
    (297, 'KALA KUND', 'Milk, Almonds, Pistachios', '7afd1cca82f8',
     'Milk: milk; Almonds: almond; Pistachios: pistachio'),
    (111, 'KARELA ALOO', '', 'f2edde6f7612', NONE),
    (179, 'KHEER (RICE PUDDING)', 'Milk, Almonds, Cashews, Pistachios', '757523a145cf',
     'Milk: milk; Almonds: almonds; Cashews: cashew; Pistachios: pista'),
    (281, 'LADOO', 'Milk, Almonds, Cashews, Wheat, Sesame', '0d11dc38fe8b',
     'Milk: clarified butter (ghee); Almonds: almonds; Cashews: cashews; Wheat: wheat flour, '
     'farina; Sesame: sesame seeds'),
    (158, 'LEMON RICE', 'Cashews, Wheat', '5ac8ea38d84c', f"Cashews: cashews; Wheat: {HING}"),
    (441, 'LOBIA RASMISSA', '', '377e74cf8e42', NONE),
    (382, 'MAKHANI DAL', 'Milk', '07748907e9a7', 'Milk: butter, heavy cream'),
    (103, 'MAKHANI PANEER', 'Milk', 'ddc31d25f094', 'Milk: paneer cheese, butter, heavy cream'),
    (243, 'MAKHANI SAUCE', 'Milk', '0bb2a3e27a70', 'Milk: butter, heavy cream'),
    (451, 'MALABAR VEG', 'Cashews', '9820c4d5c90a',
     'Cashews: cashews (coconut milk is not dairy and coconut is not a major allergen)'),
    (10, 'MALAI KOFTA', 'Milk', '12e1a6f57afe', 'Milk: cottage cheese, butter, heavy cream'),
    (134, 'MANGO MOUSSE', 'Milk', '853e79eeca4c', 'Milk: yogurt, heavy cream'),
    (128, 'MATTAR PANEER', 'Milk, Cashews', 'c04d6b306cd7',
     'Milk: cottage cheese; Cashews: cashew (makhana is not a tree nut)'),
    (177, 'MINT CHUTNEY', 'Milk', '979a5cbb2baa', 'Milk: yogurt'),
    (123, 'MIX VEG', '', 'a6f789a83a90', NONE),
    (129, 'MIX VEG MAKHANI', 'Milk, Cashews', '6da0664c8f4a',
     'Milk: cottage cheese, butter, heavy cream; Cashews: cashew'),
    (49, 'MOONG DAL', '', '94cb7621029e', NONE),
    (444, 'MORIYO', 'Cashews', 'f267edec76eb', 'Cashews: cashews'),
    (173, 'NAVRATAN KORMA', 'Milk', 'b2fe91ba7204',
     'Milk: heavy cream (makhana is not a tree nut)'),
    (131, 'PALAK PANEER', 'Milk', 'f695e1ec7dac', 'Milk: cheese, butter, heavy cream'),
    (9, 'PANEER BHURJI', 'Milk', 'c66a04e13e17', 'Milk: cottage cheese'),
    (194, 'PAV BHAJI', 'Milk', 'a82af3296c44',
     'Milk: cooked with butter, not in the ingredient list (owner)'),
    (140, 'PEAS PILAF', 'Almonds', '9af826332c40', 'Almonds: almonds'),
    (108, 'PLAIN PALAK', 'Milk', 'd6d9a09ee264', 'Milk: butter, heavy cream'),
    (372, 'POTATO POHA', 'Peanuts', '79f0a533bebe', 'Peanuts: peanuts'),
    (114, 'RAJMA', '', 'f421b503c1cb', NONE),
    (133, 'RICE PILAF', '', '73e54bd9748d', NONE),
    (110, 'SAMBER', 'Wheat', '44488bf85316', f"Wheat: {HING}"),
    (104, 'SARSO KA SAAG', 'Milk', 'e5a873b10e5d', 'Milk: butter, heavy cream'),
    (257, 'SCHEZWAN FRIED RICE', 'Wheat, Soybeans', '3f77f19efc89',
     'Wheat: soya sauce (brewed with wheat); Soybeans: soya sauce'),
    (273, 'SHAKKAR PARA', 'Wheat', 'bc690dd5dfff', 'Wheat: enriched flour (wheat flour)'),
    (386, 'SHRIKHAND', 'Milk, Almonds, Pistachios', 'f49a48885dee',
     'Milk: yogurt; Almonds: almonds; Pistachios: pistachio'),
    (319, 'SOOJI HALWA', 'Milk, Almonds, Wheat', 'c660e9f88dd5',
     'Milk: made with ghee, not in the ingredient list (owner); Almonds: almonds; '
     'Wheat: cream of wheat'),
    (248, 'SOYA PILAU', 'Milk, Soybeans', '0bc8c23ed591', 'Milk: paneer; Soybeans: soya chunks'),
    (445, 'STRAWBERRY MOUSSE', 'Milk', 'c5c5a0d6a682', 'Milk: yogurt, heavy cream'),
    (155, 'TADKA DAL', '', 'c7c4813e7389', NONE),
    (132, 'UPMA', 'Milk, Wheat', '4d4e649ea31f', 'Milk: milk; Wheat: cream of wheat'),
    (446, 'URAD CHANA DAL', '', '148f4f3b5967', NONE),
    (280, 'VEG PILAF', 'Cashews', 'b3e62ae01e31', 'Cashews: cashews'),
    (311, 'VEG SINDHI BIRYANI', '', '1762988a17c5', NONE),
]

# Allergens the owner confirmed that the ingredient words don't show.  --check
# expects exactly these to go beyond the program's suggestions.
OWNER_CONFIRMED_EXTRA = {(118, "Eggs"), (194, "Milk"), (319, "Milk")}


def fingerprint(ingredients: str) -> str:
    return hashlib.sha1((ingredients or "").encode("utf-8")).hexdigest()[:12]


def check_table() -> None:
    """The table itself: 68 different products, standard names in the law's
    order, nothing the program would refuse, and a reason for every row."""
    ids = [r[0] for r in REVIEW]
    if not len(ids) == len(set(ids)) == 68:
        raise SystemExit("REVIEW must list 68 different products")
    for _pid, name, allergens, _sha, why in REVIEW:
        names, problems = parse_allergens(allergens)
        if format_allergens(names) != allergens or problems or unknown_names(allergens):
            raise SystemExit(f"REVIEW row for {name} is not in standard form: {problems}")
        if not why:
            raise SystemExit(f"REVIEW row for {name} has no reason")


def program_running() -> bool:
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AaojeeLabels.exe"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return False
    return "aaojeelabels.exe" in out.lower()


sys.path.insert(0, os.path.dirname(HERE))
from review_chain import superseded                                       # noqa: E402

FOLDER = os.path.basename(HERE)


def superseded_later(active: dict[int, dict]) -> set[int]:
    """Products a later change (U-024, U-025, ...) has corrected since, on the owner's
    instructions.  They are checked by that change's own --check instead."""
    return superseded(FOLDER, active)


def compare(db: Database) -> tuple[list[dict], list[str]]:
    """(planned changes, reasons to stop)."""
    table = {r[0]: r for r in REVIEW}
    active = {p["id"]: p for p in db.get_all_products()}
    later = superseded_later(active)
    stop: list[str] = []
    for pid, p in sorted(active.items()):
        if (p["ingredients"] or "").strip() and pid not in table:
            stop.append(f"Not reviewed: {p['name']} (id {pid}) has ingredients but is not in "
                        "the review.")
    plan = []
    for pid, name, allergens, sha, why in REVIEW:
        p = active.get(pid)
        if pid in later:
            continue
        if p is None:
            stop.append(f"Missing: {name} (id {pid}) is not in the database (deleted or in "
                        "the Trash?).")
            continue
        if p["name"] != name:
            stop.append(f"Renamed: id {pid} is now {p['name']!r}, reviewed as {name!r}.")
            continue
        if fingerprint(p["ingredients"]) != sha:
            stop.append(f"Ingredients changed since the review: {name} (id {pid}), now "
                        f"{p['ingredients']!r}")
            continue
        old = p["allergens"] or ""
        if old == allergens:
            continue
        if old.strip():
            stop.append(f"Already filled in by hand: {name} (id {pid}) has {old!r}; the review "
                        f"says {allergens!r}.  Decide which is right.")
            continue
        plan.append(dict(id=pid, name=name, size=p["size"], barcode=p["barcode_number"],
                         field="allergens", old=old, new=allergens, why=why))
    return plan, stop


def verify(db: Database) -> list[str]:
    """Everything --check looks at.  [] means all is well."""
    _plan, bad = compare(db)
    products = {p["id"]: p for p in db.get_all_products()}
    later = superseded_later(products)
    for pid, name, allergens, _sha, _why in REVIEW:
        p = products.get(pid)
        if not p or pid in later:
            continue
        if p["allergens"] != allergens:
            bad.append(f"{name} (id {pid}): allergens {p['allergens']!r}, expected {allergens!r}")
        missing = missing_allergens(p["ingredients"], p["allergens"])
        if missing:
            bad.append(f"{name} (id {pid}): the program's check says missing {missing}")
        declared = {(pid, n) for n in parse_allergens(p["allergens"])[0]}
        hinted = {(pid, k) for k in allergen_hints(p["ingredients"])}
        unexpected = declared - hinted - OWNER_CONFIRMED_EXTRA
        if unexpected:
            bad.append(f"{name} (id {pid}): {sorted(n for _, n in unexpected)} not found in "
                       "the ingredient words and not confirmed by the owner")
    return bad


def write_review_csv(db: Database, path: str) -> None:
    products = {p["id"]: p for p in db.get_all_products()}
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "barcode", "ingredients", "allergens field",
                    "printed under the ingredients", "why"])
        for pid, name, allergens, _sha, why in sorted(REVIEW, key=lambda r: r[1]):
            p = products.get(pid, {})
            w.writerow([pid, name, p.get("barcode_number", ""), p.get("ingredients", ""),
                        allergens, contains_line(allergens) or "(no CONTAINS line)", why])


def main() -> int:
    ap = argparse.ArgumentParser(description="U-023: fill in the allergens (see the file).")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--db", default=os.path.join(ROOT, "products.db"))
    args = ap.parse_args()

    check_table()
    db_path = os.path.abspath(args.db)
    if not os.path.isfile(db_path):
        print(f"No database at {db_path}")
        return 1
    if (args.apply or args.undo) and program_running():
        print("AaojeeLabels.exe is running.  Close the program first, then run this again.")
        return 1
    db = Database(db_path)
    with_line = sum(1 for r in REVIEW if r[2])

    if args.undo:
        if not os.path.exists(CSV_PATH):
            print("No changes.csv - nothing to undo.")
            return 1
        with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        done, kept = 0, []
        for r in rows:
            p = db.get_product(int(r["id"]), include_deleted=True)
            if p and p["allergens"] == r["new"]:
                db.save_product({"id": p["id"], "allergens": r["old"]})
                done += 1
            else:
                kept.append(r["name"])
        os.replace(CSV_PATH, CSV_PATH.replace(".csv", "_undone.csv"))
        print(f"Put back {done} of {len(rows)} values." + (
            f"  Edited by hand since, so kept: {', '.join(kept)}" if kept else ""))
        return 0

    if args.check:
        bad = verify(db)
        if bad:
            print("CHECK FAILED:\n  " + "\n  ".join(bad))
            return 1
        later = superseded_later({p["id"]: p for p in db.get_all_products()})
        if later:
            print(f"CHECK PASSED: the {68 - len(later)} products not corrected since still match "
                  f"this review; {len(later)} were corrected by later changes (U-024 / U-025) - "
                  "run the latest one's --check for those.")
            return 0
        print(f"CHECK PASSED: all 68 reviewed products match ({with_line} with a CONTAINS "
              f"line, {68 - with_line} with none); every product with ingredients is "
              "reviewed; the program's own check finds nothing missing.")
        return 0

    plan, stop = compare(db)
    if stop:
        print("STOPPED - nothing was changed:\n  " + "\n  ".join(stop))
        return 1
    if not args.apply:
        for c in plan:
            print(f"{c['name']:28} {contains_line(c['new'])}")
        print(f"\n{len(plan)} products would get a CONTAINS line; {68 - with_line} have no "
              "major allergens (left blank).  Run with --apply.")
        return 0

    if os.path.exists(CSV_PATH):
        print("changes.csv already exists - U-023 was already applied. Run --undo first.")
        return 1
    db._copy_to(BACKUP_PATH)
    for c in plan:
        db.save_product({"id": c["id"], "allergens": c["new"]})
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "size", "barcode", "field", "old",
                                          "new", "why"])
        w.writeheader()
        w.writerows(plan)
    write_review_csv(db, REVIEW_CSV)
    bad = verify(db)
    print(f"Filled in the allergens for {len(plan)} products.\n"
          f"Backup: {BACKUP_PATH}\nLog: {CSV_PATH}\nReview: {REVIEW_CSV}")
    if bad:
        print("BUT the check after applying failed:\n  " + "\n  ".join(bad))
        return 1
    print("Check after applying: passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
