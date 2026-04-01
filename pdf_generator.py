import os

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

ORANGE      = colors.HexColor("#F47920")
NAVY        = colors.HexColor("#2B2D6E")
ROW_ALT     = colors.HexColor("#FFF4EC")
BORDER_GRAY = colors.HexColor("#D5D5D5")
TEXT_DARK   = colors.HexColor("#1A1A1A")
TEXT_MED    = colors.HexColor("#555555")
WHITE       = colors.white
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


class HRule(Flowable):
    def __init__(self, width, thickness=0.6, color=BORDER_GRAY, space_before=0, space_after=0):
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


_FONTS_REGISTERED = False

def _register_fonts(assets_dir: str):
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    try:
        regular = os.path.join(assets_dir, "SPORTE_COLLEGE.ttf")
        bold    = os.path.join(assets_dir, "SPORTE_COLLEGE-Outline.ttf")
        if os.path.exists(regular):
            pdfmetrics.registerFont(TTFont("SporteCollege", regular))
            if os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("SporteCollege-Bold", bold))
                pdfmetrics.registerFontFamily(
                    "SporteCollege",
                    normal="SporteCollege",
                    bold="SporteCollege-Bold",
                )
            _FONTS_REGISTERED = True
    except Exception as e:
        print(f"Font loading error: {e}")

def _title_font(assets_dir):
    _register_fonts(assets_dir)
    return "SporteCollege" if _FONTS_REGISTERED else "Helvetica-Bold"

def _assets_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

def _s(name, **kw):
    d = dict(fontName="Helvetica", fontSize=9, leading=12, textColor=TEXT_DARK)
    d.update(kw); return ParagraphStyle(name, **d)

def _fmt(n):
    return f"{n:,.2f}" if n is not None else "TBD"


