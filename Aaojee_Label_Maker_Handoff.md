# Aaojee Label Maker — Complete Handoff Document

> **Purpose of this document.** This is a complete knowledge dump for the next agent
> continuing work on the Aaojee Label Maker program. It captures the business context, the
> program's history, the data model, the exact barcode encoding rules, every implemented
> UI/behavior decision to date, all quirks and gotchas discovered during development, and
> the open items. Read this fully before making changes. Nothing here is speculative — it
> is the settled state of the project.

---

## 1. Business context

**Aaojee** is a family-run Indian grocery and prepared-food business in **Middletown, NY**
(Hudson Valley, Orange County). The business sells:

- **Cooked ready-to-go containers of Indian food** (roughly 75 recurring dishes) — dals,
  curries, rice preparations, sweets, snacks, etc.
- **Packaged dry goods** — nuts, seeds, spices, lentils, teas, rice, ghee, and similar
  items, sold in specific package sizes.

**Business address line used on labels:** `Aaojee, Middletown, NY 845-342-0040`
(Format may vary slightly — the existing label preview shows
"Aaojee, Middletown, NY 845-342-0040". This is a single settable field in the program's
Settings, so it can be edited.)

**Business owner is Harjas's father** ("dad") — the primary cook. Harjas is building this
tool for the family business. Staff use it daily.

---

## 2. What this program replaces and why

### The old setup (still in use at the store until this replaces it)

- Ran on an aging **Windows XP / Vista Dell** PC.
- **Ingredient labels** were stored one-per-file as **`.docx` Word documents**. Staff
  opened the doc, File → Print, chose the Zebra printer. That was it.
- **Barcode labels** were printed from a **proprietary program** (`lablesnet.exe`) built by
  an Indian tech vendor who also sold the store its POS system. Installed at
  `C:\LABELNWET`. Backed by a **Microsoft Access `.mdb` database** (`labeldata.mdb`) plus
  an XML settings file (`labelsetup`). The program was a Windows Forms .NET app; the
  vendor kept charging thousands for "new PCs" and "new license keys" every few years.

### Why replace it

- **Vendor lock-in** — every hardware refresh required paying the vendor again.
- The old PC is dying and cannot run modern software.
- The two-label workflow (ingredients in Word, barcodes in the vendor tool) meant the same
  dish was typed into two systems, producing constant name-inconsistency bugs
  (`MANGO MOOSE` vs `MANGO MOUSSE`; `Aloo Muttar` vs `Aloo Mattar`).
- Owning the source code and the data file means **any future developer, on any Windows
  PC, can rebuild the program for free forever**. That is the whole point.

### The old barcode program's UI (for reference — its shape informed ours)

- Title: "Barcode Labels". Blue instruction bar: *"Name, Size, UPC and Price Can be Moved
  by mouse hold button"* (elements were drag-positionable).
- Left: three-column list (UPC / Item Name / Size) with a Search Name box, alphabetically
  sorted.
- Right: label preview at top, then Printer dropdown (TSC TTP-244CE / Zebra), Print Label
  quantity, Label Size (2.25 × 1.25), UPC No. field with "Hide" checkbox and a
  "4 - UPC-E" format dropdown, Name/Weight/Price fields each with font family (Arial
  Narrow) + size + Bold, "$" Sign / +Tax toggles, Packing date + Per Lb + Address rows
  each with a "Print" checkbox, and buttons: New / Save / Close / Delete / "Saves setting
  as my Default Setting".

---

## 3. Program identity and top-level facts

- **Program name:** Aaojee Label Maker
- **Language:** Python
- **UI toolkit:** `tkinter` (Python's built-in — chosen so `.exe` bundling stays lean and
  dependency-free)
- **Database:** SQLite (single file, no server, portable)
- **Packaging:** PyInstaller → single Windows `.exe`
- **Runs on:** Windows 11 (target machine)
- **Portability model:** everything (executable, database, backups) in **one
  self-contained folder** — copy the folder = move the program

### Development / build workflow (Harjas's current loop)

1. Development happens on **Mac**, using **Claude Cowork** pointed at the project folder.
2. Cowork edits the source files directly on the Mac.
3. To produce a new `.exe`, Harjas **zips the project folder**, transfers it via
   **flashdrive** to the Windows 11 **build PC**, unzips, and rebuilds with PyInstaller.
