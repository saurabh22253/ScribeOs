"""
main.py — ScribeOS Flet Desktop Application (v2)
==================================================
Sidebar-navigation architecture with Studio + History tabs.

Layout
------
┌─────────────────────────────────────────────────────────┐
│  Sidebar (220px)  │  Main content area (expand)         │
│  ─────────────    │  ─────────────────────────────────  │
│  ⬡ ScribeOS       │  [Studio Tab]  OR  [History Tab]    │
│                   │                                      │
│  ● Studio         │                                      │
│  ◷ History        │                                      │
│                   │                                      │
│  ─── Settings ─── │                                      │
│  [API Key input]  │                                      │
│  [Save] [Load]    │                                      │
└─────────────────────────────────────────────────────────┘

Studio states:  IDLE → RECORDING → PROCESSING → DONE
History:        file list (left) + detail pane (right)
"""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import flet as ft

from core.ai_processor import AIProcessor
from core.audio_engine import AudioEngine
from core.logger import get_logger
from ui.components import (
    api_key_field,
    glossary_field,
    history_card,
    history_empty_state,
    nav_item,
    studio_empty_state,
    surface_card,
)
from ui.styles import (
    ACCENT_BRIGHT,
    ACCENT_MED,
    BG_CARD,
    BG_PAGE,
    BG_SURFACE,
    BORDER_RADIUS,
    BORDER_RADIUS_LG,
    BORDER_RADIUS_PILL,
    BORDER_RADIUS_SM,
    BORDER_SUBTLE,
    COLOR_MIC_LIVE,
    COLOR_MIC_MUTED,
    COLOR_RECORD_ACTIVE,
    COLOR_RECORD_IDLE,
    COLOR_STATUS_DEFAULT,
    COLOR_STATUS_ERROR,
    COLOR_STATUS_INFO,
    COLOR_STATUS_OK,
    COLOR_STATUS_WARN,
    FONT_BODY,
    FONT_SECTION,
    FONT_STATUS,
    MIC_ACTIVE,
    MIC_MUTED,
    MOM_BORDER,
    MOM_COLOR,
    NAV_WIDTH,
    PROCESSING_COLOR,
    RECORD_ACTIVE_BG,
    RECORD_ACTIVE_GLOW,
    RECORD_IDLE_BG,
    STATUS_DEFAULT,
    STATUS_OK,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from utlis.export_tools import export_mom, save_transcript_to_data
from utlis.security import is_valid_key, load_key, save_key

log = get_logger(__name__)

_BINARY_PATH  = str(Path(__file__).parent / "audio_bridge")
_DATA_DIR     = Path(__file__).parent / "data" / "transcripts"

# ── App states ─────────────────────────────────────────────────────────────────
_STATE_IDLE       = "idle"
_STATE_RECORDING  = "recording"
_STATE_PROCESSING = "processing"
_STATE_DONE       = "done"


class ScribeOSApp:
    """Application controller — sidebar nav, Studio + History tabs."""

    def __init__(self) -> None:
        self._audio_engine  : Optional[AudioEngine]  = None
        self._ai_processor  : Optional[AIProcessor]  = None

        self._state         : str  = _STATE_IDLE
        self._mic_muted     : bool = False
        self._mom_text      : str  = ""
        self._active_tab    : str  = "studio"     # "studio" | "history"
        self._selected_file : Optional[Path] = None

        self._page: Optional[ft.Page] = None

        # ── Control refs (set in _build_ui) ──────────────────────────────────
        self._api_key_field     : Optional[ft.TextField]    = None
        self._glossary_field    : Optional[ft.TextField]    = None
        self._nav_studio        : Optional[ft.Container]    = None
        self._nav_history       : Optional[ft.Container]    = None
        self._content_area      : Optional[ft.Container]    = None

        # Studio tab refs
        self._studio_view       : Optional[ft.Column]       = None
        self._record_btn        : Optional[ft.Container]    = None
        self._record_btn_text   : Optional[ft.Text]         = None
        self._record_btn_icon   : Optional[ft.Icon]         = None
        self._mute_btn          : Optional[ft.Container]    = None
        self._mute_btn_text     : Optional[ft.Text]         = None
        self._timer_row         : Optional[ft.Row]          = None
        self._timer_text        : Optional[ft.Text]         = None
        self._processing_overlay: Optional[ft.Container]    = None
        self._step1_card        : Optional[ft.Container]    = None
        self._step2_card        : Optional[ft.Container]    = None
        self._step1_ring        : Optional[ft.ProgressRing] = None
        self._step1_label       : Optional[ft.Text]         = None
        self._step2_label       : Optional[ft.Text]         = None
        self._transcript_pane   : Optional[ft.Container]    = None
        self._transcript_list   : Optional[ft.ListView]     = None
        self._transcript_empty  : Optional[ft.Container]    = None
        self._mom_section       : Optional[ft.Container]    = None
        self._mom_markdown      : Optional[ft.Markdown]     = None
        self._mom_btn           : Optional[ft.Container]    = None
        self._export_tx_btn     : Optional[ft.Container]    = None
        self._status_dot        : Optional[ft.Container]    = None
        self._status_text       : Optional[ft.Text]         = None

        # History tab refs
        self._history_view      : Optional[ft.Row]          = None
        self._history_list_col  : Optional[ft.ListView]     = None
        self._history_detail    : Optional[ft.Column]       = None
        self._history_empty_det : Optional[ft.Container]    = None
        self._history_title     : Optional[ft.Text]         = None
        self._history_content   : Optional[ft.Markdown]     = None
        self._history_mom_btn   : Optional[ft.Container]    = None
        self._history_del_btn   : Optional[ft.Container]    = None

    # ── Flet entry point ──────────────────────────────────────────────────────

    def main(self, page: ft.Page) -> None:
        self._page      = page
        page.title      = "ScribeOS"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor    = BG_PAGE
        page.padding    = 0

        try:
            page.window.width      = WINDOW_WIDTH
            page.window.height     = WINDOW_HEIGHT
            page.window.min_width  = 860
            page.window.min_height = 640
        except AttributeError:
            page.window_width  = WINDOW_WIDTH   # type: ignore[attr-defined]
            page.window_height = WINDOW_HEIGHT  # type: ignore[attr-defined]

        _DATA_DIR.mkdir(parents=True, exist_ok=True)

        page.add(self._build_ui())

        saved = load_key()
        if saved and self._api_key_field:
            self._api_key_field.value = saved
            page.update()

    # ── Top-level UI assembly ─────────────────────────────────────────────────

    def _build_ui(self) -> ft.Row:
        sidebar   = self._build_sidebar()
        self._content_area = ft.Container(expand=True, content=self._build_studio_tab())

        return ft.Row(
            controls=[sidebar, self._content_area],
            spacing=0,
            expand=True,
        )

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> ft.Container:
        logo = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(ft.Icons.GRAPHIC_EQ_ROUNDED, size=16, color=ACCENT_BRIGHT),
                    bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.WHITE),
                    border_radius=BORDER_RADIUS_SM,
                    padding=ft.Padding.all(7),
                ),
                ft.Column(
                    controls=[
                        ft.Text("ScribeOS", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        ft.Text(
                            "AI TRANSCRIPTION",
                            size=8,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.with_opacity(0.28, ft.Colors.WHITE),
                            style=ft.TextStyle(letter_spacing=1.2),
                        ),
                    ],
                    spacing=1,
                    tight=True,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Nav items built as plain containers so we can swap active state
        self._nav_studio = self._make_nav_item(
            ft.Icons.FIBER_MANUAL_RECORD_ROUNDED, "Studio", active=True,
            on_click=lambda _: self._switch_tab("studio"),
        )
        self._nav_history = self._make_nav_item(
            ft.Icons.HISTORY_ROUNDED, "History", active=False,
            on_click=lambda _: self._switch_tab("history"),
        )

        nav_section = ft.Column(
            controls=[
                ft.Text(
                    "WORKSPACE",
                    size=9,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.with_opacity(0.25, ft.Colors.WHITE),
                    style=ft.TextStyle(letter_spacing=1.3),
                ),
                self._nav_studio,
                self._nav_history,
            ],
            spacing=2,
        )

        # API key at bottom of sidebar
        self._api_key_field = api_key_field()

        def _icon_btn(icon, tooltip, on_click):
            return ft.IconButton(
                icon=icon,
                icon_color=ft.Colors.with_opacity(0.40, ft.Colors.WHITE),
                icon_size=15,
                tooltip=tooltip,
                on_click=on_click,
                style=ft.ButtonStyle(
                    shape=ft.CircleBorder(),
                    overlay_color=ft.Colors.with_opacity(0.07, ft.Colors.WHITE),
                ),
            )

        settings_section = ft.Column(
            controls=[
                ft.Text(
                    "SETTINGS",
                    size=9,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.with_opacity(0.25, ft.Colors.WHITE),
                    style=ft.TextStyle(letter_spacing=1.3),
                ),
                self._api_key_field,
                ft.Row(
                    controls=[
                        _icon_btn(ft.Icons.SAVE_ROUNDED, "Save key to Keychain", self._save_key),
                        _icon_btn(ft.Icons.LOCK_OPEN_ROUNDED, "Load key from Keychain", self._load_key),
                        ft.Container(expand=True),
                        ft.Text("Gemini 2.5 Flash", size=9, color=ft.Colors.with_opacity(0.22, ft.Colors.WHITE), italic=True),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=6,
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    logo,
                    ft.Container(height=20),
                    nav_section,
                    ft.Container(expand=True),
                    ft.Divider(height=1, color=BORDER_SUBTLE),
                    settings_section,
                ],
                spacing=0,
                expand=True,
            ),
            width=NAV_WIDTH,
            bgcolor=BG_SURFACE,
            border=ft.Border.only(right=ft.BorderSide(1, BORDER_SUBTLE)),
            padding=ft.Padding.all(16),
        )

    def _make_nav_item(self, icon, label, active=False, on_click=None) -> ft.Container:
        icon_color   = ACCENT_BRIGHT if active else ft.Colors.with_opacity(0.4, ft.Colors.WHITE)
        label_color  = TEXT_PRIMARY if active else TEXT_SECONDARY
        bg           = ft.Colors.with_opacity(0.08, ft.Colors.WHITE) if active else ft.Colors.TRANSPARENT

        return ft.Container(
            data=label,
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=15, color=icon_color),
                    ft.Text(label, size=13, weight=ft.FontWeight.W_500 if active else ft.FontWeight.W_400, color=label_color),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=bg,
            border_radius=BORDER_RADIUS_SM,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            on_click=on_click,
            ink=True,
        )

    def _switch_tab(self, tab: str) -> None:
        if tab == self._active_tab:
            return
        self._active_tab = tab

        # Update nav highlight
        def _style_nav(container: ft.Container, is_active: bool) -> None:
            row: ft.Row = container.content
            icon_ctrl: ft.Icon  = row.controls[0]
            text_ctrl: ft.Text  = row.controls[1]
            icon_ctrl.color  = ACCENT_BRIGHT if is_active else ft.Colors.with_opacity(0.4, ft.Colors.WHITE)
            text_ctrl.color  = TEXT_PRIMARY  if is_active else TEXT_SECONDARY
            text_ctrl.weight = ft.FontWeight.W_500 if is_active else ft.FontWeight.W_400
            container.bgcolor= ft.Colors.with_opacity(0.08, ft.Colors.WHITE) if is_active else ft.Colors.TRANSPARENT

        _style_nav(self._nav_studio,  tab == "studio")
        _style_nav(self._nav_history, tab == "history")

        if tab == "studio":
            self._content_area.content = self._build_studio_tab()
        else:
            self._content_area.content = self._build_history_tab()

        self._page.update()

    # ── Studio Tab ────────────────────────────────────────────────────────────

    def _build_studio_tab(self) -> ft.Column:
        _pill = ft.RoundedRectangleBorder(radius=BORDER_RADIUS_PILL)

        # ── Glossary input section ────────────────────────────────────────────
        self._glossary_field = glossary_field()

        glossary_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.NOTES_ROUNDED, size=14, color=ACCENT_BRIGHT),
                            ft.Text(
                                "MEETING CONTEXT & GLOSSARY",
                                size=FONT_SECTION,
                                weight=ft.FontWeight.W_700,
                                color=TEXT_MUTED,
                                style=ft.TextStyle(letter_spacing=1.4),
                            ),
                            ft.Container(expand=True),
                            ft.Text("Optional", size=10, color=ft.Colors.with_opacity(0.25, ft.Colors.WHITE), italic=True),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._glossary_field,
                ],
                spacing=10,
                tight=True,
            ),
            bgcolor=BG_CARD,
            border=ft.Border.all(1, BORDER_SUBTLE),
            border_radius=BORDER_RADIUS_LG,
            padding=ft.Padding.all(16),
            shadow=ft.BoxShadow(blur_radius=12, color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK), offset=ft.Offset(0, 2)),
        )

        # ── Recording controls ────────────────────────────────────────────────
        self._record_btn_icon = ft.Icon(ft.Icons.FIBER_MANUAL_RECORD_ROUNDED, size=16, color="#ffffff")
        self._record_btn_text = ft.Text("Start Recording", size=14, weight=ft.FontWeight.W_600, color="#ffffff")

        self._record_btn = ft.Container(
            content=ft.Row(
                controls=[self._record_btn_icon, self._record_btn_text],
                spacing=8,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=RECORD_IDLE_BG,
            border_radius=BORDER_RADIUS_PILL,
            padding=ft.Padding.symmetric(horizontal=28, vertical=14),
            on_click=self._toggle_recording,
            ink=True,
            shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.with_opacity(0.4, RECORD_IDLE_BG), offset=ft.Offset(0, 4)),
        )

        self._mute_btn_text = ft.Text("Mute Mic", size=13, color="#ffffff")
        self._mute_btn = ft.Container(
            content=ft.Row(
                controls=[ft.Icon(ft.Icons.MIC_ROUNDED, size=14, color="#ffffff"), self._mute_btn_text],
                spacing=6, tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=MIC_ACTIVE,
            border_radius=BORDER_RADIUS_PILL,
            padding=ft.Padding.symmetric(horizontal=18, vertical=12),
            on_click=self._toggle_mic,
            ink=True,
            visible=False,
        )

        self._timer_text = ft.Text("0:00", size=22, weight=ft.FontWeight.W_700, color=TEXT_PRIMARY)
        rec_dot = ft.Container(
            width=9, height=9,
            bgcolor=RECORD_ACTIVE_GLOW,
            border_radius=5,
        )
        self._timer_row = ft.Row(
            controls=[rec_dot, self._timer_text],
            spacing=8,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        controls_row = ft.Row(
            controls=[
                ft.Container(expand=True),
                self._record_btn,
                self._mute_btn,
                self._timer_row,
                ft.Container(expand=True),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
        )

        # ── Processing overlay — two live step cards ─────────────────────────
        self._step1_ring  = ft.ProgressRing(width=14, height=14, stroke_width=2, color=PROCESSING_COLOR)
        self._step1_label = ft.Text("In progress…", size=9, color=PROCESSING_COLOR)
        self._step2_label = ft.Text("Waiting…",     size=9, color=TEXT_MUTED)

        self._step1_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            self._step1_ring,
                            ft.Text("Step 1 — Acoustic", size=11, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text("Transcribing audio to generic labels", size=9, color=TEXT_SECONDARY),
                    self._step1_label,
                ],
                spacing=4,
                tight=True,
            ),
            bgcolor=ft.Colors.with_opacity(0.08, PROCESSING_COLOR),
            border=ft.Border.all(1, PROCESSING_COLOR),
            border_radius=BORDER_RADIUS,
            padding=ft.Padding.all(10),
            expand=True,
        )

        self._step2_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.MANAGE_SEARCH_ROUNDED, size=14, color=TEXT_MUTED),
                            ft.Text("Step 2 — Speaker ID", size=11, weight=ft.FontWeight.W_600, color=TEXT_MUTED),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text("Resolving real names from context", size=9, color=TEXT_MUTED),
                    self._step2_label,
                ],
                spacing=4,
                tight=True,
            ),
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            border=ft.Border.all(1, BORDER_SUBTLE),
            border_radius=BORDER_RADIUS,
            padding=ft.Padding.all(10),
            expand=True,
        )

        self._processing_overlay = ft.Container(
            content=ft.Column(
                controls=[
                    ft.ProgressRing(width=44, height=44, stroke_width=3, color=PROCESSING_COLOR),
                    ft.Text(
                        "Gemini is analyzing your meeting…",
                        size=15,
                        weight=ft.FontWeight.W_500,
                        color=TEXT_PRIMARY,
                    ),
                    ft.Text(
                        "This usually takes 30–90 seconds. Please wait.",
                        size=11,
                        color=TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Row(
                        controls=[self._step1_card, self._step2_card],
                        spacing=12,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=16,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            visible=False,
            bgcolor=BG_PAGE,
        )

        # ── Transcript area ───────────────────────────────────────────────────
        self._transcript_empty  = studio_empty_state()
        self._transcript_list   = ft.ListView(spacing=6, auto_scroll=True, padding=ft.Padding.all(2))

        transcript_stack = ft.Stack(
            controls=[
                self._transcript_empty,
                ft.Container(content=self._transcript_list, expand=True),
                self._processing_overlay,
            ],
            expand=True,
        )

        self._transcript_pane = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(width=6, height=6, bgcolor=STATUS_OK, border_radius=3),
                            ft.Text("TRANSCRIPT", size=FONT_SECTION, weight=ft.FontWeight.W_700,
                                    color=TEXT_MUTED, style=ft.TextStyle(letter_spacing=1.4)),
                            ft.Container(expand=True),
                            ft.Text("Gemini 2.5 Flash", size=9, color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE), italic=True),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    transcript_stack,
                ],
                spacing=12,
                expand=True,
            ),
            bgcolor=BG_CARD,
            border=ft.Border.all(1, BORDER_SUBTLE),
            border_radius=BORDER_RADIUS_LG,
            padding=ft.Padding.all(20),
            expand=True,
            shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK), offset=ft.Offset(0, 4)),
        )

        # ── MOM section ───────────────────────────────────────────────────────
        self._mom_markdown = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            expand=True,
        )

        self._mom_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(width=6, height=6, bgcolor=MOM_COLOR, border_radius=3),
                            ft.Text("MINUTES OF MEETING", size=FONT_SECTION, weight=ft.FontWeight.W_700,
                                    color=MOM_COLOR, style=ft.TextStyle(letter_spacing=1.4)),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=ft.Column(controls=[self._mom_markdown], scroll=ft.ScrollMode.AUTO),
                        expand=True,
                    ),
                ],
                spacing=12,
                expand=True,
            ),
            bgcolor=BG_CARD,
            border=ft.Border.all(1, MOM_BORDER),
            border_radius=BORDER_RADIUS_LG,
            padding=ft.Padding.all(20),
            visible=False,
            height=260,
            shadow=ft.BoxShadow(blur_radius=16, color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK), offset=ft.Offset(0, 3)),
        )

        # ── Action buttons ────────────────────────────────────────────────────
        def _action_btn(label, icon, onclick, color=ACCENT_MED):
            return ft.Container(
                content=ft.Row(
                    controls=[ft.Icon(icon, size=13, color="#ffffff"), ft.Text(label, size=12, color="#ffffff")],
                    spacing=6, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=color,
                border_radius=BORDER_RADIUS_PILL,
                padding=ft.Padding.symmetric(horizontal=14, vertical=9),
                on_click=onclick,
                ink=True,
            )

        self._mom_btn = _action_btn("Generate MOM", ft.Icons.AUTO_AWESOME_ROUNDED, self._generate_mom, "#4f46e5")
        self._export_tx_btn = _action_btn("Save Transcript", ft.Icons.SAVE_ROUNDED, self._export_transcript, "#1e3a5f")
        self._mom_btn.visible       = False
        self._export_tx_btn.visible = False

        action_row = ft.Row(
            controls=[
                ft.Container(expand=True),
                self._export_tx_btn,
                self._mom_btn,
            ],
            spacing=8,
        )

        # ── Status bar ────────────────────────────────────────────────────────
        self._status_dot  = ft.Container(width=6, height=6, bgcolor=STATUS_DEFAULT, border_radius=3)
        self._status_text = ft.Text("Ready", size=FONT_STATUS, color=STATUS_DEFAULT)

        status_bar = ft.Container(
            content=ft.Row(
                controls=[self._status_dot, self._status_text],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=0, vertical=4),
        )

        self._studio_view = ft.Column(
            controls=[
                ft.Container(
                    content=ft.Text("New Session", size=22, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    padding=ft.Padding.only(bottom=4),
                ),
                glossary_card,
                controls_row,
                self._transcript_pane,
                self._mom_section,
                action_row,
                status_bar,
            ],
            spacing=12,
            expand=True,
        )

        return ft.Container(
            content=self._studio_view,
            expand=True,
            padding=ft.Padding.all(24),
        )

    # ── History Tab ───────────────────────────────────────────────────────────

    def _build_history_tab(self) -> ft.Container:
        self._history_list_col = ft.ListView(spacing=0, expand=True)
        self._history_title    = ft.Text("", size=15, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY)
        self._history_content  = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            expand=True,
        )
        self._history_empty_det = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.TOUCH_APP_ROUNDED, size=48, color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
                    ft.Text("Select a session", size=14, color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE)),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

        def _hist_action_btn(label, icon, onclick, color=ACCENT_MED):
            return ft.Container(
                content=ft.Row(
                    controls=[ft.Icon(icon, size=13, color="#ffffff"), ft.Text(label, size=12, color="#ffffff")],
                    spacing=6, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=color,
                border_radius=BORDER_RADIUS_PILL,
                padding=ft.Padding.symmetric(horizontal=14, vertical=9),
                on_click=onclick,
                ink=True,
            )

        self._history_mom_btn = _hist_action_btn("Export MOM to PDF", ft.Icons.PICTURE_AS_PDF_ROUNDED, self._history_export_mom, "#4f46e5")
        self._history_del_btn = _hist_action_btn("Delete Session", ft.Icons.DELETE_OUTLINE_ROUNDED, self._history_delete, "#7f1d1d")
        self._history_mom_btn.visible = False
        self._history_del_btn.visible = False

        detail_pane = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            self._history_title,
                            ft.Container(expand=True),
                            self._history_mom_btn,
                            self._history_del_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    ft.Divider(height=1, color=BORDER_SUBTLE),
                    ft.Container(
                        content=ft.Column(
                            controls=[self._history_empty_det, ft.Container(content=self._history_content, expand=True)],
                            expand=True,
                        ),
                        expand=True,
                    ),
                ],
                spacing=12,
                expand=True,
            ),
            bgcolor=BG_CARD,
            border=ft.Border.all(1, BORDER_SUBTLE),
            border_radius=BORDER_RADIUS_LG,
            padding=ft.Padding.all(20),
            expand=True,
            shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK), offset=ft.Offset(0, 4)),
        )

        list_pane = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.HISTORY_ROUNDED, size=14, color=ACCENT_BRIGHT),
                            ft.Text("SESSIONS", size=FONT_SECTION, weight=ft.FontWeight.W_700,
                                    color=TEXT_MUTED, style=ft.TextStyle(letter_spacing=1.4)),
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.REFRESH_ROUNDED,
                                icon_size=14,
                                icon_color=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
                                tooltip="Refresh",
                                on_click=lambda _: self._reload_history(),
                                style=ft.ButtonStyle(shape=ft.CircleBorder()),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._history_list_col,
                ],
                spacing=10,
                expand=True,
            ),
            bgcolor=BG_CARD,
            border=ft.Border.all(1, BORDER_SUBTLE),
            border_radius=BORDER_RADIUS_LG,
            padding=ft.Padding.all(16),
            width=280,
            shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK), offset=ft.Offset(0, 4)),
        )

        self._history_view = ft.Row(
            controls=[list_pane, detail_pane],
            spacing=14,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        self._reload_history()

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Text("History", size=22, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        padding=ft.Padding.only(bottom=4),
                    ),
                    self._history_view,
                ],
                spacing=12,
                expand=True,
            ),
            expand=True,
            padding=ft.Padding.all(24),
        )

    # ── History logic ─────────────────────────────────────────────────────────

    def _reload_history(self) -> None:
        if not self._history_list_col:
            return
        self._history_list_col.controls.clear()

        files = sorted(_DATA_DIR.glob("*.txt"), reverse=True)
        if not files:
            self._history_list_col.controls.append(history_empty_state())
        else:
            for f in files:
                preview = ""
                try:
                    preview = f.read_text(encoding="utf-8")[:120].replace("\n", " ")
                except Exception:
                    pass
                ts_str = f.stem.replace("ScribeOS_Transcript_", "")
                try:
                    dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                    label = dt.strftime("%b %d, %Y  %H:%M")
                except ValueError:
                    label = ts_str

                path_ref = f
                self._history_list_col.controls.append(
                    history_card(
                        title=label,
                        preview=preview,
                        on_click=lambda _, p=path_ref: self._load_session(p),
                        active=(f == self._selected_file),
                    )
                )

        # Only update if the control is already mounted on the page tree
        try:
            mounted = self._history_list_col.page is not None
        except RuntimeError:
            mounted = False
        if self._page and mounted:
            self._page.update()

    def _load_session(self, path: Path) -> None:
        self._selected_file = path
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            text = f"[Error reading file: {exc}]"

        ts_str = path.stem.replace("ScribeOS_Transcript_", "")
        try:
            dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            label = dt.strftime("%b %d, %Y  %H:%M")
        except ValueError:
            label = ts_str

        self._history_title.value          = label
        self._history_content.value        = f"```\n{text}\n```"
        self._history_empty_det.visible    = False
        self._history_mom_btn.visible      = True
        self._history_del_btn.visible      = True

        self._reload_history()   # refreshes active state in list
        if self._page:
            self._page.update()

    def _history_export_mom(self, _: ft.ControlEvent) -> None:
        if not self._selected_file:
            return
        # To export MOM from history we need Gemini — use a fresh AIProcessor
        api_key = (self._api_key_field.value or "").strip()
        if not api_key:
            return

        try:
            text = self._selected_file.read_text(encoding="utf-8")
        except Exception:
            return

        self._history_mom_btn.visible = False
        if self._page:
            self._page.update()

        def _work():
            try:
                proc = AIProcessor(api_key)
                import threading as _t
                with proc._lock:
                    proc._full_transcript = text
                mom = proc.generate_mom()
                path = export_mom(mom)
                if self._page:
                    # briefly flash status if we're on studio tab
                    pass
                log.info("History MOM exported → %s", path)
            except Exception as exc:
                log.error("History MOM export error: %s", exc)
            finally:
                if self._history_mom_btn and self._page:
                    self._history_mom_btn.visible = True
                    self._page.update()

        threading.Thread(target=_work, daemon=True).start()

    def _history_delete(self, _: ft.ControlEvent) -> None:
        if not self._selected_file:
            return
        try:
            self._selected_file.unlink()
        except Exception:
            pass
        self._selected_file = None
        if self._history_title:
            self._history_title.value = ""
        if self._history_content:
            self._history_content.value = ""
        if self._history_empty_det:
            self._history_empty_det.visible = True
        if self._history_mom_btn:
            self._history_mom_btn.visible = False
        if self._history_del_btn:
            self._history_del_btn.visible = False
        self._reload_history()
        if self._page:
            self._page.update()

    # ── Recording state machine ───────────────────────────────────────────────

    def _set_state(self, state: str) -> None:
        self._state = state
        if state == _STATE_IDLE:
            self._record_btn_text.value  = "Start Recording"
            self._record_btn_icon.name   = ft.Icons.FIBER_MANUAL_RECORD_ROUNDED
            self._record_btn.bgcolor     = RECORD_IDLE_BG
            self._record_btn.shadow      = ft.BoxShadow(blur_radius=20, color=ft.Colors.with_opacity(0.4, RECORD_IDLE_BG), offset=ft.Offset(0, 4))
            self._mute_btn.visible       = False
            self._timer_row.visible      = False
            self._processing_overlay.visible = False

        elif state == _STATE_RECORDING:
            self._record_btn_text.value  = "Stop Recording"
            self._record_btn_icon.name   = ft.Icons.STOP_ROUNDED
            self._record_btn.bgcolor     = RECORD_ACTIVE_BG
            self._record_btn.shadow      = ft.BoxShadow(blur_radius=24, color=ft.Colors.with_opacity(0.5, RECORD_ACTIVE_BG), offset=ft.Offset(0, 4))
            self._mute_btn.visible       = True
            self._timer_row.visible      = True
            self._processing_overlay.visible = False
            self._mom_btn.visible        = False
            self._export_tx_btn.visible  = False
            if self._mom_section:
                self._mom_section.visible = False
            if self._timer_text:
                self._timer_text.value = "0:00"

        elif state == _STATE_PROCESSING:
            self._record_btn_text.value  = "Processing…"
            self._record_btn_icon.name   = ft.Icons.HOURGLASS_TOP_ROUNDED
            self._record_btn.bgcolor     = "#374151"
            self._record_btn.shadow      = None
            self._mute_btn.visible       = False
            self._timer_row.visible      = False
            self._processing_overlay.visible = True
            self._transcript_empty.visible   = False

        elif state == _STATE_DONE:
            self._record_btn_text.value  = "Start Recording"
            self._record_btn_icon.name   = ft.Icons.FIBER_MANUAL_RECORD_ROUNDED
            self._record_btn.bgcolor     = RECORD_IDLE_BG
            self._record_btn.shadow      = ft.BoxShadow(blur_radius=20, color=ft.Colors.with_opacity(0.4, RECORD_IDLE_BG), offset=ft.Offset(0, 4))
            self._mute_btn.visible       = False
            self._timer_row.visible      = False
            self._processing_overlay.visible = False
            self._mom_btn.visible        = True
            self._export_tx_btn.visible  = True

    def _toggle_recording(self, _: ft.ControlEvent) -> None:
        if self._state == _STATE_RECORDING:
            self._stop_recording()
        elif self._state == _STATE_IDLE or self._state == _STATE_DONE:
            self._start_recording()

    def _start_recording(self) -> None:
        api_key = (self._api_key_field.value or "").strip()
        if not api_key:
            self._set_status("Please enter your Gemini API key.", COLOR_STATUS_ERROR)
            return

        if not is_valid_key(api_key):
            self._set_status("API key format looks invalid (should start with 'AIza').", COLOR_STATUS_WARN)

        if not Path(_BINARY_PATH).exists():
            self._set_status(
                "audio_bridge binary not found. Run: swiftc audio_bridge.swift -o audio_bridge -framework ScreenCaptureKit",
                COLOR_STATUS_ERROR,
            )
            return

        try:
            self._ai_processor = AIProcessor(api_key)
        except ValueError as exc:
            self._set_status(str(exc), COLOR_STATUS_ERROR)
            return

        # Parse glossary → known names for the acoustic agent (optional)
        glossary = (self._glossary_field.value or "").strip()
        if glossary and self._ai_processor:
            import re
            # Split on commas or newlines; keep all non-empty tokens regardless of case
            raw_names = re.split(r"[,\n]+", glossary)
            self._ai_processor.known_names = [n.strip() for n in raw_names if n.strip()]

        self._audio_engine = AudioEngine(_BINARY_PATH)
        try:
            self._audio_engine.start(mic_muted=self._mic_muted)
        except FileNotFoundError as exc:
            self._set_status(str(exc), COLOR_STATUS_ERROR)
            self._audio_engine = None
            return

        self._set_state(_STATE_RECORDING)
        self._set_status("Recording…", COLOR_STATUS_OK)
        if self._page:
            self._page.update()
        self._page.run_task(self._recording_timer)
        log.info("Recording started")

    async def _recording_timer(self) -> None:
        start = time.monotonic()
        while self._state == _STATE_RECORDING:
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, 60)
            if self._timer_text:
                self._timer_text.value = f"{mins}:{secs:02d}"
                self._timer_text.update()
            await asyncio.sleep(1)

    def _stop_recording(self) -> None:
        self._set_state(_STATE_PROCESSING)
        self._set_status("Sending audio to Gemini…", COLOR_STATUS_INFO)
        if self._page:
            self._page.update()

        full_wav: Optional[bytes] = None
        if self._audio_engine:
            full_wav = self._audio_engine.stop()
            self._audio_engine = None

        def _transcribe() -> None:
            if full_wav and self._ai_processor:
                self._set_status("Step 1: acoustic transcription…", COLOR_STATUS_INFO)
                self._ai_processor.transcribe_chunk(
                    full_wav,
                    self._on_transcript_ready,
                    on_step=self._update_pipeline_step,
                )
            else:
                self._on_transcript_ready("[No audio captured]")

        threading.Thread(target=_transcribe, daemon=True).start()
        log.info("Recording stopped — processing in progress")

    def _on_transcript_ready(self, text: str) -> None:
        self._append_transcript(text)

        # Auto-save transcript
        if self._ai_processor:
            full = self._ai_processor.full_transcript
            if full.strip():
                try:
                    path = save_transcript_to_data(full)
                    log.info("Transcript auto-saved → %s", path)
                except Exception as exc:
                    log.warning("Transcript auto-save failed: %s", exc)

        self._set_state(_STATE_DONE)
        self._set_status("Transcript ready.", COLOR_STATUS_OK)
        if self._page:
            self._page.update()
        log.info("Transcription complete")

    def _update_pipeline_step(self, step: int) -> None:
        """Called from background thread when pipeline transitions to step 2."""
        if step == 2 and self._step1_card and self._step2_card:
            # Mark step 1 complete
            self._step1_ring.visible     = False
            self._step1_label.value      = "Complete ✓"
            self._step1_label.color      = COLOR_STATUS_OK
            self._step1_card.bgcolor     = ft.Colors.with_opacity(0.06, COLOR_STATUS_OK)
            self._step1_card.border      = ft.Border.all(1, COLOR_STATUS_OK)
            # Activate step 2
            self._step2_label.value      = "In progress…"
            self._step2_label.color      = PROCESSING_COLOR
            self._step2_card.bgcolor     = ft.Colors.with_opacity(0.08, PROCESSING_COLOR)
            self._step2_card.border      = ft.Border.all(1, PROCESSING_COLOR)
            step2_row: ft.Row  = self._step2_card.content.controls[0]
            step2_icon: ft.Icon = step2_row.controls[0]
            step2_icon.color  = PROCESSING_COLOR
            self._set_status("Step 2: speaker identification…", COLOR_STATUS_INFO)
        if self._page:
            self._page.update()

    # ── Mic toggle ────────────────────────────────────────────────────────────

    def _toggle_mic(self, _: ft.ControlEvent) -> None:
        self._mic_muted = not self._mic_muted
        if self._audio_engine:
            self._audio_engine.set_mic_muted(self._mic_muted)

        mic_icon: ft.Icon = self._mute_btn.content.controls[0]
        mic_icon.name        = ft.Icons.MIC_OFF_ROUNDED if self._mic_muted else ft.Icons.MIC_ROUNDED
        self._mute_btn_text.value = "Unmute Mic" if self._mic_muted else "Mute Mic"
        self._mute_btn.bgcolor    = MIC_MUTED if self._mic_muted else MIC_ACTIVE
        self._set_status(
            "Mic muted." if self._mic_muted else "Mic live.",
            COLOR_STATUS_WARN if self._mic_muted else COLOR_STATUS_OK,
        )

    # ── MOM generation ────────────────────────────────────────────────────────

    def _generate_mom(self, _: ft.ControlEvent) -> None:
        if not self._ai_processor:
            return
        self._mom_btn.bgcolor = "#374151"
        self._set_status("Generating Minutes of Meeting…", COLOR_STATUS_INFO)
        if self._page:
            self._page.update()

        def _work() -> None:
            mom = self._ai_processor.generate_mom()
            self._mom_text               = mom
            self._mom_markdown.value     = mom
            self._mom_section.visible    = True
            self._mom_btn.bgcolor        = "#4f46e5"

            try:
                path = export_mom(mom)
                self._set_status(f"MOM ready → saved to Desktop ✔", COLOR_STATUS_OK)
            except Exception as exc:
                self._set_status(f"MOM ready (save failed: {exc})", COLOR_STATUS_WARN)

            if self._page:
                self._page.update()

        threading.Thread(target=_work, daemon=True).start()

    # ── Transcript helpers ────────────────────────────────────────────────────

    def _append_transcript(self, text: str) -> None:
        if not text.strip() or not self._transcript_list or not self._page:
            return
        if self._transcript_empty:
            self._transcript_empty.visible = False

        self._transcript_list.controls.append(
            ft.Container(
                content=ft.Markdown(
                    value=text,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                ),
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                border_radius=BORDER_RADIUS,
                bgcolor=ft.Colors.with_opacity(0.035, ft.Colors.WHITE),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.05, ft.Colors.WHITE)),
            )
        )
        self._page.update()

    # ── Status bar helper ────────────────────────────────────────────────────

    def _set_status(self, message: str, color: str = COLOR_STATUS_DEFAULT) -> None:
        if self._status_text and self._page:
            self._status_text.value  = message
            self._status_text.color  = color
            if self._status_dot:
                self._status_dot.bgcolor = color
            self._page.update()

    # ── Keychain handlers ─────────────────────────────────────────────────────

    def _save_key(self, _: ft.ControlEvent) -> None:
        key = (self._api_key_field.value or "").strip()
        if save_key(key):
            self._set_status("API key saved to Keychain.", COLOR_STATUS_OK)
        else:
            self._set_status("Could not save key.", COLOR_STATUS_WARN)

    def _load_key(self, _: ft.ControlEvent) -> None:
        key = load_key()
        if key:
            self._api_key_field.value = key
            self._set_status("API key loaded from Keychain.", COLOR_STATUS_OK)
            if self._page:
                self._page.update()
        else:
            self._set_status("No saved key found.", COLOR_STATUS_WARN)

    # ── Export handlers ───────────────────────────────────────────────────────

    def _export_transcript(self, _: ft.ControlEvent) -> None:
        if not self._ai_processor:
            return
        text = self._ai_processor.full_transcript
        if not text.strip():
            self._set_status("Nothing to export yet.", COLOR_STATUS_WARN)
            return
        try:
            path = save_transcript_to_data(text)
            self._set_status(f"Transcript saved → {path}", COLOR_STATUS_OK)
        except OSError as exc:
            self._set_status(f"Export failed: {exc}", COLOR_STATUS_ERROR)


# ── Application entry point ───────────────────────────────────────────────────

def main() -> None:
    app = ScribeOSApp()
    ft.run(app.main)


if __name__ == "__main__":
    main()
