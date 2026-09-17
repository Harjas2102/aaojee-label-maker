"""
settings_manager.py — Persistent application settings for Aaojee Label Maker.
Settings are stored as JSON in the program folder beside the database.
"""

import copy
import json
import os
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Default values (sourced from Section 8 / 13 of the build spec)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    # Business
    "address_line":          "Aaojee, Middletown, NY 845-342-0040",

    # Printer
    "default_printer":       "",          # populated on first run

    # Label defaults
    "default_label_type":    "Combined",          # Combined | Ingredient | Barcode
    "default_label_size":    "2.25x1.25",         # global size for barcode & ingredient
                                                  # labels (combined is always 2.25x3.00)

    # Show the "Print Combined Label" button on the main screen.
    # Hidden by default so staff aren't confused during the transition.
    "show_combined_button":  False,

    # Default preview shown on launch — one of:
    #   "Barcode"    barcode label only
    #   "Ingredient" ingredients label only
    #   "Combined"   combined label only
    #   "All"        all three stacked vertically
    # Session-level radios on the main screen can override this at runtime.
    "default_preview":       "Barcode",

    # Element show/hide defaults
    "show_barcode":          True,
    "show_price":            True,
    "show_dollar_sign":      True,
    "show_date":             True,
    "show_address":          True,

    # Date offset (Best-By = packed date + N days)
    "bestby_offset_days":    10,

    # Auto-capitalise name and subtitle fields when saving
    "auto_capitalize":       True,

    # Vertical spacing multiplier applied to all inter-element gaps (0.5 – 3.0)
    "label_spacing":         1.0,

    # Side margin of the label in inches
    "label_margin_in":       0.08,

    # Starting number for auto-generated barcodes
    "barcode_auto_start":    100000,

    # Render printed labels at the printer's own DPI (sharper barcodes).
    # False = the older fixed 600-DPI render that Windows scales down.
    "print_at_printer_dpi":  True,

    # Salted hash of the manager PIN ("" = no PIN).  See manager_lock.py.
    "manager_pin_hash":      "",

    # Font settings — per element: {"family": ..., "size": ..., "bold": ...}
    "font_name": {
        "family": "Arial Narrow", "size": 22, "bold": True,  "italic": False
    },
    "font_subtitle": {
        "family": "Arial Narrow", "size": 14, "bold": True,  "italic": True
    },
    "font_ingredients": {
        "family": "Arial",        "size": 10, "bold": False, "italic": False
    },
    "font_price": {
        "family": "Arial Narrow", "size": 24, "bold": True,  "italic": False
    },
    "font_barcode_digits": {
        "family": "Arial",        "size":  9, "bold": False, "italic": False
    },
    "font_date": {
        "family": "Arial",        "size": 10, "bold": False, "italic": False
    },
    "font_address": {
        "family": "Arial",        "size":  9, "bold": False, "italic": False
    },
}


class Settings:
    """Load, access, and persist application settings."""

    def __init__(self, settings_path: str):
        self._path = settings_path
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load(self):
        """Read the JSON file, falling back to defaults for any missing key."""
        raw: dict[str, Any] = {}
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                raw = {}

        # Merge defaults: raw takes precedence, but every default key is present.
        # Deep-copy so the nested font dicts are never shared with DEFAULTS.
        self._data = copy.deepcopy(DEFAULTS)
        for key, value in raw.items():
            if key in DEFAULTS and isinstance(DEFAULTS[key], dict) and isinstance(value, dict):
                # Merge nested dicts (font settings) key-by-key
                merged = dict(DEFAULTS[key])
                merged.update(value)
                self._data[key] = merged
            else:
                self._data[key] = value

    def save(self):
        """Write current settings to disk.

        Written to a temp file and swapped in, so a crash or power cut mid-save
        can never leave a truncated settings.json (which would silently reset
        the printer, address and every other setting to defaults).
        """
        folder = os.path.dirname(self._path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp_path, self._path)

    def reset_to_defaults(self):
        """Restore every setting to factory defaults and save."""
        self._data = copy.deepcopy(DEFAULTS)
        self.save()

    # ------------------------------------------------------------------
    # Generic get / set
    # ------------------------------------------------------------------

    def get(self, key: str, fallback: Any = None) -> Any:
        return self._data.get(key, fallback)

    def set(self, key: str, value: Any):
        self._data[key] = value

    # ------------------------------------------------------------------
    # Typed convenience properties
    # ------------------------------------------------------------------

    @property
    def address_line(self) -> str:
        return self._data.get("address_line", DEFAULTS["address_line"])

    @address_line.setter
    def address_line(self, v: str):
        self._data["address_line"] = v

    @property
    def default_printer(self) -> str:
        return self._data.get("default_printer", "")

    @default_printer.setter
    def default_printer(self, v: str):
        self._data["default_printer"] = v

    @property
    def default_label_type(self) -> str:
        return self._data.get("default_label_type", "Combined")

    @default_label_type.setter
    def default_label_type(self, v: str):
        self._data["default_label_type"] = v

    @property
    def default_label_size(self) -> str:
        return self._data.get("default_label_size", "2.25x1.25")

    @default_label_size.setter
    def default_label_size(self, v: str):
        self._data["default_label_size"] = v

    @property
    def show_barcode(self) -> bool:
        return bool(self._data.get("show_barcode", True))

    @show_barcode.setter
    def show_barcode(self, v: bool):
        self._data["show_barcode"] = v

    @property
    def show_price(self) -> bool:
        return bool(self._data.get("show_price", True))

    @show_price.setter
    def show_price(self, v: bool):
        self._data["show_price"] = v

    @property
    def show_dollar_sign(self) -> bool:
        return bool(self._data.get("show_dollar_sign", True))

    @show_dollar_sign.setter
    def show_dollar_sign(self, v: bool):
        self._data["show_dollar_sign"] = v

    @property
    def show_date(self) -> bool:
        return bool(self._data.get("show_date", True))

    @show_date.setter
    def show_date(self, v: bool):
        self._data["show_date"] = v

    @property
    def show_address(self) -> bool:
        return bool(self._data.get("show_address", True))

    @show_address.setter
    def show_address(self, v: bool):
        self._data["show_address"] = v

    @property
    def bestby_offset_days(self) -> int:
        return int(self._data.get("bestby_offset_days", 10))

    def get_font(self, element: str) -> dict:
        """Return the font dict for *element* (e.g. 'name', 'price', ...)."""
        key = f"font_{element}"
        default = DEFAULTS.get(key, {"family": "Arial", "size": 10, "bold": False, "italic": False})
        val = self._data.get(key, default)
        return dict(val)

    def set_font(self, element: str, family: str, size: int, bold: bool,
                 italic: bool | None = None):
        """Store a font.  If *italic* is omitted the element's current italic
        flag is kept (the Font Settings dialog has no italic control)."""
        key = f"font_{element}"
        if italic is None:
            italic = bool(self.get_font(element).get("italic", False))
        self._data[key] = {"family": family, "size": size, "bold": bold, "italic": italic}

    def reset_fonts_to_defaults(self):
        """Restore only font settings to factory defaults."""
        for key in list(DEFAULTS.keys()):
            if key.startswith("font_"):
                self._data[key] = copy.deepcopy(DEFAULTS[key])
