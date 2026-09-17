"""
label_renderer.py — Pillow-based label image renderer for Aaojee Label Maker.

Produces PIL Image objects for:
  • Combined label      2.25" × 3.00"
  • Ingredient-only     2.25" × 1.25"  (also 3.00")
  • Barcode-only        2.25" × 1.25"  (also 3.00")

All text is centred.  Auto-shrink ensures the ingredient list always fits the
label even on the small stock.  Underline for subtitle is drawn manually (Pillow
has no built-in underline).

Render DPI is configurable; 300 DPI is used for printing, 96 DPI for the preview.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from barcode_engine import draw_barcode, pad_barcode, QUIET_MODULES

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

LABEL_W_IN   = 2.25          # all labels share the same width
LABEL_H_TALL = 3.00          # combined / tall variant
LABEL_H_SMALL = 1.25         # small stock

BESTBY_OFFSET = 10           # default; can be overridden via settings

# ──────────────────────────────────────────────────────────────────────────────
# Font loading
# ──────────────────────────────────────────────────────────────────────────────

_FONT_CACHE: dict[str, ImageFont.FreeTypeFont] = {}


# Map common family names to likely Windows filenames (built once, not per call)
_CANDIDATE_MAP: dict[tuple[str, bool, bool], list[str]] = {
    # Arial Narrow
    ("arial narrow", True,  True ): ["arialnbi.ttf",  "ARIALNBI.TTF"],
    ("arial narrow", True,  False): ["arialnb.ttf",   "ARIALNB.TTF",  "arialnarrowbd.ttf"],
    ("arial narrow", False, True ): ["arialni.ttf",   "ARIALNI.TTF"],
    ("arial narrow", False, False): ["arialn.ttf",    "ARIALN.TTF",   "arialnarrow.ttf"],
    # Arial
    ("arial",        True,  True ): ["arialbi.ttf",   "ARIALBI.TTF"],
    ("arial",        True,  False): ["arialbd.ttf",   "ARIALBD.TTF",  "arialb.ttf"],
    ("arial",        False, True ): ["ariali.ttf",    "ARIALI.TTF"],
    ("arial",        False, False): ["arial.ttf",     "ARIAL.TTF"],
    # Arial Bold (treated as bold Arial)
    ("arial bold",   True,  True ): ["arialbi.ttf",   "ARIALBI.TTF"],
    ("arial bold",   True,  False): ["arialbd.ttf",   "ARIALBD.TTF"],
    ("arial bold",   False, True ): ["arialbi.ttf",   "ARIALBI.TTF"],
    ("arial bold",   False, False): ["arialbd.ttf",   "ARIALBD.TTF",  "arial.ttf"],
    # Times New Roman
    ("times new roman", True,  True ): ["timesbi.ttf",  "Times New Roman Bold Italic.ttf"],
    ("times new roman", True,  False): ["timesbd.ttf",  "Times New Roman Bold.ttf",    "times.ttf"],
    ("times new roman", False, True ): ["timesi.ttf",   "Times New Roman Italic.ttf"],
    ("times new roman", False, False): ["times.ttf",    "Times New Roman.ttf",         "timesnewroman.ttf"],
    # Calibri
    ("calibri",      True,  True ): ["calibriz.ttf",  "calibrib.ttf"],
    ("calibri",      True,  False): ["calibrib.ttf",  "Calibri Bold.ttf"],
    ("calibri",      False, True ): ["calibrii.ttf",  "Calibri Italic.ttf"],
    ("calibri",      False, False): ["calibri.ttf",   "Calibri.ttf"],
    # Tahoma
    ("tahoma",       True,  True ): ["tahomabd.ttf",  "Tahoma Bold.ttf"],
    ("tahoma",       True,  False): ["tahomabd.ttf",  "Tahoma Bold.ttf"],
    ("tahoma",       False, True ): ["tahoma.ttf"],
    ("tahoma",       False, False): ["tahoma.ttf",    "Tahoma.ttf"],
    # Verdana
    ("verdana",      True,  True ): ["verdanabi.ttf", "Verdana Bold Italic.ttf"],
    ("verdana",      True,  False): ["verdanab.ttf",  "Verdana Bold.ttf"],
    ("verdana",      False, True ): ["verdanai.ttf",  "Verdana Italic.ttf"],
    ("verdana",      False, False): ["verdana.ttf",   "Verdana.ttf"],
    # Courier New
    ("courier new",  True,  True ): ["courbi.ttf",   "Courier New Bold Italic.ttf"],
    ("courier new",  True,  False): ["courbd.ttf",   "Courier New Bold.ttf"],
    ("courier new",  False, True ): ["couri.ttf",    "Courier New Italic.ttf"],
    ("courier new",  False, False): ["cour.ttf",     "Courier New.ttf"],
    # Georgia
    ("georgia",      True,  True ): ["georgiaz.ttf", "Georgia Bold Italic.ttf"],
    ("georgia",      True,  False): ["georgiab.ttf", "Georgia Bold.ttf"],
    ("georgia",      False, True ): ["georgiai.ttf", "Georgia Italic.ttf"],
    ("georgia",      False, False): ["georgia.ttf",  "Georgia.ttf"],
    # Trebuchet MS
    ("trebuchet ms", True,  True ): ["trebucbi.ttf", "Trebuchet MS Bold Italic.ttf"],
    ("trebuchet ms", True,  False): ["trebucbd.ttf", "Trebuchet MS Bold.ttf"],
    ("trebuchet ms", False, True ): ["trebuci.ttf",  "Trebuchet MS Italic.ttf"],
    ("trebuchet ms", False, False): ["trebuc.ttf",   "Trebuchet MS.ttf"],
}

_FONT_DIRS = [
    r"C:\Windows\Fonts",
    os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Fonts"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
    # Linux / CI — DejaVu fallbacks so the renderer still works in the sandbox
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/msttcorefonts",
    "/usr/share/fonts",
]

# Linux fallback families: DejaVu / Liberation
_LINUX_FALLBACKS: dict[tuple[str, bool, bool], list[str]] = {
    ("arial narrow", True,  False): ["LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
    ("arial narrow", False, False): ["LiberationSans-Regular.ttf", "DejaVuSans.ttf"],
    ("arial narrow", True,  True ): ["LiberationSans-BoldItalic.ttf", "DejaVuSans-BoldOblique.ttf"],
    ("arial",        True,  False): ["LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
    ("arial",        False, False): ["LiberationSans-Regular.ttf", "DejaVuSans.ttf"],
    ("arial",        True,  True ): ["LiberationSans-BoldItalic.ttf", "DejaVuSans-BoldOblique.ttf"],
    ("arial",        False, True ): ["LiberationSans-Italic.ttf", "DejaVuSans-Oblique.ttf"],
}


@lru_cache(maxsize=None)
def _find_font_file(family: str, bold: bool, italic: bool) -> str | None:
    """Search common Windows font directories for a matching .ttf/.otf file."""
    fam = family.strip().lower()

    key = (fam, bold, italic)
    if key in _CANDIDATE_MAP:
        candidates = _CANDIDATE_MAP[key]
    else:
        # Build a broad set of filename guesses for any arbitrary font family.
        # Windows stores fonts with many naming conventions, so we try them all.
        fam_nospace   = fam.replace(" ", "")                    # "calibri"
        fam_hyphen    = fam.replace(" ", "-")                   # "times-new-roman"
        fam_title     = family.strip().title().replace(" ", "") # "Calibri"
        fam_title_hyp = family.strip().title().replace(" ", "-")# "Times-New-Roman"
        if bold and italic:
            candidates = [
                f"{fam_nospace}bi.ttf", f"{fam_nospace}zi.ttf",
                f"{fam_title}BoldItalic.ttf", f"{fam_title}-BoldItalic.ttf",
                f"{fam_title}bolditalic.ttf",
                f"{fam_nospace} Bold Italic.ttf",
                f"{fam_nospace}.ttf", f"{fam_title}.ttf",
            ]
        elif bold:
            candidates = [
                f"{fam_nospace}bd.ttf", f"{fam_nospace}b.ttf",
                f"{fam_nospace}z.ttf",
                f"{fam_title}Bold.ttf", f"{fam_title}-Bold.ttf",
                f"{fam_title}bold.ttf",
                f"{fam_nospace} Bold.ttf",
                f"{fam_nospace}.ttf", f"{fam_title}.ttf",
            ]
        elif italic:
            candidates = [
                f"{fam_nospace}i.ttf",
                f"{fam_title}Italic.ttf", f"{fam_title}-Italic.ttf",
                f"{fam_title}italic.ttf",
                f"{fam_nospace} Italic.ttf",
                f"{fam_nospace}.ttf", f"{fam_title}.ttf",
            ]
        else:
            candidates = [
                f"{fam_nospace}.ttf", f"{fam_title}.ttf",
                f"{fam_hyphen}.ttf", f"{fam_title_hyp}.ttf",
                f"{fam_nospace}-Regular.ttf", f"{fam_title}Regular.ttf",
                f"{fam_title}-Regular.ttf",
                f"{fam_nospace} Regular.ttf",
            ]

    for d in _FONT_DIRS:
        for fname in candidates:
            path = os.path.join(d, fname)
            if os.path.isfile(path):
                return path

    for fb in _LINUX_FALLBACKS.get(key, ["DejaVuSans.ttf", "LiberationSans-Regular.ttf"]):
        for d in _FONT_DIRS:
            path = os.path.join(d, fb)
            if os.path.isfile(path):
                return path

    return None


def load_font(family: str, size_pt: int, bold: bool = False, italic: bool = False,
              dpi: int = 300) -> ImageFont.FreeTypeFont:
    """Load a font at *size_pt* typographic points, scaled to *dpi*.

    Pillow's truetype loader treats the second argument as pixels, so we
    convert: pixels = size_pt × dpi / 72.
    """
    size_px = max(6, round(size_pt * dpi / 72))
    cache_key = f"{family}|{size_px}|{bold}|{italic}"
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    path = _find_font_file(family, bold, italic)
    if path:
        try:
            font = ImageFont.truetype(path, size_px)
            _FONT_CACHE[cache_key] = font
            return font
        except Exception:
            pass

    # Requested font not found — fall back to Arial at the correct size so
    # text is never rendered microscopically small via load_default().
    # (Arial Narrow ships with Office, not Windows, so it can be missing too.)
    if family.strip().lower() != "arial":
        arial_path = _find_font_file("arial", bold, italic)
        if arial_path:
            try:
                font = ImageFont.truetype(arial_path, size_px)
                _FONT_CACHE[cache_key] = font
                return font
            except Exception:
                pass

    # Absolute last resort: Pillow's built-in bitmap font
    return ImageFont.load_default()


# ──────────────────────────────────────────────────────────────────────────────
# Text measurement helpers
# ──────────────────────────────────────────────────────────────────────────────

def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    """Return (width, height) of *text* rendered with *font*."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Word-wrap *text* so each line fits within *max_width* pixels."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        w, _ = _text_size(draw, test, font)
        if w <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_text_centred(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    y: int,
    canvas_width: int,
    fill: str = "black",
    underline: bool = False,
) -> int:
    """Draw centred text at *y*.  Returns the y position after the text."""
    w, h = _text_size(draw, text, font)
    x = (canvas_width - w) // 2
    draw.text((x, y), text, font=font, fill=fill)
    if underline:
        line_y = y + h + 1
        draw.line([(x, line_y), (x + w, line_y)], fill=fill, width=1)
    return y + h


