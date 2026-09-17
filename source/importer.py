"""
importer.py — Optional .mdb (Microsoft Access) importer for Aaojee Label Maker.

Uses pyodbc with the Microsoft Access ODBC driver, which is available on
Windows when the "Microsoft Access Database Engine" is installed (free
download from Microsoft).

This feature is entirely optional.  If pyodbc is not installed, or the ODBC
driver is missing, the UI shows a clear error instead of crashing.

Spec §9 behaviour:
  • The user picks a .mdb file.
  • Products are read and added to the SQLite database.
  • Existing products (matched by barcode_number) are skipped by default.
  • A summary is returned: imported / skipped / errors.
  • Short barcode numbers are right-padded to 6 digits (spec §4.2).
  • Missing columns are handled gracefully (import what is available).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import Database

from barcode_engine import pad_barcode


# ──────────────────────────────────────────────────────────────────────────────
# Availability check
# ──────────────────────────────────────────────────────────────────────────────

def is_available() -> tuple[bool, str]:
    """Return (available, reason_if_not)."""
    try:
        import pyodbc  # noqa: F401
    except ImportError:
        return False, (
            "pyodbc is not installed.\n\n"
            "To enable the importer, install it:\n"
            "    pip install pyodbc\n\n"
            "You also need the Microsoft Access Database Engine (free download)."
        )
    try:
        import pyodbc
        drivers = [d for d in pyodbc.drivers() if "Access" in d]
        if not drivers:
            return False, (
                "No Microsoft Access ODBC driver found.\n\n"
                "Download and install the free 'Microsoft Access Database Engine' from:\n"
                "    https://www.microsoft.com/en-us/download/details.aspx?id=54920\n\n"
                "After installing, restart this program and try again."
            )
    except Exception as e:
        return False, f"Error checking ODBC drivers: {e}"
    return True, ""


# ──────────────────────────────────────────────────────────────────────────────
# Column-name discovery
# ──────────────────────────────────────────────────────────────────────────────

# Maps the known possible Access column names → our data-model field names.
# Column names in the old database are unknown until the file is opened, so we
# try multiple candidates and take the first match found.

_COLUMN_CANDIDATES: dict[str, list[str]] = {
    "name":           ["name", "itemname", "item_name", "productname",
                       "product_name", "description", "desc", "label"],
    # "barcodeno" is the column name in the store's real labeldata.mdb
    # (barcodeNo); without it every re-import came in with no barcode, which
    # also defeated the skip-existing-barcode duplicate protection.
    "barcode_number": ["barcode", "barcode_number", "barcodeno", "upc", "upccode",
                       "upc_code", "barcodenum", "code", "sku"],
    "size":           ["size", "itemsize", "item_size", "weight", "qty", "quantity"],
    "price":          ["price", "itemprice", "item_price", "cost", "retail"],
    "subtitle":       ["subtitle", "sub_title", "description2", "desc2",
                       "altname", "alt_name"],
    "ingredients":    ["ingredients", "ingredient", "contents", "ingr"],
    "notes":          ["notes", "note", "comment", "comments", "remarks"],
}


def _map_columns(available_cols: list[str]) -> dict[str, str]:
    """Return a mapping of our field name → actual column name in the table."""
    cols_lower = {c.lower(): c for c in available_cols}
    mapping: dict[str, str] = {}
    for our_field, candidates in _COLUMN_CANDIDATES.items():
        for cand in candidates:
            if cand.lower() in cols_lower:
                mapping[our_field] = cols_lower[cand.lower()]
                break
    return mapping


# ──────────────────────────────────────────────────────────────────────────────
# Main import function
# ──────────────────────────────────────────────────────────────────────────────

def import_from_mdb(mdb_path: str, db: "Database") -> dict:
    """Read products from *mdb_path* and insert them into *db*.

    Returns a dict:
      {
        "imported":    int,
        "skipped":     int,
        "errors":      int,
        "error_msgs":  list[str],
        "table_used":  str,
        "columns_found": list[str],
        "columns_missing": list[str],
      }
    """
    result = {
        "imported": 0,
        "skipped": 0,
        "errors": 0,
        "error_msgs": [],
        "table_used": "",
        "columns_found": [],
        "columns_missing": [],
    }

    ok, reason = is_available()
    if not ok:
        result["error_msgs"].append(reason)
        result["errors"] = 1
        return result

    import pyodbc

    if not os.path.isfile(mdb_path):
        result["error_msgs"].append(f"File not found: {mdb_path}")
        result["errors"] = 1
        return result

    # Build the connection string
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={mdb_path};"
    )

    try:
        conn = pyodbc.connect(conn_str, autocommit=True)
    except Exception as e:
        result["error_msgs"].append(f"Could not open the database: {e}")
        result["errors"] = 1
        return result

    try:
        cursor = conn.cursor()

        # ── Find the table ──────────────────────────────────────────────────
        table_name = _find_product_table(cursor)
        if not table_name:
            result["error_msgs"].append(
                "Could not find a product/label table in the database.\n"
                "Expected a table named something like 'labels', 'products', "
                "'items', or 'labeldata'."
            )
            result["errors"] = 1
            return result

        result["table_used"] = table_name

        # ── Column mapping ──────────────────────────────────────────────────
        available_cols = [col.column_name for col in cursor.columns(table=table_name)]
        col_map = _map_columns(available_cols)

        result["columns_found"] = list(col_map.keys())
        result["columns_missing"] = [
            f for f in _COLUMN_CANDIDATES if f not in col_map
        ]

        if "name" not in col_map:
            result["error_msgs"].append(
                f"Could not find a 'name' column in table '{table_name}'.\n"
                f"Available columns: {available_cols}"
            )
            result["errors"] = 1
            return result

        # ── Read rows ───────────────────────────────────────────────────────
        cursor.execute(f"SELECT * FROM [{table_name}]")
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]

        for row in rows:
            row_dict = dict(zip(col_names, row))
            try:
                _import_row(row_dict, col_map, db, result)
            except Exception as e:
                result["errors"] += 1
                result["error_msgs"].append(f"Row error: {e}")

    finally:
        conn.close()

    return result


def _find_product_table(cursor) -> str | None:
    """Return the name of the most likely product table in the Access database."""
    tables = [t.table_name for t in cursor.tables(tableType="TABLE")]

    # Prefer tables whose names suggest product/label data
    preferred = ["labels", "labeldata", "label_data", "products", "items",
                 "product", "item", "inventory"]
    for pref in preferred:
        for tbl in tables:
            if tbl.lower() == pref.lower():
                return tbl

    # Fall back: return the first non-system table
    return tables[0] if tables else None


def _import_row(
    row: dict,
    col_map: dict[str, str],
    db: "Database",
    result: dict,
) -> None:
    """Process a single Access row and insert it into SQLite."""

    def get(field: str, default=""):
        col = col_map.get(field)
        if col is None:
            return default
        val = row.get(col)
        if val is None:
            return default
        return str(val).strip()

    name = get("name")
    if not name:
        result["skipped"] += 1
        return

    # Barcode: right-pad to 6 digits
    raw_bc = get("barcode_number")
    if raw_bc:
        # Strip non-digit characters (some Access exports add spaces/dashes)
        digits_only = "".join(c for c in raw_bc if c.isdigit())
        if digits_only and len(digits_only) <= 6:
            barcode = pad_barcode(digits_only)
        elif digits_only:
            # > 6 digits: store as-is and note the problem
            barcode = digits_only[:6]
        else:
            barcode = ""
    else:
        barcode = ""

    # Skip if barcode already exists in the database
    if barcode:
        conflict = db.get_barcode_conflict(barcode)
        if conflict:
            result["skipped"] += 1
            return

    # Price — the old MDB stores text like "$ 4.99", "$4.99" or "4.99"
    price_str = get("price").replace("$", "").replace(",", "").strip()
    try:
        price = float(price_str) if price_str else None
    except ValueError:
        price = None

    product_data = {
        "name":           name.upper(),
        "subtitle":       get("subtitle"),
        "ingredients":    get("ingredients"),
        "size":           get("size"),
        "price":          price,
        "barcode_number": barcode,
        "date_mode":      "Packed",   # sensible default for imported items
        "notes":          get("notes"),
    }

    db.save_product(product_data)
    result["imported"] += 1
