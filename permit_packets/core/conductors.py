"""Service entrance conductors, grounding electrode conductors and service conduit.

Copper and aluminum THWN-2 at the 75 C column, 120/240 V single-phase dwelling
service. Results are drafts for a licensed electrician's review.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Material = Literal["copper", "aluminum"]
Electrode = Literal["rods", "concrete_encased", "water_pipe"]

# NEC 310.12: a dwelling service conductor may be sized at 83% of the service rating.
SERVICE_CONDUCTOR_FACTOR = 0.83
# NEC 705.12(B)(3)(2): the main plus the PV breaker may total 120% of the bus.
BUS_BACKFEED_FACTOR = 1.2
SERVICE_CONDUCTORS_IN_CONDUIT = 3  # two hots and a full-size neutral


@dataclass(frozen=True)
class Conductor:
    size: str
    ampacity_75c: int
    circular_mils: int
    area_sq_in: float


# Ampacity differs by material. Area and circular mils are the same for both.
# (size, copper A, aluminum A, circular mils, THWN-2 area in sq in)
_SIZES = (
    ("8", 50, 40, 16510, 0.0366),
    ("6", 65, 50, 26240, 0.0507),
    ("4", 85, 65, 41740, 0.0824),
    ("3", 100, 75, 52620, 0.0973),
    ("2", 115, 90, 66360, 0.1158),
    ("1", 130, 100, 83690, 0.1562),
    ("1/0", 150, 120, 105600, 0.1855),
    ("2/0", 175, 135, 133100, 0.2223),
    ("3/0", 200, 155, 167800, 0.2679),
    ("4/0", 230, 180, 211600, 0.3237),
    ("250", 255, 205, 250000, 0.3970),
    ("300", 285, 230, 300000, 0.4608),
    ("350", 310, 250, 350000, 0.5242),
)

# NEC 310.16 75 C column, Chapter 9 Table 8 circular mils, Chapter 9 Table 5 THWN-2 area.
COPPER_75C = tuple(Conductor(size, cu, cmil, area) for size, cu, _, cmil, area in _SIZES)
ALUMINUM_75C = tuple(Conductor(size, al, cmil, area) for size, _, al, cmil, area in _SIZES)
_TABLES = {"copper": COPPER_75C, "aluminum": ALUMINUM_75C}

# NEC Chapter 9 Table 4, 40% fill for three or more conductors.
SERVICE_CONDUIT_FILL_SQ_IN = {
    "PVC": (('3/4"', 0.203), ('1"', 0.333), ('1-1/4"', 0.581), ('1-1/2"', 0.794),
            ('2"', 1.316), ('2-1/2"', 1.878), ('3"', 2.907)),
    "EMT": (('3/4"', 0.213), ('1"', 0.346), ('1-1/4"', 0.598), ('1-1/2"', 0.814),
            ('2"', 1.342), ('2-1/2"', 2.343), ('3"', 3.538)),
}

# NEC 250.66 Table: the grounding electrode conductor (copper) by service conductor size.
# Each row is (largest service conductor size it covers, GEC size).
_GEC_COPPER_SERVICE = (("2", "8"), ("1/0", "6"), ("3/0", "4"), ("350", "2"))
_GEC_ALUMINUM_SERVICE = (("1/0", "8"), ("3/0", "6"), ("250", "4"), ("350", "2"))
# NEC 250.66(A) and (B): the most a rod or a concrete-encased electrode needs.
_ELECTRODE_LIMIT = {"rods": "6", "concrete_encased": "4"}
_GEC_ORDER = ("2", "4", "6", "8")  # largest first


def _order(table: tuple[Conductor, ...], size: str) -> int:
    return next(index for index, conductor in enumerate(table) if conductor.size == size)


def wire_label(size: str) -> str:
    """How a size reads on a plan: #4, #2/0, but 250 kcmil."""
    return f"{size} kcmil" if int(size.split("/")[0]) >= 250 else f"#{size}"


