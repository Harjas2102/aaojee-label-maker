# Build Specification — Aaojee Label Maker

> **How to use this document.** Paste the entire file as the opening message of a new
> Cowork project. It is the complete brief for building the program. It is written so the
> build can proceed end to end with few or no further questions. Sections are ordered so
> that earlier ones (data model, barcode rules) are settled before later ones (UI, build).
>
> If you have the file `labeldata.mdb` from the old computer, upload it to the project as
> well — it is optional, but it enables the import feature to be tested with real data.

---

## 1. What this program is

A desktop application for a family business ("Aaojee", Middletown NY) that sells homemade
ready-to-go Indian food and some packaged dry goods. It replaces a proprietary,
vendor-locked label program. Its single job is **printing labels** for products. It does
**not** touch or replace the store's POS system.

The program must be:

- **Self-contained and portable.** Everything (program, database, backups) lives in one
  folder. Moving to a new PC = copy the folder.
- **Free of vendor lock-in.** Built in Python, human-readable source included, rebuildable
  for free by anyone on any future Windows PC.
- **Shippable as a double-clickable Windows `.exe`.** The user double-clicks an icon on the
  desktop; nothing else.

### Target environment

- Runs on: modern **Windows 11**.
- Built on: a modern **Windows 11** PC (one-time build; Python installed for the build only).
- Printers: **Zebra TLP 3844-Z** (primary) and **TSC TTP-244CE** (backup). Both connect by
  USB and appear as normal Windows printers. The program prints through the standard Windows
  print path and lets the user pick which installed printer to use.

---

## 2. Core concepts

### 2.1 The product database

The program stores a list of **products** (called "items" in the UI). A product is anything
the business wants to print a label for — a cooked dish (e.g. "Aloo Mattar"), a packaged dry
good (e.g. "Almond, 2 LB"), or anything in the future. All products share one set of fields;
each product simply fills in the fields relevant to it.

Design target: comfortably handle **1,000+ products** with instant search. (Current real
count is roughly 75 cooked dishes plus packaged goods, but the design must not feel limited.)

### 2.2 The two source label types, and the combined label

Historically the business printed two separate labels, on **2.25" × 1.25"** stock:

1. **Ingredient label** — plain printed text. Contains: dish **name** (large), an optional
   **parenthetical subtitle** describing the dish in plain English (e.g. "(PIGEON PEAS
   LENTILS)"), and an **ingredients list** (comma-separated text, introduced by the word
   "Ingredients :").
2. **Barcode label** — contains: dish **name**, **price**, a scannable **UPC-E barcode**,
   a **date line** ("Packed : M/D/YYYY"), and the business **address line**.

The business now wants a **combined label** that merges both onto a single larger
**2.25" × 3.00"** sticker. This combined label is the **primary** design going forward.

**All three label types must be supported**, on **both label sizes** where sensible:

| Label type        | Primary size   | Also available on |
|-------------------|----------------|-------------------|
| Combined          | 2.25" × 3.00"  | —                 |
| Ingredient-only   | 2.25" × 1.25"  | 2.25" × 3.00"     |
| Barcode-only      | 2.25" × 1.25"  | 2.25" × 3.00"     |

The separate labels must stay available because the business has existing stock of the
small 2.25" × 1.25" stickers to use up.

### 2.3 Relationship to the POS — important boundary

The store's POS is a separate, closed system. This program **does not and cannot** sync with
it automatically. The product list lives in **this program's own database file**.

The only link between the two systems is the **barcode number**: the same number is typed
into both the POS (once, by the user, as they do today) and into this program. When a
printed barcode is scanned at the POS, the POS reads the number and looks up its own price.

Consequence to keep in mind (not a bug — a deliberate, acceptable tradeoff for owning the
data): a price change must be entered in two places (the POS and this program). With ~75
dishes and infrequent price changes, this is acceptable. Do not attempt POS integration.

---

## 3. Product data model

Each product record has the following fields. Fields are optional unless marked required;
a product only fills in what applies to it.

| Field                | Type        | Notes |
|----------------------|-------------|-------|
| `name`               | text, **required** | The product name, e.g. "ALOO MATTAR". Free text, entered once, used by every label type. |
| `subtitle`           | text        | The parenthetical plain-English description, e.g. "PIGEON PEAS LENTILS". Stored **without** parentheses; the label adds them. Blank for most packaged goods. |
| `ingredients`        | long text   | Comma-separated ingredient list as plain text. Blank for items with no ingredient list (e.g. a bag of almonds). |
| `size`               | text        | Size/weight descriptor, e.g. "2 LB", "8 OZ", "6 PCS". Optional. |
| `price`              | decimal     | Selling price, e.g. 4.99. |
| `barcode_number`     | text (digits) | The product's permanent barcode number. See Section 4 for full rules. |
| `date_mode`          | choice      | One of: **Packed**, **Best By**, **None**. See Section 5. |
| `notes`              | text        | Free-text internal notes, not printed. Optional. |