def _draw_wrapped_centred(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    y: int,
    canvas_width: int,
    margin: int,
    fill: str = "black",
) -> int:
    """Word-wrap *text* and draw each line centred.  Returns y after the block."""
    lines = _wrap_text(text, font, canvas_width - 2 * margin, draw)
    for line in lines:
        _, lh = _text_size(draw, line, font)
        _draw_text_centred(draw, line, font, y, canvas_width, fill=fill)
        y += lh + 1
    return y


# ──────────────────────────────────────────────────────────────────────────────
# Auto-shrink helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fit_font(draw, text: str, family: str, start_pt: int, stop_pt: int,
              max_width: int, dpi: int, bold: bool = False, italic: bool = False):
    """Return the font for the largest size from *start_pt* down to (but not
    including) *stop_pt* at which *text* fits *max_width*; if none fit, the
    smallest size tried.  If *start_pt* <= *stop_pt* there is nothing to try,
    so the font is simply loaded at *start_pt* (previously this case crashed
    with an UnboundLocalError when a font size of 6–8 was chosen)."""
    fnt = None
    for pt in range(start_pt, stop_pt, -1):
        fnt = load_font(family, pt, bold=bold, italic=italic, dpi=dpi)
        w, _ = _text_size(draw, text, fnt)
        if w <= max_width:
            break
    if fnt is None:
        fnt = load_font(family, start_pt, bold=bold, italic=italic, dpi=dpi)
    return fnt


