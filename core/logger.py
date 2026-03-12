"""
core/logger.py — ScribeOS Centralised Logging
==============================================
Provides a single get_logger() factory so every module uses a consistent
format and writes to both the console and a rotating file log.

Log files are stored at ~/.scribeos/logs/scribeos.log and rotate at 5 MB
with up to three backups kept.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path.home() / ".scribeos" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_CONSOLE_FMT = "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s"
_FILE_FMT    = "[%(asctime)s] %(levelname)-7s %(name)s (%(filename)s:%(lineno)d): %(message)s"
_DATE_FMT    = "%H:%M:%S"

# Module-level cache so we never attach duplicate handlers
_initialised: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    """
    Return (and configure on first call) a named logger.

    Usage
    -----
    from core.logger import get_logger
    log = get_logger(__name__)
    log.info("ready")
    """
    logger = logging.getLogger(name)
    if name in _initialised:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── Console handler (INFO and above) ────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt=_DATE_FMT))
    logger.addHandler(ch)

    # ── Rotating file handler (DEBUG and above) ──────────────────────────────
    fh = RotatingFileHandler(
        _LOG_DIR / "scribeos.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FILE_FMT, datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)

    # Prevent messages from bubbling to the root logger's handlers
    logger.propagate = False

    _initialised.add(name)
    return logger