### Rules

- **`name` is the single source of truth.** Both the ingredient and barcode portions of any
  label pull the name from this one field. This structurally eliminates the old problem of a
  product being typed differently in two programs (the old setup produced mismatches like
  "MANGO MOOSE" vs "MANGO MOUSSE", "Aloo Muttar" vs "Aloo Mattar").
- A product's `barcode_number` should be treated as **permanent** once set. Reprints must be
  byte-for-byte identical.
- `name` is required to save a product. Everything else may be blank.

---

## 4. Barcode rules — read carefully, this is the highest-risk area

The printed barcodes are **UPC-E** (8 digits total: a leading number-system digit `0`, six
data digits, and a trailing check digit). The store's POS stores and matches on the **six
data digits only** — it ignores the leading and trailing structural digits.

### 4.1 What the user enters

The user enters the **data digits** of the barcode number in a single text field. Going
forward they will typically enter a **full 6-digit number** (e.g. `312200`, `313700`,
`311400` — these are real examples from the current cooked-food labels).

### 4.2 Padding rule (confirmed against the old program's behavior)

If the user enters **fewer than 6 digits**, the program **right-pads with zeros to 6
digits**. This exactly reproduces the old program's behavior — verified example: the old
program stored Aloo Mattar as `3143` and printed the barcode `0 314300 9`, i.e. `3143` →
right-padded to `314300`.

- Input `3143` → data digits `314300`
- Input `312200` → data digits `312200` (already 6, unchanged)
- Reject input longer than 6 digits, or non-digit characters, with a clear error message.

### 4.3 Encoding

From the 6 data digits, the program constructs a valid, scannable **UPC-E barcode**:

- Number-system digit: `0` (leading).
- Compute the **check digit** correctly. (UPC-E's check digit is defined via its expansion
  to the equivalent UPC-A number; use a correct, tested implementation — do not approximate.)
- Render the barcode graphic with the standard human-readable digits beneath it, matching
  the familiar look of the existing labels (leading `0` to the left, check digit to the
  right, six data digits across the bottom).

### 4.4 Verification requirement

Because POS compatibility is critical, the program must include a **Test Print** path
(see Section 7.6) so the user can print one barcode and scan it at the POS to confirm it
reads identically to the old labels — **before** committing to re-entering or relying on
many products.

### 4.5 Duplicate protection

The current data has barcode numbers that are close together (e.g. `317222`, `317200`,
`316000`). When the user saves a product whose 6-digit data number matches another
product's, the program must **warn** about the collision (showing which product already
uses it) and ask for confirmation before saving. It should not silently allow duplicates.

---

## 5. The date line

Each product has a `date_mode` setting controlling the date line on labels that show one
(the barcode portion and the combined label):

- **Packed** — prints `Packed : M/D/YYYY` using **today's date** at print time.
- **Best By** — prints `Best By : M/D/YYYY`, calculated as **today's date + 10 days**.
- **None** — prints no date line at all. (Used for bulk dry goods like nuts that do not
  need a date.)

### Rules

- The "packing date" is **today's date**, pulled automatically at the moment of printing.
- The date shown must be **editable at print time** — a field on the print screen, defaulting
  to today, so the user can print labels ahead of time or for a past pack date. When the
  print date is changed, a "Best By" date recalculates as that date + 10 days.
- The 10-day offset should be defined as a single named setting in the code so it can be
  changed easily later, but it is not exposed in the everyday UI.

---

## 6. Label layouts

The build should produce **clean, fixed, well-designed layouts** for all three label types.
The designs are the builder's to craft, guided by the reference photos and the points below.
Per-element font controls are also required (Section 7.5), but the fixed layouts must look
correct and professional with no adjustment needed.

### 6.1 General styling (matches the existing labels)

- Everything **centered**.
- Product **name** is the largest text, bold.
- The **subtitle** prints in parentheses, smaller than the name, beneath it. Existing labels
  render name and subtitle bold/italic/underlined — reproduce that style closely.
- The ingredient list is introduced by the word **"Ingredients :"** (the word "Ingredients"
  underlined), followed by the comma-separated list, wrapping across lines as needed.
- Text must **auto-shrink to fit** the label. The worst realistic case is a long ingredient
  list — e.g. roughly: "Pigeon Peas Lentils, Tamarind, Jaggery, Mustard Seeds, Tomatoes,
  Salt, Ginger, Lemon Juice, Green Chilli, Curry Leaves, Asafoetida, Oil & Spices" — which
  must fit legibly on the small 2.25" × 1.25" label. Design the auto-fit around this.

