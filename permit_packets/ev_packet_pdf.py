"""Render an EV charger permit packet as a 7-page draft PDF.

The checklist comes from the job's jurisdiction. The site plan is the property
to scale when there's a plan, and a labeled schematic when there isn't.
"""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from permit_packets.ev_charger import BURIAL_DEPTH_IN, LOCATION_LABELS, EvPacket
from permit_packets.core.site_plan import AerialSitePlan

INK = colors.HexColor("#15212c")
MUTED = colors.HexColor("#566572")
RULE = colors.HexColor("#cfd7dd")
COPPER = colors.HexColor("#a8551f")
SOFT = colors.HexColor("#f4e4d8")
GREEN = colors.HexColor("#1f7a58")
PALE = colors.HexColor("#eef1f3")
WATERMARK = colors.HexColor("#e9edf0")
WIDTH, HEIGHT = letter
MARGIN = 0.7 * inch
CONTENT = WIDTH - 2 * MARGIN
SECTION_PAGES = {
    "application": 2, "site_plan": 3, "one_line": 4, "load": 5, "equipment": 6, "review": 7,
}


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
    canvas.saveState()
    canvas.setFillColor(WATERMARK)
    canvas.setFont("Helvetica-Bold", 58)
    canvas.translate(WIDTH / 2, HEIGHT / 2)
    canvas.rotate(38)
    canvas.drawCentredString(0, -20, "DEMO")
    canvas.restoreState()
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(COPPER)
    canvas.drawString(MARGIN, HEIGHT - 0.42 * inch, "DEMO PACKET: NOT FOR SUBMISSION")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
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


class SitePlan(Flowable):
    """A schematic layout from the job details, not a survey."""

    scale = 2.75

    def __init__(self, packet: EvPacket) -> None:
        super().__init__()
        self.packet = packet
        self.width = CONTENT
        self.height = 120 * self.scale + 36

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        k = self.scale
        ox = (CONTENT - 80 * k) / 2 - 40
        oy = 24
        x = lambda v: ox + v * k
        y = lambda v: oy + v * k
        job = self.packet.job

        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.setDash(6, 3)
        c.rect(x(0), y(0), 80 * k, 120 * k, stroke=1, fill=0)
        c.setDash()

        def building(bx, by, bw, bh, title, note=None, fill=PALE):
            c.setFillColor(fill)
            c.setStrokeColor(INK)
            c.setLineWidth(1.2)
            c.rect(x(bx), y(by), bw * k, bh * k, stroke=1, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8.2)
            for i, word in enumerate(title):
                c.drawCentredString(x(bx + bw / 2), y(by + bh / 2) + 2 - i * 10, word)
            if note:
                c.setFont("Helvetica", 7.2)
                c.drawCentredString(x(bx + bw / 2), y(by + bh / 2) - 9, note)

        building(12, 30, 54, 44, ["EXISTING HOUSE"], f"{job.home.square_feet:,} sq ft")
        panel = (66, 58)
        if job.location == "detached_garage":
            building(44, 90, 26, 24, ["DETACHED", "GARAGE"], fill=colors.white)
            route = [panel, (74, 58), (74, 101), (70, 101)]
            charger = (70, 101)
        elif job.location == "attached_garage":
            building(12, 74, 30, 22, ["ATTACHED", "GARAGE"], fill=colors.white)
            # Inside the house, up through the shared wall to the garage.
            route = [panel, (38, 58), (38, 79), (40, 79)]
            charger = (42, 79)
        else:
            route = [panel, (66, 44)]
            charger = (66, 44)

        c.setStrokeColor(MUTED)
        c.setFillColor(colors.white)
        c.setLineWidth(0.6)
        c.rect(x(50), y(0), 16 * k, 30 * k, stroke=1, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7)
        c.drawCentredString(x(58), y(14), "Driveway")
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(x(40), oy - 11, "STREET (front property line)")

        c.setStrokeColor(COPPER)
        c.setLineWidth(2.2)
        if self.packet.job.trench_ft:
            c.setDash(7, 3)
        points = [(x(a), y(b)) for a, b in route]
        c.lines([(*points[i], *points[i + 1]) for i in range(len(points) - 1)])
        c.setDash()

        c.setFillColor(COPPER)
        c.rect(x(panel[0]) - 7, y(panel[1]) - 5, 7, 10, stroke=0, fill=1)
        c.setFillColor(INK)
        c.rect(x(charger[0]) - 7, y(charger[1]) - 5, 7, 10, stroke=0, fill=1)
        if self.packet.disconnect_amps:
            c.setFillColor(GREEN)
            c.rect(x(charger[0]) - 7, y(charger[1]) + 7, 7, 10, stroke=0, fill=1)

        lx = x(80) + 20
        ly = y(112)
        items = [
            (COPPER, f"Main panel, {job.service_amps} A (existing)"),
            (INK, f"{job.charger_amps} A EV charger (new)"),
        ]
        if self.packet.disconnect_amps:
            items.insert(1, (GREEN, f"{self.packet.disconnect_amps} A disconnect (new)"))
        c.setFont("Helvetica", 8)
        for i, (color, text) in enumerate(items):
            c.setFillColor(color)
            c.rect(lx, ly - i * 16, 8, 8, stroke=0, fill=1)
            c.setFillColor(INK)
            c.drawString(lx + 13, ly - i * 16, text)
        route_y = ly - len(items) * 16
        c.setStrokeColor(COPPER)
        c.setLineWidth(2.2)
        c.line(lx - 2, route_y + 3, lx + 10, route_y + 3)
        c.setFillColor(INK)
        c.drawString(lx + 13, route_y, f"New circuit, {job.run_ft} ft")
        c.setFont("Helvetica", 7.2)
        c.setFillColor(MUTED)
        notes = ["Schematic, not to scale.", "Field verify the route."]
        if job.trench_ft:
            notes.append(f"{job.trench_ft} ft underground.")
        for i, note in enumerate(notes):
            c.drawString(lx, route_y - 24 - i * 11, note)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(INK)
        c.drawString(lx, y(8), "N  ^  (plan up)")


