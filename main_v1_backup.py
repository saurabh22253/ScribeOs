"""
main.py — ScribeOS Flet Desktop Application
=============================================
Entry point for the ScribeOS desktop UI.

Layout (new premium design)
-----------------------------
  ┌──────────────────────────────────────────────────────────┐
  │  ⬡ ScribeOS      AI TRANSCRIPTION     [key ••••] [🔑][💾]│  ← top bar
  ├──────────────────────────────────────────────────────────┤
  │  ┌── TRANSCRIPT ──────────────────────────────────────┐  │
  │  │  (empty state / transcript lines)                  │  │  ← main card, expand
  │  └────────────────────────────────────────────────────┘  │
  │  ┌── MINUTES OF MEETING ──────────────────────────────┐  │
  │  │  (Markdown MOM — hidden until generated)           │  │  ← fixed 260 px
  │  └────────────────────────────────────────────────────┘  │
  │  ┌── control dock ────────────────────────────────────┐  │
  │  │  [● Start Scribing] [🎙 Mute]  ·  0:23  ·  [MOM]  │  │
  │  └────────────────────────────────────────────────────┘  │
  │  ● Ready                     ScribeOS · Gemini 2.5 Flash  │  ← status bar
  └──────────────────────────────────────────────────────────┘

Threading model
---------------
* Background threads from AudioEngine / AIProcessor call page.update() safely.
* All UI mutation touches named control references set in _build_ui().
"""

from __future__ import annotations

import asyncio
import time
import threading
from pathlib import Path
from typing import Optional

import flet as ft

from core.ai_processor import AIProcessor
from core.audio_engine import AudioEngine
from core.logger import get_logger
from ui.components import api_key_field, transcript_empty_state
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
    BORDER_RADIUS_PILL,
    BORDER_RADIUS_SM,
    BORDER_SUBTLE,
    COLOR_MIC_LIVE,
    COLOR_MIC_MUTED,
    COLOR_MOM_ACCENT,
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
    RECORD_ACTIVE_BG,
    RECORD_ACTIVE_GLOW,
    RECORD_IDLE_BG,
    STATUS_DEFAULT,
    STATUS_ERROR,
    STATUS_INFO,
    STATUS_OK,
    STATUS_WARN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from utlis.export_tools import export_mom, export_transcription
from utlis.security import is_valid_key, load_key, save_key

log = get_logger(__name__)

_BINARY_PATH = str(Path(__file__).parent / "audio_bridge")