4. The `.exe` runs on the build PC in the store.

> **Suggested improvement** for future work: Harjas could either work directly on the
> build PC (Cowork installed there) *or* use a cloud-sync folder (iCloud/Dropbox/GDrive)
> so Mac edits appear on the PC automatically. Both eliminate the flashdrive step. This
> is his call — the current flow works, it's just tedious.

### Where things live

- **Project folder** — typically named `AaojeeLabels/` (self-contained).
- **`products.db`** — the SQLite database at the project root.
- **`backups/`** — timestamped `.db` copies made automatically before major operations.
- **`import_source/`** — where the original `.mdb` and `.docx` folder were placed for
  one-time import (not required at runtime; keep the flashdrive as backup).
- **`source/products.db`** — a mirror copy created during the last rebuild (present, not
  authoritative; the root `products.db` is the live one).

### Printers

- **Primary:** **Zebra TLP 3844-Z** (USB, shows as normal Windows printer)
- **Backup:** **TSC TTP-244CE** (USB, shows as normal Windows printer)
- Printing goes through the standard Windows print path (not raw ZPL) so any installed
  printer works.
- The store currently uses one printer / one label size day-to-day; the alternates exist
  only for backup or emergency stock use.

### Label stock

- **Old size (still in stock, being used up):** **2.25" × 1.25"**
- **New size (long-term primary):** **2.25" × 3.00"** — for the combined label design.
  Confirmed available from their supplier.

---

## 4. Product data model

The SQLite `products` table holds one row per product. **All products — cooked food and
packaged goods alike — share the same schema.** A product just fills in what applies to it.

| Field              | Type           | Notes |
|--------------------|----------------|-------|
| `name`             | text, required | Product name in caps, e.g. `ALOO MATTAR`. Single source of truth used by every label type. Historically had spelling drift across old systems — now unified. |
| `subtitle`         | text           | Parenthetical plain-English description, e.g. `PIGEON PEAS LENTILS`. **Stored without parentheses**; the label adds them. Blank for most packaged goods. |
| `ingredients`      | long text      | Comma-separated ingredient list as plain text. Blank for items with no ingredient list (dry goods). |
| `size`             | text           | Size/weight descriptor, e.g. `2 LB`, `8 OZ`, `6 PCS`, `14 OZ (400 GM)`. Optional. |
| `price`            | decimal        | Clean decimal number, e.g. `4.99`. **No `$` sign stored** — the program adds it at print time per the `$ Sign` toggle. |
| `barcode_number`   | text (6 digits)| Zero-padded 6-digit string. See Section 5 for the full encoding rules — this is the most important area. |
| `date_mode`        | choice         | One of `Best By`, `Packed`, or `None`. See Section 6. |
| `notes`            | text           | Free-text internal notes, not printed. Optional. |

### Rules

- `name` is required to save. Everything else may be blank.
- `barcode_number` should be treated as **permanent once assigned** — reprints must be
  byte-for-byte identical, and the store's POS is keyed to these numbers.
- Duplicate barcode numbers must be prevented (with a warning if the user tries to save
  one that already exists).

### Design capacity

Comfortably handle **1,000+ products**. Current DB has **432**. The old vendor tool ran on
UPC numbers stretching into the 6000s.

---

## 5. Barcodes — the most important section

Get this exactly right or the POS will not scan the labels.

### 5.1 The format is UPC-E

**UPC-E** is the compressed 8-digit variant of UPC (specifically designed for small
labels — which is exactly why the store uses it). Every printed barcode has this shape:

```
0  XXXXXX  C
│   │      │
│   │      └── check digit (calculated, structural)
│   └───────── 6 data digits (the meaningful ID)
└───────────── number system digit — always 0 for the store's use
```

Only the **6 data digits in the middle** carry meaning. The leading `0` and the trailing
check digit are structural — required for the barcode to be valid and scannable, but not
part of the identity of the product.

### 5.2 What the POS actually stores

**The store's POS keys off the 6 data digits only.** Evidence from live POS screenshots:
the POS "Add/Edit Products" screen shows the barcode field as a plain 6-digit number (e.g.
`312200`, `313700`, `311400`) — not the 8-digit form. When a barcode is scanned at
checkout, the scanner reads all 8 digits but the POS extracts the middle 6 to do its
lookup.

This means the program's job is:

