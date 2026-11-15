"""Residential Level 2 EV charger permit: the job, the checks and the flags."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from permit_packets.core.checks import Check
from permit_packets.core.heat import exposure_flags
from permit_packets.core.panel_data import gec_check, interrupting_rating_check, panel_flags
from permit_packets.core.panel_schedule import ExistingCircuit, MISSING_FLAG, panel_schedule_check
from permit_packets.core.equipment import find_equipment
from permit_packets.core.circuits import Circuit, conduit_size, size_circuit
from permit_packets.jurisdictions import ORO_VALLEY, Jurisdiction
from permit_packets.core.load_calculation import (
    MeasuredDemand,
    HomeLoads,
    LoadCalculation,
    LoadLine,
    calculate_load,
)
from permit_packets.core.property_plan import PropertyPlan

VOLTS = 240
HIGH_SERVICE_USE_PERCENT = 80
HIGH_VOLTAGE_DROP_PERCENT = 3
DISCONNECT_REQUIRED_ABOVE_AMPS = 60
BURIAL_DEPTH_IN = 18
LARGEST_RECEPTACLE_BREAKER = 50
CHARGER_SIZES = (80, 64, 48, 40, 32, 24, 16)

Location = Literal["attached_garage", "detached_garage", "exterior_wall"]
Connection = Literal["hardwired", "receptacle"]
LOCATION_LABELS = {
    "attached_garage": "attached garage",
    "detached_garage": "detached garage",
    "exterior_wall": "exterior wall",
}


@dataclass(frozen=True)
class EvJob:
    customer: str
    address: str
    contractor: str
    license_number: str
    home: HomeLoads
    service_amps: int
    open_breaker_spaces: int
    charger_amps: int
    location: Location
    run_ft: int
    trench_ft: int
    charger_model: str = ""
    connection: Connection = "hardwired"
    has_solar: bool = False
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
    charger_venting_required: bool | None = None
    hoa_approval: str | None = None

    @property
    def sun_exposed(self) -> bool:
        """Outdoors or in the sun: the charger on an exterior wall, or conduit risers out of a trench."""
        return self.location == "exterior_wall" or self.trench_ft > 0

    @property
    def design_ambient_f(self) -> int | None:
        """The city's design ambient, when part of this run is exposed to it."""
        return self.jurisdiction.design_ambient_f if self.sun_exposed else None
    peak_demand_kw: float | None = None
    demand_source: str = "utility_12_month"


@dataclass(frozen=True)
class EvPacket:
    job: EvJob
    charger_va: int
    load: LoadCalculation
    circuit: Circuit
    disconnect_amps: int | None
    underground_conduit: str | None
    interior_conduit: str
    interior_ft: int
    checks: list[Check]
    flags: list[str] = field(default_factory=list)
    measured: MeasuredDemand | None = None

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)


def largest_charger_that_fits(load: LoadCalculation, charger_va: int) -> int | None:
    existing_va = load.total_va - charger_va
    room_amps = (load.service_amps * VOLTS - existing_va) / VOLTS
    return next((amps for amps in CHARGER_SIZES if amps <= room_amps), None)


def _flags(job: EvJob, load: LoadCalculation, circuit: Circuit, disconnect: int | None, charger_va: int,
           measured: MeasuredDemand | None = None) -> list[str]:
    flags = ["Check the existing loads against the home. They drive the service result."]
    if measured:
        flags.append("Attach the demand report (12 months from the utility, or the 30-day recording) "
                     "behind the load calculation (220.87).")
        if load.computed_amps > job.service_amps and measured.fits:
            flags.append(f"The 220.82 calculation shows {load.computed_amps:.1f} A; this packet relies on "
                         "measured demand (220.87). Confirm the city accepts it.")
        if job.has_solar:
            flags.append("This home has solar. The 2023 NEC limits using demand data where solar or peak "
                         "shaving masks the load (220.87). Confirm with the city.")
    if load.computed_amps > job.service_amps and not (measured and measured.fits):
        fits = largest_charger_that_fits(load, charger_va)
        option = f"A {fits} A charger fits this service" if fits else "No common charger size fits this service"
        flags.append(
            f"The service is over capacity by {-load.spare_amps:.1f} A. {option}. Other options are "
            "load management, a service upgrade, or 12 months of utility demand data (220.87)."
        )
    elif load.percent_of_service >= HIGH_SERVICE_USE_PERCENT:
        flags.append(
            f"Service is at {load.percent_of_service:.0f}% of capacity. "
            "Review it before adding this load."
        )
    if job.open_breaker_spaces < 2:
        flags.append("The panel needs two open spaces for this breaker.")
    if circuit.upsized_for_voltage_drop:
        flags.append(
            f"Wire was upsized to #{circuit.wire.size} AWG for voltage drop, "
            f"so the equipment ground is #{circuit.ground} AWG to match (250.122(B))."
        )
    if circuit.voltage_drop_percent > HIGH_VOLTAGE_DROP_PERCENT:
        flags.append(
            f"Voltage drop is {circuit.voltage_drop_percent:.1f}% even at the largest wire size. "
            "Shorten the run or redesign the circuit."
        )
    if job.connection == "receptacle":
        flags.append("EV receptacles need GFCI protection. Confirm a listed GFCI breaker for this panel.")
    if job.has_solar:
        flags.append("This home has solar. Check the panel's bus rating and solar breaker before adding this load.")
    charger = find_equipment(job.charger_model, "charger") if job.charger_model else None
    if not job.charger_model:
        flags.append("Add the charger make and model, then attach its data sheet.")
    elif charger is None:
        if not job.data_sheet_attached:
            flags.append(f"Attach the {job.charger_model} data sheet behind the equipment page. It isn't in the equipment library yet.")
    elif charger.max_amps < job.charger_amps:
        flags.append(f"The {charger.name} is rated {charger.max_amps} A, below the {job.charger_amps} A set here.")
    if job.trench_ft:
        flags.append("Call 811 before trenching and field verify the route.")
    if disconnect:
        flags.append("Confirm the disconnect location and type with the city.")
    if job.location == "detached_garage":
        flags.append("Confirm grounding requirements at the detached garage.")
    flags += exposure_flags(job)
    if not job.existing_circuits:
        flags.append(MISSING_FLAG)
    flags += panel_flags(job, service_amps=job.service_amps)
    if job.plan is None:
        flags.append("This site plan is a schematic. Replace it with the property's plan before submitting.")
    if job.jurisdiction.needs_parcel_number and not (job.plan and job.plan.parcel_number):
        flags.append("This city needs the parcel number on the application.")
    active = ({"always", "outdoor" if job.location == "exterior_wall" else "indoor"}
              | ({"disconnect"} if disconnect else set()) | ({"trench"} if job.trench_ft else set()))
    checklist = job.jurisdiction.checklist_for("ev_charger")
    flags += [note.text for note in checklist.notes if note.when in active]
    flags.append(checklist.code_note)
    return flags


