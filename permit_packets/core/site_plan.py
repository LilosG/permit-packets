"""The to-scale site plan page: the aerial with the job drawn on it."""
from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Spacer, Table, TableStyle

from permit_packets.core.cad import cad_layer, cad_site, cad_site_end
from permit_packets.core.layout import print_magnification, Sheet, current_sheet
from permit_packets.core.property_plan import PLAN_UNITS, PLAN_WIDTH_IN, Point, PropertyPlan

INK = colors.HexColor("#15212c")
COPPER = colors.HexColor("#c8682a")
LOT = colors.HexColor("#ffd84d")
PAPER = colors.HexColor("#eef1f3")
PLAN_PT = PLAN_WIDTH_IN * inch
MAX_LOT_LABELS = 12
MIN_LOT_LABEL_FT = 12
# Where along a lot line its dimension can go, tried in order so markers don't hide it.
LABEL_POSITIONS = (0.5, 0.35, 0.65, 0.2, 0.8, 0.1, 0.9)


HEADING_ALLOWANCE = 58.0  # page heading, spacers and the credit line, above and below the plan


def plan_print(plan: PropertyPlan, sheet: Sheet | None = None) -> tuple[float, int]:
    """(side in points, feet per printed inch) of the plan square on this sheet.

    The plan covers a fixed ground extent. On letter it prints 7 in square, so the engineer's scale
    the plan was made at is the printed scale. On a tabloid sheet it prints as large as fits, at the
    smallest whole number of feet per inch that keeps it on the page, so the stated scale is still
    exactly what a ruler on the page reads.
    """
    sheet = sheet or current_sheet()
    extent_ft = plan.scale_ft_per_in * PLAN_WIDTH_IN
    if not sheet.landscape:
        return PLAN_PT, plan.scale_ft_per_in
    room_in = (sheet.content_h - HEADING_ALLOWANCE) / inch
    ft_per_in = min(plan.scale_ft_per_in, max(1, math.ceil(extent_ft / room_in)))
    return extent_ft / ft_per_in * inch, ft_per_in


def printed_scale(plan: PropertyPlan) -> int | float:
    """The feet per inch the site plan states on the current sheet, as printed."""
    return _magnified(plan_print(plan)[1])


def _magnified(ft_per_in: int) -> int | float:
    """Feet per inch once a drawing sheet prints larger than drawn (2.5x on a 22 x 34 in set)."""
    value = ft_per_in / print_magnification()
    return int(value) if value == int(value) else round(value, 2)


def scale_text(ft_per_in: int) -> str:
    printed = _magnified(ft_per_in)
    architectural = {8: "1/8 in = 1 ft", 4: "1/4 in = 1 ft", 16: "1/16 in = 1 ft"}.get(printed)
    return f"1 in = {printed} ft" + (f" ({architectural})" if architectural else "")


@dataclass(frozen=True)
class PlanMarker:
    point: Point
    color: colors.Color
    letter: str