1. Accept 6 data digits from the user (or generate them).
2. Compute the correct UPC-E check digit for those 6 digits.
3. Render a scannable UPC-E barcode graphic that encodes: number system `0`, the 6 data
   digits, check digit — with the standard human-readable digits displayed beneath it in
   the familiar layout (`0` to the left of the bars, six digits under the bars, check
   digit to the right).

### 5.3 The right-pad rule (critical historical detail)

The old vendor program allowed users to enter **fewer than 6 digits**. When it did, it
**right-padded with zeros to 6**.

Examples (verified against real labels):
- Old DB stored Aloo Mattar as `3143` → printed barcode `0 314300 9` → POS reads
  `314300`.
- Dahi Vada `4054` → `405400`.
- The old MDB import contained one product with `barcodeNo = 12` → padded to `120000`.
- Another with `barcodeNo = 200` → padded to `200000`.

The program **must preserve this padding behavior** because the store's POS is already
programmed with the padded 6-digit values. If a new label encoded `3143` differently, the
POS wouldn't recognize it.

**Rule as implemented:** if the user enters fewer than 6 digits, right-pad with zeros to
exactly 6. Reject inputs longer than 6 digits or containing non-digits. Store the
6-digit padded form.

**Going forward** all new numbers are auto-generated as full 6 digits (see Section 5.5),
so this rule now mostly serves manual edits and import compatibility.

### 5.4 UPC-E check digit computation

The UPC-E check digit is **not computed directly from the 6 UPC-E digits.** It's computed
from the equivalent expanded **UPC-A** (12-digit) form. Any implementation must:

1. Expand the 8-digit UPC-E (`0` + 6 data + check) to its 12-digit UPC-A equivalent using
   the standard UPC-E → UPC-A expansion rules (which depend on the last digit of the 6
   data digits).
2. Compute the UPC-A check digit using the standard weighted-sum algorithm (odd positions
   × 3, sum, mod 10, subtract from 10).
3. That value is the UPC-E check digit.

Do **not** approximate this. Use a tested implementation. The build has verified the
encoder against every real barcode in the reference set (see 5.6) — any change to the
encoder must be re-verified against those.

### 5.5 Auto-generation of new barcode numbers

- On **`+ New`**, the program **automatically generates** a fresh barcode number and
  fills the Barcode # field. Staff do not need to click the `Auto` button (they routinely
  forgot). The `Auto` button still exists for regeneration on demand.
- The generator must **check the existing database** and retry silently on collision —
  no popup, no user-facing indication of the collision. This is internal.
- The user can still manually edit the Barcode # field after creation if a specific
  number is wanted.
- On save, a duplicate check runs anyway: if the user has manually entered a number that
  matches another product, warn them (showing which product uses it) and ask for
  confirmation before saving.

### 5.6 Reference values for encoder verification

These are real products with confirmed working barcodes at the store's POS. Any encoder
change must reproduce these exactly:

| Product        | 6 data digits | Full printed UPC-E |
|----------------|---------------|--------------------|
| Aloo Mattar    | `314300`      | `0 314300 9`       |
| Chana Masala   | `610400`      | `0 610400 7`       |
| Hakka Noodles  | `312200`      | `0 312200 6`       |
| Karela Aloo    | `311400`      | `0 311400 7`       |
| Mango Mousse   | `313900`      | `0 313900 6`       |
| Rice Pilaf     | `313700`      | `0 313700 8`       |

### 5.7 POS compatibility test path

There's a **Test Print** button on the main window that prints a single barcode label for
the currently selected product. This exists specifically so a new label can be printed and
scanned at the POS to verify it decodes identically to the old labels before relying on it
in production. Use this before rolling out any encoder change.

### 5.8 One thing the program does NOT do

The store's POS is a **closed, proprietary system**. This program does **not** sync with
it, cannot read from it, cannot write to it. The barcode number is the sole link between
the two systems — the same 6 digits are typed into both. This is a deliberate,
acceptable tradeoff. Consequence: price changes must be entered in two places (POS +
this program). With ~75 dishes and infrequent price changes this is acceptable and worth
the cost of owning the data.

---

## 6. Date modes

Each product has a `date_mode` controlling the date line on labels that show one (barcode
label and combined label). The ingredient-only label has no date.

- **`Best By`** — prints `Best By : M/D/YYYY`, calculated as **print date + N days**
  (default N = 10, configurable in Settings; see 8.2).
