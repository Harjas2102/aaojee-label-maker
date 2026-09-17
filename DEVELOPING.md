# Developing Aaojee Label Maker

How the project is kept, changed, tested and delivered. For using the program see
`USER_GUIDE.txt`; for what has changed and why, see `UPGRADE_TRACKER.md`.

---

## 1. Where the code lives: Git and GitHub (U-018)

The project folder is a **Git repository**, and every change is a commit with a message saying
what changed. A private **GitHub** repository holds the same history online. It replaces the old
zip-and-flash-drive loop:

```
  Mac / any PC                                Store PC
  ────────────                                ────────
  edit code                                   double-click update_and_build.bat
  git commit   ──►  GitHub (private repo)  ──►  (git pull + build.bat)
  git push          runs all tests + builds    new AaojeeLabels.exe
```

### What is in Git and what isn't

| In Git | Not in Git (see `.gitignore`) |
|--------|-------------------------------|
| `source/`, `tests/`, `tools/` | `products.db`, `settings.json`, `print_queue.json`, `backups/`: the **live store data**, which stays on the store PC |
| `build.bat`, `run_tests.bat`, `update_and_build.bat` | `AaojeeLabels.exe`, `source/build/`, `source/dist/` (rebuilt from the code) |
| Docs: handoff, user guide, build instructions, tracker, this file | `import_source/`, `ingredient_docs/`, `reference_images/` (old-system originals; keep them on the flash drive) |
| `data_changes/*/` scripts and `changes.csv` logs | `data_changes/*/*.db` copies, `upgrade_snapshots/` (pre-Git safety copies) |

The live database is never pushed to GitHub. To move store data between PCs, use
File → Export / Backup Database… and Restore, as before.

### First-time setup on a computer

1. Install Git (<https://git-scm.com/download/win>) and Python 3.10+.
2. Get the code:
   - **Store PC, already set up:** the folder is already a repository.
   - **Another computer:** `git clone https://github.com/<account>/aaojee-label-maker.git`
3. In the project folder, turn on the pre-commit check (once per copy):
   ```
   git config core.hooksPath .githooks
   python -m pip install Pillow sv-ttk
   ```

### Everyday loop

```
git pull                        # get the latest
...edit files...
python tools/run_tests.py       # optional, the hook runs the quick ones anyway
git add -A
git commit -m "Short description of the change"
git push
```

On the store PC, double-click **`update_and_build.bat`**. It pulls the latest code and runs
`build.bat`. Close the program first.

**Line endings:** `.gitattributes` keeps `.bat` files in Windows (CRLF) format and everything else
in LF, on every computer. Don't change that; a `.bat` with the wrong endings silently fails
(see the tracker history).

---

## 2. Automatic tests (U-019)

### What is tested

| File | Checks |
|------|--------|
| `tests/test_barcode.py` | All 1,000,000 six-digit barcodes encode exactly as the store's labels do (compared with a recorded fingerprint); the POS reference products; right-padding; every format a scanner can send |
| `tests/test_labels.py` | Every product in every label type and size renders; barcodes decode back to the right number at 203 and 300 DPI; the Contains / Net Wt lines never run off the label or drop ingredient text; tiny font sizes don't crash |
| `tests/test_database.py` | Saving, searching, schema upgrade (with backup), Trash, print and price history, backup / export / restore, backup rotation |
| `tests/test_modules.py` | Settings, importer, print queue, manager PIN, price rounding, categories |
| `tests/test_gui.py` | The real window: both screens and the PIN, keyboard printing, scanning, unsaved-changes prompts, editing, duplicate, Trash, printing at printer DPI, print history, preview, price tools, sorting and filters |

The tests use `tests/fixtures/products.json`, a copy of the product list taken on 2026-09-17, in
temporary folders. **They never touch the live `products.db`.** Refresh the fixture only on
purpose; the label check below compares against it.

### How to run them

- Double-click **`run_tests.bat`**, or
- `python tools/run_tests.py`: everything, about 80 s. Test windows open and close.
- `python tools/run_tests.py --quick`: everything except the window tests, about 40 s.

### "Labels unchanged" check

`python tools/compare_labels.py` renders every product's labels (4,457 images: every type and
size, on screen and at 203 DPI) with the **last commit** and with the **current files**, and
fails if any pixel differs. It saves before/after pictures of the first differences in
`tools/label_diffs/`.

If a label change **is** intended:
- when committing: `ALLOW_LABEL_CHANGES=1 git commit ...`
- on GitHub: put `[label change]` in the commit message.

### When they run automatically

| Where | When | Runs |
|-------|------|------|
| `.githooks/pre-commit` | before every commit that touches `source/`, `tests/` or `tools/` | quick tests + labels-unchanged check; **the commit is stopped if either fails** |
| GitHub Actions (`.github/workflows/tests.yml`) | every push | all tests + labels unchanged since the previous commit, then builds `AaojeeLabels.exe` and attaches it to the run under **Artifacts** |

---

## 3. Building

- `build.bat`: installs Pillow, pywin32, PyInstaller, sv-ttk and pyodbc, then builds
  `AaojeeLabels.exe` next to it. Details in `BUILD_INSTRUCTIONS.txt`.
- `update_and_build.bat`: `git pull`, then `build.bat`.
- The GitHub workflow builds the same `.exe` on every push. Download it from the run page →
  Artifacts → `AaojeeLabels-exe`.

After any build that changes printing: Test Print, then scan at the POS.

---

## 4. Recording changes

Every upgrade gets an entry in `UPGRADE_TRACKER.md`: what, why, files and functions, how it was
tested, and how to turn it off or undo it. Git history now records the exact code of every
change, so new work doesn't need `upgrade_snapshots/`. To see or undo a change:

```
git log --oneline                    # list of changes
git show <commit>                    # what one change did
git revert <commit>                  # undo it with a new commit (safe)
```

One-time data changes to `products.db` go in `data_changes/<date>_<id>_<name>/`: a script with a
dry run, `--apply` and `--undo`, its `changes.csv` log, and a copy of the database from before.
