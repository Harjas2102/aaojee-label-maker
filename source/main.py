"""
main.py — Entry point for Aaojee Label Maker.

Double-click this file (or the compiled AaojeeLabels.exe) to launch the program.

All program data (database, settings, backups) is stored in the same folder as
this script / executable, so the entire program can be moved to a new PC by
copying that one folder.
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox

# ──────────────────────────────────────────────────────────────────────────────
# Locate the application directory
# When running as a PyInstaller .exe, sys.executable points to the exe.
# When running as a script, use the script's own directory.
# ──────────────────────────────────────────────────────────────────────────────

if getattr(sys, "frozen", False):
    # Running as a compiled PyInstaller executable
    APP_DIR = os.path.dirname(sys.executable)
    # Add the _MEIPASS internal bundle to the path so our modules are importable
    sys.path.insert(0, sys._MEIPASS)
else:
    # Running as a plain Python script
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, APP_DIR)

DB_PATH       = os.path.join(APP_DIR, "products.db")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
BACKUP_DIR    = os.path.join(APP_DIR, "backups")


# ──────────────────────────────────────────────────────────────────────────────
# Imports (after sys.path is set up)
# ──────────────────────────────────────────────────────────────────────────────

from database         import Database
from settings_manager import Settings
from app_window       import AaojeeApp


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    # Initialise database and settings
    # backup_dir: a copy is saved there before an older database is upgraded
    db       = Database(DB_PATH, backup_dir=BACKUP_DIR)
    settings = Settings(SETTINGS_PATH)

    # Startup backup (silently skipped if the DB doesn't exist yet)
    try:
        db.run_startup_backup(BACKUP_DIR, max_count=30)
    except Exception as e:
        # Non-fatal: log but continue
        print(f"Warning: startup backup failed: {e}", file=sys.stderr)

    # Build and run the GUI
    root = tk.Tk()
    app  = AaojeeApp(root, db, settings, APP_DIR)
    root.mainloop()

    # Save settings on exit
    try:
        settings.save()
    except Exception:
        pass


if __name__ == "__main__":
    main()
