"""A property on a to-scale plan, in plan units of 0 to 1000 with north up."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

PLAN_UNITS = 1000
EARTH_RADIUS_M = 6378137
FEET_PER_METER = 3.28084
# Printed width of the plan. Scales are the engineer's scales a plan checker expects.
PLAN_WIDTH_IN = 7.0
ENGINEER_SCALES_FT_PER_IN = (20, 30, 40, 50, 60, 80, 100)

Point = tuple[float, float]


def plan_scale(extent_ft: float) -> int:
    return next(
        (scale for scale in ENGINEER_SCALES_FT_PER_IN if scale * PLAN_WIDTH_IN >= extent_ft * 1.15),
        ENGINEER_SCALES_FT_PER_IN[-1],
    )


@dataclass(frozen=True)
class PlanView:
    latitude: float
    longitude: float
    scale_ft_per_in: int

    @property
    def size_ft(self) -> float:
        return self.scale_ft_per_in * PLAN_WIDTH_IN

    @property
    def feet_per_unit(self) -> float:
        return self.size_ft / PLAN_UNITS

    @property
    def half_size_mercator(self) -> float:
        return self.size_ft / FEET_PER_METER / 2 / math.cos(math.radians(self.latitude))

    def mercator_center(self) -> Point:
        return mercator(self.latitude, self.longitude)

    def bbox(self) -> tuple[float, float, float, float]:
        x, y = self.mercator_center()
        half = self.half_size_mercator
        return x - half, y - half, x + half, y + half

    def to_plan(self, latitude: float, longitude: float) -> Point:
        x, y = mercator(latitude, longitude)
        center_x, center_y = self.mercator_center()
        per_unit = 2 * self.half_size_mercator / PLAN_UNITS
        return (
            round(PLAN_UNITS / 2 + (x - center_x) / per_unit, 1),
            round(PLAN_UNITS / 2 - (y - center_y) / per_unit, 1),
        )


def mercator(latitude: float, longitude: float) -> Point:
    return (
        EARTH_RADIUS_M * math.radians(longitude),
        EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2)),
    )


def ground_distance_ft(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Feet between two (latitude, longitude) points on a lot-sized scale."""
    mid = math.radians((a[0] + b[0]) / 2)
    north = math.radians(b[0] - a[0]) * EARTH_RADIUS_M
    east = math.radians(b[1] - a[1]) * EARTH_RADIUS_M * math.cos(mid)
    return math.hypot(north, east) * FEET_PER_METER


def path_length(points: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def distance_to_segment(point: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    span = dx * dx + dy * dy
    t = 0.0 if span == 0 else max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / span))
    return math.dist(point, (a[0] + t * dx, a[1] + t * dy))


def simplify(points: list[Point], tolerance: float) -> list[Point]:
    """Douglas-Peucker, so a lot edge with extra survey points reads as one edge."""
    if len(points) < 3:
        return points
    index, far = max(
        ((i, distance_to_segment(points[i], points[0], points[-1])) for i in range(1, len(points) - 1)),
        key=lambda item: item[1],
    )
    if far <= tolerance:
        return [points[0], points[-1]]
    return simplify(points[: index + 1], tolerance)[:-1] + simplify(points[index:], tolerance)


def centroid(polygon: list[Point]) -> Point:
    return (sum(p[0] for p in polygon) / len(polygon), sum(p[1] for p in polygon) / len(polygon))


@dataclass(frozen=True)
class Edge:
    start: Point
    end: Point
    length_ft: int


@dataclass(frozen=True)
class PropertyPlan:
    scale_ft_per_in: int
    panel: Point
    charger: Point
    route: list[Point]
    buildings: list[list[Point]] = field(default_factory=list)
    primary_building: int | None = None
    lot: list[Point] = field(default_factory=list)
    parcel_number: str = ""
    aerial_jpeg: bytes | None = None
    credits: list[str] = field(default_factory=list)

    @property
    def feet_per_unit(self) -> float:
        return self.scale_ft_per_in * PLAN_WIDTH_IN / PLAN_UNITS

    @property
    def route_points(self) -> list[Point]:
        return [self.panel, *self.route, self.charger]

    @property
    def measured_route_ft(self) -> int:
        return round(path_length(self.route_points) * self.feet_per_unit)

    @property
    def lot_edges(self) -> list[Edge]:
        if len(self.lot) < 3:
            return []
        ring = simplify(self.lot + [self.lot[0]], 1.5 / self.feet_per_unit)
        return [
            Edge(a, b, round(math.dist(a, b) * self.feet_per_unit))
            for a, b in zip(ring, ring[1:])
        ]

    @property
    def charger_to_lot_line_ft(self) -> int | None:
        if len(self.lot) < 3:
            return None
        ring = self.lot + [self.lot[0]]
        nearest = min(distance_to_segment(self.charger, a, b) for a, b in zip(ring, ring[1:]))
        return round(nearest * self.feet_per_unit)
