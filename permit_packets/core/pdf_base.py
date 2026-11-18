"""What every permit packet shares: the page look, the cover and the review page."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from permit_packets.core.cad import CAD_SINK, CadPage, CadRecording
from permit_packets.core.layout import Sheet, content_w, current_sheet, print_magnification
from permit_packets.core.title_block import TitleBlock, draw_title_block
from reportlab.platypus import (
    KeepInFrame,
    Flowable,
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
WIDTH, HEIGHT = letter
# The contractor's logo for the packet being built, as PNG/JPEG bytes. Set per request.
CONTRACTOR_LOGO: ContextVar[bytes | None] = ContextVar("contractor_logo", default=None)
# Printed where there is no logo.
COMPANY_NAME: ContextVar[str] = ContextVar("company_name", default="")

HEADER_LOGO_H = 0.3 * inch
COVER_LOGO_W = 1.9 * inch
COVER_LOGO_H = 1.0 * inch

MARGIN = 0.7 * inch
# The letter content width. Diagrams are drawn at this width and scaled to the sheet.
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


def _page(canvas, doc) -> None:
    sheet = current_sheet()
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    logo = CONTRACTOR_LOGO.get()
    if logo and canvas.getPageNumber() > 1:
        reader = ImageReader(BytesIO(logo))
        width, height = reader.getSize()
        w = HEADER_LOGO_H * width / height
        canvas.drawImage(reader, sheet.width - sheet.margin - w, sheet.height - 0.5 * inch, w, HEADER_LOGO_H, mask="auto")
    elif not logo:
        canvas.drawRightString(sheet.width - sheet.margin, sheet.height - 0.42 * inch, COMPANY_NAME.get() or "Lilos Growth")
    canvas.restoreState()


class SheetMark(Flowable):
    """Zero-size marker at the top of each section: names the sheet the page is."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title

    def wrap(self, available_width, available_height):
        return 0, 0

    def draw(self) -> None:
        self.canv._sheet_title = self.title


# The sheet title of each page as it is drawn, for laying the pages out as a drawing set afterwards.
PAGE_TITLES: ContextVar[list[str] | None] = ContextVar("page_titles", default=None)


@contextmanager
def collect_page_titles():
    titles: list[str] = []
    token = PAGE_TITLES.set(titles)
    try:
        yield titles
    finally:
        PAGE_TITLES.reset(token)


class NumberedCanvas(CadRecording, Canvas):
    """Holds each page until the end, so the title block can say the real page count."""

    def __init__(self, *args, block: TitleBlock, sheet: Sheet, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []
        self._block = block
        self._sheet = sheet
        self._sheet_title = ""
        self._cad_init()

    def showPage(self) -> None:
        self._pages.append(dict(self.__dict__))
        self._cad_reset()
        self._startPage()

    def save(self) -> None:
        total = len(self._pages)
        titles = PAGE_TITLES.get()
        for page in self._pages:
            self.__dict__.update(page)
            if titles is not None:
                titles.append(self._sheet_title)
            self._cad_layer = "G-TTLB"
            draw_title_block(self, self._sheet, self._block, title=self._sheet_title,
                             number=self._pageNumber, total=total)
            self._cad_layer = None
            sink = CAD_SINK.get()
            if sink is not None:
                sink.magnification = print_magnification(self._sheet)
                sink.pages.append(CadPage(self._sheet_title, self._cad_ops, tuple(self._pagesize), self._cad_site))
            super().showPage()
        super().save()


def build_document(sections: list[list], *, title: str, block: TitleBlock, sheet_titles: list[str]) -> bytes:
    """Every section is one sheet. `sheet_titles` names each one in its title block."""
    assert len(sections) == len(sheet_titles), "one sheet title per section"
    sheet = current_sheet()
    story: list = []
    for index, (section, sheet_title) in enumerate(zip(sections, sheet_titles)):
        if index:
            story.append(PageBreak())
        story += [SheetMark(sheet_title)] + section
    if blank_sheet_needed():
        story += [PageBreak(), SheetMark("Reserved for DBI"), BlankSheet(BLANK_AREA.get())]
        sheet_titles = [*sheet_titles, "Reserved for DBI"]
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=(sheet.width, sheet.height), leftMargin=sheet.margin, rightMargin=sheet.margin,
        topMargin=sheet.top_margin, bottomMargin=sheet.frame_y,
        title=title, author="Lilos Growth",
    )
    frame = Frame(sheet.margin, sheet.frame_y, sheet.content_w, sheet.content_h,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=_page)])

    def canvas_maker(*args, **kwargs):
        return NumberedCanvas(*args, block=block, sheet=sheet, **kwargs)

    doc.build(story, canvasmaker=canvas_maker)
    return buffer.getvalue()


