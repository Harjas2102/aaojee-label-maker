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
# More allergens than any real product has (LADOO has 5), plus a long net weight
WORST_EXTRAS = {"allergens": "Milk, Eggs, Almonds, Cashews, Pistachios, Peanuts, Wheat, "
                             "Soybeans, Sesame",
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
    """U-007 / U-008 / U-023: CONTAINS / Net Wt lines."""

    def test_info_lines(self):
        self.assertEqual(lr.info_lines({}), [])
        self.assertEqual(lr.info_lines({"allergens": " Milk ", "net_weight": "16 OZ"}),
                         [("CONTAINS: MILK", True), ("Net Wt: 16 OZ", False)])
        # U-023: standard names in the law's order, as in the state's example
        self.assertEqual(lr.info_lines({"allergens": "kaju, soy, milk"}),
                         [("CONTAINS: MILK, CASHEWS, SOYBEANS", True)])

    def test_lines_only_on_ingredient_and_combined(self):
        p = next(x for x in helpers.fixture_products() if x["name"] == "GUJRATI DAL")
        p = dict(p, allergens="", net_weight="")
        extra = dict(p, allergens="Milk", net_weight="16 OZ")
        for lt, size in VARIANTS:
            same = render(p, lt, size).tobytes() == render(extra, lt, size).tobytes()
            self.assertEqual(same, lt == "Barcode", lt)

    def test_combined_never_runs_off_label(self):
        """With far more allergens than any real product, the combined label fits at
        the store's spacing (1.75) and below.  At the widest spacing (3.0) it may not:
        it is then refused with a message (U-023) instead of cutting text off."""
        products = [p for p in helpers.fixture_products() if p["ingredients"]]
        for spacing in (1.0, 1.75, 3.0):
            for p in products:
                with self.subTest(spacing=spacing, product=p["name"]):
                    try:
                        img = render(dict(p, **WORST_EXTRAS), "Combined", "2.25x3.00",
                                     dpi=203, spacing=spacing)
                    except lr.LabelTextDoesNotFit as e:
                        self.assertGreater(spacing, 1.75)
                        self.assertIn("Label spacing smaller", str(e))
                        continue
                    self.assertLess(bottom_ink_row(img), img.height - 2)

    def test_real_allergens_fit_at_every_spacing(self):
        """Every real CONTAINS line fits every label at every spacing setting."""
        for spacing in (1.0, 3.0):
            for p in [x for x in helpers.fixture_products() if x["allergens"]]:
                for lt, size in (("Ingredient", "2.25x1.25"), ("Combined", "2.25x3.00")):
                    with self.subTest(spacing=spacing, product=p["name"], label=lt):
                        img = render(p, lt, size, dpi=203, spacing=spacing)
                        self.assertLess(bottom_ink_row(img), img.height - 2)

    def test_no_ingredient_text_dropped(self):
        """Text that doesn't fit raises LabelTextDoesNotFit (U-023), so a render
        that returns has every ingredient and the whole CONTAINS line."""
        refused = []
        for p in [x for x in helpers.fixture_products() if x["ingredients"]]:
            for lt, size in (("Combined", "2.25x3.00"), ("Ingredient", "2.25x1.25")):
                try:
                    render(dict(p, **WORST_EXTRAS), lt, size, dpi=203)
                except lr.LabelTextDoesNotFit:
                    refused.append((p["name"], lt))
        self.assertEqual(refused, [])

    def test_real_allergens_fit_every_label_at_every_resolution(self):
        """U-023: every product's real CONTAINS line, on every label that shows it,
        on screen (150), at the store printers' 203 DPI and the 600 DPI fallback."""
        products = [p for p in helpers.fixture_products() if p["allergens"]]
        self.assertGreaterEqual(len(products), 40)
        for p in products:
            for lt, size in (("Ingredient", "2.25x1.25"), ("Ingredient", "2.25x3.00"),
                             ("Combined", "2.25x3.00")):
                for dpi in (150, 203, 600):
                    with self.subTest(product=p["name"], label=lt, size=size, dpi=dpi):
                        with_line = render(p, lt, size, dpi=dpi)
                        without = render(dict(p, allergens=""), lt, size, dpi=dpi)
                        self.assertNotEqual(with_line.tobytes(), without.tobytes())
                        if lt == "Combined":
                            self.assertLess(bottom_ink_row(with_line), with_line.height - 2)

    def test_contains_line_same_size_as_ingredients(self):
        """FDA: the CONTAINS statement is in the same type size as the ingredient list."""
        p = next(x for x in helpers.fixture_products() if x["name"] == "LADOO")
        seen = []
        orig = lr._draw_ingredients_block

        def spy(draw, ingredients, ing_fnt, prefix_fnt, y, w_px, content_w, margin, dpi,
                max_y=None, extras=()):
            seen.append((ing_fnt.size, [f.size for _, f in extras], [t for t, _ in extras]))
            return orig(draw, ingredients, ing_fnt, prefix_fnt, y, w_px, content_w, margin, dpi,
                        max_y=max_y, extras=extras)

        lr._draw_ingredients_block = spy
        try:
            for lt, size in (("Ingredient", "2.25x1.25"), ("Combined", "2.25x3.00")):
                render(p, lt, size, dpi=203)
        finally:
            lr._draw_ingredients_block = orig
        for ing_size, extra_sizes, texts in seen:
            self.assertEqual(texts, ["CONTAINS: MILK, ALMONDS, CASHEWS, WHEAT, SESAME"])
            self.assertEqual(extra_sizes, [ing_size])

    def test_text_that_cannot_fit_is_refused_not_cut(self):
        p = next(x for x in helpers.fixture_products() if x["name"] == "GUJRATI DAL")
        huge = dict(p, ingredients=", ".join(["Pigeon Peas Lentils, Tamarind, Jaggery"] * 40))
        with self.assertRaises(lr.LabelTextDoesNotFit) as caught:
            render(huge, "Ingredient", "2.25x1.25", dpi=203)
        self.assertIn("Print Combined", str(caught.exception))
        self.assertIsInstance(caught.exception, RuntimeError)   # shown as a print error


class _DrawSpy:
    """Wraps ImageDraw to record every text drawn and every barcode bar."""

    def __init__(self, draw, log):
        self._d, self._log = draw, log

    def __getattr__(self, name):
        return getattr(self._d, name)

    def text(self, xy, text, font=None, **kw):
        self._log["text"].append((text, self._d.textbbox(xy, text, font=font)))
        return self._d.text(xy, text, font=font, **kw)

    def rectangle(self, box, **kw):
        self._log["bars"].append(box)
        return self._d.rectangle(box, **kw)


class TestBarcodeLabelDate(unittest.TestCase):
    """U-026: the date on the barcode label never runs into the barcode or the white
    quiet zone a scanner needs ("Best By : 11/21/2026" used to overlap the bars)."""

    def test_date_clear_of_barcode_and_address(self):
        from barcode_engine import QUIET_MODULES
        s = helpers.fixture_settings()
        products = [p for p in helpers.fixture_products() if p["barcode_number"]][::7]
        orig_draw = lr.ImageDraw.Draw
        try:
            for p in products:
                for mode, pack in (("Best By", date(2026, 12, 21)), ("Packed", date(2026, 12, 28))):
                    for size in ("2.25x1.25", "2.25x3.00"):
                        for dpi in (150, 203, 600):
                            log = {"text": [], "bars": []}
                            lr.ImageDraw.Draw = lambda im, _o=orig_draw, _l=log: _DrawSpy(_o(im), _l)
                            lr.render_label(dict(p, date_mode=mode), "Barcode", size, pack, FLAGS_ALL,
                                            s, s["address_line"], 10, dpi, s["label_spacing"],
                                            s["label_margin_in"])
                            with self.subTest(product=p["name"], mode=mode, size=size, dpi=dpi):
                                module = min(b[2] - b[0] + 1 for b in log["bars"])
                                quiet_start = min(b[0] for b in log["bars"]) - QUIET_MODULES * module
                                dates = [bb for t, bb in log["text"]
                                         if t.startswith(mode) or t[:2].rstrip("/").isdigit()
                                         and "/" in t]
                                self.assertGreaterEqual(len(dates), 1)
                                address_top = next(bb[1] for t, bb in log["text"]
                                                   if t == s["address_line"])
                                for bb in dates:
                                    self.assertLess(bb[2], quiet_start)
                                    self.assertLessEqual(bb[3], address_top)
                                drawn = " ".join(t for t, _ in log["text"])
                                self.assertIn("12/31/2026" if mode == "Best By" else "12/28/2026",
                                              drawn)
        finally:
            lr.ImageDraw.Draw = orig_draw


class TestDates(unittest.TestCase):
    def test_date_lines(self):
        self.assertEqual(lr.format_date_line("Best By", PACK_DATE, 10), "Best By : 9/27/2026")
        self.assertEqual(lr.format_date_line("Packed", PACK_DATE, 10), "Packed : 9/17/2026")
        self.assertIsNone(lr.format_date_line("None", PACK_DATE, 10))


if __name__ == "__main__":
    unittest.main()
