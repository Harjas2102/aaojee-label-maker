"""The real main window, driven like a user (dialogs answered by the test).

Skipped when AAOJEE_SKIP_GUI_TESTS=1 (tools/run_tests.py --quick).
"""

import csv
import os
import time
import unittest

import helpers

ALOO_MATTAR = "03143009"        # 8-digit scan of barcode 314300
CHANNA_DAL_COOKED = "03108006"   # 310800
CHANNA_DAL_2LB = "03046009"      # 304600
GUJRATI_DAL = "03150009"         # 315000
PANEER_BHURJI = "301100"         # typed 6-digit barcode


@unittest.skipUnless(helpers.GUI_ENABLED, "window tests skipped (--quick)")
class GuiTestCase(helpers.TempDirTestCase):
    settings_overrides: dict = {}

    def setUp(self):
        super().setUp()
        self.h = helpers.GuiHarness(self.tmp, **self.settings_overrides)
        self.app = self.h.app

    def tearDown(self):
        self.h.close()
        super().tearDown()

    def set_pin(self, pin="1234"):
        self.h.pins[:] = [pin, pin]
        self.app._on_set_pin()
        self.app._on_lock_now()
        self.h.pump()


# ── U-014 / U-016: screens, theme, modes ─────────────────────────────────────

class TestScreens(GuiTestCase):
    def test_starts_on_print_screen_with_search_focused(self):
        self.assertEqual(self.app._mode, "print")
        self.assertTrue(self.app._print_page.winfo_manager())
        self.assertFalse(self.app._edit_page.winfo_manager())
        self.assertEqual(self.h.focused(), self.app._search_entry)
        self.assertEqual(self.app._queue_btn.cget("text"), "Print Queue (0)")

    def test_modern_theme_when_available(self):
        import app_window
        self.assertEqual(self.app._modern_theme, app_window.sv_ttk is not None)

    def test_edit_screen_without_pin(self):
        self.assertTrue(self.app._set_mode("edit"))
        self.assertTrue(self.app._edit_page.winfo_manager())
        self.assertFalse(self.app._print_page.winfo_manager())
        self.assertTrue(self.app._set_mode("print"))
        self.assertTrue(self.app._print_page.winfo_manager())

    def test_edit_screen_needs_pin(self):
        self.set_pin()
        self.h.pins[:] = [None]
        self.assertFalse(self.app._set_mode("edit"))
        self.assertEqual(self.app._mode, "print")
        self.h.pins[:] = ["0000"]
        self.assertFalse(self.app._set_mode("edit"))
        self.h.pins[:] = ["1234"]
        self.assertTrue(self.app._set_mode("edit"))
        self.assertIn("unlocked", self.app._lock_var.get())

    def test_edit_screen_closes_when_pin_times_out(self):
        self.set_pin()
        self.h.pins[:] = ["1234"]
        self.app._set_mode("edit")
        self.app.lock._unlocked_until = time.monotonic() - 1
        self.app._refresh_lock_ui()
        self.assertEqual(self.app._mode, "print")
        self.assertIn("Locked", self.app._lock_var.get())

    def test_timeout_keeps_unsaved_edits(self):
        self.set_pin()
        self.h.open_barcode(ALOO_MATTAR)
        self.h.pins[:] = ["1234"]
        self.app._set_mode("edit")
        self.app._price_var.set("9.99")
        self.app.lock._unlocked_until = time.monotonic() - 1
        self.app._refresh_lock_ui()
        self.assertEqual(self.app._mode, "edit")

    def test_leaving_edit_with_unsaved_changes(self):
        self.h.open_barcode(ALOO_MATTAR)
        self.app._set_mode("edit")
        self.app._price_var.set("9.99")
        self.h.answers[:] = [None]
        self.assertFalse(self.app._set_mode("print"))
        self.assertEqual(self.app._price_var.get(), "9.99")
        self.h.answers[:] = [False]
        self.assertTrue(self.app._set_mode("print"))
        self.assertEqual(self.app._price_var.get(), "4.99")      # reverted to saved

    def test_new_product_opens_edit_screen(self):
        self.app._on_new()
        self.h.pump()
        self.assertEqual(self.app._mode, "edit")
        self.assertEqual(len(self.app._barcode_var.get()), 6)

    def test_ctrl_s_ignored_on_print_screen(self):
        self.h.open_barcode(ALOO_MATTAR)
        self.app._price_var.set("7.77")        # not reachable by hand on this screen
        self.h.key(self.app._search_entry, "<Control-s>")
        self.assertEqual(self.app.db.get_barcode_conflict("314300")["price"], 4.99)

    def test_spacing_and_margin_moved_to_settings(self):
        import app_window
        opened = []
        dialog = app_window.SettingsDialog(self.h.root, self.app.settings, [],
                                           lambda: opened.append(True))
        dialog._spacing_var.set("1.25")
        dialog._margin_var.set("0.10")
        dialog._save()
        self.assertEqual(self.app.settings.get("label_spacing"), 1.25)
        self.assertEqual(self.app._get_spacing(), 1.25)
        # U-025: spacing never goes above 2.5, even if settings.json says more
        self.app.settings.set("label_spacing", 3.0)
        self.assertEqual(self.app._get_spacing(), 2.5)
        self.assertEqual(self.app._get_margin(), 0.10)
        self.assertTrue(opened)