def build_ev_packet(job: EvJob) -> EvPacket:
    charger_va = job.charger_amps * VOLTS
    load = calculate_load(
        job.home,
        service_amps=job.service_amps,
        added_loads=[LoadLine("EV charger", f"{job.charger_amps} A x {VOLTS} V, 100%", charger_va)],
        volts=VOLTS,
    )
    circuit = size_circuit(job.charger_amps, job.run_ft, continuous=True, volts=VOLTS, ambient_f=job.design_ambient_f)
    disconnect = (
        circuit.breaker
        if job.location == "detached_garage" or job.charger_amps > DISCONNECT_REQUIRED_ABOVE_AMPS
        else None
    )
    measured = (
        MeasuredDemand(job.peak_demand_kw, job.demand_source, f"EV charger at 125% ({job.charger_amps} A)",
                       charger_va * 1.25, job.service_amps, VOLTS)
        if job.peak_demand_kw else None
    )
    capacity = (
        Check("Service capacity", f"{measured.amps:.1f} A by measured demand (220.87) on a {job.service_amps} A service",
              measured.fits)
        if measured else
        Check("Service capacity", f"{load.computed_amps:.1f} A computed on a {job.service_amps} A service",
              load.computed_amps <= job.service_amps)
    )
    checks = [
        capacity,
        Check("Panel spaces", f"{job.open_breaker_spaces} open, 2 needed",
              job.open_breaker_spaces >= 2),
        Check("Circuit",
              f"{circuit.breaker} A breaker for a {job.charger_amps} A continuous load "
              f"({job.charger_amps} A x 125%)",
              circuit.breaker >= circuit.required_amps),
        Check("Conductors",
              f"#{circuit.wire.size} AWG Cu, rated {circuit.wire.ampacity_75c} A at 75\N{DEGREE SIGN}C",
              circuit.wire.ampacity_75c >= circuit.breaker),
        Check("Voltage drop",
              f"{circuit.voltage_drop_volts:.1f} V, or {circuit.voltage_drop_percent:.1f}%, over {job.run_ft} ft",
              circuit.voltage_drop_percent <= HIGH_VOLTAGE_DROP_PERCENT),
    ]
    if job.connection == "receptacle":
        checks.append(Check(
            "Connection",
            f"{circuit.breaker} A receptacle circuit" if circuit.breaker <= LARGEST_RECEPTACLE_BREAKER
            else f"A {job.charger_amps} A charger must be hardwired",
            circuit.breaker <= LARGEST_RECEPTACLE_BREAKER,
        ))
    if circuit.heat:
        checks.append(Check("Temperature correction", circuit.heat.line, circuit.heat.passed))
    checks.append(interrupting_rating_check(job))
    checks.append(panel_schedule_check(job))
    gec = gec_check(job, service_amps=job.service_amps)
    if gec:
        checks.append(gec)
    return EvPacket(
        job=job,
        charger_va=charger_va,
        load=load,
        circuit=circuit,
        disconnect_amps=disconnect,
        underground_conduit=conduit_size(circuit, "PVC") if job.trench_ft else None,
        interior_conduit=conduit_size(circuit, "EMT"),
        interior_ft=max(job.run_ft - job.trench_ft, 0),
        checks=checks,
        flags=_flags(job, load, circuit, disconnect, charger_va, measured),
        measured=measured,
    )
