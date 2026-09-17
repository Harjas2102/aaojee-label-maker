"""
manager_lock.py — Optional manager PIN for Aaojee Label Maker.

When a PIN is set, actions that change how labels look or that can lose data
(Settings, Font Settings, Reset Layout, Spacing / Side Margin, Delete,
Restore, Import, changing the PIN) ask for it first.  Printing, searching and
editing products stay open to everyone.

After a correct PIN the program stays unlocked for UNLOCK_MINUTES since the
last protected action, then locks itself again.  "Lock Now" locks at once.

The PIN is never stored as text: settings.json keeps a salted PBKDF2 hash
under "manager_pin_hash".  Forgotten PIN: close the program, open
settings.json in Notepad, delete the "manager_pin_hash" line, save.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

import tkinter as tk
from tkinter import messagebox, simpledialog

PIN_SETTING_KEY = "manager_pin_hash"
UNLOCK_MINUTES  = 5
MIN_PIN_LENGTH  = 4
_ITERATIONS     = 100_000


def hash_pin(pin: str, salt_hex: str | None = None) -> str:
    """Return "salt$hash" for *pin*."""
    salt_hex = salt_hex or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"),
                                 bytes.fromhex(salt_hex), _ITERATIONS)
    return f"{salt_hex}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split("$", 1)
        return hmac.compare_digest(hash_pin(pin, salt_hex), stored)
    except Exception:
        return False


class ManagerLock:
    """Tracks whether manager-only actions are currently allowed."""

    def __init__(self, settings, clock=time.monotonic):
        self._settings = settings
        self._clock = clock
        self._unlocked_until = 0.0

    # ── state ────────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return bool(self._settings.get(PIN_SETTING_KEY))

    def is_unlocked(self) -> bool:
        return (not self.enabled) or self._clock() < self._unlocked_until

    def lock(self):
        self._unlocked_until = 0.0

    def _extend(self):
        self._unlocked_until = self._clock() + UNLOCK_MINUTES * 60

    def try_unlock(self, pin: str) -> bool:
        if self.enabled and verify_pin(pin, self._settings.get(PIN_SETTING_KEY)):
            self._extend()
            return True
        return False

    # ── UI ───────────────────────────────────────────────────────────────────

    def require(self, parent, action: str) -> bool:
        """Return True if *action* may go ahead, asking for the PIN if needed."""
        if not self.enabled:
            return True
        if self.is_unlocked():
            self._extend()
            return True
        pin = simpledialog.askstring(
            "Manager PIN",
            f"{action} needs the manager PIN.\n\nEnter PIN:",
            show="•", parent=parent)
        if pin is None:
            return False
        if self.try_unlock(pin):
            return True
        messagebox.showerror("Manager PIN", "That PIN is not correct.", parent=parent)
        return False

    def set_pin_interactive(self, parent) -> bool:
        """Set or change the PIN.  Returns True if a new PIN was saved."""
        if self.enabled and not self.require(parent, "Changing the manager PIN"):
            return False
        while True:
            pin = simpledialog.askstring(
                "Set Manager PIN",
                f"Choose a manager PIN (at least {MIN_PIN_LENGTH} characters).\n"
                "Write it down somewhere safe.",
                show="•", parent=parent)
            if pin is None:
                return False
            pin = pin.strip()
            if len(pin) < MIN_PIN_LENGTH:
                messagebox.showwarning(
                    "Set Manager PIN",
                    f"The PIN must be at least {MIN_PIN_LENGTH} characters.", parent=parent)
                continue
            again = simpledialog.askstring(
                "Set Manager PIN", "Type the same PIN again to confirm:",
                show="•", parent=parent)
            if again is None:
                return False
            if again.strip() != pin:
                messagebox.showwarning("Set Manager PIN",
                                       "The two PINs did not match.  Try again.",
                                       parent=parent)
                continue
            self._settings.set(PIN_SETTING_KEY, hash_pin(pin))
            self._settings.save()
            self._extend()
            messagebox.showinfo("Set Manager PIN", "Manager PIN saved.", parent=parent)
            return True

    def remove_pin_interactive(self, parent) -> bool:
        if not self.enabled:
            messagebox.showinfo("Remove Manager PIN", "No manager PIN is set.", parent=parent)
            return False
        if not self.require(parent, "Removing the manager PIN"):
            return False
        if not messagebox.askyesno(
                "Remove Manager PIN",
                "Remove the manager PIN?\n\nEveryone will be able to change settings "
                "and delete products.", icon="warning", parent=parent):
            return False
        self._settings.set(PIN_SETTING_KEY, "")
        self._settings.save()
        self.lock()
        messagebox.showinfo("Remove Manager PIN", "Manager PIN removed.", parent=parent)
        return True
