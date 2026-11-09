"""Residential panel / service upgrade permit: the job, the checks and the flags."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from permit_packets.core.checks import Check
from permit_packets.core.conductors import (
    SERVICE_CONDUCTOR_FACTOR,
    Conductor,
    Material,
    gec_size,
    service_conductor,
    service_conduit,
    solar_fits,
    wire_label,
)
from permit_packets.core.load_calculation import (
    HomeLoads,
    LoadCalculation,
    LoadLine,
    calculate_load,
)
from permit_packets.core.property_plan import PropertyPlan
from permit_packets.jurisdictions import ORO_VALLEY, Jurisdiction

VOLTS = 240
BUS_AND_MAIN_FACTOR = 1.2

Scope = Literal["upgrade", "replacement"]
Equipment = Literal["meter_main", "main_panel"]
ServiceDrop = Literal["overhead", "underground"]
Conduit = Literal["PVC", "EMT", "none"]
Electrode = Literal["rods", "concrete_encased", "water_pipe"]
EQUIPMENT_LABELS = {"meter_main": "Meter-main combo", "main_panel": "Main panel, meter separate"}
MATERIAL_ABBREVIATIONS = {"copper": "Cu", "aluminum": "Al"}
# Listed in the order the checks and the riser diagram show them.
ELECTRODE_LABELS = {
    "rods": "Ground rods",
    "concrete_encased": "Concrete-encased electrode",
    "water_pipe": "Metal water pipe",
}
CHECK_ELECTRODE_LABELS = {"rods": "Rods", "concrete_encased": "Concrete-encased", "water_pipe": "Water pipe"}
BRAND_LABELS = {
    "federal_pacific": "Federal Pacific", "zinsco": "Zinsco",
    "pushmatic": "Pushmatic", "challenger": "Challenger",
}
SMALLEST_UNPROTECTED_GEC = "8"
PLANNED_LOAD_BASIS = "Planned, 100% of nameplate"


@dataclass(frozen=True)
class PlannedLoadLine:
    label: str
    va: int


@dataclass(frozen=True)
class ServiceJob:
    customer: str
    address: str
    contractor: str
    license_number: str
    home: HomeLoads
    scope: Scope
    existing_service_amps: int
    new_service_amps: int
    equipment: Equipment
    service_drop: ServiceDrop
    se_length_ft: int
    electrodes: tuple[Electrode, ...]
    bus_amps: int
    relocated: bool = False
    material: Material = "copper"
    conduit: Conduit = "PVC"
    panel_model: str = ""
    existing_brand: str = "unknown"
    utility: str = ""
    meter_number: str = ""
    has_solar: bool = False
    pv_breaker_amps: int = 0
    planned_loads: tuple[PlannedLoadLine, ...] = ()
    jurisdiction: Jurisdiction = ORO_VALLEY
    plan: PropertyPlan | None = None


@dataclass(frozen=True)
class ServicePacket:
    job: ServiceJob
    load: LoadCalculation
    existing_load: LoadCalculation
    conductor: Conductor
    gecs: dict[str, str]  # electrode key to copper GEC size, in display order
    conduit_size: str | None
    checks: list[Check]
    flags: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def largest_gec(self) -> str:
        return min(self.gecs.values(), key=int)


def _flags(job: ServiceJob, gecs: dict[str, str]) -> list[str]:
    flags = [
        "Check the existing loads against the home. They drive the service result.",
        "Submit the utility service request (page 6). The utility sets the disconnect and reconnect.",
    ]
    if job.service_drop == "overhead":
        flags.append("Confirm mast, weatherhead and drip-loop clearances against the utility's service requirements.")
    else:
        flags.append("Confirm the lateral conduit size and who supplies it with the utility.")
    if job.relocated:
        flags.append("Relocating the meter needs the utility's approval of the new location.")
    if job.existing_brand in BRAND_LABELS:
        flags.append(
            f"Existing panel is a {BRAND_LABELS[job.existing_brand]}. Note it in the scope as the reason for replacement.")
    if SMALLEST_UNPROTECTED_GEC in gecs.values():
        flags.append("A #8 grounding electrode conductor must be protected in raceway or armor (250.64(B)).")
    flags += [
        "Confirm the available fault current with the utility and the new equipment's short-circuit rating (110.9, 110.24).",
        "Keep the working space in front of the panel clear: 30 in wide, 36 in deep (110.26).",
        "Extended or modified branch circuits may need AFCI protection (210.12(D)). Confirm the city's position.",
    ]
    if job.jurisdiction.state == "CA":
        flags.append("California: permit work over $1,000 can trigger smoke and CO alarm requirements. Confirm with the city.")
    if job.has_solar:
        flags.append("This home has solar. Confirm the PV breaker sits at the opposite end of the bus from the main.")
    if job.plan is None:
        flags.append("This site plan is a schematic. Replace it with the property's plan before submitting.")
    if job.jurisdiction.needs_parcel_number and not (job.plan and job.plan.parcel_number):
        flags.append("This city needs the parcel number on the application.")
    checklist = job.jurisdiction.checklist_for("service_upgrade")
    flags += [note.text for note in checklist.notes if note.when == "always"]
    flags.append(checklist.code_note)
    return flags


def build_service_packet(job: ServiceJob) -> ServicePacket:
    added = [LoadLine(planned.label, PLANNED_LOAD_BASIS, planned.va) for planned in job.planned_loads]
    load = calculate_load(job.home, service_amps=job.new_service_amps, added_loads=added, volts=VOLTS)
    existing_load = calculate_load(job.home, service_amps=job.existing_service_amps, added_loads=added, volts=VOLTS)
    conductor = service_conductor(job.new_service_amps, job.material)
    gecs = {
        electrode: gec_size(conductor, job.material, electrode)
        for electrode in ELECTRODE_LABELS if electrode in job.electrodes
    }
    conduit = service_conduit(conductor, job.conduit) if job.conduit != "none" else None
    metal = MATERIAL_ABBREVIATIONS[job.material]
    required = SERVICE_CONDUCTOR_FACTOR * job.new_service_amps
    checks = [
        Check("Service capacity",
              f"{load.computed_amps:.1f} A computed on the new {job.new_service_amps} A service",
              load.computed_amps <= job.new_service_amps),
        Check("Service conductors",
              f"{wire_label(conductor.size)} {metal} THWN-2, {conductor.ampacity_75c} A at 75\N{DEGREE SIGN}C, "
              f"for {job.new_service_amps} A x 83% = {required:.1f} A (310.12)",
              conductor.ampacity_75c >= required),
        Check("Panel rating", f"{job.bus_amps} A bus, {job.new_service_amps} A main",
              job.bus_amps >= job.new_service_amps),
        Check("Grounding electrode conductor",
              "; ".join(f"{CHECK_ELECTRODE_LABELS[electrode]}: #{size} Cu"
                        for electrode, size in gecs.items()),
              True),
    ]
    if conduit:
        checks.append(Check("Conduit fill", f"3 {wire_label(conductor.size)} in {conduit} {job.conduit}, 40% fill", True))
    if job.has_solar:
        total = job.new_service_amps + job.pv_breaker_amps
        checks.append(Check(
            "Solar (120% rule)",
            f"{job.new_service_amps} A main + {job.pv_breaker_amps} A PV = {total} A on a {job.bus_amps} A bus, "
            f"limit {BUS_AND_MAIN_FACTOR * job.bus_amps:.0f} A",
            solar_fits(job.bus_amps, job.new_service_amps, job.pv_breaker_amps),
        ))
    return ServicePacket(
        job=job, load=load, existing_load=existing_load, conductor=conductor, gecs=gecs,
        conduit_size=conduit, checks=checks, flags=_flags(job, gecs),
    )
