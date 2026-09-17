"""Label rendering: every real product renders, barcodes decode, text fits."""

import unittest
from datetime import date

import helpers
import label_renderer as lr
from barcode_engine import compute_check_digit
from printer_manager import to_monochrome

PACK_DATE = date(2026, 9, 17)
FLAGS_ALL = dict(barcode=True, price=True, dollar_sign=True, date=True, address=True)
FLAGS_NONE = dict(barcode=False, price=False, dollar_sign=False, date=False, address=False)
VARIANTS = [("Barcode", "2.25x1.25"), ("Barcode", "2.25x3.00"), ("Ingredient", "2.25x1.25"),
            ("Ingredient", "2.25x3.00"), ("Combined", "2.25x3.00")]
WORST_EXTRAS = {"allergens": "Milk, Eggs, Tree Nuts, Peanuts, Wheat, Soybeans, Sesame",
                "net_weight": "32 OZ (907 GM)"}


def render(product, label_type, size, dpi=150, flags=FLAGS_ALL, settings=None, spacing=1.75,
           min_module_in=None):
    s = settings or helpers.fixture_settings()
    return lr.render_label(product, label_type, size, PACK_DATE, flags, s, s["address_line"], 10,
                           dpi, spacing, s.get("label_margin_in", 0.05), min_module_in=min_module_in)


def bottom_ink_row(image) -> int:
    g = image.convert("L")
    w, h = g.size
    px = g.load()
    for y in range(h - 1, -1, -1):
        if any(px[x, y] < 128 for x in range(w)):
            return y
    return -1


class TestEveryProductRenders(unittest.TestCase):
    def test_all_variants_preview_dpi(self):
        for p in helpers.fixture_products():
            for lt, size in VARIANTS:
                for flags in (FLAGS_ALL, FLAGS_NONE):
                    with self.subTest(product=p["name"], label=lt, size=size):
                        img = render(p, lt, size, flags=flags)
                        h_in = 3.0 if size == "2.25x3.00" else 1.25
                        self.assertEqual(img.size, (round(2.25 * 150), round(h_in * 150)))

    def test_tiny_font_sizes_do_not_crash(self):
        s = helpers.fixture_settings()
        p = dict(helpers.fixture_products()[0], name="X" * 80, subtitle="Y" * 60, price=123.45)
        for size in (6, 7, 8):
            for key in [k for k in s if k.startswith("font_")]:
                s[key] = dict(s[key], size=size)
            for lt, sz in VARIANTS:
                render(p, lt, sz, settings=s)


class TestBarcodesScan(unittest.TestCase):
    """U-005: at the printer's own DPI every bar is whole dots and decodes correctly."""

    def test_native_dpi_decodes(self):
        products = [p for p in helpers.fixture_products() if p["barcode_number"]]
        for dpi in (203, 300):
            for p in products:
                for lt, size in (("Barcode", "2.25x1.25"), ("Combined", "2.25x3.00")):
                    with self.subTest(dpi=dpi, product=p["name"], label=lt):
                        img = to_monochrome(render(p, lt, size, dpi=dpi, min_module_in=0.013))
                        h_in = 3.0 if size == "2.25x3.00" else 1.25
                        self.assertEqual(img.size, (round(2.25 * dpi), round(h_in * dpi)))
                        decoded = helpers.decode_upce(img)
                        self.assertIsNotNone(decoded)
                        data6, check, module = decoded
                        self.assertEqual(data6, p["barcode_number"])
                        self.assertEqual(check, compute_check_digit(data6))
                        self.assertGreaterEqual(module, round(0.013 * dpi))


class TestInfoLines(unittest.TestCase):
    """U-007 / U-008: Contains / Net Wt lines."""

    def test_info_lines(self):
        self.assertEqual(lr.info_lines({}), [])
        self.assertEqual(lr.info_lines({"allergens": " Milk ", "net_weight": "16 OZ"}),
                         [("Contains: Milk", True), ("Net Wt: 16 OZ", False)])

    def test_lines_only_on_ingredient_and_combined(self):
        p = next(x for x in helpers.fixture_products() if x["name"] == "GUJRATI DAL")
        p = dict(p, allergens="", net_weight="")
        extra = dict(p, allergens="Milk", net_weight="16 OZ")
        for lt, size in VARIANTS:
            same = render(p, lt, size).tobytes() == render(extra, lt, size).tobytes()
            self.assertEqual(same, lt == "Barcode", lt)

    def test_combined_never_runs_off_label(self):
        products = [p for p in helpers.fixture_products() if p["ingredients"]]
        for spacing in (1.0, 1.75, 3.0):
            for p in products:
                with self.subTest(spacing=spacing, product=p["name"]):
                    img = render(dict(p, **WORST_EXTRAS), "Combined", "2.25x3.00", dpi=203,
                                 spacing=spacing)
                    self.assertLess(bottom_ink_row(img), img.height - 2)

    def test_no_ingredient_text_dropped(self):
        orig = lr._draw_ingredients_block
        truncated = []

        def spy(draw, ingredients, ing_fnt, prefix_fnt, y, w_px, content_w, margin, dpi,
                max_y=None, extras=()):
            lines = (len(lr._wrap_text("Ingredients : " + ingredients, ing_fnt, content_w, draw))
                     if ingredients else 0)
            lines += sum(len(lr._wrap_text(t, f, content_w, draw)) for t, f in extras)
            _, lh = lr._text_size(draw, "Ay", ing_fnt)
            end = orig(draw, ingredients, ing_fnt, prefix_fnt, y, w_px, content_w, margin, dpi,
                       max_y=max_y, extras=extras)
            if end - y < lines * (lh + 1):
                truncated.append(ingredients[:30])
            return end

        lr._draw_ingredients_block = spy
        try:
            for p in [x for x in helpers.fixture_products() if x["ingredients"]]:
                for lt, size in (("Combined", "2.25x3.00"), ("Ingredient", "2.25x1.25")):
                    render(dict(p, **WORST_EXTRAS), lt, size, dpi=203)
        finally:
            lr._draw_ingredients_block = orig
        self.assertEqual(truncated, [])


class TestDates(unittest.TestCase):
    def test_date_lines(self):
        self.assertEqual(lr.format_date_line("Best By", PACK_DATE, 10), "Best By : 9/27/2026")
        self.assertEqual(lr.format_date_line("Packed", PACK_DATE, 10), "Packed : 9/17/2026")
        self.assertIsNone(lr.format_date_line("None", PACK_DATE, 10))


if __name__ == "__main__":
    unittest.main()
