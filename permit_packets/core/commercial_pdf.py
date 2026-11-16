"""Pages and drawings the commercial packets share: the 3-phase one-line, the service load table and
the schematic site plan used when no property plan was picked."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, Paragraph, Spacer

from permit_packets.core.commercial import DEMAND_BASES, ServiceLoad
from permit_packets.core.pdf_base import (
    CELL, CELL_BOLD, CONTENT, COPPER, GREEN, H1, H2, INK, MUTED, PALE, SMALL, SOFT,
    _heads, _p, _table, content_w,
)

DEGREE = "\N{DEGREE SIGN}"
PHI = "\N{GREEK CAPITAL LETTER PHI}"


def phase_text(system) -> str:
    return f"3{PHI}, 4-wire" if system.phases == 3 else f"1{PHI}, 3-wire"


def draw_box(c, x: float, mid: float, w: float, h: float, title: str, lines: list[str], fill=colors.white) -> None:
    c.setFillColor(fill)
    c.setStrokeColor(INK)
    c.setLineWidth(1.3)
    c.roundRect(x, mid - h / 2, w, h, 3, stroke=1, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 7.4)
    c.drawCentredString(x + w / 2, mid + h / 2 + 6, title)
    c.setFont("Helvetica", 6.9)
    top = mid + (len(lines) - 1) * 5
    for i, line in enumerate(lines):
        c.drawCentredString(x + w / 2, top - i * 10 - 2, line)


def draw_conductors(c, x1: float, x2: float, y: float, hots: int, *, neutral: bool = True) -> None:
    """A run drawn as one line with a slash for every conductor: each hot, then the neutral."""
    c.setStrokeColor(INK)
    c.setLineWidth(1.5)
    c.line(x1, y, x2, y)
    count = hots + (1 if neutral else 0)
    span = 5.2 * (count - 1)
    start = (x1 + x2) / 2 - span / 2
    c.setLineWidth(1)
    for i in range(count):
        sx = start + i * 5.2
        c.line(sx - 2, y - 4.5, sx + 2, y + 4.5)


def ground_symbol(c, x: float, top: float) -> float:
    """Three bars hanging from `top`. Returns where the symbol ends."""
    c.setStrokeColor(GREEN)
    c.setLineWidth(1.2)
    c.line(x, top, x, top - 16)
    for i, half in enumerate((13, 8, 3)):
        c.line(x - half, top - 16 - i * 4, x + half, top - 16 - i * 4)
    return top - 16 - 8


class OneLineFlow(Flowable):
    """A row of equipment boxes joined by conductor runs, for any commercial job.

    `boxes` are (title, lines, filled) left to right; `runs` label each of the joins between them as
    (heading, detail lines, hots). `grounds` are (box index, caption) pairs."""

    def __init__(self, boxes, runs, grounds=(), *, height: float = 178) -> None:
        super().__init__()
        self.boxes, self.runs, self.grounds = boxes, runs, grounds
        self.width = CONTENT
        self.height = height

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        count = len(self.boxes)
        box_w, box_h, mid = 80, 64, 104
        gap = (CONTENT - count * box_w) / (count - 1)
        xs = [i * (box_w + gap) for i in range(count)]
        for x, (title, lines, filled) in zip(xs, self.boxes):
            draw_box(c, x, mid, box_w, box_h, title, lines, SOFT if filled else colors.white)
        for i, (heading, details, hots, *rest) in enumerate(self.runs):
            left, right = xs[i] + box_w, xs[i + 1]
            draw_conductors(c, left, right, mid, hots, neutral=rest[0] if rest else True)
            centre = (left + right) / 2
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 6.8)
            c.drawCentredString(centre, mid + 14, heading)
            c.setFont("Helvetica", 6.3)
            for j, line in enumerate(details):
                c.drawCentredString(centre, mid - 14 - j * 8.4, line)
        for index, caption in self.grounds:
            gx = xs[index] + box_w / 2
            end = ground_symbol(c, gx, mid - box_h / 2)
            c.setFillColor(GREEN)
            c.setFont("Helvetica", 6.6)
            if index == count - 1:  # the last box has no room to its right
                c.drawRightString(gx - 16, end + 2, caption)
            else:
                c.drawString(gx + 16, end + 2, caption)


class SchematicSite(Flowable):
    """A labeled layout from the job's details, not a survey, for a packet with no property plan."""

    scale = 2.6

    def __init__(self, *, kind: str, equipment: str, panel_text: str, route_text: str) -> None:
        super().__init__()
        self.kind, self.equipment, self.panel_text, self.route_text = kind, equipment, panel_text, route_text
        self.width = CONTENT
        self.height = 120 * self.scale + 36

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        k = self.scale
        ox, oy = (CONTENT - 100 * k) / 2 - 40, 24
        x = lambda v: ox + v * k
        y = lambda v: oy + v * k
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.setDash(6, 3)
        c.rect(x(0), y(0), 100 * k, 120 * k, stroke=1, fill=0)
        c.setDash()

        def block(bx, by, bw, bh, words, fill=PALE):
            c.setFillColor(fill)
            c.setStrokeColor(INK)
            c.setLineWidth(1.2)
            c.rect(x(bx), y(by), bw * k, bh * k, stroke=1, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8)
            for i, word in enumerate(words):
                c.drawCentredString(x(bx + bw / 2), y(by + bh / 2) + 2 - i * 10, word)

        block(10, 64, 56, 44, ["EXISTING", "BUILDING"])
        panel = (60, 72)
        if self.kind == "ev_lot":
            c.setFillColor(colors.white)
            c.setStrokeColor(MUTED)
            c.setLineWidth(0.6)
            c.rect(x(10), y(8), 80 * k, 44 * k, stroke=1, fill=1)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 7.2)
            c.drawCentredString(x(50), y(14), "PARKING AREA")
            c.setStrokeColor(MUTED)
            for i in range(6):
                c.line(x(18 + i * 11), y(26), x(18 + i * 11), y(42))
            equipment = (38, 34)
            route = [panel, (72, 56), (38, 56), equipment]
        elif self.kind == "detached":
            block(62, 10, 28, 24, ["DETACHED", "BUILDING"], colors.white)
            equipment = (66, 26)
            route = [panel, (74, 60), (74, 34), (70, 30)]
        elif self.kind == "exterior":
            equipment = (66, 92)
            route = [panel, equipment]
        else:
            panel, equipment = (60, 72), (22, 72)
            route = [panel, equipment]
        c.setStrokeColor(COPPER)
        c.setLineWidth(2.2)
        pts = [(x(a), y(b)) for a, b in route]
        c.lines([(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1)])
        c.setFillColor(INK)
        c.rect(x(panel[0]) - 7, y(panel[1]) - 5, 7, 10, stroke=0, fill=1)
        c.setFillColor(GREEN)
        c.rect(x(equipment[0]) - 7, y(equipment[1]) - 5, 7, 10, stroke=0, fill=1)
        lx, ly = x(100) + 18, y(112)
        c.setFont("Helvetica", 8)
        for i, (color, text) in enumerate(((INK, self.panel_text), (GREEN, self.equipment))):
            c.setFillColor(color)
            c.rect(lx, ly - i * 16, 8, 8, stroke=0, fill=1)
            c.setFillColor(INK)
            c.drawString(lx + 13, ly - i * 16, text)
        c.setStrokeColor(COPPER)
        c.setLineWidth(2.2)
        c.line(lx - 2, ly - 29, lx + 10, ly - 29)
        c.setFillColor(INK)
        c.drawString(lx + 13, ly - 32, self.route_text)
        c.setFont("Helvetica", 7.2)
        c.setFillColor(MUTED)
        c.drawString(lx, ly - 56, "Schematic, not to scale.")
        c.drawString(lx, ly - 67, "Field verify the route.")
        c.setFillColor(INK)
        c.setFont("Helvetica", 7.5)
        c.drawString(lx, y(8), "N  ^  (plan up)")


