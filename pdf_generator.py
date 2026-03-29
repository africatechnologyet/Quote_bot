import os
import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, Flowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Setup logging to help troubleshoot on Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Brand colours ──────────────────────────────────────────────────
ORANGE      = colors.HexColor("#F47920")
NAVY        = colors.HexColor("#2B2D6E")
ROW_ALT     = colors.HexColor("#FFF4EC")
BORDER_GRAY = colors.HexColor("#D5D5D5")
TEXT_DARK   = colors.HexColor("#1A1A1A")
TEXT_MED    = colors.HexColor("#555555")
WHITE       = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

# ── Custom HR Flowable ─────────────────────────────────────────────
class HRule(Flowable):
    def __init__(self, width, thickness=0.6, color=BORDER_GRAY,
                 space_before=0, space_after=0):
        super().__init__()
        self._width = width; self._thickness = thickness
        self._color = color; self._sb = space_before; self._sa = space_after
        self.height = thickness + space_before + space_after
        self.width  = width

    def wrap(self, availW, availH):
        return self._width, self.height

    def draw(self):
        self.canv.setStrokeColor(self._color)
        self.canv.setLineWidth(self._thickness)
        self.canv.line(0, self._sa, self._width, self._sa)

# ── Assets Discovery ───────────────────────────────────────────────
def _get_assets_path():
    """Locates the assets folder relative to this script."""
    base_path = os.path.dirname(os.path.abspath(__file__))
    assets_path = os.path.join(base_path, "assets")
    
    if not os.path.exists(assets_path):
        logger.error(f"CRITICAL: Assets directory not found at {assets_path}")
        # List directory to help debug in logs
        logger.info(f"Current directory contents: {os.listdir(base_path)}")
    return assets_path

# ── Font registration ──────────────────────────────────────────────
_FONTS_REGISTERED = False

def _register_fonts(assets_dir: str):
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED: return
    
    # Use exact filenames as they appear on GitHub (Case Sensitive)
    font_path = os.path.join(assets_dir, "SPORTE_COLLEGE.ttf")
    
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont("SporteCollege", font_path))
            _FONTS_REGISTERED = True
            logger.info("Custom font registered successfully.")
        except Exception as e:
            logger.error(f"Failed to register font: {e}")
    else:
        logger.warning(f"Font file missing at {font_path}. Using fallback.")

def _get_font(assets_dir: str, fallback="Helvetica-Bold"):
    _register_fonts(assets_dir)
    return "SporteCollege" if _FONTS_REGISTERED else fallback

# ── Style + format helpers ─────────────────────────────────────────
def _s(name, **kw):
    d = dict(fontName="Helvetica", fontSize=9, leading=12, textColor=TEXT_DARK)
    d.update(kw)
    return ParagraphStyle(name, **d)

def _fmt(n) -> str:
    return f"{n:,.2f}" if n is not None else "TBD"

# ══════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════