- **`Packed`** — prints `Packed : M/D/YYYY` using the print date.
- **`None`** — no date line prints. Used for bulk dry goods (e.g. nuts) that don't need a
  date.

### Defaults

- **New products default to `Best By`** — this is the primary use case at the store.
- The Best-By offset is a **visible, editable field in Settings** with typing + / − arrow
  buttons. Default value **10**.

### Print-date field on the main window

- Defaults to **today's date** at program launch.
- Editable — for labeling batches cooked on a previous day.
- Includes a **custom mini calendar picker** (day grid with prev/next month arrows,
  built without adding a `tkcalendar` dependency — chosen to keep PyInstaller bundling
  simple). Direct typing of the date also still works.
- When the print date is changed, any `Best By` date on the preview recalculates as
  (print date + offset).

---

## 7. Label designs

Three label types, on two possible stock sizes.

| Label type       | Primary size    | Also available on |
|------------------|-----------------|-------------------|
| Barcode-only     | 2.25" × 1.25"   | 2.25" × 3.00"     |
| Ingredient-only  | 2.25" × 1.25"   | 2.25" × 3.00"     |
| Combined         | 2.25" × 3.00"   | —                 |

### 7.1 Style (matches the existing physical labels)

- **Centered** layout.
- Product **name** is the largest text, bold, at the top.
- **Subtitle** (in parentheses) prints beneath the name, smaller, bold/italic/underlined,
  matching the historical style.
- Ingredients block is introduced by **`Ingredients :`** (the word "Ingredients"
  underlined), followed by the comma-separated list, wrapping across lines.
- Text **auto-shrinks to fit** the label. The design worst-case is a long ingredient list
  on the small 2.25" × 1.25" stock — e.g. Gujrati Dal's twelve-item list must remain
  legible.

### 7.2 Barcode-only label contents

Name, price (large), UPC-E barcode with human-readable digits, date line (if not None),
address line.

### 7.3 Ingredient-only label contents

Name, subtitle (if present), `Ingredients :` block. No barcode, no price, no date.

### 7.4 Combined label contents (2.25" × 3.00")

Top to bottom (typical arrangement — refine visually):
Name → Subtitle (if present) → Ingredients block (if present) → Price → UPC-E barcode →
Date line (if not None) → Address line.

### 7.5 Per-element show/hide toggles (on the main window)

A "Show / Hide on label" row with checkboxes:
- **Barcode**
- **Price**
- **$ Sign** (whether the `$` is drawn before the price)
- **Date**
- **Address**

These are per-print toggles; they do not affect stored data.

### 7.6 Per-element font controls (optional)

Font family / size / bold controls exist for main label elements (name, subtitle/size,
price, barcode digits) so a user can tweak the look — matching flexibility of the old
program (which used Arial Narrow at sizes ~12/10/20, bold). A **"Reset to default
layout"** action returns to the builder's designed look so the user can never permanently
break it. Everyday users should not need to touch these; they're a power-user affordance.

### 7.7 Fine-tuning knobs

- **Spacing** — vertical rhythm between elements (default `1.75`).
- **Side Margin** — inches, shifts content left/right (default `0.05` or similar small
  value).

These are exposed in the main "Print Settings" area for fine-tuning; staff should not
need them daily.

---

## 8. User interface (current state)

Single main window. Left panel = product list. Center = product details + print settings.
Right column = big print action buttons at top, preview(s) below.

### 8.1 Left panel

- **Search box** at the top — filters the list as the user types, case-insensitive,
  substring match on name.
- **Filter dropdown** ("Show:") — currently supports:
  - **All Items** (default)
  - **Cooked Food / Ingredient Labels** — keyed off `date_mode = "Best By"` (the
    definitional signal that a product has an ingredient label). Designed so **more
    categories can be added later without rework** — the filter is a general mechanism,
    not a one-off.
- **Item count** ("N items") below the search box.
- **Three-column list**: Name / Barcode # / Size. Alphabetical by name. Vertical
  scrollbar **always visible** (previously it only appeared when the panel was manually
  resized — fixed).
- The Search box and Filter dropdown **combine** — searching within a filtered view
  filters further.

### 8.2 Product details form (center-top)

Fields (single source of truth for both label types):
- **Name*** (required, wide)
- **Subtitle** (wide)
- **Ingredients** (wide, **multi-line 2–3 lines tall** so full ingredient lists are
  visible while typing)
