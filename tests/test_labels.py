"""Label rendering: every real product renders, barcodes decode, text fits."""

import unittest
from datetime import date

import helpers
import label_renderer as lr
from barcode_engine import compute_check_digit
from printer_manager import fit_to_stock, to_monochrome

PACK_DATE = date(2026, 9, 17)
FLAGS_ALL = dict(barcode=True, price=True, dollar_sign=True, date=True, address=True)
FLAGS_NONE = dict(barcode=False, price=False, dollar_sign=False, date=False, address=False)
WIDE = lr.WIDE_LABEL          # U-028: "3.00x2.25", the 3-inch sticker on its side
VARIANTS = [("Barcode", "2.25x1.25"), ("Barcode", "2.25x3.00"), ("Ingredient", "2.25x1.25"),
            ("Ingredient", "2.25x3.00"), ("Combined", "2.25x3.00"),
            ("Barcode", WIDE), ("Ingredient", WIDE), ("Combined", WIDE)]
COMBINED = (("Combined", "2.25x3.00"), ("Combined", WIDE))
# More allergens than any real product has (LADOO has 5), plus a long net weight
WORST_EXTRAS = {"allergens": "Milk, Eggs, Almonds, Cashews, Pistachios, Peanuts, Wheat, "
                             "Soybeans, Sesame",
                "net_weight": "32 OZ (907 GM)"}


def render(product, label_type, size, dpi=150, flags=FLAGS_ALL, settings=None, spacing=1.75,
           min_module_in=None):
    s = settings or helpers.fixture_settings()
    return lr.render_label(product, label_type, size, PACK_DATE, flags, s, s["address_line"], 10,
                           dpi, spacing, s.get("label_margin_in", 0.05), min_module_in=min_module_in)