# ── U-017: keyboard flow; U-001 scanning ─────────────────────────────────────

class TestKeyboard(GuiTestCase):
    def test_type_enter_quantity_enter_prints(self):
        app = self.app
        app._search_var.set("gujrati")
        self.h.key(app._search_entry, "<Return>", 400)
        self.assertEqual(app._name_var.get(), "GUJRATI DAL")
        self.assertEqual(self.h.focused(), app._qty_entry)
        app._qty_var.set("3")
        self.h.key(app._qty_entry, "<Return>")
        self.assertEqual(self.h.printed[-1][2:], ("2.25x1.25", 3))
        self.assertEqual(self.h.focused(), app._search_entry)

    def test_shift_enter_prints_ingredients_and_f_keys(self):
        app = self.app
        self.h.open_barcode(GUJRATI_DAL)
        self.h.key(app._qty_entry, "<Shift-Return>")
        rows = app.db.get_print_history()
        self.assertEqual(rows[0]["label_type"], "Ingredient")
        self.h.key(app._search_entry, "<F5>")
        self.assertEqual(app.db.get_print_history()[0]["label_type"], "Barcode")
        self.h.key(app._search_entry, "<F8>")
        self.assertEqual(len(app.print_queue.items), 1)

    def test_print_keys_do_nothing_on_edit_screen(self):
        self.h.open_barcode(GUJRATI_DAL)
        self.app._set_mode("edit")
        self.h.key(self.app._name_entry, "<F5>")
        self.assertEqual(self.h.printed, [])

    def test_arrow_keys_move_through_list(self):
        app = self.app
        app._search_var.set("channa")
        self.h.pump()
        self.h.key(app._search_entry, "<Down>")
        first = app._tree_id_map[app._tree.selection()[0]]
        self.h.key(app._search_entry, "<Down>")
        second = app._tree_id_map[app._tree.selection()[0]]
        self.assertNotEqual(first, second)
        self.assertEqual(app._current_id, second)
        self.h.key(app._search_entry, "<Up>")
        self.assertEqual(app._current_id, first)

    def test_scan_opens_product_and_stays_in_search(self):
        app = self.app
        app._category_var.set("Cooked Food / Ingredient Labels")
        app._on_filter_change()
        app._search_var.set(ALOO_MATTAR)
        self.h.key(app._search_entry, "<Return>")
        self.assertEqual(app._name_var.get(), "ALOO MATTAR")
        self.assertEqual(self.h.focused(), app._search_entry)
        self.assertTrue(app._search_entry.selection_present())

    def test_scan_of_filtered_out_product_and_unknown_barcode(self):
        app = self.app
        app._category_var.set("Cooked Food / Ingredient Labels")
        app._on_filter_change()
        self.h.open_barcode(CHANNA_DAL_2LB)
        self.assertEqual(app._name_var.get(), "CHANNA DAL")
        self.assertEqual(app._category_var.get(), "All Items")
        self.h.open_barcode("09999991")
        self.assertIn("No product has barcode", app._count_var.get())
        self.h.open_barcode("031000000806")                   # UPC-A form
        self.assertEqual(app._name_var.get(), "CHANNA DAL COOKED")