- **Size** (narrow) + **Price ($)** (narrow) on one row
- **Barcode #** (narrow) + **`Auto`** button + **Date Mode** dropdown on one row
- **Notes** (wide)
- **Auto-capitalise Name & Subtitle** checkbox (on by default — the store's style is
  all-caps names)

Short fields are sized to their content and share rows (not full-width) — deliberate
compaction to eliminate scrolling.

Action buttons (green/red/blue):
- **Save** (green)
- **Delete** (red — with confirmation)
- **+ New** (blue) — clears the form and **auto-generates a fresh unique barcode number**
  (Section 5.5)

### 8.3 Print settings (center-bottom)

- **Print Date** (with mini calendar picker) + **Spacing** on one row
- **Side Margin** on the next
- **Show / Hide on label** checkboxes (Barcode, Price, $ Sign, Date, Address)

Note: **Printer** and **Label Size** are NOT on this screen. They're locked global
defaults chosen once in Settings (Section 8.5) so staff can't accidentally change them.
This was an early complaint — employees kept mis-selecting.

### 8.4 Right column — action buttons and previews

Top-right corner is the action zone, containing large green buttons:
- **`Print Barcode`** (barcode icon)
- **`Print Ingredients`** (icon)
- **`Print Combined Label`** — built in and functional, but **hidden by default** via a
  Settings toggle. Staff aren't using combined stock yet (they're using up 2.25 × 1.25
  first). Turn on the setting when ready.
- Above the buttons: **Quantity** stepper (− / N / +) and a **Test Print (1 barcode
  label)** button.

Directly below the action buttons: the **Preview area**.

**Preview options** (radio buttons for session override): Barcode / Ingredients /
Combined. A **Settings-level default** ("Default preview") controls what's shown on
launch, with **four options**:
- **Barcode only**
- **Ingredients only**
- **Combined only**
- **All three** (barcode on top, ingredients middle, combined bottom, stacked)

When a preview mode is active for a product with no relevant content (e.g. an ingredient
preview for a bag of almonds with no ingredient text), that preview area simply renders
blank — no special handling.

The Settings default persists across launches. When "Both/All three" is set as default,
the on-screen radio buttons still allow session-level override.

### 8.5 Settings menu (File / Settings / Help — Settings)

Global, persistent settings:
- **Business address line** (default: `Aaojee, Middletown, NY 845-342-0040`)
- **Default printer**
- **Default label size**
- **Default element show/hide states**
- **Best-By offset days** (default 10; editable via typing + `+`/`−` steppers)
- **Default preview** (Section 8.4)
- **Show Combined Print button** (default: off)

### 8.6 Behavioral rules that apply everywhere

- **Scroll wheel must never change dropdown values.** This was a real bug — clicking a
  dropdown left it focused, and scrolling to look at the preview would cycle its value.
  Every dropdown in the program (Label Type, Label Size, Date Mode, Printer, filter,
  etc.) must respond to scroll-wheel input by **doing nothing to its value**. Values
  change only by explicit click/selection.

---

## 9. The one-time import from the old system

Two source assets from the old computer were imported to seed the database:

- **`labeldata.mdb`** — Microsoft Access file, one table (`labels`), 432 usable rows.
- **A folder of `.docx` files** — one per ingredient label, from the old Word workflow.

### 9.1 The `.mdb` structure (documented from direct inspection)

Table: **`labels`**. 16 columns; **only 4 matter**:

| Column       | Type in MDB      | Use                                                    |
|--------------|------------------|--------------------------------------------------------|
| `itemname`   | Text(50)         | → product `name`. Trim leading/trailing whitespace.    |
| `itemsize`   | Text(50)         | → product `size`. Trim; blank allowed.                 |
| `price`      | Text(50) — messy | → product `price`. Strip `$` and spaces, parse decimal.|
| `barcodeNo`  | Long Integer     | → product `barcode_number`. Convert to text, **right-pad with `0` to 6 digits**. |

The other columns (`barcodetop`, `barcodeleft`, `nametop`, `nameleft`, `sizetop`,
`sizeleft`, `pricetop`, `priceleft`, `tax`, `res`, `res1`, `res2`) are **junk** — old
on-screen positions and unused flags. Ignore them.

