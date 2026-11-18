"""Residential panel / service upgrade permit: the job, the checks and the flags."""
from __future__ import annotations

import re

from dataclasses import dataclass, field
from typing import Literal

from permit_packets.core.heat import HeatCalc, exposure_flags, heat_calc
from permit_packets.core.panel_data import SIZE_ORDER, gec_check, interrupting_rating_check, panel_flags
from permit_packets.core.panel_schedule import ExistingCircuit, MISSING_FLAG, panel_schedule_check
from permit_packets.core.checks import Check
from permit_packets.core.conductors import (
    SERVICE_CONDUCTOR_FACTOR,
    Conductor,
    Material,
    at_least,
    conduit_with_egc,
    egc_for,
    feeder_conductor,
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
from permit_packets.core.panel_model import service_panel_check
from permit_packets.core.raceways import above_ground, service_raceway
from permit_packets.core.equipment import find_equipment
from permit_packets.job_types.service_upgrade.ev_addon import EvAddOn, EvCircuit, ev_checks, ev_flags, size_ev
from permit_packets.jurisdictions import ORO_VALLEY, Jurisdiction

VOLTS = 240
BUS_AND_MAIN_FACTOR = 1.2

Scope = Literal["upgrade", "replacement"]
Equipment = Literal["meter_main", "main_panel"]
ServiceDrop = Literal["overhead", "underground"]
Conduit = Literal["PVC", "EMT", "RMC", "none"]
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
# A 400 A dwelling service here is a Class 320 meter-main (400 A maximum, 320 A continuous) with two 200 A
# main breakers, each in its own compartment, as the two service disconnects (NEC 230.71(B)). Each feeds a panel.
DUAL_SERVICE_AMPS = 400
DUAL_MAIN_AMPS = 200


@dataclass(frozen=True)
class FedPanel:
    """A panel fed from one of the two 200 A service disconnects of a 400 A meter-main."""
    model: str
    bus_amps: int
    location: str
    feeder_ft: int
    existing: bool = False


@dataclass(frozen=True)
class Feeder:
    name: str  # "Panel 1"
    main: str  # "Main 1"
    breaker: int
    conductor: Conductor
    egc: str
    conduit: str | None
    raceway: str
    panel: FedPanel
    heat: HeatCalc | None = None


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
    main_outdoors: bool = False
    panel_model: str = ""
    existing_brand: str = "unknown"
    utility: str = ""
    meter_number: str = ""
    has_solar: bool = False
    pv_breaker_amps: int = 0
    surge_protection: str | None = None
    planned_loads: tuple[PlannedLoadLine, ...] = ()
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
    panels: tuple[FedPanel, ...] = ()  # 400 A: the two panels the service disconnects feed, panel 1 first
    ev: EvAddOn | None = None

    @property
    def dual(self) -> bool:
        """A 400 A service: two 200 A service disconnects, each feeding a panel."""
        return self.new_service_amps == DUAL_SERVICE_AMPS

    @property
    def sun_exposed(self) -> bool:
        """Outdoors or in the sun: the service entrance conductors run outdoors from the weatherhead or riser to the meter."""
        return True

    @property
    def design_ambient_f(self) -> int | None:
        """The city's design ambient, when part of this run is exposed to it."""
        return self.jurisdiction.design_ambient_f if self.sun_exposed else None


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
    heat: HeatCalc | None = None
    # A meter-main feeds the panel through a feeder past the service disconnect: two hots, a neutral and this EGC.
    feeder_egc: str | None = None
    raceway: str = "PVC"  # what the run is drawn in: the electrician's choice unless the city's amendments forbid it
    # NEC 230.85: "main" when the main breaker is outdoors (a meter-main, or a main panel on an outside wall);
    # "meter_disconnect" when the main panel is inside and a disconnect goes in at the meter.
    emergency: str = "main"
    # Overhead upgrades: the new mast from the weatherhead to the meter, in RMC sized for the service conductors
    # (230.28 mast strength; 230.43 wiring method). None for underground (the lateral is the utility's) and
    # for a same-size panel replacement, which keeps the existing mast.
    mast_conduit: str | None = None
    feeders: tuple[Feeder, ...] = ()  # 400 A: one feeder per service disconnect
    ev: EvCircuit | None = None

    @property
    def is_meter_main(self) -> bool:
        return self.job.equipment == "meter_main"

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def largest_gec(self) -> str:
        return max(self.gecs.values(), key=SIZE_ORDER.index)


SPD_LABELS = {"type_1": "Type 1", "type_2": "Type 2"}


def meter_main_check(job) -> Check | None:
    """Where the utility publishes the meter-mains it accepts, the one named must be on the list."""
    approved = job.jurisdiction.approved_meter_mains
    if approved is None or job.equipment != "meter_main":
        return None
    utility = job.jurisdiction.utility_short or "the utility"
    words = set(re.findall(r"[A-Z0-9-]+", job.panel_model.upper()))
    match = next((number for number in approved if number in words), None)
    if match:
        return Check("Utility meter socket", f"{match} is on {utility}'s approved meter socket list", True)
    named = job.panel_model or "No meter-main named"
    return Check("Utility meter socket",
                 f"{named}: not on {utility}'s approved meter socket list. Pick one it lists", False)


def surge_check(job: ServiceJob) -> Check:
    """NEC 230.67: a dwelling service that is replaced or upgraded gets a Type 1 or Type 2 surge protective device."""
    if job.surge_protection not in SPD_LABELS:
        return Check("Surge protection", "Choose a Type 1 or Type 2 surge protective device (230.67)", False)
    return Check("Surge protection", f"{SPD_LABELS[job.surge_protection]} SPD at the service (230.67)", True)


EMERGENCY_MARKINGS = {
    "main": "EMERGENCY DISCONNECT, SERVICE DISCONNECT",
    "meter_disconnect": "EMERGENCY DISCONNECT, METER DISCONNECT, NOT SERVICE EQUIPMENT",
}


def emergency_line(job: ServiceJob, emergency: str) -> str:
    """What the riser, the scope and the checks say about the outdoor emergency disconnect (230.85)."""
    if job.dual:
        return (f"The two {DUAL_MAIN_AMPS} A main breakers in the meter-main are the outdoor emergency disconnects, "
                f"each marked \"{EMERGENCY_MARKINGS['main']}\" (230.85(1))")
    if emergency == "main":
        where = "meter-main" if job.equipment == "meter_main" else "main panel on the outside wall"
        return (f"The {job.new_service_amps} A main breaker in the {where} is the outdoor emergency disconnect, "
                f"marked \"{EMERGENCY_MARKINGS['main']}\" (230.85(1))")
    return (f"A {job.new_service_amps} A meter disconnect at the meter, outdoors and readily accessible, is the "
            f"emergency disconnect, marked \"{EMERGENCY_MARKINGS['meter_disconnect']}\" (230.85(2), 230.82(3))")


def _flags(job: ServiceJob, gecs: dict[str, str], notes: tuple[str, ...] = (), ev: EvCircuit | None = None) -> list[str]:
    flags = [
        "Check the existing loads against the home. They drive the service result.",
        "Submit the utility service request (page 7). The utility sets the disconnect and reconnect.",
    ]
    if job.service_drop == "overhead":
        flags.append("Confirm the mast size, its support, the point of attachment and drip-loop clearances against "
                     "the utility's service requirements (230.24, 230.26, 230.28).")
    else:
        flags.append("Confirm the lateral conduit size and who supplies it with the utility.")
    if job.relocated:
        flags.append("Relocating the meter needs the utility's approval of the new location.")
    if job.existing_brand in BRAND_LABELS:
        flags.append(
            f"Existing panel is a {BRAND_LABELS[job.existing_brand]}. Note it in the scope as the reason for replacement.")
    if job.dual:
        flags.append("Panels 1 and 2 are fed past the service disconnects: keep each panel's neutral bar isolated from "
                     "ground, bond the equipment grounding conductor to the enclosure and leave out the main bonding "
                     "jumper (250.24(A)(5), 250.142(B)).")
        flags.append("Mark each 200 A service disconnect with the panel it supplies, and mark each panel with where "
                     "it is fed from (230.70(B), 408.4(B)). Keep the two disconnects grouped (230.72(A)).")
        flags.append("With two service disconnects, put a surge protective device on each, in each panel or its "
                     "compartment, so the whole service is covered (230.67).")
        sheet = find_equipment(job.panel_model, "panel")
        if sheet is None or sheet.service_disconnects != 2:
            flags.append("Confirm the meter-main is listed with two 200 A service disconnects, each in its own "
                         "compartment (230.71(B)), and a Class 320 socket: 400 A maximum, 320 A continuous.")
        flags.append("A 400 A residential service is metered as Class 320 (320 A continuous). Confirm the utility's "
                     "meter panel requirements and whether it will upgrade the service drop or lateral.")
    elif job.equipment == "meter_main":
        flags.append("The panel fed from the meter-main is past the service disconnect: keep its neutral bar isolated "
                     "from ground, bond the equipment grounding conductor to the enclosure and leave out the main "
                     "bonding jumper (250.24(A)(5), 250.142(B)).")
    if SMALLEST_UNPROTECTED_GEC in gecs.values():
        flags.append("A #8 grounding electrode conductor must be protected in raceway or armor (250.64(B)).")
    flags += list(notes)
    if job.jurisdiction.concrete_encased_note and "concrete_encased" not in gecs:
        flags.append(job.jurisdiction.concrete_encased_note)
    flags += [
        "Confirm the available fault current with the utility and the new equipment's short-circuit rating (110.9).",
        "Keep the working space in front of the panel clear: 30 in wide, 36 in deep (110.26).",
        job.jurisdiction.afci_note or
        "Extended or modified branch circuits may need AFCI protection (210.12(D)). Confirm the city's position.",
    ]
    flags += exposure_flags(job)
    if job.has_solar:
        flags.append("This home has solar. Confirm the PV breaker sits at the opposite end of the bus from the main.")
    if not job.existing_circuits:
        flags.append(MISSING_FLAG)
    flags += panel_flags(job, service_amps=job.new_service_amps, material=job.material, electrodes=tuple(gecs))
    if job.plan is None:
        flags.append("This site plan is a schematic. Replace it with the property's plan before submitting.")
    if job.jurisdiction.needs_parcel_number and not (job.plan and job.plan.parcel_number):
        flags.append("This city needs the parcel number on the application.")
    if ev is not None:
        flags += ev_flags(ev, job.jurisdiction)
    checklist = job.jurisdiction.checklist_for("service_upgrade")
    flags += [note.text for note in checklist.notes if note.when == "always"]
    flags.append(checklist.code_note)
    return flags


def dual_feeders(job: ServiceJob, material: Material, raceway: str) -> tuple[Feeder, ...]:
    """One 200 A feeder from each service disconnect to its panel, sized at 75 C for the breaker (310.16)."""
    feeders = []
    for index, panel in enumerate(job.panels, start=1):
        conductor = feeder_conductor(DUAL_MAIN_AMPS, material, whole_dwelling=False, ambient_f=job.design_ambient_f)
        egc = egc_for(DUAL_MAIN_AMPS, material)
        conduit = None if raceway == "cable" else conduit_with_egc(conductor, egc, raceway)
        heat = (heat_calc(conductor.size, material, job.design_ambient_f, cap_a=conductor.ampacity_75c,
                          carries_a=DUAL_MAIN_AMPS, carries_label=f"{DUAL_MAIN_AMPS} A main")
                if job.design_ambient_f is not None else None)
        feeders.append(Feeder(f"Panel {index}", f"Main {index}", DUAL_MAIN_AMPS, conductor, egc, conduit, raceway,
                              panel, heat))
    return tuple(feeders)


def _dual_checks(job: ServiceJob, feeders: tuple[Feeder, ...], ev: EvCircuit | None) -> list[Check]:
    metal = MATERIAL_ABBREVIATIONS[job.material]
    checks = []
    sheet = find_equipment(job.panel_model, "panel")
    if sheet is not None:
        problems = []
        if not sheet.meter_main:
            problems.append("it is not a meter-main")
        if sheet.service_disconnects != 2 or sheet.main_amps != DUAL_MAIN_AMPS:
            problems.append("it does not have two 200 A service disconnects")
        if not sheet.class_320:
            problems.append("its meter socket is not Class 320")
        checks.append(Check(
            "Service disconnects",
            f"{sheet.name}: {'; '.join(problems)}" if problems else
            f"2 x {DUAL_MAIN_AMPS} A main breakers, each in its own compartment (230.71(B)); Class 320 socket, "
            "400 A maximum, 320 A continuous, per the data sheet", not problems))
    for feeder in feeders:
        # One line per feeder: conductor, heat, conduit and the panel's bus.
        parts = [f"{wire_label(feeder.conductor.size)} {metal} THWN-2 + #{feeder.egc} EGC, "
                 f"{feeder.conductor.ampacity_75c} A at 75\N{DEGREE SIGN}C for the {feeder.breaker} A main (310.16)"]
        passed = feeder.conductor.ampacity_75c >= feeder.breaker and feeder.panel.bus_amps >= feeder.breaker
        if feeder.heat:
            parts.append(f"{feeder.heat.corrected_a:.0f} A at {job.design_ambient_f}\N{DEGREE SIGN}F (310.15(B)(1))")
            passed = passed and feeder.heat.passed
        if feeder.conduit:
            parts.append(f"{feeder.conduit} {feeder.raceway}, 40% fill")
        parts.append(f"{feeder.panel.bus_amps} A bus")
        checks.append(Check(f"Feeder, {feeder.main.lower()} to {feeder.name.lower()}", "; ".join(parts), passed))
    # Each disconnect carries its own panel's load: panel 1 the home as it is, panel 2 the new loads.
    house = calculate_load(job.home, service_amps=DUAL_MAIN_AMPS, added_loads=[], volts=VOLTS)
    checks.append(Check("Main 1 load", f"{house.computed_amps:.1f} A, the home's existing loads (220.82), on "
                        f"the {DUAL_MAIN_AMPS} A main", house.computed_amps <= DUAL_MAIN_AMPS))
    new_va = sum(load.va for load in job.planned_loads) + (ev.addon.va if ev else 0)
    if new_va:
        checks.append(Check("Main 2 load", f"{new_va / VOLTS:.1f} A of new loads at 100% of nameplate, on the "
                            f"{DUAL_MAIN_AMPS} A main", new_va / VOLTS <= DUAL_MAIN_AMPS))
    return checks


def _ev_panel_name(job: ServiceJob) -> str:
    if job.dual:
        return "Panel 2"
    return "the new panel" if job.equipment == "meter_main" else "the new main panel"


def build_service_packet(job: ServiceJob) -> ServicePacket:
    jurisdiction = job.jurisdiction
    ev = size_ev(job.ev, jurisdiction.design_ambient_f, _ev_panel_name(job)) if job.ev else None
    added = [LoadLine(planned.label, PLANNED_LOAD_BASIS, planned.va) for planned in job.planned_loads]
    if ev:
        added.append(LoadLine("EV charger", f"{ev.addon.charger_amps} A x {VOLTS} V, 100%", ev.addon.va))
    load = calculate_load(job.home, service_amps=job.new_service_amps, added_loads=added, volts=VOLTS)
    existing_load = calculate_load(job.home, service_amps=job.existing_service_amps, added_loads=added, volts=VOLTS)
    # The service conductors: for 400 A the mast's conductors, and the size the grounding is sized from (250.66).
    conductor = service_conductor(job.new_service_amps, job.material, job.design_ambient_f)
    gecs = {
        electrode: gec_size(conductor, job.material, electrode)
        for electrode in ELECTRODE_LABELS if electrode in job.electrodes
    }
    feeder_egc = egc_for(job.new_service_amps, job.material) if job.equipment == "meter_main" and not job.dual else None
    past_disconnect = job.dual or bool(feeder_egc)
    if past_disconnect:  # past the service disconnect: a feeder, so the service-entrance amendments don't apply
        drawn = above_ground(jurisdiction, "cable" if job.conduit == "none" else job.conduit, "feeder")
    else:
        drawn = service_raceway(jurisdiction, job.conduit)
    raceway = drawn.kind
    feeders = dual_feeders(job, job.material, raceway) if job.dual else ()
    if raceway == "cable" or job.dual:
        conduit = None
    elif feeder_egc:
        conduit = conduit_with_egc(conductor, feeder_egc, raceway)
    else:
        conduit = at_least(service_conduit(conductor, raceway), jurisdiction.min_service_raceway)
    emergency = "main" if job.equipment == "meter_main" or job.main_outdoors else "meter_disconnect"
    mast_conduit = (at_least(service_conduit(conductor, "RMC"), jurisdiction.min_service_raceway)
                    if job.service_drop == "overhead" and job.scope == "upgrade" else None)
    metal = MATERIAL_ABBREVIATIONS[job.material]
    required = SERVICE_CONDUCTOR_FACTOR * job.new_service_amps
    # 400 A underground: the lateral is the utility's and lands in the meter-main, so there are no
    # contractor service conductors to correct for heat.
    service_conductors = not (job.dual and job.service_drop == "underground")
    heat = (
        heat_calc(conductor.size, job.material, job.design_ambient_f, cap_a=conductor.ampacity_75c, carries_a=required,
                  carries_label="83% of service (310.12)")
        if job.design_ambient_f is not None and service_conductors else None
    )
    if job.dual:
        conductor_check = "Service conductors, mast"
    else:
        conductor_check = "Feeder conductors, meter-main to panel" if feeder_egc else "Service conductors"
    checks = [
        Check("Service capacity",
              f"{load.computed_amps:.1f} A computed on the new {job.new_service_amps} A service",
              load.computed_amps <= job.new_service_amps),
    ]
    if service_conductors:
        checks.append(Check(
            conductor_check,
            f"{wire_label(conductor.size)} {metal} THWN-2, {conductor.ampacity_75c} A at 75\N{DEGREE SIGN}C, "
            f"for {job.new_service_amps} A x 83% = {required:.1f} A (310.12)",
            conductor.ampacity_75c >= required))
    if job.dual:
        checks.append(Check("Meter-main rating", f"{job.bus_amps} A meter-main, {job.new_service_amps} A service",
                            job.bus_amps >= job.new_service_amps))
    else:
        checks.append(Check("Panel rating", f"{job.bus_amps} A bus, {job.new_service_amps} A main",
                            job.bus_amps >= job.new_service_amps))
    checks.append(Check("Grounding electrode conductor",
                        "; ".join(f"{CHECK_ELECTRODE_LABELS[electrode]}: #{size} Cu" for electrode, size in gecs.items()),
                        True))
    if conduit:
        ground = f" + 1 #{feeder_egc} EGC" if feeder_egc else ""
        minimum = (f", {jurisdiction.min_service_raceway} minimum (local 230.43(B))"
                   if jurisdiction.min_service_raceway and not feeder_egc else "")
        checks.append(Check("Conduit fill",
                            f"3 {wire_label(conductor.size)}{ground} in {conduit} {raceway}, 40% fill{minimum}", True))
    checks.append(Check("Emergency disconnect", emergency_line(job, emergency), True))
    limit = jurisdiction.max_meter_to_main_ft
    if limit and emergency == "meter_disconnect":
        checks.append(Check(
            "Main disconnect distance",
            f"{job.se_length_ft} ft from the meter to the main, {limit} ft limit ({jurisdiction.name} 230.70(A)(1))",
            job.se_length_ft <= limit))
    if job.has_solar:
        # 400 A: the PV breaker stays in panel 1, the home's panel, behind its 200 A main.
        bus, main = ((job.panels[0].bus_amps, DUAL_MAIN_AMPS) if job.dual and job.panels
                     else (job.bus_amps, job.new_service_amps))
        where = " in panel 1" if job.dual else ""
        total = main + job.pv_breaker_amps
        checks.append(Check(
            "Solar (120% rule)",
            f"{main} A main + {job.pv_breaker_amps} A PV = {total} A on a {bus} A bus{where}, "
            f"limit {BUS_AND_MAIN_FACTOR * bus:.0f} A",
            solar_fits(bus, main, job.pv_breaker_amps),
        ))
    if heat:
        checks.append(Check("Temperature correction", heat.line, heat.passed))
    if any(r.section == "surge" for r in job.jurisdiction.checklist_for("service_upgrade").items):
        checks.append(surge_check(job))
    if job.dual:
        checks += _dual_checks(job, feeders, ev)
    else:
        model = service_panel_check(job)
        if model:
            checks.append(model)
    meter_main = meter_main_check(job)
    if meter_main:
        checks.append(meter_main)
    if ev:
        checks += ev_checks(ev)
    checks.append(interrupting_rating_check(job))
    checks.append(panel_schedule_check(job))
    gec = gec_check(job, service_amps=job.new_service_amps, material=job.material, electrodes=tuple(gecs))
    if gec:
        checks.append(gec)
    return ServicePacket(
        job=job, load=load, existing_load=existing_load, conductor=conductor, gecs=gecs,
        conduit_size=conduit, checks=checks, flags=_flags(job, gecs, (drawn.note,) if drawn.note else (), ev),
        heat=heat, feeder_egc=feeder_egc, raceway=raceway, emergency=emergency, mast_conduit=mast_conduit,
        feeders=feeders, ev=ev,
    )