# ── U-004 unsaved changes, editing, U-010 duplicate, U-012 trash ─────────────

class TestEditing(GuiTestCase):
    def setUp(self):
        super().setUp()
        self.h.open_barcode(ALOO_MATTAR)
        self.app._set_mode("edit")

    def test_unsaved_prompt_when_opening_another_product(self):
        app = self.app
        app._price_var.set("5.25")
        self.h.answers[:] = [None]
        self.h.open_barcode(CHANNA_DAL_COOKED)
        self.assertEqual((app._name_var.get(), app._price_var.get()), ("ALOO MATTAR", "5.25"))
        self.h.answers[:] = [True]
        self.h.open_barcode(CHANNA_DAL_COOKED)
        self.assertEqual(app.db.get_barcode_conflict("314300")["price"], 5.25)
        self.assertEqual(app._name_var.get(), "CHANNA DAL COOKED")

    def test_bad_price_refused_and_save_normalises(self):
        app = self.app
        app._price_var.set("4,99")
        self.assertFalse(app._on_save())
        self.assertIn("Price must be a number", app._status_var.get())
        app._name_var.set("aloo mattar")
        app._barcode_var.set("3143")
        app._price_var.set("4.5")
        self.assertTrue(app._on_save())
        self.assertEqual((app._name_var.get(), app._barcode_var.get(), app._price_var.get()),
                         ("ALOO MATTAR", "314300", "4.50"))
        self.assertIn("Saved", app._status_var.get())

    def test_new_fields_and_category_suggestion(self):
        app = self.app
        app._allergens_var.set("Milk")
        app._net_weight_var.set("16 oz")
        self.assertTrue(app._on_save())
        p = app.db.get_barcode_conflict("314300")
        self.assertEqual((p["allergens"], p["net_weight"]), ("Milk", "16 OZ"))
        app._on_new()
        app._name_var.set("kaju katli test")
        app._size_var.set("8 oz")
        self.assertTrue(app._on_save())
        self.assertEqual(app.db.get_product(app._current_id)["category"], "Sweets")

    def test_duplicate_as_new_size(self):
        app = self.app
        source_id = app._current_id
        app._on_duplicate()
        self.assertIsNone(app._current_id)
        self.assertEqual((app._name_var.get(), app._size_var.get()), ("ALOO MATTAR", ""))
        self.assertNotEqual(app._barcode_var.get(), "314300")
        app._size_var.set("32 OZ")
        self.assertTrue(app._on_save())
        self.assertNotEqual(app._current_id, source_id)

    def test_delete_goes_to_trash_and_restores(self):
        app = self.app
        pid = app._current_id
        self.h.answers[:] = [True]
        app._on_delete()
        self.assertIsNone(app.db.get_product(pid))
        app._open_trash()
        self.h.pump()
        window = app._trash_window
        window.tree.selection_set(str(pid))
        window._restore()
        self.assertIsNotNone(app.db.get_product(pid))
        window.destroy()

    def test_close_with_unsaved_changes(self):
        self.app._price_var.set("1.00")
        self.h.answers[:] = [None]
        self.app._on_close()
        self.assertTrue(self.h.root.winfo_exists())


# ── Printing: U-005 native DPI, U-009 history, U-002 queue, date / barcode checks

