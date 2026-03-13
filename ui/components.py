"""
ui/components.py — ScribeOS UI Component Library (v2)
======================================================
Reusable Flet controls for the sidebar-navigation architecture.
"""

from __future__ import annotations

import flet as ft

from ui.styles import (
    ACCENT_BRIGHT,
    ACCENT_MED,
    BG_CARD,
    BG_INPUT,
    BG_PAGE,
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
    NAV_ACTIVE_BG,
    NAV_HOVER_BG,
    NAV_ICON_ACTIVE,
    NAV_ICON_INACTIVE,
    NAV_WIDTH,
    STATUS_DEFAULT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


# ── Primitives ────────────────────────────────────────────────────────────────

def dot(color: str, size: int = 7) -> ft.Container:
    r = size // 2
    return ft.Container(width=size, height=size, bgcolor=color, border_radius=r)


def section_chip(text: str, color: str = TEXT_MUTED) -> ft.Row:
    return ft.Row(
        controls=[
            ft.Text(
                text.upper(),
                size=FONT_SECTION,
                weight=ft.FontWeight.W_700,
                color=color,
                style=ft.TextStyle(letter_spacing=1.5),
            )
        ],
        spacing=6,
    )


# ── Sidebar nav item ─────────────────────────────────────────────────────────

def nav_item(
    icon: str,
    label: str,
    active: bool = False,
    on_click=None,
) -> ft.Container:
    icon_color = NAV_ICON_ACTIVE if active else NAV_ICON_INACTIVE
    label_color = TEXT_PRIMARY if active else TEXT_SECONDARY
    bg = NAV_ACTIVE_BG if active else ft.Colors.TRANSPARENT

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(icon, size=16, color=icon_color),
                ft.Text(
                    label,
                    size=13,
                    weight=ft.FontWeight.W_500 if active else ft.FontWeight.W_400,
                    color=label_color,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=bg,
        border_radius=BORDER_RADIUS_SM,
        padding=ft.Padding.symmetric(horizontal=12, vertical=9),
        on_click=on_click,
        ink=True,
    )


# ── Input ─────────────────────────────────────────────────────────────────────

def api_key_field() -> ft.TextField:
    return ft.TextField(
        hint_text="Paste Gemini API key…",
        password=True,
        can_reveal_password=True,
        border_radius=BORDER_RADIUS_SM,
        border_color=BORDER_SUBTLE,
        focused_border_color=ACCENT_MED,
        bgcolor=BG_INPUT,
        filled=True,
        expand=True,
        text_size=11,
        prefix_icon=ft.Icons.KEY_ROUNDED,
        content_padding=ft.Padding.symmetric(horizontal=10, vertical=8),
    )


def glossary_field() -> ft.TextField:
    return ft.TextField(
        hint_text="e.g. Meeting with Saurabh and Abhay regarding ScribeOS deployment…",
        multiline=True,
        min_lines=3,
        max_lines=4,
        border_radius=BORDER_RADIUS,
        border_color=BORDER_SUBTLE,
        focused_border_color=ACCENT_MED,
        bgcolor=BG_INPUT,
        filled=True,
        expand=True,
        text_size=FONT_BODY,
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
    )


# ── Cards / containers ────────────────────────────────────────────────────────

def surface_card(
    content: ft.Control,
    padding: int = 20,
    expand: bool = False,
    height: float | None = None,
    border_color: str = BORDER_SUBTLE,
) -> ft.Container:
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
            blur_radius=20,
            color=ft.Colors.with_opacity(0.35, ft.Colors.BLACK),
            offset=ft.Offset(0, 4),
        ),
    )


# ── History list item card ────────────────────────────────────────────────────

def history_card(
    title: str,
    preview: str,
    on_click=None,
    active: bool = False,
) -> ft.Container:
    bg = "#21262D" if active else BG_CARD
    border_col = ACCENT_MED if active else BORDER_SUBTLE

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    title,
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=TEXT_PRIMARY,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=1,
                ),
                ft.Text(
                    preview,
                    size=11,
                    color=TEXT_SECONDARY,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=2,
                ),
            ],
            spacing=4,
            tight=True,
        ),
        bgcolor=bg,
        border=ft.border.all(1, border_col),
        border_radius=BORDER_RADIUS,
        padding=ft.Padding.all(12),
        on_click=on_click,
        ink=True,
        margin=ft.Margin.only(bottom=4),
    )


# ── Empty states ──────────────────────────────────────────────────────────────

def studio_empty_state() -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.SPATIAL_AUDIO_ROUNDED,
                    size=64,
                    color=ft.Colors.with_opacity(0.07, ft.Colors.WHITE),
                ),
                ft.Text(
                    "Ready to Record",
                    size=16,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.with_opacity(0.20, ft.Colors.WHITE),
                ),
                ft.Text(
                    "Type your meeting context above, then hit Record",
                    size=12,
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


def history_empty_state() -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.HISTORY_ROUNDED,
                    size=56,
                    color=ft.Colors.with_opacity(0.07, ft.Colors.WHITE),
                ),
                ft.Text(
                    "No Sessions Yet",
                    size=16,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.with_opacity(0.20, ft.Colors.WHITE),
                ),
                ft.Text(
                    "Past transcripts will appear here",
                    size=12,
                    color=ft.Colors.with_opacity(0.12, ft.Colors.WHITE),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )


# ── Backward-compat stubs ─────────────────────────────────────────────────────

def glass_card(content, padding=18, expand=False, height=None, border_color=BORDER_SUBTLE):
    return surface_card(content, padding=padding, expand=expand, height=height, border_color=border_color)

def transcript_empty_state():
    return studio_empty_state()

def badge_label(text, color=TEXT_MUTED, dot_color=None):
    return section_chip(text, color=color)

def header_row():
    return ft.Row(
        controls=[
            ft.Icon(ft.Icons.GRAPHIC_EQ_ROUNDED, size=24, color=ACCENT_BRIGHT),
            ft.Text("ScribeOS", size=FONT_TITLE, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
        ],
        spacing=8,
    )

def section_label(text, color=TEXT_SECONDARY):
    return ft.Text(text, size=FONT_SECTION, weight=ft.FontWeight.W_600, color=color)

def status_chip(text="Ready", color=STATUS_DEFAULT):
    return ft.Text(text, size=FONT_STATUS, color=color)

def transcript_container(list_view):
    return ft.Container(
        content=list_view,
        border=ft.border.all(1, COLOR_TRANSCRIPT_BORDER),
        border_radius=BORDER_RADIUS,
        bgcolor=COLOR_TRANSCRIPT_BG,
        expand=True,
        padding=ft.Padding.all(12),
    )

def mom_container(markdown_ctrl):
    return ft.Container(
        content=ft.Column(controls=[markdown_ctrl], scroll=ft.ScrollMode.AUTO),
        border=ft.border.all(1, BORDER_DEFAULT),
        border_radius=BORDER_RADIUS,
        bgcolor=BG_SURFACE,
        padding=ft.Padding.all(16),
        expand=True,
    )