def info_lines(product: dict) -> list[tuple[str, bool]]:
    """Lines printed after the ingredients, as (text, bold):
    the allergen line (U-007) and the net weight (U-008).  Empty fields add
    nothing, so labels for products without them are unchanged."""
    lines = []
    allergens = (product.get("allergens") or "").strip()
    if allergens:
        lines.append((f"Contains: {allergens}", True))
    net_weight = (product.get("net_weight") or "").strip()
    if net_weight:
        lines.append((f"Net Wt: {net_weight}", False))
    return lines


def _info_fonts(extras, family: str, pt: int, bold: bool, dpi: int):
    """Pair each info line with its font at the ingredients' fitted size."""
    return [(text, load_font(family, pt, bold or line_bold, dpi=dpi)) for text, line_bold in extras]


def _find_fitting_ingredients_size(
    draw: ImageDraw.ImageDraw,
    ingredients: str,
    family: str,
    bold: bool,
    max_width: int,
    max_height: int,
    dpi: int,
    size_start: int = 12,
    size_min: int = 6,
    extras: list[tuple[str, bool]] = (),
) -> tuple[int, Any]:
    """Largest font size where the ingredient block (plus any info lines)
    fits in *max_height*."""
    full_text = "Ingredients : " + ingredients if ingredients else ""
    for pt in range(size_start, size_min - 1, -1):
        fnt = load_font(family, pt, bold, dpi=dpi)
        n_lines = len(_wrap_text(full_text, fnt, max_width, draw))
        for text, xfnt in _info_fonts(extras, family, pt, bold, dpi):
            n_lines += len(_wrap_text(text, xfnt, max_width, draw))
        _, lh = _text_size(draw, "Ay", fnt)
        h = n_lines * (lh + 1)
        if h <= max_height:
            return pt, fnt
    # absolute minimum
    fnt = load_font(family, size_min, bold, dpi=dpi)
    return size_min, fnt