class TestPrinting(GuiTestCase):
    def setUp(self):
        super().setUp()
        self.h.open_barcode(GUJRATI_DAL)

    def test_native_dpi_and_fallback(self):
        app = self.app
        app._qty_var.set("2")
        app._print_label_type("Barcode")
        self.assertEqual(self.h.printed[-1], ((457, 254), "1", "2.25x1.25", 2))
        app.settings.set("print_at_printer_dpi", False)
        app._printer_dpi_cache.clear()
        self.h.answers[:] = [True]                     # U-027: yes, the 3-inch roll is in
        app._print_label_type("Combined")
        self.assertEqual(self.h.printed[-1][:3], ((1350, 1800), "RGB", "2.25x3.00"))

    def test_history_records_each_print(self):
        app = self.app
        app._print_label_type("Barcode")
        app._on_test_print()
        app.print_queue.add(app._current_id, "Barcode + Ingredients", 2)
        app._open_print_queue()
        self.h.pump()
        self.h.answers[:] = [True]
        app._queue_window._print_all()
        sources = [(r["source"], r["label_type"]) for r in app.db.get_print_history()]
        self.assertEqual(sources, [("Queue", "Ingredient"), ("Queue", "Barcode"),
                                   ("Test Print", "Barcode"), ("Print", "Barcode")])
        app._open_print_history()
        self.h.pump()
        self.assertEqual(len(app._history_window.tree.get_children()), 4)
        out = os.path.join(self.tmp, "history.csv")
        self.h.saves[:] = [out]
        app._history_window._export()
        self.assertEqual(len(list(csv.reader(open(out, encoding="utf-8-sig")))), 5)

    def test_invalid_date_blocks_printing(self):
        self.app._print_date_var.set("13/45/2026")
        self.app._print_label_type("Barcode")
        self.assertEqual(self.h.printed, [])
        self.assertIn("not a valid date", self.h.last_message())

    def test_print_date_rolls_over(self):
        from datetime import date, timedelta
        yesterday = date.today() - timedelta(days=1)
        self.app._auto_print_date = yesterday
        self.app._print_date_var.set(f"{yesterday.month}/{yesterday.day}/{yesterday.year}")
        self.app._roll_print_date()
        self.assertEqual(self.app._parse_print_date(), date.today())

    # ── U-022: today's date is pre-filled and comes back by itself ──────────

    def _pick(self, d):
        self.app._print_date_var.set(f"{d.month}/{d.day}/{d.year}")
        self.h.pump(50)

    def test_starts_on_today_with_no_warning(self):
        from datetime import date
        self.assertEqual(self.app._parse_print_date(), date.today())
        self.assertEqual(self.app._date_warning_var.get(), "")

    def test_picked_date_warns_and_is_kept_while_in_use(self):
        import app_window
        from datetime import date, timedelta
        tomorrow = date.today() + timedelta(days=1)
        self._pick(tomorrow)
        self.assertIn("Not today", self.app._date_warning_var.get())
        # 10 minutes later, still printing with it: kept, and the clock restarts
        self.app._date_last_used -= 10 * 60
        self.app._print_label_type("Barcode")
        self.app._roll_print_date(expire_custom=True)
        self.assertEqual(self.app._parse_print_date(), tomorrow)
        self.app._date_last_used -= (app_window.CUSTOM_DATE_MINUTES - 1) * 60
        self.app._roll_print_date(expire_custom=True)
        self.assertEqual(self.app._parse_print_date(), tomorrow)

    def test_picked_date_goes_back_to_today_when_unused(self):
        import app_window
        from datetime import date, timedelta
        self._pick(date.today() - timedelta(days=2))
        self.app._date_last_used -= app_window.CUSTOM_DATE_MINUTES * 60 + 1
        self.app._schedule_date_rollover()           # the once-a-minute check
        self.assertEqual(self.app._parse_print_date(), date.today())
        self.assertEqual(self.app._date_warning_var.get(), "")

    def test_date_never_changes_at_the_moment_of_printing(self):
        import app_window
        from datetime import date, timedelta
        tomorrow = date.today() + timedelta(days=1)
        self._pick(tomorrow)
        self.app._date_last_used -= app_window.CUSTOM_DATE_MINUTES * 60 + 1
        self.app._print_label_type("Barcode")
        row = self.app.db.get_print_history()[0]
        self.assertEqual(row["print_date"], f"{tomorrow.month}/{tomorrow.day}/{tomorrow.year}")

    def test_today_button_and_bad_date_warning(self):
        from datetime import date
        self.app._print_date_var.set("13/45/2026")
        self.h.pump(50)
        self.assertIn("Not a valid date", self.app._date_warning_var.get())
        self.app._print_date_var.set(self.app._today_str())
        self.h.pump(50)
        self.assertEqual(self.app._parse_print_date(), date.today())
        self.assertEqual(self.app._date_warning_var.get(), "")

    def test_card_and_preview(self):
        app = self.app
        app._update_preview()
        self.assertIn("$3.99", app._card_details_var.get())
        self.assertTrue(app._card_date_var.get().startswith("Best By : "))
        for mode in ("Barcode", "Ingredient", "Combined", "All"):
            app._preview_type_var.set(mode)
            app._update_preview()
            shown = [v for v, t in app._preview_tiles.items()
                     if t["frame"].winfo_manager() and t["image"] is not None]
            self.assertEqual(len(shown), 3 if mode == "All" else 1, mode)

    def test_preview_grows_with_window(self):
        app = self.app
        root = self.h.root
        if root.winfo_screenwidth() < 1800 or root.winfo_screenheight() < 950:
            # GitHub's test machines have a 1024x768 screen; Windows won't make the window larger.
            self.skipTest("screen too small to resize the window")
        app._preview_type_var.set("Barcode")
        self.h.root.geometry("1280x800")
        self.h.pump(400)
        app._update_preview()
        small = int(app._preview_tiles["Barcode"]["canvas"].cget("width"))
        self.h.root.geometry("1800x950")
        self.h.pump(500)
        app._update_preview()
        large = int(app._preview_tiles["Barcode"]["canvas"].cget("width"))
        self.assertGreater(large, small)


