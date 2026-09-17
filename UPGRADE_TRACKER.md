# Aaojee Label Maker — Upgrade Tracker

A running log of every upgrade made to the program: what changed, where in the code, how it
was tested, and how to turn it off or undo it. If something misbehaves after an update, start
here.

**How to use this file**

- Every upgrade gets an ID (`U-001`, `U-002`, …). Add new ones at the bottom of the
  [Upgrade log](#upgrade-log) and add a row to the [Index](#index).
- **From U-014 on, the project is in Git** (see `DEVELOPING.md`). Each upgrade is one or more
  commits, and the commit IDs are listed with the entry. `git show <id>` shows exactly what
  changed, and `git revert <id>` undoes it.
- Before U-014, changes were protected by copying `source/` into `upgrade_snapshots/`.
  Those folders are kept on disk (not in Git).
- Code changes only reach the store after rebuilding with `build.bat` or
  `update_and_build.bat` (close the program first).

---

## Index

| ID    | Date       | Upgrade                                   | Status              | Turn off / undo |
|-------|------------|-------------------------------------------|---------------------|-----------------|
| U-001 | 2026-09-17 | Scan a label to find a product            | Done, not yet built | Restore snapshot |
| U-002 | 2026-09-17 | Print queue (batch printing)              | Done, not yet built | Don't use it; or restore snapshot |
| U-003 | 2026-09-17 | Manager PIN lock                          | Done, not yet built | Settings → Remove Manager PIN |
| U-004 | 2026-09-17 | Unsaved-changes warning                   | Done, not yet built | Restore snapshot |
| U-005 | 2026-09-17 | Sharper barcodes (print at printer's DPI) | Done, not yet built | Settings → untick "Print at the printer's own resolution" |
| U-006 | 2026-09-17 | Product data cleanup (6 parts)            | **Live** (data only, no rebuild needed) | `cleanup.py --undo` (see U-006) |
| U-007 | 2026-09-17 | Allergens "Contains:" line                | Done, not yet built | Leave the Allergens field blank |
| U-008 | 2026-09-17 | Net weight line                           | Done, not yet built | Leave the Net Wt field blank |
| U-009 | 2026-09-17 | Print history                             | Done, not yet built | Restore snapshot (history is only recorded) |
| U-010 | 2026-09-17 | Duplicate as new size                     | Done, not yet built | Don't use it; or restore snapshot |
| U-011 | 2026-09-17 | Price tools (change many / export)        | Done, not yet built | "Undo Last Change"; or restore snapshot |
| U-012 | 2026-09-17 | Trash (undo delete)                       | Done, not yet built | Restore snapshot (see U-012 note) |
| U-013 | 2026-09-17 | Better product list (price, sort, categories) | Code: not yet built · Categories data: **Live** | `assign_categories.py --undo`; or restore snapshot |
| —     | 2026-09-17 | Database schema v2 (for U-007–U-013)      | **Live** (applied with U-013 data) | See [Schema v2](#schema-v2-2026-09-17) |
| U-014 | 2026-09-17 | Two screens: Print Labels / Edit Products | Done, not yet built | `git revert` the UI commit, or restore snapshot |
| U-015 | 2026-09-17 | Bigger, resizing preview                  | Done, not yet built | (part of the UI commit) |
| U-016 | 2026-09-17 | Windows 11 look (sv-ttk theme)            | Done, not yet built | Uninstall `sv-ttk` and rebuild: the program falls back to the old theme |
| U-017 | 2026-09-17 | Keyboard printing flow                    | Done, not yet built | (part of the UI commit) |
| U-018 | 2026-09-17 | Git version control + GitHub sync         | **Live** — private repo github.com/Harjas2102/aaojee-label-maker | — |
| U-019 | 2026-09-17 | Automated tests on every change           | **Live** (hook on; GitHub runs tests + builds the .exe on every push) | `git config --unset core.hooksPath` turns the hook off |

"Not yet built" means the source is changed but `AaojeeLabels.exe` hasn't been rebuilt with it.
Update the status to **Live** once the new build is in use at the store.

---

## Before this tracker (history)

Changes made earlier, all on 2026-09-17, are described in detail in
`Aaojee_Label_Maker_Handoff.md` §17 "Maintenance log". In short:

1. **Bug-fix sweep (no visible changes):**
   - Font sizes 6–8 crashed label rendering.
   - Search wiped unsaved edits.
   - A bad price silently erased the stored price.
   - The importer missed the real `barcodeNo` column.
   - Backups could miss changes still in the SQLite `-wal` file.
   - Restore accepted any file.
   - Settings are now saved atomically.
   - Printing was optimized.
2. **Approved follow-ups:**
   - Print Date rolls over at midnight.
   - Printing refuses an invalid date or barcode.
   - The Bold checkbox works.
   - A missing Arial Narrow now falls back to Arial instead of a tiny default font.
   - `USER_GUIDE.txt` was rewritten.
   - Clutter files were removed.
3. **`build.bat` fixed:**
   - It had Mac (LF) line endings, so Windows misread it and the window just closed. It is now
     CRLF.
   - It calls `python -m PyInstaller` because `pyinstaller` wasn't on PATH.
   - It deletes the old exe before building so a failed build can't report "SUCCESS".
   - **`build.bat` must keep CRLF line endings.**

---

## Upgrade log

### U-001 — Scan a label to find a product

**What it does.** With the cursor in the Search box, scanning any printed label (or typing a
barcode and pressing Enter) opens that product. The search text stays selected so the next scan
replaces it. Enter also opens the only match of a typed name. Esc clears Search, and Ctrl+F jumps
to it. Typing digits also filters the list by barcode number.

**Why.** Reprinting from an existing label no longer means reading the name and searching for it.

**How it works.**
- Scanners can send a UPC-E label in several forms. `scanned_code_to_data6()` accepts all of them
  and verifies check digits, so a mis-scan never matches:
  - 6 digits: `310800`
  - 7 digits: `0310800` or `3108006`
  - 8 digits: `03108006`
  - 12-digit UPC-A: `031000000806`
  - 13-digit EAN: `0031000000806`
- If the scanned product is hidden by the "Show:" filter, the filter switches to All Items.
- An unknown barcode beeps and shows "No product has barcode …" in the item count line.

**Files changed.**
| File | Change |
|------|--------|
| `source/barcode_engine.py` | New `scanned_code_to_data6()`, `_upca_to_upce_data()` |
| `source/database.py` | `search_products(query, barcodes)` also matches barcode numbers, exact matches first; new `get_products_by_barcode()` |
| `source/app_window.py` | Search box binds Return/KP_Enter/Escape; new `_on_search_enter()`, `_focus_search()`, `_select_product_in_tree()`; Ctrl+F binding; `_refresh_product_list()` passes decoded codes |

**Tested.**
- All 1,000,000 possible 6-digit numbers resolve correctly from all six scanner formats.
- Wrong check digits are rejected.
- Name search still returns the same results ("channa" → 11 items, as in the screenshot).
- GUI tests: 8-digit and 12-digit scans open the right product, a scan through a filter works,
  an unknown code is reported, and Enter opens a single name match.

**Not tested / limits.**
- No physical scanner was available. Most USB scanners type like a keyboard and press Enter.
  If a scanner doesn't send Enter, the list still filters to the product but it won't open by
  itself; click it, or turn on the scanner's "Enter suffix" setting.
- Scanning only works while the cursor is in the Search box. A scan while typing in another field
  types into that field.

**Undo.** Restore the three files above from the snapshot (see [Rolling back](#rolling-back)).

---

### U-002 — Print queue (batch printing)

**What it does.**
- **"+ Add to Print Queue"** (right column) adds the open product with the current Quantity.
  - Products with ingredients default to "Barcode + Ingredients"; others to "Barcode".
  - Adding the same product and label choice again adds to its quantity.
- **"Print Queue (N)"** opens a window where you can:
  - change a row's quantity or label choice (Barcode / Ingredients / Barcode + Ingredients, plus
    Combined when the Combined button is enabled in Settings);
  - remove a row, or Clear All;
  - **Print All**, which shows a confirmation with the total label count, printer and print date.
- The queue is saved in `print_queue.json` and kept until Clear All, so a daily batch can be
  reused. A "Last printed" time is recorded per row.

**Why.** The morning batch was search, set quantity and print, once per dish.

**Behavior details.**
- **What it prints:** products as saved in the database, with the Print Date and Show / Hide
  checkboxes from the main window at the moment you click Print All.
- **Unsaved edits:** adding a product with unsaved edits asks to save first. A never-saved new
  product can't be queued.
- **Checks before printing:** the same checks as single prints. An invalid Print Date or an
  invalid stored barcode blocks the whole batch.
- **Skipped labels:**
  - The ingredient label is skipped, with a note in the confirmation, for products with no
    ingredients.
  - Deleted products are skipped and marked "(deleted product — will be skipped)".
- **Printer errors:** if the printer fails partway, printing stops and a message lists what was
  already sent.

**Files changed.**
| File | Change |
|------|--------|
| `source/print_queue.py` | **New.** `PrintQueue` (load/save JSON), `PrintQueueWindow`, `LABEL_CHOICES`, `default_choice()` |
| `source/app_window.py` | Queue buttons in `_build_print_actions()`; `_on_add_to_queue()`, `_open_print_queue()`, `on_print_queue_changed()`, `print_queue_items()`, `print_date_text()`; printing refactored into `_resolve_printer()` + `_print_product()` (shared by single, test and queue prints) |

**New data file.** `print_queue.json` in the program folder, next to `products.db`. It is safe
to delete, which just empties the queue. It is included in the "moving to a new PC" list in
`USER_GUIDE.txt`.

**Tested (GUI, fake printer).**
- Default label choices and merging repeated adds.
- The count on the main button.
- Persisting to disk, including edits made in the window.
- Cancel at the confirmation prints nothing.
- The confirmation shows the right totals (72 labels / 2 products) and the skipped ingredient
  note.
- Print All sends the right label types, sizes and copies.
- Invalid date blocks the batch.
- Mid-batch printer failure reports progress.
- Deleted product is skipped.
- Clear All.

**Not tested.** A real multi-product batch on the Zebra/TSC. Try a small batch first (2 products,
qty 1).

**Undo.** Just don't use it. Nothing changes unless someone clicks the queue buttons. To remove it
completely, restore the snapshot.

---

### U-003 — Manager PIN lock

**What it does.** Off until a manager sets a PIN (Settings → Set / Change Manager PIN…, at least
4 characters).
- **Once set, these ask for the PIN:**
  - Settings… and Font Settings…
  - Reset to Default Layout
  - Spacing and Side Margin (greyed out while locked, with an "Unlock…" / "Lock" button)
  - Delete
  - Restore from Backup and Import
  - Changing or removing the PIN
- **These stay open to everyone:** printing, the print queue, searching, and adding or editing
  products.
- **Unlock timing:** a correct PIN unlocks for 5 minutes, extended by each protected action.
  Settings → Lock Now locks immediately.

**Why.** Prevents accidental changes like the Font Settings mistake on 2026-09-17, when the name
font size was changed to 35 by accident.

**Storage.** `settings.json` → `"manager_pin_hash"`: a salted PBKDF2-SHA256 hash, never the PIN
itself. `""` means no PIN.

**Forgot the PIN.**
1. Close the program.
2. Open `settings.json` in Notepad.
3. Delete the `"manager_pin_hash": "…",` line, or set it to `""`.
4. Save and restart.

**Files changed.**
| File | Change |
|------|--------|
| `source/manager_lock.py` | **New.** `hash_pin()`, `verify_pin()`, `ManagerLock` (`require()`, `set_pin_interactive()`, `remove_pin_interactive()`, `lock()`), constants `UNLOCK_MINUTES = 5`, `MIN_PIN_LENGTH = 4` |
| `source/app_window.py` | `self.lock`; PIN checks in `_open_settings()`, `_open_font_settings()`, `_reset_fonts()`, `_on_delete()`, `_on_restore()`, `_on_import_mdb()`; Settings-menu items; `_refresh_lock_ui()`, `_schedule_lock_refresh()` (every 5 s), `_on_layout_lock_btn()` |
| `source/settings_manager.py` | Default `"manager_pin_hash": ""` |

**Tested (GUI).**
- A short PIN is rejected.
- The PIN is stored only as a hash.
- The lock button appears only when a PIN is set.
- Lock Now greys out Spacing and Side Margin.
- Cancel and a wrong PIN both block Settings; the right PIN opens it and stays unlocked for the
  next action.
- Delete, Restore, Import and Reset Layout all ask for the PIN.
- The unlock expires.
- The PIN can be removed.

**Undo.** Settings → Remove Manager PIN… Everything then behaves exactly as before.

---

### U-004 — Unsaved-changes warning

**What it does.** If the form has changes that weren't saved, the program asks
"Save them before …?" when you:
- open another product (click, arrow keys or scan);
- double-click to reload the same product;
- click + New;
- restore a backup;
- close the program (the X button or File → Exit).

The answers are **Yes** = save first, **No** = discard, **Cancel** = stay on the edited product
(the list highlight goes back to it). If Yes fails validation (e.g. a bad price), you stay on the
product with the red message.

**Why.** Edits used to disappear silently when a cashier clicked another product before saving.

**How it works.**
- `_take_clean_snapshot()` records the form fields when a product is loaded, saved, or cleared,
  and after + New fills in its barcode.
- `_is_dirty()` compares the form against that snapshot, field by field, as typed with spaces
  trimmed.
- `_on_save()` now returns True/False so callers know whether saving worked.

**Files changed.**
| File | Change |
|------|--------|
| `source/app_window.py` | `_form_snapshot()`, `_take_clean_snapshot()`, `_is_dirty()`, `_confirm_unsaved()`, `_on_close()` (also `WM_DELETE_WINDOW` and File → Exit); checks in `_on_tree_select()`, `_on_new()`, `_on_restore()`; `_on_save()` returns bool |

**Tested (GUI).**
- A freshly loaded product is not dirty; an edit makes it dirty.
- Cancel keeps both the edits and the product.
- No discards the edits (the database is unchanged) and opens the next product.
- Yes saves, then opens the next product and highlights it.
- Yes with an invalid price stays on the product.
- + New after discarding gives a clean form with a new barcode.
- Closing with an unsaved product, then Cancel, keeps the window open.
- Double-click reload, then No, reverts the edits.

**Undo.** Restore `app_window.py` from the snapshot. Note that this also removes U-001, U-002,
U-003 and U-005's app-side code.

---

### U-005 — Sharper barcodes (print at the printer's own resolution)

**What it does.** Printed labels are now rendered at the printer's native DPI, read from the
Windows driver: 203 DPI for the Zebra TLP 3844-Z and TSC TTP-244CE. They are sent as pure
black/white. Every barcode bar is a whole number of printer dots, at least 3 dots (0.0148")
wide at 203 DPI.

**Why.** Labels used to be rendered at 600 DPI and shrunk by Windows to 203 DPI. That made each
13-mil bar about 2.7 dots, so the driver rounded bars unevenly (some 2 dots, some 3). Uneven bars
are a common cause of slow or failed scans.

**Visible difference.**
- Layout, fonts and positions are unchanged.
- The barcode is about 10% wider (3-dot modules instead of about 2.7).
- Text is crisp black/white instead of driver-dithered.
- The on-screen preview is unchanged (still rendered at 150 DPI).

**Safety nets.**
- If the driver's DPI can't be read, the old 600-DPI path is used automatically. This covers
  unequal X/Y DPI and DPI outside 150–1200.
- Settings → "Print at the printer's own resolution (sharper barcodes)" can be unticked to force
  the old path. It is stored as `print_at_printer_dpi` in `settings.json`, default `true`.
- The DPI is read once per printer per session; saving Settings clears it.

**Files changed.**
| File | Change |
|------|--------|
| `source/printer_manager.py` | New `get_printer_dpi()`, `to_monochrome()`; removed unused `RENDER_DPI` |
| `source/label_renderer.py` | `render_label(..., min_module_in=None)`; layouts take `module_px` to enforce a minimum bar width (None = unchanged) |
| `source/app_window.py` | `LEGACY_PRINT_DPI = 600`, `NATIVE_MIN_MODULE_IN = 0.013`; `_print_dpi()`; `_print_product()` renders at native DPI + monochrome; Settings dialog checkbox |
| `source/settings_manager.py` | Default `"print_at_printer_dpi": True` |

**Tested.**
- Every product with a barcode was rendered as Barcode 2.25×1.25, Barcode 2.25×3.00 and
  Combined, at both 203 and 300 DPI (1,299 labels per DPI). Each was decoded back from the image
  by an independent UPC-E reader: **all decode to the correct number and check digit**.
- All bars are whole dots of at least the minimum width, each image is exactly the label size in
  printer dots, and the output is pure black/white.
- The preview and 600-DPI renders are pixel-identical to before (4,721 comparisons).
- GUI: Print Barcode, Test Print and the queue send 457×254-dot 1-bit images at a fake 203 DPI;
  with the setting off, or an unreadable DPI, they fall back to 1350×750 RGB.

**Not tested.** A real print on the store printers. **After rebuilding:**
1. Test Print a known product.
2. Scan it at the POS.
3. Compare its size and position on the label with an old one.

If anything is off, untick the setting (no rebuild needed) and note it here.

**Known limit (existing, not caused by this).** On the 2.25×1.25 barcode label, a long date line
("Best By : 12/28/2026") can come within the barcode's left quiet zone (the blank margin
scanners need). This happened before this change too. If a label scans poorly, this is a
candidate to fix.

---

### U-006 — Product data cleanup

**What it is.** A one-time correction of the product data in `products.db`. It was applied
2026-09-17 with the program closed. It changes data only, not code, so it is already live in the
current `.exe`.

**Where everything is.** `data_changes/2026-09-17_U-006_data_cleanup/`
| File | Purpose |
|------|---------|
| `cleanup.py` | The exact rules used. Run it with no arguments for a dry run, `--apply` to apply, `--undo` to reverse. |
| `changes.csv` | Every change: product id, name, field, **old value**, **new value**, reason. Opens in Excel. 183 rows. |
| `products_before_U-006.db` | A permanent full copy of the database from just before the cleanup. It is kept out of `backups/`, whose rotation would eventually delete it. |

**Result.** 433 → 439 products, with 177 field changes and 6 products added. All barcode numbers
and prices are unchanged, and the database integrity check is `ok`.

| # | Cleanup | What was done | Count |
|---|---------|---------------|-------|
| 1 | **Size spellings** | One format: number, space, unit, e.g. `2 LB`, `14 OZ (400 GM)`. Units are `LB` (from lb/Lb/LBS), `OZ`, `GM` (from G/GMS/GRAMS/gm), `ML`, `PCS` (from PIECES). Trailing zeros removed (`2.00 lb` → `2 LB`, `4.0LB` → `4 LB`). Typos fixed: `14 0Z` → `14 OZ`, `1IB.` → `1 LB`, `14 .1OZ` → `14.1 OZ`, `14 OZ.` → `14 OZ`. Anything not clearly a size was left alone. | 145 sizes; 95 spellings → 48 |
| 2 | **Stray spaces** | Double spaces removed from 7 names (e.g. `KAJU  PISTA BURFI`). Ingredient punctuation spacing fixed in 6 products: `Tomatoes,Cilantro` → `Tomatoes, Cilantro`; empty `Salt, , Oil` → `Salt, Oil`; `salt &oil` → `salt & oil`. `FD&C` was deliberately left as is. **Spelling in ingredients was not changed** (see follow-ups). | 13 |
| 3 | **Misspelled name** | `MANGO MOOSE` → `MANGO MOUSSE` (both rows, barcodes 313800 and 313900). | 2 |
| 4 | **Duplicates** | **Flagged, not deleted.** Only the POS knows which barcode of each pair is live, and deleting the wrong one would break reprints. Both rows in each pair got a Notes line starting `CHECK (data cleanup 2026-09-17)` naming the other barcode. After normalizing sizes, a 6th pair appeared: BASMATI RICE 4 LB. | 6 pairs |
| 5 | **Date modes** | MAKHANI SAUCE and POTATO POHA have ingredient labels but were set to Packed; changed to **Best By** (the handoff rule: ingredient label = cooked = Best By). GOBHI MUTTAR, SABUDANA KHICHDI and WASABI FRIED GREEN PEAS were **flagged** in Notes: they need ingredients typed in, and no source document exists (their `.docx` files are misfiled, empty, or just "29Month"). Ingredient text was not invented. | 2 changed, 3 flagged |
| 6 | **New products from unmatched `.docx`** | Added ALSI PINNI, ASSORTED NUTS (1.5 LB, Packed), LOBIA RASMISSA (BLACK EYE BEANS), MORIYO (SAMO), STRAWBERRY MOUSSE, URAD CHANA DAL (SPLIT MATPE BEANS & CHICKPEA LENTILS). Ingredients are copied from `import_source/ingredient_docs/` with spacing tidied and spelling kept as on the original labels. **Price and barcode left blank**: the POS barcode numbers aren't known, and a made-up barcode would print a label that doesn't scan. Each has a Notes line saying so. Cooked ones are Best By. | 6 |

**Needs a person to finish.** Find each product by typing its barcode in Search (U-001).
| Product | Barcode(s) | To do |
|---------|-----------|-------|
| BASMATI RICE 4 LB | 318900 / 502700 | Same price. Look both up in the POS; delete the one the POS doesn't use. |
| DEER BROWN MUSTARD- BIG 14 OZ | 562000 / 562100 | Same as above. |
| QUINOA SALAD | 607600 / 607700 | Same as above. |
| RASMALAI | 605100 / 605900 | Same as above. |
| MANGO CANDY | 565000 ($1.99) / 565500 ($2.99) | Different prices, probably different sizes. Add the size to both. |
| MANGO MOUSSE | 313800 ($4.99, has ingredients) / 313900 ($5.99, none) | Add sizes. The $5.99 one probably needs the same ingredients and Best By. |
| GOBHI MUTTAR, SABUDANA KHICHDI, WASABI FRIED GREEN PEAS | 314200, 560500, 558900 | Type in ingredients and subtitle. |
| ALSI PINNI, ASSORTED NUTS, LOBIA RASMISSA, MORIYO, STRAWBERRY MOUSSE, URAD CHANA DAL | none yet | Enter price, and the barcode number from the POS (or create one with Auto and add it to the POS). |

After fixing an item, delete its `CHECK …` / `Added from …` line from Notes.

**Spelling left for a person to decide** (it prints on labels, so it wasn't changed automatically):
- **Ingredients:**
  - BHINDI ALOO: `tumeric`, `spieces`
  - LOBIA RASMISSA: `spieces`, and `salt tomatoes` (missing comma)
  - ALSI PINNI: `Flex Seed` (probably Flax Seed)
  - ALOO MATTAR: `Cilantro Salt` (missing comma)
  - ALOO SABZI: `Chillis`
- **Product names:**
  - `DEER BLACK CARDIMOM`
  - `FLAT CINAMMON STICK`, `CINAMMON STICKS`
  - `STAR ANIES`
  - `ROASTED PISTACHO`
  - `URAD WHITE SPLIT PEALED`
  - `TAMRIND PASTE`
  - `FLEX SEEDS`

**Tested.**
- Applied to a copy first: 439 rows, integrity ok, barcodes and prices unchanged, 0 names with
  double spaces, 48 distinct sizes.
- Running `--apply` a second time is refused.
- `--undo` restored the copy exactly.
- Then applied to the live database. Every product (all 439) renders as Barcode, Ingredient and
  Combined, in both preview and 203-DPI print, with no errors (2,634 renders).

**Undo.**
1. Close the program.
2. Run `python data_changes/2026-09-17_U-006_data_cleanup/cleanup.py --undo`. It puts back every
   old value that hasn't been edited since, and removes the 6 added products if they haven't been
   edited. Hand edits made afterwards are kept and listed.
3. For a full reset instead, restore `products_before_U-006.db` with File → Restore from Backup.
   This loses any edits made after 2026-09-17.

---

### Schema v2 (2026-09-17)

U-007 to U-013 need new places to store data. `source/database.py` upgrades the database
automatically the first time a new build opens it, and saves
`backups/premigration_v2_<timestamp>.db` first. That name doesn't match the 30-backup rotation
pattern, so it is never deleted automatically.

- **New product columns:**
  - `allergens`, `net_weight`, `category` (text, default blank)
  - `deleted_at` (blank = not deleted)
- **New tables:**
  - `print_history` (U-009)
  - `price_history` (U-011)
- **Schema version:** `PRAGMA user_version = 2`.
- **Upgrade itself** changes no existing values. Tested on the real data: all 439 products
  identical before and after.

**Already applied to the live `products.db`** when the U-013 categories were assigned. The
backup is `backups/premigration_v2_20260917_020953.db`, from just before the upgrade.

**Compatibility with the current (older) `.exe`.** It keeps working on the upgraded database;
this was tested by saving and reading with the previous `database.py`. Two things to know:
- It ignores allergens, net weight and categories.
- **It shows products that are in the Trash as normal products.** Once the new build is in use,
  don't go back to the old `.exe` without emptying the Trash first.

**Undo.** Restore `backups/premigration_v2_20260917_020953.db` with File → Restore from Backup.
This loses changes made after 2026-09-17 02:09.

---

### U-007 — Allergens "Contains:" line

**What it does.** A new **Allergens** field on the product form, with a **Pick…** button that
ticks from the nine major US allergens (Milk, Eggs, Fish, Shellfish, Tree Nuts, Peanuts, Wheat,
Soybeans, Sesame). Anything else can be typed in, and typed extras are kept by the picker. When
filled in, ingredient and combined labels print a **bold** `Contains: Milk, Tree Nuts` line under
the ingredients. It also prints for a product with no ingredient list (e.g. ASSORTED NUTS →
size line + Contains line). The barcode label is not affected.

**Why.** Allergen declarations are a standard label requirement and a safety issue.

**Files.**
| File | Change |
|------|--------|
| `source/allergens.py` | **New.** `MAJOR_ALLERGENS`, `AllergenPicker` |
| `source/label_renderer.py` | New `info_lines()` / `_info_fonts()`; `_find_fitting_ingredients_size(..., extras)` and `_draw_ingredients_block(..., extras)` fit and draw the extra lines at the ingredients' size; layouts draw the block when there are ingredients **or** extra lines |
| `source/app_window.py` | Allergens row (form row 3), `_open_allergen_picker()`, load / clear / collect / unsaved-check include it |
| `source/database.py` | `allergens` column |

**Label fitting.** The Contains and Net Wt lines are fitted together with the ingredients, and
the text shrinks as needed.

On the combined label, the layout reserves a fixed height for price, barcode and date. At
Spacing 1.75 that reservation isn't quite enough once the extra lines make the block taller, so
the address could be pushed off the bottom. `render_label()` now measures that overflow and, only
for products with these lines, lays the label out again with less room for the ingredients.

Tested with all 134 products that have ingredients, with typical and worst-case allergen/net
weight text, at spacing 1.0 / 1.75 / 3.0 and 203 / 300 DPI:
- nothing runs off the label;
- no ingredient text is dropped;
- **all existing labels are still pixel-identical** (4,721 renders).

**Undo.** Clear the Allergens field on a product; its labels go back to exactly how they were.

---

### U-008 — Net weight line

**What it does.** A new **Net Wt** field (row 5, stored uppercase, e.g. `16 OZ`). When filled
in, ingredient and combined labels print `Net Wt: 16 OZ` under the Contains line. It is separate
from **Size**, so labels for products that already have a size (which prints only when there are
no ingredients) don't change.

**Files.** `label_renderer.py` (`info_lines()`, same fitting as U-007); `app_window.py` (Net Wt
field); `database.py` (`net_weight` column).

**Undo.** Clear the field.

---

### U-009 — Print history

**What it does.** Every **successful** print is recorded in the `print_history` table: Print
Barcode / Ingredients / Combined, Test Print, and each label type of each Print Queue row. Each
record has:
- date and time;
- product id, name, size, barcode and price at that moment;
- label type and size, and copies;
- the Print Date, and the exact date line printed ("Best By : 9/27/2026");
- the printer, and where it was printed from (Print / Test Print / Queue).

A failed print is not recorded. If recording ever fails, the print still counts as done and no
error is shown.

**File → Print History…** shows Today / Last 7 days / Last 30 days / All, with a search by name
or barcode and totals ("12 print jobs, 240 labels"). **Save as Spreadsheet…** writes a CSV.

**Why.** Traceability: which batch and date a label came from, if there is ever a problem with a
product.

**Files.** `source/print_history.py` (**new**, `PrintHistoryWindow`, `range_start()`,
`export_history()`); `database.py` (`print_history` table, `log_print()`,
`get_print_history()`); `app_window.py` (`_print_product(..., source)` → `_log_print()`, File
menu).

---

### U-010 — Duplicate as new size

**What it does.** A **⧉ Duplicate** button in the form header (also File → Duplicate as New Size)
opens a new, unsaved product copied from the open one: same name, subtitle, ingredients,
allergens, category, price and date mode, with **blank Size**, **a new auto barcode**, and blank
Net Wt and Notes. The cursor goes to Size and a message explains what to do. Leaving without
saving triggers the unsaved-changes question (U-004). If the open product has unsaved edits, it
asks first and copies the saved version.

**Files.** `app_window.py` (`_on_duplicate()`, button style `duplicate`, `_size_entry`).

---

### U-011 — Price tools

**What it does.**
- **Tools → Change Prices…** (needs the manager PIN if set):
  - Pick products: the list as currently searched/filtered, a category, or all.
  - Change by percent or dollars (negative lowers).
  - Rounding: nearest cent, up to .49/.99, or up to .99.
  - The preview shows old → new prices; double-click a row to leave it out.
  - **Apply** backs up the database, changes the prices, records every change in the
    `price_history` table, and offers a CSV of the changes to type into the POS.
  - **Undo Last Change** puts old prices back, except any price edited by hand since, which is
    listed and left alone.
- **Tools → Export Price List…** saves every product's barcode, name, size, price and category
  as CSV.

**Why.** Prices usually go up across many products at once. The POS still has to be updated
separately (this program can't reach it), and the CSV makes that easier.

**Files.** `source/price_tools.py` (**new**: `round_price()`, `new_price()`,
`PriceChangeDialog`, CSV exports); `database.py` (`price_history` table,
`apply_price_batch()`, `get_last_price_batch()`, `undo_price_batch()`); `app_window.py` (Tools
menu, `visible_products()`, `category_names()`, `category_predicate()`, `backup_now()`,
`refresh_products()`, which reloads the open product so a stale price in the form can't be saved
back over a new one).

**Tested.**
- Rounding cases, including negative amounts and the $0.01 floor.
- Percent, dollar and decrease changes.
- Apply 10% to 32 products with one row excluded: the excluded product is untouched.
- The backup is made, and the POS CSV is written.
- Undo restores every price, and keeps a price that was hand-edited since.
- An invalid amount changes nothing.
- The PIN is required.

---

### U-012 — Trash (undo delete)

**What it does.** **Delete** now moves a product to the Trash; the confirmation says so, and
the PIN is still required. **File → Trash…** has:
- **Restore** (warns if an active product now uses the same barcode);
- **Delete Forever…** and **Empty Trash…** (both need the PIN and confirm).

Products in the Trash are hidden from the list, search, scans and the print queue. Their barcode
numbers stay reserved: Auto skips them, and the duplicate-barcode warning on Save says
"(in the Trash)".

**Files.** `source/trash_window.py` (**new**); `database.py` (`deleted_at` column; every
product query filters `deleted_at IS NULL`; `delete_product()` is now soft; `get_trash()`,
`restore_product()`, `purge_product()`, `empty_trash()`; `get_product(..., include_deleted)`;
`get_barcode_conflict()` prefers active products); `app_window.py` (delete message, File menu).

**Note.** The U-006 cleanup script's `--undo` still hard-deletes the products it added, which is
intended.

---

### U-013 — Better product list

**What it does.**
- **Price column** in the list. The list panel is 40 px wider (340 px) and can still be
  resized by dragging.
- **Click any heading to sort** by Name, Barcode #, Size or Price; click again to reverse. A
  ▲/▼ arrow shows the sort. Size sorts by real weight (200 GM < 14 OZ < 1 LB). A scanned barcode
  match always stays at the top.
- **Categories:**
  - A **Category** dropdown on the form (Sweets / Spices / Dry Goods / (none)); never printed.
  - "Show:" gains **Sweets**, **Spices**, **Dry Goods** and **No category**.
  - A new product saved with (none) gets a best guess, and the status line says so.

**Starting categories for existing products** were assigned on 2026-09-17 by a guess from the
name, size and date mode (`source/categories.py`, `suggest_category()`):
- 310 products got a category: 180 Dry Goods, 66 Spices, 64 Sweets.
- 129 were left without one, mostly cooked dishes, which the "Cooked Food" filter covers.

Records are in `data_changes/2026-09-17_U-013_categories/`:
- `assign_categories.py`: dry run, `--apply`, `--undo`;
- `changes.csv`: every assignment;
- `products_before_U-013.db`: a copy from just before.

Wrong guesses are harmless (filtering only); fix them on the product form.

**Files.** `source/categories.py` (**new**); `app_window.py` (`PRODUCT_CATEGORIES`,
`LIST_COLUMNS`, `_size_sort_key()`, `_sorted_products()`, `_on_sort_column()`,
`_update_sort_headings()`, Category field, suggestion in `_on_save()`); `database.py`
(`category` column).

**Tested (GUI).** Price column shown; sort by price in both directions; size order for
CUMIN SEEDS (200 GM → 14 OZ → 28 OZ → 3 LB); new filters listed; category saved and cleared; new
product gets "Sweets" suggested.

---

### Tests for U-007 – U-013

- **Engine (40 checks):**
  - Migration on the real data: backup made once, no values changed, the old code still works.
  - Partial updates don't blank the new fields.
  - Trash: hide, restore, delete forever, empty, barcode reservation.
  - Print history: logging, search, date ranges, CSV.
  - Price tools: rounding, batch, undo with a hand-edited price, CSVs.
  - Category guesses.
  - Label lines appear only on ingredient and combined labels, and the worst case fits.
- **GUI (49 checks)** on a copy of the real data:
  - All of the above through the real window.
  - A failed print is not logged.
  - The PIN guards Change Prices and Delete Forever.
- **All earlier suites still pass:** bug-fix sweep, U-001 – U-005, backend.
- **Build:** a test build bundles every new module and launches on the upgraded database.
- **Not tested:** real printers and a real scanner.

---

### U-014 — Two screens: Print Labels and Edit Products

**What it does.** A dark bar at the top has two tabs:
- **🖨 Print Labels** opens first. It has:
  - a large **product card**: name, subtitle, size · price · barcode, the date line that will
    print, and the Contains line;
  - a big **Quantity** stepper and Print Date;
  - "Show on label" checkboxes;
  - the big print buttons (with their keyboard keys), print queue buttons and Test Print.
- **✏ Edit Products** has the product form, with Save / Delete / Duplicate / New.
  - **When a manager PIN is set, opening it needs the PIN.** This is a change from U-003, where
    editing products was open to everyone.
  - The PIN session is kept alive while typing on this screen. After 5 idle minutes the screen
    returns to Print Labels on its own, unless there are unsaved changes.
  - Leaving it with unsaved changes asks Save / Discard / Cancel, and Discard puts the saved
    values back.
- The **product list** (left) and **preview** (right) are shared by both screens.
- **Spacing and Side Margin moved to Settings → Settings…**, which already needs the PIN. The
  U-003 "Unlock… / Lock" button next to Spacing is gone. The PIN state now shows in the top
  bar: 🔒 Locked, or 🔓 Manager unlocked with a Lock button.
- File → **New Product** / Ctrl+N and **Duplicate** switch to Edit Products first.
- **Keys:** Ctrl+E opens Edit Products, Ctrl+P returns to Print Labels, Ctrl+S saves (Edit screen
  only).
- **Window:** the program opens maximised.

**Why.** Cashiers mostly print. Separating printing from editing makes the everyday screen
simpler and harder to change by accident.

**Files.** `source/app_window.py`:
- new `_build_mode_bar()`, `_update_mode_bar()`, `_set_mode()`, `_revert_form()`,
  `_build_print_page()`, `_update_card()`;
- `_build_ui()` rebuilt: shared list + centre page + preview;
- `_refresh_lock_ui()` now drives the top bar and the auto-return;
- `_get_spacing()` / `_get_margin()` read from settings;
- SettingsDialog gains Label spacing / Side margin;
- removed `_build_right_panel()`, `_build_print_controls()`, `_build_print_actions()`,
  `_on_spacing_change()`, `_on_margin_change()`, `_on_layout_lock_btn()`.

`source/manager_lock.py`: new `touch()`.

**Snapshot before U-014 – U-017:** `upgrade_snapshots/2026-09-17_before-ui-overhaul/`. **Git:** commit
`3d63432`.

---

### U-015 — Bigger preview

**What it does.** The preview column now takes all the width left after the list (340 px) and
the centre column (540 px). A single label is drawn as large as the column and window height
allow, up to 760 px wide, and redraws when the window is resized. "All three" shows the tiles
at 70% of that width and can be scrolled with the mouse wheel. The preview choices are in a 2×2
grid, so none are cut off at 1280 px. On screens at least 1600 px wide, the list widens to
450 px so long names and sizes fit.

**Files.** `app_window.py`: `_build_preview_column()`, `_on_preview_resize()`,
`_preview_limits()`, `_on_body_resize()`, `_render_into_tile(..., max_h)`, `_update_preview()`;
constants `PREVIEW_MIN_W`, `PREVIEW_LIMIT_W`, `PREVIEW_STACKED_RATIO`, `LIST_PANEL_W`,
`LIST_PANEL_WIDE_W`, `CENTER_W`.

---

### U-016 — Windows 11 look

**What it does.** Uses the **sv-ttk** "Sun Valley" light theme (Windows 11 style) for all
standard controls, with Segoe UI fonts, flat coloured buttons, a 15 pt search box and 30 px list
rows. If `sv_ttk` isn't installed, the program falls back to the previous Windows theme and still
works.

**New dependency:** `sv-ttk`, a small pure-Python package with theme image files. It passed the
handoff's packaging-risk bar:
- `build.bat` installs it and bundles its files with `--collect-data sv_ttk` (verified: the
  test build includes the theme files and launches themed);
- it is added to `requirements.txt`.

**Files.** `app_window.py` (`_setup_window()`, optional `import sv_ttk`), `build.bat`,
`requirements.txt`, `.github/workflows/tests.yml`.

**Turn off.** Remove `sv-ttk` (`python -m pip uninstall sv-ttk`) and rebuild.

---

### U-017 — Keyboard printing flow

**What it does.** On the Print Labels screen:
- The cursor starts in the search box.
- Type a name, then **Enter**: the first match (or the one chosen with **↑ / ↓**) opens and the
  cursor jumps to **Quantity**.
- Type a number, then **Enter** prints barcode labels; **Shift+Enter** prints ingredient labels.
- The cursor then returns to Search, ready for the next product.
- **F5 / F6 / F7** print barcode / ingredients / combined; **F8** adds to the print queue;
  **Esc** returns to Search.
- A **scanned** barcode still opens the product and keeps the cursor in Search for the next scan
  (U-001).
- Print keys do nothing on the Edit screen.
- Help → **Keyboard Shortcuts** lists everything.

**Change from U-001.** Enter on typed text used to open a product only if it was the single
match. It now opens the first match.

**Files.** `app_window.py`: `_on_search_enter()`, `_move_selection()`, `_focus_quantity()`,
`_print_key()`, `_show_shortcuts()`, key bindings in `_build_menu()`, `_build_left_panel()`,
`_build_print_page()`.

---

### U-018 — Git version control and GitHub

**What it does.**
- The project folder is a Git repository (branch `main`).
- `.gitignore` keeps live store data, build output, old-system originals, pre-Git snapshots and
  database copies out of Git.
- `.gitattributes` forces CRLF for `.bat` files (the `build.bat` failure earlier today) and LF
  for everything else, and stores the `changes.csv` logs byte-for-byte.
- Commits so far:
  1. `1da9dab` Baseline: the state after U-001 – U-013.
  2. `08d2918` Automated tests (U-019).
  3. `3d63432` UI overhaul (U-014 – U-017).
  4. Docs and tooling (this entry).
- **`update_and_build.bat`** (store PC) runs `git pull --ff-only`, then `build.bat`.
- **`DEVELOPING.md`** explains the workflow: Mac or PC → commit → push → store PC update.

**GitHub.** The workflow file is ready, but the private repository isn't created yet. This PC
has no GitHub login, so that step needs the owner (see the chat instructions). After the first
push, every push runs the tests and builds the `.exe` on GitHub. **Not yet verified on GitHub.**

**Why.** It replaces the zip → flash drive → unzip loop, and gives an exact history of every
change and a safe undo (`git revert`).

---

### U-019 — Tests that run on every change

**What it does.** 69 automated tests plus a pixel-level "labels unchanged" check, run automatically
in two places:
- **before every commit** that touches code (`.githooks/pre-commit`: quick tests + label check;
  the commit is stopped on failure);
- **on GitHub for every push** (all tests + label check against the previous commit, then an
  `.exe` build).

Also runnable by hand: `run_tests.bat`, `python tools/run_tests.py [--quick]`,
`python tools/compare_labels.py`. The earlier ad-hoc test scripts from U-001 – U-013 were rewritten
into this suite. See `DEVELOPING.md` §2 for the full list.

**Proven to work.**
- The label check caught a deliberate one-pixel layout change in 945 of 4,457 renders and saved
  before/after pictures, then passed again after it was reverted.
- The hook ran and passed on the test commit and the UI overhaul commit.

**Files.** `tests/` (`helpers.py`, `test_barcode.py`, `test_labels.py`, `test_database.py`,
`test_modules.py`, `test_gui.py`, `fixtures/products.json`, `fixtures/settings.json`),
`tools/run_tests.py`, `tools/compare_labels.py`, `.githooks/pre-commit`,
`.github/workflows/tests.yml`, `run_tests.bat`.

**Turn off the hook.** `git config --unset core.hooksPath`. For a one-off intended label change:
`ALLOW_LABEL_CHANGES=1 git commit ...`.

---

### Tests for U-014 – U-019

- **Full suite:** 69 tests, all passing (39 non-window + 30 window tests).
- **Label check:** all 4,457 label renders identical to the baseline commit, so the UI overhaul
  didn't change a single printed pixel.
- **Window tests for the new screens:**
  - starts on Print Labels with Search focused;
  - theme loads;
  - the Edit screen needs the PIN, times out back to Print, but not with unsaved edits;
  - leaving with unsaved edits: Cancel stays, Discard reverts;
  - New opens the Edit screen; Ctrl+S is ignored on the Print screen;
  - spacing and margin are saved from Settings;
  - type → Enter → quantity → Enter prints and returns to Search;
  - Shift+Enter, F5 and F8 work; print keys are ignored on the Edit screen;
  - ↑ / ↓ move through the list;
  - scans keep focus in Search;
  - the preview grows with the window.
- **Real build:** built with `build.bat` into a scratch folder; theme files bundled; launched
  maximised on the real data with the new theme.
- **Screenshots checked:** 1920×989 and 1280×720; both screens fit at 1280×720.
- **Not tested:** real printers, a real scanner, GitHub Actions.

---

## Rolling back

**Undo the UI overhaul (U-014 – U-017), keeping everything else:** find the commit with
`git log --oneline` and run `git revert <commit id>`, then rebuild. Without Git: copy
`upgrade_snapshots/2026-09-17_before-ui-overhaul/source/*.py` over `source/` and rebuild. The
database is unaffected.

**Undo only U-007 – U-013 (keep U-001 – U-005):**
1. Close the program.
2. Copy the `.py` files from `upgrade_snapshots/2026-09-17_before-features-7-13/source/` over
   `source/`.
3. Delete these new files from `source/`: `allergens.py`, `categories.py`, `print_history.py`,
   `trash_window.py`, `price_tools.py`.
4. Run `build.bat`.

The database can stay as it is: the older code works with schema v2. Before going back, **empty
the Trash**, because the older code shows trashed products as normal ones. To also put the data
back exactly as it was, restore `upgrade_snapshots/2026-09-17_before-features-7-13/products.db`
with File → Restore from Backup. That copy is from just before these features; later edits are
lost.

**Undo everything back to before U-001:**

The source as it was before U-001–U-005 is saved in:

```
upgrade_snapshots/2026-09-17_before-upgrades-1-5/
    source/   (all .py files + AaojeeLabels.spec)
    build.bat
    USER_GUIDE.txt
```

To undo all five:
1. Close the program.
2. Copy the `.py` files from the snapshot's `source/` over `source/`.
3. Delete `source/manager_lock.py` and `source/print_queue.py`.
4. Run `build.bat`.

`products.db` is not changed by U-001–U-005 (no schema change). U-006 changed product data only — undo it separately (see U-006). You can leave
`print_queue.json`, `manager_pin_hash` and `print_at_printer_dpi` in `settings.json`; the old
version ignores them.

## After rebuilding — first-day checklist

- [ ] Test Print → scan at POS → correct item (U-005).
- [ ] Printed barcode label matches an old one in position and size (U-005).
- [ ] Scan an existing label into the Search box → product opens (U-001).
- [ ] Queue 2 products at qty 1 → Print All → both print (U-002).
- [ ] Edit a price, click another product → the warning appears (U-004).
- [ ] If using a PIN: set it, write it down somewhere safe, confirm Settings asks for it (U-003).
- [ ] Open a cooked product, add Allergens + Net Wt, check the Ingredients and Combined previews,
      print one ingredient label (U-007 / U-008).
- [ ] Print something, then File → Print History… shows it (U-009).
- [ ] Duplicate a product, give it a size, Save; add its new barcode to the POS (U-010).
- [ ] Tools → Change Prices…: preview only, then Close without applying (U-011).
- [ ] Delete a test product, restore it from File → Trash… (U-012).
- [ ] Click the Price heading to sort; try Show: Sweets / Spices / Dry Goods (U-013).
- [ ] Program opens full screen on **Print Labels**. Type a name → Enter → type 1 → Enter prints
      one barcode label (U-014 / U-017).
- [ ] Scan a label: the product opens and the cursor stays in Search (U-001 / U-017).
- [ ] If a PIN is set: the Edit Products tab asks for it; Spacing / Side Margin are in Settings (U-014).
- [ ] The window looks like Windows 11 (rounded, light controls). If it looks like the old grey
      theme, `sv-ttk` didn't install; re-run `build.bat` with internet (U-016).
- [ ] Double-click `run_tests.bat` once on the store PC: all tests pass (U-019).
- [ ] Update the Index statuses above to **Live**.