**Price formatting pitfalls** in the MDB (all encountered in real data):
- `"$ 4.99"` (dollar + space)
- `"$4.99"` (dollar, no space)
- `"4.99"` (clean)

All must be normalized to a plain decimal number stored in `price`.

**Barcode length pitfalls:** almost every row is 4 digits, but a small number were
shorter — `12` and `200` are known — and would lose leading zeros if imported as integers
without the padding step. Both padded fine and are in the database, but their true POS
values should be **verified by hand** against physical labels.

### 9.2 The `.docx` folder

Contains ~73 files, each holding the raw text of one ingredient label — some combination
of **dish name**, a **parenthetical subtitle**, and the **ingredients list**.

**Matching quirks encountered in real data** (worth knowing for future imports):

- Filenames and internal names sometimes disagree. `GOBI MATTAR.docx` actually prints
  "GOBHI ALOO" inside; `KAJU KESAR PEDA.docx` prints "KAJU KATLI". The matcher was
  keyed to the name inside the document, not the filename.
- Some files were misfiled entirely — festival greetings (`Eid Mubarak.docx`,
  `shubh diwali.docx`), a price-increase notice (`Brownie.docx`), allergen notices
  (`SULPHUR DIOXIDE.docx`, `NUTS.docx`), and one empty file
  (`SABUDANA KHICHDI.docx`) and one nearly-empty (`WASABI _FRIED _GREENPEAS.docx`
  containing only "29Month"). These produce no ingredient content; they were reported
  as unmatched.
- Name spelling drift across systems: `MANGO MOOSE` vs `MANGO MOUSSE`;
  `Aloo Muttar` vs `Aloo Mattar`. Matches use minor-spelling tolerance.
- Multiple package sizes with the same name (MOONG DAL in 3 raw-lentil sizes; also
  GULAB JAMUN, BESAN BURFI, MANGO MOOSE, FENNEL CANDY): ingredient text was applied
  only to the cooked/prepared variant, not to bags of raw goods.

### 9.3 What the import ended up producing

