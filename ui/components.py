"""
ui/components.py — ScribeOS UI Component Library
==================================================
Factory functions for every reusable Flet control used in the app.
main.py imports only what it needs; the rest are available for future use.
"""

from __future__ import annotations

import flet as ft

from ui.styles import (
    ACCENT_BRIGHT,
    ACCENT_MED,
    BG_CARD,
    BG_INPUT,
    BG_SURFACE,
    BORDER_DEFAULT,
    BORDER_RADIUS,
    BORDER_RADIUS_LG,
    BORDER_RADIUS_SM,
    BORDER_SUBTLE,
    COLOR_TRANSCRIPT_BG,
    COLOR_TRANSCRIPT_BORDER,
    FONT_BODY,
    FONT_SECTION,
    FONT_STATUS,
    FONT_TITLE,
    MOM_COLOR,
    STATUS_DEFAULT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


# ── Primitives ────────────────────────────────────────────────────────────────

def dot(color: str, size: int = 7) -> ft.Container:
    """Small filled circle used as a status or section indicator."""
    r = size // 2
    return ft.Container(width=size, height=size, bgcolor=color, border_radius=r)


def badge_label(
    text: str,
    color: str = TEXT_MUTED,
    dot_color: str | None = None,
) -> ft.Row:
    """
    Compact section heading — e.g. "● TRANSCRIPT" — with optional leading dot.
    """
    controls: list[ft.Control] = []
    if dot_color:
        controls.append(dot(dot_color))
    controls.append(
        ft.Text(
            text.upper(),
            size=FONT_SECTION,
            weight=ft.FontWeight.W_700,
            color=color,
            style=ft.TextStyle(letter_spacing=1.5),
        )
    )
    return ft.Row(
        controls=controls,
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


# ── Cards ─────────────────────────────────────────────────────────────────────

def glass_card(
    content: ft.Control,
    padding: int = 18,
    expand: bool = False,
    height: float | None = None,
    border_color: str = BORDER_SUBTLE,
) -> ft.Container:
    """Elevated glass-effect card with depth shadow."""
    return ft.Container(
        content=content,
        bgcolor=BG_CARD,
        border=ft.border.all(1, border_color),
        border_radius=BORDER_RADIUS_LG,
        padding=ft.Padding.all(padding),
        expand=expand,
        height=height,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=32,
            color=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
            offset=ft.Offset(0, 6),
        ),
    )


# ── Input ─────────────────────────────────────────────────────────────────────

def api_key_field() -> ft.TextField:
    """Premium masked API key input with indigo focus accent."""
    return ft.TextField(
        hint_text="Paste your Gemini API key…",
        password=True,
        can_reveal_password=True,
        border_radius=BORDER_RADIUS,
        border_color=BORDER_DEFAULT,
        focused_border_color=ACCENT_MED,
        bgcolor=BG_INPUT,
        filled=True,
        expand=True,
        text_size=FONT_BODY,
        prefix_icon=ft.Icons.KEY_ROUNDED,
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=10),
    )


# ── Empty state ───────────────────────────────────────────────────────────────

def transcript_empty_state() -> ft.Container:
    """Centred placeholder rendered before any transcript arrives."""
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.GRAPHIC_EQ_ROUNDED,
                    size=56,
                    color=ft.Colors.with_opacity(0.10, ft.Colors.WHITE),
                ),
                ft.Text(
                    "Ready to Scribe",
                    size=17,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.with_opacity(0.22, ft.Colors.WHITE),
                ),
                ft.Text(
                    "Hit record below — your transcript will appear here",
                    size=FONT_BODY,
                    color=ft.Colors.with_opacity(0.12, ft.Colors.WHITE),
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )


# ── Backward-compatible stubs (kept so existing imports don't break) ──────────

def header_row() -> ft.Row:
    return ft.Row(
        controls=[
            ft.Icon(ft.Icons.GRAPHIC_EQ_ROUNDED, size=24, color=ACCENT_BRIGHT),
            ft.Text("ScribeOS", size=FONT_TITLE, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
        ],
        spacing=8,
    )


def section_label(text: str, color: str = TEXT_SECONDARY) -> ft.Text:
    return ft.Text(text, size=FONT_SECTION, weight=ft.FontWeight.W_600, color=color)


def status_chip(text: str = "Ready", color: str = STATUS_DEFAULT) -> ft.Text:
    return ft.Text(text, size=FONT_STATUS, color=color)


def transcript_container(list_view: ft.ListView) -> ft.Container:
    return ft.Container(
        content=list_view,
        border=ft.border.all(1, COLOR_TRANSCRIPT_BORDER),
        border_radius=BORDER_RADIUS,
        bgcolor=COLOR_TRANSCRIPT_BG,
        expand=True,
        padding=ft.Padding.all(12),
    )


def mom_container(markdown_ctrl: ft.Markdown) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[markdown_ctrl],
            scroll=ft.ScrollMode.AUTO,
        ),
        border=ft.border.all(1, BORDER_DEFAULT),
        border_radius=BORDER_RADIUS,
        bgcolor=BG_SURFACE,
        padding=ft.Padding.all(16),
        expand=True,
    )
