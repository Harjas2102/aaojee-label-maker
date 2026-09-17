"""Database: products, schema upgrade, Trash, print / price history, backups."""

import glob
import os
import shutil
import sqlite3
import unittest

import helpers
from database import Database


class TestProducts(helpers.TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.db = helpers.make_database(self.tmp)

    def test_all_fixture_products_load(self):
        self.assertEqual(len(self.db.get_all_products()), len(helpers.fixture_products()))

    def test_search_is_literal_and_matches_barcodes(self):
        self.assertEqual(self.db.search_products("%"), [])
        self.assertEqual(self.db.search_products("_"), [])
        self.assertTrue(any(p["barcode_number"] == "310800" for p in self.db.search_products("3108")))
        names = [p["name"] for p in self.db.search_products("channa")]
        self.assertTrue(names and all("CHANNA" in n for n in names))

    def test_scanned_code_listed_first(self):
        rows = self.db.search_products("03108006", ["310800"])
        self.assertEqual(rows[0]["barcode_number"], "310800")

    def test_insert_update_keeps_unlisted_fields(self):
        pid = self.db.save_product({"name": "T", "allergens": "Milk", "net_weight": "8 OZ",
                                    "category": "Sweets", "price": 1.5, "barcode_number": "999990"})
        self.db.save_product({"id": pid, "name": "T2", "price": 2.0})
        p = self.db.get_product(pid)
        self.assertEqual((p["name"], p["price"], p["allergens"], p["net_weight"], p["category"]),
                         ("T2", 2.0, "Milk", "8 OZ", "Sweets"))

    def test_next_barcode_skips_used(self):
        a = self.db.get_next_barcode(100000)
        self.db.save_product({"name": "T", "barcode_number": a})
        self.assertNotEqual(self.db.get_next_barcode(100000), a)

    def test_connections_closed(self):
        self.db.get_all_products()
        self.assertFalse(os.path.exists(self.db.db_path + "-wal"))


class TestSchemaUpgrade(helpers.TempDirTestCase):
    def _old_database(self):
        path = os.path.join(self.tmp, "products.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
              subtitle TEXT NOT NULL DEFAULT '', ingredients TEXT NOT NULL DEFAULT '',
              size TEXT NOT NULL DEFAULT '', price REAL, barcode_number TEXT NOT NULL DEFAULT '',
              date_mode TEXT NOT NULL DEFAULT 'Packed', notes TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now')));
        """)
        for p in helpers.fixture_products():
            conn.execute("INSERT INTO products (id, name, subtitle, ingredients, size, price, "
                         "barcode_number, date_mode, notes) VALUES (?,?,?,?,?,?,?,?,?)",
                         [p[k] for k in ("id", "name", "subtitle", "ingredients", "size", "price",
                                         "barcode_number", "date_mode", "notes")])
        conn.commit()
        conn.close()
        return path

    def test_upgrade_backs_up_once_and_keeps_data(self):
        path = self._old_database()
        backups = os.path.join(self.tmp, "backups")
        before = sqlite3.connect(path).execute("SELECT * FROM products ORDER BY id").fetchall()
        db = Database(path, backup_dir=backups)
        conn = sqlite3.connect(path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(products)")}
        self.assertTrue({"allergens", "net_weight", "category", "deleted_at"} <= cols)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], Database.SCHEMA_VERSION)
        after = conn.execute("SELECT id, name, subtitle, ingredients, size, price, barcode_number, "
                             "date_mode, notes FROM products ORDER BY id").fetchall()
        conn.close()
        self.assertEqual([tuple(r[:9]) for r in after],
                         [tuple(r[i] for i in range(9)) for r in before])
        self.assertEqual(len(glob.glob(os.path.join(backups, "premigration_v*.db"))), 1)
        Database(path, backup_dir=backups)
        self.assertEqual(len(glob.glob(os.path.join(backups, "premigration_v*.db"))), 1)
        self.assertEqual(len(db.get_all_products()), len(before))


class TestTrash(helpers.TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.db = helpers.make_database(self.tmp, products=[])
        self.pid = self.db.save_product({"name": "TRASH ME", "barcode_number": "999991"})

    def test_delete_hides_and_restore_returns(self):
        self.db.delete_product(self.pid)
        self.assertIsNone(self.db.get_product(self.pid))
        self.assertEqual(self.db.search_products("TRASH"), [])
        self.assertEqual(self.db.get_products_by_barcode(["999991"]), [])
        self.assertEqual([p["id"] for p in self.db.get_trash()], [self.pid])
        self.assertNotEqual(self.db.get_next_barcode(999991), "999991")
        self.db.restore_product(self.pid)
        self.assertIsNotNone(self.db.get_product(self.pid))

    def test_purge_and_empty(self):
        self.db.delete_product(self.pid)
        self.db.purge_product(self.pid)
        self.assertIsNone(self.db.get_product(self.pid, include_deleted=True))
        a = self.db.save_product({"name": "A"})
        self.db.delete_product(a)
        self.assertEqual(self.db.empty_trash(), 1)

    def test_active_product_preferred_in_conflict(self):
        live = self.db.save_product({"name": "LIVE", "barcode_number": "999992"})
        dead = self.db.save_product({"name": "DEAD", "barcode_number": "999992"})
        self.db.delete_product(dead)
        self.assertEqual(self.db.get_barcode_conflict("999992")["id"], live)


class TestHistories(helpers.TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.db = helpers.make_database(self.tmp, products=[])

    def test_print_history(self):
        self.db.log_print({"product_name": "A", "copies": 30, "barcode_number": "314300"})
        self.db.log_print({"product_name": "B"})
        rows = self.db.get_print_history()
        self.assertEqual([r["product_name"] for r in rows], ["B", "A"])
        self.assertEqual(rows[1]["copies"], 30)
        self.assertEqual(len(self.db.get_print_history(query="3143")), 1)
        self.assertEqual(self.db.get_print_history(since="2999-01-01 00:00:00"), [])

    def test_price_batch_and_undo(self):
        a = self.db.save_product({"name": "A", "price": 4.99})
        b = self.db.save_product({"name": "B", "price": 2.49})
        batch = self.db.apply_price_batch([{"id": a, "new_price": 5.49},
                                           {"id": b, "new_price": 2.99}], "test")
        self.assertEqual(len(self.db.get_last_price_batch()), 2)
        self.db.save_product({"id": b, "price": 3.25})
        restored, kept = self.db.undo_price_batch(batch)
        self.assertEqual((restored, kept), (1, ["B"]))
        self.assertEqual(self.db.get_product(a)["price"], 4.99)
        self.assertEqual(self.db.get_product(b)["price"], 3.25)
        self.assertEqual(self.db.get_last_price_batch(), [])


class TestBackups(helpers.TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.db = helpers.make_database(self.tmp)

    def test_backup_includes_wal_data_and_is_single_file(self):
        holder = sqlite3.connect(self.db.db_path)
        holder.execute("PRAGMA journal_mode=WAL")
        holder.execute("INSERT INTO products (name) VALUES ('WAL ONLY')")
        holder.commit()
        dest = self.db.backup(os.path.join(self.tmp, "backups"))
        holder.close()
        conn = sqlite3.connect(dest)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM products WHERE name='WAL ONLY'").fetchone()[0], 1)
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        conn.close()

    def test_restore_rejects_wrong_files_and_round_trips(self):
        bad = os.path.join(self.tmp, "bad.db")
        with open(bad, "w") as f:
            f.write("not a database")
        with self.assertRaises(ValueError):
            self.db.restore_from(bad)
        export = os.path.join(self.tmp, "export.db")
        self.db.export_to(export)
        self.db.delete_product(self.db.get_all_products()[0]["id"])
        self.db.purge_product(self.db.get_trash()[0]["id"])
        self.db.restore_from(export)
        self.assertEqual(len(self.db.get_all_products()), len(helpers.fixture_products()))

    def test_rotation_keeps_30(self):
        folder = os.path.join(self.tmp, "b")
        os.makedirs(folder)
        for i in range(35):
            open(os.path.join(folder, f"products_20990101_0000{i:02d}.db"), "w").close()
        open(os.path.join(folder, "premigration_v2_x.db"), "w").close()
        self.db.cleanup_old_backups(folder, 30)
        self.assertEqual(len(glob.glob(os.path.join(folder, "products_*.db"))), 30)
        self.assertTrue(os.path.exists(os.path.join(folder, "premigration_v2_x.db")))


if __name__ == "__main__":
    unittest.main()