# ──────────────────────────────────────────────────────────────────────────────
# Date formatting
# ──────────────────────────────────────────────────────────────────────────────

def format_date_line(date_mode: str, pack_date: date, bestby_offset: int = 10) -> str | None:
    """Return the formatted date line string, or None for date_mode='None'."""
    if date_mode == "None":
        return None
    if date_mode == "Best By":
        d = pack_date + timedelta(days=bestby_offset)
        return f"Best By : {d.month}/{d.day}/{d.year}"
    # Default / "Packed"
    return f"Packed : {pack_date.month}/{pack_date.day}/{pack_date.year}"


# ──────────────────────────────────────────────────────────────────────────────
# Main render function
# ──────────────────────────────────────────────────────────────────────────────

def render_label(
    product: dict,
    label_type: str,         # "Combined" | "Ingredient" | "Barcode"
    label_size: str,         # "2.25x3.00" | "2.25x1.25"
    pack_date: date,
    show_flags: dict,        # keys: barcode, price, dollar_sign, date, address
    font_settings: dict,     # keyed by element name, each a dict with family/size/bold
    address_line: str = "Aaojee Middletown NY 845 342 0040",
    bestby_offset: int = 10,
    dpi: int = 300,
    gap_scale: float = 1.0,  # multiplier for inter-element vertical gaps (0.5 – 3.0)
    margin_in: float = 0.08, # side margin in inches (0.03 – 0.25)
    min_module_in: float | None = None,
) -> Image.Image:
    """Render and return a PIL Image of the label.

    *min_module_in* sets a minimum width (inches) for one barcode module.
    It is used when rendering at a label printer's own low resolution
    (e.g. 203 DPI), where fitting the column alone would make the bars
    thinner than they print today.  None keeps the normal sizing.
    """

    gap_scale = max(0.25, min(4.0, float(gap_scale)))  # clamp to sane range

    # ── Canvas dimensions ────────────────────────────────────────────────────
    w_px = round(LABEL_W_IN * dpi)
    h_in = LABEL_H_TALL if label_size == "2.25x3.00" else LABEL_H_SMALL
    h_px = round(h_in * dpi)

    img  = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)

    # Vertical margin (top/bottom) is fixed; side margin is user-adjustable.
    # Keeping them separate means changing "Side Margin" never shifts content
    # up or down — it only narrows/widens the text column.
    margin      = round(0.05 * dpi)                                  # fixed top/bottom
    margin_side = round(max(0.03, min(0.25, margin_in)) * dpi)       # controllable L/R
    content_w   = w_px - 2 * margin_side

    def fs(element: str) -> dict:
        return font_settings.get(f"font_{element}", {
            "family": "Arial", "size": 10, "bold": False, "italic": False
        })

    def gap(inches: float) -> int:
        """Return a vertical gap in pixels, scaled by gap_scale."""
        return max(1, round(inches * dpi * gap_scale))

    def module_px(px: int) -> int:
        """Apply the optional minimum barcode module width."""
        if min_module_in:
            return max(px, round(min_module_in * dpi))
        return px

    # ── Dispatch to layout functions ─────────────────────────────────────────
    if label_type == "Combined":
        overflow, block_used, block_room = _layout_combined(
            draw, product, pack_date, show_flags, font_settings, fs, w_px, h_px, margin,
            content_w, address_line, bestby_offset, dpi, gap, module_px)
        if overflow > 0 and info_lines(product):
            # The "Contains:" / "Net Wt:" lines made the ingredients block push the
            # address off the bottom.  Lay out again allowing the block only the
            # height it used minus the overflow, so its font steps down until
            # everything fits.  (Labels without those lines never take this
            # path, so they print exactly as before.)
            img  = Image.new("RGB", (w_px, h_px), "white")
            draw = ImageDraw.Draw(img)
            _layout_combined(draw, product, pack_date, show_flags, font_settings, fs,
                             w_px, h_px, margin, content_w, address_line, bestby_offset,
                             dpi, gap, module_px,
                             block_trim=block_room - (block_used - overflow))
    elif label_type == "Ingredient":
        _layout_ingredient(draw, product, font_settings, fs,
                           w_px, h_px, margin, content_w, dpi, gap)
    else:  # "Barcode"
        _layout_barcode(draw, product, pack_date, show_flags, font_settings, fs,
                        w_px, h_px, margin, content_w, address_line, bestby_offset, dpi, gap,
                        module_px)

    return img