@dataclass
class BlankArea:
    """The empty area a city reserves on its title sheet, and whether the cover already carries it."""

    width_in: float
    height_in: float
    on_cover: bool = False


BLANK_AREA: ContextVar[BlankArea | None] = ContextVar("blank_area", default=None)
BLANK_MIN_FLAGS_W = 220.0  # the cover's flag list needs at least this much width beside the boxes
BLANK_MAX_BAND = 0.4  # and the boxes at most this share of the cover's height


@contextmanager
def use_blank_area(inches: tuple[float, float] | None):
    area = BlankArea(*inches) if inches else None
    token = BLANK_AREA.set(area)
    try:
        yield area
    finally:
        BLANK_AREA.reset(token)


def _blank_size_on_cover(area: BlankArea, stamp: float) -> tuple[float, float] | None:
    """The area's (width, height) in points, in the orientation that fits beside the stamp box, else None."""
    sheet = current_sheet()
    for w, h in ((area.width_in * inch, area.height_in * inch), (area.height_in * inch, area.width_in * inch)):
        if max(stamp, h) + 4 <= BLANK_MAX_BAND * sheet.content_h and sheet.content_w - stamp - w - 32 >= BLANK_MIN_FLAGS_W:
            return w, h
    return None


class BlankAreaBox(Flowable):
    """An empty rectangle at its true size, labeled for the agency that stamps it."""

    def __init__(self, width: float, height: float) -> None:
        super().__init__()
        self.box_w, self.box_h = width, height

    def wrap(self, available_width, available_height):
        return self.box_w, self.box_h

    def draw(self) -> None:
        _draw_blank(self.canv, 0, 0, self.box_w, self.box_h)


def _draw_blank(c, x: float, y: float, w: float, h: float) -> None:
    c.saveState()
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.setDash(4, 3)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.setDash()
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawCentredString(x + w / 2, y + h - 14, "Reserved for DBI")
    c.setFont("Helvetica", 6.6)
    c.drawCentredString(x + w / 2, y + h - 25, f"Empty {w / inch:g} in x {h / inch:g} in area for agency stamps")
    c.restoreState()


class BlankSheet(Flowable):
    """A sheet that is the blank area: a letter page cannot hold an 8.5 x 11 in area inside its margins, so
    the rectangle is drawn at the page edge, at its true size."""

    def __init__(self, area: BlankArea) -> None:
        super().__init__()
        self.area = area

    def wrap(self, available_width, available_height):
        return 0, 0

    def draw(self) -> None:
        sheet = current_sheet()
        w, h = self.area.width_in * inch, self.area.height_in * inch
        if h > sheet.height or w > sheet.width:
            w, h = h, w
        # A zero-height flowable is drawn at the top left of the frame, (margin, height - top_margin) on the page.
        _draw_blank(self.canv, -sheet.margin, sheet.top_margin - sheet.height, min(w, sheet.width), min(h, sheet.height))


def blank_sheet_needed() -> bool:
    """True when the title sheet's blank area could not go on the cover and gets a sheet of its own."""
    area = BLANK_AREA.get()
    return area is not None and not area.on_cover


class StampBox(Flowable):
    """An empty square the city stamps, at its true size."""

    def __init__(self, side: float) -> None:
        super().__init__()
        self.side = side

    def wrap(self, available_width, available_height):
        return self.side, self.side

    def draw(self) -> None:
        c = self.canv
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.setDash(4, 3)
        c.rect(0, 0, self.side, self.side, stroke=1, fill=0)
        c.setDash()
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawCentredString(self.side / 2, self.side - 12, "Reserved for city stamp")
        c.setFont("Helvetica", 6.6)
        inches = self.side / inch
        c.drawCentredString(self.side / 2, 6, f"{inches:g} in x {inches:g} in")


