"""
allergens.py — The nine major food allergens and the "CONTAINS:" label line.

U-007 added the Allergens field.  U-023 (2026-11-11) makes it follow the New
York law that takes effect on 2026-11-12:

    Agriculture and Markets Law § 199-g: every food establishment shall label
    all prepackaged food with a written notification identifying any
    ingredient that constitutes a major food allergen.

The store uses "Method 2" from the Department of Agriculture and Markets
guidance: one statement printed right after the ingredient list that names
EVERY major allergen in the food, in the same type size:

    CONTAINS: MILK, ALMONDS, CASHEWS

Rules built in here (FD&C Act § 403(w); FDA "Questions and Answers Regarding
Food Allergens", Edition 5, January 2025):
  • Only the nine major allergens may go on the line (Q&A D.10) — never
    coconut, mustard, gluten, poppy seeds, ...
  • Tree nuts, fish and crustacean shellfish must be named by kind (§ 403(w)(2),
    Q&A C.5): "Cashews", "Cod", "Shrimp" — not "Tree Nuts", "Fish", "Shellfish".
  • Only the tree nuts in FDA's Table 1 count (Q&A C.7, C.8).  Coconut,
    chestnut, shea, nutmeg and makhana (lotus seed) are not major allergens.
  • Milk from animals other than cows and eggs from birds other than chickens
    name the animal: "Goat Milk", "Duck Eggs" (Q&A C.2, C.4).
  • Hidden sources count: ghee and butter are milk (Q&A B.7); wheat flour mixed
    into a spice such as hing is wheat (Q&A B.4).
  • Highly refined oils are exempt; cold-pressed / unrefined peanut and sesame
    oils are not (§ 199-g(1)(c)(ii)(A), Q&A D.9).

The product's allergens are stored as plain text ("Milk, Almonds, Cashews") in
the order the law lists them.  allergen_hints() reads the ingredient list and
suggests allergens that look missing; it only advises — a person decides.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk

# ── The nine major allergens ─────────────────────────────────────────────────

BASIC = ["Milk", "Eggs", "Peanuts", "Wheat", "Soybeans", "Sesame"]

# FDA Table 1 (Q&A Edition 5), in alphabetical order.  The first nine are
# offered as tick boxes; the walnut kinds after them are accepted when typed.
TREE_NUTS = ["Almonds", "Brazil Nuts", "Cashews", "Hazelnuts", "Macadamia Nuts",
             "Pecans", "Pine Nuts", "Pistachios", "Walnuts"]
MORE_TREE_NUTS = ["Black Walnuts", "California Walnuts", "Heartnuts"]

# Fish and crustacean shellfish are declared by kind.  These are the names the
# program knows; any other kind can be typed (the program asks once to confirm).
FISH = ["Anchovies", "Basa", "Bass", "Carp", "Catfish", "Cod", "Flounder", "Grouper",
        "Haddock", "Hake", "Halibut", "Herring", "Hilsa", "Kingfish", "Mackerel",
        "Mahi Mahi", "Perch", "Pollock", "Pomfret", "Rohu", "Salmon", "Sardines",
        "Snapper", "Sole", "Swordfish", "Tilapia", "Trout", "Tuna", "Whitefish"]
SHELLFISH = ["Crab", "Crawfish", "Crayfish", "Krill", "Lobster", "Prawns", "Shrimp"]

# Kept for anything that imported the old name (U-007).
MAJOR_ALLERGENS = BASIC + TREE_NUTS

_ALL_TREE_NUTS = TREE_NUTS + MORE_TREE_NUTS
_WALNUT_KINDS = {"walnuts", "black walnuts", "california walnuts", "heartnuts"}

# Typed spellings → the standard name printed on the label.
_SYNONYMS = {
    "milk": "Milk", "dairy": "Milk", "cow milk": "Milk", "cows milk": "Milk",
    "cow's milk": "Milk",
    "egg": "Eggs", "eggs": "Eggs", "chicken egg": "Eggs", "chicken eggs": "Eggs",
    "hen eggs": "Eggs",
    "peanut": "Peanuts", "peanuts": "Peanuts", "groundnut": "Peanuts", "groundnuts": "Peanuts",
    "wheat": "Wheat",
    "soy": "Soybeans", "soya": "Soybeans", "soybean": "Soybeans", "soybeans": "Soybeans",
    "soy bean": "Soybeans", "soy beans": "Soybeans", "soya bean": "Soybeans",
    "soya beans": "Soybeans", "soy milk": "Soybeans", "soya milk": "Soybeans",
    "sesame": "Sesame", "sesame seed": "Sesame", "sesame seeds": "Sesame", "til": "Sesame",
    "almond": "Almonds", "almonds": "Almonds", "badam": "Almonds", "almond milk": "Almonds",
    "brazil nut": "Brazil Nuts", "brazil nuts": "Brazil Nuts",
    "cashew": "Cashews", "cashews": "Cashews", "cashew nut": "Cashews",
    "cashew nuts": "Cashews", "kaju": "Cashews", "cashew milk": "Cashews",
    "hazelnut": "Hazelnuts", "hazelnuts": "Hazelnuts", "filbert": "Hazelnuts",
    "filberts": "Hazelnuts",
    "macadamia": "Macadamia Nuts", "macadamias": "Macadamia Nuts",
    "macadamia nut": "Macadamia Nuts", "macadamia nuts": "Macadamia Nuts",
    "bush nut": "Macadamia Nuts", "bush nuts": "Macadamia Nuts",
    "pecan": "Pecans", "pecans": "Pecans",
    "pine nut": "Pine Nuts", "pine nuts": "Pine Nuts", "pinon nut": "Pine Nuts",
    "pinon nuts": "Pine Nuts", "pignoli": "Pine Nuts", "chilgoza": "Pine Nuts",
    "pistachio": "Pistachios", "pistachios": "Pistachios", "pista": "Pistachios",
    "walnut": "Walnuts", "walnuts": "Walnuts", "akhrot": "Walnuts",
    "english walnuts": "Walnuts", "persian walnuts": "Walnuts",
    "black walnut": "Black Walnuts", "black walnuts": "Black Walnuts",
    "california walnut": "California Walnuts", "california walnuts": "California Walnuts",
    "heartnut": "Heartnuts", "heartnuts": "Heartnuts", "japanese walnut": "Heartnuts",
    "japanese walnuts": "Heartnuts",
    "anchovy": "Anchovies", "sardine": "Sardines", "prawn": "Prawns", "shrimps": "Shrimp",
    "crabs": "Crab", "lobsters": "Lobster",
    # Ingredient names typed into the Allergens box → the allergen they are
    "butter": "Milk", "ghee": "Milk", "clarified butter": "Milk", "cream": "Milk",
    "paneer": "Milk", "cheese": "Milk", "yogurt": "Milk", "yoghurt": "Milk", "curd": "Milk",
    "dahi": "Milk", "khoya": "Milk", "mawa": "Milk", "whey": "Milk", "buttermilk": "Milk",
    "flour": "Wheat", "wheat flour": "Wheat", "maida": "Wheat", "atta": "Wheat",
    "semolina": "Wheat", "sooji": "Wheat", "suji": "Wheat", "farina": "Wheat",
    "tofu": "Soybeans", "tahini": "Sesame", "til seeds": "Sesame",
}
for _name in BASIC + _ALL_TREE_NUTS + FISH + SHELLFISH:
    _SYNONYMS.setdefault(_name.lower(), _name)

_KNOWN = set(BASIC + _ALL_TREE_NUTS + FISH + SHELLFISH)

# Entries that are too broad: the law wants the kind.
_TREE_NUT_BROAD = "Name each kind of tree nut (e.g. Almonds, Cashews) instead of “{}”."
_FISH_BROAD = "Name the kind of fish (e.g. Cod, Salmon) instead of “{}”."
_SHELLFISH_BROAD = "Name the kind of shellfish (e.g. Shrimp, Crab) instead of “{}”."
_TOO_BROAD = {
    "tree nuts": _TREE_NUT_BROAD, "tree nut": _TREE_NUT_BROAD, "nuts": _TREE_NUT_BROAD,
    "nut": _TREE_NUT_BROAD, "mixed nuts": _TREE_NUT_BROAD, "dry fruits": _TREE_NUT_BROAD,
    "dry fruit": _TREE_NUT_BROAD, "dryfruits": _TREE_NUT_BROAD,
    "fish": _FISH_BROAD, "fishes": _FISH_BROAD,
    "shellfish": _SHELLFISH_BROAD, "crustacean shellfish": _SHELLFISH_BROAD,
    "crustaceans": _SHELLFISH_BROAD, "crustacean": _SHELLFISH_BROAD,
    "seafood": _SHELLFISH_BROAD,
}

# Entries that are not major allergens and must stay off the CONTAINS line.
_NOT_MAJOR_DEFAULT = "“{}” is not one of the 9 major food allergens — leave it off."
_COCONUT = "Coconut is not a major food allergen (FDA removed it in 2025) — leave it off."
_NONE = "Leave the Allergens field empty when the product has no major allergens."
_MOLLUSC = ("“{}” is not a major allergen: only crustacean shellfish (shrimp, crab, "
            "lobster) are — leave it off.")
_NOT_TREE_NUT = "“{}” is not on FDA's list of tree nut allergens — leave it off."
_NOT_MAJOR = {
    "oat milk": _NOT_MAJOR_DEFAULT, "rice milk": _NOT_MAJOR_DEFAULT,
    "coconut": _COCONUT, "coconuts": _COCONUT, "coconut milk": _COCONUT,
    "coconut powder": _COCONUT, "coconut cream": _COCONUT, "desiccated coconut": _COCONUT,
    "gluten": "Gluten is not one of the 9. If it comes from wheat, write Wheat.",
    "gelatin": ("Gelatin is not a major allergen. (If it is made from fish, write the fish, "
                "e.g. Cod.)"),
    "nutmeg": "Nutmeg is a spice, not a tree nut — leave it off.",
    "makhana": "Makhana (lotus seed / fox nut) is not a tree nut allergen — leave it off.",
    "fox nut": _NOT_TREE_NUT, "fox nuts": _NOT_TREE_NUT, "lotus seed": _NOT_TREE_NUT,
    "lotus seeds": _NOT_TREE_NUT, "chestnut": _NOT_TREE_NUT, "chestnuts": _NOT_TREE_NUT,
    "water chestnut": _NOT_TREE_NUT, "water chestnuts": _NOT_TREE_NUT, "shea": _NOT_TREE_NUT,
    "shea nut": _NOT_TREE_NUT, "shea nuts": _NOT_TREE_NUT, "kola nut": _NOT_TREE_NUT,
    "cola nut": _NOT_TREE_NUT, "pili nut": _NOT_TREE_NUT, "ginkgo nut": _NOT_TREE_NUT,
    "hickory nut": _NOT_TREE_NUT, "beech nut": _NOT_TREE_NUT, "butternut": _NOT_TREE_NUT,
    "lychee": _NOT_TREE_NUT, "lichee": _NOT_TREE_NUT,
    "clam": _MOLLUSC, "clams": _MOLLUSC, "oyster": _MOLLUSC, "oysters": _MOLLUSC,
    "mussel": _MOLLUSC, "mussels": _MOLLUSC, "scallop": _MOLLUSC, "scallops": _MOLLUSC,
    "squid": _MOLLUSC, "octopus": _MOLLUSC, "molluscs": _MOLLUSC, "mollusks": _MOLLUSC,
    "none": _NONE, "no": _NONE, "nil": _NONE, "n/a": _NONE, "na": _NONE,
    "nothing": _NONE, "no allergens": _NONE, "none of the above": _NONE,
}
for _word in ("mustard", "mustard seed", "mustard seeds", "celery", "lupin", "lupine",
              "sulphites", "sulfites", "sulphur dioxide", "sulfur dioxide", "corn", "maize",
              "chickpea", "chickpeas", "lentil", "lentils", "rice", "oats", "oat", "barley",
              "rye", "poppy seed", "poppy seeds", "sunflower seeds", "pumpkin seeds",
              "flax", "flaxseed", "flax seed", "flax seeds", "alsi", "garlic", "onion",
              "msg", "kiwi", "banana", "strawberry", "tomato"):
    _NOT_MAJOR.setdefault(_word, _NOT_MAJOR_DEFAULT)


def _rank(name: str) -> tuple:
    """Label order: the law's own list — milk, eggs, fish, crustacean
    shellfish, tree nuts, peanuts, wheat, soybeans, sesame — then anything else."""
    low = name.lower()
    if low == "milk" or low.endswith(" milk"):
        return (0, low != "milk", low)
    if low == "eggs" or low.endswith(" eggs") or low.endswith(" egg"):
        return (1, low != "eggs", low)
    if name in FISH:
        return (2, 0, low)
    if name in SHELLFISH:
        return (3, 0, low)
    if name in _ALL_TREE_NUTS:
        return (4, 0, low)
    for i, basic in enumerate(("Peanuts", "Wheat", "Soybeans", "Sesame")):
        if name == basic:
            return (5 + i, 0, low)
    return (9, 0, low)


def _animal_variant(item: str) -> str | None:
    """'goat milk' → 'Goat Milk', 'duck egg' → 'Duck Eggs' (Q&A C.2 / C.4)."""
    m = re.fullmatch(r"([a-z][a-z' ]*?)(?:'s)? (milk|eggs?)", item.lower())
    if not m:
        return None
    animal = m.group(1).strip().title()
    return f"{animal} Milk" if m.group(2) == "milk" else f"{animal} Eggs"


def parse_allergens(text: str | None) -> tuple[list[str], list[str]]:
    """Split the Allergens field into names, in label order, without repeats.

    Returns (names, problems).  Known names get their standard spelling
    ("soy" → "Soybeans", "kaju" → "Cashews"); anything else is kept as typed.
    *problems* says why an entry must not be printed as it is (too broad, or
    not a major allergen).  Nothing typed is ever dropped from *names*."""
    names: list[str] = []
    problems: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;&\n]|\band\b", text or "", flags=re.IGNORECASE):
        item = " ".join(raw.replace("’", "'").split()).strip(" .:-")
        if item.lower().startswith("contains"):          # "Contains: Milk" typed in
            item = item[len("contains"):].strip(" .:-")
        if not item:
            continue
        key = item.lower()
        if key in _TOO_BROAD:
            problems.append(_TOO_BROAD[key].format(item))
            name = item
        elif key in _NOT_MAJOR:
            problems.append(_NOT_MAJOR[key].format(item))
            name = item
        else:
            name = _SYNONYMS.get(key) or _animal_variant(item) or item
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    names.sort(key=_rank)
    return names, problems


def format_allergens(names: list[str]) -> str:
    """The text stored in the Allergens field: 'Milk, Almonds, Cashews'."""
    return ", ".join(sorted(names, key=_rank))


def normalize_allergens(text: str | None) -> str:
    """Tidy typed text into the stored form (standard names, label order)."""
    return format_allergens(parse_allergens(text)[0])


def contains_line(text: str | None) -> str:
    """The line printed under the ingredients, e.g. 'CONTAINS: MILK, CASHEWS'.
    Empty when the product has no allergens (no line is printed)."""
    names, _ = parse_allergens(text)
    if not names:
        return ""
    return "CONTAINS: " + ", ".join(n.upper() for n in names)


def unknown_names(text: str | None) -> list[str]:
    """Entries the program doesn't recognise (e.g. a kind of fish it doesn't
    list).  They may be right; the person saving is asked to confirm them."""
    names, _ = parse_allergens(text)
    out = []
    for n in names:
        key = n.lower()
        if (n in _KNOWN or key in _TOO_BROAD or key in _NOT_MAJOR
                or _animal_variant(n) is not None):
            continue
        out.append(n)
    return out


# ── Suggestions from the ingredient list ─────────────────────────────────────

NUTS_WHICH = "Tree nuts (which kind?)"
FISH_WHICH = "Fish (which kind?)"
SHELLFISH_WHICH = "Shellfish (which kind?)"
GENERIC_HINTS = (NUTS_WHICH, FISH_WHICH, SHELLFISH_WHICH)

_NON_WHEAT_FLOURS = (r"(?:rice|chickpea|chick pea|gram|besan|corn|maize|lentils?|urad|moong|"
                     r"coconut|almond|tapioca|potato|millet|jowar|bajra|ragi|soy|soya|oat|"
                     r"banana|water ?chestnut|singhara|kuttu|rajgira|amaranth|buckwheat|"
                     r"arrowroot|cassava|peanut|quinoa|sorghum|cashew|makki)")

# (allergen, words that suggest it, phrases ignored for that allergen)
_HINT_RULES_RAW: list[tuple[str, str, list[str]]] = [
    ("Milk",
     r"milk|milk solids|butter|buttermilk|ghee|cream|yogh?urt|curds?|dahi|paneer|panir|"
     r"cheese|khoya|khoa|mawa|malai|whey|casein|caseinate|lactose|kefir|rabri|rabdi|"
     r"chhena|chenna|lassi|kulfi",
     [r"coconut milk", r"coconut cream", r"almond milk", r"soya? milk", r"oat milk",
      r"rice milk", r"cashew milk", r"peanut butter", r"cocoa butter", r"cacao butter",
      r"shea butter", r"nut butter", r"apple butter", r"cream of wheat", r"cream of tartar",
      r"cream of rice", r"non-?dairy", r"dairy-?free", r"milk-?free"]),
    ("Eggs", r"eggs?|egg noodles|mayonnaise|mayo|albumen|meringue",
     [r"egg-?free", r"eggless", r"no eggs?"]),
    ("Wheat",
     r"wheat|flour|maida|atta|suji|sooji|semolina|rava|farina|noodles|vermicelli|seviyan|"
     r"sevaiyan|pasta|spaghetti|macaroni|bread|breadcrumbs|naan|roti|chapati|chapatti|"
     r"paratha|kulcha|bhatura|seitan|bulgur|couscous|spelt|durum|dalia|daliya|"
     r"soy sauce|soya sauce|asafoetida|asafetida|hing|biscuits?|cookies?|crackers?",
     [r"buckwheat", _NON_WHEAT_FLOURS + r" flour", _NON_WHEAT_FLOURS + r" atta",
      r"rice noodles", r"glass noodles", r"rice vermicelli", r"rice rava", r"idli rava",
      r"gluten-? ?free (?:hing|asafoetida|asafetida)", r"tamari"]),
    # Highly refined soybean oil is exempt and almost always what is sold.
    ("Soybeans",
     r"soy|soya|soybeans?|soy beans?|soya beans?|tofu|edamame|miso|tempeh|"
     r"textured vegetable protein|tvp",
     [r"soya? ?bean oil", r"soya? oil"]),
    ("Peanuts", r"peanuts?|groundnuts?|ground nuts?|mungfali|moongphali|moongfali|arachis",
     [r"(?:highly )?refined (?:peanut|groundnut|ground nut) oil"]),
    ("Sesame", r"sesame|til|tahini|tahina|gingelly|benne",
     [r"(?:highly )?refined (?:sesame|til|gingelly) oil"]),
    ("Almonds", r"almonds?|badam|marzipan", []),
    ("Brazil Nuts", r"brazil ?nuts?", []),
    ("Cashews", r"cashews?|cashew ?nuts?|kaju", []),
    ("Hazelnuts", r"hazelnuts?|hazel nuts?|filberts?", []),
    ("Macadamia Nuts", r"macadamias?|macadamia nuts?|bush nuts?", []),
    ("Pecans", r"pecans?", []),
    ("Pine Nuts", r"pine ?nuts?|pinon|piñon|pignoli|pignolia|chilgoza|chilgoze", []),
    ("Pistachios", r"pistachios?|pistachioes|pistas?|pistacho", []),
    ("Walnuts", r"walnuts?|akhrot", []),
    (NUTS_WHICH, r"nuts?|mixed nuts|dry ?fruits?|dryfruits?|tree nuts?",
     [r"(?:pine|brazil|macadamia|bush|cashew|hazel|ground|pinon|fox|lotus|betel|areca|"
      r"tiger|kola|cola|shea|palm|beech|pili|ginkgo|hickory|water ?chest|chest|coco|"
      r"dough|pea|wal|butter) ?nuts?"]),
    (FISH_WHICH, r"fish|fish sauce|worcestershire|anchov(?:y|ies)", [r"fish-?free", r"shellfish"]),
    (SHELLFISH_WHICH, r"shellfish|seafood", []),
]
for _name in FISH:
    if _name != "Anchovies":
        _single = _name[:-1] if _name.endswith("s") and not _name.endswith("ss") else _name
        _HINT_RULES_RAW.append((_name, re.escape(_single.lower()) + "(?:es|s)?", []))
for _name, _words in (("Shrimp", r"shrimps?"), ("Prawns", r"prawns?"), ("Crab", r"crabs?"),
                      ("Lobster", r"lobsters?"), ("Crawfish", r"crawfish"),
                      ("Crayfish", r"crayfish"), ("Krill", r"krill")):
    _HINT_RULES_RAW.append((_name, _words, []))

_HINT_RULES = [(name, re.compile(rf"\b(?:{words})\b"),
                [re.compile(rf"\b{m}\b") for m in masks])
               for name, words, masks in _HINT_RULES_RAW]


def allergen_hints(ingredients: str | None) -> dict[str, list[str]]:
    """Major allergens the ingredient list seems to contain, with the words
    that point to them: {'Milk': ['paneer', 'butter'], 'Wheat': ['asafoetida']}.

    It only reads the words.  It can't know about things not written in the
    list (ghee in a dish whose list doesn't say so), and it treats hing and
    soy sauce as containing wheat, as the store's own do."""
    text = " ".join((ingredients or "").lower().replace("’", "'").split())
    found: dict[str, list[str]] = {}
    for name, pattern, masks in _HINT_RULES:
        t = text
        for mask in masks:
            t = mask.sub(" ", t)
        words: list[str] = []
        for m in pattern.finditer(t):
            if m.group(0) not in words:
                words.append(m.group(0))
        if words:
            found[name] = words
    return found


def _is_declared(key: str, have: set[str]) -> bool:
    if key == "Milk":
        return any(n == "milk" or n.endswith(" milk") for n in have)
    if key == "Eggs":
        return any(n == "eggs" or n.endswith(" eggs") for n in have)
    if key == "Walnuts":
        return bool(have & _WALNUT_KINDS)
    if key == NUTS_WHICH:
        return any(n in {t.lower() for t in _ALL_TREE_NUTS} for n in have)
    if key == FISH_WHICH:
        known_other = {k.lower() for k in _KNOWN if k not in FISH}
        return any(n in {f.lower() for f in FISH} or (n not in known_other
                   and not n.endswith((" milk", " eggs"))) for n in have)
    if key == SHELLFISH_WHICH:
        return any(n in {s.lower() for s in SHELLFISH} for n in have)
    return key.lower() in have


def missing_allergens(ingredients: str | None, allergens: str | None) -> dict[str, list[str]]:
    """Suggestions from the ingredients that the Allergens field doesn't cover."""
    hints = allergen_hints(ingredients)
    have = {n.lower() for n in parse_allergens(allergens)[0]}
    return {k: v for k, v in hints.items() if not _is_declared(k, have)}


def add_allergens(allergens: str | None, keys) -> str:
    """The Allergens text with *keys* added (the 'which kind?' ones can't be
    added automatically and are skipped)."""
    names, _ = parse_allergens(allergens)
    extra = [k for k in keys if k not in GENERIC_HINTS]
    return format_allergens(parse_allergens(", ".join(names + extra))[0])


def describe_missing(key: str, words: list[str]) -> str:
    quoted = ", ".join(f"“{w}”" for w in words)
    if key == NUTS_WHICH:
        return f"The ingredients say {quoted}: name which tree nuts (e.g. Cashews)."
    if key == FISH_WHICH:
        return f"The ingredients say {quoted}: name which fish (e.g. Cod)."
    if key == SHELLFISH_WHICH:
        return f"The ingredients say {quoted}: name which shellfish (e.g. Shrimp)."
    return f"The ingredients mention {quoted}, but {key.upper()} is not on the CONTAINS line."


def label_problems(product: dict) -> list[str]:
    """Reasons a product's CONTAINS line may be wrong or incomplete; [] if it
    looks right.  Checked before ingredient / combined labels are printed."""
    _, problems = parse_allergens(product.get("allergens"))
    out = list(problems)
    for key, words in missing_allergens(product.get("ingredients"),
                                        product.get("allergens")).items():
        out.append(describe_missing(key, words))
    return out


# ── Picker window ────────────────────────────────────────────────────────────

class AllergenPicker(tk.Toplevel):
    """Tick boxes for the major allergens, with tree nuts by kind, plus a box
    for fish / shellfish / other kinds.  Calls on_done(text) on OK."""

    def __init__(self, parent, current: str, on_done, ingredients: str = ""):
        super().__init__(parent)
        self.title("Allergens — CONTAINS line")
        self.resizable(False, False)
        self.transient(parent)
        self._on_done = on_done
        self._ingredients = ingredients or ""

        names, _ = parse_allergens(current)
        boxes = BASIC + TREE_NUTS
        chosen = set(names)
        self._vars: dict[str, tk.BooleanVar] = {}

        f = ttk.Frame(self, padding=12)
        f.pack(fill=tk.BOTH)
        ttk.Label(f, text="Tick every major food allergen in this product,\n"
                          "including hidden ones: ghee and butter are Milk, most hing "
                          "has Wheat,\nsoy sauce has Soybeans and Wheat.",
                  font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(0, 6))

        basic = ttk.LabelFrame(f, text="Major allergens", padding=(8, 4))
        basic.pack(fill=tk.X)
        for i, name in enumerate(BASIC):
            self._add_box(basic, name, name in chosen, i // 3, i % 3)

        nuts = ttk.LabelFrame(f, text="Tree nuts — tick each kind used", padding=(8, 4))
        nuts.pack(fill=tk.X, pady=(8, 0))
        for i, name in enumerate(TREE_NUTS):
            self._add_box(nuts, name, name in chosen, i // 3, i % 3)

        other = ttk.Frame(f)
        other.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(other, text="Fish / shellfish / other, by kind (e.g. Cod, Shrimp, Goat Milk):"
                  ).pack(anchor=tk.W)
        self._other_var = tk.StringVar(value=", ".join(n for n in names if n not in boxes))
        self._other_var.trace_add("write", lambda *_: self._refresh())
        ttk.Entry(other, textvariable=self._other_var, width=60).pack(fill=tk.X)

        self._hints = allergen_hints(self._ingredients)
        if self._hints:
            hint_row = ttk.Frame(f)
            hint_row.pack(fill=tk.X, pady=(8, 0))
            text = "  ·  ".join(f"{k.upper() if k not in GENERIC_HINTS else k} "
                                f"({', '.join(v)})" for k, v in self._hints.items())
            ttk.Label(hint_row, text="From the ingredients: " + text, wraplength=420,
                      foreground="#9b2c2c").pack(side=tk.LEFT, anchor=tk.W)
            ttk.Button(hint_row, text="Tick these", command=self._tick_hints).pack(
                side=tk.RIGHT, padx=(6, 0))

        ttk.Label(f, text="Not major allergens — leave off: coconut, makhana, nutmeg, "
                          "mustard, poppy seeds, chickpeas.",
                  foreground="gray").pack(anchor=tk.W, pady=(8, 0))
        self._preview_var = tk.StringVar()
        ttk.Label(f, textvariable=self._preview_var, font=("Arial", 10, "bold"),
                  wraplength=460).pack(anchor=tk.W, pady=(8, 0))
        self._problem_var = tk.StringVar()
        ttk.Label(f, textvariable=self._problem_var, foreground="#b42318",
                  wraplength=460).pack(anchor=tk.W)

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=4)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._ok())
        self._refresh()
        self.grab_set()
        self.focus_set()

    def _add_box(self, parent, name: str, on: bool, row: int, col: int):
        var = tk.BooleanVar(value=on)
        var.trace_add("write", lambda *_: self._refresh())
        self._vars[name] = var
        ttk.Checkbutton(parent, text=name, variable=var).grid(
            row=row, column=col, sticky=tk.W, padx=(0, 16), pady=2)

    def text(self) -> str:
        picked = [name for name, var in self._vars.items() if var.get()]
        return normalize_allergens(", ".join(picked + [self._other_var.get()]))

    def _tick_hints(self):
        others = parse_allergens(self._other_var.get())[0]
        for key in self._hints:
            if key in self._vars:
                self._vars[key].set(True)
            elif key not in GENERIC_HINTS and key not in others:
                others.append(key)
        self._other_var.set(format_allergens(others))

    def _refresh(self):
        text = self.text()
        line = contains_line(text)
        self._preview_var.set(f"Will print:  {line}" if line
                              else "No CONTAINS line (no major allergens ticked).")
        problems = parse_allergens(text)[1]
        problems += [describe_missing(k, v)
                     for k, v in missing_allergens(self._ingredients, text).items()]
        self._problem_var.set("\n".join(problems))

    def _ok(self):
        text = self.text()
        problems = parse_allergens(text)[1]
        if problems:
            self._problem_var.set("\n".join(problems))
            return
        self._on_done(text)
        self.destroy()
