"""What every permit packet shares: the page look, the cover and the review page."""
from __future__ import annotations

from contextvars import ContextVar
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#15212c")
MUTED = colors.HexColor("#566572")
RULE = colors.HexColor("#cfd7dd")
COPPER = colors.HexColor("#a8551f")
SOFT = colors.HexColor("#f4e4d8")
GREEN = colors.HexColor("#1f7a58")
PALE = colors.HexColor("#eef1f3")
WATERMARK = colors.HexColor("#e9edf0")
WATERMARK_INK = colors.HexColor("#3a4a57")
WIDTH, HEIGHT = letter
# The contractor's logo for the packet being built, as PNG/JPEG bytes. Set per request.
CONTRACTOR_LOGO: ContextVar[bytes | None] = ContextVar("contractor_logo", default=None)
HEADER_LOGO_H = 0.3 * inch
COVER_LOGO_W = 1.9 * inch
COVER_LOGO_H = 1.0 * inch

MARGIN = 0.7 * inch
CONTENT = WIDTH - 2 * MARGIN


def _style(name: str, **kwargs) -> ParagraphStyle:
    return ParagraphStyle(
        name,
        fontName=kwargs.pop("font", "Helvetica"),
        textColor=kwargs.pop("color", INK),
        **kwargs,
    )


H1 = _style("h1", font="Helvetica-Bold", fontSize=19, leading=23)
H2 = _style("h2", font="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=4, spaceAfter=4)
BODY = _style("body", fontSize=9.4, leading=13)
SMALL = _style("small", fontSize=8.2, leading=11, color=MUTED)
CREDIT = _style("credit", fontSize=6.6, leading=8.4, color=MUTED)
CELL = _style("cell", fontSize=8.8, leading=11.5)
CELL_BOLD = _style("cell-bold", font="Helvetica-Bold", fontSize=8.8, leading=11.5)
FLAG = _style("flag", fontSize=8.3, leading=11, spaceAfter=3, leftIndent=15, firstLineIndent=-15)
LABEL = _style("label", font="Helvetica-Bold", fontSize=7.4, leading=10, color=COPPER)


def _p(text: object, style: ParagraphStyle = CELL) -> Paragraph:
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _table(rows, widths, *, head: bool = True, extra=()) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if head else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if head:
        style.append(("BACKGROUND", (0, 0), (-1, 0), PALE))
    table.setStyle(TableStyle(style + list(extra)))
    return table


TIGHT = [("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]


def _heads(*labels: str) -> list[Paragraph]:
    return [_p(label, CELL_BOLD) for label in labels]


def _watermark(canvas, doc) -> None:
    """Drawn after the page content and see-through, so table fills can't hide part of it."""
    canvas.saveState()
    canvas.setFillColor(WATERMARK_INK)
    canvas.setFillAlpha(0.09)
    canvas.setFont("Helvetica-Bold", 58)
    canvas.translate(WIDTH / 2, HEIGHT / 2)
    canvas.rotate(38)
    canvas.drawCentredString(0, -20, "DEMO")
    canvas.restoreState()


def _page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(COPPER)
    canvas.drawString(MARGIN, HEIGHT - 0.42 * inch, "DEMO PACKET: NOT FOR SUBMISSION")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    logo = CONTRACTOR_LOGO.get()
    if logo and canvas.getPageNumber() > 1:
        reader = ImageReader(BytesIO(logo))
        width, height = reader.getSize()
        w = HEADER_LOGO_H * width / height
        canvas.drawImage(reader, WIDTH - MARGIN - w, HEIGHT - 0.5 * inch, w, HEADER_LOGO_H, mask="auto")
    elif not logo:
        canvas.drawRightString(WIDTH - MARGIN, HEIGHT - 0.42 * inch, "Lilos Growth")
    canvas.setStrokeColor(RULE)
    canvas.line(MARGIN, 0.5 * inch, WIDTH - MARGIN, 0.5 * inch)
    canvas.drawString(
        MARGIN, 0.34 * inch,
        "Draft for review by a licensed electrician. Confirm against the city's current requirements before use.",
    )
    canvas.restoreState()


class NumberedCanvas(Canvas):
    """Holds each page until the end, so the footer can say the real page count."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []

    def showPage(self) -> None:
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._pages)
        for page in self._pages:
            self.__dict__.update(page)
            self.setFont("Helvetica", 8)
            self.setFillColor(MUTED)
            self.drawRightString(WIDTH - MARGIN, 0.34 * inch, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def build_document(sections: list[list], *, title: str) -> bytes:
    story: list = []
    for index, section in enumerate(sections):
        if index:
            story.append(PageBreak())
        story += section
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.65 * inch, bottomMargin=0.65 * inch,
        title=title, author="Lilos Growth",
    )
    frame = Frame(MARGIN, 0.6 * inch, CONTENT, HEIGHT - 1.2 * inch,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=_page, onPageEnd=_watermark)])
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


def cover_page(
    *,
    title: str,
    address: str,
    job_cell: str,
    contractor_cell: str,
    checklist_cell: str,
    checklist_rows: list[tuple[str, str, str]],
    checks: list[tuple[str, str, bool]],
    flags: list[str],
) -> list:
    """The first page: the job, the city's checklist, the engineering checks and the flags."""
    story = [_p(title, H1), _p(address, BODY), Spacer(1, 8)]
    logo = CONTRACTOR_LOGO.get()
    if logo:
        reader = ImageReader(BytesIO(logo))
        width, height = reader.getSize()
        scale = min(COVER_LOGO_W / width, COVER_LOGO_H / height)
        image = Image(BytesIO(logo), width * scale, height * scale)
        story = [Table(
            [[[_p(title, H1), _p(address, BODY)], image]],
            colWidths=[CONTENT - COVER_LOGO_W, COVER_LOGO_W],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]),
        ), Spacer(1, 8)]
    story += [
        _table(
            [[_p("JOB", LABEL), _p("CONTRACTOR", LABEL), _p("CHECKLIST", LABEL)],
             [_p(job_cell), _p(contractor_cell), _p(checklist_cell)]],
            [CONTENT / 3] * 3,
        ),
        Spacer(1, 8),
    ]
    rows = [[_p(item), _p(where), _p(status, CELL_BOLD)] for item, where, status in checklist_rows]
    story += [
        _p("Checklist", H2),
        _table(
            [_heads("Required", "In this packet", "Status")] + rows,
            [3.9 * inch, CONTENT - 4.55 * inch, 0.65 * inch], extra=TIGHT,
        ),
        Spacer(1, 6),
        _p("Engineering checks", H2),
        _table(
            [_heads("Check", "Result", "Status")]
            + [[_p(name), _p(result), _p("Pass" if passed else "Fix", CELL_BOLD)]
               for name, result, passed in checks],
            [1.6 * inch, CONTENT - 2.25 * inch, 0.65 * inch], extra=TIGHT,
        ),
        Spacer(1, 6),
        _p("Flagged for your review", H2),
    ]
    half = (len(flags) + 1) // 2
    columns = [flags[:half], flags[half:]]
    story.append(Table(
        [[[_p(f"[  ]  {flag}", FLAG) for flag in column] for column in columns]],
        colWidths=[CONTENT / 2, CONTENT / 2],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
    ))
    return story


def review_page(items: list[str]) -> list:
    """The pre-submittal review: a sign-off table and the approval block."""
    return [
        _p("Pre-Submittal Review", H1),
        _p("Complete before sending this packet to the city.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Reviewed by", "Done")]
               + [[_p(item), _p("Electrician"), _p("[  ]")] for item in items],
               [CONTENT - 2 * inch, 1.4 * inch, 0.6 * inch]),
        Spacer(1, 14),
        _p("Approval", H2),
        _table([[_p("Reviewed by"), _p("")], [_p("Signature"), _p("")], [_p("Date"), _p("")]],
               [2 * inch, CONTENT - 2 * inch], head=False),
    ]


