"""
categories.py — Product categories for the "Show:" list filter (U-013).

A product's category is stored in the database and can be changed on the
product form.  suggest_category() is only a starting guess, used for the
one-time assignment of existing products and for new products saved with no
category chosen.  It looks at the name (and whether the product has a size,
which cooked dishes don't).

Categories only filter the product list.  They are never printed.
"""

from __future__ import annotations

import re

SWEETS    = "Sweets"
SPICES    = "Spices"
DRY_GOODS = "Dry Goods"
CATEGORIES = [SWEETS, SPICES, DRY_GOODS]

_SWEET_WORDS = [
    "BURFI", "BARFI", "PEDA", "LADOO", "LADDOO", "LADDU", "HALWA", "JALEBI", "RASMALAI",
    "RASGULLA", "GULAB JAMUN", "KHEER", "MOUSSE", "MOOSE", "KALAKAND", "KATLI", "PINNI",
    "SHRIKHAND", "CANDY", "CHANDARKALA", "SOHAN", "MYSORE PAK", "FIRNI", "RABRI", "KULFI",
    "FALOODA", "CUSTARD", "CHIKKI", "SHAKKAR PARA", "KHOYA", "SANDESH", "BROWNIE",
    "AAM PAPAD", "PETHA", "GAJAK", "REWARI", "IMARTI", "BALUSHAHI", "MALPUA", "CHAM CHAM",
    "RAJBHOG", "SHYAM SAVERA", "MOTICHOOR", "BESAN LADDU", "PAYASAM", "MISHTI",
    "KALA KUND", "GUR PARE",
]

# Never auto-categorised: prepared / frozen foods and snacks that happen to
# contain a spice or grain word ("MASALA IDLI", "AJWAIN COOKIES").
_SKIP_WORDS = ["MASALA IDLI", "RAVA IDLI", "COOKIES", "CHUTNEY", "NAMKEEN", "SANDWICH"]

# Checked before spices, so seeds / powders / oils that are really groceries
# ("CHIA SEEDS", "MUSTARD OIL", "COCONUT POWDER") go to Dry Goods.
_DRY_FIRST_WORDS = ["OIL", "CHIA", "SAGO", "FLEX", "FLAX", "COCONUT", "TUKMARIA", "GHEE"]

_SPICE_WORDS = [
    "SEED", "SEEDS", "POWDER", "PWDR", "MASALA", "CARDAMOM", "CARDIMOM", "CINNAMON",
    "CINAMMON", "CINAMON", "CLOVE", "CLOVES", "CUMIN", "JEERA", "TURMERIC", "TUMERIC",
    "PEPPER", "CHILLI", "CHILI", "ANISE", "ANIES", "NUTMEG", "BAY LEAF", "JAVETRI", "MACE",
    "AJWAIN", "HING", "ASAFOETIDA", "PAPRIKA", "FENUGREEK", "METHI", "MUSTARD", "AMCHUR",
    "BLACK SALT", "SAFFRON", "ANAR DANA", "CURRY", "GARAM", "KALONJI", "SAUNF", "DHANIA",
    "CORIANDER", "TUKMARIA", "GOOND", "FATKADI", "KASURI", "STAR",
]

_DRY_WORDS = [
    "DAL", "RICE", "FLOUR", "ATTA", "BEANS", "CHANA", "CHANNA", "MOONG", "URAD", "URD",
    "TOOR", "MASOOR", "RAJMA", "PEAS", "LENTIL", "LENTILS", "NUT", "NUTS", "ALMOND",
    "CASHEW", "CASHEWS", "PISTA", "PISTACHIO", "PISTACHO", "WALNUT", "WALNUTS", "RAISIN",
    "RAISINS", "DATES", "PEANUT", "PEANUTS", "MAKHANA", "POHA", "SOOJI", "SUJI", "RAVA",
    "SUGAR", "JAGGERY", "GUR", "TEA", "OIL", "GHEE", "WADI", "VERMICELLI", "SEV", "PAPAD",
    "BESAN", "CHORI", "MOTH", "KULTHI", "LOBIA", "SAGO", "SABUDANA", "MILLET", "QUINOA",
    "OATS", "CORN", "COCONUT", "DRY FRUIT", "FIGS", "ANJEER", "APRICOT", "PULP", "PASTE",
    "PICKLE", "FRYUMS", "PUFFED", "KALA CHANA", "BASMATI", "SONA", "CHICKPEA", "CHICKPEAS",
    "ALMONDS", "COUSCOUS", "CRANBERRI", "CRANBERRY", "ALSI", "BUKHARA", "PAPPADAM",
]


def _has_word(name: str, words: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", name) for w in words)


def suggest_category(name: str, size: str = "", date_mode: str = "") -> str:
    """Best guess for a product's category, or "" if nothing fits.

    Sweets can be cooked or packaged.  Spices and dry goods are packaged
    groceries, so they need a size (cooked dishes such as "CHANA MASALA" have
    none) and must not be "Best By" (made in the store).
    """
    n = (name or "").upper()
    if _has_word(n, _SKIP_WORDS):
        return ""
    if _has_word(n, _SWEET_WORDS):
        return SWEETS
    if not (size or "").strip() or date_mode == "Best By":
        return ""
    if _has_word(n, _DRY_FIRST_WORDS):
        return DRY_GOODS
    if _has_word(n, _SPICE_WORDS):
        return SPICES
    if _has_word(n, _DRY_WORDS):
        return DRY_GOODS
    return ""