class OneLine(Flowable):
    def __init__(self, packet: EvPacket) -> None:
        super().__init__()
        self.packet = packet
        self.width = CONTENT
        self.height = 170

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        packet = self.packet
        circuit = packet.circuit
        job = packet.job
        mid = 100
        box_w = 84
        box_h = 62

        def box(bx, title, lines, fill=colors.white):
            c.setFillColor(fill)
            c.setStrokeColor(INK)
            c.setLineWidth(1.3)
            c.roundRect(bx, mid - box_h / 2, box_w, box_h, 3, stroke=1, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7.6)
            c.drawCentredString(bx + box_w / 2, mid + box_h / 2 + 6, title)
            c.setFont("Helvetica", 7)
            for i, line in enumerate(lines):
                c.drawCentredString(bx + box_w / 2, mid + 8 - i * 10, line)

        xs = [0, 120]
        box(xs[0], "UTILITY METER", ["Existing", "120/240 V", "1-phase"])
        box(xs[1], "MAIN PANEL",
            [f"{job.service_amps} A service", f"New {circuit.breaker} A, 2-pole",
             f"{job.open_breaker_spaces} spaces open"], SOFT)
        charger_x = CONTENT - box_w
        if packet.disconnect_amps:
            disconnect_x = 290
            box(disconnect_x, "DISCONNECT",
                [f"{packet.disconnect_amps} A, 240 V", "Non-fused", LOCATION_LABELS[job.location].capitalize()])
            xs.append(disconnect_x)
        box(charger_x, "EV CHARGER",
            [f"{job.charger_amps} A Level 2", f"{packet.charger_va:,} VA", "UL listed"])
        xs.append(charger_x)

        c.setStrokeColor(INK)
        c.setLineWidth(1.5)
        for left, right in zip(xs, xs[1:]):
            c.line(left + box_w, mid, right, mid)

        label_x = (xs[1] + box_w + xs[2]) / 2
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7.2)
        c.drawCentredString(label_x, mid + 15, "New circuit")
        c.setFont("Helvetica", 6.8)
        c.drawCentredString(label_x, mid + 5, f"2 #{circuit.wire.size} Cu THWN-2")
        c.drawCentredString(label_x, mid - 10, f"1 #{circuit.ground} Cu EGC")
        c.drawCentredString(label_x, mid - 20, f"{job.run_ft} ft, see schedule")

        ground_x = xs[1] + box_w / 2
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.2)
        c.line(ground_x, mid - box_h / 2, ground_x, mid - box_h / 2 - 16)
        for i, half in enumerate((13, 8, 3)):
            c.line(ground_x - half, mid - box_h / 2 - 16 - i * 4, ground_x + half, mid - box_h / 2 - 16 - i * 4)
        c.setFillColor(GREEN)
        c.setFont("Helvetica", 7)
        c.drawString(ground_x + 17, mid - box_h / 2 - 22, "Existing grounding electrode system")


