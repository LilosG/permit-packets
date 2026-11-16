"""Commercial Level 2 EV charger permit: the job, the checks and the flags."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from permit_packets.core.checks import Check
from permit_packets.core.circuits import Circuit, conduit_size, size_circuit
from permit_packets.core.conductors import wire_label
from permit_packets.core.commercial import (
    DemandBasis,
    LoadLine,
    ServiceLoad,
    System,
    gec_check_for,
    new_load_line,
    panel_flags_for,
)
from permit_packets.core.equipment import find_equipment
from permit_packets.core.heat import exposure_flags
from permit_packets.core.panel_data import interrupting_rating_check
from permit_packets.core.panel_schedule import ExistingCircuit, MISSING_FLAG, panel_schedule_check
from permit_packets.core.property_plan import PropertyPlan
from permit_packets.jurisdictions import Jurisdiction

DISCONNECT_REQUIRED_ABOVE_AMPS = 60  # CEC 625.43
MAX_VOLTAGE_DROP_PERCENT = 3
BURIAL_COVER_TEXT = "PVC cover per Table 300.5: 18 in, or 24 in under driveways and parking lots"
Location = Literal["parking_lot", "parking_garage", "building_wall"]
LOCATION_LABELS = {"parking_lot": "parking lot", "parking_garage": "parking garage", "building_wall": "building wall"}


@dataclass(frozen=True)
class CommercialEvJob:
    customer: str
    address: str
    contractor: str
    license_number: str
    system: System
    service_amps: int
    existing_demand_kva: float
    open_breaker_spaces: int
    charger_count: int
    charger_amps: int
    location: Location
    run_ft: int
    trench_ft: int
    demand_basis: DemandBasis = "utility_12_month"
    building_use: str = ""
    charger_model: str = ""
    load_management: bool = False
    managed_limit_amps: int | None = None
    accessible_spaces: int | None = None
    charger_venting_required: bool | None = None
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
    def volts(self) -> int:
        """Chargers run line to line: 208 V from a 208Y/120 V system, 240 V from a 120/240 V one."""
        return 208 if self.system.phases == 3 else 240

    @property
    def charger_kw(self) -> float:
        return self.volts * self.charger_amps / 1000

    @property
    def sun_exposed(self) -> bool:
        return self.location != "parking_garage" or self.trench_ft > 0

    @property
    def spaces_needed(self) -> int:
        return 2 * self.charger_count

    @property
    def disconnect_required(self) -> bool:
        return self.charger_amps > DISCONNECT_REQUIRED_ABOVE_AMPS


@dataclass(frozen=True)
class CommercialEvPacket:
    job: CommercialEvJob
    load: ServiceLoad
    circuit: Circuit
    underground_conduit: str | None
    interior_conduit: str
    checks: list[Check]
    flags: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def total_charger_kw(self) -> float:
        return self.job.charger_kw * self.job.charger_count


def _flags(job: CommercialEvJob, load: ServiceLoad, circuit: Circuit) -> list[str]:
    flags = []
    if job.demand_basis == "calculated":
        flags.append("Attach the Article 220 load calculation for the existing load behind the load page. "
                     "It drives the service result.")
    else:
        flags.append("Attach the demand report (12 months from the utility, or the 30-day recording) behind "
                     "the load page (220.87). It drives the service result.")
    if not load.fits:
        flags.append(
            f"The service is over capacity by {-load.spare_amps:.1f} A. Options are an energy management system "
            "that limits the chargers (625.42), fewer or smaller chargers, or a service upgrade.")
    elif load.percent_of_service >= 80:
        flags.append(f"The service is at {load.percent_of_service:.0f}% of capacity with these chargers. "
                     "Review it before adding this load.")
    if job.open_breaker_spaces < job.spaces_needed:
        flags.append(f"The panel needs {job.spaces_needed} open spaces for {job.charger_count} two-pole "
                     "charger breakers.")
    if job.load_management:
        flags.append("The energy management system must be listed for the purpose and set to hold the chargers to "
                     f"{job.managed_limit_amps} A (625.42). Show its settings on the plans.")
    if circuit.upsized_for_voltage_drop:
        flags.append(f"Wire was upsized to {wire_label(circuit.wire.size)} for voltage drop, so the equipment ground is "
                     f"{wire_label(circuit.ground)} to match (250.122(B)).")
    if circuit.voltage_drop_percent > MAX_VOLTAGE_DROP_PERCENT:
        flags.append(f"Voltage drop is {circuit.voltage_drop_percent:.1f}% even at the largest wire size. "
                     "Shorten the run or feed the chargers from a closer panel.")
    if job.charger_count > 1:
        flags.append("Circuits sharing a conduit or trench need the ampacity adjustment for more than three "
                     "current-carrying conductors (310.15(C)(1)) and a check of the conduit fill.")
    if job.disconnect_required:
        flags.append("A charger rated over 60 A needs a readily accessible disconnect (625.43). Show its location.")
    charger = find_equipment(job.charger_model, "charger") if job.charger_model else None
    if not job.charger_model:
        flags.append("Add the charger make and model, then attach its data sheet.")
    elif charger is None:
        if not job.data_sheet_attached:
            flags.append(f"Attach the {job.charger_model} data sheet behind the equipment page. It isn't in the "
                         "equipment library yet.")
    elif charger.max_amps < job.charger_amps:
        flags.append(f"The {charger.name} is rated {charger.max_amps} A, below the {job.charger_amps} A set here.")
    flags.append("Chargers and equipment must be listed (625.5). Wire is sized at the 75\N{DEGREE SIGN}C column: "
                 "confirm the charger and breaker terminals are marked for it (110.14(C)).")
    if job.location == "parking_garage":
        if job.charger_venting_required is None:
            flags.append("Ask the manufacturer whether the charger needs ventilation for indoor use (625.52) and "
                         "record the answer.")
        elif job.charger_venting_required:
            flags.append("The charger needs ventilation indoors (625.52). Show the ventilation on the plans.")
    if job.accessible_spaces is None:
        flags.append("Enter how many charging spaces are accessible. California Building Code 11B-228.3 sets the "
                     "number and the path of travel.")
    else:
        flags.append("Confirm the accessible charging spaces and their path of travel against California Building "
                     "Code 11B-228.3.")
    if job.trench_ft:
        flags.append(f"Call 811 before trenching. {BURIAL_COVER_TEXT} (300.5).")
    flags += [
        "Keep the working space in front of the panel clear: 30 in wide, 36 in deep, 6-1/2 ft high (110.26).",
        "Update the panel directory so every charger circuit is identified (408.4(A)).",
    ]
    flags += exposure_flags(job)
    if not job.existing_circuits:
        flags.append(MISSING_FLAG)
    flags += panel_flags_for(job)
    if job.plan is None:
        flags.append("This site plan is a schematic. Replace it with the property's plan before submitting.")
    if job.jurisdiction.needs_parcel_number and not (job.plan and job.plan.parcel_number):
        flags.append("This city needs the parcel number on the application.")
    active = {"always"} | ({"trench"} if job.trench_ft else set()) | ({"disconnect"} if job.disconnect_required else set())
    checklist = job.jurisdiction.checklist_for("commercial_ev_charger")
    flags += [note.text for note in checklist.notes if note.when in active]
    flags.append(checklist.code_note)
    return flags


def build_commercial_ev_packet(job: CommercialEvJob) -> CommercialEvPacket:
    system = job.system
    total_va = job.charger_count * job.volts * job.charger_amps
    if job.load_management:
        line = LoadLine("EV chargers, managed", f"EVEMS holds them to {job.managed_limit_amps} A (625.42)",
                        system.va(job.managed_limit_amps))
    else:
        line = new_load_line(
            f"{job.charger_count} x EV charger", total_va, continuous=True,
            basis=f"{job.charger_count} x {job.charger_amps} A x {job.volts} V")
    load = ServiceLoad(system, job.service_amps, job.existing_demand_kva, job.demand_basis, (line,))
    circuit = size_circuit(job.charger_amps, job.run_ft, continuous=True, volts=job.volts)
    degree = "\N{DEGREE SIGN}"
    checks = [
        Check("Service capacity", f"{load.amps:.1f} A computed on the {job.service_amps} A service ({system.volts} V)",
              load.fits),
        Check("Panel spaces", f"{job.open_breaker_spaces} open, {job.spaces_needed} needed",
              job.open_breaker_spaces >= job.spaces_needed),
        Check("Circuit", f"{circuit.breaker} A, 2-pole breaker for a {job.charger_amps} A continuous load "
              f"({job.charger_amps} A x 125%)", circuit.breaker >= circuit.required_amps),
        Check("Conductors", f"{wire_label(circuit.wire.size)} Cu, rated {circuit.wire.ampacity_75c} A at 75{degree}C",
              circuit.wire.ampacity_75c >= circuit.breaker),
        Check("Voltage drop", f"{circuit.voltage_drop_volts:.1f} V, or {circuit.voltage_drop_percent:.1f}%, over "
              f"{job.run_ft} ft", circuit.voltage_drop_percent <= MAX_VOLTAGE_DROP_PERCENT),
        interrupting_rating_check(job),
        panel_schedule_check(job),
    ]
    gec = gec_check_for(job)
    if gec is not None:
        checks.insert(-2, gec)
    return CommercialEvPacket(
        job=job, load=load, circuit=circuit,
        underground_conduit=conduit_size(circuit, "PVC") if job.trench_ft else None,
        interior_conduit=conduit_size(circuit, "EMT"), checks=checks, flags=_flags(job, load, circuit),
    )