def pixel_size(size: str, dpi: int) -> tuple[int, int]:
    w_in, h_in = lr.label_inches(size)
    return round(w_in * dpi), round(h_in * dpi)


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
                        self.assertEqual(img.size, pixel_size(size, 150))

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
                for lt, size in (("Barcode", "2.25x1.25"), *COMBINED):
                    with self.subTest(dpi=dpi, product=p["name"], label=lt, size=size):
                        img = to_monochrome(render(p, lt, size, dpi=dpi, min_module_in=0.013))
                        self.assertEqual(img.size, pixel_size(size, dpi))
                        if size == WIDE:
                            # U-028: what the printer gets is turned a quarter turn for
                            # the 2.25" roll; turned back, it is the same picture.
                            turned, w_in, h_in = fit_to_stock(img, 3.00, 2.25, 2.45)
                            self.assertEqual((turned.size, w_in, h_in),
                                             (pixel_size("2.25x3.00", dpi), 2.25, 3.00))
                            img = turned.rotate(90, expand=True)
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
                for lt, size in COMBINED:
                    with self.subTest(spacing=spacing, product=p["name"], size=size):
                        try:
                            img = render(dict(p, **WORST_EXTRAS), lt, size,
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
                for lt, size in (("Ingredient", "2.25x1.25"), *COMBINED):
                    with self.subTest(spacing=spacing, product=p["name"], label=lt, size=size):
                        img = render(p, lt, size, dpi=203, spacing=spacing)
                        self.assertLess(bottom_ink_row(img), img.height - 2)

    def test_no_ingredient_text_dropped(self):
        """Text that doesn't fit raises LabelTextDoesNotFit (U-023), so a render
        that returns has every ingredient and the whole CONTAINS line."""
        refused = []
        for p in [x for x in helpers.fixture_products() if x["ingredients"]]:
            for lt, size in (*COMBINED, ("Ingredient", "2.25x1.25"), ("Ingredient", WIDE)):
                try:
                    render(dict(p, **WORST_EXTRAS), lt, size, dpi=203)
                except lr.LabelTextDoesNotFit:
                    refused.append((p["name"], lt, size))
        self.assertEqual(refused, [])

    def test_real_allergens_fit_every_label_at_every_resolution(self):
        """U-023: every product's real CONTAINS line, on every label that shows it,
        on screen (150), at the store printers' 203 DPI and the 600 DPI fallback."""
        products = [p for p in helpers.fixture_products() if p["allergens"]]
        self.assertGreaterEqual(len(products), 40)
        for p in products:
            for lt, size in (("Ingredient", "2.25x1.25"), ("Ingredient", "2.25x3.00"),
                             ("Ingredient", WIDE), *COMBINED):
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
            for lt, size in (("Ingredient", "2.25x1.25"), *COMBINED):
                render(p, lt, size, dpi=203)
        finally:
            lr._draw_ingredients_block = orig
        self.assertGreaterEqual(len(seen), 3)
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
                    for size in ("2.25x1.25", "2.25x3.00", WIDE):
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


class TestWideCombinedLabel(unittest.TestCase):
    """U-028: the combined label on its side, 3.00" wide x 2.25" tall, for the side
    of a 16 oz container.  Price / date / address sit beside the barcode, and the
    ingredients get the rest."""

    def _drawn(self, product, dpi, pack=PACK_DATE, flags=FLAGS_ALL, spacing=None):
        s = helpers.fixture_settings()
        log = {"text": [], "bars": []}
        orig_draw = lr.ImageDraw.Draw
        lr.ImageDraw.Draw = lambda im: _DrawSpy(orig_draw(im), log)
        try:
            img = lr.render_label(product, "Combined", WIDE, pack, flags, s, s["address_line"],
                                  10, dpi, s["label_spacing"] if spacing is None else spacing,
                                  s["label_margin_in"])
        finally:
            lr.ImageDraw.Draw = orig_draw
        return img, log, s

    def test_size_is_three_wide(self):
        self.assertEqual(lr.label_inches(WIDE), (3.00, 2.25))
        self.assertEqual(lr.label_inches("2.25x3.00"), (2.25, 3.00))
        self.assertEqual(lr.label_inches("2.25x1.25"), (2.25, 1.25))
        p = helpers.fixture_products()[0]
        for lt in ("Combined", "Barcode", "Ingredient"):
            self.assertEqual(render(p, lt, WIDE, dpi=203).size, (609, 457))

    def test_nothing_overlaps_or_leaves_the_label(self):
        """Every product with ingredients and a barcode, the widest date, at screen
        and printer resolutions: the ingredient text stays above the footer, the
        price / date / address stay clear of the barcode's quiet zone, and nothing
        is drawn off the label."""
        from barcode_engine import QUIET_MODULES
        products = [p for p in helpers.fixture_products()
                    if p["ingredients"] and p["barcode_number"] and p["price"] is not None]
        self.assertGreaterEqual(len(products), 40)
        for p in products:
            for dpi in (150, 203, 600):
                with self.subTest(product=p["name"], dpi=dpi):
                    p = dict(p, date_mode="Best By")
                    img, log, s = self._drawn(p, dpi, pack=date(2026, 12, 21))
                    w, h = img.size
                    price, when = f"${p['price']:.2f}", "Best By : 12/31/2026"
                    module = min(b[2] - b[0] + 1 for b in log["bars"])
                    bars_left = min(b[0] for b in log["bars"])
                    bars_top = min(b[1] for b in log["bars"])
                    quiet_left = bars_left - QUIET_MODULES * module
                    boxes = {t: bb for t, bb in log["text"]}
                    for t in (price, when, s["address_line"]):          # beside the barcode
                        self.assertIn(t, boxes)
                        self.assertLess(boxes[t][2], quiet_left, t)
                        self.assertLessEqual(boxes[t][3], h - 1, t)
                    footer_top = min(bars_top, boxes[price][1])
                    body = [(t, bb) for t, bb in log["text"]
                            if t not in (price, when, s["address_line"]) and bb[1] < bars_top]
                    self.assertTrue(any(t.startswith("Ingredients : ") for t, _ in body))
                    self.assertIn(lr.contains_line(p["allergens"]) or "Ingredients",
                                  " ".join(t for t, _ in body))
                    for t, bb in body:
                        self.assertLessEqual(bb[3], footer_top, t)      # above the footer
                    for t, bb in log["text"]:
                        self.assertGreaterEqual(bb[0], 0, t)
                        self.assertGreaterEqual(bb[1], 0, t)
                        self.assertLessEqual(bb[2], w, t)
                        self.assertLessEqual(bb[3], h, t)
                    self.assertLessEqual(max(b[2] for b in log["bars"])
                                         + QUIET_MODULES * module, w)   # right quiet zone

    def test_ingredients_never_smaller_than_on_the_upright_label(self):
        """The reason for the layout: every real product's ingredients print at least
        as large as on the 2.25 x 3.00 label, at the size set in Settings (10 pt) for
        all of them."""
        seen = []
        orig = lr._draw_ingredients_block

        def spy(draw, ingredients, ing_fnt, *a, **k):
            seen.append(ing_fnt.size)
            return orig(draw, ingredients, ing_fnt, *a, **k)

        lr._draw_ingredients_block = spy
        try:
            spec = helpers.fixture_settings()["font_ingredients"]
            full = lr.load_font(spec["family"], spec["size"], spec.get("bold", False), dpi=203).size
            for p in [x for x in helpers.fixture_products() if x["ingredients"]]:
                render(p, "Combined", "2.25x3.00", dpi=203)
                upright = seen[-1]           # the last layout pass is the one printed
                render(p, "Combined", WIDE, dpi=203)
                wide = seen[-1]
                with self.subTest(product=p["name"]):
                    self.assertGreaterEqual(wide, upright)
                    self.assertEqual(wide, full)
        finally:
            lr._draw_ingredients_block = orig

    def test_parts_can_be_switched_off(self):
        """Any mix of barcode / price / date / address still renders, and without
        ingredients the name and footer are centred on the label."""
        p = next(x for x in helpers.fixture_products() if x["name"] == "GUJRATI DAL")
        for hide in ("barcode", "price", "date", "address"):
            img = render(p, "Combined", WIDE, dpi=203, flags=dict(FLAGS_ALL, **{hide: False}))
            self.assertNotEqual(img.tobytes(), render(p, "Combined", WIDE, dpi=203).tobytes())
        render(p, "Combined", WIDE, dpi=203, flags=FLAGS_NONE)
        plain = dict(p, ingredients="", allergens="", net_weight="", subtitle="", size="2 LB")
        img, log, _ = self._drawn(plain, 203)
        top = min(bb[1] for _, bb in log["text"])
        bottom = max(bb[3] for _, bb in log["text"])
        self.assertLessEqual(abs(top - (img.height - bottom)), 4)       # centred
        self.assertEqual(helpers.decode_upce(to_monochrome(img))[0], p["barcode_number"])

    def test_text_that_cannot_fit_is_refused_not_cut(self):
        p = next(x for x in helpers.fixture_products() if x["name"] == "GUJRATI DAL")
        huge = dict(p, ingredients=", ".join(["Pigeon Peas Lentils, Tamarind, Jaggery"] * 60))
        with self.assertRaises(lr.LabelTextDoesNotFit):
            render(huge, "Combined", WIDE, dpi=203)


class TestPrintedSideways(unittest.TestCase):
    """U-028: the wide label is turned for the 2.25"-wide roll, and only then."""

    def test_fit_to_stock(self):
        from PIL import Image
        wide = Image.new("1", (609, 457), 1)
        wide.putpixel((0, 0), 0)                       # top-left corner of the label
        img, w_in, h_in = fit_to_stock(wide, 3.00, 2.25, 2.45)        # the store's roll
        self.assertEqual((img.size, img.mode, w_in, h_in), ((457, 609), "1", 2.25, 3.00))
        self.assertEqual(img.getpixel((456, 0)), 0)    # clockwise: the left edge leads
        self.assertEqual(fit_to_stock(wide, 3.00, 2.25, None)[0].size, (457, 609))
        # A real 3-inch-wide roll: printed as it is
        self.assertIs(fit_to_stock(wide, 3.00, 2.25, 3.20)[0], wide)
        self.assertIs(fit_to_stock(wide, 3.00, 2.25, 3.00)[0], wide)
        # Upright labels are never turned
        tall = Image.new("1", (457, 609), 1)
        for stock in (2.45, 2.25, None):
            self.assertEqual(fit_to_stock(tall, 2.25, 3.00, stock), (tall, 2.25, 3.00))
            self.assertEqual(fit_to_stock(tall, 2.25, 1.25, stock), (tall, 2.25, 1.25))


class TestDates(unittest.TestCase):
    def test_date_lines(self):
        self.assertEqual(lr.format_date_line("Best By", PACK_DATE, 10), "Best By : 9/27/2026")
        self.assertEqual(lr.format_date_line("Packed", PACK_DATE, 10), "Packed : 9/17/2026")
        self.assertIsNone(lr.format_date_line("None", PACK_DATE, 10))


if __name__ == "__main__":
    unittest.main()
