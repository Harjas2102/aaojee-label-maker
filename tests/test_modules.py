"""Smaller modules: settings, importer, print queue, PIN, price tools, categories."""

import json
import os
import time
import unittest
from decimal import Decimal

import helpers


class TestSettings(helpers.TempDirTestCase):
    def test_atomic_save_and_defaults_not_shared(self):
        from settings_manager import Settings, DEFAULTS
        s = helpers.make_settings(self.tmp)
        s.set_font("name", "Arial", 20, True)
        s.save()
        self.assertFalse(os.path.exists(s._path + ".tmp"))
        self.assertEqual(json.load(open(s._path))["font_name"]["size"], 20)
        self.assertEqual(DEFAULTS["font_name"]["size"], 22)
        fresh = Settings(os.path.join(self.tmp, "missing.json"))
        self.assertEqual(fresh.address_line, "Aaojee, Middletown, NY 845-342-0040")

    def test_font_save_keeps_italic(self):
        s = helpers.make_settings(self.tmp)
        s.set_font("subtitle", "Arial Narrow", 14, True)
        self.assertTrue(s.get_font("subtitle")["italic"])


class TestImporter(helpers.TempDirTestCase):
    def test_real_mdb_columns_and_prices(self):
        import importer
        cols = ["itemname", "itemsize", "price", "barcodeNo", "barcodetop", "res1"]
        mapping = importer._map_columns(cols)
        self.assertEqual(mapping["barcode_number"], "barcodeNo")
        db = helpers.make_database(self.tmp, products=[])
        rows = [{"itemname": " ALOO MATTAR ", "itemsize": "", "price": "$ 4.99", "barcodeNo": 3143},
                {"itemname": "SONA", "itemsize": "10 LB", "price": "$12.99", "barcodeNo": 12}]
        for _ in range(2):
            result = {"imported": 0, "skipped": 0, "errors": 0, "error_msgs": []}
            for r in rows:
                importer._import_row(r, mapping, db, result)
        products = {p["barcode_number"]: p for p in db.get_all_products()}
        self.assertEqual(len(db.get_all_products()), 2)
        self.assertEqual(products["314300"]["price"], 4.99)
        self.assertEqual(products["120000"]["price"], 12.99)


class TestPrintQueueModel(helpers.TempDirTestCase):
    def test_add_merge_persist(self):
        from print_queue import PrintQueue, default_choice
        path = os.path.join(self.tmp, "print_queue.json")
        q = PrintQueue(path)
        q.add(1, "Barcode", 5)
        q.add(1, "Barcode", 7)
        q.add(2, "Barcode + Ingredients", 2)
        self.assertEqual(q.total_labels(), 16)
        self.assertEqual([(i["product_id"], i["qty"]) for i in PrintQueue(path).items], [(1, 12), (2, 2)])
        self.assertEqual(default_choice({"ingredients": "x"}), "Barcode + Ingredients")
        self.assertEqual(default_choice({"ingredients": ""}), "Barcode")


class TestManagerLock(helpers.TempDirTestCase):
    def test_pin_hash_and_expiry(self):
        from manager_lock import ManagerLock, hash_pin, verify_pin
        stored = hash_pin("1234")
        self.assertNotIn("1234", stored)
        self.assertTrue(verify_pin("1234", stored))
        self.assertFalse(verify_pin("9999", stored))
        s = helpers.make_settings(self.tmp, manager_pin_hash=stored)
        now = [1000.0]
        lock = ManagerLock(s, clock=lambda: now[0])
        self.assertFalse(lock.is_unlocked())
        self.assertTrue(lock.try_unlock("1234"))
        now[0] += 299
        self.assertTrue(lock.is_unlocked())
        now[0] += 2
        self.assertFalse(lock.is_unlocked())


class TestPriceTools(unittest.TestCase):
    def test_rounding(self):
        from price_tools import round_price, new_price
        r = lambda v, m: str(round_price(Decimal(v), m))
        self.assertEqual([r("5.24", "49_99"), r("5.49", "49_99"), r("5.50", "49_99"),
                          r("5.00", "99"), r("5.235", "cent"), r("-1", "cent")],
                         ["5.49", "5.49", "5.99", "5.99", "5.24", "0.01"])
        self.assertEqual(str(new_price(4.99, "percent", Decimal("10"), "49_99")), "5.49")
        self.assertEqual(str(new_price(4.99, "dollars", Decimal("-0.50"), "cent")), "4.49")


class TestCategories(unittest.TestCase):
    def test_suggestions(self):
        from categories import suggest_category as s
        self.assertEqual(s("KAJU KATLI", "14 OZ"), "Sweets")
        self.assertEqual(s("CUMIN SEEDS", "200 GM"), "Spices")
        self.assertEqual(s("MUSTARD OIL", "500 ML"), "Dry Goods")
        self.assertEqual(s("IDLI RICE", "4 LB"), "Dry Goods")
        self.assertEqual(s("CHANA MASALA", ""), "")
        self.assertEqual(s("MASALA IDLI", "5 PCS"), "")


if __name__ == "__main__":
    unittest.main()
