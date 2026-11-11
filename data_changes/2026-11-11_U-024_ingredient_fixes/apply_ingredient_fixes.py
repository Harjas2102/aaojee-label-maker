"""
U-024 — Ingredient corrections from the owner (2026-11-11), after U-023.

Usage (with the program CLOSED):
    python apply_ingredient_fixes.py                  dry run: shows every change
    python apply_ingredient_fixes.py --apply          make the changes
    python apply_ingredient_fixes.py --check          confirm the database is as it should be
    python apply_ingredient_fixes.py --undo           put the old values back
Add  --db "C:\\path\\to\\products.db"  for a database other than the project folder's
(on the store PC: the program folder's products.db).

What the owner asked for (every change, with its reason, is in planned_changes.json):
  • Every "Oil" becomes "Canola Oil", including "Veg Oil" / "Vegetable Oil": the kitchen uses
    canola oil (Laxmi Canola Oil); vegetable oil is not in use.  50 products.
  • Allergens that were only on the CONTAINS line now have their reason in the ingredients
    too ("not just the allergen without any context"):
      - every "Asafoetida" becomes "Asafoetida (Wheat Flour)" (the store's hing has wheat);
      - HAKKA NOODLES: "Noodles" → "Egg Noodles";
      - PAV BHAJI: Butter added;  SOOJI HALWA: Clarified Butter (ghee) added.
  • CHANA MASALA: Dry Fenugreek and Asafoetida added → its CONTAINS line becomes WHEAT.
  • GOLGAPPA PANI: CILENTRO → CILANTRO; SPICES, TAMARIND, LEMON JUICE, GREEN CHILLIES added.
  • FRUIT CUSTARD: the fruits are listed (Banana, Blueberry, Strawberry, Grape, Lychee,
    Mandarin Orange, Pineapple).
  • GAJJAR HALWA: Green Cardamom added.
  • PEAS PILAF: no almonds; VEG PILAF: no cashews → neither has a CONTAINS line now.
HAKKA NOODLES keeps SOYBEANS: it comes from the soy sauce, not from oil.

The allergens in planned_changes.json were worked out from the new ingredient text by the
program's own check (allergen_hints) and compared with U-023: only CHANA MASALA, PEAS PILAF
and VEG PILAF change.  After this change every allergen on every CONTAINS line is named
by a word in that product's ingredient list.

Safety: a product is changed only if its ingredients and allergens are still exactly the
"old" values; anything edited since is listed and nothing is changed.  --apply saves
products_before_U-024.db here first and writes changes.csv.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "source"))

from allergens import (GENERIC_HINTS, allergen_hints, contains_line,  # noqa: E402
                       format_allergens, missing_allergens, parse_allergens)
from database import Database                                         # noqa: E402

sys.path.insert(0, os.path.dirname(HERE))
from review_chain import superseded                                   # noqa: E402

PLAN_PATH = os.path.join(HERE, "planned_changes.json")
CSV_PATH = os.path.join(HERE, "changes.csv")
BACKUP_PATH = os.path.join(HERE, "products_before_U-024.db")
U023_PATH = os.path.join(ROOT, "data_changes", "2026-11-11_U-023_allergens", "apply_allergens.py")


def load_plan() -> list[dict]:
    with open(PLAN_PATH, encoding="utf-8") as f:
        plan = json.load(f)
    ids = [c["id"] for c in plan]
    if len(ids) != len(set(ids)):
        raise SystemExit("planned_changes.json lists a product twice")
    for c in plan:
        names, problems = parse_allergens(c["new_allergens"])
        expected = format_allergens([k for k in allergen_hints(c["new_ingredients"])
                                     if k not in GENERIC_HINTS])
        if problems or format_allergens(names) != c["new_allergens"] or expected != c["new_allergens"]:
            raise SystemExit(f"planned allergens for {c['name']} don't match its ingredients")
    return plan


def load_u023():
    spec = importlib.util.spec_from_file_location("apply_allergens", U023_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def program_running() -> bool:
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AaojeeLabels.exe"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return False
    return "aaojeelabels.exe" in out.lower()


def compare(db: Database, plan: list[dict]) -> tuple[list[dict], list[str]]:
    """(changes still to make, reasons to stop).  Products a later change (U-025, ...)
    has corrected since count as done: that change's --check covers them."""
    todo, stop = [], []
    later = superseded(os.path.basename(HERE), {p["id"]: p for p in db.get_all_products()})
    for c in plan:
        if c["id"] in later:
            continue
        p = db.get_product(c["id"])
        if p is None:
            stop.append(f"Missing: {c['name']} (id {c['id']}) is not in the database.")
            continue
        now = (p["name"], p["ingredients"], p["allergens"])
        if now == (c["name"], c["new_ingredients"], c["new_allergens"]):
            continue                                            # already done
        if now != (c["name"], c["old_ingredients"], c["old_allergens"]):
            stop.append(f"Changed since the review: {c['name']} (id {c['id']}) now has "
                        f"ingredients {p['ingredients']!r}, allergens {p['allergens']!r}.")
            continue
        todo.append(c)
    return todo, stop


