"""
ui/styles.py — ScribeOS Design System (v2)
==========================================
Premium dark-theme design tokens — Linear / Notion / Otter.ai aesthetic.
Tweak once, change everything.
"""

# ── Core palette ───────────────────────────────────────────────────────────────
# GitHub Dark-inspired depth layers
BG_PAGE       = "#0E1117"   # deepest canvas
BG_SURFACE    = "#161B22"   # sidebar, panels
BG_CARD       = "#1C2128"   # elevated cards, inputs
BG_INPUT      = "#1C2128"   # text fields

# Borders
BORDER_SUBTLE  = "#30363D"
BORDER_DEFAULT = "#3D444D"

# Accent — Indigo / Amethyst
ACCENT_BRIGHT = "#818cf8"   # highlights, icons
ACCENT_MED    = "#6366F1"   # interactive elements
ACCENT_DARK   = "#4f46e5"   # button fills

# Sidebar nav
NAV_WIDTH         = 220
NAV_ACTIVE_BG     = "#21262D"
NAV_HOVER_BG      = "#1C2128"
NAV_ICON_ACTIVE   = "#8B5CF6"
NAV_ICON_INACTIVE = "#6E7681"

# Record states
RECORD_IDLE_BG    = "#6366F1"
RECORD_ACTIVE_BG  = "#be123c"
RECORD_ACTIVE_GLOW= "#f43f5e"

# Mic states
MIC_ACTIVE    = "#0e7490"
MIC_MUTED     = "#c2410c"

# Processing state
PROCESSING_COLOR = "#6366F1"

# Minutes of meeting — violet
MOM_COLOR  = "#a78bfa"
MOM_BORDER = "#2d2255"

# Text
TEXT_PRIMARY   = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
TEXT_MUTED     = "#6E7681"

# Status
STATUS_OK      = "#3fb950"
STATUS_WARN    = "#d29922"
STATUS_ERROR   = "#f85149"
STATUS_INFO    = "#58a6ff"
STATUS_DEFAULT = "#6E7681"

# ── Backward-compatible aliases ────────────────────────────────────────────────
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
WINDOW_WIDTH    = 1100
WINDOW_HEIGHT   = 780
PADDING         = 0

BORDER_RADIUS      = 10
BORDER_RADIUS_SM   = 6
BORDER_RADIUS_LG   = 12
BORDER_RADIUS_PILL = 100

# ── Typography ─────────────────────────────────────────────────────────────────
FONT_DISPLAY  = 28
FONT_TITLE    = 16
FONT_SECTION  = 11
FONT_BODY     = 13
FONT_STATUS   = 12
