"""Barcode encoding — the store's POS depends on these exactly (handoff §5)."""

import hashlib
import unittest

import helpers  # noqa: F401  (puts source/ on the path)
import barcode_engine as be

# SHA-256 of every check digit + bar pattern for all 1,000,000 six-digit
# numbers, recorded 2026-09-17 from the encoder the store uses.  If this
# changes, printed barcodes changed — do not "fix" the test; find out why.
ALL_BARCODES_DIGEST = "5f2af4cd348f596e15205cfa13b4b311bcc4c56c36800576beb88aa2a8d2eaca"

# Real products with barcodes confirmed at the POS (handoff §5.6)
REFERENCE = {"314300": 9, "610400": 7, "312200": 6, "311400": 7, "313900": 6, "313700": 8}


class TestEncoding(unittest.TestCase):
    def test_reference_products(self):
        for data6, check in REFERENCE.items():
            self.assertEqual(be.compute_check_digit(data6), check, data6)

    def test_self_test_passes(self):
        self.assertTrue(be.run_self_test())

    def test_every_barcode_unchanged(self):
        h = hashlib.sha256()
        for n in range(1_000_000):
            d = f"{n:06d}"
            ck = be.compute_check_digit(d)
            h.update(bytes([ck]))
            h.update(bytes(be.encode_upce(d, ck)))
        self.assertEqual(h.hexdigest(), ALL_BARCODES_DIGEST)

    def test_right_pad_rule(self):
        self.assertEqual(be.pad_barcode("3143"), "314300")
        self.assertEqual(be.pad_barcode("12"), "120000")
        self.assertEqual(be.pad_barcode("312200"), "312200")
        for bad in ("1234567", "12a4", ""):
            with self.assertRaises(ValueError):
                be.pad_barcode(bad)

    def test_validate_input(self):
        self.assertEqual(be.validate_barcode_input(""), (True, ""))
        self.assertTrue(be.validate_barcode_input("3143")[0])
        self.assertFalse(be.validate_barcode_input("1234567")[0])
        self.assertFalse(be.validate_barcode_input("31 43")[0])


class TestScannerInput(unittest.TestCase):
    """U-001: every form a scanner may send resolves to the same product."""

    def _forms(self, d6):
        ck = be.compute_check_digit(d6)
        upca11 = be._upce_to_upca(d6)
        upca = upca11 + str(be._upca_check(upca11))
        return [d6, "0" + d6, d6 + str(ck), "0" + d6 + str(ck), upca, "0" + upca]

    def test_all_formats_sampled(self):
        for n in range(0, 1_000_000, 7):          # ~143k numbers, all last digits
            d6 = f"{n:06d}"
            for form in self._forms(d6):
                self.assertIn(d6, be.scanned_code_to_data6(form), form)

    def test_real_label(self):
        self.assertEqual(be.scanned_code_to_data6("03108006"), ["310800"])
        # A UPC-A number can have more than one UPC-E spelling (here 310800 and
        # the non-standard 310803); all are returned and the one that exists wins.
        codes = be.scanned_code_to_data6("031000000806")
        self.assertIn("310800", codes)
        self.assertTrue(all(be._upce_to_upca(c) == "03100000080" for c in codes))

    def test_bad_check_digits_rejected(self):
        self.assertEqual(be.scanned_code_to_data6("03143008"), [])
        self.assertEqual(be.scanned_code_to_data6("031400000038"), [])

    def test_non_codes(self):
        for text in ("", "CHANNA", "31", "12345678901234"):
            self.assertEqual(be.scanned_code_to_data6(text), [])


if __name__ == "__main__":
    unittest.main()