# ──────────────────────────────────────────────────────────────────────────────
# Layout: Combined (2.25" × 3.00")
# ──────────────────────────────────────────────────────────────────────────────

def _layout_combined(draw, product, pack_date, show_flags, font_settings, fs,
                     w_px, h_px, margin, content_w, address_line, bestby_offset, dpi, gap,
                     module_px=lambda px: px, block_trim: int = 0) -> tuple[int, int, int]:
    """Top-to-bottom: name, subtitle, ingredients, price, barcode, date, address.

    Returns (overflow, block_used, block_room): how many pixels the content ran
    past the bottom margin (0 if it fit), and the height the ingredients block
    used / was allowed.  *block_trim* takes pixels away from the block's room.
    """
    block_used = block_room = 0
    y = margin

    name        = (product.get("name") or "").upper()
    subtitle    = (product.get("subtitle") or "").upper()
    ingredients = product.get("ingredients") or ""
    extras      = info_lines(product)
    size_str    = (product.get("size") or "").upper()
    price       = product.get("price")
    barcode_raw = product.get("barcode_number") or ""
    date_mode   = product.get("date_mode") or "Packed"

    # ── Name (auto-shrink to fit content width) ───────────────────────────────
    name_spec = fs("name")
    name_fnt  = _fit_font(draw, name, name_spec["family"], name_spec["size"], 6,
                          content_w, dpi, bold=name_spec.get("bold", True))
    y = _draw_text_centred(draw, name, name_fnt, y, w_px) + gap(0.06)

    # ── Subtitle (bold+italic, underlined, auto-shrink) ───────────────────────
    if subtitle:
        sub_spec = fs("subtitle")
        sub_text = f"({subtitle})"
        sub_fnt  = _fit_font(draw, sub_text, sub_spec["family"], sub_spec["size"], 6,
                             content_w, dpi, bold=sub_spec.get("bold", True), italic=True)
        y = _draw_text_centred(draw, sub_text, sub_fnt, y, w_px, underline=True)
        y += gap(0.05)

    # ── Size line (if present, no ingredients) ───────────────────────────────
    if size_str and not ingredients:
        sub_spec = fs("subtitle")
        sub_fnt  = load_font(sub_spec["family"], sub_spec["size"], bold=False, dpi=dpi)
        y = _draw_text_centred(draw, size_str, sub_fnt, y, w_px)
        y += gap(0.05)

    # ── Ingredients block (+ "Contains:" / "Net Wt:" lines) ───────────────────
    if ingredients or extras:
        barcode_section_h = round(0.70 * dpi)
        price_h           = round(0.30 * dpi)
        date_addr_h       = round(0.20 * dpi)
        remaining = h_px - y - margin - barcode_section_h - price_h - date_addr_h - block_trim
        remaining = max(remaining, round(0.30 * dpi))

        ing_spec = fs("ingredients")
        ing_family, ing_bold = ing_spec.get("family", "Arial"), ing_spec.get("bold", False)
        ing_pt, ing_fnt = _find_fitting_ingredients_size(
            draw, ingredients,
            family=ing_family,
            bold=ing_bold,
            max_width=content_w,
            max_height=remaining,
            dpi=dpi,
            size_start=ing_spec.get("size", 10),
            size_min=6,
            extras=extras,
        )
        ing_max_y = y + remaining
        block_top = y
        y = _draw_ingredients_block(draw, ingredients, ing_fnt, ing_fnt,
                                    y, w_px, content_w, margin, dpi,
                                    max_y=ing_max_y,
                                    extras=_info_fonts(extras, ing_family, ing_pt, ing_bold, dpi))
        block_used, block_room = y - block_top, remaining
        y += gap(0.04)

    y += gap(0.05)   # spacer before price

    # ── Price ─────────────────────────────────────────────────────────────────
    if show_flags.get("price", True) and price is not None:
        price_spec = fs("price")
        price_fnt  = load_font(price_spec["family"], price_spec["size"],
                               bold=price_spec.get("bold", True), dpi=dpi)
        dollar     = "$" if show_flags.get("dollar_sign", True) else ""
        y = _draw_text_centred(draw, f"{dollar}{price:.2f}", price_fnt, y, w_px)
        y += gap(0.05)

    # ── Barcode ───────────────────────────────────────────────────────────────
    if show_flags.get("barcode", True) and barcode_raw:
        try:
            data6  = pad_barcode(barcode_raw)
            bc_fnt = load_font(fs("barcode_digits")["family"],
                               fs("barcode_digits")["size"],
                               bold=fs("barcode_digits").get("bold", False), dpi=dpi)
            mod_w     = module_px(max(2, round(0.013 * dpi)))
            bar_h     = round(0.50 * dpi)
            total_bc_w = (51 + 2 * QUIET_MODULES) * mod_w
            bc_w, bc_h = draw_barcode(draw,
                                      (w_px - total_bc_w) // 2, y,
                                      data6, mod_w, bar_h, bc_fnt)
            y += bc_h + gap(0.04)
        except Exception:
            pass

    # ── Date line ─────────────────────────────────────────────────────────────
    if show_flags.get("date", True):
        date_line = format_date_line(date_mode, pack_date, bestby_offset)
        if date_line:
            date_fnt = load_font(fs("date")["family"], fs("date")["size"],
                                 bold=fs("date").get("bold", False), dpi=dpi)
            y = _draw_text_centred(draw, date_line, date_fnt, y, w_px)
            y += gap(0.04)

    # ── Address (anchored near the bottom) ────────────────────────────────────
    if show_flags.get("address", True) and address_line:
        addr_fnt = load_font(fs("address")["family"], fs("address")["size"],
                             bold=fs("address").get("bold", False), dpi=dpi)
        _, ah = _text_size(draw, address_line, addr_fnt)
        addr_y = max(y, h_px - margin - ah)
        _draw_text_centred(draw, address_line, addr_fnt, addr_y, w_px)
        return max(0, y - (h_px - margin - ah)), block_used, block_room
    return max(0, y - (h_px - margin)), block_used, block_room


