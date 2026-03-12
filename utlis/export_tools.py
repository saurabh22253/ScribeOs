"""
utlis/export_tools.py — ScribeOS Export Utilities
==================================================
Functions to save the session transcript and Minutes of Meeting document
to the user's filesystem.

Both functions return the absolute path of the saved file so the UI can
display a confirmation message with the exact location.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"


def export_transcription(
    text: str,
    output_dir: str = "~/Desktop",
) -> str:
    """
    Save the full session transcript as a plain-text file.

    Parameters
    ----------
    text:       The transcription text to save.
    output_dir: Destination folder (~ is expanded automatically).

    Returns
    -------
    Absolute path of the saved file.
    """
    ts   = datetime.now().strftime(_TIMESTAMP_FMT)
    path = Path(output_dir).expanduser() / f"ScribeOS_Transcript_{ts}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def export_mom(
    markdown_text: str,
    output_dir: str = "~/Desktop",
) -> str:
    """
    Save the Minutes of Meeting document as a Markdown file.

    Parameters
    ----------
    markdown_text: The MOM content in Markdown format.
    output_dir:    Destination folder (~ is expanded automatically).

    Returns
    -------
    Absolute path of the saved file.
    """
    ts   = datetime.now().strftime(_TIMESTAMP_FMT)
    path = Path(output_dir).expanduser() / f"ScribeOS_MOM_{ts}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_text, encoding="utf-8")
    return str(path)