class ScribeOSApp:
    """Application controller — owns all state, wires all subsystems."""

    def __init__(self) -> None:
        self._audio_engine : Optional[AudioEngine]  = None
        self._ai_processor : Optional[AIProcessor]  = None

        self._is_recording : bool = False
        self._mic_muted    : bool = False
        self._mom_text     : str  = ""

        self._page: Optional[ft.Page] = None

        # ── Named control references (populated in _build_ui) ────────────────
        self._api_key_field  : Optional[ft.TextField]   = None
        self._start_stop_btn : Optional[ft.FilledButton] = None
        self._mute_btn       : Optional[ft.FilledButton] = None
        self._mom_btn        : Optional[ft.FilledButton] = None
        self._export_tx_btn  : Optional[ft.TextButton]   = None
        self._export_mom_btn : Optional[ft.TextButton]   = None
        self._status_text    : Optional[ft.Text]         = None
        self._status_dot     : Optional[ft.Container]    = None
        self._transcript_list: Optional[ft.ListView]     = None
        self._mom_markdown   : Optional[ft.Markdown]     = None
        self._mom_section    : Optional[ft.Container]    = None
        self._empty_state    : Optional[ft.Container]    = None
        self._timer_text     : Optional[ft.Text]         = None
        self._timer_display  : Optional[ft.Container]    = None

    # ── Flet entry point ──────────────────────────────────────────────────────

    def main(self, page: ft.Page) -> None:
        self._page       = page
        page.title       = "ScribeOS"
        page.theme_mode  = ft.ThemeMode.DARK
        page.bgcolor     = BG_PAGE
        page.padding     = 0        # sections manage their own padding

        try:
            page.window.width      = WINDOW_WIDTH
            page.window.height     = WINDOW_HEIGHT
            page.window.min_width  = 800
            page.window.min_height = 620
        except AttributeError:
            page.window_width  = WINDOW_WIDTH   # type: ignore[attr-defined]
            page.window_height = WINDOW_HEIGHT  # type: ignore[attr-defined]

        page.add(self._build_ui())

        saved = load_key()
        if saved and self._api_key_field:
            self._api_key_field.value = saved
            page.update()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> ft.Column:

        # ══════════════════════════════════════════════════════════════════════
        # TOP BAR
        # ══════════════════════════════════════════════════════════════════════

        logo = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(ft.Icons.GRAPHIC_EQ_ROUNDED, size=17, color=ACCENT_BRIGHT),
                    bgcolor=ft.Colors.with_opacity(0.14, ft.Colors.WHITE),
                    border_radius=BORDER_RADIUS_SM,
                    padding=ft.Padding.all(8),
                ),
                ft.Column(
                    controls=[
                        ft.Text("ScribeOS", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        ft.Text(
                            "AI TRANSCRIPTION",
                            size=9,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.with_opacity(0.30, ft.Colors.WHITE),
                            style=ft.TextStyle(letter_spacing=1.3),
                        ),
                    ],
                    spacing=1,
                    tight=True,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._api_key_field = api_key_field()

        def _icon_btn(icon, tooltip, on_click) -> ft.IconButton:
            return ft.IconButton(
                icon=icon,
                icon_color=ft.Colors.with_opacity(0.45, ft.Colors.WHITE),
                icon_size=17,
                tooltip=tooltip,
                on_click=on_click,
                style=ft.ButtonStyle(
                    shape=ft.CircleBorder(),
                    overlay_color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
                ),
            )

        top_bar = ft.Container(
            content=ft.Row(
                controls=[
                    logo,
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                self._api_key_field,
                                _icon_btn(ft.Icons.SAVE_ROUNDED, "Save to Keychain", self._save_key),
                                _icon_btn(ft.Icons.LOCK_OPEN_ROUNDED, "Load from Keychain", self._load_key),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        width=430,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=BG_SURFACE,
            border=ft.Border.only(bottom=ft.BorderSide(1, BORDER_SUBTLE)),
            padding=ft.Padding.symmetric(horizontal=24, vertical=14),
        )

        # ══════════════════════════════════════════════════════════════════════
        # TRANSCRIPT CARD
        # ══════════════════════════════════════════════════════════════════════

        self._empty_state = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.SPATIAL_AUDIO_ROUNDED,
                        size=60,
                        color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
                    ),
                    ft.Text(
                        "Ready to Scribe",
                        size=18,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                    ),
                    ft.Text(
                        "Hit record below — your transcript will appear here",
                        size=13,
                        color=ft.Colors.with_opacity(0.10, ft.Colors.WHITE),
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

        self._transcript_list = ft.ListView(
            spacing=8,
            auto_scroll=True,
            padding=ft.Padding.all(4),
        )

        transcript_stack = ft.Stack(
            controls=[
                self._empty_state,
                ft.Container(content=self._transcript_list, expand=True),
            ],
            expand=True,
        )

        transcript_header = ft.Row(
            controls=[
                ft.Container(width=7, height=7, bgcolor=STATUS_OK, border_radius=4),
                ft.Text(
                    "TRANSCRIPT",
                    size=FONT_SECTION,
                    weight=ft.FontWeight.W_700,
                    color=TEXT_MUTED,
                    style=ft.TextStyle(letter_spacing=1.5),
                ),
                ft.Container(expand=True),
                ft.Text(
                    "Gemini 2.5 Flash",
                    size=10,
                    color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                    italic=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        transcript_card = ft.Container(
            content=ft.Column(
                controls=[transcript_header, transcript_stack],
                spacing=14,
                expand=True,
            ),
            bgcolor=BG_CARD,
            border=ft.border.all(1, BORDER_SUBTLE),
            border_radius=BORDER_RADIUS_LG,
            padding=ft.Padding.all(20),
            expand=True,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=32,
                color=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
                offset=ft.Offset(0, 6),
            ),
        )

        # ══════════════════════════════════════════════════════════════════════
        # MINUTES OF MEETING CARD
        # ══════════════════════════════════════════════════════════════════════

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
                            ft.Container(width=7, height=7, bgcolor=MOM_COLOR, border_radius=4),
                            ft.Text(
                                "MINUTES OF MEETING",
                                size=FONT_SECTION,
                                weight=ft.FontWeight.W_700,
                                color=MOM_COLOR,
                                style=ft.TextStyle(letter_spacing=1.5),
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=ft.Column(
                            controls=[self._mom_markdown],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        expand=True,
                    ),
                ],
                spacing=14,
                expand=True,
            ),
            bgcolor=BG_CARD,
            border=ft.border.all(1, MOM_BORDER),
            border_radius=BORDER_RADIUS_LG,
            padding=ft.Padding.all(20),
            visible=False,
            height=270,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=24,
                color=ft.Colors.with_opacity(0.35, ft.Colors.BLACK),
                offset=ft.Offset(0, 4),
            ),
        )

        # ══════════════════════════════════════════════════════════════════════
        # CONTROL DOCK
        # ══════════════════════════════════════════════════════════════════════

        _pill = ft.RoundedRectangleBorder(radius=BORDER_RADIUS_PILL)

        self._start_stop_btn = ft.FilledButton(
            content=ft.Text("Start Scribing", size=14, weight=ft.FontWeight.W_600, color="#ffffff"),
            icon=ft.Icons.FIBER_MANUAL_RECORD_ROUNDED,
            on_click=self._toggle_recording,
            style=ft.ButtonStyle(
                bgcolor=RECORD_IDLE_BG,
                color="#ffffff",
                padding=ft.Padding.symmetric(horizontal=28, vertical=14),
                shape=_pill,
            ),
        )

        self._mute_btn = ft.FilledButton(
            content=ft.Text("Mute Mic", size=13, color="#ffffff"),
            icon=ft.Icons.MIC_ROUNDED,
            on_click=self._toggle_mic,
            disabled=True,
            style=ft.ButtonStyle(
                bgcolor=MIC_ACTIVE,
                color="#ffffff",
                padding=ft.Padding.symmetric(horizontal=20, vertical=12),
                shape=_pill,
            ),
        )

        self._timer_text = ft.Text(
            "0:00",
            size=20,
            weight=ft.FontWeight.W_700,
            color=TEXT_PRIMARY,
        )
        self._timer_display = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=8, height=8,
                        bgcolor=RECORD_ACTIVE_GLOW,
                        border_radius=4,
                    ),
                    self._timer_text,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=0),
            visible=False,
        )

        self._mom_btn = ft.FilledButton(
            content=ft.Text("Generate MOM", size=13, color="#ffffff"),
            icon=ft.Icons.AUTO_AWESOME_ROUNDED,
            on_click=self._generate_mom,
            visible=False,
            style=ft.ButtonStyle(
                bgcolor="#4c1d95",
                color="#ffffff",
                padding=ft.Padding.symmetric(horizontal=20, vertical=12),
                shape=_pill,
            ),
        )

        _txt_style = ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            shape=_pill,
            overlay_color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
        )

        self._export_tx_btn = ft.TextButton(
            content=ft.Text("Export .txt", size=12, color=TEXT_SECONDARY),
            icon=ft.Icons.DOWNLOAD_ROUNDED,
            on_click=self._export_transcript,
            visible=False,
            style=_txt_style,
        )

        self._export_mom_btn = ft.TextButton(
            content=ft.Text("Export MOM", size=12, color=MOM_COLOR),
            icon=ft.Icons.DOWNLOAD_ROUNDED,
            on_click=self._export_mom_file,
            visible=False,
            style=_txt_style,
        )

        control_dock = ft.Container(
            content=ft.Row(
                controls=[
                    self._start_stop_btn,
                    self._mute_btn,
                    self._timer_display,
                    ft.Container(expand=True),
                    self._mom_btn,
                    self._export_tx_btn,
                    self._export_mom_btn,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            bgcolor=BG_SURFACE,
            border=ft.border.all(1, BORDER_SUBTLE),
            border_radius=BORDER_RADIUS_LG,
            padding=ft.Padding.symmetric(horizontal=20, vertical=14),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.5, ft.Colors.BLACK),
                offset=ft.Offset(0, -2),
            ),
        )

        # ══════════════════════════════════════════════════════════════════════
        # STATUS BAR
        # ══════════════════════════════════════════════════════════════════════

        self._status_dot = ft.Container(
            width=6, height=6,
            bgcolor=STATUS_DEFAULT,
            border_radius=3,
        )
        self._status_text = ft.Text("Ready", size=FONT_STATUS, color=STATUS_DEFAULT)

        status_bar = ft.Container(
            content=ft.Row(
                controls=[
                    self._status_dot,
                    self._status_text,
                    ft.Container(expand=True),
                    ft.Text(
                        "ScribeOS · Gemini 2.5 Flash",
                        size=10,
                        color=ft.Colors.with_opacity(0.16, ft.Colors.WHITE),
                        italic=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=9),
            border=ft.Border.only(top=ft.BorderSide(1, BORDER_SUBTLE)),
        )

        # ══════════════════════════════════════════════════════════════════════
        # FINAL ASSEMBLY
        # ══════════════════════════════════════════════════════════════════════

        return ft.Column(
            controls=[
                top_bar,
                ft.Container(
                    content=ft.Column(
                        controls=[
                            transcript_card,
                            self._mom_section,
                            control_dock,
                        ],
                        spacing=12,
                        expand=True,
                    ),
                    expand=True,
                    padding=ft.Padding.all(16),
                ),
                status_bar,
            ],
            spacing=0,
            expand=True,
        )

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _set_status(self, message: str, color: str = COLOR_STATUS_DEFAULT) -> None:
        if self._status_text and self._page:
            self._status_text.value = message
            self._status_text.color = color
            if self._status_dot:
                self._status_dot.bgcolor = color
            self._page.update()

    def _append_transcript(self, text: str) -> None:
        if not text.strip() or not self._transcript_list or not self._page:
            return

        # Hide empty state on first real content
        if self._empty_state and not self._transcript_list.controls:
            self._empty_state.visible = False

        self._transcript_list.controls.append(
            ft.Container(
                content=ft.Markdown(
                    value=text,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                ),
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                border_radius=BORDER_RADIUS,
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
                border=ft.border.all(1, ft.Colors.with_opacity(0.05, ft.Colors.WHITE)),
            )
        )
        self._page.update()

    # ── Button handlers ───────────────────────────────────────────────────────

    def _toggle_recording(self, _: ft.ControlEvent) -> None:
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        api_key = (self._api_key_field.value or "").strip()
        if not api_key:
            self._set_status("Please enter your Gemini API Key.", COLOR_STATUS_ERROR)
            return

        if not is_valid_key(api_key):
            self._set_status(
                "API key format looks invalid (should start with 'AIza').",
                COLOR_STATUS_WARN,
            )

        if not Path(_BINARY_PATH).exists():
            self._set_status(
                "audio_bridge binary not found. "
                "Run:  swiftc audio_bridge.swift -o audio_bridge -framework ScreenCaptureKit",
                COLOR_STATUS_ERROR,
            )
            return

        try:
            self._ai_processor = AIProcessor(api_key)
        except ValueError as exc:
            self._set_status(str(exc), COLOR_STATUS_ERROR)
            return

        self._audio_engine = AudioEngine(_BINARY_PATH)
        try:
            self._audio_engine.start(mic_muted=self._mic_muted)
        except FileNotFoundError as exc:
            self._set_status(str(exc), COLOR_STATUS_ERROR)
            self._audio_engine = None
            return

        self._is_recording = True
        self._start_stop_btn.content.value = "Stop Scribing"
        self._start_stop_btn.icon          = ft.Icons.STOP_ROUNDED
        self._start_stop_btn.style.bgcolor = COLOR_RECORD_ACTIVE
        self._mute_btn.disabled            = False
        self._mom_btn.visible              = False
        self._export_tx_btn.visible        = False
        self._export_mom_btn.visible       = False
        if self._mom_section:
            self._mom_section.visible = False
        if self._timer_text:
            self._timer_text.value = "0:00"
        if self._timer_display:
            self._timer_display.visible = True

        self._set_status("Recording…", COLOR_STATUS_OK)
        self._page.update()
        self._page.run_task(self._recording_timer)
        log.info("Recording started")

    async def _recording_timer(self) -> None:
        start = time.monotonic()
        while self._is_recording:
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, 60)
            if self._timer_text:
                self._timer_text.value = f"{mins}:{secs:02d}"
                self._timer_text.update()
            await asyncio.sleep(1)

    def _stop_recording(self) -> None:
        self._is_recording = False

        if self._timer_display:
            self._timer_display.visible = False

        self._start_stop_btn.content.value = "Transcribing…"
        self._start_stop_btn.icon          = ft.Icons.HOURGLASS_TOP_ROUNDED
        self._start_stop_btn.style.bgcolor = ft.Colors.GREY_700
        self._start_stop_btn.disabled      = True
        self._mute_btn.disabled            = True
        self._set_status("Sending to Gemini…", COLOR_STATUS_INFO)

        full_wav: Optional[bytes] = None
        if self._audio_engine:
            full_wav = self._audio_engine.stop()
            self._audio_engine = None

        def _transcribe() -> None:
            if full_wav and self._ai_processor:
                self._set_status("Transcribing full recording…", COLOR_STATUS_INFO)
                self._ai_processor.transcribe_chunk(full_wav, self._append_transcript)
            else:
                self._append_transcript("[No audio captured]")

            self._start_stop_btn.content.value = "Start Scribing"
            self._start_stop_btn.icon          = ft.Icons.FIBER_MANUAL_RECORD_ROUNDED
            self._start_stop_btn.style.bgcolor = COLOR_RECORD_IDLE
            self._start_stop_btn.disabled      = False
            self._mom_btn.visible              = True
            self._export_tx_btn.visible        = True
            self._set_status("Transcript ready.", COLOR_STATUS_OK)
            if self._page:
                self._page.update()
            log.info("Transcription complete")

        threading.Thread(target=_transcribe, daemon=True).start()
        log.info("Recording stopped — transcription in progress")

    def _toggle_mic(self, _: ft.ControlEvent) -> None:
        self._mic_muted = not self._mic_muted
        if self._audio_engine:
            self._audio_engine.set_mic_muted(self._mic_muted)

        self._mute_btn.content.value = "Unmute Mic" if self._mic_muted else "Mute Mic"
        self._mute_btn.icon          = ft.Icons.MIC_OFF_ROUNDED if self._mic_muted else ft.Icons.MIC_ROUNDED
        self._mute_btn.style.bgcolor = COLOR_MIC_MUTED if self._mic_muted else COLOR_MIC_LIVE
        self._set_status(
            "Mic muted." if self._mic_muted else "Mic live.",
            COLOR_STATUS_WARN if self._mic_muted else COLOR_STATUS_OK,
        )

    def _generate_mom(self, _: ft.ControlEvent) -> None:
        if not self._ai_processor:
            return
        self._mom_btn.disabled = True
        self._set_status("Generating Minutes of Meeting…", COLOR_STATUS_INFO)

        def _work() -> None:
            mom = self._ai_processor.generate_mom()
            self._mom_text               = mom
            self._mom_markdown.value     = mom
            self._mom_section.visible    = True
            self._mom_btn.disabled       = False
            self._export_mom_btn.visible = True

            # Auto-save PDF to workspace moms/ folder immediately
            try:
                path = export_mom(mom)
                self._set_status(f"MOM ready → saved to moms/ ✔", COLOR_STATUS_OK)
            except Exception as exc:  # noqa: BLE001
                self._set_status(f"MOM ready (save failed: {exc})", COLOR_STATUS_WARN)

            if self._page:
                self._page.update()

        threading.Thread(target=_work, daemon=True).start()

    # ── Keychain handlers ─────────────────────────────────────────────────────

    def _save_key(self, _: ft.ControlEvent) -> None:
        key = (self._api_key_field.value or "").strip()
        if save_key(key):
            self._set_status("API key saved to Keychain.", COLOR_STATUS_OK)
        else:
            self._set_status("Could not save key (keyring unavailable?).", COLOR_STATUS_WARN)

    def _load_key(self, _: ft.ControlEvent) -> None:
        key = load_key()
        if key:
            self._api_key_field.value = key
            self._set_status("API key loaded from Keychain.", COLOR_STATUS_OK)
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
            path = export_transcription(text)
            self._set_status(f"Transcript saved → {path}", COLOR_STATUS_OK)
        except OSError as exc:
            self._set_status(f"Export failed: {exc}", COLOR_STATUS_ERROR)

    def _export_mom_file(self, _: ft.ControlEvent) -> None:
        if not self._mom_text.strip():
            self._set_status("Generate MOM first.", COLOR_STATUS_WARN)
            return
        try:
            path = export_mom(self._mom_text)
            self._set_status(f"MOM saved → {path}", COLOR_STATUS_OK)
        except OSError as exc:
            self._set_status(f"Export failed: {exc}", COLOR_STATUS_ERROR)


# ── Application entry point ───────────────────────────────────────────────────

def main() -> None:
    app = ScribeOSApp()
    ft.run(app.main)


if __name__ == "__main__":
    main()

