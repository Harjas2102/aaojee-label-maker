"""
printer_manager.py — Windows print path for Aaojee Label Maker.

Uses win32print + win32ui (from pywin32) to send a PIL Image directly to a
Windows printer at the correct physical size.  On non-Windows systems the
module degrades gracefully: get_printers() returns an empty list and
print_label() raises RuntimeError with a helpful message.
"""

from __future__ import annotations

import sys
from PIL import Image


# ──────────────────────────────────────────────────────────────────────────────
# Platform guard
# ──────────────────────────────────────────────────────────────────────────────

_WINDOWS = sys.platform == "win32"

if _WINDOWS:
    try:
        import win32print
        import win32ui
        from PIL import ImageWin
        _PYWIN32_OK = True
    except ImportError:
        _PYWIN32_OK = False
else:
    _PYWIN32_OK = False


# ──────────────────────────────────────────────────────────────────────────────
# Printer discovery
# ──────────────────────────────────────────────────────────────────────────────

def get_printers() -> list[str]:
    """Return a list of installed printer names.  Empty list on non-Windows."""
    if not _PYWIN32_OK:
        return []
    printers = [p[2] for p in win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    )]
    return sorted(printers)


def get_default_printer() -> str:
    """Return the system default printer name, or '' if not available."""
    if not _PYWIN32_OK:
        return ""
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return ""


def get_printer_dpi(printer_name: str) -> tuple[int, int] | None:
    """Return the printer's native (horizontal, vertical) dots per inch, or
    None if it can't be read (no pywin32, unknown printer, driver error)."""
    if not _PYWIN32_OK or not printer_name:
        return None
    try:
        hdc = win32ui.CreateDC()
        try:
            hdc.CreatePrinterDC(printer_name)
            return hdc.GetDeviceCaps(88), hdc.GetDeviceCaps(90)   # LOGPIXELSX/Y
        finally:
            try:
                hdc.DeleteDC()
            except Exception:
                pass
    except Exception:
        return None


def to_monochrome(image: Image.Image) -> Image.Image:
    """Convert to pure black/white (no grey).  Thermal label printers can only
    print solid dots; sending grey makes the driver dither text and bar edges."""
    return image.convert("L").point(lambda v: 255 if v >= 128 else 0, mode="1")


# ──────────────────────────────────────────────────────────────────────────────
# Core print routine
# ──────────────────────────────────────────────────────────────────────────────

def print_label(
    image: Image.Image,
    printer_name: str,
    label_width_in: float,
    label_height_in: float,
    copies: int = 1,
) -> None:
    """Print *image* on *printer_name* at the given physical dimensions.

    The image is stretched to the label size in printer dots.  When it was
    rendered at the printer's own DPI (see get_printer_dpi) its size already
    matches, so every pixel lands on exactly one printer dot.
    Raises RuntimeError if printing is unavailable or the print job fails.
    """
    if not _WINDOWS:
        raise RuntimeError(
            "Printing is only available on Windows.  "
            "On this machine you can preview labels but cannot print."
        )
    if not _PYWIN32_OK:
        raise RuntimeError(
            "pywin32 is not installed.  Run:  pip install pywin32\n"
            "Then re-launch the program."
        )
    if not printer_name:
        raise RuntimeError("No printer selected.  Please choose a printer first.")

    hprinter = win32print.OpenPrinter(printer_name)
    try:
        hdc = win32ui.CreateDC()
        try:
            hdc.CreatePrinterDC(printer_name)

            # Printer DPI
            printer_dpi_x = hdc.GetDeviceCaps(88)   # LOGPIXELSX
            printer_dpi_y = hdc.GetDeviceCaps(90)   # LOGPIXELSY

            # Physical size in printer pixels
            dest_w = round(label_width_in  * printer_dpi_x)
            dest_h = round(label_height_in * printer_dpi_y)

            # Every copy is the same bitmap — convert it once, not per page.
            dib = ImageWin.Dib(image)

            hdc.StartDoc(printer_name)
            try:
                for _ in range(copies):
                    hdc.StartPage()
                    dib.draw(hdc.GetHandleOutput(), (0, 0, dest_w, dest_h))
                    hdc.EndPage()
            except Exception:
                # Cancel the half-sent job so it doesn't sit stuck in the
                # Windows print queue blocking later prints.
                try:
                    hdc.AbortDoc()
                except Exception:
                    pass
                raise
            hdc.EndDoc()
        finally:
            # Always release the device context; never let a cleanup failure
            # hide the real printing error.
            try:
                hdc.DeleteDC()
            except Exception:
                pass
    finally:
        win32print.ClosePrinter(hprinter)


# ──────────────────────────────────────────────────────────────────────────────
# Convenience wrapper used by the UI
# ──────────────────────────────────────────────────────────────────────────────

def print_labels(
    image: Image.Image,
    printer_name: str,
    label_size: str,           # "2.25x3.00" | "2.25x1.25"
    copies: int = 1,
) -> None:
    """Parse *label_size*, then call print_label()."""
    try:
        w_str, h_str = label_size.split("x")
        w_in = float(w_str)
        h_in = float(h_str)
    except Exception:
        raise ValueError(f"Unrecognised label_size string: {label_size!r}")
    print_label(image, printer_name, w_in, h_in, copies)
