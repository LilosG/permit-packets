"""Residential subpanel / feeder permit: the job, the checks and the flags."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from permit_packets.core.heat import exposure_flags
from permit_packets.core.panel_data import gec_check, interrupting_rating_check, panel_flags
from permit_packets.core.panel_schedule import ExistingCircuit, MISSING_FLAG, panel_schedule_check
from permit_packets.core.checks import Check
from permit_packets.core.conductors import (
    FEEDER_VOLTS,
    MAX_FEEDER_VOLTAGE_DROP_PERCENT,
    Feeder,
    Material,
    feeder_conduit,
    size_feeder,
    wire_label,
)
from permit_packets.core.load_calculation import (
    HomeLoads,
    LoadCalculation,
    LoadLine,
    calculate_load,
)
from permit_packets.core.property_plan import PropertyPlan
from permit_packets.core.raceways import above_ground
from permit_packets.jurisdictions import ORO_VALLEY, Jurisdiction

Location = Literal["same_building", "attached_garage", "detached_building"]
Conduit = Literal["PVC", "EMT"]
LOCATION_LABELS = {
    "same_building": "same building",
    "attached_garage": "attached garage",
    "detached_building": "detached building",
}
MATERIAL_ABBREVIATIONS = {"copper": "Cu", "aluminum": "Al"}
ASSUMED_LOAD_FACTOR = 0.8  # the feeder load when no loads are listed: 80% of the breaker
SPACES_NEEDED = 2
SUBPANEL_LOAD_BASIS = "Subpanel, 100% of nameplate"
BURIAL_COVER_IN = 18  # NEC 300.5 Table 300.5, PVC in a trench


@dataclass(frozen=True)
class SubpanelLoadLine:
    label: str
    va: int


@dataclass(frozen=True)
class SubpanelJob:
    customer: str
    address: str
    contractor: str
    license_number: str
    home: HomeLoads
    service_amps: int
    open_breaker_spaces: int
    location: Location
    subpanel_amps: int
    feeder_breaker_amps: int
    run_ft: int
    trench_ft: int
    material: Material = "aluminum"
    conduit: Conduit = "PVC"
    whole_dwelling: bool = False
    subpanel_model: str = ""
    loads: tuple[SubpanelLoadLine, ...] = ()
    jurisdiction: Jurisdiction = ORO_VALLEY
    plan: PropertyPlan | None = None
    existing_circuits: tuple[ExistingCircuit, ...] = ()
    available_fault_current_a: int | None = None
    equipment_aic_ka: int = 10
    panel_location: str = ""
    panel_bus_amps: int | None = None
    panel_main: str | None = None
    gec_size: str = ""
    data_sheet_attached: bool = False

    @property
    def sun_exposed(self) -> bool:
        """Outdoors or in the sun: an underground run with risers, or a feeder out to a detached building."""
        return self.trench_ft > 0 or self.location == "detached_building"

    @property
    def design_ambient_f(self) -> int | None:
        """The city's design ambient, when part of this run is exposed to it."""
        return self.jurisdiction.design_ambient_f if self.sun_exposed else None


@dataclass(frozen=True)
class SubpanelPacket:
    job: SubpanelJob
    load: LoadCalculation  # the house, with the subpanel loads added
    feeder: Feeder
    feeder_load_amps: float
    loads_assumed: bool  # no loads were listed, so the feeder load is 80% of the breaker
    conduit_size: str
    checks: list[Check]
    flags: list[str] = field(default_factory=list)
    raceway_text: str = ""  # the conduit as drawn, e.g. '1-1/4" PVC underground, 1-1/4" EMT above ground'

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)


