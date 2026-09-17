"""
database.py — SQLite product database for Aaojee Label Maker
All product CRUD, barcode-conflict detection, print / price history, and
backup logic live here.
"""

import sqlite3
import os
import glob
from contextlib import contextmanager
from datetime import datetime

# Product fields a caller may set.  (id / created_at / updated_at / deleted_at
# are managed here.)
PRODUCT_FIELDS = ("name", "subtitle", "ingredients", "allergens", "net_weight",
                  "size", "price", "barcode_number", "date_mode", "category", "notes")

# Columns added after the first release (schema v1).  Each is added with
# ALTER TABLE the first time a newer program opens an older database.
_ADDED_COLUMNS = [
    ("allergens",  "TEXT NOT NULL DEFAULT ''"),   # U-007 "Contains: …" line
    ("net_weight", "TEXT NOT NULL DEFAULT ''"),   # U-008 "Net Wt: …" line
    ("category",   "TEXT NOT NULL DEFAULT ''"),   # U-013 list filter
    ("deleted_at", "TEXT"),                       # U-012 Trash (NULL = not deleted)
]

ACTIVE = "deleted_at IS NULL"


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


class Database:
    """Wraps the SQLite products database.  The file lives beside the source."""

    SCHEMA_VERSION = 2

    def __init__(self, db_path: str, backup_dir: str | None = None):
        self.db_path = db_path
        self._init_db(backup_dir)

    # ------------------------------------------------------------------
    # Initialisation / migration
    # ------------------------------------------------------------------

    def _init_db(self, backup_dir: str | None = None):
        """Create tables on first run, and upgrade an older database in place.

        If columns have to be added to an existing database and *backup_dir*
        is given, a copy named premigration_v<N>_<timestamp>.db is saved there
        first.  (That name is outside the products_*.db pattern, so the
        30-backup rotation never deletes it.)
        """
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS products (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT    NOT NULL,
                    subtitle        TEXT    NOT NULL DEFAULT '',
                    ingredients     TEXT    NOT NULL DEFAULT '',
                    size            TEXT    NOT NULL DEFAULT '',
                    price           REAL,
                    barcode_number  TEXT    NOT NULL DEFAULT '',
                    date_mode       TEXT    NOT NULL DEFAULT 'Packed',
                    notes           TEXT    NOT NULL DEFAULT '',
                    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
                );
            """)
            have = {r[1] for r in conn.execute("PRAGMA table_info(products)")}
            missing = [(c, decl) for c, decl in _ADDED_COLUMNS if c not in have]
            row_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

        if missing and row_count and backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._copy_to(os.path.join(backup_dir,
                                       f"premigration_v{self.SCHEMA_VERSION}_{ts}.db"))

        with self._connect() as conn:
            for col, decl in missing:
                conn.execute(f"ALTER TABLE products ADD COLUMN {col} {decl}")
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_products_name
                    ON products (name COLLATE NOCASE);

                CREATE INDEX IF NOT EXISTS idx_products_barcode
                    ON products (barcode_number);

                -- U-009: one row per print job (single, test or queue print)
                CREATE TABLE IF NOT EXISTS print_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    printed_at      TEXT    NOT NULL,
                    product_id      INTEGER,
                    product_name    TEXT    NOT NULL DEFAULT '',
                    size            TEXT    NOT NULL DEFAULT '',
                    barcode_number  TEXT    NOT NULL DEFAULT '',
                    price           REAL,
                    label_type      TEXT    NOT NULL DEFAULT '',
                    label_size      TEXT    NOT NULL DEFAULT '',
                    copies          INTEGER NOT NULL DEFAULT 1,
                    print_date      TEXT    NOT NULL DEFAULT '',
                    date_line       TEXT    NOT NULL DEFAULT '',
                    printer         TEXT    NOT NULL DEFAULT '',
                    source          TEXT    NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_print_history_time
                    ON print_history (printed_at);

                -- U-011: every price changed by the Change Prices tool
                CREATE TABLE IF NOT EXISTS price_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id        TEXT    NOT NULL,
                    changed_at      TEXT    NOT NULL,
                    product_id      INTEGER NOT NULL,
                    product_name    TEXT    NOT NULL DEFAULT '',
                    size            TEXT    NOT NULL DEFAULT '',
                    barcode_number  TEXT    NOT NULL DEFAULT '',
                    old_price       REAL,
                    new_price       REAL,
                    description     TEXT    NOT NULL DEFAULT '',
                    undone_at       TEXT
                );
            """)
            conn.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")

    @contextmanager
    def _connect(self):
        """Open a connection, commit (or roll back on error), and always close.

        sqlite3's own ``with conn:`` only commits — it never closes — so
        connections used to linger until garbage collection.  Closing them
        promptly lets SQLite fold the WAL file back into products.db.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Queries  (products in the Trash are left out unless asked for)
    # ------------------------------------------------------------------

    def get_all_products(self) -> list[dict]:
        """Return all products sorted alphabetically by name."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM products WHERE {ACTIVE} ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [dict(r) for r in rows]

    def search_products(self, query: str, barcodes: list[str] | tuple = ()) -> list[dict]:
        """Return products whose name or barcode number contains *query*
        (case-insensitive), plus any whose barcode is exactly one of
        *barcodes* (the decoded forms of a scanned code).  Exact barcode
        matches are listed first."""
        # Escape LIKE wildcards so "%" or "_" typed in the search box match
        # literally instead of matching everything.
        escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = f"%{escaped}%"
        barcodes = list(barcodes)
        marks = ",".join("?" * len(barcodes)) or "NULL"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM products WHERE {ACTIVE} AND ("
                "     name LIKE ? ESCAPE '!' OR barcode_number LIKE ? ESCAPE '!' "
                f"   OR barcode_number IN ({marks})) "
                f"ORDER BY (barcode_number IN ({marks})) DESC, name COLLATE NOCASE",
                (pattern, pattern, *barcodes, *barcodes),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_products_by_barcode(self, barcodes: list[str] | tuple) -> list[dict]:
        """Return every product whose barcode number is one of *barcodes*."""
        barcodes = [b for b in barcodes if b]
        if not barcodes:
            return []
        marks = ",".join("?" * len(barcodes))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM products WHERE {ACTIVE} AND barcode_number IN ({marks}) "
                "ORDER BY name COLLATE NOCASE",
                barcodes,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_product(self, product_id: int, include_deleted: bool = False) -> dict | None:
        where = "id = ?" if include_deleted else f"id = ? AND {ACTIVE}"
        with self._connect() as conn:
            row = conn.execute(f"SELECT * FROM products WHERE {where}", (product_id,)).fetchone()
        return dict(row) if row else None

    def get_next_barcode(self, start: int = 100000) -> str:
        """Return the lowest unused 6-digit barcode number as a zero-padded string.
        Starts searching from *start* (default 100000) and increments until a
        free slot is found.  Returns a 6-digit string, e.g. '100003'.
        Numbers used by products in the Trash count as used, so restoring a
        product can never clash with a newer one.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT barcode_number FROM products WHERE length(barcode_number) = 6"
            ).fetchall()
        used = {int(r[0]) for r in rows if r[0].isdigit()}

        candidate = start
        while candidate in used and candidate <= 999999:
            candidate += 1
        return str(candidate).zfill(6)

    def get_barcode_conflict(self, barcode: str, exclude_id: int | None = None) -> dict | None:
        """Return the product that already uses *barcode*, excluding *exclude_id*.
        Active products are preferred; a product in the Trash is returned (with
        a non-empty deleted_at) only if no active one uses the barcode."""
        if not barcode:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE barcode_number = ? AND id IS NOT ? "
                "ORDER BY deleted_at IS NOT NULL LIMIT 1",
                (barcode, exclude_id),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def save_product(self, data: dict) -> int:
        """Insert (id absent/0) or update (id present) a product.  Returns the id.

        On update only the fields present in *data* are written, so callers
        that don't know about newer fields (e.g. the importer) can't blank them.
        """
        now = _now()
        product_id = data.get("id")
        defaults = {"name": "", "subtitle": "", "ingredients": "", "allergens": "",
                    "net_weight": "", "size": "", "price": None, "barcode_number": "",
                    "date_mode": "Packed", "category": "", "notes": ""}

        with self._connect() as conn:
            if product_id:
                fields = [f for f in PRODUCT_FIELDS if f in data]
                sets = ", ".join(f"{f} = ?" for f in fields)
                conn.execute(
                    f"UPDATE products SET {sets}, updated_at = ? WHERE id = ?",
                    (*[data[f] for f in fields], now, product_id),
                )
            else:
                values = [data.get(f, defaults[f]) for f in PRODUCT_FIELDS]
                cur = conn.execute(
                    f"INSERT INTO products ({', '.join(PRODUCT_FIELDS)}, created_at, updated_at) "
                    f"VALUES ({', '.join('?' * len(PRODUCT_FIELDS))}, ?, ?)",
                    (*values, now, now),
                )
                product_id = cur.lastrowid

        return product_id

    # ── Trash (U-012) ─────────────────────────────────────────────────────────

    def delete_product(self, product_id: int):
        """Move a product to the Trash (it can be restored)."""
        with self._connect() as conn:
            conn.execute("UPDATE products SET deleted_at = ? WHERE id = ?", (_now(), product_id))

    def get_trash(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM products WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def restore_product(self, product_id: int):
        with self._connect() as conn:
            conn.execute("UPDATE products SET deleted_at = NULL, updated_at = ? WHERE id = ?",
                         (_now(), product_id))

    def purge_product(self, product_id: int):
        """Permanently delete a product that is in the Trash."""
        with self._connect() as conn:
            conn.execute("DELETE FROM products WHERE id = ? AND deleted_at IS NOT NULL",
                         (product_id,))

    def empty_trash(self) -> int:
        with self._connect() as conn:
            return conn.execute("DELETE FROM products WHERE deleted_at IS NOT NULL").rowcount

    # ── Print history (U-009) ─────────────────────────────────────────────────

    def log_print(self, entry: dict):
        text_cols = ("product_name", "size", "barcode_number", "label_type", "label_size",
                     "print_date", "date_line", "printer", "source")
        row = {c: entry.get(c) or "" for c in text_cols}
        row["product_id"] = entry.get("product_id")
        row["price"] = entry.get("price")
        row["copies"] = int(entry.get("copies") or 1)
        cols = list(row)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO print_history (printed_at, {', '.join(cols)}) "
                f"VALUES (?, {', '.join('?' * len(cols))})",
                (_now(), *row.values()),
            )

    def get_print_history(self, since: str | None = None, query: str = "") -> list[dict]:
        """Newest first.  *since* is an ISO timestamp; *query* matches name or barcode."""
        sql = "SELECT * FROM print_history WHERE 1=1"
        args: list = []
        if since:
            sql += " AND printed_at >= ?"
            args.append(since)
        if query:
            sql += " AND (product_name LIKE ? OR barcode_number LIKE ?)"
            args += [f"%{query}%", f"%{query}%"]
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY printed_at DESC, id DESC", args).fetchall()
        return [dict(r) for r in rows]

    # ── Price changes (U-011) ─────────────────────────────────────────────────

    def apply_price_batch(self, changes: list[dict], description: str) -> str:
        """Set new prices.  *changes*: dicts with id, new_price.  Returns the batch id."""
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        now = _now()
        with self._connect() as conn:
            for ch in changes:
                row = conn.execute("SELECT name, size, barcode_number, price FROM products "
                                   "WHERE id = ?", (ch["id"],)).fetchone()
                if row is None:
                    continue
                conn.execute("UPDATE products SET price = ?, updated_at = ? WHERE id = ?",
                             (ch["new_price"], now, ch["id"]))
                conn.execute(
                    "INSERT INTO price_history (batch_id, changed_at, product_id, product_name, "
                    "size, barcode_number, old_price, new_price, description) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (batch_id, now, ch["id"], row["name"], row["size"], row["barcode_number"],
                     row["price"], ch["new_price"], description))
        return batch_id

    def get_last_price_batch(self) -> list[dict]:
        """Rows of the most recent price change that hasn't been undone."""
        with self._connect() as conn:
            row = conn.execute("SELECT batch_id FROM price_history WHERE undone_at IS NULL "
                               "ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return []
            rows = conn.execute("SELECT * FROM price_history WHERE batch_id = ? ORDER BY "
                                "product_name COLLATE NOCASE", (row[0],)).fetchall()
        return [dict(r) for r in rows]

    def undo_price_batch(self, batch_id: str) -> tuple[int, list[str]]:
        """Put back old prices.  A price that was changed again since is left
        alone.  Returns (restored count, names left alone)."""
        restored, kept = 0, []
        now = _now()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM price_history WHERE batch_id = ? AND undone_at IS NULL",
                                (batch_id,)).fetchall()
            for r in rows:
                cur = conn.execute(
                    "UPDATE products SET price = ?, updated_at = ? WHERE id = ? AND price IS ?",
                    (r["old_price"], now, r["product_id"], r["new_price"]))
                if cur.rowcount:
                    restored += 1
                else:
                    kept.append(r["product_name"])
            conn.execute("UPDATE price_history SET undone_at = ? WHERE batch_id = ?", (now, batch_id))
        return restored, kept

    # ------------------------------------------------------------------
    # Backup / restore
    # ------------------------------------------------------------------

    def _copy_to(self, dest_path: str):
        """Write a consistent, self-contained copy of the live database.

        Uses SQLite's online-backup API rather than a plain file copy: in WAL
        mode recent changes can still be sitting in products.db-wal, which a
        file copy silently leaves behind.  The copy is switched to a normal
        single-file journal so it opens cleanly from a USB stick, and is
        written to a temp file first so a failure never leaves a half-written
        backup in place.
        """
        tmp_path = dest_path + ".tmp"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        try:
            src = sqlite3.connect(self.db_path)
            try:
                dst = sqlite3.connect(tmp_path)
                try:
                    src.backup(dst)
                    dst.execute("PRAGMA journal_mode=DELETE")
                finally:
                    dst.close()
            finally:
                src.close()
            os.replace(tmp_path, dest_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def backup(self, backup_dir: str) -> str:
        """Copy the database to *backup_dir* with a timestamp.  Returns the new path."""
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(backup_dir, f"products_{ts}.db")
        self._copy_to(dest)
        return dest

    def cleanup_old_backups(self, backup_dir: str, max_count: int = 30):
        """Delete the oldest backups so that at most *max_count* copies remain."""
        pattern = os.path.join(backup_dir, "products_*.db")
        files = sorted(glob.glob(pattern))          # oldest → newest (lexicographic)
        while len(files) > max_count:
            os.remove(files.pop(0))

    def restore_from(self, source_path: str):
        """Replace the live database with *source_path* (a backup file).

        The file is checked first, so picking the wrong file shows an error
        instead of wiping the product list.
        """
        src = sqlite3.connect(source_path)
        try:
            try:
                cols = {r[1] for r in src.execute("PRAGMA table_info(products)")}
                ok = src.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            except sqlite3.DatabaseError:
                cols, ok = set(), False
            if not ok or not {"name", "barcode_number"} <= cols:
                raise ValueError(
                    "That file is not a valid Aaojee products database.\n"
                    "Nothing was changed.")

            dst = sqlite3.connect(self.db_path)
            try:
                # Leave WAL mode while the pages are replaced (WAL databases
                # cannot change page size mid-backup); _connect re-enables it.
                dst.execute("PRAGMA journal_mode=DELETE")
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        self._init_db()

    def export_to(self, dest_path: str):
        """Copy the live database to *dest_path* (manual export / USB backup)."""
        self._copy_to(dest_path)

    # ------------------------------------------------------------------
    # Startup helper
    # ------------------------------------------------------------------

    def run_startup_backup(self, backup_dir: str, max_count: int = 30) -> str | None:
        """
        Create a backup on launch if the database file actually exists.
        Returns the backup path, or None if the DB doesn't exist yet.
        """
        if not os.path.exists(self.db_path):
            return None
        path = self.backup(backup_dir)
        self.cleanup_old_backups(backup_dir, max_count)
        return path
