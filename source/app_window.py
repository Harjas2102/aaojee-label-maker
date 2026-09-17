"""
app_window.py — Main tkinter window for Aaojee Label Maker.

Layout
──────
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Menu bar                                                             │
  ├────────────────┬────────────────────────────────┬────────────────────┤
  │  Search        │  Product detail form           │  Print buttons     │
  │  Product list  │  (compact, multi-field rows)    │  (Barcode / Ingr / │
  │  (treeview)    │  ─────────────────────────────  │   Combined)        │
  │                │  Print settings                │  Quantity · Test   │
  │                │  (date · spacing · margin)      │  ─────────────────  │
  │                │  Show / Hide toggles            │  Preview toggle    │
  │                │                                 │  Compact preview   │
  └────────────────┴────────────────────────────────┴────────────────────┘

Nothing on the right side scrolls — everything fits on screen at once.
Printer and Label Size are global defaults set in Settings, not on this screen.
"""

from __future__ import annotations

import os
import re
import sys
import math
import calendar
import contextlib
import io
from datetime import date, datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from PIL import Image, ImageTk, ImageDraw

try:                       # U-016: Windows 11 look (optional; see build.bat)
    import sv_ttk
except ImportError:
    sv_ttk = None

# Our modules (imported at runtime; all live in the same source directory)
from database import Database
from barcode_engine import (pad_barcode, validate_barcode_input, run_self_test,
                            scanned_code_to_data6)
from label_renderer import render_label, format_date_line, info_lines
from printer_manager import (get_printers, get_default_printer, print_labels,
                             get_printer_dpi, to_monochrome)
from settings_manager import Settings
from manager_lock import ManagerLock
from print_queue import PrintQueue, PrintQueueWindow, LABEL_CHOICES, default_choice
from categories import CATEGORIES, suggest_category
from allergens import AllergenPicker
from print_history import PrintHistoryWindow
from trash_window import TrashWindow
from price_tools import PriceChangeDialog, export_price_list
import importer as mdb_importer


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

LABEL_SIZES = ["2.25x3.00", "2.25x1.25"]
DATE_MODES  = ["Packed", "Best By", "None"]

# Category filters for the product list.  Extensible: to offer another filter,
# add a (label, predicate) entry — the predicate is any function of a product
# dict.  The cooked-food filter keys off date_mode, which is the source of
# truth for ingredient-label items ("Best By").
def _in_category(category: str):
    return lambda p: (p.get("category") or "") == category


PRODUCT_CATEGORIES = [
    ("All Items",                       lambda p: True),
    ("Cooked Food / Ingredient Labels", lambda p: (p.get("date_mode") or "") == "Best By"),
    *[(c, _in_category(c)) for c in CATEGORIES],          # U-013: Sweets, Spices, Dry Goods
    ("No category",                     lambda p: not (p.get("category") or "")),
]
NO_CATEGORY = "(none)"   # shown in the form's Category dropdown for ""

# U-013: product list columns (key, heading, width, stretch)
LIST_COLUMNS = [
    ("name",    "Name",      140, True),
    ("barcode", "Barcode #",  70, False),
    ("size",    "Size",       70, False),
    ("price",   "Price",      54, False),
]
_OUNCES_PER = {"OZ": 1.0, "LB": 16.0, "GM": 1 / 28.3495}


