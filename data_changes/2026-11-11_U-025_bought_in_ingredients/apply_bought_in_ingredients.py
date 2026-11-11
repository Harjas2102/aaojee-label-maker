"""
U-025 — Bought-in parts written out, Golgappa Pani water, Sooji Halwa order (2026-11-11).

Usage (with the program CLOSED):
    python apply_bought_in_ingredients.py                  dry run: shows every change
    python apply_bought_in_ingredients.py --apply          make the changes
    python apply_bought_in_ingredients.py --check          confirm the database is as it should be
    python apply_bought_in_ingredients.py --undo           put the old values back
Add  --db "C:\\path\\to\\products.db"  for a database other than the project folder's
(on the store PC: the program folder's products.db).

The owner sent the ingredient lists from the packages (2026-11-11):
  • Soy sauce:  Water, Soybeans, Sugar, Salt, Wheat Flour  (label: "Contains: soy, wheat,
    sulfites").
  • Chilli sauce (Sriracha):  Chili, Sugar, Salt, Garlic, Acetic Acid, Potassium Sorbate and
    Sodium Bisulfite as preservatives, Xanthan Gum  (label: "Contains sulphite").
  • MDH Pani Puri Masala:  Salt White, Cumin, Unripe Dried Mango, Salt Black, Citric Acid
    (E330), Tamarind, Mint Leaves, Dried Ginger, Yellow Chilli, Black Pepper, Musk Melon,
    Turmeric, Cloves, Caraway, Asafoetida  ("may contain mustard").
Changes (4 products; reasons in planned_changes.json):
  • HAKKA NOODLES and SCHEZWAN FRIED RICE: the chilli sauce and soy sauce get their own
    ingredients in brackets, so the WHEAT and SOYBEANS on the CONTAINS line are explained.
  • GOLGAPPA PANI: Water added first (the main ingredient); "Spices" is the MDH Pani Puri
    Masala, written out.  Its "Asafoetida" is treated as containing wheat, like the store's own
    hing (MDH doesn't say), so the CONTAINS line is WHEAT.  The list is written in normal
    capitals rather than ALL CAPS: it prints at 7.1 pt instead of 6 pt on the 2.25 x 1.25 label.
  • SOOJI HALWA: reordered from most to least by weight (owner: "reverse the order as you see
    fit"): Cream of Wheat, Sugar, Clarified Butter, Almonds, Raisins, Cardamom, Saffron.
Sulfites and mustard are not among the 9 major allergens, so they are not on the CONTAINS line
(FDA Q&A D.10); the sulfite is listed in the chilli sauce's brackets as on its label.
No CONTAINS line changes except GOLGAPPA PANI (none -> WHEAT).

Safety: a product is changed only if its ingredients and allergens are still exactly the
"old" values (U-024's results).  --apply saves products_before_U-025.db here first and
writes changes.csv.  --check here covers everything: this change, U-024 and U-023.
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
BACKUP_PATH = os.path.join(HERE, "products_before_U-025.db")
U024_PATH = os.path.join(ROOT, "data_changes", "2026-11-11_U-024_ingredient_fixes",
                         "apply_ingredient_fixes.py")


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


def load_u024():
    spec = importlib.util.spec_from_file_location("apply_ingredient_fixes", U024_PATH)
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
    """Everything --check looks at.  [] means all is well.  U-024's check runs too: it
    covers every product with ingredients (and hands the ones changed here back to this
    check), so together they cover the whole store."""
    todo, bad = compare(db, plan)
    bad += [f"Not applied yet: {c['name']} (id {c['id']})" for c in todo]
    u024 = load_u024()
    bad += u024.verify(db, u024.load_plan())
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="U-025: bought-in parts written out (see the file).")
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
        print("changes.csv already exists - U-025 was already applied. Run --undo first.")
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
