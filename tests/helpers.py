"""
Shared helpers for the automated tests.

Tests never touch the live products.db or settings.json.  Each test builds a
throw-away database from tests/fixtures/products.json (a copy of the product
list) inside a temporary folder.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

GUI_ENABLED = os.environ.get("AAOJEE_SKIP_GUI_TESTS") != "1"


def fixture_products() -> list[dict]:
    with open(os.path.join(FIXTURES, "products.json"), encoding="utf-8") as f:
        return json.load(f)


def fixture_settings() -> dict:
    with open(os.path.join(FIXTURES, "settings.json"), encoding="utf-8") as f:
        return json.load(f)


class TempDirTestCase(unittest.TestCase):
    """Gives each test self.tmp, removed afterwards."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aaojee_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def make_database(folder: str, products: list[dict] | None = None):
    """Create products.db in *folder* filled with the fixture products (ids kept)."""
    from database import Database, PRODUCT_FIELDS
    path = os.path.join(folder, "products.db")
    db = Database(path)
    rows = fixture_products() if products is None else products
    conn = sqlite3.connect(path)
    with conn:
        for p in rows:
            fields = ["id", *[f for f in PRODUCT_FIELDS if f in p]]
            conn.execute(f"INSERT INTO products ({', '.join(fields)}) VALUES "
                         f"({', '.join('?' * len(fields))})", [p[f] for f in fields])
    conn.close()
    return db


def make_settings(folder: str, **overrides):
    from settings_manager import Settings
    path = os.path.join(folder, "settings.json")
    data = fixture_settings()
    data.update(overrides)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return Settings(path)


# ── UPC-E decoder (independent of the encoder's drawing code) ────────────────

def decode_upce(image) -> tuple[str, int, int] | None:
    """Scan an image row by row like a barcode reader.  Returns
    (6 data digits, check digit, module width in pixels) or None."""
    import barcode_engine as be
    mono = image.convert("L")
    w, h = mono.size
    px = mono.load()
    for y in range(h):
        runs: list[list[int]] = []
        for x in range(w):
            bit = 1 if px[x, y] < 128 else 0
            if runs and runs[-1][0] == bit:
                runs[-1][1] += 1
            else:
                runs.append([bit, 1])
        for i in range(len(runs) - 32):
            if runs[i][0] != 1:
                continue
            win = runs[i:i + 33]
            total = sum(n for _, n in win)
            if total % 51:
                continue
            m = total // 51
            if any(n % m for _, n in win):
                continue
            mods = [n // m for _, n in win]
            if mods[:3] != [1, 1, 1] or mods[-6:] != [1] * 6:
                continue
            digits, parity = "", ""
            for k in range(6):
                bits: list[int] = []
                for b, n in win[3 + 4 * k: 7 + 4 * k]:
                    bits += [b] * (n // m)
                hits = ([(d, "L") for d, pat in be._L.items() if pat == bits]
                        + [(d, "G") for d, pat in be._G.items() if pat == bits])
                if len(hits) != 1:
                    break
                digits += hits[0][0]
                parity += hits[0][1]
            else:
                if parity in be._PARITY:
                    return digits, be._PARITY.index(parity), m
    return None


# ── GUI harness ──────────────────────────────────────────────────────────────

class GuiHarness:
    """Opens the real main window on temp copies, with every dialog answered
    by the test.

      h.answers  — return values for askyesno / askyesnocancel, in order
      h.pins     — return values for the PIN prompt, in order
      h.saves    — file paths returned by "Save as" dialogs, in order
      h.opens    — file paths returned by "Open" dialogs, in order
      h.messages — (kind, title, text) of every dialog shown
      h.printed  — (image size, image mode, label size, copies) of every print
    """

    DIALOG_MODULES = ("app_window", "manager_lock", "print_queue", "trash_window",
                      "price_tools", "print_history")

    def __init__(self, folder: str, printer_dpi=(203, 203), **settings_overrides):
        import tkinter as tk
        import importlib
        self.answers: list = []
        self.pins: list = []
        self.saves: list = []
        self.opens: list = []
        self.messages: list = []
        self.printed: list = []
        self._patched: list = []
        self.folder = folder

        for name in self.DIALOG_MODULES:
            mod = importlib.import_module(name)
            mb = mod.messagebox
            for fn in ("showinfo", "showwarning", "showerror"):
                self._patch(mb, fn, self._recorder(fn))
            self._patch(mb, "askyesno", self._asker("askyesno"))
            self._patch(mb, "askyesnocancel", self._asker("askyesnocancel"))
            if hasattr(mod, "filedialog"):
                self._patch(mod.filedialog, "asksaveasfilename", lambda **k: self.saves.pop(0))
                self._patch(mod.filedialog, "askopenfilename", lambda **k: self.opens.pop(0))
        import manager_lock
        self._patch(manager_lock.simpledialog, "askstring", lambda *a, **k: self.pins.pop(0))
        import app_window
        self._patch(app_window, "print_labels", self._fake_print)
        self._patch(app_window, "get_printer_dpi", lambda name: printer_dpi)
        self._patch(app_window, "get_default_printer", lambda: "Test Printer")

        self.db = make_database(folder)
        self.settings = make_settings(folder, **settings_overrides)
        self.root = tk.Tk()
        self.app = app_window.AaojeeApp(self.root, self.db, self.settings, folder)
        self.root.state("normal")
        self.root.geometry("1280x800+0+0")
        # Keyboard tests need the window in front with focus
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        self.pump(300)

    def key(self, widget, sequence: str, ms: int = 250):
        """Send a key press (e.g. "<Return>") to *widget* as if typed."""
        widget.focus_force()
        self.pump(80)
        widget.event_generate(sequence, when="tail")
        self.pump(ms)

    def focused(self):
        return self.root.focus_get()

    def open_barcode(self, code: str):
        self.app._search_var.set(code)
        self.pump()
        self.app._on_search_enter()
        self.pump()

    def _patch(self, obj, attr, value):
        self._patched.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    def _recorder(self, kind):
        def show(title, message="", **_):
            self.messages.append((kind, title, message))
        return show

    def _asker(self, kind):
        def ask(title, message="", **_):
            self.messages.append((kind, title, message))
            return self.answers.pop(0)
        return ask

    def _fake_print(self, image, printer, label_size, copies=1):
        self.printed.append((image.size, image.mode, label_size, copies))

    def pump(self, ms: int = 150):
        self.root.update()
        self.root.after(ms, self.root.quit)
        self.root.mainloop()
        self.root.update()

    def last_message(self) -> str:
        return self.messages[-1][2] if self.messages else ""

    def close(self):
        try:
            for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(job)
            self.root.destroy()
        except Exception:
            pass
        for obj, attr, value in reversed(self._patched):
            setattr(obj, attr, value)
