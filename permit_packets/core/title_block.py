"""The title block on every drawing and data page: project, sheet, contractor and the designer's sign-off."""
from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import simpleSplit

from permit_packets.core.layout import Sheet

INK = colors.HexColor("#15212c")
MUTED = colors.HexColor("#566572")
COPPER = colors.HexColor("#a8551f")
RULE = colors.HexColor("#8794a0")
DRAFT_NOTE = "Draft for review by a licensed electrician. Confirm against the city's current requirements before use."


@dataclass(frozen=True)
class TitleBlock:
    address: str
    parcel: str
    contractor: str
    license_number: str


def title_block_for(job) -> TitleBlock:
    """The title block for any job: every job type has an address, a plan, a contractor and a license."""
    parcel = job.plan.parcel_number if job.plan and job.plan.parcel_number else ""
    return TitleBlock(job.address, parcel, job.contractor, job.license_number)


def sheet_number(index: int) -> str:
    return f"E-{index}"


def _fit(c, text: str, font: str, width: float, size: float, lines: int, floor: float = 6.4):
    """Wrapped lines that fit the width in at most `lines` lines, shrinking the font if needed."""
    while True:
        wrapped = [line for part in text.split("\n") for line in simpleSplit(part, font, size, width) or [""]]
        if len(wrapped) <= lines or size <= floor:
            return wrapped[:lines], size
        size -= 0.4


def _cell(c, x, y, w, h, label, value, *, font="Helvetica-Bold", size=8.2, lines=2, pad=4):
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.setFillColor(COPPER)
    c.setFont("Helvetica-Bold", 6.4)
    c.drawString(x + pad, y + h - 7.4, label)
    wrapped, size = _fit(c, value, font, w - 2 * pad, size, lines)
    c.setFillColor(INK)
    c.setFont(font, size)
    top = y + h - 7.4 - size - 1.2
    for i, line in enumerate(wrapped):
        c.drawString(x + pad, top - i * (size + 1.1), line)


def _signature_cell(c, x, y, w, h, *, pad=4):
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.setFillColor(COPPER)
    c.setFont("Helvetica-Bold", 6.4)
    c.drawString(x + pad, y + h - 7.4, "ELECTRICIAN (DESIGNER OF RECORD)")
    base = y + 5
    fields = (("Prepared by", 0.36), ("Signature", 0.40), ("Date", 0.24))
    inner = w - 2 * pad - 2 * 6
    cursor = x + pad
    c.setFont("Helvetica", 6.6)
    for label, share in fields:
        span = inner * share
        c.setFillColor(INK)
        c.drawString(cursor, base + 2.2, label)
        used = stringWidth(label, "Helvetica", 6.6) + 3
        c.setStrokeColor(INK)
        c.setLineWidth(0.5)
        c.line(cursor + used, base, cursor + span, base)
        cursor += span + 6


def draw_title_block(c, sheet: Sheet, block: TitleBlock, *, title: str, number: int, total: int) -> None:
    x0, y0, w, h = sheet.margin, sheet.block_y, sheet.content_w, sheet.block_h
    c.saveState()
    address = block.address
    parcel = f"Parcel {block.parcel}" if block.parcel else "Parcel: not on file"
    project = f"{address}\n{parcel}"
    contractor = f"{block.contractor}\nLicense {block.license_number}"

    def project_cell(x, y, cw, ch):
        _cell(c, x, y, cw, ch, "PROJECT ADDRESS", address, lines=2)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 6.6)
        c.drawString(x + 4, y + 3.4, parcel)

    def number_cell(x, y, cw, ch):
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.rect(x, y, cw, ch, stroke=1, fill=0)
        c.setFillColor(COPPER)
        c.setFont("Helvetica-Bold", 6.4)
        c.drawString(x + 4, y + ch - 7.4, "SHEET")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 17 if not sheet.landscape else 20)
        c.drawString(x + 4, y + ch - 7.4 - 17, sheet_number(number))
        c.setFont("Helvetica", 6.8)
        c.setFillColor(MUTED)
        c.drawRightString(x + cw - 4, y + 4, f"Page {number} of {total}")

    if not sheet.landscape:
        top_h = 36
        bottom_h = h - top_h
        y_top = y0 + bottom_h
        a, b = 0.46 * w, 0.30 * w
        project_cell(x0, y_top, a, top_h)
        _cell(c, x0 + a, y_top, b, top_h, "SHEET TITLE", title, size=9.5, lines=2)
        number_cell(x0 + a + b, y_top, w - a - b, top_h)
        d = 0.32 * w
        _cell(c, x0, y0, d, bottom_h, "CONTRACTOR", contractor, lines=2)
        _signature_cell(c, x0 + d, y0, w - d, bottom_h)
    else:
        shares = (0.27, 0.19, 0.17, 0.28, 0.09)
        xs = [x0]
        for share in shares:
            xs.append(xs[-1] + share * w)
        project_cell(xs[0], y0, xs[1] - xs[0], h)
        _cell(c, xs[1], y0, xs[2] - xs[1], h, "SHEET TITLE", title, size=11, lines=3)
        _cell(c, xs[2], y0, xs[3] - xs[2], h, "CONTRACTOR", contractor, lines=3)
        _signature_cell(c, xs[3], y0, xs[4] - xs[3], h)
        number_cell(xs[4], y0, xs[5] - xs[4], h)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.4)
    c.drawString(x0, y0 - 9, DRAFT_NOTE)
    c.restoreState()