# ──────────────────────────────────────────────────────────────────────────────
# Layout: Ingredient-only
# ──────────────────────────────────────────────────────────────────────────────

def _layout_ingredient(draw, product, font_settings, fs,
                        w_px, h_px, margin, content_w, dpi, gap):
    """Name, subtitle (if present), ingredients block.  No price/barcode/date."""
    y = margin

    name        = (product.get("name") or "").upper()
    subtitle    = (product.get("subtitle") or "").upper()
    ingredients = product.get("ingredients") or ""
    extras      = info_lines(product)
    size_str    = (product.get("size") or "").upper()

    # ── Name ──────────────────────────────────────────────────────────────────
    name_spec = fs("name")
    name_fnt  = _fit_font(draw, name, name_spec["family"], name_spec["size"], 6,
                          content_w, dpi, bold=name_spec.get("bold", True))
    y = _draw_text_centred(draw, name, name_fnt, y, w_px) + gap(0.05)

    # ── Subtitle (auto-shrink to fit) ─────────────────────────────────────────
    if subtitle:
        sub_spec = fs("subtitle")
        sub_text = f"({subtitle})"
        sub_fnt  = _fit_font(draw, sub_text, sub_spec["family"], sub_spec["size"], 6,
                             content_w, dpi, bold=sub_spec.get("bold", True), italic=True)
        y = _draw_text_centred(draw, sub_text, sub_fnt, y, w_px, underline=True)
        y += gap(0.04)

    if size_str and not ingredients:
        sub_spec = fs("subtitle")
        sub_fnt  = load_font(sub_spec["family"], sub_spec["size"], bold=False, dpi=dpi)
        y = _draw_text_centred(draw, size_str, sub_fnt, y, w_px)
        y += gap(0.04)

    # ── Ingredients (+ "Contains:" / "Net Wt:" lines) ─────────────────────────
    if ingredients or extras:
        remaining = h_px - y - margin
        remaining = max(remaining, round(0.15 * dpi))
        ing_spec = fs("ingredients")
        ing_family, ing_bold = ing_spec.get("family", "Arial"), ing_spec.get("bold", False)
        ing_pt, ing_fnt = _find_fitting_ingredients_size(
            draw, ingredients,
            family=ing_family,
            bold=ing_bold,
            max_width=content_w,
            max_height=remaining,
            dpi=dpi,
            size_start=ing_spec.get("size", 10),
            size_min=6,
            extras=extras,
        )
        ing_max_y = y + remaining
        _draw_ingredients_block(draw, ingredients, ing_fnt, ing_fnt,
                                y, w_px, content_w, margin, dpi,
                                max_y=ing_max_y,
                                extras=_info_fonts(extras, ing_family, ing_pt, ing_bold, dpi))


