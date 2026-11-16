"""Commercial feeder sizing and service load for 3-phase and single-phase systems.

Residential feeders (conductors.py) are 120/240 V single-phase and may use the 83% dwelling rule of
NEC 310.12. Neither applies to a commercial building, so commercial packets size here:

* the feeder conductor is the smallest at the 75 C column that carries the feeder breaker (NEC 215.2,
  215.3, 240.4, 110.14(C)), then steps up until voltage drop is within 3%;
* voltage drop is sqrt(3) x K x I x L / CM on a 3-phase system and 2 x K x I x L / CM on a single-phase one;
* the neutral is carried at full size and the equipment grounding conductor follows NEC Table 250.122;
* the service load is the existing demand (measured, NEC 220.87, or the electrician's own Article 220
  calculation) plus the new load, with continuous loads at 125% (NEC 215.2, 230.42).

Copper and aluminum THWN-2 up to 500 kcmil, one conductor per phase. Results are drafts for a licensed
electrician's review.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from permit_packets.core.conductors import (
    ALUMINUM_75C,
    COPPER_75C,
    EGC_TABLE,
    SERVICE_CONDUIT_FILL_SQ_IN,
    Conductor,
    Material,
    _ground_properties,
    _order,
)

SQRT3 = math.sqrt(3)
COPPER_K = 12.9
ALUMINUM_K = 21.2
_K = {"copper": COPPER_K, "aluminum": ALUMINUM_K}
CONTINUOUS_FACTOR = 1.25
MAX_VOLTAGE_DROP_PERCENT = 3.0
EGC_TOLERANCE = 0.99  # published circular mils are rounded, so a ratio within 1% counts
MEASURED_DEMAND_FACTOR = 1.25  # NEC 220.87
LARGEST_SIZE = "500"


@dataclass(frozen=True)
class System:
    key: str
    label: str
    volts: int  # line to line on a 3-phase system, 240 on the 120/240 V single-phase one
    phases: int
    to_neutral: int

    @property
    def hots(self) -> int:
        return 3 if self.phases == 3 else 2

    @property
    def one_line_label(self) -> str:
        return f"{self.volts} V, {self.phases}-phase, 4-wire" if self.phases == 3 else "120/240 V, 1-phase, 3-wire"

    def amps(self, va: float) -> float:
        """Line current for a balanced load of `va` volt-amperes."""
        return va / (SQRT3 * self.volts) if self.phases == 3 else va / self.volts

    def va(self, amps: float) -> float:
        return amps * (SQRT3 * self.volts if self.phases == 3 else self.volts)


SYSTEMS: dict[str, System] = {
    "208y120": System("208y120", "208Y/120 V, 3-phase, 4-wire", 208, 3, 120),
    "480y277": System("480y277", "480Y/277 V, 3-phase, 4-wire", 480, 3, 277),
    "120_240": System("120_240", "120/240 V, single-phase, 3-wire", 240, 1, 120),
}
SystemKey = Literal["208y120", "480y277", "120_240"]

# NEC 240.6(A) standard ratings, as far as one set of conductors carries them.
STANDARD_BREAKERS = (15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 125, 150, 175, 200, 225, 250, 300, 350)

# NEC 310.16 75 C column, Chapter 9 Table 8 circular mils, Chapter 9 Table 5 THWN-2 area, for the two sizes
# conductors.py stops short of.
_LARGER = (("400", 400000, 0.5863, 335, 270), ("500", 500000, 0.7073, 380, 310))
COPPER = COPPER_75C + tuple(Conductor(size, cu, cmil, area) for size, cmil, area, cu, _ in _LARGER)
ALUMINUM = ALUMINUM_75C + tuple(Conductor(size, al, cmil, area) for size, cmil, area, _, al in _LARGER)
_TABLES = {"copper": COPPER, "aluminum": ALUMINUM}

# NEC 250.122, extended past conductors.py's 400 A row: (largest breaker, copper EGC, aluminum EGC).
EGC_ROWS = EGC_TABLE + ((500, "2", "1/0"), (600, "1", "2/0"))


def next_standard(amps: float) -> int:
    for rating in STANDARD_BREAKERS:
        if rating >= amps:
            return rating
    raise ValueError(f"no standard breaker covers {amps:g} A on one set of conductors")


def voltage_drop(amps: float, one_way_ft: float, conductor: Conductor, material: Material,
                 system: System) -> tuple[float, float]:
    """Volts dropped and that as a percent of the system voltage."""
    factor = SQRT3 if system.phases == 3 else 2
    drop = factor * _K[material] * amps * one_way_ft / conductor.circular_mils
    return drop, drop / system.volts * 100


def egc_size(breaker: int, material: Material) -> str:
    return next(row[1 if material == "copper" else 2] for row in EGC_ROWS if breaker <= row[0])


@dataclass(frozen=True)
class CommercialFeeder:
    system: System
    breaker: int
    material: Material
    conductor: Conductor
    start: Conductor  # what the breaker alone calls for, before any voltage drop upsizing
    egc: str
    vd_volts: float
    vd_percent: float

    @property
    def upsized(self) -> bool:
        return self.conductor is not self.start

    @property
    def poles(self) -> int:
        return self.system.hots


def _grown_egc(breaker: int, material: Material, start: Conductor, chosen: Conductor) -> str:
    """The EGC for the breaker, grown in proportion to the hots when they were upsized (NEC 250.122(B))."""
    base = egc_size(breaker, material)
    if chosen is start:
        return base
    required = _ground_properties(base)[0] * chosen.circular_mils / start.circular_mils * EGC_TOLERANCE
    sizes = ["14", "12", "10", *(conductor.size for conductor in COPPER)]
    for size in sizes:
        if _ground_properties(size)[0] >= required:
            # Never larger than the hots (250.122(A)).
            return size if _ground_properties(size)[0] <= chosen.circular_mils else chosen.size
    return chosen.size


def size_feeder(breaker: int, material: Material, load_amps: float, one_way_ft: float,
                system: System) -> CommercialFeeder:
    """Start at the smallest conductor the breaker allows, then step up until voltage drop is within 3%."""
    table = _TABLES[material]
    start = next((c for c in table if c.ampacity_75c >= breaker), None)
    if start is None:
        raise ValueError(f"no {material} conductor up to {LARGEST_SIZE} kcmil carries {breaker} A on one set")
    chosen = start
    for conductor in table[_order(table, start.size):_order(table, LARGEST_SIZE) + 1]:
        chosen = conductor
        if voltage_drop(load_amps, one_way_ft, conductor, material, system)[1] <= MAX_VOLTAGE_DROP_PERCENT:
            break
    volts, percent = voltage_drop(load_amps, one_way_ft, chosen, material, system)
    return CommercialFeeder(
        system=system, breaker=breaker, material=material, conductor=chosen, start=start,
        egc=_grown_egc(breaker, material, start, chosen), vd_volts=volts, vd_percent=percent,
    )


def feeder_conduit(feeder: CommercialFeeder, conduit_type: str) -> str:
    """The smallest conduit that holds the hots, the full-size neutral and the EGC at 40% fill."""
    fill = (feeder.system.hots + 1) * feeder.conductor.area_sq_in + _ground_properties(feeder.egc)[1]
    for size, capacity in SERVICE_CONDUIT_FILL_SQ_IN[conduit_type]:
        if fill <= capacity:
            return size
    raise ValueError(f"{fill:.3f} sq in is too much wire for {conduit_type} up to "
                     f"{SERVICE_CONDUIT_FILL_SQ_IN[conduit_type][-1][0]}")


# Service load.

DEMAND_BASES = {
    "utility_12_month": "Utility maximum demand, 12 months (220.87)",
    "recorded_30_day": "Recorded maximum demand, 30 days at 15-minute average (220.87)",
    "calculated": "Existing load calculated by the electrician (Article 220)",
}
DemandBasis = Literal["utility_12_month", "recorded_30_day", "calculated"]


@dataclass(frozen=True)
class LoadLine:
    label: str
    basis: str
    va: float


@dataclass(frozen=True)
class ServiceLoad:
    system: System
    service_amps: int
    existing_kva: float
    existing_basis: DemandBasis
    lines: tuple[LoadLine, ...]  # the new load, after the continuous factor

    @property
    def existing_va(self) -> float:
        factor = 1 if self.existing_basis == "calculated" else MEASURED_DEMAND_FACTOR
        return self.existing_kva * 1000 * factor

    @property
    def new_va(self) -> float:
        return sum(line.va for line in self.lines)

    @property
    def total_va(self) -> float:
        return self.existing_va + self.new_va

    @property
    def amps(self) -> float:
        return self.system.amps(self.total_va)

    @property
    def spare_amps(self) -> float:
        return self.service_amps - self.amps

    @property
    def percent_of_service(self) -> float:
        return self.amps / self.service_amps * 100

    @property
    def fits(self) -> bool:
        return self.amps <= self.service_amps


def new_load_line(label: str, va: float, *, continuous: bool, basis: str = "Nameplate") -> LoadLine:
    """A new load at 100%, or at 125% when it runs three hours or more (NEC 215.2(A)(1), 230.42(A)(1))."""
    if continuous:
        return LoadLine(label, f"{basis} x 125%, continuous", va * CONTINUOUS_FACTOR)
    return LoadLine(label, f"{basis} x 100%", va)