def verify(db: Database, plan: list[dict]) -> list[str]:
    """Everything --check looks at.  [] means all is well."""
    bad = []
    todo, stop = compare(db, plan)
    bad += stop
    bad += [f"Not applied yet: {c['name']} (id {c['id']})" for c in todo]
    planned = {c["id"] for c in plan}
    later = superseded(os.path.basename(HERE), {p["id"]: p for p in db.get_all_products()})
    u023 = load_u023()
    reviewed = {r[0]: r for r in u023.REVIEW}
    for p in db.get_all_products():
        if not (p["ingredients"] or "").strip():
            continue
        name, pid = p["name"], p["id"]
        if pid not in planned and pid not in later:
            r = reviewed.get(pid)
            if r is None or u023.fingerprint(p["ingredients"]) != r[3] or p["allergens"] != r[2]:
                bad.append(f"{name} (id {pid}): not covered by the U-023 / U-024 review")
        hints = allergen_hints(p["ingredients"])
        generic = [k for k in hints if k in GENERIC_HINTS]
        expected = format_allergens([k for k in hints if k not in GENERIC_HINTS])
        if generic or p["allergens"] != expected or missing_allergens(p["ingredients"],
                                                                      p["allergens"]):
            bad.append(f"{name} (id {pid}): allergens {p['allergens']!r} but the ingredient "
                       f"words point to {expected!r}{' + ' + str(generic) if generic else ''}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="U-024: ingredient corrections (see the file).")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--db", default=os.path.join(ROOT, "products.db"))
    args = ap.parse_args()

    plan = load_plan()
    db_path = os.path.abspath(args.db)
    if not os.path.isfile(db_path):
        print(f"No database at {db_path}")
        return 1
    if (args.apply or args.undo) and program_running():
        print("AaojeeLabels.exe is running.  Close the program first, then run this again.")
        return 1
    db = Database(db_path)

    if args.undo:
        if not os.path.exists(CSV_PATH):
            print("No changes.csv - nothing to undo.")
            return 1
        done, kept = 0, []
        for c in plan:
            p = db.get_product(c["id"], include_deleted=True)
            if p and (p["ingredients"], p["allergens"]) == (c["new_ingredients"], c["new_allergens"]):
                db.save_product({"id": c["id"], "ingredients": c["old_ingredients"],
                                 "allergens": c["old_allergens"]})
                done += 1
            else:
                kept.append(c["name"])
        os.replace(CSV_PATH, CSV_PATH.replace(".csv", "_undone.csv"))
        print(f"Put back {done} of {len(plan)} products." + (
            f"  Edited by hand since, so kept: {', '.join(kept)}" if kept else ""))
        return 0

    if args.check:
        bad = verify(db, plan)
        if bad:
            print("CHECK FAILED:\n  " + "\n  ".join(bad))
            return 1
        with_ing = [p for p in db.get_all_products() if (p["ingredients"] or "").strip()]
        with_line = sum(1 for p in with_ing if p["allergens"])
        print(f"CHECK PASSED: {len(with_ing)} products with ingredients, all reviewed "
              f"({with_line} with a CONTAINS line, {len(with_ing) - with_line} with none); every "
              "allergen on every CONTAINS line is named by a word in its ingredient list, and "
              "nothing the ingredients point to is missing.")
        return 0

    todo, stop = compare(db, plan)
    if stop:
        print("STOPPED - nothing was changed:\n  " + "\n  ".join(stop))
        return 1
    if not args.apply:
        for c in todo:
            line = (f"   {contains_line(c['old_allergens']) or '(no CONTAINS line)'} -> "
                    f"{contains_line(c['new_allergens']) or '(no CONTAINS line)'}"
                    if c["old_allergens"] != c["new_allergens"] else "")
            print(f"{c['name']}\n   {c['old_ingredients']}\n-> {c['new_ingredients']}\n{line}")
        print(f"\n{len(todo)} products would change.  Run with --apply.")
        return 0

    if os.path.exists(CSV_PATH):
        print("changes.csv already exists - U-024 was already applied. Run --undo first.")
        return 1
    db._copy_to(BACKUP_PATH)
    rows = []
    for c in todo:
        db.save_product({"id": c["id"], "ingredients": c["new_ingredients"],
                         "allergens": c["new_allergens"]})
        for field in ("ingredients", "allergens"):
            if c[f"old_{field}"] != c[f"new_{field}"]:
                rows.append(dict(id=c["id"], name=c["name"], field=field, old=c[f"old_{field}"],
                                 new=c[f"new_{field}"], why=c["why"]))
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "field", "old", "new", "why"])
        w.writeheader()
        w.writerows(rows)
    print(f"Changed {len(todo)} products ({len(rows)} values).\n"
          f"Backup: {BACKUP_PATH}\nLog: {CSV_PATH}")
    bad = verify(db, plan)
    if bad:
        print("BUT the check after applying failed:\n  " + "\n  ".join(bad))
        return 1
    print("Check after applying: passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