class TestTools(GuiTestCase):
    def test_price_change_apply_and_undo(self):
        app = self.app
        app._search_var.set("DAL")
        self.h.pump()
        before = {p["id"]: p["price"] for p in app.db.get_all_products()}
        app._open_price_tools()
        self.h.pump()
        window = app._price_window
        window._amount.set("10")
        self.h.pump()
        self.h.answers[:] = [True, False]
        window._apply()
        changed = sum(1 for p in app.db.get_all_products() if p["price"] != before[p["id"]])
        self.assertGreater(changed, 0)
        self.h.answers[:] = [True]
        window._undo_last()
        self.assertEqual({p["id"]: p["price"] for p in app.db.get_all_products()}, before)
        window.destroy()

    def test_sorting_and_filters(self):
        app = self.app
        app._on_sort_column("price")
        self.h.pump()
        prices = [float(app._tree.item(i, "values")[3]) for i in app._tree.get_children()
                  if app._tree.item(i, "values")[3]]
        self.assertEqual(prices, sorted(prices))
        app._category_var.set("Spices")
        app._on_filter_change()
        self.assertTrue(all(p["category"] == "Spices" for p in app.visible_products()))


# ── U-023: allergens — the CONTAINS line (NY Agriculture and Markets Law § 199-g)

class TestAllergens(GuiTestCase):
    """PANEER BHURJI: "Cottage Cheese, Peas, …", allergens "Milk"."""

    def setUp(self):
        super().setUp()
        self.h.open_barcode(PANEER_BHURJI)
        self.assertEqual(self.app._name_var.get(), "PANEER BHURJI")

    def saved(self) -> str:
        return self.app.db.get_product(self.app._current_id)["allergens"]

    def test_card_shows_contains_line_and_warning(self):
        app = self.app
        app._update_preview()
        self.assertEqual(app._card_allergens_var.get(), "CONTAINS: MILK")
        self.assertEqual(app._card_allergen_warn_var.get(), "")
        app._allergens_var.set("")
        app._update_preview()
        self.assertIn("MILK is not on the CONTAINS line", app._card_allergen_warn_var.get())
        self.assertEqual(app._allergen_check_var.get(), app._card_allergen_warn_var.get())

    def test_save_offers_to_add_missing_allergens(self):
        app = self.app
        app._allergens_var.set("")
        self.h.answers[:] = [None]                    # Cancel: stay, nothing saved
        self.assertFalse(app._on_save())
        self.assertEqual(self.saved(), "Milk")
        self.assertIn("“cheese”", self.h.last_message())
        self.h.answers[:] = [False]                   # No: save as it is
        self.assertTrue(app._on_save())
        self.assertEqual(self.saved(), "")
        self.h.answers[:] = [True]                    # Yes: add MILK, then save
        self.assertTrue(app._on_save())
        self.assertEqual(self.saved(), "Milk")
        self.assertEqual(app._allergens_var.get(), "Milk")
        app._ingredients_text.insert("end-1c", ", Cashews")
        self.h.answers[:] = [True]
        self.assertTrue(app._on_save())
        self.assertEqual(self.saved(), "Milk, Cashews")
        self.assertIn("CASHEWS", self.h.last_message())

    def test_broad_names_and_non_allergens_refused(self):
        app = self.app
        app._allergens_var.set("Milk, Tree Nuts")
        self.assertFalse(app._on_save())
        self.assertIn("Name each kind of tree nut", app._status_var.get())
        app._allergens_var.set("Milk, Coconut")
        self.assertFalse(app._on_save())
        self.assertIn("Coconut is not a major food allergen", app._status_var.get())
        self.assertEqual(self.saved(), "Milk")

    def test_typed_names_saved_in_standard_form(self):
        app = self.app
        app._allergens_var.set("kaju, milk")
        self.assertTrue(app._on_save())
        self.assertEqual(self.saved(), "Milk, Cashews")
        self.assertEqual(app._allergens_var.get(), "Milk, Cashews")

    def test_unknown_name_needs_confirming(self):
        app = self.app
        app._allergens_var.set("Milk, Swai")
        self.h.answers[:] = [False]
        self.assertFalse(app._on_save())
        self.assertIn("Swai", self.h.last_message())
        self.h.answers[:] = [True]
        self.assertTrue(app._on_save())
        self.assertEqual(self.saved(), "Milk, Swai")

    def test_print_asks_when_contains_line_looks_incomplete(self):
        app = self.app
        app._allergens_var.set("")
        self.h.answers[:] = [False]                   # don't print
        app._print_label_type("Ingredient")
        self.assertEqual(self.h.printed, [])
        self.assertIn("Allergen check", self.h.last_message())
        self.h.answers[:] = [True]                    # print anyway
        app._print_label_type("Ingredient")
        self.assertEqual(len(self.h.printed), 1)
        app._print_label_type("Barcode")              # no CONTAINS line: no question
        self.assertEqual(len(self.h.printed), 2)
        app._allergens_var.set("Milk")
        self.h.answers[:] = [True]                    # only the roll question (U-027)
        app._print_label_type("Combined")             # allergens complete: no question
        self.assertEqual(len(self.h.printed), 3)
        self.assertEqual(len(self.h.answers), 0)

    def test_queue_asks_when_contains_line_looks_incomplete(self):
        app = self.app
        app.db.save_product({"id": app._current_id, "allergens": ""})
        app.print_queue.add(app._current_id, "Barcode + Ingredients", 1)
        app._open_print_queue()
        self.h.pump()
        self.h.answers[:] = [False]
        app._queue_window._print_all()
        self.assertEqual(self.h.printed, [])
        self.assertIn("PANEER BHURJI", self.h.last_message())

    def test_label_too_long_is_refused_with_a_message(self):
        app = self.app
        app._ingredients_text.insert("end-1c", ", Cottage Cheese, Peas, Tomatoes" * 60)
        app._print_label_type("Ingredient")
        self.assertEqual(self.h.printed, [])
        self.assertEqual(self.h.messages[-1][:2], ("showerror", "Print Error"))
        self.assertIn("nothing was printed", self.h.last_message())

    def test_picker(self):
        from allergens import AllergenPicker
        app = self.app
        app._allergens_var.set("")
        app._open_allergen_picker()
        self.h.pump()
        picker = [w for w in self.h.root.winfo_children() if isinstance(w, AllergenPicker)][-1]
        self.assertFalse(picker._vars["Milk"].get())
        picker._tick_hints()
        self.assertTrue(picker._vars["Milk"].get())
        self.assertEqual(picker._preview_var.get(), "Will print:  CONTAINS: MILK")
        picker._vars["Cashews"].set(True)
        picker._other_var.set("Tree Nuts")
        picker._ok()                                  # refused: too broad
        self.assertTrue(picker.winfo_exists())
        self.assertIn("tree nut", picker._problem_var.get())
        picker._other_var.set("")
        picker._ok()
        self.assertEqual(app._allergens_var.get(), "Milk, Cashews")