# ──────────────────────────────────────────────────────────────────────────────
# Layout: Barcode-only
# ──────────────────────────────────────────────────────────────────────────────

def _layout_barcode(draw, product, pack_date, show_flags, font_settings, fs,
                    w_px, h_px, margin, content_w, address_line, bestby_offset, dpi, gap,
                    module_px=lambda px: px):
    """Two-column label layout matching the Dahi Vada reference:
      • Name   — top, left-aligned, full content width
      • Left column  (~53%): large price, date below it
      • Right column (~47%): very tall barcode filling available height
      • Address — bottom, centred, full width
    """
    is_small  = h_px <= round(1.30 * dpi)
    left_edge = (w_px - content_w) // 2       # == margin_side

    name        = (product.get("name") or "").upper()
    price       = product.get("price")
    barcode_raw = product.get("barcode_number") or ""
    date_mode   = product.get("date_mode") or "Packed"

    # ── Column geometry ────────────────────────────────────────────────────────
    gutter       = max(4, round(0.04 * dpi))
    right_col_w  = round(content_w * 0.47)
    left_col_w   = content_w - right_col_w - gutter
    right_col_x  = left_edge + left_col_w + gutter

    # ── Address reserve (we need to know this early) ──────────────────────────
    addr_reserve = 0
    addr_fnt     = None
    if show_flags.get("address", True) and address_line:
        addr_fnt = load_font(fs("address")["family"], fs("address")["size"],
                             bold=fs("address").get("bold", False), dpi=dpi)
        _, ah    = _text_size(draw, address_line, addr_fnt)
        addr_reserve = ah + gap(0.03)

    # ── Name (auto-shrink, left-aligned, full content width) ──────────────────
    name_spec   = fs("name")
    max_name_pt = min(name_spec["size"], 14 if is_small else name_spec["size"])
    name_fnt    = _fit_font(draw, name, name_spec["family"], max_name_pt, 6,
                            content_w, dpi, bold=name_spec.get("bold", True))
    _, nh = _text_size(draw, name or "A", name_fnt)
    draw.text((left_edge, margin), name, font=name_fnt, fill="black")
    name_bottom = margin + nh + gap(0.04)

    # ── Barcode height budget (right column, fills from name_bottom to addr) ──
    avail_h = h_px - name_bottom - addr_reserve - margin

    # ── Barcode (right column, drawn first so we know its exact height) ────────
    bc_h_drawn = 0
    if show_flags.get("barcode", True) and barcode_raw:
        try:
            data6        = pad_barcode(barcode_raw)
            bc_fnt_spec  = fs("barcode_digits")
            bc_fnt       = load_font(bc_fnt_spec["family"], bc_fnt_spec["size"],
                                     bold=bc_fnt_spec.get("bold", False), dpi=dpi)
            try:
                tb       = draw.textbbox((0, 0), "0 123456 7", font=bc_fnt)
                digit_h  = tb[3] - tb[1] + 4
            except Exception:
                digit_h  = round(bc_fnt_spec["size"] * dpi / 72) + 4

            # Module width: fill the right column as tightly as possible,
            # capped at 0.018" so bars never look too thick to scan.
            total_modules = 51 + 2 * QUIET_MODULES          # 69 modules with quiet zones
            mod_w = module_px(max(2, min(
                right_col_w // total_modules,                # fill column
                max(2, round(0.018 * dpi)),                  # GS1 max for readability
            )))
            bar_h  = max(round(0.30 * dpi), avail_h - digit_h - gap(0.02))
            bc_x   = right_col_x  # left edge of quiet zone in right column

            _, bc_h_drawn = draw_barcode(
                draw, bc_x, name_bottom, data6, mod_w, bar_h, bc_fnt,
            )
        except Exception:
            pass

    # ── Price (left column, large, left-aligned) ───────────────────────────────
    ly = name_bottom          # current y in left column
    if show_flags.get("price", True) and price is not None:
        price_spec   = fs("price")
        max_price_pt = min(price_spec["size"], 22 if is_small else price_spec["size"])
        # Auto-shrink so price fits left column
        price_fnt    = _fit_font(draw, "$99.99", price_spec["family"], max_price_pt, 8,
                                 left_col_w, dpi, bold=price_spec.get("bold", True))
        dollar      = "$" if show_flags.get("dollar_sign", True) else ""
        price_str   = f"{dollar}{price:.2f}"
        draw.text((left_edge, ly), price_str, font=price_fnt, fill="black")
        _, ph = _text_size(draw, price_str, price_fnt)
        ly += ph + gap(0.04)

    # ── Date (below price, left-aligned) ──────────────────────────────────────
    if show_flags.get("date", True):
        date_line = format_date_line(date_mode, pack_date, bestby_offset)
        if date_line:
            date_fnt = load_font(fs("date")["family"], fs("date")["size"],
                                 bold=fs("date").get("bold", False), dpi=dpi)
            draw.text((left_edge, ly), date_line, font=date_fnt, fill="black")
            _, dh = _text_size(draw, date_line, date_fnt)
            ly += dh + gap(0.03)

    # ── Address (anchored at the bottom, centred full width) ──────────────────
    if addr_fnt is not None and address_line:
        _, ah  = _text_size(draw, address_line, addr_fnt)
        addr_y = h_px - margin - ah
        _draw_text_centred(draw, address_line, addr_fnt, addr_y, w_px)


