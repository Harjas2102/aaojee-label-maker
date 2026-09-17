"""
barcode_engine.py — UPC-E barcode encoding for Aaojee Label Maker.

UPC-E is an 8-digit compressed barcode (0 + 6 data digits + check digit).
The store's POS stores only the 6 data digits; leading/trailing structural
digits are stripped by the scanner.

Spec §4:
  • Input: 1–6 data digits entered by the user.
  • Right-pad with zeros to 6 digits (e.g. "3143" → "314300").
  • Reject if > 6 digits or non-numeric.
  • Compute check digit via UPC-A expansion.
  • Render as a scannable UPC-E barcode image.

Verification values (from §13):
  data       UPC-E full
  314300  →  0 314300 9
  312200  →  0 312200 6
  313700  →  0 313700 8
  311400  →  0 311400 7
  313900  →  0 313900 6
  610400  →  0 610400 7
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


# ──────────────────────────────────────────────────────────────────────────────
# Bar-pattern tables
# ──────────────────────────────────────────────────────────────────────────────

# L-type (odd parity) — standard UPC-A left-side encoding, 7 modules each.
# 1 = dark bar, 0 = light space.
_L: dict[str, list[int]] = {
    "0": [0, 0, 0, 1, 1, 0, 1],
    "1": [0, 0, 1, 1, 0, 0, 1],
    "2": [0, 0, 1, 0, 0, 1, 1],
    "3": [0, 1, 1, 1, 1, 0, 1],
    "4": [0, 1, 0, 0, 0, 1, 1],
    "5": [0, 1, 1, 0, 0, 0, 1],
    "6": [0, 1, 0, 1, 1, 1, 1],
    "7": [0, 1, 1, 1, 0, 1, 1],
    "8": [0, 1, 1, 0, 1, 1, 1],
    "9": [0, 0, 0, 1, 0, 1, 1],
}

# G-type (even parity) = REVERSE of the bitwise complement of L-type.
# (Not just the complement — EAN/UPC-E G-codes are the mirror image of
#  the R-code: G[d] = reverse(complement(L[d])).  Using complement alone
#  produces mirror-image bars that scanners cannot read.)
_G: dict[str, list[int]] = {d: list(reversed([1 - b for b in _L[d]])) for d in _L}

# Parity table for UPC-E, number-system digit 0.
# Index by check digit (0–9).  'G' = G-type, 'L' = L-type, left→right.
# Source: GS1 General Specifications Table 5 / ISO 15420.
_PARITY: list[str] = [
    "GGGLLL",   # check 0 → 111000
    "GGLGLL",   # check 1 → 110100
    "GGLLGL",   # check 2 → 110010
    "GGLLLG",   # check 3 → 110001
    "GLGGLL",   # check 4 → 101100
    "GLLGGL",   # check 5 → 100110
    "GLLLGG",   # check 6 → 100011
    "GLGLGL",   # check 7 → 101010
    "GLGLLG",   # check 8 → 101001
    "GLLGLG",   # check 9 → 100101
]

# Guards
_START_GUARD = [1, 0, 1]
_END_GUARD   = [0, 1, 0, 1, 0, 1]

# GS1 requires ≥7 module quiet zone each side; use 9 for scanner tolerance
QUIET_MODULES = 9


# ──────────────────────────────────────────────────────────────────────────────
# Data-digits helpers
# ──────────────────────────────────────────────────────────────────────────────

def pad_barcode(raw: str) -> str:
    """Right-pad *raw* to exactly 6 digits with zeros.
    '3143' → '314300', '312200' → '312200'.
    Raises ValueError if *raw* is longer than 6 digits or contains non-digits.
    """
    raw = raw.strip()
    if not raw.isdigit():
        raise ValueError("Barcode must contain digits only.")
    if len(raw) > 6:
        raise ValueError("Barcode number cannot be longer than 6 digits.")
    return raw.ljust(6, "0")


def validate_barcode_input(raw: str) -> tuple[bool, str]:
    """Return (ok, message).  ok=True means input is acceptable."""
    raw = raw.strip()
    if raw == "":
        return True, ""           # blank = no barcode, always valid
    if not raw.isdigit():
        return False, "Barcode must contain digits only (no spaces or letters)."
    if len(raw) > 6:
        return False, "Barcode number cannot be longer than 6 digits."
    return True, ""


# ──────────────────────────────────────────────────────────────────────────────
# Check-digit computation
# ──────────────────────────────────────────────────────────────────────────────

def _upce_to_upca(data6: str) -> str:
    """Expand a 6-digit UPC-E data string to 11 UPC-A digits (no check digit).

    Expansion rules (last digit of data6 determines which rule applies):
      d6 = 0 → UPC-A = 0  d1 d2 0 0 0 0 0  d3 d4 d5
      d6 = 1 → UPC-A = 0  d1 d2 1 0 0 0 0  d3 d4 d5
      d6 = 2 → UPC-A = 0  d1 d2 2 0 0 0 0  d3 d4 d5
      d6 = 3 → UPC-A = 0  d1 d2 d3 0 0 0 0 0  d4 d5
      d6 = 4 → UPC-A = 0  d1 d2 d3 d4 0 0 0 0 0  d5
      d6 = 5 → UPC-A = 0  d1 d2 d3 d4 d5 0 0 0 0 5
      d6 = 6 → UPC-A = 0  d1 d2 d3 d4 d5 0 0 0 0 6
      d6 = 7 → UPC-A = 0  d1 d2 d3 d4 d5 0 0 0 0 7
      d6 = 8 → UPC-A = 0  d1 d2 d3 d4 d5 0 0 0 0 8
      d6 = 9 → UPC-A = 0  d1 d2 d3 d4 d5 0 0 0 0 9

    (An earlier version placed d6 before the four zeros for 5–9.  Both
    positions carry weight 3 in the UPC-A check sum, so every check digit —
    and therefore every printed barcode — is identical; this is the
    standard GS1 expansion.)
    """
    if len(data6) != 6:
        raise ValueError(f"Expected 6 data digits, got {len(data6)}")
    d = data6  # d[0]..d[5]  (d[5] is the "last digit" in the spec)
    last = int(d[5])
    if last == 0:
        return f"0{d[0]}{d[1]}00000{d[2]}{d[3]}{d[4]}"
    if last == 1:
        return f"0{d[0]}{d[1]}10000{d[2]}{d[3]}{d[4]}"
    if last == 2:
        return f"0{d[0]}{d[1]}20000{d[2]}{d[3]}{d[4]}"
    if last == 3:
        return f"0{d[0]}{d[1]}{d[2]}00000{d[3]}{d[4]}"
    if last == 4:
        return f"0{d[0]}{d[1]}{d[2]}{d[3]}00000{d[4]}"
    # 5–9: the manufacturer code uses all 5 data digits, product digits vary
    return f"0{d[0]}{d[1]}{d[2]}{d[3]}{d[4]}0000{d[5]}"


def _upca_check(digits11: str) -> int:
    """Compute the UPC-A check digit for an 11-digit string."""
    odd_sum  = sum(int(digits11[i]) for i in range(0, 11, 2))   # positions 1,3,5,7,9,11
    even_sum = sum(int(digits11[i]) for i in range(1, 11, 2))   # positions 2,4,6,8,10
    return (10 - ((odd_sum * 3 + even_sum) % 10)) % 10


def compute_check_digit(data6: str) -> int:
    """Return the UPC-E check digit for a 6-digit data string."""
    upca = _upce_to_upca(data6)
    return _upca_check(upca)


# ──────────────────────────────────────────────────────────────────────────────
# Scanner input → 6 data digits
# ──────────────────────────────────────────────────────────────────────────────

def _upca_to_upce_data(upca11: str) -> list[str]:
    """Every 6-digit UPC-E data string that expands to the 11-digit UPC-A body."""
    u = upca11
    candidates = [
        u[1:3] + u[8:11] + u[3],     # last digit 0–2
        u[1:4] + u[9:11] + "3",      # last digit 3
        u[1:5] + u[10] + "4",        # last digit 4
        u[1:6] + u[10],              # last digit 5–9
    ]
    out: list[str] = []
    for c in candidates:
        if len(c) == 6 and c.isdigit() and c not in out and _upce_to_upca(c) == u:
            out.append(c)
    return out


def scanned_code_to_data6(code: str) -> list[str]:
    """Return the 6-digit data numbers that a scanned or typed code can mean.

    Barcode scanners can be configured to send a UPC-E label in several
    forms; all of these resolve to the same product:
      6 digits   314300          the data digits themselves
      7 digits   0314300         number system + data (no check digit)
                 3143009         data + check digit (no number system)
      8 digits   03143009        the full UPC-E
      12 digits  031400000039    expanded to UPC-A
      13 digits  0031400000039   UPC-A as EAN-13
    Check digits are verified, so a mis-scan does not match a product.
    Returns [] if the code cannot be a UPC-E barcode.
    """
    d = code.strip()
    if not d.isdigit():
        return []
    out: list[str] = []

    def add(x: str):
        if x not in out:
            out.append(x)

    n = len(d)
    if n == 6:
        add(d)
    elif n == 7:
        if d[0] == "0":
            add(d[1:])
        if int(d[6]) == compute_check_digit(d[:6]):
            add(d[:6])
    elif n == 8:
        if d[0] == "0" and int(d[7]) == compute_check_digit(d[1:7]):
            add(d[1:7])
    elif n in (12, 13):
        upca = d if n == 12 else (d[1:] if d[0] == "0" else "")
        if upca and upca[0] == "0" and int(upca[11]) == _upca_check(upca[:11]):
            for x in _upca_to_upce_data(upca[:11]):
                add(x)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Bar-pattern encoder
# ──────────────────────────────────────────────────────────────────────────────

def encode_upce(data6: str, check: int | None = None) -> list[int]:
    """Return the full module sequence (0/1) for a UPC-E symbol.

    Sequence: start-guard (3) + 6×7 data modules (42) + end-guard (6) = 51 modules.
    *check* may be passed in when the caller has already computed it.
    """
    if check is None:
        check = compute_check_digit(data6)
    parity = _PARITY[check]

    modules: list[int] = list(_START_GUARD)
    for digit, ptype in zip(data6, parity):
        table = _G if ptype == "G" else _L
        modules.extend(table[digit])
    modules.extend(_END_GUARD)

    assert len(modules) == 51, f"Expected 51 modules, got {len(modules)}"
    return modules


# ──────────────────────────────────────────────────────────────────────────────
# Pillow rendering
# ──────────────────────────────────────────────────────────────────────────────

def draw_barcode(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    data6: str,
    module_width: int = 3,
    bar_height: int = 80,
    font: ImageFont.FreeTypeFont | None = None,
    include_text: bool = True,
) -> tuple[int, int]:
    """Draw a UPC-E barcode onto *draw* at (*x*, *y*).

    *x* is the left edge of the left quiet zone.  Bars are drawn inside the
    quiet zones.  The human-readable text follows GS1 UPC-E layout:
      • number-system digit "0" to the left of the start guard
      • 6 data digits centred below the data bars
      • check digit to the right of the end guard

    Returns (total_width_px, total_height_px) including quiet zones and text.
    """
    check       = compute_check_digit(data6)
    modules     = encode_upce(data6, check)
    quiet_px    = QUIET_MODULES * module_width
    data_bar_w  = len(modules) * module_width   # 51 × module_width
    total_width = data_bar_w + 2 * quiet_px

    # ── Draw bars (offset by left quiet zone) ─────────────────────────────
    cx = x + quiet_px
    for bit in modules:
        if bit:
            draw.rectangle([cx, y, cx + module_width - 1, y + bar_height - 1], fill="black")
        cx += module_width

    # ── Human-readable text below bars ────────────────────────────────────
    text_height = 0
    if include_text and font is not None:
        bar_start_x = x + quiet_px
        bar_end_x   = bar_start_x + data_bar_w
        ty          = y + bar_height + 2

        def _measure(s: str) -> tuple[int, int]:
            try:
                bb = draw.textbbox((0, 0), s, font=font)
                return bb[2] - bb[0], bb[3] - bb[1]
            except AttributeError:
                return draw.textsize(s, font=font)  # type: ignore[attr-defined]

        w0,      th = _measure("0")
        w_data,  _  = _measure(data6)
        w_check, _  = _measure(str(check))

        # Number-system digit "0" — just left of the start guard
        draw.text((bar_start_x - w0 - 2, ty), "0", fill="black", font=font)
        # 6 data digits — centred under the data bars
        draw.text((bar_start_x + (data_bar_w - w_data) // 2, ty),
                  data6, fill="black", font=font)
        # Check digit — just right of the end guard
        draw.text((bar_end_x + 2, ty), str(check), fill="black", font=font)

        text_height = th + 4

    return total_width, bar_height + text_height


def make_barcode_image(
    data6: str,
    module_width: int = 3,
    bar_height: int = 80,
    font: ImageFont.FreeTypeFont | None = None,
    padding: int = 6,
) -> Image.Image:
    """Return a standalone white-background PIL image of just the barcode."""
    total_w = (51 + 2 * QUIET_MODULES) * module_width
    text_h  = 18 if font else 0
    w = total_w + padding * 2
    h = bar_height + text_h + padding * 2

    img  = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    draw_barcode(draw, padding, padding, data6, module_width, bar_height, font)
    return img


# ──────────────────────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────────────────────

_KNOWN_CHECKS = {
    "314300": 9,   # Aloo Mattar (3143 → right-padded)
    "312200": 6,   # Hakka Noodles
    "313700": 8,   # Rice Pilaf
    "311400": 7,   # Karela Aloo
    "313900": 6,   # Mango Mousse
    "610400": 7,   # Chana Masala  (UPC-A 0 610 00000 040 → check 7)
}


def run_self_test() -> bool:
    """Verify check digits for all known spec values.  Returns True if all pass."""
    all_pass = True
    for data6, expected_check in _KNOWN_CHECKS.items():
        got = compute_check_digit(data6)
        status = "PASS" if got == expected_check else "FAIL"
        if got != expected_check:
            all_pass = False
        print(f"  {status}  data={data6}  expected check={expected_check}  got={got}")
    return all_pass


if __name__ == "__main__":
    print("UPC-E check-digit self-test:")
    ok = run_self_test()
    print(f"\n{'All tests passed.' if ok else 'SOME TESTS FAILED!'}")