def application_page(
    *, rows: list[tuple[str, str]], scope: str, inspections: list[tuple[str, str]],
) -> list:
    """Permit application data: the fields, the scope of work and the inspection plan."""
    return [
        _p("Permit Application Data", H1),
        _p("Prepared for transfer to the city's permit application. This page is not the city's form.", SMALL),
        Spacer(1, 10),
        _table([[_p(a, CELL_BOLD), _p(b)] for a, b in rows], [2.4 * inch, CONTENT - 2.4 * inch], head=False),
        Spacer(1, 14),
        _p("Scope of work", H2),
        _p(scope, BODY),
        Spacer(1, 14),
        _p("Inspection plan", H2),
        _table([_heads("Stage", "What's inspected")] + [[_p(a), _p(b)] for a, b in inspections],
               [1.4 * inch, CONTENT - 1.4 * inch]),
    ]


def load_page(load, *, method: str, service_rows: list[tuple[str, str]]) -> list:
    """The load calculation table. `service_rows` are the lines under the computed load."""
    right = lambda text, style: Paragraph(
        f"{text:,.0f}", ParagraphStyle(f"{style.name}-right", parent=style, alignment=2))
    rows = [_heads("Load", "Basis", "VA")]

    def add(label, basis, va, bold=False):
        style = CELL_BOLD if bold else CELL
        rows.append([_p(label, style), _p(basis, style), right(va, style)])

    for line in load.lines:
        add(line.label, line.basis, line.va)
    add("Subtotal", "", load.subtotal_va, True)
    add("First 10,000 VA", "100%", load.first_va)
    add("Remainder", f"{load.subtotal_va - load.first_va:,.0f} VA x 40%", load.remainder_va)
    if load.hvac_va:
        add(load.hvac_label, "Larger of heating or cooling, 100%", load.hvac_va)
    for line in load.added_loads:
        add(line.label, line.basis, line.va)
    add("Total calculated load", "", load.total_va, True)
    return [
        _p("Load Calculation", H1),
        _p(method, SMALL),
        Spacer(1, 10),
        _table(rows, [2.5 * inch, CONTENT - 3.5 * inch, 1 * inch]),
        Spacer(1, 10),
        _table(
            [[_p("Computed load", CELL_BOLD),
              _p(f"{load.total_va:,.0f} VA / 240 V = {load.computed_amps:.1f} A", CELL_BOLD)]]
            + [[_p(label), _p(value)] for label, value in service_rows],
            [2.5 * inch, CONTENT - 2.5 * inch],
            head=False,
            extra=[("BACKGROUND", (0, 0), (-1, 0), SOFT)],
        ),
    ]