# On a 22 x 34 in drawing set the flags are the electrician's to-dos, not drawings: they move from the
# cover to the Pre-Submittal Review page (a supplemental 8.5 x 11 in page), so the cover keeps full-size text.
MOVED_FLAGS: ContextVar[list[str] | None] = ContextVar("moved_flags", default=None)


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
    stamp_box_in: float | None = None,
) -> list:
    """The first page: the job, the city's checklist, the engineering checks and the flags.

    When the city reserves a stamp area, an empty square of exactly that size sits at the foot of the
    page, drawn outside the shrink-to-fit so it keeps its true size.
    """
    sheet = current_sheet()
    width, height = sheet.content_w, sheet.content_h
    if sheet.key == "ansi_d":
        # The drawing set puts the 2 x 2 in stamp area on every sheet at true size (core/drawing_sets.py).
        stamp_box_in = None
        if flags:
            MOVED_FLAGS.set(list(flags))
            flags = [f"{len(flags)} items for the electrician are on the Pre-Submittal Review page."]
    head = [_p(title, H1), _p(address, BODY)]
    logo = CONTRACTOR_LOGO.get()
    if logo:
        reader = ImageReader(BytesIO(logo))
        w, h = reader.getSize()
        scale = min(COVER_LOGO_W / w, COVER_LOGO_H / h)
        image = Image(BytesIO(logo), w * scale, h * scale)
        head = [Table(
            [[head, image]],
            colWidths=[width - COVER_LOGO_W, COVER_LOGO_W],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]),
        )]
    info = _table(
        [[_p("JOB", LABEL), _p("CONTRACTOR", LABEL), _p("CHECKLIST", LABEL)],
         [_p(job_cell), _p(contractor_cell), _p(checklist_cell)]],
        [width / 3] * 3,
    )
    rows = [[_p(item), _p(where), _p(status, CELL_BOLD)] for item, where, status in checklist_rows]
    check_rows = [[_p(name), _p(result), _p("Pass" if passed else "Fix", CELL_BOLD)]
                  for name, result, passed in checks]

    def checklist_table(w):
        return _table([_heads("Required", "In this packet", "Status")] + rows,
                      [w * 0.5, w - w * 0.5 - 0.65 * inch, 0.65 * inch], extra=TIGHT)

    def checks_table(w):
        return _table([_heads("Check", "Result", "Status")] + check_rows,
                      [w * 0.3, w - w * 0.3 - 0.65 * inch, 0.65 * inch], extra=TIGHT)

    if sheet.landscape:
        left, right = width * 0.56, width * 0.44 - 14
        body = [Table(
            [[[_p("Checklist", H2), checklist_table(left)], [_p("Engineering checks", H2), checks_table(right)]]],
            colWidths=[left + 14, right],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
        )]
    else:
        body = [_p("Checklist", H2), checklist_table(width), Spacer(1, 6),
                _p("Engineering checks", H2), checks_table(width)]

    def flag_columns(columns: int, w: float):
        per = -(-len(flags) // columns) or 1
        chunks = [flags[i:i + per] for i in range(0, len(flags), per)] or [[]]
        return Table(
            [[[_p(f"[  ]  {flag}", FLAG) for flag in chunk] for chunk in chunks]],
            colWidths=[w / len(chunks)] * len(chunks),
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]),
        )

    top = head + [Spacer(1, 8), info, Spacer(1, 8)] + body + [Spacer(1, 6), _p("Flagged for your review", H2)]
    # The cover is always one page: a long flag list shrinks to fit rather than pushing every
    # later page (and every "Page N" reference) back by one.
    if stamp_box_in is None:
        columns = 3 if sheet.landscape else 2
        return [KeepInFrame(width, height - 4, top + [flag_columns(columns, width)], mode="shrink")]
    stamp = stamp_box_in * inch
    area = BLANK_AREA.get()
    blank = _blank_size_on_cover(area, stamp) if area else None
    if blank:
        area.on_cover = True
    blank_w = blank[0] + 16 if blank else 0
    band = max(stamp, blank[1] if blank else 0) + 4
    flags_w = width - stamp - blank_w - 16
    main_h = height - band - 12
    lower = Table(
        [[KeepInFrame(flags_w, band, [flag_columns(2 if sheet.landscape else 1, flags_w)], mode="shrink"),
          *([BlankAreaBox(*blank)] if blank else []), StampBox(stamp)]],
        colWidths=[flags_w + 16, *([blank_w] if blank else []), stamp], rowHeights=[band],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                          ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
    )
    return [KeepInFrame(width, main_h, top, mode="shrink"), Spacer(1, 4), lower]