def service_conductor(service_amps: int, material: Material) -> Conductor:
    """The smallest conductor rated for 83% of the service (NEC 310.12)."""
    required = SERVICE_CONDUCTOR_FACTOR * service_amps
    table = _TABLES[material]
    for conductor in table:
        if conductor.ampacity_75c >= required:
            return conductor
    raise ValueError(f"no listed conductor carries {required:g} A in {material}")


def gec_size(conductor: Conductor, material: Material, electrode: Electrode) -> str:
    """The copper grounding electrode conductor, by service conductor and electrode (NEC 250.66)."""
    table = _TABLES[material]
    rows = _GEC_COPPER_SERVICE if material == "copper" else _GEC_ALUMINUM_SERVICE
    position = _order(table, conductor.size)
    size = next((gec for largest, gec in rows if position <= _order(table, largest)), None)
    if size is None:
        raise ValueError(f"no grounding electrode conductor listed for {conductor.size} {material}")
    limit = _ELECTRODE_LIMIT.get(electrode)
    # A bigger number is a smaller wire, so the smaller wire is the later one in the order.
    if limit is not None and _GEC_ORDER.index(limit) > _GEC_ORDER.index(size):
        return limit
    return size


def service_conduit(conductor: Conductor, conduit_type: str) -> str:
    """The smallest conduit that holds two hots and a full-size neutral at 40% fill."""
    fill = SERVICE_CONDUCTORS_IN_CONDUIT * conductor.area_sq_in
    sizes = SERVICE_CONDUIT_FILL_SQ_IN[conduit_type]
    for size, capacity in sizes:
        if fill <= capacity:
            return size
    raise ValueError(f"{fill:.3f} sq in is too much wire for {conduit_type} up to {sizes[-1][0]}")


def solar_fits(bus_amps: int, main_amps: int, pv_breaker_amps: int) -> bool:
    """NEC 705.12(B)(3)(2): main plus PV breaker within 120% of the bus, PV breaker at the far end."""
    return main_amps + pv_breaker_amps <= BUS_BACKFEED_FACTOR * bus_amps


# Feeders to a subpanel, 120/240 V single-phase.

# NEC 250.122: the equipment grounding conductor by the largest breaker it covers.
# Each row is (largest breaker, copper size, aluminum size).
EGC_TABLE = (
    (15, "14", "12"), (20, "12", "10"), (60, "10", "8"), (100, "8", "6"),
    (200, "6", "4"), (300, "4", "2"), (400, "3", "1"),
)
# Chapter 9 Table 5 THWN-2 areas for the small grounds _SIZES doesn't list. Conduit fill only.
SMALL_GROUND_AREA_SQ_IN = {"14": 0.0097, "12": 0.0133, "10": 0.0211}
_SMALL_GROUND_CIRCULAR_MILS = {"14": 4110, "12": 6530, "10": 10380}
# Resistance constants for the voltage drop formula.
ALUMINUM_K = 21.2
COPPER_K = 12.9
_K = {"copper": COPPER_K, "aluminum": ALUMINUM_K}
FEEDER_VOLTS = 240
MAX_FEEDER_VOLTAGE_DROP_PERCENT = 3.0
LARGEST_FEEDER_SIZE = "350"
FEEDER_CONDUCTORS_IN_CONDUIT = 3  # two hots and a full-size neutral, plus the ground
EGC_TOLERANCE = 0.99  # published circular mils are rounded, so a ratio within 1% counts


@dataclass(frozen=True)
class Feeder:
    conductor: Conductor
    egc: str
    upsized: bool
    vd_volts: float
    vd_percent: float


def _ground_properties(size: str) -> tuple[int, float]:
    """Circular mils and THWN-2 area of a ground wire, small sizes included."""
    if size in SMALL_GROUND_AREA_SQ_IN:
        return _SMALL_GROUND_CIRCULAR_MILS[size], SMALL_GROUND_AREA_SQ_IN[size]
    conductor = COPPER_75C[_order(COPPER_75C, size)]
    return conductor.circular_mils, conductor.area_sq_in