- **432 products** imported (the DB source of `labeldata.mdb` contained 432 usable
  rows; one deleted row was counted in Access, hence Harjas's initial "433" recollection).
- **58 products received ingredient / subtitle text** from `.docx` matches.
- **58 `Best By`** / **374 `Packed`** at date-mode assignment time. Rule: any product that
  received `.docx` ingredient text → `Best By`; everything else → `Packed`. This is
  because *only cooked food has an ingredient label*, so the presence of imported
  ingredient text is the definitional signal.

### 9.4 Three known cooked-food dishes that ended up `Packed` due to import failure

Because their `.docx` sources were misnamed or empty:
- **GOBHI MUTTAR** (its `.docx` was misnamed and matched to GOBHI ALOO)
- **SABUDANA KHICHDI** (`.docx` was empty)
- **WASABI FRIED GREEN PEAS** (`.docx` had garbage content only)

These have been flipped to `date_mode = "Best By"` so the filter and everyday flow
include them correctly. Their ingredient text is still blank — needs to be entered by
hand, as does the subtitle.

### 9.5 `.docx` files that could not be matched (ingredient text with no product)

Six labels had real ingredient content but no product match: **ALSI PINNI**,
**ASSORTED NUTS**, **LOBIA** (label reads "Lobia Rasmissa"), **MORIYO**,
**STRAWBERRY MOUSSE**, **URAD CHANA DAL**. These are candidate products to **add** to
the database if they should exist.

### 9.6 The importer as a permanent feature

The import functionality is built into the program as a **permanent, optional feature** —
not a one-time build step. It can be run again at any time via a menu action, pointing at
any `.mdb` file. It must:
- Never overwrite silently. Existing products keyed on the same barcode should be skipped
  or confirmed.
- Report clearly at the end: how many imported, how many skipped, unmatched docs, and
  any short-barcode oddities to double-check.

---

## 10. Data safety, portability, and backups

- The entire program (executable, database, backups) lives in one folder — copy the
  folder to move the program to a new PC.
- **Automatic backups** — before major operations (like the rebuild), the current
  `products.db` is copied to `backups/products_<timestamp>.db`. The most recent known
  backup was `backups/products_20260525_021200.db`.
- **Manual Export / Restore** — the program has a File-menu action to save the DB to a
  chosen location (USB drive, etc.) and restore from one. This is the user-facing safety
  net and the migration path when moving to a new PC.
- SQLite `integrity_check` was verified `ok` after the last rebuild.

---

## 11. Packaging and delivery

- Source lives in the project folder.
- Build tool: **PyInstaller**.
- Output: a single **`.exe`** (or a small folder containing the `.exe` and its assets)
  the user double-clicks to launch. No console window, no separate Python install
  required for the end user.
- The build script and plain-language instructions for a non-developer to rebuild on any
  Windows 11 PC live in the project.
- **Dependencies:** kept minimal on purpose. `tkinter` is stdlib. The custom calendar was
  written by hand to avoid taking on `tkcalendar` as a dependency (which had known
  PyInstaller bundling headaches). Any new dependency should be evaluated against this
  bar: does its value justify the packaging risk?

---

## 12. Explicit non-goals — do NOT build these

- **No POS integration.** The store's POS is closed and off-limits. The barcode number
  is the sole link. Do not attempt to sync product data with it.
- **No inventory tracking, sales, or accounting features.** Out of scope.
- **No network, cloud, or multi-PC sync.** The program is single-PC. Portability is
  achieved by copying the folder.
- **No real GS1-registered UPCs.** The barcode numbers are internal lookup keys for the
  store's own POS. UPC-E encoding is used because it's the format the store's existing
  labels and POS use — not because the numbers are registered.
- **No copying cooked-recipe ingredient text onto packaged raw-goods variants.** The
  importer deliberately did not do this (raw dal vs cooked dal is different content). If
  the user wants ingredient text on packaged variants, they add it explicitly.

---

## 13. Currently open items / pending decisions

Nothing here blocks day-to-day use, but the next agent should be aware of these:

1. **6 unmatched ingredient labels from the `.docx` import** — Harjas hasn't decided
   whether to add them as products (ALSI PINNI, ASSORTED NUTS, LOBIA, MORIYO, STRAWBERRY
   MOUSSE, URAD CHANA DAL).
2. **Two short-barcode products need physical verification** — SONA MASOORI RICE
   (`barcodeNo 12` → `120000`) and GREEN CARDAMOM (`barcodeNo 200` → `200000`). Scan
   physical labels or check the POS to confirm.
3. **Combined label rollout timing** — combined stock is available; the feature is built
   and hidden. When the store switches from 2.25 × 1.25 to 2.25 × 3.00 stock, flip the
   "Show Combined Print button" setting on.
4. **Best-By list needs a human eyeball** — the 58-item Best-By list was reported after
   the rebuild; Harjas should verify no cooked dish is missing. The three known
   omissions (GOBHI MUTTAR, SABUDANA KHICHDI, WASABI FRIED GREEN PEAS) have been fixed.
5. **Build/transfer loop friction** — the Mac-edit → zip → flashdrive → PC-build cycle
   is painful. Two alternatives (work directly on the PC; use a cloud-sync folder) are
   documented above but not implemented.

---

## 14. Naming and identity conventions

Small details that matter for consistency:
- Product names are stored **in all caps** (`ALOO MATTAR`, not `Aloo Mattar`).
- Subtitles are stored **without the parentheses** (`PIGEON PEAS LENTILS`, not
  `(PIGEON PEAS LENTILS)`) — the label renderer adds them.
- Prices are stored **without `$`** (just `4.99`) — the renderer adds `$` per toggle.
- Barcode numbers are stored **as 6-digit strings** with leading zeros preserved (`012345`
  is valid; `12345` should be normalized to `123450` via right-pad).
- Address line is stored **as-is** including formatting/punctuation — the renderer
  prints it verbatim on one line.
- Dates on labels use **`M/D/YYYY`** format (as shown on the current labels).

---

## 15. Quick reference — commands and paths

- **Root project folder:** `AaojeeLabels/` (self-contained)
- **Live database:** `AaojeeLabels/products.db`
- **Backups folder:** `AaojeeLabels/backups/`
- **Import source folder (one-time):** `AaojeeLabels/import_source/` (holds legacy
  `labeldata.mdb` and `.docx` folder)
- **Old vendor program location (source of migrated data):** `C:\LABELNWET\` — files:
  `labeldata.mdb`, `labeldata.ldb` (Access lock file — ignore), `labelsetup` (XML config),
  `lablesnet` (old executable)
- **PyInstaller build:** run the build script from the project root on a Windows 11 PC
  with Python installed; the `.exe` appears in `dist/`.

---

## 16. Verification checklist for future changes

Any modification touching the label renderer, the barcode encoder, or the print pipeline
must be verified against these before shipping:

1. **Encoder:** the six reference products in Section 5.6 must produce their exact
   printed UPC-E strings.
2. **Right-pad rule:** entering `3143` must produce a barcode encoding `314300`.
3. **POS scan test:** print a Test Print label for a known-good product and scan it at
   the POS — it must produce the same lookup as an old label.
4. **Auto-generation collision:** create many new products in sequence; no duplicate
   barcode numbers should ever be saved.
5. **`.docx` re-import safety:** running the importer against the same source twice
   should not create duplicates.
6. **Scroll-wheel-on-dropdown:** clicking any dropdown then scrolling anywhere must not
   change the dropdown's value.
7. **Long-ingredient auto-fit:** the Gujrati Dal ingredient list (~12 items) must remain
   legible on the 2.25" × 1.25" ingredient-only label.
8. **Portability:** zip the entire project folder, unzip to a fresh location, rebuild —
   the program should launch with all data intact.

---

## 17. Maintenance log

> Feature upgrades from 2026-09-17 onward (scan-to-find, print queue, manager PIN,
> unsaved-changes warning, native-DPI printing, …) are logged in **`UPGRADE_TRACKER.md`**.

### 2026-09-17 — Bug-fix / optimization sweep (no intended UI or label changes)

Source only; the `.exe` must be rebuilt with `build.bat` to pick these up. Verified by
rendering every product in every label variant before/after (4,712 renders pixel-identical)
and encoding all 1,000,000 possible 6-digit barcodes before/after (identical).

- **Renderer:** Font Settings sizes of 6 (name/subtitle) or 6–8 (price) crashed label
  rendering (`UnboundLocalError`) — fixed. Font-file lookups are now cached.
- **Barcode engine:** UPC-E→UPC-A expansion for last digit 5–9 now uses the standard digit
  order (check digits provably unchanged); docstring reference value for 610400 corrected
  to 7.
- **Main window:** typing in Search (or any list refresh) no longer reloads the current
  product from the DB, which silently discarded unsaved edits and wiped the "✓ Saved."
  message; double-click still reloads. A non-numeric price (e.g. `4,99`) is now refused
  on Save instead of silently erasing the stored price. Ctrl+N / Ctrl+S work with Caps
  Lock on. Test Print now uses the same Spacing as real prints. Restore and MDB import
  take a safety backup first.
- **Database:** connections are closed promptly; backups/export/restore use SQLite's
  backup API (a plain file copy could miss changes still in the `-wal` file); Restore
  validates the chosen file before replacing anything; `%`/`_` in Search match literally.
- **Settings:** `settings.json` is written atomically; Font Settings no longer clears the
  subtitle's italic flag; built-in default address matches the real one.
- **Importer:** the real MDB column `barcodeNo` was never matched (re-imports got no
  barcodes and could duplicate every product); `"$ 4.99"`-style prices were dropped.
- **Printing:** bitmap converted once per job instead of per copy; a failed job is aborted
  so it can't jam the Windows print queue.

### 2026-09-17 — Follow-up (approved behavior changes)

- **Print Date rolls over at midnight** while the program stays open, as long as the field
  still shows the automatically set date; a date the user picked is kept (§6 updated in
  spirit: "defaults to today" now holds for long-running sessions too).
- **Print is refused with a warning** when the Print Date isn't a valid M/D/YYYY date or the
  Barcode # can't be encoded (applies only when that element would actually print).
- **Font Settings "Bold" is honoured** for every element (previously name/subtitle/price
  were forced bold and date/address/barcode digits forced regular). Default settings render
  identically.
- **Missing Arial Narrow falls back to Arial** instead of Pillow's tiny default font.
  Renders are identical on PCs that have Arial Narrow.
- `USER_GUIDE.txt` rewritten for the current UI; `build.bat` now installs `pyodbc`
  (non-fatal) so the importer is bundled; `BUILD_INSTRUCTIONS.txt` updated to match.
- Removed clutter: `.fuse_hidden*`, `.DS_Store`, `test_write.tmp`, the stale
  `source/products.db` mirror, and the one-off Mac-path script `source/import_data.py`.

---

*End of handoff document.*