def review_page(items: list[str]) -> list:
    """The pre-submittal review: a sign-off table and the approval block, and the cover's flags when a
    drawing set moved them here."""
    moved = MOVED_FLAGS.get()
    flagged = ([Spacer(1, 14), _p("Flagged for your review", H2)] + [_p(f"[  ]  {flag}", FLAG) for flag in moved]
               if moved else [])
    if moved:
        MOVED_FLAGS.set(None)
    return [
        _p("Pre-Submittal Review", H1),
        _p("Complete before sending this packet to the city.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Reviewed by", "Done")]
               + [[_p(item), _p("Electrician"), _p("[  ]")] for item in items],
               [content_w() - 2 * inch, 1.4 * inch, 0.6 * inch]),
        Spacer(1, 14),
        _p("Approval", H2),
        _table([[_p("Reviewed by"), _p("")], [_p("Signature"), _p("")], [_p("Date"), _p("")]],
               [2 * inch, content_w() - 2 * inch], head=False),
    ] + flagged


def application_page(
    *, rows: list[tuple[str, str]], scope: str, inspections: list[tuple[str, str]],
) -> list:
    """Permit application data: the fields, the scope of work and the inspection plan."""
    return [
        _p("Permit Application Data", H1),
        _p("Prepared for transfer to the city's permit application. This page is not the city's form.", SMALL),
        Spacer(1, 10),
        _table([[_p(a, CELL_BOLD), _p(b)] for a, b in rows], [2.4 * inch, content_w() - 2.4 * inch], head=False),
        Spacer(1, 14),
        _p("Scope of work", H2),
        _p(scope, BODY),
        Spacer(1, 14),
        _p("Inspection plan", H2),
        _table([_heads("Stage", "What's inspected")] + [[_p(a), _p(b)] for a, b in inspections],
               [1.4 * inch, content_w() - 1.4 * inch]),
    ]


def load_page(load, *, method: str, service_rows: list[tuple[str, str]], measured=None) -> list:
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
        _table(rows, [2.5 * inch, content_w() - 3.5 * inch, 1 * inch]),
        Spacer(1, 10),
        _table(
            [[_p("Computed load", CELL_BOLD),
              _p(f"{load.total_va:,.0f} VA / 240 V = {load.computed_amps:.1f} A", CELL_BOLD)]]
            + [[_p(label), _p(value)] for label, value in service_rows],
            [2.5 * inch, content_w() - 2.5 * inch],
            head=False,
            extra=[("BACKGROUND", (0, 0), (-1, 0), SOFT)],
        ),
    ] + (_measured_demand(measured) if measured else [])


def _measured_demand(measured) -> list:
    """The NEC 220.87 check, under the 220.82 calculation, when demand data is supplied."""
    from permit_packets.core.load_calculation import DEMAND_SOURCES
    rows = [
        [_p("Maximum demand"), _p(f"{measured.peak_kw:g} kW, {DEMAND_SOURCES[measured.source].lower()}")],
        [_p("Existing load at 125%"), _p(f"{measured.peak_kw:g} kW x 1,000 x 125% = {measured.existing_va:,.0f} VA")],
        [_p(measured.new_label), _p(f"{measured.new_va:,.0f} VA")],
        [_p("Total", CELL_BOLD), _p(f"{measured.total_va:,.0f} VA / {measured.volts} V = {measured.amps:.1f} A on a "
                                     f"{measured.service_amps} A service", CELL_BOLD)],
        [_p("Result"), _p(f"{measured.service_amps - measured.amps:.1f} A to spare" if measured.fits
                          else f"Over by {measured.amps - measured.service_amps:.1f} A")],
    ]
    return [
        Spacer(1, 14),
        _p("Existing load by measured demand (NEC 220.87)", H2),
        _p("Maximum demand at 125% plus the new load must not exceed the service rating. "
           "Attach the demand report behind this page.", SMALL),
        Spacer(1, 6),
        _table(rows, [2.5 * inch, content_w() - 2.5 * inch], head=False),
    ]