def feeder_conductor(breaker: int, material: Material, whole_dwelling: bool = False) -> Conductor:
    """The smallest conductor rated for the breaker (NEC 240.4), or 83% of it when the
    feeder carries a whole dwelling (NEC 310.12)."""
    required = breaker * (SERVICE_CONDUCTOR_FACTOR if whole_dwelling else 1)
    for conductor in _TABLES[material]:
        if conductor.ampacity_75c >= required:
            return conductor
    raise ValueError(f"no listed conductor carries {required:g} A in {material}")


def feeder_voltage_drop(
    amps: float, one_way_ft: float, conductor: Conductor, material: Material,
) -> tuple[float, float]:
    """Volts dropped and that as a percent of 240 V, for a two-wire run."""
    drop = 2 * _K[material] * amps * one_way_ft / conductor.circular_mils
    return drop, drop / FEEDER_VOLTS * 100


def _feeder_egc(breaker: int, material: Material, start: Conductor, chosen: Conductor) -> str:
    """The EGC for the breaker, grown in proportion to the hots when they were upsized (NEC 250.122(B))."""
    column = 1 if material == "copper" else 2
    base = next(row[column] for row in EGC_TABLE if breaker <= row[0])
    if chosen is start:
        return base
    required = _ground_properties(base)[0] * chosen.circular_mils / start.circular_mils * EGC_TOLERANCE
    sizes = [*SMALL_GROUND_AREA_SQ_IN, *(conductor.size for conductor in _TABLES[material])]
    for size in sizes:
        if _ground_properties(size)[0] >= required:
            # Never larger than the hots.
            return size if _ground_properties(size)[0] <= chosen.circular_mils else chosen.size
    return chosen.size


def size_feeder(
    breaker: int, material: Material, load_amps: float, one_way_ft: float, whole_dwelling: bool = False,
) -> Feeder:
    """Start at the breaker's conductor, then step up until voltage drop is within 3%, up to 350 kcmil."""
    table = _TABLES[material]
    start = feeder_conductor(breaker, material, whole_dwelling)
    last = _order(table, LARGEST_FEEDER_SIZE)
    chosen = start
    for conductor in table[_order(table, start.size):last + 1]:
        chosen = conductor
        if feeder_voltage_drop(load_amps, one_way_ft, conductor, material)[1] <= MAX_FEEDER_VOLTAGE_DROP_PERCENT:
            break
    volts, percent = feeder_voltage_drop(load_amps, one_way_ft, chosen, material)
    return Feeder(
        conductor=chosen, egc=_feeder_egc(breaker, material, start, chosen),
        upsized=chosen is not start, vd_volts=volts, vd_percent=percent,
    )


def feeder_conduit(feeder: Feeder, conduit_type: str) -> str:
    """The smallest conduit that holds two hots, a neutral and the EGC at 40% fill."""
    fill = FEEDER_CONDUCTORS_IN_CONDUIT * feeder.conductor.area_sq_in + _ground_properties(feeder.egc)[1]
    sizes = SERVICE_CONDUIT_FILL_SQ_IN[conduit_type]
    for size, capacity in sizes:
        if fill <= capacity:
            return size
    raise ValueError(f"{fill:.3f} sq in is too much wire for {conduit_type} up to {sizes[-1][0]}")


# Branch circuits to a 240 V appliance: copper THWN-2 at the 60 C or 75 C column.

@dataclass(frozen=True)
class BranchConductor:
    size: str
    ampacity_60c: int
    ampacity_75c: int
    circular_mils: int
    area_sq_in: float

    def ampacity(self, terminals_75c: bool) -> int:
        return self.ampacity_75c if terminals_75c else self.ampacity_60c


