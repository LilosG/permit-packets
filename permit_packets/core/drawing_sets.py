"""A 22 x 34 in drawing set from a packet laid out on letter pages.

San Francisco (DBI Information Sheet E-01 and DBI's PDF rules): electrical plans no smaller than
11 x 17 in, scaled no smaller than 1/8 in = 1 ft, text at least 1/8 in tall, a 2 x 2 in stamp area in the
same place on every sheet, and an empty 8.5 x 11 in area on the title sheet. Forms and data sheets are
supplemental documents and stay 8.5 x 11 in.

Each drawing page is printed at SHEET_SCALE on a 22 x 34 in portrait sheet. At 2.5x the smallest text the
packet draws (6.4 pt) prints with capitals taller than 1/8 in, and a site plan drawn at 1 in = 20 ft prints
at exactly 1/8 in = 1 ft. The cover prints at COVER_SCALE so the 8.5 x 11 in area fits below it at true
size; at 2x the 6.4 pt minimum still prints with capitals taller than 1/8 in.
"""
from __future__ import annotations

from io import BytesIO

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas

from permit_packets.core.layout import PRINT_MAGNIFICATION

SHEET_W, SHEET_H = 22 * inch, 34 * inch
SHEET_SCALE = PRINT_MAGNIFICATION["ansi_d"]
COVER_SCALE = 2.0
TOP_MARGIN = 0.5 * inch
STAMP_SIDE = 2.0 * inch
STAMP_X = SHEET_W - 0.375 * inch - STAMP_SIDE  # the same spot on every sheet, bottom right
STAMP_Y = 0.5 * inch
LABEL_PT = 13  # capitals about 0.13 in tall: our own labels meet the 1/8 in rule too

COVER_TITLE = "Checklist and Checks"
# Sheets that are drawings and calculations. Everything else (application data, utility request,
# equipment data and its attached data sheets, the pre-submittal review) is a supplemental document.
DRAWING_TITLES = frozenset({
    COVER_TITLE, "Site Plan", "One-Line Diagram", "Riser Diagram", "Feeder Schedule", "Load Calculation",
    "Panel Schedule",
})
INK = colors.HexColor("#15212c")


def _overlay(blank_in: tuple[float, float] | None, cover_bottom: float | None) -> PageObject:
    """The stamp area every sheet carries, plus the agency area on the cover."""
    buffer = BytesIO()
    c = Canvas(buffer, pagesize=(SHEET_W, SHEET_H))
    c.setStrokeColor(INK)
    c.setLineWidth(1)
    c.setDash(5, 4)
    c.rect(STAMP_X, STAMP_Y, STAMP_SIDE, STAMP_SIDE)
    c.setDash()
    c.setFillColor(INK)
    c.setFont("Helvetica", LABEL_PT)
    for i, line in enumerate(("Reserved for", "DBI stamp", "2 x 2 in")):
        c.drawCentredString(STAMP_X + STAMP_SIDE / 2, STAMP_Y + STAMP_SIDE - 30 - i * 18, line)
    if blank_in and cover_bottom is not None:
        w, h = blank_in[0] * inch, blank_in[1] * inch
        x, y = (SHEET_W - COVER_SCALE * 8.5 * inch) / 2, cover_bottom - 0.25 * inch - h
        c.setDash(5, 4)
        c.rect(x, y, w, h)
        c.setDash()
        c.drawCentredString(x + w / 2, y + h - 30, f"Empty {blank_in[0]:g} in x {blank_in[1]:g} in area")
        c.drawCentredString(x + w / 2, y + h - 48, "for agency stamps")
    c.showPage()
    c.save()
    return PdfReader(BytesIO(buffer.getvalue())).pages[0]


def _sheet(page: PageObject, scale: float, blank_in: tuple[float, float] | None) -> PageObject:
    box = page.mediabox
    width, height = float(box.width), float(box.height)
    sheet = PageObject.create_blank_page(width=SHEET_W, height=SHEET_H)
    x = (SHEET_W - width * scale) / 2
    y = SHEET_H - TOP_MARGIN - height * scale
    sheet.merge_transformed_page(page, Transformation().scale(scale).translate(x - float(box.left) * scale,
                                                                                 y - float(box.bottom) * scale))
    sheet.merge_page(_overlay(blank_in, y if blank_in else None))
    return sheet


def page_roles(page_count: int, titles: list[str], attachments: tuple[int, int] | None) -> list[str | None]:
    """Each page's sheet title; attached manufacturer data sheets have none."""
    roles: list[str | None] = list(titles)
    if attachments:
        after, count = attachments
        roles[after:after] = [None] * count
    return (roles + [None] * page_count)[:page_count]


def drawing_set(pdf: bytes, titles: list[str], blank_in: tuple[float, float] | None) -> bytes:
    """Drawing pages onto 22 x 34 in sheets; supplemental pages stay as drawn. Metadata is kept."""
    from permit_packets.core.equipment import attachment_span

    reader = PdfReader(BytesIO(pdf))
    writer = PdfWriter()
    for page, title in zip(reader.pages, page_roles(len(reader.pages), titles, attachment_span(pdf))):
        if title == COVER_TITLE:
            writer.add_page(_sheet(page, COVER_SCALE, blank_in))
        elif title in DRAWING_TITLES:
            writer.add_page(_sheet(page, SHEET_SCALE, None))
        else:
            writer.add_page(page)
    if reader.metadata:
        writer.add_metadata({key: str(value) for key, value in reader.metadata.items()})
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