### 6.2 Combined label — 2.25" × 3.00" (primary)

Contains, top to bottom (typical arrangement — refine visually):

- Product **name** (large, bold).
- **Subtitle** in parentheses, if present.
- **Ingredients** block ("Ingredients : ..."), if present.
- **Price** (large).
- **UPC-E barcode** with human-readable digits.
- **Date line** (per `date_mode`), if not None.
- **Address line**.

### 6.3 Ingredient-only label — 2.25" × 1.25" (also available at 3.00")

- Name, subtitle (if present), ingredients block. Plain text. No barcode, no price, no date.

### 6.4 Barcode-only label — 2.25" × 1.25" (also available at 3.00")

- Name, price, UPC-E barcode, date line (if not None), address line.

### 6.5 Per-element show/hide

Reproduce the old program's element toggles. On the print screen the user can show/hide:

- the barcode (a "Hide barcode" option),
- the price,
- the `$` sign on the price,
- the date line,
- the address line.

These are print-time toggles; sensible defaults come from saved settings (Section 8).

---

## 7. The user interface

A single main window. Layout follows the old program's proven shape (it worked well for the
business): a searchable list on the left, an editing/printing panel on the right.

### 7.1 Left panel — the product list

- A **search box** at the top labeled clearly (e.g. "Search").
- A scrollable **list/table** of all products, three columns: **Name**, **Barcode #**,
  **Size**. Sorted alphabetically by name.
- Search filters the list **as the user types**, matching anywhere in the name (typing
  "kar" surfaces "Karela Aloo"). Case-insensitive.
- Selecting a product loads it into the right panel.

### 7.2 Right panel — product details

- Editable fields for the full data model (Section 3): name, subtitle, ingredients, size,
  price, barcode number, date mode, notes.
- Buttons: **New** (clear the form for a new product), **Save**, **Delete** (with a
  confirmation prompt).
- Saving validates: name required; barcode digits-only and ≤ 6 digits; duplicate-barcode
  warning per Section 4.5.

### 7.3 Print controls

- **Label type** selector: Combined / Ingredient-only / Barcode-only.
- **Label size** selector: 2.25" × 3.00" / 2.25" × 1.25" (valid combinations per Section 2.2).
- **Printer** selector: lists installed Windows printers; defaults to the saved choice.
- **Quantity** field — number of copies to print (the business often prints e.g. 30 of one
  dish from a single batch cooked). Defaults to 1.
- **Print date** field — defaults to today; editable (Section 5).
- The per-element show/hide toggles (Section 6.5).
- A **Print** button.

### 7.4 Live preview

A preview area shows the currently selected product rendered as the chosen label type/size,
updating as fields and toggles change — like the old program's preview.

### 7.5 Font controls (secondary, optional to use)

Expose per-element **font family, size, and bold** controls for the main label elements
(name, subtitle/size text, price, barcode digits), matching the flexibility of the old
program (which used Arial Narrow at sizes around 12 / 10 / 20, bold). These adjust the
fixed layout; they are not required for everyday use. Include a **"Reset to default
layout"** action so the user can always return to the builder's designed look and never
permanently break it.

### 7.6 Test Print

A clearly labeled **Test Print** action that prints a single barcode label for the selected
product, for verifying POS scan compatibility (Section 4.4).

---

## 8. Settings

Global settings, stored in the program's folder, editable via a Settings screen:

- **Business address line** — defaults to: `Aaojee Middletown NY 845 342 0040`. Editable.
- **Default printer.**
- **Default label type and size.**
- **Default element show/hide states.**
- (Internal, not necessarily surfaced: the Best-By day offset, default 10.)

The old program stored equivalent settings in an XML file (`labelsetup`) with values
including `labelwidth 2.25`, `labelhight 1.25`, `upctype 4 - UPC-E`, `addressprint True`,
`packing True`, `expire False`, `address Aaojee Middletown NY 845 342 0040`. Use these as
the initial defaults.

---

## 9. The importer — reading the old `labeldata.mdb`

A **permanent, optional feature** (not a one-time build step): a button in the program,
e.g. **"Import from old database"**, usable at any time.

### Behavior

- The user picks a `.mdb` file (the old program's database — `labeldata.mdb`, a Microsoft
  Access file; the old folder was `C:\LABELNWET`).
- The program reads the products out of it and adds them to its own database.
- It must **not** overwrite or destroy existing products silently. For products whose
  barcode number already exists, either skip them or ask — make the behavior clear to the
  user and safe by default.
- Show a summary afterward: how many imported, how many skipped, any problems.

### Expectations and caveats

- The `.mdb` is expected to contain at least **name, barcode/UPC number, and size** for each
  product. It very likely does **not** contain ingredient text or subtitles (the old setup
  printed ingredients from separate Word documents, so that text probably never lived in
  this database). Imported cooked dishes will therefore usually still need their
  `ingredients` and `subtitle` filled in by hand afterward — this is expected, not a failure.