def service_load_page(load: ServiceLoad, *, method: str, result_rows: list[tuple[str, str]],
                      title: str = "Load Calculation") -> list:
    """The service load: the existing demand, each new load after its factor, and the line current."""
    right = lambda value, style: Paragraph(
        f"{value:,.0f}", ParagraphStyle(f"{style.name}-right", parent=style, alignment=2))
    rows = [_heads("Load", "Basis", "VA")]

    def add(label, basis, va, bold=False):
        style = CELL_BOLD if bold else CELL
        rows.append([_p(label, style), _p(basis, style), right(va, style)])

    factor = "" if load.existing_basis == "calculated" else " x 125%"
    add("Existing load", f"{load.existing_kva:g} kVA{factor}: {DEMAND_BASES[load.existing_basis].lower()}",
        load.existing_va)
    for line in load.lines:
        add(line.label, line.basis, line.va)
    add("Total calculated load", "", load.total_va, True)
    system = load.system
    divisor = f"1.732 x {system.volts} V" if system.phases == 3 else f"{system.volts} V"
    return [
        _p(title, H1),
        _p(method, SMALL),
        Spacer(1, 10),
        _table(rows, [2.2 * inch, content_w() - 3.2 * inch, 1 * inch]),
        Spacer(1, 10),
        _table(
            [[_p("Computed load", CELL_BOLD),
              _p(f"{load.total_va:,.0f} VA / ({divisor}) = {load.amps:.1f} A", CELL_BOLD)]]
            + [[_p(label), _p(value)] for label, value in result_rows],
            [2.2 * inch, content_w() - 2.2 * inch], head=False,
            extra=[("BACKGROUND", (0, 0), (-1, 0), SOFT)],
        ),
    ]


def conductor_text(feeder) -> str:
    from permit_packets.core.conductors import wire_label

    size, metal = wire_label(feeder.conductor.size), "Cu" if feeder.material == "copper" else "Al"
    return f"{feeder.system.hots} {size} {metal} + {size} N + {wire_label(feeder.egc)} EGC"


__all__ = ["DEGREE", "H2", "OneLineFlow", "SchematicSite", "conductor_text", "draw_box", "phase_text",
           "service_load_page"]