def generate_quote_pdf(
    path: str,
    client: str,
    location: str,
    grades: list,
    pump: dict | None,
    validity: str,
    quote_no: str,
    date_str: str,
):
    ASSETS = _assets_dir()
    _register_fonts(ASSETS)

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=12*mm, bottomMargin=14*mm,
        title=f"CoBuilt Quote {quote_no}",
        author="CoBuilt Solutions",
    )
    usable_w   = PAGE_W - 2 * MARGIN
    story      = []
    title_font = _title_font(ASSETS)

    # ── 1. HEADER ─────────────────────────────────────────────────
    logo_path = os.path.join(ASSETS, "logo_clean.png")
    addr = Paragraph(
        "<b>CoBuilt Solutions</b><br/>"
        "Addis Ababa, Ethiopia<br/>"
        "Phone: +251911246502<br/>"
        "+251911246820<br/>"
        "Email: CoBuilt@CoBuilt.com<br/>"
        "Web: www.CoBuilt.com",
        _s("Addr", fontSize=8, leading=11),
    )
    if os.path.exists(logo_path):
        logo_cell = Image(logo_path, width=26*mm, height=29*mm, hAlign="RIGHT")
    else:
        logo_cell = Paragraph("<b>CoBuilt</b><br/>Solutions",
                              _s("LF", alignment=TA_RIGHT, fontSize=14, textColor=ORANGE))

    hdr = Table([[addr, logo_cell]], colWidths=[usable_w*0.65, usable_w*0.35])
    hdr.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("ALIGN",        (1,0),(1,0),   "RIGHT"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    story.append(hdr)
    story.append(HRule(usable_w, thickness=2.5, color=ORANGE, space_before=4, space_after=8))

    # ── 2. TITLE ──────────────────────────────────────────────────
    story.append(Paragraph(
        "CONCRETE QUOTE",
        _s("Title", fontName=title_font, fontSize=24, textColor=NAVY,
           alignment=TA_CENTER, leading=28, spaceAfter=0),
    ))
    story.append(HRule(usable_w, thickness=0.7, color=BORDER_GRAY, space_before=6, space_after=8))

    # ── 3. DATE & QUOTE NO ────────────────────────────────────────
    date_block = Table([
        [Paragraph(f"<b>Date:</b> {date_str}",
                   _s("DR", fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT))],
        [Paragraph(f"<b>Quote No:</b> {quote_no}",
                   _s("QR", fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT))],
    ], colWidths=[usable_w])
    date_block.setStyle(TableStyle([
        ("ALIGN",        (0,0),(-1,-1), "RIGHT"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 1),
        ("BOTTOMPADDING",(0,0),(-1,-1), 1),
    ]))
    story.append(date_block)
    story.append(Spacer(1, 8))

    # ── 4. CLIENT INFO GRID ───────────────────────────────────────
    total_volume = sum(g["volume"] for g in grades)
    grade_labels = ", ".join(g["grade"] for g in grades)
    pump_label   = pump["type"] if pump else "\u2014"

    def ic(lbl, val):
        return [
            Paragraph(f"<b>{lbl}</b>", _s("IL", fontName="Helvetica-Bold", fontSize=9)),
            Paragraph(str(val),        _s("IV", fontSize=9, textColor=TEXT_MED)),
        ]

    cw   = usable_w / 4
    info = Table([
        [*ic("Company:",        client),      *ic("Pump Service:",      pump_label)],
        [*ic("Location:",       location),    *ic("Payment terms:",     "100% advance")],
        [*ic("Quantity:",       f"{total_volume:,.2f}m\u00b3"),
         *ic("Validity of quote:", f"Valid for {validity}")],
        [*ic("Concrete Grade:", grade_labels),
         Paragraph("", _s("E1")), Paragraph("", _s("E2"))],
    ], colWidths=[cw*0.65, cw*1.35, cw*0.72, cw*1.28])
    info.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 2),
        ("RIGHTPADDING", (0,0),(-1,-1), 2),
        ("TOPPADDING",   (0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("LINEBELOW",    (0,0),(-1,-2), 0.4, BORDER_GRAY),
    ]))
    story.append(info)
    story.append(Spacer(1, 10))

    # ── 5. ITEMS TABLE ────────────────────────────────────────────
    cNo   = usable_w * 0.07
    cDesc = usable_w * 0.28
    cGrd  = usable_w * 0.13
    cQty  = usable_w * 0.17
    cPrc  = usable_w * 0.18
    cTot  = usable_w * 0.17

    S_TH = _s("TH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE, alignment=TA_CENTER)
    S_TD = _s("TD", fontSize=9, alignment=TA_CENTER)

    rows = [[
        Paragraph("No.",         S_TH),
        Paragraph("Description", S_TH),
        Paragraph("Grade",       S_TH),
        Paragraph("Quantity",    S_TH),
        Paragraph("Price",       S_TH),
        Paragraph("Total Price", S_TH),
    ]]

    for i, g in enumerate(grades, 1):
        rows.append([
            Paragraph(str(i),                        S_TD),
            Paragraph("Concrete OPC",                S_TD),
            Paragraph(g["grade"],                    S_TD),
            Paragraph(f"{g['volume']:,.2f}m\u00b3",  S_TD),
            Paragraph(_fmt(g["unit_price"]),         S_TD),
            Paragraph(_fmt(g["total"]),              S_TD),
        ])

    if pump:
        pump_price_str = _fmt(pump["rate"]) + "/m\u00b3" if pump["rate"] else "TBD"
        rows.append([
            Paragraph("\u2014",                        S_TD),
            Paragraph(pump["type"],                    S_TD),
            Paragraph("\u2014",                        S_TD),
            Paragraph(f"{total_volume:,.2f}m\u00b3",  S_TD),
            Paragraph(pump_price_str,                  S_TD),
            Paragraph(_fmt(pump["total"]),             S_TD),
        ])

    items = Table(rows, colWidths=[cNo,cDesc,cGrd,cQty,cPrc,cTot], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  ORANGE),
        ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("GRID",          (0,0),(-1,-1), 0.4, BORDER_GRAY),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, ROW_ALT]),
    ]))
    story.append(items)
    story.append(Spacer(1, 4))

    # ── 6. TOTALS ─────────────────────────────────────────────────
    subtotal    = sum(g["total"] for g in grades) + (pump["total"] if pump else 0)
    vat         = subtotal * 0.15
    grand_total = subtotal + vat

    tot = Table([
        [Paragraph("Subtotal:",
                   _s("TL",  fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT)),
         Paragraph(_fmt(subtotal),
                   _s("TV",  fontSize=9, alignment=TA_RIGHT, textColor=TEXT_MED))],
        [Paragraph("VAT (15%):",
                   _s("TL2", fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT)),
         Paragraph(_fmt(vat),
                   _s("TV2", fontSize=9, alignment=TA_RIGHT, textColor=TEXT_MED))],
        [Paragraph("Grand Total:",
                   _s("GL",  fontName="Helvetica-Bold", fontSize=10,
                      alignment=TA_RIGHT, textColor=NAVY)),
         Paragraph(_fmt(grand_total),
                   _s("GV",  fontName="Helvetica-Bold", fontSize=10,
                      alignment=TA_RIGHT, textColor=NAVY))],
    ], colWidths=[usable_w*0.70, usable_w*0.30])
    tot.setStyle(TableStyle([
        ("ALIGN",        (0,0),(-1,-1), "RIGHT"),
        ("LEFTPADDING",  (0,0),(-1,-1), 4),
        ("RIGHTPADDING", (0,0),(-1,-1), 4),
        ("TOPPADDING",   (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ("LINEABOVE",    (0,2),(-1,2),  1.5, ORANGE),
        ("LINEBELOW",    (0,2),(-1,2),  1.5, ORANGE),
        ("BACKGROUND",   (0,2),(-1,2),  colors.HexColor("#FFF4EC")),
    ]))
    story.append(tot)
    story.append(Spacer(1, 5))

    # ── 7. NOTES ──────────────────────────────────────────────────
    S_NOTE = _s("Note", fontSize=8, textColor=TEXT_MED, fontName="Helvetica-Oblique")
    story.append(Paragraph(
        "<i>Note: VAT (15%) has been included in the Grand Total above.</i>", S_NOTE))
    story.append(Paragraph(
        "- As the order volume increases, we can extend a discount accordingly.", S_NOTE))
    story.append(Spacer(1, 10))

    # ── 8. TERMS & CONDITIONS ─────────────────────────────────────
    story.append(Paragraph(
        "<b>Terms &amp; Conditions</b>",
        _s("TCH", fontName="Helvetica-Bold", fontSize=9)))
    for t in [
        f"Delivery Schedule: Within 7\u201310 working days from confirmation.",
        "Payment Terms: 100% advance.",
        f"Validity: This quote is valid for {validity} from the date of issue.",
        "Exclusions: Does not include site preparation, road access issues, "
        "or waiting time beyond 1 hour per truck.",
        "Reserves the right to ask for compensation due to any issues related "
        "to access issues or client\u2019s scope.",
    ]:
        story.append(Paragraph(f"\u2022 {t}",
                               _s("TC", fontSize=7.5, textColor=TEXT_MED, leading=10)))
    story.append(Spacer(1, 14))

    # ── 9. CONTACT + STAMP ────────────────────────────────────────
    S_CB = _s("CB", fontName="Helvetica-Bold", fontSize=8.5, textColor=TEXT_DARK, leading=13)
    S_CN = _s("CN", fontSize=8.5, textColor=TEXT_MED, leading=13)

    contact_col = [
        Paragraph("<b>For any clarifications, please contact:</b>", S_CB),
        Paragraph("Biruk Endale",            S_CN),
        Paragraph("Chief Operation Officer", S_CN),
        Paragraph("CoBuilt Solutions",       S_CN),
        Paragraph("+251911246502",           S_CN),
        Paragraph("+251911246520",           S_CN),
    ]

    appr_label = Paragraph(
        "<b>Approved By:</b>",
        _s("AL", fontName="Helvetica-Bold", fontSize=9,
           alignment=TA_RIGHT, textColor=TEXT_DARK),
    )

    stamp_path = os.path.join(ASSETS, "stamp_clean.png")
    if os.path.exists(stamp_path):
        stamp_img = Image(stamp_path, width=90*mm, height=55*mm, hAlign="RIGHT")
        appr_col  = [appr_label, Spacer(1, 3), stamp_img]
    else:
        appr_col = [
            appr_label, Spacer(1, 8),
            Paragraph(
                "<i>Biruk Endale<br/>Chief Operation Officer<br/>CoBuilt Solutions</i>",
                _s("AS", fontSize=8.5, alignment=TA_RIGHT,
                   fontName="Helvetica-Oblique", textColor=TEXT_MED)),
        ]

    bottom = Table([[contact_col, appr_col]], colWidths=[usable_w*0.45, usable_w*0.55])
    bottom.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("ALIGN",        (1,0),(1,0),   "RIGHT"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    story.append(bottom)

    # ── 10. FOOTER ────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRule(usable_w, thickness=0.5, color=BORDER_GRAY, space_before=0, space_after=4))
    story.append(Paragraph(
        "<i>A branch of SSara Group</i>",
        _s("Foot", fontSize=7.5, textColor=TEXT_MED,
           alignment=TA_CENTER, fontName="Helvetica-Oblique")))

    doc.build(story)
