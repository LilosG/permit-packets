"""The to-scale site plan page: the aerial with the job drawn on it."""
from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable

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


@dataclass(frozen=True)
class PlanMarker:
    point: Point
    color: colors.Color
    letter: str


class AerialSitePlan(Flowable):
    """The plan's route is drawn between its route markers; `markers` are the dots on it."""

    def __init__(
        self, plan: PropertyPlan, *, markers: list[PlanMarker], underground: bool, width: float,
    ) -> None:
        super().__init__()
        self.plan = plan
        self.markers = markers
        self.underground = underground
        self.width = width
        self.height = PLAN_PT
        self.left = (width - PLAN_PT) / 2
        self.placed: list[tuple[float, float, float, float]] = []

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def _xy(self, point: Point) -> tuple[float, float]:
        k = PLAN_PT / PLAN_UNITS
        return self.left + point[0] * k, PLAN_PT - point[1] * k

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
        x0, top = self.left + 8, PLAN_PT - 8
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

        scale = self.plan.scale_ft_per_in
        bar_ft = scale
        bar_pt = inch
        bx, by = self.left + 8, 8
        c.setFillColor(colors.white)
        c.roundRect(bx, by, bar_pt + 88, 24, 2, stroke=1, fill=1)
        c.setFillColor(INK)
        c.rect(bx + 7, by + 7, bar_pt / 2, 4, stroke=0, fill=1)
        c.rect(bx + 7 + bar_pt / 2, by + 7, bar_pt / 2, 4, stroke=1, fill=0)
        c.setFont("Helvetica", 6.8)
        c.drawString(bx + 7, by + 14, "0")
        c.drawRightString(bx + 7 + bar_pt, by + 14, f"{bar_ft} ft")
        c.setFont("Helvetica-Bold", 7.2)
        c.drawString(bx + bar_pt + 13, by + 9, f'1 in = {scale} ft')

    def draw(self) -> None:
        c = self.canv
        plan = self.plan
        c.saveState()
        clip = c.beginPath()
        clip.rect(self.left, 0, PLAN_PT, PLAN_PT)
        c.clipPath(clip, stroke=0, fill=0)
        if plan.aerial_jpeg:
            c.drawImage(ImageReader(BytesIO(plan.aerial_jpeg)), self.left, 0, PLAN_PT, PLAN_PT)
        else:
            c.setFillColor(PAPER)
            c.rect(self.left, 0, PLAN_PT, PLAN_PT, stroke=0, fill=1)

        # The photo already shows the buildings, and outline data can sit a few feet off.
        if not plan.aerial_jpeg:
            for index, building in enumerate(plan.buildings):
                c.setStrokeColor(INK)
                c.setLineWidth(1.6 if index == plan.primary_building else 0.7)
                self._polyline(building, close=True)

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

        for marker in self.markers:
            self._marker(marker.point, marker.color, marker.letter)

        self._north_and_scale()

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
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.rect(self.left, 0, PLAN_PT, PLAN_PT, stroke=1, fill=0)
