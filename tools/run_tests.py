"""
Run the automated tests.

    python tools/run_tests.py            everything (opens and closes the program window a few times)
    python tools/run_tests.py --quick    everything except the window (GUI) tests

Needs Pillow:  python -m pip install Pillow sv-ttk
Exit code 0 = all passed.
"""

from __future__ import annotations

import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")


def main() -> int:
    quick = "--quick" in sys.argv
    if quick:
        os.environ["AAOJEE_SKIP_GUI_TESTS"] = "1"
    sys.path.insert(0, TESTS)
    started = time.time()
    suite = unittest.defaultTestLoader.discover(TESTS, pattern="test_*.py", top_level_dir=TESTS)
    result = unittest.TextTestRunner(verbosity=1, buffer=True).run(suite)
    took = time.time() - started
    ok = result.wasSuccessful()
    print(f"\n{'ALL TESTS PASSED' if ok else 'TESTS FAILED'} "
          f"({result.testsRun} tests, {len(result.skipped)} skipped, {took:.0f}s)"
          + ("  [quick: window tests skipped]" if quick else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