def generate_quote_pdf(
    path: str,
    client: str,
    location: str,
    grades: list,
    pump: dict | None,
    extra_service: float,
    quote_no: str,
    date_str: str,
):
    ASSETS = _get_assets_path()
    
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=12*mm, bottomMargin=14*mm,
        title=f"CoBuilt Quote {quote_no}",
    )
    
    usable_w = PAGE_W - 2 * MARGIN
    story = []
    
    # ── 1. HEADER (Logo + Address) ────────────────────────────────
    logo_path = os.path.join(ASSETS, "logo_clean.png")
    
    addr = Paragraph(
        "<b>CoBuilt Solutions</b><br/>"
        "Addis Ababa, Ethiopia<br/>"
        "Phone: +251911246502 | +251911246820<br/>"
        "Email: CoBuilt@CoBuilt.com<br/>"
        "Web: www.CoBuilt.com",
        _s("Addr", fontSize=8, leading=11),
    )
    
    if os.path.exists(logo_path):
        logo_cell = Image(logo_path, width=26*mm, height=29*mm, hAlign="RIGHT")
    else:
        logo_cell = Paragraph("<b>CoBuilt</b><br/>Solutions", 
                              _s("L_Fallback", alignment=TA_RIGHT, fontSize=14, textColor=ORANGE))

    hdr_table = Table([[addr, logo_cell]], colWidths=[usable_w*0.7, usable_w*0.3])
    hdr_table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 0)]))
    story.append(hdr_table)
    story.append(HRule(usable_w, thickness=2.5, color=ORANGE, space_before=4, space_after=8))

    # ── 2. TITLE ──────────────────────────────────────────────────
    story.append(Paragraph(
        "CONCRETE QUOTE",
        _s("Title", fontName=_get_font(ASSETS), fontSize=24, textColor=NAVY,
           alignment=TA_CENTER, leading=28),
    ))
    story.append(HRule(usable_w, thickness=0.7, color=BORDER_GRAY, space_before=6, space_after=8))

    # ── 3. DATE / QUOTE NO ────────────────────────────────────────
    meta_data = [
        [Paragraph(f"<b>Date:</b> {date_str}", _s("D", alignment=TA_RIGHT))],
        [Paragraph(f"<b>Quote No:</b> {quote_no}", _s("Q", alignment=TA_RIGHT))]
    ]
    meta_table = Table(meta_data, colWidths=[usable_w])
    meta_table.setStyle(TableStyle([("ALIGN", (0,0), (-1,-1), "RIGHT"), ("LEFTPADDING", (0,0), (-1,-1), 0)]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # ── 4. CLIENT INFO ────────────────────────────────────────────
    total_volume = sum(g["volume"] for g in grades)
    grade_list = ", ".join(g["grade"] for g in grades)
    
    def info_row(label, value):
        return [Paragraph(f"<b>{label}</b>", _s("L")), Paragraph(str(value), _s("V", textColor=TEXT_MED))]

    info_data = [
        [*info_row("Company:", client), *info_row("Service:", pump["type"] if pump else "Standard")],
        [*info_row("Location:", location), *info_row("Terms:", "100% Advance")],
        [*info_row("Quantity:", f"{total_volume:,.2f} m³"), *info_row("Validity:", "3 Days")],
        [*info_row("Grades:", grade_list), "", ""]
    ]
    
    info_table = Table(info_data, colWidths=[usable_w*0.15, usable_w*0.35, usable_w*0.15, usable_w*0.35])
    info_table.setStyle(TableStyle([("LINEBELOW", (0,0), (-1,-2), 0.5, BORDER_GRAY), ("VALIGN", (0,0), (-1,-1), "TOP")]))
    story.append(info_table)
    story.append(Spacer(1, 12))

    # ── 5. ITEMS TABLE ────────────────────────────────────────────
    th_style = _s("TH", fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_CENTER)
    td_style = _s("TD", alignment=TA_CENTER)
    
    rows = [[Paragraph(x, th_style) for x in ["No.", "Description", "Grade", "Qty", "Price", "Total"]]]
    
    for i, g in enumerate(grades, 1):
        rows.append([i, "Concrete OPC", g["grade"], f"{g['volume']}m³", _fmt(g["unit_price"]), _fmt(g["total"])])
    
    if extra_service > 0:
        rows.append(["-", "Extra Services", "-", "-", "-", _fmt(extra_service)])
    
    if pump:
        rows.append(["-", pump["type"], "-", f"{total_volume}m³", _fmt(pump["rate"]), _fmt(pump["total"])])

    item_table = Table(rows, colWidths=[usable_w*0.08, usable_w*0.32, usable_w*0.15, usable_w*0.15, usable_w*0.15, usable_w*0.15])
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), ORANGE),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER_GRAY),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, ROW_ALT]),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(item_table)

    # ── 6. TOTALS ─────────────────────────────────────────────────
    subtotal = sum(g["total"] for g in grades) + (pump["total"] if pump else 0)
    vat = subtotal * 0.15
    grand = subtotal + vat

    summary_data = [
        [Paragraph("Subtotal:", _s("S", alignment=TA_RIGHT)), _fmt(subtotal)],
        [Paragraph("VAT (15%):", _s("S", alignment=TA_RIGHT)), _fmt(vat)],
        [Paragraph("<b>Grand Total (ETB):</b>", _s("G", alignment=TA_RIGHT, textColor=NAVY)), Paragraph(f"<b>{_fmt(grand)}</b>", _s("G", textColor=NAVY))]
    ]
    summary_table = Table(summary_data, colWidths=[usable_w*0.8, usable_w*0.2])
    summary_table.setStyle(TableStyle([("ALIGN", (0,0), (-1,-1), "RIGHT")]))
    story.append(Spacer(1, 10))
    story.append(summary_table)

    # ── 7. STAMP & SIGNATURE ──────────────────────────────────────
    story.append(Spacer(1, 20))
    stamp_path = os.path.join(ASSETS, "stamp_clean.png")
    
    contact_info = Paragraph(
        "<b>For clarifications:</b><br/>Biruk Endale<br/>COO, CoBuilt Solutions<br/>+251911246502",
        _s("CI", fontSize=8)
    )
    
    if os.path.exists(stamp_path):
        stamp_img = Image(stamp_path, width=50*mm, height=30*mm, hAlign="RIGHT")
        footer_table = Table([[contact_info, stamp_img]], colWidths=[usable_w*0.5, usable_w*0.5])
    else:
        footer_table = Table([[contact_info, Paragraph("____________________<br/>Approved Signature", _s("AS", alignment=TA_RIGHT))]], colWidths=[usable_w*0.5, usable_w*0.5])
    
    footer_table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "BOTTOM")]))
    story.append(footer_table)

    doc.build(story)