class Trench(Flowable):
    def __init__(self, conduit: str) -> None:
        super().__init__()
        self.conduit = conduit
        self.width = CONTENT
        self.height = 96

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        grade = 74
        c.setStrokeColor(INK)
        c.setLineWidth(1.5)
        c.line(0, grade, 150, grade)
        c.line(210, grade, CONTENT * 0.62, grade)
        c.setFillColor(PALE)
        c.setLineWidth(0.8)
        c.rect(150, 20, 60, grade - 20, stroke=1, fill=1)
        c.setFillColor(COPPER)
        c.circle(180, 28, 7, stroke=0, fill=1)
        c.setStrokeColor(INK)
        c.setLineWidth(0.6)
        c.line(225, grade, 225, 28)
        c.line(221, grade, 229, grade)
        c.line(221, 28, 229, 28)
        c.setFillColor(INK)
        c.setFont("Helvetica", 8)
        c.drawString(233, 50, f'{BURIAL_DEPTH_IN}" minimum cover')
        c.drawString(233, 38, "Confirm for the conduit type used")
        c.drawString(233, 18, f"{self.conduit} PVC conduit")
        c.drawString(4, grade + 6, "Finished grade")


def _checklist_row(packet: EvPacket, section: str) -> tuple[str, str]:
    job = packet.job
    plan = job.plan
    if section == "application":
        missing = job.jurisdiction.needs_parcel_number and not (plan and plan.parcel_number)
        return "Page 2: add the parcel number" if missing else "Page 2: fields ready for the city's form", (
            "Open" if missing else "Ready")
    if section == "site_plan":
        if plan:
            return f"Page 3: to scale, 1 in = {plan.scale_ft_per_in} ft", "Ready"
        return "Page 3: schematic only, replace it", "Open"
    if section == "equipment":
        return "Page 6: add manufacturer sheets", "Attach"
    if section == "ventilation":
        return "Only if this charger requires venting", "Check"
    if section == "hoa":
        return "Homeowner to confirm before work starts", "Open"
    return f"Page {SECTION_PAGES[section]}", "Ready"


def _cover(packet: EvPacket) -> list:
    job = packet.job
    jurisdiction = job.jurisdiction
    checklist_cell = (
        f"{jurisdiction.label}\nFrom the city's published checklist"
        if jurisdiction.known else f"{jurisdiction.label}\nGeneral checklist, city rules added in setup"
    )
    parcel = f"\nParcel {job.plan.parcel_number}" if job.plan and job.plan.parcel_number else ""
    story = [_p("EV Charger Permit Packet", H1), _p(job.address, BODY), Spacer(1, 8)]
    story += [
        _table(
            [[_p("JOB", LABEL), _p("CONTRACTOR", LABEL), _p("CHECKLIST", LABEL)],
             [_p(f"{job.home.square_feet:,} sq ft home{parcel}\n"
                 f"Charger at {LOCATION_LABELS[job.location]}\nCustomer: {job.customer}"),
              _p(f"{job.contractor}\nLicense {job.license_number}"),
              _p(checklist_cell)]],
            [CONTENT / 3] * 3,
        ),
        Spacer(1, 8),
    ]
    rows = []
    for requirement in jurisdiction.checklist:
        where, status = _checklist_row(packet, requirement.section)
        rows.append([_p(requirement.item), _p(where), _p(status, CELL_BOLD)])
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
            + [[_p(check.name), _p(check.result), _p("Pass" if check.passed else "Fix", CELL_BOLD)]
               for check in packet.checks],
            [1.6 * inch, CONTENT - 2.25 * inch, 0.65 * inch], extra=TIGHT,
        ),
        Spacer(1, 6),
        _p("Flagged for your review", H2),
    ]
    half = (len(packet.flags) + 1) // 2
    columns = [packet.flags[:half], packet.flags[half:]]
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