# ── U-027: main label follows the label roll in the printer ───────────────────

class TestSmallRoll(GuiTestCase):
    """The store today: the 2.25 x 1.25 roll, Barcode as the main label."""

    def test_combined_on_small_roll_asks_first(self):
        app = self.app
        self.h.open_barcode(GUJRATI_DAL)
        self.assertEqual(app._main_label(), "Barcode")
        self.h.answers[:] = [False]
        app._print_label_type("Combined")
        self.assertEqual(self.h.printed, [])
        self.assertIn("2.25 × 1.25 roll", self.h.last_message())
        self.h.answers[:] = [True]
        app._print_label_type("Combined")
        self.assertEqual(self.h.printed[-1][2], "2.25x3.00")

    def test_switching_the_roll_in_settings(self):
        import app_window
        app = self.app
        self.assertIn("Enter", app._barcode_btn.cget("text"))
        dialog = app_window.SettingsDialog(self.h.root, app.settings, [], app._on_settings_saved)
        dialog._size_var.set(app_window.ROLL_CHOICES["2.25x3.00"])
        dialog._save()
        self.assertEqual(app.settings.default_label_size, "2.25x3.00")
        self.assertEqual(app._main_label(), "Combined")
        self.assertIn("Enter", app._combined_btn.cget("text"))
        self.assertNotIn("Enter", app._barcode_btn.cget("text"))
        dialog = app_window.SettingsDialog(self.h.root, app.settings, [], app._on_settings_saved)
        self.assertEqual(dialog._size_var.get(), app_window.ROLL_CHOICES["2.25x3.00"])
        dialog._size_var.set(app_window.ROLL_CHOICES["2.25x1.25"])
        dialog._save()
        self.assertEqual(app._main_label(), "Barcode")
        self.assertIn("Enter", app._barcode_btn.cget("text"))