# NEC 310.16 copper, Chapter 9 Table 8 circular mils, Chapter 9 Table 5 THWN-2 area.
# (size, 60 C A, 75 C A, circular mils, area in sq in)
BRANCH_COPPER = tuple(BranchConductor(*row) for row in (
    ("14", 15, 20, 4110, 0.0097),
    ("12", 20, 25, 6530, 0.0133),
    ("10", 30, 35, 10380, 0.0211),
    ("8", 40, 50, 16510, 0.0366),
    ("6", 55, 65, 26240, 0.0507),
    ("4", 70, 85, 41740, 0.0824),
    ("3", 85, 100, 52620, 0.0973),
    ("2", 95, 115, 66360, 0.1158),
    ("1", 110, 130, 83690, 0.1562),
))
# NEC 240.4(D): the largest breaker allowed on small copper conductors.
SMALL_CONDUCTOR_LIMIT = {"14": 15, "12": 20, "10": 30}
STANDARD_BREAKERS = (15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 125)
LARGEST_BRANCH_SIZE = "1"


@dataclass(frozen=True)
class Branch:
    wire: BranchConductor
    egc: str
    upsized: bool
    vd_volts: float
    vd_percent: float


def _branch_start(
    breaker: int, terminals_75c: bool, hvac_mca: float | None,
) -> BranchConductor:
    """The smallest wire for the circuit before voltage drop. A non-HVAC wire must carry the
    breaker and be allowed on it (NEC 240.4(D)); an HVAC wire carries the MCA (240.4(G), 440)."""
    for wire in BRANCH_COPPER:
        if hvac_mca is not None:
            if wire.ampacity(terminals_75c) >= hvac_mca:
                return wire
        elif wire.ampacity(terminals_75c) >= breaker and breaker <= SMALL_CONDUCTOR_LIMIT.get(wire.size, breaker):
            return wire
    column = 75 if terminals_75c else 60
    raise ValueError(f"no copper size up to #1 carries a {breaker} A circuit at the {column}\N{DEGREE SIGN}C column")


def _branch_egc(breaker: int, start: BranchConductor, chosen: BranchConductor) -> str:
    """The EGC for the breaker (NEC 250.122), grown with the hots when they were upsized (250.122(B))
    and never larger than the hots (250.122(A))."""
    base = next(row[1] for row in EGC_TABLE if breaker <= row[0])
    required = _ground_properties(base)[0] * chosen.circular_mils / start.circular_mils * EGC_TOLERANCE
    sizes = [*SMALL_GROUND_AREA_SQ_IN, *(conductor.size for conductor in COPPER_75C)]
    for size in sizes:
        if _ground_properties(size)[0] >= required:
            return size if _ground_properties(size)[0] <= chosen.circular_mils else chosen.size
    return chosen.size


def size_branch(
    *, breaker: int, load_amps: float, run_ft: float, terminals_75c: bool, hvac_mca: float | None = None,
) -> Branch:
    """Start at the smallest wire the breaker (or HVAC MCA) allows, then step up until voltage
    drop at the load is within 3%, up to #1."""
    start = _branch_start(breaker, terminals_75c, hvac_mca)
    chosen = start
    for wire in BRANCH_COPPER[BRANCH_COPPER.index(start):]:
        chosen = wire
        drop = 2 * COPPER_K * load_amps * run_ft / wire.circular_mils
        if drop / FEEDER_VOLTS * 100 <= MAX_FEEDER_VOLTAGE_DROP_PERCENT or wire.size == LARGEST_BRANCH_SIZE:
            break
    drop = 2 * COPPER_K * load_amps * run_ft / chosen.circular_mils
    return Branch(
        wire=chosen, egc=_branch_egc(breaker, start, chosen), upsized=chosen is not start,
        vd_volts=drop, vd_percent=drop / FEEDER_VOLTS * 100,
    )


def branch_conduit(branch: Branch, hots_and_neutral: int, conduit_type: str) -> str:
    """The smallest conduit that holds the hots, any neutral and the EGC at 40% fill."""
    fill = hots_and_neutral * branch.wire.area_sq_in + _ground_properties(branch.egc)[1]
    sizes = SERVICE_CONDUIT_FILL_SQ_IN[conduit_type]
    for size, capacity in sizes:
        if fill <= capacity:
            return size
    raise ValueError(f"{fill:.3f} sq in is too much wire for {conduit_type} up to {sizes[-1][0]}")
