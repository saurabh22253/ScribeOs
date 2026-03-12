"""
utlis/security.py — ScribeOS API Key Security
==============================================
Provides thin wrappers around the system keychain (via `keyring`) so the
Gemini API key is never written to disk in plain text.

On macOS the key is stored in the login Keychain and can be inspected with
  Keychain Access.app → scribeos → gemini_api_key

Usage
-----
    from utlis.security import save_key, load_key, delete_key

    save_key("AIza...")
    key = load_key()      # returns str | None
    delete_key()
"""

from __future__ import annotations

import re
from typing import Optional

try:
    import keyring
    import keyring.errors
    _KEYRING_AVAILABLE = True
except ImportError:  # pragma: no cover
    _KEYRING_AVAILABLE = False

_SERVICE  = "ScribeOS"
_KEY_NAME = "gemini_api_key"

# Minimal sanity check: Gemini API keys start with "AIza" and are ~39 chars.
_KEY_PATTERN = re.compile(r"^AIza[0-9A-Za-z_\-]{35,}$")


def is_valid_key(api_key: str) -> bool:
    """Return True if the string looks like a valid Gemini API key."""
    return bool(api_key and _KEY_PATTERN.match(api_key.strip()))


def save_key(api_key: str) -> bool:
    """
    Persist the API key in the macOS Keychain.

    Returns True on success, False if keyring is unavailable or the save fails.
    """
    if not _KEYRING_AVAILABLE:
        return False
    try:
        keyring.set_password(_SERVICE, _KEY_NAME, api_key.strip())
        return True
    except Exception:  # noqa: BLE001
        return False


def load_key() -> Optional[str]:
    """
    Retrieve the stored API key from the macOS Keychain.

    Returns None if keyring is unavailable or no key has been saved.
    """
    if not _KEYRING_AVAILABLE:
        return None
    try:
        return keyring.get_password(_SERVICE, _KEY_NAME)
    except Exception:  # noqa: BLE001
        return None


def delete_key() -> None:
    """Remove the stored API key from the Keychain (e.g. on sign-out)."""
    if not _KEYRING_AVAILABLE:
        return
    try:
        keyring.delete_password(_SERVICE, _KEY_NAME)
    except Exception:  # noqa: BLE001
        pass
