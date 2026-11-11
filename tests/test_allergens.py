"""U-023: the allergen rules behind the CONTAINS line (NY AML § 199-g, FDA Q&A Ed. 5)."""

import importlib.util
import os
import unittest

import helpers
import allergens as al

U023_SCRIPT = os.path.join(helpers.ROOT, "data_changes", "2026-11-11_U-023_allergens",
                           "apply_allergens.py")
U024_SCRIPT = os.path.join(helpers.ROOT, "data_changes", "2026-11-11_U-024_ingredient_fixes",
                           "apply_ingredient_fixes.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_u023():
    return _load(U023_SCRIPT, "apply_allergens")


class TestNames(unittest.TestCase):
    def test_standard_names_and_law_order(self):
        names, problems = al.parse_allergens("sesame, soy, kaju, egg, milk, groundnut, wheat, pista")
        self.assertEqual(names, ["Milk", "Eggs", "Cashews", "Pistachios", "Peanuts", "Wheat",
                                 "Soybeans", "Sesame"])
        self.assertEqual(problems, [])

    def test_repeats_and_spellings_collapse(self):
        self.assertEqual(al.normalize_allergens("Milk, milk; dairy & ghee and Paneer"), "Milk")
        self.assertEqual(al.normalize_allergens("Contains: almond, Almonds"), "Almonds")
        self.assertEqual(al.normalize_allergens(""), "")

    def test_other_animals_named(self):
        self.assertEqual(al.normalize_allergens("goat milk, milk, duck egg"),
                         "Milk, Goat Milk, Duck Eggs")

    def test_too_broad_is_a_problem(self):
        for typed in ("Tree Nuts", "nuts", "Fish", "Shellfish", "Crustacean shellfish",
                      "Dry fruits"):
            with self.subTest(typed=typed):
                names, problems = al.parse_allergens(f"Milk, {typed}")
                self.assertEqual(len(problems), 1)
                self.assertIn(typed, names)       # never silently dropped

    def test_not_major_is_a_problem(self):
        for typed in ("Coconut", "Coconut milk", "Mustard", "Gluten", "Clams", "None",
                      "Makhana", "Nutmeg", "Poppy seeds", "Chestnuts"):
            with self.subTest(typed=typed):
                self.assertEqual(len(al.parse_allergens(typed)[1]), 1)

    def test_unknown_names_need_confirming(self):
        self.assertEqual(al.unknown_names("Milk, Swai, Cod, Goat Milk"), ["Swai"])
        self.assertEqual(al.unknown_names("Milk, Tree Nuts, Coconut"), [])

    def test_contains_line(self):
        self.assertEqual(al.contains_line("wheat, milk, sesame"), "CONTAINS: MILK, WHEAT, SESAME")
        self.assertEqual(al.contains_line(""), "")
        self.assertEqual(al.contains_line(None), "")


class TestHints(unittest.TestCase):
    CASES = [
        ("Paneer, Butter, Heavy Cream", {"Milk"}),
        ("Clarified Butter, Sugar", {"Milk"}),
        ("Coconut milk, Coconut Powder, Makhana, Nutmeg, Poppy Seeds", set()),
        ("Cream of Wheat, Sugar", {"Wheat"}),
        ("Peanut Butter", {"Peanuts"}),
        ("Rice Flour, Lentils Flour, Chickpea Flour, Corn Flour", set()),
        ("Enriched Flour, Vegetable Oil", {"Wheat"}),
        ("Flour", {"Wheat"}),
        ("Asafoetida, Salt", {"Wheat"}),
        ("Gluten free hing", set()),
        ("Egg Noodles", {"Eggs", "Wheat"}),
        ("Soy Sauce", {"Soybeans", "Wheat"}),
        ("Soybean Oil, Soya Oil", set()),
        ("Peanut Oil", {"Peanuts"}),
        ("Refined Peanut Oil, Highly refined sesame oil", set()),
        ("Eggplant, Eggless", set()),
        ("Lentils, Basmati Rice, Until", set()),
        ("Til Seeds", {"Sesame"}),
        ("Tilapia", {"Tilapia"}),
        ("Pine Nuts", {"Pine Nuts"}),
        ("Mixed Nuts", {al.NUTS_WHICH}),
        ("Buckwheat", set()),
        ("Kaju, Badam, Pista, Akhrot", {"Cashews", "Almonds", "Pistachios", "Walnuts"}),
        ("Shrimp, Fish", {"Shrimp", al.FISH_WHICH}),
        ("Curry Leaves, Curds", {"Milk"}),
    ]

    def test_cases(self):
        for text, expected in self.CASES:
            with self.subTest(ingredients=text):
                self.assertEqual(set(al.allergen_hints(text)), expected)

    def test_missing(self):
        self.assertEqual(al.missing_allergens("Paneer, Cashews", "Milk, Cashews"), {})
        self.assertEqual(set(al.missing_allergens("Paneer, Cashews", "Milk")), {"Cashews"})
        self.assertEqual(al.missing_allergens("Mixed nuts", "Almonds, Walnuts"), {})
        self.assertEqual(al.missing_allergens("Goat milk", "Goat Milk"), {})
        self.assertEqual(al.missing_allergens("Black walnut", "Black Walnuts"), {})
        self.assertEqual(set(al.missing_allergens("Fish sauce", "")), {al.FISH_WHICH})
        self.assertEqual(al.missing_allergens("Fish sauce", "Anchovies"), {})

    def test_add(self):
        self.assertEqual(al.add_allergens("Cashews", ["Milk", al.NUTS_WHICH]), "Milk, Cashews")

    def test_label_problems(self):
        self.assertEqual(al.label_problems({"ingredients": "Paneer", "allergens": "Milk"}), [])
        self.assertEqual(len(al.label_problems({"ingredients": "Paneer", "allergens": ""})), 1)
        self.assertEqual(len(al.label_problems({"ingredients": "", "allergens": "Tree Nuts"})), 1)
        self.assertEqual(al.label_problems({}), [])


class TestStoreReview(unittest.TestCase):
    """The 68 products reviewed on 2026-11-11 (data_changes/…U-023…)."""

    def test_review_table(self):
        mod = load_u023()
        mod.check_table()                                  # raises if anything is off
        with_line = [r for r in mod.REVIEW if r[2]]
        self.assertEqual((len(mod.REVIEW), len(with_line)), (68, 46))

    def test_fixture_matches_review(self):
        """Every fixture product whose ingredient text is the reviewed text has
        the reviewed allergens, and the program's own check agrees."""
        mod = load_u023()
        by_name = {r[1]: r for r in mod.REVIEW}
        matched = 0
        for p in helpers.fixture_products():
            if not p["ingredients"]:
                self.assertEqual(p["allergens"], "", p["name"])
                continue
            self.assertEqual(al.missing_allergens(p["ingredients"], p["allergens"]), {},
                             p["name"])
            r = by_name.get(p["name"])
            if r and mod.fingerprint(p["ingredients"]) == r[3]:
                matched += 1
                self.assertEqual(p["allergens"], r[2], p["name"])
        self.assertGreaterEqual(matched, 64)


class TestIngredientFixes(unittest.TestCase):
    """U-024: the owner's ingredient corrections, applied after U-023."""

    def test_plan_follows_on_from_u023(self):
        u023, u024 = load_u023(), _load(U024_SCRIPT, "apply_ingredient_fixes")
        plan = u024.load_plan()            # raises if any allergens don't match the words
        reviewed = {r[0]: r for r in u023.REVIEW}
        self.assertEqual(len(plan), 56)
        for c in plan:
            r = reviewed[c["id"]]
            self.assertEqual((c["name"], u023.fingerprint(c["old_ingredients"]), c["old_allergens"]),
                             (r[1], r[3], r[2]), c["name"])

    def test_every_contains_line_has_its_reason_in_the_ingredients(self):
        u024 = _load(U024_SCRIPT, "apply_ingredient_fixes")
        for c in u024.load_plan():
            words = al.allergen_hints(c["new_ingredients"])
            self.assertEqual(set(al.parse_allergens(c["new_allergens"])[0]),
                             {k for k in words if k not in al.GENERIC_HINTS}, c["name"])
            self.assertNotRegex(c["new_ingredients"], r"(?i)(?<!canola )\boil\b", c["name"])
        changed = {c["name"]: (c["old_allergens"], c["new_allergens"]) for c in u024.load_plan()
                   if c["old_allergens"] != c["new_allergens"]}
        self.assertEqual(changed, {"CHANA MASALA": ("", "Wheat"), "PEAS PILAF": ("Almonds", ""),
                                   "VEG PILAF": ("Cashews", "")})


class TestBoughtInIngredients(unittest.TestCase):
    """U-025: sauces and masala written out, Golgappa Pani water, Sooji Halwa order."""

    U025_SCRIPT = os.path.join(helpers.ROOT, "data_changes",
                               "2026-11-11_U-025_bought_in_ingredients",
                               "apply_bought_in_ingredients.py")

    def test_plan_follows_on_from_u024(self):
        u024 = _load(U024_SCRIPT, "apply_ingredient_fixes")
        u025 = _load(self.U025_SCRIPT, "apply_bought_in_ingredients")
        after_u024 = {c["id"]: c for c in u024.load_plan()}
        plan = u025.load_plan()            # raises if any allergens don't match the words
        self.assertEqual({c["name"] for c in plan},
                         {"HAKKA NOODLES", "SCHEZWAN FRIED RICE", "GOLGAPPA PANI", "SOOJI HALWA"})
        for c in plan:
            prev = after_u024[c["id"]]
            self.assertEqual((c["old_ingredients"], c["old_allergens"]),
                             (prev["new_ingredients"], prev["new_allergens"]), c["name"])
            self.assertEqual(set(al.parse_allergens(c["new_allergens"])[0]),
                             {k for k in al.allergen_hints(c["new_ingredients"])
                              if k not in al.GENERIC_HINTS}, c["name"])
        changed = {c["name"]: c["new_allergens"] for c in plan
                   if c["old_allergens"] != c["new_allergens"]}
        self.assertEqual(changed, {"GOLGAPPA PANI": "Wheat"})

    def test_sulfites_and_mustard_stay_off_the_contains_line(self):
        self.assertEqual(al.allergen_hints("Sodium Bisulfite, Mustard Seeds"), {})
        self.assertTrue(al.parse_allergens("Sulfites")[1])


if __name__ == "__main__":
    unittest.main()
