"""Commercial subpanel / feeder permit: the job, the checks and the flags."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from permit_packets.core.checks import Check
from permit_packets.core.commercial import (
    ASSUMED_LOAD_FACTOR,
    MAX_VOLTAGE_DROP_PERCENT,
    CommercialFeeder,
    DemandBasis,
    LoadLine,
    ServiceLoad,
    System,
    feeder_conduit,
    gec_check_for,
    new_load_line,
    panel_flags_for,
    size_feeder,
)
from permit_packets.core.conductors import Material, wire_label
from permit_packets.core.heat import exposure_flags
from permit_packets.core.panel_data import interrupting_rating_check
from permit_packets.core.panel_schedule import ExistingCircuit, MISSING_FLAG, panel_schedule_check
from permit_packets.core.property_plan import PropertyPlan
from permit_packets.core.raceways import above_ground
from permit_packets.jurisdictions import Jurisdiction

Location = Literal["inside_building", "exterior_wall", "detached_building"]
Conduit = Literal["PVC", "EMT"]
LOCATION_LABELS = {
    "inside_building": "inside the building",
    "exterior_wall": "on an exterior wall",
    "detached_building": "in a detached building",
}
MATERIAL_ABBREVIATIONS = {"copper": "Cu", "aluminum": "Al"}
BURIAL_COVER_TEXT = "PVC cover per Table 300.5: 18 in, or 24 in under driveways and parking lots"


@dataclass(frozen=True)
class SubpanelLoadLine:
    label: str
    kva: float
    continuous: bool = False


@dataclass(frozen=True)
class CommercialSubpanelJob:
    customer: str
    address: str
    contractor: str
    license_number: str
    system: System
    service_amps: int
    existing_demand_kva: float
    open_breaker_spaces: int
    location: Location
    subpanel_amps: int
    feeder_breaker_amps: int
    run_ft: int
    trench_ft: int
    demand_basis: DemandBasis = "utility_12_month"
    material: Material = "copper"
    conduit: Conduit = "EMT"
    building_use: str = ""
    subpanel_model: str = ""
    loads: tuple[SubpanelLoadLine, ...] = ()
    jurisdiction: Jurisdiction = None  # type: ignore[assignment]
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
        return self.trench_ft > 0 or self.location != "inside_building"

    @property
    def spaces_needed(self) -> int:
        return self.system.hots


@dataclass(frozen=True)
class CommercialSubpanelPacket:
    job: CommercialSubpanelJob
    load: ServiceLoad
    feeder: CommercialFeeder
    feeder_load_amps: float
    loads_assumed: bool
    conduit_size: str
    raceway_text: str
    checks: list[Check]
    flags: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)


def _flags(job: CommercialSubpanelJob, packet_load: ServiceLoad, feeder: CommercialFeeder, assumed: bool,
           raceway_note: str | None) -> list[str]:
    flags = []
    if job.demand_basis == "calculated":
        flags.append("Attach the Article 220 load calculation for the existing load behind the load page. "
                     "It drives the service result.")
    else:
        flags.append("Attach the demand report (12 months from the utility, or the 30-day recording) behind "
                     "the load page (220.87). It drives the service result.")
    if raceway_note:
        flags.append(raceway_note)
    if not packet_load.fits:
        flags.append(f"The service is over capacity by {-packet_load.spare_amps:.1f} A. Options are load "
                     "management, a service upgrade, or lower measured demand data.")
    if job.location == "detached_building":
        flags.append("A feeder to a detached building needs a disconnect at the building (225.31, 225.32) and "
                     "its own grounding electrode (250.32). Confirm the feeder's grounding with the city.")
    flags.append("Keep neutral and ground separate in the subpanel: no neutral-to-ground bond (250.24(A)(5), 250.142).")
    if job.trench_ft:
        flags.append(f"Call 811 before trenching. {BURIAL_COVER_TEXT} (300.5).")
    if feeder.upsized:
        flags.append(f"Feeder upsized to {wire_label(feeder.conductor.size)} for voltage drop, so the EGC is "
                     f"{wire_label(feeder.egc)} to match (250.122(B)).")
    if feeder.vd_percent > MAX_VOLTAGE_DROP_PERCENT:
        flags.append(f"Voltage drop is {feeder.vd_percent:.1f}% even at the largest size. Shorten the run, "
                     "move to a higher voltage or run parallel sets.")
    flags += [
        f"Confirm the breaker and panel terminals are rated 75{chr(176)}C (110.14(C)).",
        "Keep the working space in front of the panelboard clear: 30 in wide, 36 in deep, 6-1/2 ft high, "
        "and the dedicated space above it (110.26).",
        "Mark the panelboard for arc-flash hazard where it is likely to be examined while energized (110.16(A)) "
        "and identify the phase conductors and system (210.5(C), 215.12).",
        "Balance the new load across the three phases." if job.system.phases == 3 else
        "Balance the new load across the two legs.",
        "The neutral is carried at full size. Confirm it for non-linear loads (220.61).",
        "New branch circuits from the subpanel need GFCI protection where 210.8(B) requires it.",
    ]
    if assumed:
        flags.append("No loads listed, so the feeder load assumes 80% of the breaker. Add the planned loads.")
    flags += exposure_flags(job)
    if not job.existing_circuits:
        flags.append(MISSING_FLAG)
    flags += panel_flags_for(job)
    if job.plan is None:
        flags.append("This site plan is a schematic. Replace it with the property's plan before submitting.")
    if job.jurisdiction.needs_parcel_number and not (job.plan and job.plan.parcel_number):
        flags.append("This city needs the parcel number on the application.")
    active = {"always"} | ({"trench"} if job.trench_ft else set())
    checklist = job.jurisdiction.checklist_for("commercial_subpanel")
    flags += [note.text for note in checklist.notes if note.when in active]
    flags.append(checklist.code_note)
    return flags


def build_commercial_subpanel_packet(job: CommercialSubpanelJob) -> CommercialSubpanelPacket:
    system = job.system
    assumed = not job.loads
    if assumed:
        feeder_va = system.va(ASSUMED_LOAD_FACTOR * job.feeder_breaker_amps)
        lines = (LoadLine("Subpanel feeder load, assumed", "80% of the feeder breaker", feeder_va),)
    else:
        lines = tuple(new_load_line(item.label, item.kva * 1000, continuous=item.continuous) for item in job.loads)
        feeder_va = sum(line.va for line in lines)
    load = ServiceLoad(system, job.service_amps, job.existing_demand_kva, job.demand_basis, lines)
    feeder_load = system.amps(feeder_va)
    feeder = size_feeder(job.feeder_breaker_amps, job.material, feeder_load, job.run_ft, system)
    drawn = above_ground(job.jurisdiction, job.conduit, "feeder")
    if drawn.kind != job.conduit:  # PVC kept for the underground part only, metal raceway above ground
        conduit_size = feeder_conduit(feeder, drawn.kind)
        underground = feeder_conduit(feeder, job.conduit) if job.trench_ft else None
        raceway_text = (f"{underground} {job.conduit} underground, {conduit_size} {drawn.kind} above ground"
                        if underground else f"{conduit_size} {drawn.kind}")
    else:
        conduit_size = feeder_conduit(feeder, job.conduit)
        raceway_text = f"{conduit_size} {job.conduit}"
    size = wire_label(feeder.conductor.size)
    metal = MATERIAL_ABBREVIATIONS[job.material]
    degree = "\N{DEGREE SIGN}"
    checks = [
        Check("Service capacity", f"{load.amps:.1f} A computed on the {job.service_amps} A service ({system.volts} V)",
              load.fits),
        Check("Panel spaces", f"{job.open_breaker_spaces} open, {job.spaces_needed} needed",
              job.open_breaker_spaces >= job.spaces_needed),
        Check("Feeder breaker", f"{job.feeder_breaker_amps} A, {feeder.poles}-pole, on a {job.subpanel_amps} A subpanel",
              job.feeder_breaker_amps <= job.subpanel_amps),
        Check("Feeder conductors",
              f"{system.hots} {size} {metal} + {size} neutral + {wire_label(feeder.egc)} EGC, "
              f"{feeder.conductor.ampacity_75c} A at 75{degree}C", True),
        Check("Feeder load", f"{feeder_load:.1f} A of {job.feeder_breaker_amps} A"
              + ("" if assumed else ", continuous loads at 125%"), feeder_load <= job.feeder_breaker_amps),
        Check("Voltage drop", f"{feeder.vd_volts:.1f} V, {feeder.vd_percent:.1f}% over {job.run_ft} ft",
              feeder.vd_percent <= MAX_VOLTAGE_DROP_PERCENT),
        Check("Conduit fill", f"{system.hots + 1} wires in {raceway_text}, 40% fill", True),
        interrupting_rating_check(job),
        panel_schedule_check(job),
    ]
    gec = gec_check_for(job)
    if gec is not None:
        checks.insert(-2, gec)
    return CommercialSubpanelPacket(
        job=job, load=load, feeder=feeder, feeder_load_amps=feeder_load, loads_assumed=assumed,
        conduit_size=conduit_size, raceway_text=raceway_text, checks=checks,
        flags=_flags(job, load, feeder, assumed, drawn.note),
    )