class FittedDiagram(Flowable):
    """A diagram drawn at the letter content width, scaled up to the sheet, with its data strip below.

    The strip is drawn at true size under the diagram, so every line stays readable at 100%.
    """

    def __init__(self, inner: Flowable, *, legend: list[str] | None = None, max_h: float | None = None) -> None:
        super().__init__()
        self.inner = inner
        self.legend = legend or []
        self.max_h = max_h

    def _legend_height(self, width: float) -> float:
        if not self.legend:
            return 0
        columns = 2 if width > 400 and len(self.legend) > 3 else 1
        rows = -(-len(self.legend) // columns)
        return rows * 10.5 + 10

    def wrap(self, available_width, available_height):
        width = content_w()
        legend_h = self._legend_height(width)
        room = min(available_height, self.max_h or available_height) - legend_h - 6
        self.factor = min(width / CONTENT, room / self.inner.height)
        self.legend_h = legend_h
        self.width = width
        self.height = self.inner.height * self.factor + legend_h + (6 if legend_h else 0)
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.translate((self.width - CONTENT * self.factor) / 2, self.legend_h + (6 if self.legend_h else 0))
        c.scale(self.factor, self.factor)
        self.inner.drawOn(c, 0, 0)
        c.restoreState()
        if self.legend:
            columns = 2 if self.width > 400 and len(self.legend) > 3 else 1
            rows = -(-len(self.legend) // columns)
            c.saveState()
            c.setStrokeColor(INK)
            c.setLineWidth(0.6)
            c.rect(0, 0, self.width, self.legend_h, stroke=1, fill=0)
            c.setFillColor(INK)
            c.setFont("Helvetica", 7.6)
            for index, line in enumerate(self.legend):
                column, row = divmod(index, rows)
                c.drawString(6 + column * self.width / columns, self.legend_h - 11 - row * 10.5, line)
            c.restoreState()


def diagram(inner: Flowable, *, legend: list[str] | None = None, share: float = 0.38) -> FittedDiagram:
    """Fit a diagram to the sheet: at most `share` of the page height, scaled up from the letter drawing."""
    return FittedDiagram(inner, legend=legend, max_h=current_sheet().content_h * share)


def fit_page(story: list) -> list:
    """Keep a page to one sheet: content that runs long shrinks to fit rather than spilling onto another."""
    sheet = current_sheet()
    return [KeepInFrame(sheet.content_w, sheet.content_h - 4, story, mode="shrink")]


def heat_block(heat, jurisdiction) -> list:
    """The temperature correction worked out on the one-line page: base ampacity, factor, corrected ampacity, breaker."""
    if heat is None:
        return []
    degree = "\N{DEGREE SIGN}"
    carries = heat.carries_label.capitalize() if heat.carries_label == "breaker" else heat.carries_label
    rows = [
        _heads("Conductor", f"Base ampacity, 90{degree}C", "Correction factor", "Corrected ampacity",
               f"Limit, {heat.cap_column}{degree}C terminals", carries, "Result"),
        [_p(heat.wire), _p(f"{heat.base_90c} A"), _p(f"{heat.factor:.2f}"), _p(f"{heat.corrected_a:.1f} A"),
         _p(f"{heat.cap_a} A"), _p(f"{heat.carries_a:g} A"), _p("OK" if heat.passed else "Too small", CELL_BOLD)],
    ]
    w = content_w()
    source = f" Source: {jurisdiction.design_ambient_source}" if jurisdiction.design_ambient_source else ""
    return [
        Spacer(1, 10),
        _p("Temperature correction, outdoor conductors (NEC 310.15(B)(1))", H2),
        _table(rows, [w * 0.18, w * 0.15, w * 0.13, w * 0.15, w * 0.16, w * 0.12, w * 0.11]),
        Spacer(1, 3),
        _p(f"{heat.line}.", SMALL),
        _p(f"Design ambient {heat.ambient_f}{degree}F ({heat.ambient_c:.1f}{degree}C): "
           f"{jurisdiction.design_ambient_label} for {jurisdiction.name}.{source} The corrected ampacity is limited to the "
           f"{heat.cap_column}{degree}C terminal rating (NEC 110.14(C)).", SMALL),
    ]