# ──────────────────────────────────────────────────────────────────────────────
# Shared: draw "Ingredients :" block
# ──────────────────────────────────────────────────────────────────────────────

def _draw_ingredients_block(draw, ingredients, ing_fnt, prefix_fnt,
                             y, w_px, content_w, margin, dpi,
                             max_y: int | None = None,
                             extras: list[tuple[str, Any]] = ()) -> int:
    """Draw the 'Ingredients : …' block.  'Ingredients' is underlined.
    *extras* are (text, font) info lines drawn centred underneath
    ("Contains: …", "Net Wt: …").
    Lines that would exceed *max_y* are silently clipped (not drawn).
    Returns y after the block."""

    prefix  = "Ingredients : "
    body    = ingredients
    full    = prefix + body

    lines   = _wrap_text(full, ing_fnt, content_w, draw) if ingredients else []
    _, lh   = _text_size(draw, "Ay", ing_fnt)

    for i, line in enumerate(lines):
        # Stop drawing if we would exceed the allowed area
        if max_y is not None and y + lh > max_y:
            break
        if i == 0:
            # On the first line, underline only the word "Ingredients"
            pw, _ = _text_size(draw, "Ingredients", prefix_fnt)
            # draw underline under "Ingredients" only
            full_w, _ = _text_size(draw, line, ing_fnt)
            x_start = (w_px - full_w) // 2
            draw.text((x_start, y), line, font=ing_fnt, fill="black")
            draw.line(
                [(x_start, y + lh + 1), (x_start + pw, y + lh + 1)],
                fill="black", width=1,
            )
        else:
            _draw_text_centred(draw, line, ing_fnt, y, w_px)
        y += lh + 1

    for text, fnt in extras:
        for line in _wrap_text(text, fnt, content_w, draw):
            if max_y is not None and y + lh > max_y:
                return y
            _draw_text_centred(draw, line, fnt, y, w_px)
            y += lh + 1

    return y