class TestThreeInchRoll(GuiTestCase):
    """After the switch: the 2.25 x 3.00 roll, Combined as the main label."""
    settings_overrides = {"default_label_size": "2.25x3.00"}

    def test_enter_prints_combined_with_no_roll_question(self):
        app = self.app
        self.assertEqual(app._main_label(), "Combined")
        buttons = [w for w in app._barcode_btn.master.pack_slaves()
                   if w in (app._combined_btn, app._barcode_btn)]
        self.assertEqual(buttons, [app._combined_btn, app._barcode_btn])   # Combined first
        app._search_var.set("gujrati")
        self.h.key(app._search_entry, "<Return>", 400)
        app._qty_var.set("2")
        self.h.key(app._qty_entry, "<Return>")
        self.assertEqual(self.h.printed[-1], ((457, 609), "1", "2.25x3.00", 2))
        self.assertEqual(app.db.get_print_history()[0]["label_type"], "Combined")
        self.h.key(app._search_entry, "<F5>")                 # barcode label: 3 inches too
        self.assertEqual(self.h.printed[-1][2], "2.25x3.00")
        self.assertEqual(app.db.get_print_history()[0]["label_type"], "Barcode")

    def test_queue_and_test_print_use_the_big_roll(self):
        app = self.app
        self.h.open_barcode(GUJRATI_DAL)
        app._on_add_to_queue()
        self.assertEqual(app.print_queue.items[-1]["label"], "Combined")
        app._on_test_print()
        self.assertEqual(self.h.printed[-1][2], "2.25x3.00")
        app._open_print_queue()
        self.h.pump()
        self.assertIn("Combined", app._queue_window._label_values())
        self.h.answers[:] = [True]                            # "Print N labels?" only
        app._queue_window._print_all()
        self.assertEqual(self.h.printed[-1][2], "2.25x3.00")
        self.assertEqual(len(self.h.answers), 0)


if __name__ == "__main__":
    unittest.main()
