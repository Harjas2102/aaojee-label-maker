"""
review_chain.py — shared by the allergen / ingredient data changes (U-023 onward).

Each change has a --check.  When a LATER change corrects a product again, the earlier
change's --check leaves that product to the later one.  Later changes are the folders in
data_changes/ that sort after the earlier one's folder and have a planned_changes.json
(the latest one wins).
"""

from __future__ import annotations

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def later_values(after_folder: str) -> dict[int, tuple[str, str]]:
    """{product id: (ingredients, allergens)} as set by changes after *after_folder*."""
    out: dict[int, tuple[str, str]] = {}
    for path in sorted(glob.glob(os.path.join(HERE, "*", "planned_changes.json"))):
        if os.path.basename(os.path.dirname(path)) <= after_folder:
            continue
        with open(path, encoding="utf-8") as f:
            for c in json.load(f):
                out[c["id"]] = (c["new_ingredients"], c["new_allergens"])
    return out


def superseded(after_folder: str, products: dict[int, dict]) -> set[int]:
    """Products whose ingredients and allergens are exactly what a later change set."""
    return {pid for pid, value in later_values(after_folder).items()
            if pid in products
            and (products[pid]["ingredients"], products[pid]["allergens"]) == value}