def scope_of_work(packet: EvPacket) -> str:
    job = packet.job
    circuit = packet.circuit
    destination = (
        f"to a new {packet.disconnect_amps} A disconnect, then to the charger"
        if packet.disconnect_amps else "to the charger"
    )
    route = (
        f"Trench about {job.trench_ft} ft and run" if job.trench_ft else "Run"
    )
    service_note = (
        "No service upgrade."
        if packet.load.computed_amps <= job.service_amps
        else "Service capacity must be resolved before submittal."
    )
    charger = f" ({job.charger_model})" if job.charger_model else ""
    return (
        f"Install one {job.charger_amps} A, 240 V Level 2 EV charger{charger}, {job.connection}, "
        f"at the {LOCATION_LABELS[job.location]}. "
        f"Add a {circuit.breaker} A, 2-pole breaker to the existing {job.service_amps} A main panel. "
        f"{route} a new dedicated {job.run_ft} ft branch circuit {destination}. {service_note}"
    )


def application_fields(packet: EvPacket) -> list[tuple[str, str]]:
    job = packet.job
    return [
        ("Project address", job.address),
        ("Parcel number", job.plan.parcel_number if job.plan and job.plan.parcel_number else "Not on file"),
        ("Jurisdiction", job.jurisdiction.label),
        ("Property owner", job.customer),
        ("Permit type", "Electrical, residential EV charger"),
        ("Charger", job.charger_model or "Add make and model"),
        ("Contractor", job.contractor),
        ("License number", job.license_number),
    ]


def _application(packet: EvPacket) -> list:
    job = packet.job
    scope = scope_of_work(packet)
    rows = application_fields(packet)
    inspections = [("Final", "Panel, breaker, charger, labeling, and manufacturer instructions on site")]
    if job.trench_ft:
        inspections.insert(0, ("Underground", "Open trench, conduit and burial depth, before backfill"))
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


def _one_line(packet: EvPacket) -> list:
    circuit = packet.circuit
    wires = f"2 #{circuit.wire.size} Cu THWN-2, 1 #{circuit.ground} Cu EGC"
    protection = f"{circuit.breaker} A, 2-pole"
    rows = []
    if packet.underground_conduit:
        rows.append(["Underground run", wires, f"{packet.underground_conduit} PVC, {packet.job.trench_ft} ft", protection])
    if packet.interior_ft:
        rows.append(["Above ground run", wires, f"{packet.interior_conduit} EMT, {packet.interior_ft} ft", protection])
    story = [
        _p("One-Line Diagram", H1),
        _p("Conductors, conduit sizes and types, and overcurrent protection.", SMALL),
        Spacer(1, 10),
        OneLine(packet),
        Spacer(1, 10),
        _p("Conductor and conduit schedule", H2),
        _table([_heads("Segment", "Conductors", "Conduit", "Protection")]
               + [[_p(cell) for cell in row] for row in rows],
               [1.6 * inch, 1.9 * inch, 1.6 * inch, CONTENT - 5.1 * inch]),
    ]
    if packet.underground_conduit:
        story += [Spacer(1, 12), _p("Trench detail", H2), Trench(packet.underground_conduit)]
    return story


def _load(packet: EvPacket) -> list:
    load = packet.load
    code = packet.job.jurisdiction.code_name
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
    add(load.hvac_label, "Larger of heating or cooling, 100%", load.hvac_va)
    for line in load.added_loads:
        add(line.label, line.basis, line.va)
    add("Total calculated load", "", load.total_va, True)
    result = (
        f"{load.spare_amps:.1f} A, so no upgrade is required"
        if load.spare_amps >= 0
        else f"Over by {-load.spare_amps:.1f} A, so this needs a fix before submittal"
    )
    return [
        _p("Load Calculation", H1),
        _p(f"Optional dwelling method, {code} 220.82, with the EV charger added at 100% of nameplate. "
           "Confirm the method the city accepts.", SMALL),
        Spacer(1, 10),
        _table(rows, [2.5 * inch, CONTENT - 3.5 * inch, 1 * inch]),
        Spacer(1, 10),
        _table(
            [[_p("Computed load", CELL_BOLD),
              _p(f"{load.total_va:,.0f} VA / 240 V = {load.computed_amps:.1f} A", CELL_BOLD)],
             [_p("Existing service"), _p(f"{load.service_amps} A")],
             [_p("Spare capacity"), _p(result)]],
            [2.5 * inch, CONTENT - 2.5 * inch],
            head=False,
            extra=[("BACKGROUND", (0, 0), (-1, 0), SOFT)],
        ),
    ]


