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

# Folder inside the workspace where all MOM PDFs are stored automatically
_MOMS_DIR = Path.home() / "Desktop"

# Folder for auto-saved session transcripts
_TRANSCRIPTS_DIR = Path(__file__).parent.parent / "data" / "transcripts"

def _markdown_to_pdf_bytes(markdown_text: str, generated_at: str) -> bytes:
    """Convert Markdown → dark-themed PDF bytes using reportlab (pure Python)."""
    import io
    from xml.etree import ElementTree as ET
    import markdown as md_lib
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.platypus import (
        BaseDocTemplate, Frame, PageTemplate,
        Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Preformatted, ListFlowable, ListItem,
    )

    # ── Colour tokens (mirror ui/styles.py) ──────────────────────────────
    BG       = colors.HexColor('#07070f')
    CARD     = colors.HexColor('#111124')
    SURFACE  = colors.HexColor('#0d0d1c')
    PRIMARY  = colors.HexColor('#f1f5f9')
    BODY_C   = colors.HexColor('#e2e8f0')
    SECOND   = colors.HexColor('#94a3b8')
    MUTED    = colors.HexColor('#475569')
    ACCENT   = colors.HexColor('#a78bfa')   # violet
    INDIGO   = colors.HexColor('#818cf8')
    HDR_ROW  = colors.HexColor('#1a1a32')
    BORDER   = colors.HexColor('#252545')
    BORDER_S = colors.HexColor('#1a1a32')
    CODE_BG  = colors.HexColor('#0a0a18')

    # ── Paragraph style factory ───────────────────────────────────────────
    _base = getSampleStyleSheet()['Normal']

    def S(name, **kw):
        defaults = dict(
            parent=_base, fontName='Helvetica', fontSize=12,
            leading=19, textColor=BODY_C, backColor=BG,
            spaceBefore=3, spaceAfter=5, leftIndent=0, rightIndent=0,
        )
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    ST = {
        'p':      S('p'),
        'h1':     S('h1',  fontName='Helvetica-Bold', fontSize=20, textColor=PRIMARY,
                           spaceBefore=18, spaceAfter=6,  leading=26),
        'h2':     S('h2',  fontName='Helvetica-Bold', fontSize=15, textColor=ACCENT,
                           spaceBefore=14, spaceAfter=5,  leading=21),
        'h3':     S('h3',  fontName='Helvetica-Bold', fontSize=13, textColor=INDIGO,
                           spaceBefore=10, spaceAfter=4,  leading=18),
        'h4':     S('h4',  fontName='Helvetica-Bold', fontSize=12, textColor=SECOND,
                           spaceBefore=8,  spaceAfter=3,  leading=17),
        'pre':    S('pre', fontName='Courier',       fontSize=10, textColor=SECOND,
                           backColor=CODE_BG, leftIndent=12, rightIndent=12,
                           spaceBefore=8, spaceAfter=8, leading=15),
        'q':      S('q',   textColor=SECOND, leftIndent=14,
                           spaceBefore=4, spaceAfter=4),
        'th':     S('th',  fontName='Helvetica-Bold', fontSize=11,
                           textColor=ACCENT, backColor=HDR_ROW),
        'td':     S('td',  fontSize=11, textColor=BODY_C, backColor=CARD),
        'hbadge': S('hbadge', fontName='Helvetica-Bold', fontSize=9,
                              textColor=BG, backColor=ACCENT, leading=12),
        'htitle': S('htitle', fontName='Helvetica-Bold', fontSize=16,
                              textColor=PRIMARY, backColor=BG, leading=20),
        'hsub':   S('hsub',   fontSize=9, textColor=MUTED, backColor=BG,
                              leading=12, alignment=TA_RIGHT),
    }

    # ── Inline markup helper ──────────────────────────────────────────────
    _ESC = {'&': '&amp;', '<': '&lt;', '>': '&gt;'}

    def esc(s: str) -> str:
        for c, e in _ESC.items():
            s = s.replace(c, e)
        return s

    def to_markup(el) -> str:
        """Recursively convert an ET element to reportlab XML markup."""
        parts = [esc(el.text or '')]
        for child in el:
            tag = child.tag.lower()
            inner = to_markup(child)
            if tag in ('strong', 'b'):
                parts.append(f'<b>{inner}</b>')
            elif tag in ('em', 'i'):
                parts.append(f'<i>{inner}</i>')
            elif tag == 'code':
                parts.append(
                    f'<font name="Courier" color="#818cf8" size="10">{inner}</font>'
                )
            elif tag == 'a':
                href = esc(child.get('href', ''))
                parts.append(f'<a href="{href}" color="#818cf8">{inner}</a>')
            else:
                parts.append(inner)
            parts.append(esc(child.tail or ''))
        return ''.join(parts)

    # ── Table renderer ────────────────────────────────────────────────────
    def render_table(el) -> Table | None:
        def collect_rows(node):
            rows = []
            for child in node:
                if child.tag.lower() == 'tr':
                    rows.append(child)
                else:
                    rows.extend(collect_rows(child))
            return rows

        row_elems = collect_rows(el)
        if not row_elems:
            return None

        data, bg_cmds = [], []
        for ri, tr in enumerate(row_elems):
            cells = list(tr)
            is_header = any(c.tag.lower() == 'th' for c in cells)
            row = []
            for cell in cells:
                sty = ST['th'] if cell.tag.lower() == 'th' else ST['td']
                row.append(Paragraph(to_markup(cell) or '', sty))
            data.append(row)
            bg = HDR_ROW if is_header else (SURFACE if ri % 2 == 0 else CARD)
            bg_cmds.append(('BACKGROUND', (0, ri), (-1, ri), bg))

        n_cols = max(len(r) for r in data)
        for r in data:
            while len(r) < n_cols:
                r.append(Paragraph('', ST['td']))

        col_w = (A4[0] - 4.4 * cm) / n_cols
        tbl = Table(data, colWidths=[col_w] * n_cols, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('GRID',          (0, 0), (-1, -1), 0.5, BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            *bg_cmds,
        ]))
        return tbl

    # ── Element → flowables ───────────────────────────────────────────────
    def render(el) -> list:
        tag = el.tag.lower() if isinstance(el.tag, str) else ''
        out = []

        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            sty = ST.get(tag, ST['h4'])
            out.append(Paragraph(to_markup(el), sty))
            if tag in ('h1', 'h2'):
                out.append(HRFlowable(
                    width='100%', thickness=0.75,
                    color=ACCENT if tag == 'h2' else BORDER_S,
                    spaceAfter=4,
                ))

        elif tag == 'p':
            markup = to_markup(el)
            if markup.strip():
                out.append(Paragraph(markup, ST['p']))

        elif tag in ('ul', 'ol'):
            items = []
            for li in el:
                if li.tag.lower() == 'li':
                    items.append(ListItem(
                        Paragraph(to_markup(li), ST['p']),
                        leftIndent=20, bulletColor=ACCENT,
                    ))
            if items:
                out.append(ListFlowable(
                    items,
                    bulletType='bullet' if tag == 'ul' else '1',
                    leftIndent=16, bulletColor=ACCENT,
                ))

        elif tag == 'table':
            tbl = render_table(el)
            if tbl:
                out += [Spacer(1, 6), tbl, Spacer(1, 8)]

        elif tag == 'pre':
            out.append(Preformatted(''.join(el.itertext()), ST['pre']))

        elif tag == 'blockquote':
            for child in el:
                markup = to_markup(child)
                if markup.strip():
                    out.append(Paragraph(markup, ST['q']))

        elif tag == 'hr':
            out.append(HRFlowable(
                width='100%', thickness=0.5, color=BORDER_S,
                spaceBefore=8, spaceAfter=8,
            ))

        else:
            for child in el:
                out.extend(render(child))

        return out

    # ── Document setup ────────────────────────────────────────────────────
    buf = io.BytesIO()

    def draw_bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BG)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.restoreState()

    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2*cm,    bottomMargin=2.2*cm,
        title='Minutes of Meeting — ScribeOS',
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='body')
    doc.addPageTemplates([PageTemplate(id='dark', frames=[frame], onPage=draw_bg)])

    # ── Header band ───────────────────────────────────────────────────────
    uw = A4[0] - 4.4 * cm
    badge_w, sub_w, title_w = 1.5*cm, 5.5*cm, uw - 1.5*cm - 5.5*cm
    hdr = Table(
        [[
            Paragraph('MOM', ST['hbadge']),
            Paragraph('Minutes of Meeting', ST['htitle']),
            Paragraph(f'ScribeOS · {generated_at}', ST['hsub']),
        ]],
        colWidths=[badge_w, title_w, sub_w],
    )
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (0, 0),  ACCENT),
        ('BACKGROUND',    (1, 0), (-1, 0), BG),
        ('VALIGN',        (0, 0), (-1, 0), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('LEFTPADDING',   (0, 0), (0, 0),  8),
        ('RIGHTPADDING',  (0, 0), (0, 0),  8),
        ('LEFTPADDING',   (1, 0), (1, 0),  10),
        ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT),
    ]))

    story: list = [hdr, Spacer(1, 14)]

    # ── Parse markdown → ET → flowables ──────────────────────────────────
    md = md_lib.Markdown(extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists'])
    html_str = md.convert(markdown_text)
    try:
        root = ET.fromstring(f'<root>{html_str}</root>')
    except ET.ParseError:
        root = ET.fromstring(f'<root><p>{esc(markdown_text)}</p></root>')

    for child in root:
        story.extend(render(child))

    doc.build(story)
    return buf.getvalue()


def export_transcription(
    text: str,
    output_dir: str = "~/Desktop",
) -> str:
    """
    Save the full session transcript as a plain-text file to a custom dir.
    """
    ts   = datetime.now().strftime(_TIMESTAMP_FMT)
    path = Path(output_dir).expanduser() / f"ScribeOS_Transcript_{ts}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def save_transcript_to_data(text: str) -> str:
    """
    Auto-save the session transcript to data/transcripts/ for History tab.
    Returns the absolute path of the saved file.
    """
    ts   = datetime.now().strftime(_TIMESTAMP_FMT)
    path = _TRANSCRIPTS_DIR / f"ScribeOS_Transcript_{ts}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def export_mom(
    markdown_text: str,
    output_dir: str | None = None,
) -> str:
    """
    Save the Minutes of Meeting document as a styled PDF.

    Saves automatically to the workspace moms/ folder by default.
    Pass output_dir to override the destination.

    Returns
    -------
    Absolute path of the saved PDF file.
    """
    ts           = datetime.now().strftime(_TIMESTAMP_FMT)
    generated_at = datetime.now().strftime("%d %b %Y, %H:%M")
    dest         = Path(output_dir).expanduser() if output_dir else _MOMS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    path         = dest / f"ScribeOS_MOM_{ts}.pdf"
    pdf_bytes = _markdown_to_pdf_bytes(markdown_text, generated_at)
    path.write_bytes(pdf_bytes)
    return str(path)
