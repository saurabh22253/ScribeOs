"""
ui/styles.py — ScribeOS Design System
======================================
Premium dark-theme design tokens.  Every colour, size, and type choice that
appears in the UI lives here — tweak once, change everything.
"""

import flet as ft

# ── Core palette ───────────────────────────────────────────────────────────────
# Layer depths (darkest → lightest)
BG_PAGE       = "#07070f"   # deepest canvas
BG_SURFACE    = "#0d0d1c"   # navbar / dock
BG_CARD       = "#111124"   # elevated cards
BG_INPUT      = "#0a0a18"   # text fields

# Borders
BORDER_SUBTLE  = "#1a1a32"
BORDER_DEFAULT = "#252545"

# Accent — indigo family
ACCENT_BRIGHT = "#818cf8"   # highlights, icons
ACCENT_MED    = "#6366f1"   # interactive elements
ACCENT_DARK   = "#4f46e5"   # button fills

# Record states — idle=indigo, active=rose
RECORD_IDLE_BG    = "#4f46e5"
RECORD_ACTIVE_BG  = "#be123c"
RECORD_ACTIVE_GLOW= "#f43f5e"

# Mic states
MIC_ACTIVE    = "#0e7490"   # cyan-700
MIC_MUTED     = "#c2410c"   # orange-700

# Minutes of meeting — violet
MOM_COLOR  = "#a78bfa"
MOM_BORDER = "#2e1065"

# Text
TEXT_PRIMARY   = "#f1f5f9"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED     = "#475569"

# Status
STATUS_OK      = "#34d399"
STATUS_WARN    = "#fbbf24"
STATUS_ERROR   = "#f87171"
STATUS_INFO    = "#818cf8"
STATUS_DEFAULT = "#64748b"

# ── Backward-compatible aliases (imported by main.py) ─────────────────────────
COLOR_ACCENT          = ACCENT_BRIGHT
COLOR_RECORD_ACTIVE   = RECORD_ACTIVE_BG
COLOR_RECORD_IDLE     = RECORD_IDLE_BG
COLOR_MIC_LIVE        = MIC_ACTIVE
COLOR_MIC_MUTED       = MIC_MUTED
COLOR_MOM_ACCENT      = MOM_COLOR
COLOR_STATUS_DEFAULT  = STATUS_DEFAULT
COLOR_STATUS_OK       = STATUS_OK
COLOR_STATUS_WARN     = STATUS_WARN
COLOR_STATUS_ERROR    = STATUS_ERROR
COLOR_STATUS_INFO     = STATUS_INFO
COLOR_TRANSCRIPT_BG     = BG_CARD
COLOR_TRANSCRIPT_BORDER = BORDER_DEFAULT
COLOR_TRANSCRIPT_TEXT   = TEXT_PRIMARY
COLOR_SURFACE           = BG_SURFACE

# ── Dimensions ─────────────────────────────────────────────────────────────────
WINDOW_WIDTH    = 1020
WINDOW_HEIGHT   = 760
PADDING         = 0          # zero — sections manage their own padding

BORDER_RADIUS      = 12
BORDER_RADIUS_SM   = 8
BORDER_RADIUS_LG   = 18
BORDER_RADIUS_PILL = 100

# ── Typography ─────────────────────────────────────────────────────────────────
FONT_DISPLAY  = 32
FONT_TITLE    = 18
FONT_SECTION  = 11
FONT_BODY     = 13
FONT_STATUS   = 12