- Old records may store **short barcode numbers** (e.g. `3143`). Apply the **right-pad-to-6**
  rule (Section 4.2) on import so imported barcodes match what the POS expects.
- The exact Access table and column names are unknown until the file is opened during the
  build. Inspect the actual file, map its columns to this program's data model, and handle
  it gracefully. If a column is missing, import what is available and leave the rest blank.
- If no `.mdb` is provided, the feature simply sits unused; the program is fully functional
  without it. Hand-entry is always available as the fallback.

---

## 10. Data storage, portability, and backups

- All program data lives in **one self-contained folder** (e.g. `C:\AaojeeLabels\`):
  the program executable, the product database, the settings, and backups.
- The product database should be a single file in that folder (SQLite is a good fit:
  one file, no server, robust, free). Moving to a new PC = copy the folder; the program
  finds its database beside itself.
- **Automatic backups:** on each launch (or on a sensible schedule), copy the database into
  a `backups` subfolder, timestamped, keeping a reasonable number of recent copies. This
  protects against file corruption and mistakes.
- Provide a manual **Export / Backup** action (save a copy of the database to a chosen
  location, e.g. a USB drive) and a corresponding **Restore** action. This is the
  user-facing safety net and the migration path to a new PC.

---

## 11. Packaging and the build-to-EXE process

- Build the program in **Python**.
- The end deliverable is a **double-clickable Windows `.exe`** — the user launches it from a
  desktop icon, with no console window and no separate runtime to install.
- Use a standard Python-to-EXE packager (e.g. PyInstaller) to produce the executable.
- Acceptable delivery forms: a plain `.exe`, a `.zip` containing the `.exe` and its folder,
  or a simple installer — any of these, as long as the end state is "double-click to run".
- Provide a short, clear **build script** plus **step-by-step build instructions** written
  for a non-developer, covering: installing Python on the Windows 11 PC, running the build
  script, and where the finished `.exe` appears. The build step runs once; the resulting
  `.exe` is then permanent and rebuildable any time for free.
- Include the **full human-readable source code** and a brief note on how to rebuild, so the
  business is never locked to any vendor again.

### Deliverables checklist

1. Full Python source code, organized and commented.
2. A build script that produces the Windows `.exe`.
3. Plain-language build instructions for a non-developer on Windows 11.
4. A short user guide: day-to-day use, the importer, backup/restore, moving to a new PC.

---

## 12. Build order (suggested)

A logical sequence so the project can self-check as it goes:

1. Project skeleton; the single-folder data location; SQLite database with the Section 3
   schema.
2. UPC-E encoding with correct check digit + the right-pad rule. Verify by generating the
   known example: data `314300` must produce the barcode shown as `0 314300 9`. Also verify
   `312200`, `313700`, `311400`, `313900`, `610400` against the reference photos.
3. Main window: product list + search + detail form; New / Save / Delete; validation and
   duplicate-barcode warning.
4. The three label layouts + live preview + auto-shrink-to-fit.
5. Printing: printer selection, quantity, print-date field, element show/hide, Test Print.
6. Settings screen and saved defaults.
7. The optional `.mdb` importer.
8. Automatic backups + manual export/restore.
9. Per-element font controls + "reset to default layout".
10. Package to `.exe`; write build script, build instructions, and user guide.

---

## 13. Known reference values (from the existing setup)

- Business address line: `Aaojee Middletown NY 845 342 0040`
- Barcode symbology: UPC-E, leading number-system digit `0`
- Confirmed real products and their barcode data digits (for testing the encoder):
  Hakka Noodles `312200`, Rice Pilaf `313700`, Karela Aloo `311400`,
  Mango Mousse `313900`, Chana Masala `610400`, Aloo Mattar `314300`
  (Aloo Mattar was stored short as `3143` in the old program and right-padded to `314300`).
- Old program location: `C:\LABELNWET` — files `labeldata.mdb` (Access database),
  `labelsetup` (XML settings), `lablesnet` (the old executable).
- Label stock currently in use: 2.25" × 1.25". New combined stock: 2.25" × 3.00"
  (confirmed available from the supplier).
- Printers: Zebra TLP 3844-Z (primary), TSC TTP-244CE (backup), both USB.

---

## 14. Out of scope (do not build)

- Any integration, syncing, or direct communication with the POS system.
- Inventory tracking, sales, or accounting features.
- Network, cloud, or multi-PC sync. The program is single-PC; portability is achieved by
  copying the folder, not by networking.
- Real/registered GS1 UPC numbers. The barcode numbers are internal lookup keys for the
  store's own POS only; the program generates valid, scannable UPC-E barcodes from the
  numbers the user provides.