def _flags(job: SubpanelJob, load: LoadCalculation, feeder: Feeder, assumed: bool,
           raceway_note: str | None = None) -> list[str]:
    flags = ["Check the existing loads against the home. They drive the service result."]
    if raceway_note:
        flags.append(raceway_note)
    if load.computed_amps > job.service_amps:
        flags.append(
            f"The service is over capacity by {-load.spare_amps:.1f} A. Options are load management, "
            "a service upgrade, or 12 months of utility demand data (220.87)."
        )
    if job.location == "detached_building":
        flags.append(
            "A detached building needs its own grounding electrode (250.32(A)) and a disconnect at the "
            "building (225.31). The subpanel's main breaker can serve as the disconnect."
        )
    flags.append("Keep neutral and ground separate in the subpanel. No neutral-to-ground bond (250.24(A)(5)).")
    if job.trench_ft:
        flags.append(f"Call 811 before trenching. Confirm {BURIAL_COVER_IN} in of cover for PVC (300.5).")
    if feeder.upsized:
        flags.append(
            f"Feeder upsized to {wire_label(feeder.conductor.size)} for voltage drop, "
            f"so the EGC is {wire_label(feeder.egc)} to match (250.122(B))."
        )
    if feeder.vd_percent > MAX_FEEDER_VOLTAGE_DROP_PERCENT:
        flags.append(
            f"Voltage drop is {feeder.vd_percent:.1f}% even at the largest size. "
            "Shorten the run or redesign the feeder."
        )
    flags += [
        "Confirm the breaker and panel terminals are rated 75\N{DEGREE SIGN}C (110.14(C)).",
        "Keep the working space in front of both panels clear: 30 in wide, 36 in deep (110.26).",
        "New branch circuits in the subpanel need GFCI and AFCI protection where required (210.8, 210.12).",
    ]
    if assumed:
        flags.append("No loads listed, so the feeder load assumes 80% of the breaker. Add the planned loads.")
    flags += exposure_flags(job)
    if not job.existing_circuits:
        flags.append(MISSING_FLAG)
    flags += panel_flags(job, service_amps=job.service_amps)
    if job.plan is None:
        flags.append("This site plan is a schematic. Replace it with the property's plan before submitting.")
    if job.jurisdiction.needs_parcel_number and not (job.plan and job.plan.parcel_number):
        flags.append("This city needs the parcel number on the application.")
    active = {"always"} | ({"trench"} if job.trench_ft else set())
    checklist = job.jurisdiction.checklist_for("subpanel")
    flags += [note.text for note in checklist.notes if note.when in active]
    flags.append(checklist.code_note)
    return flags


def build_subpanel_packet(job: SubpanelJob) -> SubpanelPacket:
    added = [LoadLine(item.label, SUBPANEL_LOAD_BASIS, item.va) for item in job.loads]
    load = calculate_load(job.home, service_amps=job.service_amps, added_loads=added, volts=FEEDER_VOLTS)
    assumed = not job.loads
    feeder_load = (
        ASSUMED_LOAD_FACTOR * job.feeder_breaker_amps if assumed
        else sum(item.va for item in job.loads) / FEEDER_VOLTS
    )
    feeder = size_feeder(
        job.feeder_breaker_amps, job.material, feeder_load, job.run_ft, whole_dwelling=job.whole_dwelling,
        ambient_f=job.design_ambient_f)
    drawn = above_ground(job.jurisdiction, job.conduit, "feeder")
    if drawn.kind != job.conduit:  # PVC kept for the underground part only, metal raceway above ground
        conduit_size = feeder_conduit(feeder, drawn.kind)
        underground = feeder_conduit(feeder, job.conduit) if job.trench_ft else None
        raceway_text = (f"{underground} {job.conduit} underground, {conduit_size} {drawn.kind} above ground"
                        if underground else f"{conduit_size} {drawn.kind}")
    else:
        conduit_size = feeder_conduit(feeder, job.conduit)
        raceway_text = f"{conduit_size} {job.conduit}"
    metal = MATERIAL_ABBREVIATIONS[job.material]
    size = wire_label(feeder.conductor.size)
    checks = [
        Check("Service capacity",
              f"{load.computed_amps:.1f} A computed on the {job.service_amps} A service",
              load.computed_amps <= job.service_amps),
        Check("Panel spaces", f"{job.open_breaker_spaces} open, {SPACES_NEEDED} needed",
              job.open_breaker_spaces >= SPACES_NEEDED),
        Check("Feeder breaker", f"{job.feeder_breaker_amps} A breaker on a {job.subpanel_amps} A subpanel",
              job.feeder_breaker_amps <= job.subpanel_amps),
        Check("Feeder conductors",
              f"2 {size} {metal} + {size} neutral + {wire_label(feeder.egc)} EGC, "
              f"{feeder.conductor.ampacity_75c} A at 75\N{DEGREE SIGN}C",
              True),
        Check("Feeder load", f"{feeder_load:.1f} A of {job.feeder_breaker_amps} A",
              feeder_load <= job.feeder_breaker_amps),
        Check("Voltage drop", f"{feeder.vd_volts:.1f} V, {feeder.vd_percent:.1f}% over {job.run_ft} ft",
              feeder.vd_percent <= MAX_FEEDER_VOLTAGE_DROP_PERCENT),
        Check("Conduit fill", f"4 wires in {raceway_text}, 40% fill", True),
    ]
    if feeder.heat:
        checks.append(Check("Temperature correction", feeder.heat.line, feeder.heat.passed))
    checks.append(interrupting_rating_check(job))
    checks.append(panel_schedule_check(job))
    gec = gec_check(job, service_amps=job.service_amps)
    if gec:
        checks.append(gec)
    return SubpanelPacket(
        job=job, load=load, feeder=feeder, feeder_load_amps=feeder_load, loads_assumed=assumed,
        conduit_size=conduit_size, checks=checks, flags=_flags(job, load, feeder, assumed, drawn.note),
        raceway_text=raceway_text,
    )