def _size_sort_key(size: str):
    """Weights sort by actual weight ('200 GM' < '14 OZ' < '1 LB' < '2 LB'),
    then volumes / counts by unit and number; blanks last."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*([A-Z]+)", (size or "").upper())
    if not m:
        return (2, "", 0.0, size or "")
    number, unit = float(m.group(1)), m.group(2)
    if unit in _OUNCES_PER:
        return (0, "", number * _OUNCES_PER[unit], size)
    return (1, unit, number, size)

# Compact preview: each tile's canvas is sized exactly to the rendered label
# (no margins).  U-015: the preview column takes all the width left over, and
# a single label is drawn as large as that column allows (up to
# PREVIEW_LIMIT_W wide); "All three" tiles are PREVIEW_STACKED_RATIO of that.
PREVIEW_MIN_W         = 300
PREVIEW_LIMIT_W       = 760
PREVIEW_STACKED_RATIO = 0.7
LIST_PANEL_W          = 340     # width of the product list column
LIST_PANEL_WIDE_W     = 450     # … on screens at least WIDE_SCREEN_W pixels wide
WIDE_SCREEN_W         = 1600
CENTER_W              = 540     # width of the Print / Edit column
CARD_WRAP             = 500

# U-014: the two screens
MODE_PRINT = "print"
MODE_EDIT  = "edit"
MODE_BAR_BG = "#1e293b"
UI_FONT = "Segoe UI" if sys.platform == "win32" else "TkDefaultFont"
PREVIEW_DPI       = 150     # render DPI for the on-screen preview

# Printing.  Labels are rendered at the printer's own resolution (e.g. 203 DPI
# on the Zebra / TSC) so every bar lands on whole printer dots.  If the DPI
# can't be read, or the setting is off, the older 600-DPI path is used and
# Windows scales the image down.
LEGACY_PRINT_DPI      = 600
NATIVE_MIN_MODULE_IN  = 0.013   # keep bars at least as wide as the 600-DPI path

# Preview mode options.  Internal value matches the render_label argument,
# plus a special "All" value meaning "stack Barcode + Ingredient + Combined".
PREVIEW_MODES = ["Barcode", "Ingredient", "Combined", "All"]
PREVIEW_MODE_LABELS = {
    "Barcode":    "Barcode only",
    "Ingredient": "Ingredients only",
    "Combined":   "Combined only",
    "All":        "All three (stacked)",
}

# Print-button colours (styled like the old green PRINT button)
BTN_GREEN     = "#276749"
BTN_GREEN_ACT = "#1e5037"
BTN_GREY      = "#4a5568"
BTN_GREY_ACT  = "#2d3748"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _block_mousewheel(widget) -> None:
    """Stop the scroll wheel from changing a combobox/spinbox value.

    Comboboxes and spinboxes cycle their value on a mouse-wheel scroll once
    they have focus, which causes accidental, silent changes.  Binding the
    wheel events at the widget level and returning "break" cancels that.
    """
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        widget.bind(seq, lambda _e: "break")


# ──────────────────────────────────────────────────────────────────────────────
# Main application class
# ──────────────────────────────────────────────────────────────────────────────

class AaojeeApp:
    def __init__(self, root: tk.Tk, db: Database, settings: Settings, app_dir: str):
        self.root     = root
        self.db       = db
        self.settings = settings
        self.app_dir  = app_dir

        # Current product state
        self._current_id: int | None = None
        self._preview_job = None          # after() handle for debounced preview
        self._preview_image: ImageTk.PhotoImage | None = None  # keep reference!
        self._icons: dict[str, ImageTk.PhotoImage] = {}
        # The day the Print Date field was last automatically set to "today".
        # While the field still shows that day, it rolls over at midnight.
        self._auto_print_date: date = date.today()
        # Form contents as last loaded/saved — used to detect unsaved changes.
        self._clean_snapshot: dict | None = None
        # Printer name → native DPI (or None if unusable), read once per session.
        self._printer_dpi_cache: dict[str, int | None] = {}

        # Installed printers (used by the Settings dialog)
        self._printers = get_printers()

        self.lock = ManagerLock(settings)
        self.print_queue = PrintQueue(os.path.join(app_dir, "print_queue.json"))
        self._queue_window: PrintQueueWindow | None = None

        self._setup_window()
        self._build_menu()
        self._build_ui()
        self._refresh_product_list()
        self._take_clean_snapshot()
        self._schedule_preview_update()
        self._schedule_date_rollover()
        self._schedule_lock_refresh()
        self.on_print_queue_changed()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ──────────────────────────────────────────────────────────────────────────
    # Window setup
    # ──────────────────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.root.title("Aaojee Label Maker")
        self.root.geometry("1280x800")
        self.root.minsize(1200, 700)
        if sys.platform == "win32":
            try:
                self.root.state("zoomed")          # U-016: use the whole screen
            except tk.TclError:
                pass
        try:
            icon_path = os.path.join(self.app_dir, "icon.ico")
            if os.path.isfile(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        # U-016: Windows 11 "Sun Valley" look when the sv_ttk package is
        # available; otherwise the standard Windows theme.
        style = ttk.Style()
        self._modern_theme = False
        if sv_ttk is not None:
            try:
                sv_ttk.set_theme("light")
                self._modern_theme = True
            except Exception:
                pass
        if not self._modern_theme and sys.platform == "win32":
            try:
                style.theme_use("vista")
            except Exception:
                pass
        self._bg = style.lookup(".", "background") or "#f0f0f0"
        style.configure("Accent.TButton", font=(UI_FONT, 10, "bold"))
        style.configure("Treeview", rowheight=30, font=(UI_FONT, 11))
        style.configure("Treeview.Heading", font=(UI_FONT, 10, "bold"))
        style.configure("Card.TFrame", background="white")
        style.configure("Card.TLabel", background="white")
        style.configure("Hint.TLabel", foreground="#6b7280")
        style.configure("Status.TLabel", foreground="#b42318")

        # Named styles for the coloured buttons
        def solid(bg, active, size=9, **kw):
            style = dict(bg=bg, fg="white", activebackground=active, activeforeground="white",
                         relief=tk.FLAT, bd=0, font=(UI_FONT, size, "bold"), cursor="hand2",
                         padx=12, pady=5)
            style.update(kw)
            return style

        self._btn_style = {
            "new":       solid("#2b6cb0", "#2c5282"),
            "save":      solid("#276749", "#22543d"),
            "delete":    solid("#c53030", "#9b2c2c"),
            "duplicate": solid("#4a5568", "#2d3748"),
            "queue":     solid("#2b6cb0", "#2c5282", pady=7),
            "test":      solid(BTN_GREY, BTN_GREY_ACT, pady=6),
            "print":     solid(BTN_GREEN, BTN_GREEN_ACT, size=13, pady=10, compound=tk.LEFT,
                               anchor="w"),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Menu bar
    # ──────────────────────────────────────────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Print Labels", command=lambda: self._set_mode(MODE_PRINT),
                              accelerator="Ctrl+P")
        file_menu.add_command(label="Edit Products", command=lambda: self._set_mode(MODE_EDIT),
                              accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="New Product", command=self._on_new, accelerator="Ctrl+N")
        file_menu.add_command(label="Duplicate as New Size", command=self._on_duplicate)
        file_menu.add_separator()
        file_menu.add_command(label="Print History…", command=self._open_print_history)
        file_menu.add_command(label="Trash…",         command=self._open_trash)
        file_menu.add_separator()
        file_menu.add_command(label="Export / Backup Database…", command=self._on_export)
        file_menu.add_command(label="Restore from Backup…",      command=self._on_restore)
        file_menu.add_separator()
        file_menu.add_command(label="Import from Old Database (.mdb)…", command=self._on_import_mdb)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close, accelerator="Alt+F4")
        menubar.add_cascade(label="File", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Settings…",               command=self._open_settings)
        settings_menu.add_command(label="Font Settings…",          command=self._open_font_settings)
        settings_menu.add_command(label="Reset to Default Layout",  command=self._reset_fonts)
        settings_menu.add_separator()
        settings_menu.add_command(label="Set / Change Manager PIN…", command=self._on_set_pin)
        settings_menu.add_command(label="Remove Manager PIN…",       command=self._on_remove_pin)
        settings_menu.add_command(label="Lock Now",                  command=self._on_lock_now)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Change Prices…",      command=self._open_price_tools)
        tools_menu.add_command(label="Export Price List…",  command=self._on_export_price_list)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_command(label="Run Barcode Self-Test", command=self._run_barcode_test)
        help_menu.add_command(label="About",                 command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)
        # Bind both cases so the shortcuts still work with Caps Lock on
        # (common here, since product names are typed in capitals).
        def bind_ctrl(letter, handler):
            for key in (letter.lower(), letter.upper()):
                self.root.bind(f"<Control-{key}>", handler)

        bind_ctrl("n", lambda _e: self._on_new())
        bind_ctrl("s", lambda _e: self._on_save() if self._mode == MODE_EDIT else None)
        bind_ctrl("f", self._focus_search)
        bind_ctrl("e", lambda _e: self._set_mode(MODE_EDIT))
        bind_ctrl("p", lambda _e: self._set_mode(MODE_PRINT))
        # U-017: printing from the keyboard (Print mode only)
        self.root.bind("<F5>", lambda _e: self._print_key("Barcode"))
        self.root.bind("<F6>", lambda _e: self._print_key("Ingredient"))
        self.root.bind("<F7>", lambda _e: self._print_key("Combined"))
        self.root.bind("<F8>", lambda _e: self._on_add_to_queue() if self._mode == MODE_PRINT else None)

    # ──────────────────────────────────────────────────────────────────────────
    # Main UI layout (U-014 / U-015)
    #
    #   ┌ mode bar: [Print Labels] [Edit Products]                 lock status ┐
    #   ├──────────────┬──────────────────────────────┬────────────────────────┤
    #   │ search       │ Print page  (product card,   │ label preview          │
    #   │ filter       │   quantity, date, buttons)   │ (large)                │
    #   │ product list │   — or —                     │                        │
    #   │              │ Edit page   (product form)   │                        │
    #   └──────────────┴──────────────────────────────┴────────────────────────┘
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._mode = MODE_PRINT
        self._icons = self._make_icons()
        self._build_mode_bar()

        body = ttk.Frame(self.root, padding=(8, 4, 8, 8))
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body, width=LIST_PANEL_W)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        self._build_left_panel(left)
        self._list_panel = left
        body.bind("<Configure>", self._on_body_resize)

        center = ttk.Frame(body, width=CENTER_W)
        center.pack(side=tk.LEFT, fill=tk.Y, padx=14)
        center.pack_propagate(False)

        preview_col = ttk.Frame(body)
        preview_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_preview_column(preview_col)

        self._print_page = ttk.Frame(center)
        self._edit_page = ttk.Frame(center)
        self._build_print_page(self._print_page)
        self._build_product_form(self._edit_page)
        self._print_page.pack(fill=tk.BOTH, expand=True)

        self._apply_combined_visibility()
        self._update_mode_bar()
        self.root.after_idle(self._focus_search)

    # ── Mode bar ──────────────────────────────────────────────────────────────

    def _build_mode_bar(self):
        bar = tk.Frame(self.root, bg=MODE_BAR_BG, padx=10, pady=6)
        bar.pack(fill=tk.X)
        tab = dict(font=(UI_FONT, 11, "bold"), relief=tk.FLAT, bd=0, cursor="hand2",
                   padx=16, pady=6)
        self._mode_buttons = {
            MODE_PRINT: tk.Button(bar, text="🖨  Print Labels", **tab,
                                  command=lambda: self._set_mode(MODE_PRINT)),
            MODE_EDIT:  tk.Button(bar, text="✏  Edit Products", **tab,
                                  command=lambda: self._set_mode(MODE_EDIT)),
        }
        self._mode_buttons[MODE_PRINT].pack(side=tk.LEFT)
        self._mode_buttons[MODE_EDIT].pack(side=tk.LEFT, padx=(6, 0))

        self._lock_btn = tk.Button(bar, text="Lock", font=(UI_FONT, 9, "bold"), relief=tk.FLAT,
                                   bd=0, cursor="hand2", padx=10, pady=4, bg="#e2e8f0",
                                   fg=MODE_BAR_BG, activebackground="#cbd5e1",
                                   command=self._on_lock_now)
        self._lock_var = tk.StringVar()
        self._lock_label = tk.Label(bar, textvariable=self._lock_var, bg=MODE_BAR_BG,
                                    fg="#e2e8f0", font=(UI_FONT, 9))
        self._lock_label.pack(side=tk.RIGHT, padx=(0, 8))
        self._mode_hint_var = tk.StringVar()
        tk.Label(bar, textvariable=self._mode_hint_var, bg=MODE_BAR_BG, fg="#cbd5e1",
                 font=(UI_FONT, 9)).pack(side=tk.LEFT, padx=16)

    def _update_mode_bar(self):
        for mode, btn in self._mode_buttons.items():
            active = mode == self._mode
            btn.configure(bg="white" if active else MODE_BAR_BG,
                          fg=MODE_BAR_BG if active else "#e2e8f0",
                          activebackground="white" if active else "#334155",
                          activeforeground=MODE_BAR_BG if active else "white")
        self._mode_hint_var.set(
            "Type or scan to find a product · Enter = pick · type quantity · Enter = print"
            if self._mode == MODE_PRINT else
            "Changes are saved only when you click Save (Ctrl+S)")

    def _set_mode(self, mode: str) -> bool:
        """Switch between Print Labels and Edit Products.  Editing needs the
        manager PIN when one is set.  Returns True if now in *mode*."""
        if mode == self._mode:
            return True
        if mode == MODE_EDIT:
            if not self.lock.require(self.root, "Editing products"):
                return False
        else:
            if not self._confirm_unsaved("going back to printing"):
                return False
            if self._is_dirty():                 # changes were thrown away
                self._revert_form()
        self._mode = mode
        if mode == MODE_EDIT:
            self._print_page.pack_forget()
            self._edit_page.pack(fill=tk.BOTH, expand=True)
            self._name_entry.focus_set()
        else:
            self._edit_page.pack_forget()
            self._print_page.pack(fill=tk.BOTH, expand=True)
            self._focus_search()
        self._update_mode_bar()
        self._refresh_lock_ui()
        return True

    def _revert_form(self):
        """Put the form back to the saved product (or empty)."""
        product = self.db.get_product(self._current_id) if self._current_id is not None else None
        if product:
            self._load_product(product)
        else:
            self._clear_form()

    # ── LEFT PANEL ────────────────────────────────────────────────────────────

    def _build_left_panel(self, parent: ttk.Frame):
        ttk.Label(parent, text="Find a product", font=(UI_FONT, 10, "bold")).pack(anchor=tk.W)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        search_entry = ttk.Entry(parent, textvariable=self._search_var, font=(UI_FONT, 15))
        search_entry.pack(fill=tk.X, pady=(2, 4), ipady=3)
        # Barcode scanners type the code and press Enter.  Enter opens the
        # scanned product (or the first match); Up / Down move through the
        # list; Escape clears the search.
        search_entry.bind("<Return>",   self._on_search_enter)
        search_entry.bind("<KP_Enter>", self._on_search_enter)
        search_entry.bind("<Escape>",   lambda _e: self._search_var.set(""))
        search_entry.bind("<Down>",     lambda _e: self._move_selection(1))
        search_entry.bind("<Up>",       lambda _e: self._move_selection(-1))
        self._search_entry = search_entry

        # Category filter (works together with Search)
        filter_frame = ttk.Frame(parent)
        filter_frame.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(filter_frame, text="Show:").pack(side=tk.LEFT)
        self._category_var = tk.StringVar(value=PRODUCT_CATEGORIES[0][0])
        category_combo = ttk.Combobox(
            filter_frame, textvariable=self._category_var,
            values=[c[0] for c in PRODUCT_CATEGORIES], state="readonly")
        category_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        category_combo.bind("<<ComboboxSelected>>", self._on_filter_change)
        _block_mousewheel(category_combo)

        self._count_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self._count_var, style="Hint.TLabel").pack(anchor=tk.W)

        # Treeview + always-visible vertical scrollbar.
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        cols = tuple(c[0] for c in LIST_COLUMNS)
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for key, _heading, width, stretch in LIST_COLUMNS:
            self._tree.heading(key, anchor=tk.W, command=lambda k=key: self._on_sort_column(k))
            self._tree.column(key, width=width, stretch=stretch)
        # U-013: click a heading to sort by it; click again to reverse
        self._sort_column = "name"
        self._sort_descending = False
        self._update_sort_headings()
        self._visible_products: list[dict] = []

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", lambda e: self._on_tree_select(e, force=True))
        self._tree.bind("<Return>", lambda _e: self._focus_quantity())

        # Keep product id → tree iid mapping
        self._tree_id_map: dict[str, int] = {}

    # ── PRINT PAGE (U-014) ────────────────────────────────────────────────────

    def _build_print_page(self, parent: ttk.Frame):
        # Product card
        card = ttk.Frame(parent, style="Card.TFrame", padding=(16, 12))
        card.pack(fill=tk.X, pady=(4, 10))
        ttk.Label(card, text="SELECTED PRODUCT", style="Card.TLabel",
                  font=(UI_FONT, 8, "bold"), foreground="#6b7280").pack(anchor=tk.W)
        self._action_name_var = tk.StringVar(value="(none)")
        self._card_name = ttk.Label(card, textvariable=self._action_name_var, style="Card.TLabel",
                                    font=(UI_FONT, 22, "bold"), wraplength=CARD_WRAP)
        self._card_name.pack(anchor=tk.W)
        self._card_subtitle_var = tk.StringVar()
        ttk.Label(card, textvariable=self._card_subtitle_var, style="Card.TLabel",
                  font=(UI_FONT, 11, "italic"), foreground="#374151",
                  wraplength=CARD_WRAP).pack(anchor=tk.W)
        self._card_details_var = tk.StringVar(value="Type a name or scan a label to begin.")
        ttk.Label(card, textvariable=self._card_details_var, style="Card.TLabel",
                  font=(UI_FONT, 14)).pack(anchor=tk.W, pady=(6, 0))
        self._card_date_var = tk.StringVar()
        ttk.Label(card, textvariable=self._card_date_var, style="Card.TLabel",
                  font=(UI_FONT, 11), foreground="#374151").pack(anchor=tk.W)
        self._card_allergens_var = tk.StringVar()
        ttk.Label(card, textvariable=self._card_allergens_var, style="Card.TLabel",
                  font=(UI_FONT, 10, "bold"), foreground="#9b2c2c",
                  wraplength=CARD_WRAP).pack(anchor=tk.W)

        # Quantity
        qty_frame = ttk.Frame(parent)
        qty_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(qty_frame, text="Quantity", font=(UI_FONT, 13, "bold")).pack(side=tk.LEFT)
        self._qty_var = tk.StringVar(value="1")
        step = dict(font=(UI_FONT, 16, "bold"), width=3, relief=tk.FLAT, bd=0, cursor="hand2",
                    bg="#e2e8f0", activebackground="#cbd5e1")
        tk.Button(qty_frame, text="−", command=self._qty_minus, **step).pack(side=tk.LEFT, padx=(14, 0))
        self._qty_entry = tk.Entry(qty_frame, textvariable=self._qty_var, font=(UI_FONT, 20, "bold"),
                                   width=5, justify=tk.CENTER, relief=tk.SOLID, bd=1)
        self._qty_entry.pack(side=tk.LEFT, padx=6, ipady=2)
        tk.Button(qty_frame, text="+", command=self._qty_plus, **step).pack(side=tk.LEFT)
        # U-017: Enter prints the barcode label, Shift+Enter the ingredients label
        for seq in ("<Return>", "<KP_Enter>"):
            self._qty_entry.bind(seq, lambda _e: self._print_key("Barcode"))
        self._qty_entry.bind("<Shift-Return>", lambda _e: self._print_key("Ingredient"))
        self._qty_entry.bind("<Escape>", self._focus_search)
        self._qty_entry.bind("<FocusIn>", lambda _e: self._qty_entry.select_range(0, tk.END))
        ttk.Label(qty_frame, text="Enter = print", style="Hint.TLabel").pack(side=tk.LEFT, padx=10)

        # Print date + show / hide
        date_row = ttk.Frame(parent)
        date_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(date_row, text="Print Date", font=(UI_FONT, 10, "bold")).pack(side=tk.LEFT)
        self._print_date_var = tk.StringVar(value=self._today_str())
        self._print_date_var.trace_add("write", self._on_date_change)
        self._date_entry = ttk.Entry(date_row, textvariable=self._print_date_var, width=12)
        self._date_entry.pack(side=tk.LEFT, padx=(8, 4))
        ttk.Button(date_row, text="📅", width=3, command=self._open_calendar).pack(side=tk.LEFT)

        toggle_frame = ttk.Frame(parent)
        toggle_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(toggle_frame, text="Show on label:").pack(side=tk.LEFT, padx=(0, 4))
        self._show_barcode_var = tk.BooleanVar(value=self.settings.show_barcode)
        self._show_price_var   = tk.BooleanVar(value=self.settings.show_price)
        self._show_dollar_var  = tk.BooleanVar(value=self.settings.show_dollar_sign)
        self._show_date_var    = tk.BooleanVar(value=self.settings.show_date)
        self._show_address_var = tk.BooleanVar(value=self.settings.show_address)
        chk = dict(command=self._schedule_preview_update)
        for text, var in (("Barcode", self._show_barcode_var), ("Price", self._show_price_var),
                          ("$ Sign", self._show_dollar_var), ("Date", self._show_date_var),
                          ("Address", self._show_address_var)):
            ttk.Checkbutton(toggle_frame, text=text, variable=var, **chk).pack(side=tk.LEFT, padx=3)

        # Big print buttons
        self._barcode_btn = tk.Button(
            parent, text="  Print Barcode          Enter / F5", image=self._icons["barcode"],
            command=lambda: self._print_label_type("Barcode"), **self._btn_style["print"])
        self._barcode_btn.pack(fill=tk.X, pady=3)
        self._ingredient_btn = tk.Button(
            parent, text="  Print Ingredients      Shift+Enter / F6",
            image=self._icons["ingredient"],
            command=lambda: self._print_label_type("Ingredient"), **self._btn_style["print"])
        self._ingredient_btn.pack(fill=tk.X, pady=3)
        # Combined button — built now, shown only when enabled in Settings
        self._combined_btn = tk.Button(
            parent, text="  Print Combined Label   F7", image=self._icons["combined"],
            command=lambda: self._print_label_type("Combined"), **self._btn_style["print"])

        # Print queue — add the current product, or open the batch list
        self._queue_row = ttk.Frame(parent)
        self._queue_row.pack(fill=tk.X, pady=(8, 0))
        self._queue_row.columnconfigure(0, weight=1, uniform="q")
        self._queue_row.columnconfigure(1, weight=1, uniform="q")
        tk.Button(self._queue_row, text="+ Add to Print Queue  (F8)", command=self._on_add_to_queue,
                  **self._btn_style["queue"]).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self._queue_btn = tk.Button(self._queue_row, text="Print Queue",
                                    command=self._open_print_queue, **self._btn_style["queue"])
        self._queue_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        tk.Button(parent, text="Test Print  (1 barcode label, to check it scans)",
                  command=self._on_test_print, **self._btn_style["test"]).pack(fill=tk.X, pady=(6, 4))

        self._status_var = tk.StringVar()
        ttk.Label(parent, textvariable=self._status_var, style="Status.TLabel",
                  wraplength=CARD_WRAP).pack(anchor=tk.W, pady=(4, 0))

    def _update_card(self, data: dict):
        """Refresh the Print page's product card from the form data."""
        if not data["name"]:
            self._card_subtitle_var.set("")
            self._card_details_var.set("Type a name or scan a label to begin.")
            self._card_date_var.set("")
            self._card_allergens_var.set("")
            return
        self._card_subtitle_var.set(f"({data['subtitle']})" if data["subtitle"] else "")
        parts = []
        if data["size"]:
            parts.append(data["size"])
        parts.append("no price" if data["price"] is None else f"${data['price']:.2f}")
        parts.append(f"Barcode {data['barcode_number']}" if data["barcode_number"] else "no barcode")
        self._card_details_var.set("   ·   ".join(parts))
        date_line = format_date_line(data["date_mode"] or "Packed", self._get_pack_date(),
                                     self.settings.bestby_offset_days)
        self._card_date_var.set(date_line or "No date line")
        self._card_allergens_var.set(f"Contains: {data['allergens']}" if data["allergens"] else "")

    # ── PREVIEW COLUMN (U-015) ────────────────────────────────────────────────

    def _build_preview_column(self, parent: ttk.Frame):
        hdr = ttk.Frame(parent)
        hdr.pack(fill=tk.X)
        ttk.Label(hdr, text="Label Preview", font=(UI_FONT, 10, "bold")).pack(side=tk.LEFT)
        # Default is read from settings.default_preview; the radios are a
        # session-level override the user can change at any time.
        initial_mode = self.settings.get("default_preview", "Barcode")
        if initial_mode not in PREVIEW_MODES:
            initial_mode = "Barcode"
        self._preview_type_var = tk.StringVar(value=initial_mode)
        radios = ttk.Frame(parent)
        radios.pack(fill=tk.X, pady=(2, 6))
        for i, (label, value) in enumerate([("Barcode", "Barcode"), ("Ingredients", "Ingredient"),
                                            ("Combined", "Combined"), ("All three", "All")]):
            ttk.Radiobutton(radios, text=label, value=value, variable=self._preview_type_var,
                            command=self._schedule_preview_update).grid(
                row=i // 2, column=i % 2, sticky=tk.W, padx=(0, 16))

        # Scrollable preview container — holds the placeholder (when no product
        # is selected) or 1–3 stacked preview tiles.
        preview_outer = ttk.Frame(parent)
        preview_outer.pack(fill=tk.BOTH, expand=True)
        preview_outer.rowconfigure(0, weight=1)
        preview_outer.columnconfigure(0, weight=1)
        self._preview_scrollcanvas = tk.Canvas(preview_outer, highlightthickness=0, bg=self._bg)
        pv_scrollbar = ttk.Scrollbar(preview_outer, orient=tk.VERTICAL,
                                     command=self._preview_scrollcanvas.yview)
        self._preview_scrollcanvas.configure(yscrollcommand=pv_scrollbar.set)
        self._preview_scrollcanvas.grid(row=0, column=0, sticky="nsew")
        pv_scrollbar.grid(row=0, column=1, sticky="ns")
        self._preview_inner = ttk.Frame(self._preview_scrollcanvas)
        self._preview_scrollcanvas.create_window((0, 0), window=self._preview_inner, anchor="nw")
        self._preview_inner.bind(
            "<Configure>",
            lambda _e: self._preview_scrollcanvas.configure(
                scrollregion=self._preview_scrollcanvas.bbox("all")))
        # The label is drawn to fit this box; re-draw when the window is resized.
        self._preview_box = (PREVIEW_MIN_W + 30, 600)
        preview_outer.bind("<Configure>", self._on_preview_resize)
        self._preview_scrollcanvas.bind(
            "<MouseWheel>",
            lambda e: self._preview_scrollcanvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        # Placeholder shown when no product is selected
        self._preview_placeholder = tk.Canvas(
            self._preview_inner, width=PREVIEW_MIN_W, height=200,
            bg="white", highlightthickness=1, highlightbackground="#cbd5e1")
        self._preview_placeholder.create_text(
            PREVIEW_MIN_W // 2, 100, text="(select a product)", fill="grey")

        # Three preview tiles.  Each has a small caption (only shown when
        # multiple are stacked) plus a bordered canvas sized to its label.
        self._preview_tiles: dict[str, dict] = {}
        for value, caption in [("Barcode", "Barcode"),
                               ("Ingredient", "Ingredients"),
                               ("Combined", "Combined")]:
            tile = ttk.Frame(self._preview_inner)
            cap = ttk.Label(tile, text=caption, font=(UI_FONT, 8, "bold"), style="Hint.TLabel")
            border = tk.Frame(tile, relief=tk.SOLID, bd=1, bg="white")
            canvas = tk.Canvas(border, width=PREVIEW_MIN_W, height=80,
                               bg="white", highlightthickness=0)
            canvas.pack()
            border.pack(anchor=tk.W)
            self._preview_tiles[value] = {
                "frame": tile, "caption": cap, "border": border,
                "canvas": canvas, "image": None,
            }

    # ── Button icons ──────────────────────────────────────────────────────────

    def _make_icons(self) -> dict:
        """Draw small white icons for the print buttons using Pillow."""
        icons: dict[str, ImageTk.PhotoImage] = {}
        size = 24

        # Barcode — a row of vertical bars
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for x, w in [(2, 2), (6, 1), (9, 3), (14, 1), (17, 2), (21, 1)]:
            d.rectangle([x, 4, x + w - 1, 19], fill="white")
        icons["barcode"] = ImageTk.PhotoImage(img)

        # Ingredients — a bulleted list
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for yy in (6, 12, 18):
            d.ellipse([3, yy - 2, 7, yy + 2], fill="white")
            d.rectangle([10, yy - 1, 21, yy + 1], fill="white")
        icons["ingredient"] = ImageTk.PhotoImage(img)

        # Combined — a label tag with text lines and a mini barcode
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([3, 2, 20, 21], outline="white", width=2)
        d.rectangle([6, 6, 17, 7], fill="white")
        d.rectangle([6, 10, 17, 11], fill="white")
        for x in range(6, 18, 2):
            d.rectangle([x, 14, x, 18], fill="white")
        icons["combined"] = ImageTk.PhotoImage(img)

        return icons

    def _on_body_resize(self, event):
        """Give the product list more room on wide screens so names and
        sizes aren't cut off."""
        wide = event.width >= WIDE_SCREEN_W
        width = LIST_PANEL_WIDE_W if wide else LIST_PANEL_W
        if int(self._list_panel.cget("width")) != width:
            self._list_panel.configure(width=width)
            self._tree.column("size", width=100 if wide else 70)

    def _on_preview_resize(self, event):
        old_w, old_h = self._preview_box
        if abs(event.width - old_w) > 12 or abs(event.height - old_h) > 12:
            self._preview_box = (event.width, event.height)
            self._schedule_preview_update()

    def _preview_limits(self) -> tuple[int, int]:
        """(max width, max height) for a single previewed label."""
        box_w, box_h = self._preview_box
        return (max(PREVIEW_MIN_W, min(PREVIEW_LIMIT_W, box_w - 30)),
                max(200, box_h - 12))

    def _apply_combined_visibility(self):
        """Show or hide the Combined PRINT button per the Settings toggle.
        The Combined preview radio is always available regardless."""
        show = bool(self.settings.get("show_combined_button", False))
        if show:
            if not self._combined_btn.winfo_manager():
                self._combined_btn.pack(fill=tk.X, pady=3, after=self._ingredient_btn)
        else:
            self._combined_btn.pack_forget()

    # ── Keyboard flow (U-017) ─────────────────────────────────────────────────

    def _focus_quantity(self):
        if self._mode != MODE_PRINT:
            return "break"
        self._qty_entry.focus_set()
        self._qty_entry.select_range(0, tk.END)
        self._qty_entry.icursor(tk.END)
        return "break"

    def _move_selection(self, delta: int):
        items = self._tree.get_children()
        if not items:
            return "break"
        sel = self._tree.selection()
        index = items.index(sel[0]) + delta if sel else (0 if delta > 0 else len(items) - 1)
        index = max(0, min(len(items) - 1, index))
        self._tree.selection_set(items[index])
        self._tree.see(items[index])
        return "break"

    def _print_key(self, label_type: str):
        """Print from the keyboard (Print mode only), then go back to Search."""
        if self._mode != MODE_PRINT:
            return None
        if label_type == "Combined" and not self._combined_btn.winfo_manager():
            return "break"
        self._print_label_type(label_type)
        self._focus_search()
        return "break"

    def _show_shortcuts(self):
        messagebox.showinfo(
            "Keyboard Shortcuts",
            "PRINT LABELS\n"
            "  Type a name, or scan a label   find the product\n"
            "  Up / Down                      move through the list\n"
            "  Enter (in Search)              pick the first product, go to Quantity\n"
            "  Enter (in Quantity)            print barcode labels\n"
            "  Shift+Enter (in Quantity)      print ingredient labels\n"
            "  F5 / F6 / F7                   print barcode / ingredients / combined\n"
            "  F8                             add to the print queue\n"
            "  Esc                            back to Search\n\n"
            "EVERYWHERE\n"
            "  Ctrl+F   Search          Ctrl+P   Print Labels\n"
            "  Ctrl+E   Edit Products   Ctrl+N   New product\n"
            "  Ctrl+S   Save (Edit Products)")

    # ── PRODUCT FORM ──────────────────────────────────────────────────────────

    def _build_product_form(self, parent: ttk.Frame):
        hdr = ttk.Frame(parent)
        hdr.pack(fill=tk.X, pady=(4, 8))
        ttk.Label(hdr, text="Product Details", font=(UI_FONT, 13, "bold")).pack(side=tk.LEFT)
        tk.Button(hdr, text="+ New",   command=self._on_new,
                  **self._btn_style["new"]).pack(   side=tk.RIGHT, padx=2)
        tk.Button(hdr, text="⧉ Duplicate", command=self._on_duplicate,
                  **self._btn_style["duplicate"]).pack(side=tk.RIGHT, padx=2)
        tk.Button(hdr, text="✕ Delete", command=self._on_delete,
                  **self._btn_style["delete"]).pack(side=tk.RIGHT, padx=2)
        tk.Button(hdr, text="💾 Save",  command=self._on_save,
                  **self._btn_style["save"]).pack(  side=tk.RIGHT, padx=2)

        form = ttk.Frame(parent)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        # Row 0 — Name (wide)
        ttk.Label(form, text="Name *").grid(row=0, column=0, sticky=tk.W, pady=3, padx=(0, 6))
        self._name_var = tk.StringVar()
        self._name_var.trace_add("write", self._on_form_change)
        self._name_entry = ttk.Entry(form, textvariable=self._name_var)
        self._name_entry.grid(row=0, column=1, columnspan=3, sticky=tk.EW, pady=3)

        # Row 1 — Subtitle (wide)
        ttk.Label(form, text="Subtitle").grid(row=1, column=0, sticky=tk.W, pady=3, padx=(0, 6))
        self._subtitle_var = tk.StringVar()
        self._subtitle_var.trace_add("write", self._on_form_change)
        ttk.Entry(form, textvariable=self._subtitle_var).grid(
            row=1, column=1, columnspan=3, sticky=tk.EW, pady=3)

        # Row 2 — Ingredients (wide, multi-line so the whole list is visible)
        ttk.Label(form, text="Ingredients").grid(row=2, column=0, sticky=tk.NW, pady=3, padx=(0, 6))
        self._ingredients_text = tk.Text(form, height=4, wrap=tk.WORD, font=(UI_FONT, 10),
                                         relief=tk.SOLID, bd=1, highlightthickness=0,
                                         padx=4, pady=3)
        self._ingredients_text.grid(row=2, column=1, columnspan=3, sticky=tk.EW, pady=3)
        self._ingredients_text.bind("<KeyRelease>", self._on_form_change)

        # Row 3 — Allergens (wide, with a picker) — U-007
        ttk.Label(form, text="Allergens").grid(row=3, column=0, sticky=tk.W, pady=3, padx=(0, 6))
        al_frame = ttk.Frame(form)
        al_frame.grid(row=3, column=1, columnspan=3, sticky=tk.EW, pady=3)
        self._allergens_var = tk.StringVar()
        self._allergens_var.trace_add("write", self._on_form_change)
        ttk.Entry(al_frame, textvariable=self._allergens_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(al_frame, text="Pick…", width=6,
                   command=self._open_allergen_picker).pack(side=tk.LEFT, padx=(4, 0))

        # Row 4 — Size | Price  (short fields, sized to content)
        ttk.Label(form, text="Size").grid(row=4, column=0, sticky=tk.W, pady=3, padx=(0, 6))
        self._size_var = tk.StringVar()
        self._size_var.trace_add("write", self._on_form_change)
        self._size_entry = ttk.Entry(form, textvariable=self._size_var, width=16)
        self._size_entry.grid(row=4, column=1, sticky=tk.W, pady=3)
        ttk.Label(form, text="Price ($)").grid(row=4, column=2, sticky=tk.W, pady=3, padx=(8, 6))
        self._price_var = tk.StringVar()
        self._price_var.trace_add("write", self._on_form_change)
        ttk.Entry(form, textvariable=self._price_var, width=10).grid(
            row=4, column=3, sticky=tk.W, pady=3)

        # Row 5 — Net Wt (U-008) | Category (U-013)
        ttk.Label(form, text="Net Wt").grid(row=5, column=0, sticky=tk.W, pady=3, padx=(0, 6))
        self._net_weight_var = tk.StringVar()
        self._net_weight_var.trace_add("write", self._on_form_change)
        ttk.Entry(form, textvariable=self._net_weight_var, width=16).grid(
            row=5, column=1, sticky=tk.W, pady=3)
        ttk.Label(form, text="Category").grid(row=5, column=2, sticky=tk.W, pady=3, padx=(8, 6))
        self._category_field_var = tk.StringVar(value=NO_CATEGORY)
        cat_combo = ttk.Combobox(form, textvariable=self._category_field_var,
                                 values=[NO_CATEGORY, *CATEGORIES], state="readonly", width=10)
        cat_combo.grid(row=5, column=3, sticky=tk.W, pady=3)
        _block_mousewheel(cat_combo)

        # Row 6 — Barcode # (+ Auto) | Date Mode  (short fields)
        ttk.Label(form, text="Barcode #").grid(row=6, column=0, sticky=tk.W, pady=3, padx=(0, 6))
        bc_frame = ttk.Frame(form)
        bc_frame.grid(row=6, column=1, sticky=tk.W, pady=3)
        self._barcode_var = tk.StringVar()
        self._barcode_var.trace_add("write", self._on_barcode_change)
        ttk.Entry(bc_frame, textvariable=self._barcode_var, width=10).pack(side=tk.LEFT)
        ttk.Button(bc_frame, text="Auto", width=5,
                   command=self._on_auto_barcode).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(form, text="Date Mode").grid(row=6, column=2, sticky=tk.W, pady=3, padx=(8, 6))
        self._date_mode_var = tk.StringVar(value="Best By")
        self._date_mode_var.trace_add("write", self._on_form_change)
        dm_combo = ttk.Combobox(form, textvariable=self._date_mode_var,
                                values=DATE_MODES, state="readonly", width=10)
        dm_combo.grid(row=6, column=3, sticky=tk.W, pady=3)
        _block_mousewheel(dm_combo)

        # Row 7 — Notes (wide)
        ttk.Label(form, text="Notes").grid(row=7, column=0, sticky=tk.W, pady=3, padx=(0, 6))
        self._notes_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._notes_var).grid(
            row=7, column=1, columnspan=3, sticky=tk.EW, pady=3)

        # Row 8 — Auto-capitalise toggle
        self._auto_caps_var = tk.BooleanVar(value=self.settings.get("auto_capitalize", True))
        ttk.Checkbutton(form, text="Auto-capitalise Name & Subtitle",
                        variable=self._auto_caps_var,
                        command=self._on_caps_toggle).grid(
            row=8, column=0, columnspan=4, sticky=tk.W, pady=(6, 2))

        # Status line (the same message is shown on the Print page)
        ttk.Label(parent, textvariable=self._status_var, style="Status.TLabel",
                  wraplength=CARD_WRAP).pack(anchor=tk.W, pady=(8, 0))

    # ── Quantity helpers ──────────────────────────────────────────────────────

    def _qty_plus(self):
        try:
            self._qty_var.set(str(min(999, int(self._qty_var.get()) + 1)))
        except ValueError:
            self._qty_var.set("1")

    def _qty_minus(self):
        try:
            self._qty_var.set(str(max(1, int(self._qty_var.get()) - 1)))
        except ValueError:
            self._qty_var.set("1")

    # ──────────────────────────────────────────────────────────────────────────
    # Product list
    # ──────────────────────────────────────────────────────────────────────────

    def _refresh_product_list(self, query: str = ""):
        self._tree.delete(*self._tree.get_children())
        self._tree_id_map.clear()

        codes = scanned_code_to_data6(query) if query else []
        products = (self.db.search_products(query, codes) if query else self.db.get_all_products())
        products = [p for p in products if self._category_predicate()(p)]
        products = self._sorted_products(products)
        # A scanned / typed barcode that matches exactly stays at the top
        products.sort(key=lambda p: p.get("barcode_number") not in codes)
        self._visible_products = products
        for p in products:
            bc_disp = p.get("barcode_number") or ""
            sz_disp = p.get("size") or ""
            pr_disp = "" if p.get("price") is None else f"{p['price']:.2f}"
            iid = self._tree.insert("", tk.END, values=(p["name"], bc_disp, sz_disp, pr_disp))
            self._tree_id_map[iid] = p["id"]

        count = len(products)
        self._count_var.set(f"{count} item{'s' if count != 1 else ''}")

        if self._current_id is not None:
            for iid, pid in self._tree_id_map.items():
                if pid == self._current_id:
                    self._tree.selection_set(iid)
                    self._tree.see(iid)
                    break

    def _on_search_change(self, *_):
        self._refresh_product_list(self._search_var.get().strip())

    # ── U-013 sorting ─────────────────────────────────────────────────────────

    def _sorted_products(self, products: list[dict]) -> list[dict]:
        col = self._sort_column
        if col == "barcode":
            key = lambda p: (not p.get("barcode_number"), p.get("barcode_number") or "")
        elif col == "size":
            key = lambda p: _size_sort_key(p.get("size") or "")
        elif col == "price":
            key = lambda p: (p.get("price") is None, p.get("price") or 0.0)
        else:
            key = lambda p: (p.get("name") or "").casefold()
        # Sort by name first so equal keys (e.g. same price) stay alphabetical
        products = sorted(products, key=lambda p: (p.get("name") or "").casefold())
        return sorted(products, key=key, reverse=self._sort_descending)

    def _on_sort_column(self, column: str):
        if column == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column, self._sort_descending = column, False
        self._update_sort_headings()
        self._refresh_product_list(self._search_var.get().strip())

    def _update_sort_headings(self):
        for key, heading, _w, _s in LIST_COLUMNS:
            arrow = (" ▼" if self._sort_descending else " ▲") if key == self._sort_column else ""
            self._tree.heading(key, text=heading + arrow)

    # ── helpers used by the tool windows ──────────────────────────────────────

    def visible_products(self) -> list[dict]:
        """Products currently shown in the list (after search, filter, sort)."""
        return list(self._visible_products)

    def category_names(self) -> list[str]:
        return [name for name, _pred in PRODUCT_CATEGORIES[1:]]

    def category_predicate(self, name: str):
        return dict(PRODUCT_CATEGORIES).get(name, PRODUCT_CATEGORIES[0][1])

    def refresh_products(self):
        """Re-read the list; reload the open product if it has no unsaved edits
        (so a price changed by a tool isn't overwritten by the old form value)."""
        self._refresh_product_list(self._search_var.get().strip())
        if self._current_id is not None and not self._is_dirty():
            product = self.db.get_product(self._current_id)
            if product:
                self._load_product(product)
            else:
                self._clear_form()

    def backup_now(self) -> str:
        return self.db.backup(os.path.join(self.app_dir, "backups"))

    def _focus_search(self, _e=None):
        self._search_entry.focus_set()
        self._search_entry.select_range(0, tk.END)
        self._search_entry.icursor(tk.END)
        return "break"

    def _select_product_in_tree(self, pid: int | None) -> bool:
        """Highlight *pid* in the list (loading happens via <<TreeviewSelect>>)."""
        for iid, tree_pid in self._tree_id_map.items():
            if tree_pid == pid:
                if self._tree.selection() != (iid,):
                    self._tree.selection_set(iid)
                self._tree.see(iid)
                return True
        return False

    def _on_search_enter(self, _e=None):
        """Enter in the search box.

        A scanned barcode opens that product and keeps the cursor in Search,
        ready for the next scan.  Typed text opens the first product in the
        list (or the highlighted one) and, on the Print screen, moves to
        Quantity so the next Enter prints (U-017)."""
        query = self._search_var.get().strip()
        codes = scanned_code_to_data6(query) if query else []
        if codes:
            matches = self.db.get_products_by_barcode(codes)
            if len(matches) == 1:
                target = matches[0]["id"]
                if target not in self._tree_id_map.values():
                    # Hidden by the "Show:" filter — show everything.
                    self._category_var.set(PRODUCT_CATEGORIES[0][0])
                    self._refresh_product_list(query)
                self._select_product_in_tree(target)
            else:
                self.root.bell()
                self._count_var.set(f"No product has barcode {query}")
            self._focus_search()
            return "break"
        if query.isdigit() and len(query) >= 6 and not self._tree_id_map:
            self.root.bell()
            self._count_var.set(f"No product has barcode {query}")
            self._focus_search()
            return "break"
        items = self._tree.get_children()
        if not items:
            self.root.bell()
            return "break"
        if not self._tree.selection():
            self._tree.selection_set(items[0])
            self._tree.see(items[0])
        self.root.update_idletasks()
        if self._mode == MODE_PRINT:
            # Let the selection load first, then move to Quantity
            self.root.after_idle(self._focus_quantity)
        return "break"

    def _on_filter_change(self, *_):
        """Category filter changed — re-apply it together with the search text."""
        self._refresh_product_list(self._search_var.get().strip())

    def _category_predicate(self):
        """Return the predicate function for the currently selected category."""
        label = self._category_var.get()
        for name, pred in PRODUCT_CATEGORIES:
            if name == label:
                return pred
        return PRODUCT_CATEGORIES[0][1]

    def _on_tree_select(self, event=None, force: bool = False):
        sel = self._tree.selection()
        if not sel:
            return
        pid = self._tree_id_map.get(sel[0])
        if pid is None:
            return
        # Refreshing the list (every search keystroke, after Save, etc.)
        # re-selects the product that is already loaded.  Reloading it from
        # the database then would throw away unsaved edits in the form and
        # wipe the status line, so skip it.  Double-click still reloads.
        if pid == self._current_id and not force:
            return
        doing = "reloading it" if pid == self._current_id else "opening another product"
        if not self._confirm_unsaved(doing):
            # Stay on the product being edited
            if not self._select_product_in_tree(self._current_id):
                self._tree.selection_remove(self._tree.selection())
            return
        product = self.db.get_product(pid)
        if product:
            self._load_product(product)
            # A "Save" above rebuilds the list, so highlight the new product again
            self._select_product_in_tree(pid)

    # ──────────────────────────────────────────────────────────────────────────
    # Product form logic
    # ──────────────────────────────────────────────────────────────────────────

    def _load_product(self, product: dict):
        self._current_id = product["id"]
        name = product.get("name") or ""
        self._name_var.set(name)
        self._subtitle_var.set(product.get("subtitle") or "")
        self._ingredients_text.delete("1.0", tk.END)
        self._ingredients_text.insert("1.0", product.get("ingredients") or "")
        self._size_var.set(product.get("size") or "")
        self._allergens_var.set(product.get("allergens") or "")
        self._net_weight_var.set(product.get("net_weight") or "")
        self._category_field_var.set(product.get("category") or NO_CATEGORY)
        price = product.get("price")
        self._price_var.set(f"{price:.2f}" if price is not None else "")
        self._barcode_var.set(product.get("barcode_number") or "")
        self._date_mode_var.set(product.get("date_mode") or "Best By")
        self._notes_var.set(product.get("notes") or "")
        self._status_var.set("")
        self._action_name_var.set(name or "(unnamed)")
        self._schedule_preview_update()
        self._take_clean_snapshot()

    def _clear_form(self):
        self._current_id = None
        for var in (self._name_var, self._subtitle_var, self._size_var,
                    self._price_var, self._barcode_var, self._notes_var,
                    self._allergens_var, self._net_weight_var):
            var.set("")
        self._category_field_var.set(NO_CATEGORY)
        self._ingredients_text.delete("1.0", tk.END)
        self._date_mode_var.set("Best By")
        self._status_var.set("")
        self._action_name_var.set("(none)")
        self._schedule_preview_update()
        self._take_clean_snapshot()

    # ── Unsaved-changes tracking ──────────────────────────────────────────────

    def _form_snapshot(self) -> dict:
        """The editable fields exactly as typed (whitespace-trimmed)."""
        return {
            "name":        self._name_var.get().strip(),
            "subtitle":    self._subtitle_var.get().strip(),
            "ingredients": " ".join(self._ingredients_text.get("1.0", "end-1c").split()),
            "allergens":   self._allergens_var.get().strip(),
            "net_weight":  self._net_weight_var.get().strip(),
            "category":    self._category_field_var.get(),
            "size":        self._size_var.get().strip(),
            "price":       self._price_var.get().strip(),
            "barcode":     self._barcode_var.get().strip(),
            "date_mode":   self._date_mode_var.get(),
            "notes":       self._notes_var.get().strip(),
        }

    def _take_clean_snapshot(self):
        self._clean_snapshot = self._form_snapshot()

    def _is_dirty(self) -> bool:
        return self._clean_snapshot is not None and self._form_snapshot() != self._clean_snapshot

    def _confirm_unsaved(self, doing: str) -> bool:
        """If the form has unsaved changes, ask what to do.  Returns True if the
        caller may go ahead (changes saved or discarded), False to stay."""
        if not self._is_dirty():
            return True
        name = self._name_var.get().strip() or "this new product"
        answer = messagebox.askyesnocancel(
            "Unsaved Changes",
            f"You have unsaved changes to {name}.\n\n"
            f"Save them before {doing}?\n\n"
            "Yes = save    No = throw them away    Cancel = go back",
            icon="warning",
        )
        if answer is None:
            return False
        if answer:
            return self._on_save()
        return True

    def _on_close(self):
        if self._confirm_unsaved("closing"):
            self.root.destroy()

    def _collect_form_data(self) -> dict:
        """Read all form fields and return a product dict."""
        price_str = self._price_var.get().strip().lstrip("$")
        try:
            price = float(price_str) if price_str else None
        except ValueError:
            price = None

        auto_caps = getattr(self, "_auto_caps_var", None)
        caps = auto_caps.get() if auto_caps is not None else True

        def _cap(text: str) -> str:
            return text.strip().upper() if caps else text.strip()

        # The ingredients box is multi-line for readability; store it as one
        # clean comma-separated line (collapse any newlines/extra spaces).
        ingredients = " ".join(self._ingredients_text.get("1.0", "end-1c").split())

        return {
            "id":             self._current_id,
            "name":           _cap(self._name_var.get()),
            "subtitle":       _cap(self._subtitle_var.get()),
            "ingredients":    ingredients,
            "allergens":      ", ".join(a.strip() for a in self._allergens_var.get().split(",")
                                        if a.strip()),
            "net_weight":     " ".join(self._net_weight_var.get().split()).upper(),
            "category":       "" if self._category_field_var.get() == NO_CATEGORY
                              else self._category_field_var.get(),
            "size":           self._size_var.get().strip().upper(),
            "price":          price,
            "barcode_number": self._barcode_var.get().strip(),
            "date_mode":      self._date_mode_var.get(),
            "notes":          self._notes_var.get().strip(),
        }

    def _validate_form(self, data: dict) -> tuple[bool, str]:
        """Return (valid, error_message)."""
        if not data["name"]:
            return False, "Product name is required."
        ok, msg = validate_barcode_input(data["barcode_number"])
        if not ok:
            return False, msg
        # A mistyped price (e.g. "4,99") used to be saved silently as "no
        # price", erasing the existing one.  Refuse it instead.
        raw_price = self._price_var.get().strip().lstrip("$").strip()
        if raw_price:
            try:
                price_ok = math.isfinite(float(raw_price))
            except ValueError:
                price_ok = False
            if not price_ok:
                return False, "Price must be a number, e.g. 4.99 (or leave it blank)."
        return True, ""

    # ──────────────────────────────────────────────────────────────────────────
    # CRUD actions
    # ──────────────────────────────────────────────────────────────────────────

    def _on_new(self):
        if not self._set_mode(MODE_EDIT):
            return
        if not self._confirm_unsaved("starting a new product"):
            return
        self._clear_form()
        self._tree.selection_remove(self._tree.selection())
        # Auto-assign the next available barcode number so it's ready to save
        self._on_auto_barcode()
        self._take_clean_snapshot()

    def _on_save(self) -> bool:
        """Save the form.  Returns True if the product was saved."""
        data = self._collect_form_data()
        valid, err = self._validate_form(data)
        if not valid:
            self._status_var.set(f"⚠ {err}")
            return False

        if data["barcode_number"]:
            data["barcode_number"] = pad_barcode(data["barcode_number"])

        if data["barcode_number"]:
            conflict = self.db.get_barcode_conflict(
                data["barcode_number"], exclude_id=self._current_id
            )
            if conflict:
                where = "  (in the Trash)" if conflict.get("deleted_at") else ""
                answer = messagebox.askyesno(
                    "Duplicate Barcode",
                    f"Barcode {data['barcode_number']} is already used by:\n\n"
                    f"  {conflict['name']}{where}\n\n"
                    "Save anyway?",
                    icon="warning",
                )
                if not answer:
                    return False

        # U-013: a new product saved without a category gets a best guess
        suggested = ""
        if self._current_id is None and not data["category"]:
            suggested = suggest_category(data["name"], data["size"], data["date_mode"])
            data["category"] = suggested

        try:
            new_id = self.db.save_product(data)
            self._current_id = new_id
            self._refresh_product_list(self._search_var.get().strip())
            # Show the saved values exactly as stored (padded barcode,
            # capitalised name, 2-decimal price).
            saved = self.db.get_product(new_id)
            if saved:
                self._load_product(saved)
            self._status_var.set(f"✓ Saved.  Category set to {suggested} — change it if that's wrong."
                                 if suggested else "✓ Saved.")
            self._action_name_var.set(data["name"] or "(unnamed)")
            return True
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
            return False

    def _on_delete(self):
        if self._current_id is None:
            messagebox.showinfo("Delete", "No product is selected.")
            return
        if not self.lock.require(self.root, "Deleting a product"):
            return
        name = self._name_var.get() or "(unnamed)"
        if not messagebox.askyesno("Confirm Delete",
                                   f"Move this product to the Trash?\n\n  {name}\n\n"
                                   "You can restore it from File → Trash.",
                                   icon="warning"):
            return
        self.db.delete_product(self._current_id)
        self._clear_form()
        self._refresh_product_list(self._search_var.get().strip())
        self._status_var.set(f"Moved {name} to the Trash (File → Trash to restore).")

    def _on_duplicate(self):
        """U-010: start a new product copied from the open one, with a fresh
        barcode and a blank Size, for adding another package size."""
        if self._current_id is None:
            messagebox.showinfo("Duplicate",
                                "Open a saved product first, then click Duplicate to make "
                                "a copy of it for another size.")
            return
        if not self._set_mode(MODE_EDIT):
            return
        if not self._confirm_unsaved("making a copy"):
            return
        source = self.db.get_product(self._current_id)
        if not source:
            return
        self._clear_form()
        self._tree.selection_remove(self._tree.selection())
        self._name_var.set(source["name"])
        self._subtitle_var.set(source.get("subtitle") or "")
        self._ingredients_text.insert("1.0", source.get("ingredients") or "")
        self._allergens_var.set(source.get("allergens") or "")
        self._category_field_var.set(source.get("category") or NO_CATEGORY)
        price = source.get("price")
        self._price_var.set(f"{price:.2f}" if price is not None else "")
        self._date_mode_var.set(source.get("date_mode") or "Best By")
        self._on_auto_barcode()
        # The form is deliberately left "unsaved" so leaving it asks first.
        self._action_name_var.set(f"{source['name']} (new copy)")
        self._status_var.set(f"Copy of {source['name']} {source.get('size') or ''}".rstrip()
                             + " — type the new Size (and Price / Net Wt), then Save.  "
                             "It has a new barcode number.")
        self._size_entry.focus_set()

    def _on_auto_barcode(self):
        """Fill the Barcode # field with the next unused auto-generated number."""
        start = int(self.settings.get("barcode_auto_start", 100000))
        next_bc = self.db.get_next_barcode(start)
        self._barcode_var.set(next_bc)
        self._status_var.set(f"Auto-assigned barcode {next_bc}")

    def _on_barcode_change(self, *_):
        """Validate the barcode field live and show feedback; then update preview."""
        raw = self._barcode_var.get().strip()
        if raw:
            ok, msg = validate_barcode_input(raw)
            if not ok:
                self._status_var.set(f"⚠ Barcode: {msg}")
            else:
                current = self._status_var.get()
                if current.startswith("⚠ Barcode:"):
                    self._status_var.set("")
        self._schedule_preview_update()

    def _on_caps_toggle(self):
        """Persist the auto-capitalise toggle setting immediately."""
        self.settings.set("auto_capitalize", self._auto_caps_var.get())
        self.settings.save()
        self._schedule_preview_update()

    def _get_margin(self) -> float:
        """Side margin in inches (Settings → Settings…)."""
        try:
            return float(self.settings.get("label_margin_in", 0.08))
        except (TypeError, ValueError):
            return 0.08

    # ──────────────────────────────────────────────────────────────────────────
    # Print actions
    # ──────────────────────────────────────────────────────────────────────────

    def _build_show_flags(self) -> dict:
        return {
            "barcode":     self._show_barcode_var.get(),
            "price":       self._show_price_var.get(),
            "dollar_sign": self._show_dollar_var.get(),
            "date":        self._show_date_var.get(),
            "address":     self._show_address_var.get(),
        }

    def _parse_print_date(self) -> date | None:
        """The Print Date field as a date, or None if it isn't a valid M/D/YYYY."""
        try:
            return datetime.strptime(self._print_date_var.get().strip(), "%m/%d/%Y").date()
        except ValueError:
            return None

    def _get_pack_date(self) -> date:
        return self._parse_print_date() or date.today()

    def _roll_print_date(self):
        """Advance the Print Date to today if it is still showing the day it was
        automatically set to (i.e. nobody picked a different date on purpose),
        so leaving the program open overnight never prints yesterday's date."""
        today   = date.today()
        current = self._parse_print_date()
        if current == self._auto_print_date and current != today:
            self._print_date_var.set(self._today_str())
            current = today
        if current == today:
            self._auto_print_date = today

    def _schedule_date_rollover(self):
        self._roll_print_date()
        self.root.after(60_000, self._schedule_date_rollover)

    def _check_print_inputs(self, title: str, label_type: str,
                            show_date: bool, show_barcode: bool) -> bool:
        """Refuse to print when a typo would silently change the label: a Print
        Date that isn't a real date, or a Barcode # that can't be encoded."""
        if label_type == "Ingredient":
            return True
        if (show_date and self._date_mode_var.get() != "None"
                and self._parse_print_date() is None):
            messagebox.showwarning(
                title,
                f"The Print Date \u201c{self._print_date_var.get().strip()}\u201d "
                "is not a valid date.\n\n"
                "Type it as month/day/year, e.g. "
                f"{self._today_str()}, or pick it from the calendar.",
            )
            return False
        raw_bc = self._barcode_var.get().strip()
        if show_barcode and raw_bc:
            ok, msg = validate_barcode_input(raw_bc)
            if not ok:
                messagebox.showwarning(
                    title,
                    f"The Barcode # \u201c{raw_bc}\u201d is not valid:\n{msg}\n\n"
                    "Fix it before printing, otherwise the label would print "
                    "without a barcode.",
                )
                return False
        return True

    def _get_spacing(self) -> float:
        """Label spacing (Settings → Settings…)."""
        try:
            return float(self.settings.get("label_spacing", 1.0))
        except (TypeError, ValueError):
            return 1.0

    def _resolve_label_size(self, label_type: str) -> str:
        """Combined labels are always 2.25x3.00.  Barcode/Ingredient labels use
        the global default label size set in Settings."""
        if label_type == "Combined":
            return "2.25x3.00"
        return self.settings.default_label_size or "2.25x1.25"

    def _resolve_printer(self, title: str) -> str | None:
        printer = self.settings.default_printer or get_default_printer()
        if not printer:
            messagebox.showwarning(
                title,
                "No printer is set.\n\n"
                "Open  Settings → Settings…  and choose the default printer.",
            )
            return None
        return printer

    def _print_dpi(self, printer: str) -> int | None:
        """The printer's native DPI if labels should be rendered at it, else None."""
        if not self.settings.get("print_at_printer_dpi", True):
            return None
        if printer not in self._printer_dpi_cache:
            dpi = get_printer_dpi(printer)
            ok = dpi is not None and dpi[0] == dpi[1] and 150 <= dpi[0] <= 1200
            self._printer_dpi_cache[printer] = dpi[0] if ok else None
        return self._printer_dpi_cache[printer]

    def _print_product(self, product: dict, label_type: str, show_flags: dict,
                       printer: str, copies: int, label_size: str | None = None,
                       source: str = "Print"):
        """Render *product* for *printer*, send *copies* of it, and record the
        job in Print History (U-009)."""
        size = label_size or self._resolve_label_size(label_type)
        native_dpi = self._print_dpi(printer)
        img = render_label(
            product       = product,
            label_type    = label_type,
            label_size    = size,
            pack_date     = self._get_pack_date(),
            show_flags    = show_flags,
            font_settings = self.settings._data,
            address_line  = self.settings.address_line,
            bestby_offset = self.settings.bestby_offset_days,
            dpi           = native_dpi or LEGACY_PRINT_DPI,
            gap_scale     = self._get_spacing(),
            margin_in     = self._get_margin(),
            min_module_in = NATIVE_MIN_MODULE_IN if native_dpi else None,
        )
        if native_dpi:
            img = to_monochrome(img)
        print_labels(img, printer, size, copies=copies)
        self._log_print(product, label_type, size, show_flags, printer, copies, source)

    def _log_print(self, product, label_type, label_size, show_flags, printer, copies, source):
        date_line = ""
        if label_type != "Ingredient" and show_flags.get("date", True):
            date_line = format_date_line(product.get("date_mode") or "Packed",
                                         self._get_pack_date(),
                                         self.settings.bestby_offset_days) or ""
        try:
            self.db.log_print({
                "product_id": product.get("id"), "product_name": product.get("name"),
                "size": product.get("size"), "barcode_number": product.get("barcode_number"),
                "price": product.get("price"), "label_type": label_type,
                "label_size": label_size, "copies": copies,
                "print_date": self.print_date_text(), "date_line": date_line,
                "printer": printer, "source": source,
            })
        except Exception:
            # The labels already printed; a history hiccup must not report a failure.
            pass

    def _print_label_type(self, label_type: str):
        """Print the selected product as *label_type* (Barcode/Ingredient/Combined)."""
        if not self._name_var.get().strip():
            messagebox.showwarning("Print", "No product loaded.  Select a product first.")
            return

        self._roll_print_date()
        flags = self._build_show_flags()
        if not self._check_print_inputs("Print", label_type,
                                        flags["date"], flags["barcode"]):
            return

        printer = self._resolve_printer("Print")
        if not printer:
            return

        try:
            qty = max(1, int(self._qty_var.get()))
        except ValueError:
            qty = 1

        # Keep the preview in sync with what we're about to print
        if label_type != self._preview_type_var.get():
            self._preview_type_var.set(label_type)
        self._schedule_preview_update()

        try:
            self._print_product(self._collect_form_data(), label_type, flags, printer, qty)
        except RuntimeError as e:
            messagebox.showerror("Print Error", str(e))
        except Exception as e:
            messagebox.showerror("Print Error", f"Unexpected error: {e}")

    def _on_test_print(self):
        """Print a single barcode-only label on 2.25×1.25 stock for POS verification."""
        if not self._name_var.get().strip():
            messagebox.showwarning("Test Print", "No product loaded.")
            return
        self._roll_print_date()
        if not self._check_print_inputs("Test Print", "Barcode",
                                        show_date=True, show_barcode=True):
            return
        printer = self._resolve_printer("Test Print")
        if not printer:
            return
        all_on = {"barcode": True, "price": True, "dollar_sign": True,
                  "date": True, "address": True}
        try:
            self._print_product(self._collect_form_data(), "Barcode", all_on, printer, 1,
                                label_size="2.25x1.25", source="Test Print")
            messagebox.showinfo("Test Print",
                                "Test label sent to printer.\n"
                                "Scan it at the POS to verify it reads correctly.")
        except RuntimeError as e:
            messagebox.showerror("Test Print Error", str(e))
        except Exception as e:
            messagebox.showerror("Test Print Error", f"Unexpected error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Print queue
    # ──────────────────────────────────────────────────────────────────────────

    def print_date_text(self) -> str:
        return self._print_date_var.get().strip()

    def on_print_queue_changed(self):
        n = len(self.print_queue.items)
        self._queue_btn.config(text=f"Print Queue ({n})")

    def _open_single(self, attr: str, window_cls):
        """Open a tool window, or bring the existing one to the front."""
        win = getattr(self, attr, None)
        if win is not None and win.winfo_exists():
            if hasattr(win, "refresh"):
                win.refresh()
            win.deiconify()
            win.lift()
            win.focus_set()
            return win
        win = window_cls(self)
        setattr(self, attr, win)
        return win

    def _open_print_history(self):
        self._open_single("_history_window", PrintHistoryWindow)

    def _open_trash(self):
        self._open_single("_trash_window", TrashWindow)

    def _open_price_tools(self):
        if not self.lock.require(self.root, "Changing prices"):
            return
        self._open_single("_price_window", PriceChangeDialog)

    def _open_allergen_picker(self):
        AllergenPicker(self.root, self._allergens_var.get(), self._allergens_var.set)

    def _on_export_price_list(self):
        path = filedialog.asksaveasfilename(
            title="Export Price List", defaultextension=".csv",
            initialfile=f"aaojee_price_list_{date.today():%Y%m%d}.csv",
            filetypes=[("Spreadsheet (CSV)", "*.csv")])
        if not path:
            return
        try:
            products = self.db.get_all_products()
            export_price_list(path, products)
            messagebox.showinfo("Export Price List", f"Saved {len(products)} products to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Price List", str(e))

    def _open_print_queue(self):
        if self._queue_window is not None and self._queue_window.winfo_exists():
            self._queue_window.refresh()
            self._queue_window.deiconify()
            self._queue_window.lift()
            self._queue_window.focus_set()
            return
        self._queue_window = PrintQueueWindow(self)

    def _on_add_to_queue(self):
        if self._current_id is None:
            if self._name_var.get().strip():
                messagebox.showinfo("Print Queue",
                                    "Save this new product before adding it to the print queue.")
            else:
                messagebox.showwarning("Print Queue", "Select a product first.")
            return
        if self._is_dirty():
            answer = messagebox.askyesnocancel(
                "Print Queue",
                "This product has unsaved changes.  The print queue prints the "
                "saved version.\n\nSave the changes first?")
            if answer is None:
                return
            if answer and not self._on_save():
                return
        product = self.db.get_product(self._current_id)
        if not product:
            return
        try:
            qty = max(1, int(self._qty_var.get()))
        except ValueError:
            qty = 1
        choice = default_choice(product)
        item = self.print_queue.add(product["id"], choice, qty)
        self._status_var.set(
            f"✓ Added {product['name']} ({choice}) — now {item['qty']} in the print queue.")
        self.on_print_queue_changed()
        if self._queue_window is not None and self._queue_window.winfo_exists():
            self._queue_window.refresh()

    def print_queue_items(self, window) -> list[int]:
        """Print everything in the queue.  Returns the indexes fully printed."""
        items = self.print_queue.items
        if not items:
            return []
        self._roll_print_date()
        flags = self._build_show_flags()

        jobs: list[tuple[int, dict, list[str], int]] = []
        notes: list[str] = []
        for i, it in enumerate(items):
            product = self.db.get_product(it["product_id"])
            if not product:
                notes.append("A deleted product was skipped.")
                continue
            types = []
            for lt in LABEL_CHOICES[it["label"]]:
                if (lt == "Ingredient" and not (product.get("ingredients") or "").strip()
                        and not info_lines(product)):
                    notes.append(f"{product['name']}: has no ingredients, "
                                 "so its ingredient label is skipped.")
                    continue
                types.append(lt)
            if types:
                jobs.append((i, product, types, it["qty"]))
        if not jobs:
            messagebox.showwarning("Print Queue", "Nothing to print.\n\n" + "\n".join(notes),
                                   parent=window)
            return []

        # Same safety checks as single printing
        needs_date = flags["date"] and any(
            p.get("date_mode") != "None" and any(t != "Ingredient" for t in types)
            for _, p, types, _ in jobs)
        if needs_date and self._parse_print_date() is None:
            messagebox.showwarning(
                "Print Queue",
                f"The Print Date \u201c{self.print_date_text()}\u201d on the main window "
                "is not a valid date.\n\nType it as month/day/year, e.g. "
                f"{self._today_str()}.", parent=window)
            return []
        if flags["barcode"]:
            bad = [p["name"] for _, p, types, _ in jobs
                   if any(t != "Ingredient" for t in types)
                   and p.get("barcode_number")
                   and not validate_barcode_input(p["barcode_number"])[0]]
            if bad:
                messagebox.showwarning(
                    "Print Queue",
                    "These products have an invalid Barcode # and would print "
                    "without a barcode:\n\n" + "\n".join(bad), parent=window)
                return []

        printer = self._resolve_printer("Print Queue")
        if not printer:
            return []

        total = sum(qty * len(types) for _, _, types, qty in jobs)
        summary = (f"Print {total} label{'s' if total != 1 else ''} for "
                   f"{len(jobs)} product{'s' if len(jobs) != 1 else ''}?\n\n"
                   f"Printer:  {printer}\nPrint date:  {self.print_date_text()}")
        if notes:
            summary += "\n\nNote:\n" + "\n".join(notes)
        if not messagebox.askyesno("Print Queue", summary, parent=window):
            return []

        printed: list[int] = []
        for n, (i, product, types, qty) in enumerate(jobs, start=1):
            window.set_status(f"Printing {n} of {len(jobs)}: {product['name']}…")
            try:
                for lt in types:
                    self._print_product(product, lt, flags, printer, qty, source="Queue")
            except Exception as e:
                done = ", ".join(p["name"] for j, p, _, _ in jobs if j in printed) or "nothing"
                window.set_status(f"Stopped at {product['name']}.")
                messagebox.showerror(
                    "Print Queue",
                    f"Printing stopped at {product['name']}:\n{e}\n\n"
                    f"Already sent: {done}.\n"
                    "This item and everything after it were not fully printed.",
                    parent=window)
                return printed
            printed.append(i)
        window.set_status(f"✓ Sent {total} labels for {len(jobs)} products to {printer}.")
        return printed

    # ──────────────────────────────────────────────────────────────────────────
    # Live preview
    # ──────────────────────────────────────────────────────────────────────────

    def _on_form_change(self, *_):
        if self._mode == MODE_EDIT:
            self.lock.touch()
        self._schedule_preview_update()

    def _schedule_preview_update(self, *_):
        """Debounce preview renders to avoid hammering during fast typing."""
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(200, self._update_preview)

    def _hide_preview_tiles(self):
        for v in ("Barcode", "Ingredient", "Combined"):
            tile = self._preview_tiles[v]
            tile["frame"].pack_forget()
            tile["caption"].pack_forget()

    def _render_into_tile(self, value, product, tile_max_w, max_h=None):
        """Render *value* (Barcode/Ingredient/Combined) into its tile."""
        tile = self._preview_tiles[value]
        try:
            img = render_label(
                product       = product,
                label_type    = value,
                label_size    = self._resolve_label_size(value),
                pack_date     = self._get_pack_date(),
                show_flags    = self._build_show_flags(),
                font_settings = self.settings._data,
                address_line  = self.settings.address_line,
                bestby_offset = self.settings.bestby_offset_days,
                dpi           = PREVIEW_DPI,
                gap_scale     = self._get_spacing(),
                margin_in     = self._get_margin(),
            )
        except Exception as e:
            tile["canvas"].config(width=tile_max_w, height=60)
            tile["canvas"].delete("all")
            tile["canvas"].create_text(
                tile_max_w // 2, 30, text=f"Preview error:\n{e}",
                fill="red", width=tile_max_w - 10, justify=tk.CENTER)
            tile["image"] = None
            return
        img_w, img_h = img.size
        scale = tile_max_w / img_w
        if max_h:
            scale = min(scale, max_h / img_h)
        disp_w = max(1, round(img_w * scale))
        disp_h = max(1, round(img_h * scale))
        img = img.resize((disp_w, disp_h), Image.LANCZOS)
        tile["image"] = ImageTk.PhotoImage(img)
        tile["canvas"].config(width=disp_w, height=disp_h)
        tile["canvas"].delete("all")
        tile["canvas"].create_image(0, 0, anchor=tk.NW, image=tile["image"])

    def _update_preview(self):
        self._preview_job = None
        data = self._collect_form_data()
        self._update_card(data)

        # No product loaded — show the placeholder, hide all tiles
        if not data["name"]:
            self._hide_preview_tiles()
            if not self._preview_placeholder.winfo_manager():
                self._preview_placeholder.pack(anchor=tk.W, pady=4)
            return
        self._preview_placeholder.pack_forget()

        mode = self._preview_type_var.get()
        max_w, max_h = self._preview_limits()
        if mode == "All":
            active     = ["Barcode", "Ingredient", "Combined"]
            tile_max_w = max(PREVIEW_MIN_W - 60, round(max_w * PREVIEW_STACKED_RATIO))
            show_caps  = True
            max_h      = None                   # stacked tiles scroll instead
        else:
            active     = [mode if mode in ("Barcode", "Ingredient", "Combined") else "Barcode"]
            tile_max_w = max_w
            show_caps  = False

        # Re-pack tiles in fixed Barcode → Ingredient → Combined order
        self._hide_preview_tiles()
        for v in active:
            tile = self._preview_tiles[v]
            tile["frame"].pack(anchor=tk.W, pady=(0, 6))
            if show_caps:
                tile["caption"].pack(anchor=tk.W, before=tile["border"])
            self._render_into_tile(v, data, tile_max_w, max_h=max_h)

    def _on_date_change(self, *_):
        self._schedule_preview_update()

    # ──────────────────────────────────────────────────────────────────────────
    # Calendar picker
    # ──────────────────────────────────────────────────────────────────────────

    def _open_calendar(self):
        """Open the mini calendar picker for the Print Date field.
        The date can still be typed directly into the entry."""
        try:
            current = datetime.strptime(
                self._print_date_var.get().strip(), "%m/%d/%Y").date()
        except ValueError:
            current = date.today()

        def on_pick(d: date):
            self._print_date_var.set(f"{d.month}/{d.day}/{d.year}")

        popup = CalendarPopup(self.root, current, on_pick)
        # Position the popup just below the date entry
        try:
            self.root.update_idletasks()
            x = self._date_entry.winfo_rootx()
            y = self._date_entry.winfo_rooty() + self._date_entry.winfo_height() + 2
            popup.geometry(f"+{x}+{y}")
        except Exception:
            pass

    @staticmethod
    def _today_str() -> str:
        d = date.today()
        return f"{d.month}/{d.day}/{d.year}"

    # ──────────────────────────────────────────────────────────────────────────
    # Settings / fonts
    # ──────────────────────────────────────────────────────────────────────────

    def _open_settings(self):
        if not self.lock.require(self.root, "Opening Settings"):
            return
        SettingsDialog(self.root, self.settings, self._printers, self._on_settings_saved)

    def _on_settings_saved(self):
        self.settings.save()
        self._printer_dpi_cache.clear()
        self._apply_combined_visibility()
        self._schedule_preview_update()

    def _open_font_settings(self):
        if not self.lock.require(self.root, "Opening Font Settings"):
            return
        FontSettingsDialog(self.root, self.settings, self._on_settings_saved)

    # ── Manager PIN ───────────────────────────────────────────────────────────

    def _on_set_pin(self):
        self.lock.set_pin_interactive(self.root)
        self._refresh_lock_ui()

    def _on_remove_pin(self):
        self.lock.remove_pin_interactive(self.root)
        self._refresh_lock_ui()

    def _on_lock_now(self):
        self.lock.lock()
        self._refresh_lock_ui()

    def _refresh_lock_ui(self):
        """Show the manager-PIN state in the mode bar, and leave the Edit screen
        once the PIN session has timed out (if nothing is unsaved)."""
        if not self.lock.enabled:
            self._lock_var.set("")
            self._lock_btn.pack_forget()
            return
        unlocked = self.lock.is_unlocked()
        if (not unlocked and self._mode == MODE_EDIT and not self._is_dirty()):
            self._set_mode(MODE_PRINT)
        self._lock_var.set("🔓 Manager unlocked" if unlocked else "🔒 Locked")
        if unlocked:
            if not self._lock_btn.winfo_manager():
                self._lock_btn.pack(side=tk.RIGHT, before=self._lock_label, padx=(0, 4))
        else:
            self._lock_btn.pack_forget()

    def _schedule_lock_refresh(self):
        self._refresh_lock_ui()
        self.root.after(5_000, self._schedule_lock_refresh)

    def _reset_fonts(self):
        if not self.lock.require(self.root, "Resetting the layout"):
            return
        if messagebox.askyesno("Reset Layout",
                               "Reset all font settings to the built-in defaults?"):
            self.settings.reset_fonts_to_defaults()
            self.settings.save()
            self._schedule_preview_update()

    # ──────────────────────────────────────────────────────────────────────────
    # Backup / export / restore
    # ──────────────────────────────────────────────────────────────────────────

    def _on_export(self):
        dest = filedialog.asksaveasfilename(
            title="Export / Backup Database",
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
            initialfile="aaojee_products_backup.db",
        )
        if not dest:
            return
        try:
            self.db.export_to(dest)
            messagebox.showinfo("Export", f"Database backed up to:\n{dest}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _on_restore(self):
        if not self.lock.require(self.root, "Restoring a backup"):
            return
        if not self._confirm_unsaved("restoring a backup"):
            return
        src = filedialog.askopenfilename(
            title="Restore from Backup",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
        )
        if not src:
            return
        if not messagebox.askyesno("Restore",
                                   f"This will REPLACE the current database with:\n{src}\n\n"
                                   "The current data will be lost (a backup of it is saved to "
                                   "the backups folder first). "
                                   "Continue?",
                                   icon="warning"):
            return
        try:
            # Snapshot the current data so a restore can always be undone,
            # including edits made since the startup backup.
            self.db.backup(os.path.join(self.app_dir, "backups"))
            self.db.restore_from(src)
            messagebox.showinfo("Restore", "Database restored.  Reloading product list.")
            self._clear_form()
            self._refresh_product_list(self._search_var.get().strip())
        except Exception as e:
            messagebox.showerror("Restore Error", str(e))

    # ──────────────────────────────────────────────────────────────────────────
    # MDB Importer
    # ──────────────────────────────────────────────────────────────────────────

    def _on_import_mdb(self):
        if not self.lock.require(self.root, "Importing from the old database"):
            return
        ok, reason = mdb_importer.is_available()
        if not ok:
            messagebox.showwarning("Import — Unavailable", reason)
            return

        src = filedialog.askopenfilename(
            title="Select old labeldata.mdb file",
            filetypes=[("Access Database", "*.mdb *.accdb"), ("All files", "*.*")],
        )
        if not src:
            return

        try:
            self.db.backup(os.path.join(self.app_dir, "backups"))
        except Exception as e:
            messagebox.showerror("Import", "Could not back up the database first, "
                                           f"so nothing was imported:\n{e}")
            return

        result = mdb_importer.import_from_mdb(src, self.db)

        summary = (
            f"Import complete.\n\n"
            f"  Imported : {result['imported']}\n"
            f"  Skipped  : {result['skipped']}  (barcode already exists)\n"
            f"  Errors   : {result['errors']}\n"
        )
        if result.get("table_used"):
            summary += f"\nTable read: {result['table_used']}"
        if result.get("columns_missing"):
            summary += (
                f"\n\nNote: these columns were not found and will be blank:\n"
                + ", ".join(result["columns_missing"])
            )
        if result.get("error_msgs"):
            summary += "\n\nErrors:\n" + "\n".join(result["error_msgs"][:5])

        messagebox.showinfo("Import Results", summary)
        self._refresh_product_list(self._search_var.get().strip())

    # ──────────────────────────────────────────────────────────────────────────
    # Misc
    # ──────────────────────────────────────────────────────────────────────────

    def _run_barcode_test(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = run_self_test()
        output = buf.getvalue()
        title = "Barcode Self-Test — ALL PASSED ✓" if ok else "Barcode Self-Test — FAILURES ✗"
        messagebox.showinfo(title, output)

    def _show_about(self):
        messagebox.showinfo(
            "About Aaojee Label Maker",
            "Aaojee Label Maker\n\n"
            "A free, self-contained label printing program\n"
            "for Aaojee, Middletown NY.\n\n"
            "Built in Python + tkinter.  Source included.\n"
            "Free to rebuild on any Windows PC.",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Settings dialog
# ──────────────────────────────────────────────────────────────────────────────

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, settings: Settings, printers: list[str], on_save):
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.grab_set()
        self._settings = settings
        self._on_save  = on_save

        pad = dict(padx=10, pady=5)
        f   = ttk.Frame(self, padding=12)
        f.pack()
        f.columnconfigure(1, weight=1)

        def lbl(row, text):
            ttk.Label(f, text=text).grid(row=row, column=0, sticky=tk.W, **pad)

        # Address
        lbl(0, "Business address line:")
        self._addr_var = tk.StringVar(value=settings.address_line)
        ttk.Entry(f, textvariable=self._addr_var, width=44).grid(
            row=0, column=1, **pad, sticky=tk.EW)

        # Default printer — global, used for all printing
        lbl(1, "Default printer:")
        self._printer_var = tk.StringVar(value=settings.default_printer)
        printer_combo = ttk.Combobox(f, textvariable=self._printer_var,
                                     values=printers, width=38)
        printer_combo.grid(row=1, column=1, **pad, sticky=tk.EW)
        _block_mousewheel(printer_combo)

        # Default label size — global (combined is always 2.25x3.00)
        lbl(2, "Label size:")
        self._size_var = tk.StringVar(value=settings.default_label_size)
        size_combo = ttk.Combobox(f, textvariable=self._size_var, values=LABEL_SIZES,
                                  state="readonly", width=18)
        size_combo.grid(row=2, column=1, **pad, sticky=tk.W)
        _block_mousewheel(size_combo)
        ttk.Label(f, text="Applies to Barcode & Ingredient labels.  "
                          "Combined labels always print at 2.25×3.00.",
                  foreground="gray").grid(row=3, column=1, sticky=tk.W, padx=10)

        # Best-By date offset — editable, with + / − buttons
        lbl(4, "Best-By date offset:")
        offset_frame = ttk.Frame(f)
        offset_frame.grid(row=4, column=1, **pad, sticky=tk.W)
        self._offset_var = tk.StringVar(value=str(settings.bestby_offset_days))
        ttk.Button(offset_frame, text="−", width=3,
                   command=lambda: self._offset_delta(-1)).pack(side=tk.LEFT)
        ttk.Entry(offset_frame, textvariable=self._offset_var, width=6,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=4)
        ttk.Button(offset_frame, text="+", width=3,
                   command=lambda: self._offset_delta(1)).pack(side=tk.LEFT)
        ttk.Label(offset_frame, text="days  (Best By = print date + this many days)",
                  foreground="gray").pack(side=tk.LEFT, padx=(8, 0))

        # Show/hide defaults
        lbl(5, "Show on labels by default:")
        chk_frame = ttk.Frame(f)
        chk_frame.grid(row=5, column=1, **pad, sticky=tk.W)
        self._show_bc_var = tk.BooleanVar(value=settings.show_barcode)
        self._show_pr_var = tk.BooleanVar(value=settings.show_price)
        self._show_ds_var = tk.BooleanVar(value=settings.show_dollar_sign)
        self._show_dt_var = tk.BooleanVar(value=settings.show_date)
        self._show_ad_var = tk.BooleanVar(value=settings.show_address)
        ttk.Checkbutton(chk_frame, text="Barcode", variable=self._show_bc_var).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(chk_frame, text="Price",   variable=self._show_pr_var).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(chk_frame, text="$ Sign",  variable=self._show_ds_var).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(chk_frame, text="Date",    variable=self._show_dt_var).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(chk_frame, text="Address", variable=self._show_ad_var).pack(side=tk.LEFT, padx=4)

        # Show the Combined print button
        self._combined_var = tk.BooleanVar(
            value=bool(settings.get("show_combined_button", False)))
        ttk.Checkbutton(
            f, text='Show the "Print Combined Label" button on the main screen',
            variable=self._combined_var).grid(row=6, column=0, columnspan=2,
                                              sticky=tk.W, padx=10, pady=(8, 4))

        # Default preview shown on launch — the main-screen radios remain a
        # session-level override.
        lbl(7, "Default preview:")
        current_pv = settings.get("default_preview", "Barcode")
        if current_pv not in PREVIEW_MODE_LABELS:
            current_pv = "Barcode"
        self._preview_mode_var = tk.StringVar(value=PREVIEW_MODE_LABELS[current_pv])
        preview_combo = ttk.Combobox(
            f, textvariable=self._preview_mode_var,
            values=list(PREVIEW_MODE_LABELS.values()),
            state="readonly", width=22)
        preview_combo.grid(row=7, column=1, **pad, sticky=tk.W)
        _block_mousewheel(preview_combo)

        # Render at the printer's own resolution (sharper barcodes)
        self._native_dpi_var = tk.BooleanVar(
            value=bool(settings.get("print_at_printer_dpi", True)))
        ttk.Checkbutton(
            f, text="Print at the printer's own resolution (sharper barcodes).  "
                    "Untick only if labels print wrongly.",
            variable=self._native_dpi_var).grid(row=8, column=0, columnspan=2,
                                                sticky=tk.W, padx=10, pady=(4, 4))

        # Label layout fine-tuning (moved here from the main screen, U-014)
        lbl(9, "Label spacing:")
        layout = ttk.Frame(f)
        layout.grid(row=9, column=1, **pad, sticky=tk.W)
        self._spacing_var = tk.StringVar(value=f"{float(settings.get('label_spacing', 1.0)):.2f}")
        spacing = ttk.Spinbox(layout, textvariable=self._spacing_var, from_=0.5, to=3.0,
                              increment=0.25, width=6, format="%.2f")
        spacing.pack(side=tk.LEFT)
        _block_mousewheel(spacing)
        ttk.Label(layout, text="   Side margin:").pack(side=tk.LEFT)
        self._margin_var = tk.StringVar(value=f"{float(settings.get('label_margin_in', 0.08)):.2f}")
        margin = ttk.Spinbox(layout, textvariable=self._margin_var, from_=0.03, to=0.25,
                             increment=0.01, width=6, format="%.2f")
        margin.pack(side=tk.LEFT, padx=(4, 0))
        _block_mousewheel(margin)
        ttk.Label(layout, text="inches", foreground="gray").pack(side=tk.LEFT, padx=(4, 0))

        # Buttons
        btn_f = ttk.Frame(self, padding=(12, 0, 12, 12))
        btn_f.pack(fill=tk.X)
        ttk.Button(btn_f, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_f, text="Save", command=self._save,
                   style="Accent.TButton").pack(side=tk.RIGHT, padx=4)

    def _offset_delta(self, delta: int):
        try:
            v = int(self._offset_var.get())
        except ValueError:
            v = 10
        v = max(0, min(365, v + delta))
        self._offset_var.set(str(v))

    def _save(self):
        s = self._settings
        s.address_line       = self._addr_var.get().strip()
        s.default_printer    = self._printer_var.get()
        s.default_label_size = self._size_var.get()
        try:
            s.set("bestby_offset_days", max(0, min(365, int(self._offset_var.get()))))
        except ValueError:
            pass
        s.show_barcode     = self._show_bc_var.get()
        s.show_price       = self._show_pr_var.get()
        s.show_dollar_sign = self._show_ds_var.get()
        s.show_date        = self._show_dt_var.get()
        s.show_address     = self._show_ad_var.get()
        s.set("show_combined_button", self._combined_var.get())
        s.set("print_at_printer_dpi", self._native_dpi_var.get())
        for key, var, low, high in (("label_spacing", self._spacing_var, 0.5, 3.0),
                                    ("label_margin_in", self._margin_var, 0.03, 0.25)):
            try:
                s.set(key, max(low, min(high, float(var.get()))))
            except ValueError:
                pass
        chosen = self._preview_mode_var.get()
        for internal, label in PREVIEW_MODE_LABELS.items():
            if label == chosen:
                s.set("default_preview", internal)
                break
        self._on_save()
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────
# Font settings dialog
# ──────────────────────────────────────────────────────────────────────────────

class FontSettingsDialog(tk.Toplevel):
    ELEMENTS = [
        ("name",           "Product Name"),
        ("subtitle",       "Subtitle / Parenthetical"),
        ("ingredients",    "Ingredients text"),
        ("price",          "Price"),
        ("barcode_digits", "Barcode digits"),
        ("date",           "Date line"),
        ("address",        "Address line"),
    ]
    FAMILIES = [
        "Arial Narrow", "Arial", "Arial Bold", "Calibri",
        "Tahoma", "Verdana", "Times New Roman", "Courier New",
    ]

    def __init__(self, parent, settings: Settings, on_save):
        super().__init__(parent)
        self.title("Font Settings")
        self.grab_set()
        self._settings = settings
        self._on_save  = on_save

        self._vars: dict[str, tuple] = {}

        f = ttk.Frame(self, padding=12)
        f.pack()

        headers = ["Element", "Font Family", "Size (pt)", "Bold"]
        for col, h in enumerate(headers):
            ttk.Label(f, text=h, font=("Arial", 9, "bold")).grid(
                row=0, column=col, padx=6, pady=4, sticky=tk.W)

        for row, (elem, label) in enumerate(self.ELEMENTS, start=1):
            fnt = settings.get_font(elem)
            ttk.Label(f, text=label).grid(row=row, column=0, padx=6, pady=3, sticky=tk.W)

            fam_var  = tk.StringVar(value=fnt.get("family", "Arial"))
            size_var = tk.StringVar(value=str(fnt.get("size", 10)))
            bold_var = tk.BooleanVar(value=fnt.get("bold", False))
            self._vars[elem] = (fam_var, size_var, bold_var)

            fam_combo = ttk.Combobox(f, textvariable=fam_var, values=self.FAMILIES, width=20)
            fam_combo.grid(row=row, column=1, padx=6, pady=3)
            _block_mousewheel(fam_combo)

            size_spin = ttk.Spinbox(f, textvariable=size_var, from_=6, to=72, width=6)
            size_spin.grid(row=row, column=2, padx=6, pady=3)
            _block_mousewheel(size_spin)

            ttk.Checkbutton(f, variable=bold_var).grid(row=row, column=3, padx=6, pady=3)

        btn_f = ttk.Frame(self, padding=(12, 0, 12, 12))
        btn_f.pack(fill=tk.X)
        ttk.Button(btn_f, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_f, text="Save", command=self._save,
                   style="Accent.TButton").pack(side=tk.RIGHT, padx=4)

    def _save(self):
        for elem, (fam_var, size_var, bold_var) in self._vars.items():
            try:
                size = int(size_var.get())
            except ValueError:
                size = 10
            self._settings.set_font(elem, fam_var.get(), size, bold_var.get())
        self._on_save()
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────
# Calendar popup — a small, dependency-free month-grid date picker
# ──────────────────────────────────────────────────────────────────────────────

class CalendarPopup(tk.Toplevel):
    """A compact pure-tkinter calendar.  Click a day to pick it; the Print Date
    field can also still be typed into directly."""

    DOW = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]

    def __init__(self, parent, initial: date, on_pick):
        super().__init__(parent)
        self.title("Select Print Date")
        self.resizable(False, False)
        self.transient(parent)
        self._on_pick    = on_pick
        self._today      = date.today()
        self._selected   = initial
        self._view_year  = initial.year
        self._view_month = initial.month

        outer = ttk.Frame(self, padding=8)
        outer.pack()

        # Header — month navigation
        hdr = ttk.Frame(outer)
        hdr.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(hdr, text="◀", width=3, command=self._prev_month).pack(side=tk.LEFT)
        self._hdr_var = tk.StringVar()
        ttk.Label(hdr, textvariable=self._hdr_var, font=("Arial", 10, "bold"),
                  anchor=tk.CENTER, width=18).pack(side=tk.LEFT, expand=True)
        ttk.Button(hdr, text="▶", width=3, command=self._next_month).pack(side=tk.LEFT)

        # Day grid
        self._grid = ttk.Frame(outer)
        self._grid.pack()

        # Footer
        ftr = ttk.Frame(outer)
        ftr.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(ftr, text="Today", command=lambda: self._pick(date.today())).pack(side=tk.LEFT)
        ttk.Button(ftr, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

        self._render()
        self.grab_set()
        self.focus_set()
        self.bind("<Escape>", lambda _e: self.destroy())

    def _render(self):
        for w in self._grid.winfo_children():
            w.destroy()

        self._hdr_var.set(f"{calendar.month_name[self._view_month]} {self._view_year}")

        for c, name in enumerate(self.DOW):
            ttk.Label(self._grid, text=name, width=4, anchor=tk.CENTER,
                      font=("Arial", 8, "bold")).grid(row=0, column=c, padx=1, pady=1)

        cal = calendar.Calendar(firstweekday=6)  # Sunday-first weeks
        weeks = cal.monthdayscalendar(self._view_year, self._view_month)
        for r, week in enumerate(weeks, start=1):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                d = date(self._view_year, self._view_month, day)
                if d == self._selected:
                    bg, fg = "#276749", "white"
                elif d == self._today:
                    bg, fg = "#cdefd6", "black"
                else:
                    bg, fg = "#f5f5f5", "black"
                tk.Button(self._grid, text=str(day), width=3,
                          bg=bg, fg=fg, relief=tk.FLAT, bd=1,
                          activebackground="#9ae6b4", cursor="hand2",
                          command=lambda dd=d: self._pick(dd)).grid(
                    row=r, column=c, padx=1, pady=1)

    def _prev_month(self):
        self._view_month -= 1
        if self._view_month < 1:
            self._view_month = 12
            self._view_year -= 1
        self._render()

    def _next_month(self):
        self._view_month += 1
        if self._view_month > 12:
            self._view_month = 1
            self._view_year += 1
        self._render()

    def _pick(self, d: date):
        self._on_pick(d)
        self.destroy()