class AerialSitePlan(Flowable):
    """The plan's route is drawn between its route markers; `markers` are the dots on it."""

    def __init__(
        self, plan: PropertyPlan, *, markers: list[PlanMarker], underground: bool, width: float,
        side: float | None = None, ft_per_in: int | None = None, outline_over_aerial: bool = False,
    ) -> None:
        super().__init__()
        self.plan = plan
        self.outline_over_aerial = outline_over_aerial
        self.markers = markers
        self.underground = underground
        self.width = width
        self.side = side or PLAN_PT
        self.ft_per_in = ft_per_in or plan.scale_ft_per_in
        self.height = self.side
        self.left = (width - self.side) / 2
        self.placed: list[tuple[float, float, float, float]] = []

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def _xy(self, point: Point) -> tuple[float, float]:
        k = self.side / PLAN_UNITS
        return self.left + point[0] * k, self.side - point[1] * k

    def _polyline(self, points: list[Point], *, close: bool = False) -> None:
        path = self.canv.beginPath()
        path.moveTo(*self._xy(points[0]))
        for point in points[1:]:
            path.lineTo(*self._xy(point))
        if close:
            path.close()
        self.canv.drawPath(path, stroke=1, fill=0)

    def _label(self, x: float, y: float, text: str, *, bold: bool = False) -> bool:
        c = self.canv
        font = "Helvetica-Bold" if bold else "Helvetica"
        size = 7.4
        width = stringWidth(text, font, size) + 7
        height = 11.5
        box = (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        if any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in self.placed):
            return False
        self.placed.append(box)
        c.setFillColor(colors.white)
        c.setStrokeColor(INK)
        c.setLineWidth(0.4)
        c.roundRect(box[0], box[1], width, height, 2, stroke=1, fill=1)
        c.setFillColor(INK)
        c.setFont(font, size)
        c.drawCentredString(x, y - 2.6, text)
        return True

    def _marker(self, point: Point, color, text: str) -> None:
        c = self.canv
        x, y = self._xy(point)
        c.setFillColor(color)
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.3)
        c.circle(x, y, 8, stroke=1, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 7.4)
        c.drawCentredString(x, y - 2.6, text)
        self.placed.append((x - 9, y - 9, x + 9, y + 9))

    def _north_and_scale(self) -> None:
        c = self.canv
        cad_layer(c, "G-ANNO-NPLT")
        x0, top = self.left + 8, self.side - 8
        c.setFillColor(colors.white)
        c.setStrokeColor(INK)
        c.setLineWidth(0.4)
        c.roundRect(x0, top - 38, 24, 38, 2, stroke=1, fill=1)
        c.setFillColor(INK)
        path = c.beginPath()
        path.moveTo(x0 + 12, top - 6)
        path.lineTo(x0 + 17, top - 26)
        path.lineTo(x0 + 12, top - 21)
        path.lineTo(x0 + 7, top - 26)
        path.close()
        c.drawPath(path, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(x0 + 12, top - 35, "N")

        scale = self.ft_per_in
        bar_ft = scale
        bar_pt = inch
        bx, by = self.left + 8, 8
        label = scale_text(scale)
        c.setFillColor(colors.white)
        c.roundRect(bx, by, bar_pt + max(88, 20 + stringWidth(label, "Helvetica-Bold", 7.2)), 24, 2, stroke=1, fill=1)
        c.setFillColor(INK)
        c.rect(bx + 7, by + 7, bar_pt / 2, 4, stroke=0, fill=1)
        c.rect(bx + 7 + bar_pt / 2, by + 7, bar_pt / 2, 4, stroke=1, fill=0)
        c.setFont("Helvetica", 6.8)
        c.drawString(bx + 7, by + 14, "0")
        c.drawRightString(bx + 7 + bar_pt, by + 14, f"{bar_ft} ft")
        c.setFont("Helvetica-Bold", 7.2)
        c.drawString(bx + bar_pt + 13, by + 9, label)

    def draw(self) -> None:
        c = self.canv
        plan = self.plan
        cad_site(c, self.left, self.side, self.ft_per_in)
        c.saveState()
        clip = c.beginPath()
        clip.rect(self.left, 0, self.side, self.side)
        c.clipPath(clip, stroke=0, fill=0)
        if plan.aerial_jpeg:
            c.drawImage(ImageReader(BytesIO(plan.aerial_jpeg)), self.left, 0, self.side, self.side)
        else:
            c.setFillColor(PAPER)
            c.rect(self.left, 0, self.side, self.side, stroke=0, fill=1)

        # The photo already shows the buildings, and outline data can sit a few feet off.
        cad_layer(c, "A-BLDG-OTLN")
        if not plan.aerial_jpeg:
            for index, building in enumerate(plan.buildings):
                c.setStrokeColor(INK)
                c.setLineWidth(1.6 if index == plan.primary_building else 0.7)
                self._polyline(building, close=True)
        elif self.outline_over_aerial and plan.primary_building is not None and plan.buildings:
            # Where outlines were measured to sit on the parcels, the house is outlined over the photo.
            house = plan.buildings[plan.primary_building]
            c.setStrokeColor(INK)
            c.setLineWidth(3.0)
            self._polyline(house, close=True)
            c.setStrokeColor(colors.white)
            c.setLineWidth(1.4)
            self._polyline(house, close=True)

        cad_layer(c, "C-PROP-LINE")
        if plan.lot:
            c.setStrokeColor(INK)
            c.setLineWidth(2.6)
            self._polyline(plan.lot, close=True)
            c.setStrokeColor(LOT)
            c.setLineWidth(1.4)
            c.setDash(7, 4)
            self._polyline(plan.lot, close=True)
            c.setDash()

        points = plan.route_points
        cad_layer(c, "E-POWR-WIRE")
        if points:
            c.setStrokeColor(colors.white)
            c.setLineWidth(4.6)
            c.setLineCap(1)
            self._polyline(points)
            c.setStrokeColor(COPPER)
            c.setLineWidth(2.6)
            if self.underground:
                c.setDash(8, 4)
            self._polyline(points)
            c.setDash()

        cad_layer(c, "E-ANNO-SYMB")
        for marker in self.markers:
            self._marker(marker.point, marker.color, marker.letter)

        self._north_and_scale()
        cad_layer(c, None)

        if len(points) > 1:
            a, b = max(zip(points, points[1:]), key=lambda pair: math.dist(*pair))
            mx, my = self._xy(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
            self._label(mx, my, f"{plan.measured_route_ft} ft route", bold=True)

        edges = sorted(
            (edge for edge in plan.lot_edges if edge.length_ft >= MIN_LOT_LABEL_FT),
            key=lambda edge: -edge.length_ft,
        )
        for edge in edges[:MAX_LOT_LABELS]:
            for share in LABEL_POSITIONS:
                x, y = self._xy((
                    edge.start[0] + (edge.end[0] - edge.start[0]) * share,
                    edge.start[1] + (edge.end[1] - edge.start[1]) * share,
                ))
                if self._label(x, y, f"{edge.length_ft} ft"):
                    break
        c.restoreState()
        cad_layer(c, "G-ANNO-BORD")
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.rect(self.left, 0, self.side, self.side, stroke=1, fill=0)
        cad_site_end(c)


def site_plan_page(
    *, address: str, plan: PropertyPlan, markers: list[PlanMarker], underground: bool,
    legend: list[str], measures: list[str], outline_over_aerial: bool = False,
) -> list:
    """The whole site plan sheet. On letter the plan sits over its legend; on tabloid it sits
    beside it, printed as large as the sheet allows with its scale stated for that size."""
    from permit_packets.core.pdf_base import CREDIT, H1, SMALL, _p, _table

    sheet = current_sheet()
    side, ft_per_in = plan_print(plan, sheet)
    printed_on = " on the 22 x 34 in sheet" if print_magnification(sheet) != 1 else ""
    measures = [*measures, f"Scale {scale_text(ft_per_in)}{printed_on} when printed at 100%",
                "Not a survey. Field verify all dimensions."]
    credit = _p(". ".join(credit.rstrip(".") for credit in plan.credits) + ".", CREDIT)
    outlined = outline_over_aerial and plan.aerial_jpeg and plan.primary_building is not None and plan.buildings
    if outlined:
        legend = [*legend, "White outline: house footprint"]
    drawing = AerialSitePlan(plan, markers=markers, underground=underground,
                             width=side if sheet.landscape else sheet.content_w, side=side, ft_per_in=ft_per_in,
                             outline_over_aerial=bool(outlined))
    head = [_p("Site Plan", H1), _p(address + (f". Parcel {plan.parcel_number}." if plan.parcel_number else "."), SMALL),
            Spacer(1, 6)]
    if not sheet.landscape:
        return head + [
            drawing, Spacer(1, 6),
            _table([[_p("\n".join(legend)), _p("\n".join(measures))]],
                   [sheet.content_w / 2, sheet.content_w / 2], head=False),
            Spacer(1, 3), credit,
        ]
    gap = 18
    side_w = sheet.content_w - side - gap
    panel = [_p("Legend", SMALL), _p("\n".join(legend)), Spacer(1, 12), _p("Measurements", SMALL),
             _p("\n".join(measures)), Spacer(1, 12), credit]
    return head + [Table(
        [[drawing, panel]], colWidths=[side + gap, side_w],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                          ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]),
    )]