def _equipment(packet: EvPacket) -> list:
    rows = [
        ("EV charger",
         f"{packet.job.charger_model or 'Level 2'}, {packet.job.charger_amps} A, 240 V, "
         f"{packet.charger_va:,} VA, {packet.job.connection}",
         f"UL listed, {packet.job.jurisdiction.code_name} Article 625"),
        ("Breaker", f"{packet.circuit.breaker} A, 2-pole, matched to existing panel", "Listed for the panel"),
    ]
    if packet.disconnect_amps:
        rows.append(("Disconnect", f"{packet.disconnect_amps} A, 240 V, non-fused, lockable, rated for location", "UL listed"))
    if packet.underground_conduit:
        rows.append(("Underground conduit", f"{packet.underground_conduit} PVC", "Listed"))
    if packet.interior_ft:
        rows.append(("Above ground conduit", f"{packet.interior_conduit} EMT", "Listed"))
    return [
        _p("Equipment Data", H1),
        _p("Attach the manufacturer's data sheets and UL listing information behind this page.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Listing")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, CONTENT - 3.2 * inch, 1.7 * inch]),
    ]


def _review(packet: EvPacket) -> list:
    items = [
        "Existing loads match the home",
        "Panel has two open spaces",
        "Breaker matches the panel listing",
        "Charger data sheets attached",
        "HOA approval received, if required",
        "Code edition confirmed with the city",
    ]
    if packet.job.trench_ft:
        items.insert(1, "Trench route and depth are confirmed")
    if packet.disconnect_amps:
        items.append("Disconnect requirement confirmed")
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


def _site_plan(packet: EvPacket) -> list:
    job = packet.job
    plan = job.plan
    if plan is None:
        return [
            _p("Site Plan", H1),
            _p("Shows the location of the charger, the main panel and the new circuit.", SMALL),
            Spacer(1, 10),
            SitePlan(packet),
        ]
    legend = [
        f"P  Main panel, {job.service_amps} A (existing)",
        f"EV  {job.charger_amps} A charger (new)",
    ]
    if packet.disconnect_amps:
        legend.append(f"D  {packet.disconnect_amps} A disconnect (new)")
    route = f"New circuit {'underground' if job.trench_ft else 'route'}, {plan.measured_route_ft} ft measured on plan"
    legend.append(route)
    if plan.lot:
        legend.append("Dashed yellow: lot line")
    measures = [f"Wire run with rises: {job.run_ft} ft"]
    setback = plan.charger_to_lot_line_ft
    if setback is not None:
        measures.append(f"Charger to nearest lot line: {setback} ft")
    measures.append(f"Scale 1 in = {plan.scale_ft_per_in} ft when printed at 100%")
    measures.append("Not a survey. Field verify all dimensions.")
    return [
        _p("Site Plan", H1),
        _p(job.address + (f". Parcel {plan.parcel_number}." if plan.parcel_number else "."), SMALL),
        Spacer(1, 6),
        AerialSitePlan(
            plan, disconnect=bool(packet.disconnect_amps), underground=bool(job.trench_ft), width=CONTENT,
        ),
        Spacer(1, 6),
        _table([[_p("\n".join(legend)), _p("\n".join(measures))]], [CONTENT / 2, CONTENT / 2], head=False),
        Spacer(1, 3),
        _p(". ".join(credit.rstrip(".") for credit in plan.credits) + ".", CREDIT),
    ]


def render_ev_packet_pdf(packet: EvPacket) -> bytes:
    sections = [
        _cover(packet), _application(packet), _site_plan(packet), _one_line(packet),
        _load(packet), _equipment(packet), _review(packet),
    ]
    story: list = []
    for index, section in enumerate(sections):
        if index:
            story.append(PageBreak())
        story += section
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.65 * inch, bottomMargin=0.65 * inch,
        title="EV Charger Permit Packet (demo)", author="Lilos Growth",
    )
    frame = Frame(MARGIN, 0.6 * inch, CONTENT, HEIGHT - 1.2 * inch,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=_page)])
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
