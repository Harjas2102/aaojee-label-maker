"""
Check that printed labels look exactly the same as in an earlier commit.

    python tools/compare_labels.py                 compare working files with the last commit
    python tools/compare_labels.py --ref HEAD~1    compare with another commit
    python tools/compare_labels.py --allow         report differences but don't fail

Every product in tests/fixtures/products.json is rendered as every label type
and size, on screen (150 DPI) and as printed at 203 DPI, with both versions of
source/.  Any label that differs by even one pixel is reported, and
side-by-side pictures (earlier | now) are saved in tools/label_diffs/ so the
change can be looked at.

If a label change is intended, commit with ALLOW_LABEL_CHANGES=1 set, or put
[label change] in the commit message for the GitHub check.
Exit code 0 = identical (or --allow).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIFF_DIR = os.path.join(ROOT, "tools", "label_diffs")
MAX_PICTURES = 12

VARIANTS = [("Barcode", "2.25x1.25"), ("Barcode", "2.25x3.00"), ("Ingredient", "2.25x1.25"),
            ("Ingredient", "2.25x3.00"), ("Combined", "2.25x3.00")]
EXTRAS = {"allergens": "Milk, Tree Nuts", "net_weight": "16 OZ"}


# ── worker: runs in a separate Python process against one copy of source/ ────

def _jobs():
    with open(os.path.join(ROOT, "tests", "fixtures", "products.json"), encoding="utf-8") as f:
        products = json.load(f)
    for p in products:
        for lt, size in VARIANTS:
            for dpi in (150, 203):
                yield f"{p['id']}|{lt}|{size}|{dpi}", p, lt, size, dpi
        if p["ingredients"]:
            yield f"{p['id']}|Combined+extras|2.25x3.00|203", dict(p, **EXTRAS), "Combined", "2.25x3.00", 203


def _worker(source_dir: str, out_path: str, image_keys: list[str] | None, image_dir: str | None):
    sys.path.insert(0, source_dir)
    from datetime import date
    import label_renderer as lr
    with open(os.path.join(ROOT, "tests", "fixtures", "settings.json"), encoding="utf-8") as f:
        s = json.load(f)
    flags = dict(barcode=True, price=True, dollar_sign=True, date=True, address=True)
    hashes = {}
    for key, p, lt, size, dpi in _jobs():
        if image_keys is not None and key not in image_keys:
            continue
        kwargs = {"min_module_in": 0.013} if dpi == 203 else {}
        try:
            img = lr.render_label(p, lt, size, date(2026, 9, 17), flags, s, s["address_line"], 10,
                                  dpi, s["label_spacing"], s["label_margin_in"], **kwargs)
        except TypeError:          # an older version without min_module_in
            img = lr.render_label(p, lt, size, date(2026, 9, 17), flags, s, s["address_line"], 10,
                                  dpi, s["label_spacing"], s["label_margin_in"])
        except Exception as e:     # a crash counts as a difference
            hashes[key] = f"ERROR {type(e).__name__}: {e}"
            continue
        hashes[key] = hashlib.sha1(img.tobytes()).hexdigest()
        if image_dir:
            img.save(os.path.join(image_dir, key.replace("|", "_") + ".png"))
    with open(out_path, "w") as f:
        json.dump(hashes, f)


# ── main ─────────────────────────────────────────────────────────────────────

def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _export_source(ref: str, dest: str) -> bool:
    try:
        names = _git("ls-tree", "-r", "--name-only", ref, "--", "source/").split()
    except subprocess.CalledProcessError:
        return False
    for name in names:
        if not name.endswith(".py"):
            continue
        data = subprocess.run(["git", "show", f"{ref}:{name}"], cwd=ROOT, capture_output=True,
                              check=True).stdout
        with open(os.path.join(dest, os.path.basename(name)), "wb") as f:
            f.write(data)
    return bool(names)


def _run_workers(dirs_and_outputs, image_keys=None, image_dirs=None):
    procs = []
    for i, (src, out) in enumerate(dirs_and_outputs):
        cmd = [sys.executable, os.path.abspath(__file__), "--worker", src, out]
        if image_keys is not None:
            keys_file = out + ".keys.json"
            with open(keys_file, "w") as f:
                json.dump(image_keys, f)
            cmd += ["--images", keys_file, image_dirs[i]]
        procs.append(subprocess.Popen(cmd))
    return all(p.wait() == 0 for p in procs)


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--worker":
        keys = image_dir = None
        if "--images" in args:
            i = args.index("--images")
            with open(args[i + 1]) as f:
                keys = json.load(f)
            image_dir = args[i + 2]
        _worker(args[1], args[2], keys, image_dir)
        return 0

    ref = args[args.index("--ref") + 1] if "--ref" in args else "HEAD"
    allow = "--allow" in args or os.environ.get("ALLOW_LABEL_CHANGES") == "1"
    tmp = tempfile.mkdtemp(prefix="aaojee_labels_")
    try:
        old_src = os.path.join(tmp, "ref_source")
        os.makedirs(old_src)
        if not _export_source(ref, old_src):
            print(f"compare_labels: no source/ in {ref} - nothing to compare.")
            return 0
        new_src = os.path.join(ROOT, "source")
        old_out, new_out = os.path.join(tmp, "old.json"), os.path.join(tmp, "new.json")
        print(f"Rendering every label with {ref} and with the current files...")
        if not _run_workers([(old_src, old_out), (new_src, new_out)]):
            print("compare_labels: rendering failed (see errors above).")
            return 1
        with open(old_out) as f:
            old = json.load(f)
        with open(new_out) as f:
            new = json.load(f)
        changed = sorted(k for k in new if old.get(k) != new[k])
        if not changed:
            print(f"Labels unchanged: all {len(new)} renders identical to {ref}.")
            return 0

        print(f"\n{len(changed)} of {len(new)} label renders differ from {ref}:")
        for k in changed[:20]:
            print("   ", k, "" if not str(new[k]).startswith("ERROR") else new[k])
        shutil.rmtree(DIFF_DIR, ignore_errors=True)
        os.makedirs(DIFF_DIR)
        sample = changed[:MAX_PICTURES]
        dirs = [os.path.join(tmp, "old_png"), os.path.join(tmp, "new_png")]
        for d in dirs:
            os.makedirs(d)
        _run_workers([(old_src, old_out + "2"), (new_src, new_out + "2")], sample, dirs)
        from PIL import Image
        for k in sample:
            name = k.replace("|", "_") + ".png"
            pics = [Image.open(os.path.join(d, name)).convert("RGB")
                    for d in dirs if os.path.exists(os.path.join(d, name))]
            if len(pics) == 2:
                w = pics[0].width + pics[1].width + 20
                h = max(p.height for p in pics)
                side = Image.new("RGB", (w, h), (255, 0, 0))
                side.paste(pics[0], (0, 0))
                side.paste(pics[1], (pics[0].width + 20, 0))
                side.save(os.path.join(DIFF_DIR, name))
        print(f"\nPictures (earlier | now): {DIFF_DIR}")
        if allow:
            print("Label changes allowed (ALLOW_LABEL_CHANGES=1 / --allow).")
            return 0
        print("If this change is intended, commit again with ALLOW_LABEL_CHANGES=1.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
