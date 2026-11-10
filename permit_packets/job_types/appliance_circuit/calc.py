"""Residential 240 V appliance circuit permit (hot tub, sauna, heat pump, mini-split, other):
the job, the checks and the flags."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from permit_packets.core.checks import Check
from permit_packets.core.circuits import CONTINUOUS_FACTOR
from permit_packets.core.conductors import (
    FEEDER_VOLTS,
    MAX_FEEDER_VOLTAGE_DROP_PERCENT,
    STANDARD_BREAKERS,
    Branch,
    branch_conduit,
    size_branch,
    wire_label,
)
from permit_packets.core.job_inputs import display_number
from permit_packets.core.load_calculation import (
    HomeLoads,
    LoadCalculation,
    LoadLine,
    calculate_load,
)
from permit_packets.core.property_plan import PropertyPlan
from permit_packets.jurisdictions import ORO_VALLEY, Jurisdiction

Appliance = Literal["hot_tub", "sauna", "heat_pump", "mini_split", "other"]
Location = Literal["indoor", "outdoor", "detached"]
Wiring = Literal["PVC", "EMT", "cable"]
Gfci = Literal["breaker", "spa_pack", "none"]
APPLIANCE_LABELS = {
    "hot_tub": "hot tub", "sauna": "sauna", "heat_pump": "heat pump",
    "mini_split": "mini-split", "other": "240 V appliance",
}
APPLIANCE_TITLES = {
    "hot_tub": "Hot Tub", "sauna": "Sauna", "heat_pump": "Heat Pump",
    "mini_split": "Mini-Split", "other": "240 V Appliance",
}
LOCATION_LABELS = {"indoor": "indoor", "outdoor": "outdoor", "detached": "detached building"}
HVAC = ("heat_pump", "mini_split")
DEGREE = "\N{DEGREE SIGN}"
SPACES_NEEDED = 2
BURIAL_COVER_IN = 18  # NEC 300.5 Table 300.5, PVC in a trench
MIN_DISCONNECT_DISTANCE_FT = 5  # NEC 680.13


@dataclass(frozen=True)
class ApplianceJob:
    customer: str
    address: str
    contractor: str
    license_number: str
    home: HomeLoads
    service_amps: int
    open_breaker_spaces: int
    appliance: Appliance
    location: Location
    wiring: Wiring
    run_ft: int
    trench_ft: int
    needs_neutral: bool
    appliance_model: str = ""
    nameplate_amps: float | None = None
    heater_kw: float | None = None
    mca: float | None = None
    mocp: int | None = None
    manufacturer_breaker: int | None = None
    continuous: bool = False
    terminals_75c: bool = False
    gfci: Gfci | None = None
    disconnect_distance_ft: int | None = None
    jurisdiction: Jurisdiction = ORO_VALLEY
    plan: PropertyPlan | None = None

    @property
    def is_hvac(self) -> bool:
        return self.appliance in HVAC

    @property
    def is_continuous(self) -> bool:
        """A hot tub and a sauna heater run for three hours or more (424.4(B)); other loads say so."""
        return self.appliance in ("hot_tub", "sauna") or (self.appliance == "other" and self.continuous)

    @property
    def has_disconnect(self) -> bool:
        return self.appliance == "hot_tub" or self.is_hvac

    @property
    def load_amps(self) -> float:
        if self.appliance == "sauna":
            return self.heater_kw * 1000 / FEEDER_VOLTS
        if self.is_hvac:
            return self.mca
        return self.nameplate_amps

    @property
    def conductors_in_conduit(self) -> int:
        """Two hots, plus a neutral when the appliance has a 120 V part."""
        return 3 if self.needs_neutral else 2


@dataclass(frozen=True)
class AppliancePacket:
    job: ApplianceJob
    load: LoadCalculation  # the house, with the appliance added
    load_amps: float
    minimum_breaker: int  # non-HVAC: the smallest standard breaker for the load. HVAC: the MCA's smallest
    breaker: int
    branch: Branch
    conduit_size: str | None  # None for cable
    checks: list[Check]
    flags: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)


def _smallest_breaker(amps: float) -> int:
    for breaker in STANDARD_BREAKERS:
        if breaker >= amps:
            return breaker
    raise ValueError(f"no standard breaker covers {amps:g} A")


def _largest_breaker_within(limit: int) -> int:
    return max(breaker for breaker in STANDARD_BREAKERS if breaker <= limit)


def sentence_case(text: str) -> str:
    """The first letter up, the rest as written: "240 V appliance" stays as it is."""
    return text[0].upper() + text[1:]


def display_amps(value: float) -> str:
    return display_number(round(value, 1))


def _flags(job: ApplianceJob, load: LoadCalculation, branch: Branch) -> list[str]:
    flags = ["Check the existing loads against the home. They drive the service result."]
    if load.computed_amps > job.service_amps:
        flags.append(
            f"The service is over capacity by {-load.spare_amps:.1f} A. Options are load management, "
            "a service upgrade, or 12 months of utility demand data (220.87)."
        )
    if branch.upsized:
        flags.append(
            f"Circuit upsized to {wire_label(branch.wire.size)} for voltage drop, "
            f"so the EGC is {wire_label(branch.egc)} to match (250.122(B))."
        )
    if branch.vd_percent > MAX_FEEDER_VOLTAGE_DROP_PERCENT:
        flags.append(
            f"Voltage drop is {branch.vd_percent:.1f}% even at the largest size. "
            "Shorten the run or redesign the circuit."
        )
    if job.trench_ft:
        flags.append(f"Call 811 before trenching. Confirm {BURIAL_COVER_IN} in of cover for PVC (300.5).")
    column = 75 if job.terminals_75c else 60
    flags.append(
        f"Wire sized at the {column}{DEGREE}C column. Confirm the equipment's terminal rating (110.14(C))."
    )
    if job.appliance == "hot_tub":
        flags += [
            "Bond the spa's metal parts and equipment per the manufacturer and 680.42/680.26.",
            "Keep receptacles at least 6 ft from the spa, and GFCI-protect any within 20 ft (680.43).",
            "Check overhead line clearances above the spa (680.9).",
            "The disconnect must be within sight of the spa.",
        ]
    elif job.appliance == "sauna":
        flags += [
            "Follow the heater's instructions for wiring, including high-temperature wire inside the room.",
            "No receptacles inside the sauna room. Mount the control and contactor where the heater's "
            "instructions say.",
            "Some heater makers prohibit GFCI on the heater circuit. Follow the instructions.",
        ]
        if job.location != "indoor":
            flags.append("An outdoor or freestanding sauna can also need a building permit for the structure.")
    elif job.is_hvac:
        flags += [
            "Put a disconnect within sight of the outdoor unit (440.14).",
            "Add a 120 V service receptacle within 25 ft of the unit (210.63).",
            "Outdoor HVAC outlets may need GFCI protection (210.8(F)). Confirm the code edition the city enforces.",
        ]
    else:
        flags.append("Size the circuit from the appliance's nameplate and instructions.")
    if job.jurisdiction.state == "CA":
        flags.append("California: permit work over $1,000 can trigger smoke and CO alarm requirements. Confirm with the city.")
    if job.plan is None:
        flags.append("This site plan is a schematic. Replace it with the property's plan before submitting.")
    if job.jurisdiction.needs_parcel_number and not (job.plan and job.plan.parcel_number):
        flags.append("This city needs the parcel number on the application.")
    active = {"always"} | ({"trench"} if job.trench_ft else set())
    checklist = job.jurisdiction.checklist_for("appliance_circuit")
    flags += [note.text for note in checklist.notes if note.when in active]
    flags.append(checklist.code_note)
    return flags


def build_appliance_packet(job: ApplianceJob) -> AppliancePacket:
    load_amps = job.load_amps
    label = sentence_case(APPLIANCE_LABELS[job.appliance])
    load = calculate_load(
        job.home,
        service_amps=job.service_amps,
        added_loads=[LoadLine(label, f"{display_amps(load_amps)} A x {FEEDER_VOLTS} V, 100%", round(load_amps * FEEDER_VOLTS))],
        volts=FEEDER_VOLTS,
    )
    if job.is_hvac:
        minimum = _smallest_breaker(job.mca)
        breaker = _largest_breaker_within(job.mocp)
    else:
        minimum = _smallest_breaker(load_amps * (CONTINUOUS_FACTOR if job.is_continuous else 1))
        breaker = job.manufacturer_breaker or minimum
    branch = size_branch(
        breaker=breaker, load_amps=load_amps, run_ft=job.run_ft, terminals_75c=job.terminals_75c,
        hvac_mca=job.mca if job.is_hvac else None,
    )
    conduit_size = (
        None if job.wiring == "cable" else branch_conduit(branch, job.conductors_in_conduit, job.wiring)
    )
    if job.is_hvac:
        breaker_check = Check(
            "Breaker", f"{breaker} A, nameplate max {job.mocp} A (440.22)",
            job.mca <= breaker <= job.mocp)
    else:
        kind = "continuous" if job.is_continuous else "non-continuous"
        breaker_check = Check(
            "Breaker", f"{breaker} A for a {display_amps(load_amps)} A {kind} load", breaker >= minimum)
    checks = [
        Check("Service capacity",
              f"{load.computed_amps:.1f} A computed on the {job.service_amps} A service",
              load.computed_amps <= job.service_amps),
        Check("Panel spaces", f"{job.open_breaker_spaces} open, {SPACES_NEEDED} needed",
              job.open_breaker_spaces >= SPACES_NEEDED),
        breaker_check,
        Check("Conductors",
              f"{wire_label(branch.wire.size)} Cu THWN-2, "
              f"{branch.wire.ampacity(job.terminals_75c)} A at {75 if job.terminals_75c else 60}{DEGREE}C",
              True),
        Check("Voltage drop", f"{branch.vd_volts:.1f} V, {branch.vd_percent:.1f}% over {job.run_ft} ft",
              branch.vd_percent <= MAX_FEEDER_VOLTAGE_DROP_PERCENT),
    ]
    if conduit_size:
        checks.append(Check(
            "Conduit fill", f"{job.conductors_in_conduit + 1} wires in {conduit_size} {job.wiring}, 40% fill", True))
    if job.appliance == "hot_tub":
        gfci_result = {
            "breaker": "GFCI breaker (680.44)", "spa_pack": "Listed spa pack (680.44)",
            "none": "None, but 680.44 requires GFCI protection",
        }[job.gfci]
        checks.append(Check("GFCI protection", gfci_result, job.gfci != "none"))
        checks.append(Check(
            "Disconnect distance",
            f"{job.disconnect_distance_ft} ft from the spa, {MIN_DISCONNECT_DISTANCE_FT} ft minimum",
            job.disconnect_distance_ft >= MIN_DISCONNECT_DISTANCE_FT))
    return AppliancePacket(
        job=job, load=load, load_amps=load_amps, minimum_breaker=minimum, breaker=breaker,
        branch=branch, conduit_size=conduit_size, checks=checks, flags=_flags(job, load, branch),
    )
