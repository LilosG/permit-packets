"""Residential Level 2 EV charger permit: the job, the checks and the flags."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from permit_packets.circuits import Circuit, conduit_size, size_circuit
from permit_packets.jurisdictions import ORO_VALLEY, Jurisdiction
from permit_packets.load_calculation import (
    HomeLoads,
    LoadCalculation,
    LoadLine,
    calculate_load,
)
from permit_packets.property_plan import PropertyPlan

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


@dataclass(frozen=True)
class Check:
    name: str
    result: str
    passed: bool


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

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)


def largest_charger_that_fits(load: LoadCalculation, charger_va: int) -> int | None:
    existing_va = load.total_va - charger_va
    room_amps = (load.service_amps * VOLTS - existing_va) / VOLTS
    return next((amps for amps in CHARGER_SIZES if amps <= room_amps), None)


def _flags(job: EvJob, load: LoadCalculation, circuit: Circuit, disconnect: int | None, charger_va: int) -> list[str]:
    flags = ["Check the existing loads against the home. They drive the service result."]
    if load.computed_amps > job.service_amps:
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
    if not job.charger_model:
        flags.append("Add the charger make and model, then attach its data sheet.")
    if job.trench_ft:
        flags.append("Call 811 before trenching and field verify the route.")
    if disconnect:
        flags.append("Confirm the disconnect location and type with the city.")
    if job.location == "detached_garage":
        flags.append("Confirm grounding requirements at the detached garage.")
    if job.plan is None:
        flags.append("This site plan is a schematic. Replace it with the property's plan before submitting.")
    if job.jurisdiction.needs_parcel_number and not (job.plan and job.plan.parcel_number):
        flags.append("This city needs the parcel number on the application.")
    active = {"always"} | ({"disconnect"} if disconnect else set()) | ({"trench"} if job.trench_ft else set())
    flags += [note.text for note in job.jurisdiction.notes if note.when in active]
    flags.append(job.jurisdiction.code_note)
    return flags


def build_ev_packet(job: EvJob) -> EvPacket:
    charger_va = job.charger_amps * VOLTS
    load = calculate_load(
        job.home,
        service_amps=job.service_amps,
        added_loads=[LoadLine("EV charger", f"{job.charger_amps} A x {VOLTS} V, 100%", charger_va)],
        volts=VOLTS,
    )
    circuit = size_circuit(job.charger_amps, job.run_ft, continuous=True, volts=VOLTS)
    disconnect = (
        circuit.breaker
        if job.location == "detached_garage" or job.charger_amps > DISCONNECT_REQUIRED_ABOVE_AMPS
        else None
    )
    checks = [
        Check("Service capacity",
              f"{load.computed_amps:.1f} A computed on a {job.service_amps} A service",
              load.computed_amps <= job.service_amps),
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
        flags=_flags(job, load, circuit, disconnect, charger_va),
    )
