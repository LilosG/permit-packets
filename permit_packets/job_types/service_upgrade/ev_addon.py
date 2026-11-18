"""An EV charger installed with a panel / service upgrade: its branch circuit, checks, flags and checklist rows.

The circuit is sized the way the EV charger packet sizes it (NEC 625.40, 625.42: 125% of the charger's
rating; 75 C conductors; 3% voltage drop), on the new panel the upgrade installs. The upgrade's load
calculation carries the charger at 100% of its rating (220.82(B)).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from permit_packets.core.checks import Check
from permit_packets.core.circuits import Circuit, conduit_size, size_circuit
from permit_packets.core.equipment import find_equipment

VOLTS = 240
HIGH_VOLTAGE_DROP_PERCENT = 3
DISCONNECT_REQUIRED_ABOVE_AMPS = 60  # NEC 625.43
LARGEST_RECEPTACLE_BREAKER = 50  # NEC 625.44(A): plug-in EVSE on receptacles up to 50 A
BURIAL_DEPTH_IN = 18

Location = Literal["attached_garage", "detached_garage", "exterior_wall"]
Connection = Literal["hardwired", "receptacle"]
LOCATION_LABELS = {
    "attached_garage": "in the attached garage",
    "detached_garage": "in the detached garage",
    "exterior_wall": "on the exterior wall",
}


@dataclass(frozen=True)
class EvAddOn:
    charger_model: str
    charger_amps: int
    run_ft: int
    location: Location = "attached_garage"
    connection: Connection = "hardwired"
    trench_ft: int = 0
    venting_required: bool | None = None

    @property
    def va(self) -> int:
        return self.charger_amps * VOLTS

    @property
    def outdoors(self) -> bool:
        return self.location == "exterior_wall" or self.trench_ft > 0


@dataclass(frozen=True)
class EvCircuit:
    addon: EvAddOn
    circuit: Circuit
    disconnect_amps: int | None
    interior_conduit: str
    underground_conduit: str | None
    panel_name: str  # the panel the breaker goes in

    @property
    def wire_text(self) -> str:
        return f"2 #{self.circuit.wire.size} Cu THWN-2 + 1 #{self.circuit.ground} Cu EGC"


def size_ev(addon: EvAddOn, ambient_f: int | None, panel_name: str) -> EvCircuit:
    circuit = size_circuit(addon.charger_amps, addon.run_ft, continuous=True, volts=VOLTS,
                           ambient_f=ambient_f if addon.outdoors else None)
    disconnect = (circuit.breaker if addon.location == "detached_garage"
                  or addon.charger_amps > DISCONNECT_REQUIRED_ABOVE_AMPS else None)
    return EvCircuit(
        addon=addon, circuit=circuit, disconnect_amps=disconnect,
        interior_conduit=conduit_size(circuit, "EMT"),
        underground_conduit=conduit_size(circuit, "PVC") if addon.trench_ft else None,
        panel_name=panel_name,
    )


def ev_checks(ev: EvCircuit) -> list[Check]:
    addon, circuit = ev.addon, ev.circuit
    charger = find_equipment(addon.charger_model, "charger")
    parts = [f"{circuit.breaker} A breaker in {ev.panel_name} for {addon.charger_amps} A x 125% (625.42)",
             f"#{circuit.wire.size} Cu, {circuit.wire.ampacity_75c} A at 75\N{DEGREE SIGN}C"]
    passed = circuit.breaker >= circuit.required_amps and circuit.wire.ampacity_75c >= circuit.breaker
    if charger is not None:
        parts.append(f"charger rated up to {charger.max_amps} A")
        passed = passed and charger.max_amps >= addon.charger_amps
    if circuit.heat:
        parts.append(f"{circuit.heat.corrected_a:.0f} A corrected for heat (310.15(B)(1))")
        passed = passed and circuit.heat.passed
    checks = [
        Check("EV circuit", "; ".join(parts), passed),
        Check("EV voltage drop", f"{circuit.voltage_drop_volts:.1f} V, or {circuit.voltage_drop_percent:.1f}%, over "
              f"{addon.run_ft} ft", circuit.voltage_drop_percent <= HIGH_VOLTAGE_DROP_PERCENT),
    ]
    if addon.connection == "receptacle":
        checks.append(Check(
            "EV connection",
            f"{circuit.breaker} A receptacle circuit" if circuit.breaker <= LARGEST_RECEPTACLE_BREAKER
            else f"A {addon.charger_amps} A charger must be hardwired",
            circuit.breaker <= LARGEST_RECEPTACLE_BREAKER))
    return checks


def ev_flags(ev: EvCircuit, jurisdiction) -> list[str]:
    addon, circuit = ev.addon, ev.circuit
    flags = []
    if circuit.upsized_for_voltage_drop:
        flags.append(f"EV wire was upsized to #{circuit.wire.size} AWG for voltage drop, so its equipment ground is "
                     f"#{circuit.ground} AWG to match (250.122(B)).")
    if addon.connection == "receptacle":
        flags.append("EV receptacles need GFCI protection. Confirm a listed GFCI breaker for this panel.")
    if not addon.charger_model:
        flags.append("Add the charger make and model, then attach its data sheet.")
    elif find_equipment(addon.charger_model, "charger") is None:
        flags.append(f"Attach the {addon.charger_model} data sheet and installation instructions behind the equipment "
                     "page. It isn't in the equipment library yet.")
    flags.append("EV wire sized at the 75\N{DEGREE SIGN}C column. Confirm the charger and breaker terminals are listed "
                 "and marked for 75\N{DEGREE SIGN}C, as most Level 2 chargers are (110.14(C)(1)(a)).")
    if ev.disconnect_amps:
        flags.append(f"Install a {ev.disconnect_amps} A disconnect for the charger, readily accessible and lockable "
                     "open; if it is out of sight of the charger, mark the charger with where it is (625.43).")
    if addon.trench_ft:
        flags.append("Call 811 before trenching and field verify the route.")
    if addon.location == "detached_garage":
        flags.append("Confirm grounding requirements at the detached garage.")
    checklist = jurisdiction.checklist_for("ev_charger")
    active = {"always", "outdoor" if addon.location == "exterior_wall" else "indoor"}
    active |= {"disconnect"} if ev.disconnect_amps else set()
    active |= {"trench"} if addon.trench_ft else set()
    # The EV handout's general notes (submittal, smoke alarms) repeat the service checklist's, so only
    # what is about the charger is added.
    service_notes = {note.text for note in jurisdiction.checklist_for("service_upgrade").notes}
    flags += [note.text for note in checklist.notes if note.when in active and note.text not in service_notes]
    return flags


def ev_requirement_rows(ev: EvCircuit, jurisdiction, *, pages: dict[str, int], plan) -> list[tuple[str, str, str]]:
    """The city's EV checklist lines, other than the application and load (the service checklist has them)."""
    addon = ev.addon
    rows = []
    for requirement in jurisdiction.checklist_for("ev_charger").items:
        section = requirement.section
        if section in ("application", "load"):
            continue
        item = f"EV charger: {requirement.item}"
        if section == "site_plan":
            if plan is None:
                rows.append((item, f"Page {pages['site_plan']}: schematic only, replace it", "Open"))
            elif "charger" in plan.markers:
                rows.append((item, f"Page {pages['site_plan']}: charger and panels marked on the plan", "Ready"))
            else:
                rows.append((item, f"Page {pages['site_plan']}: mark the charger on the plan", "Open"))
        elif section == "equipment":
            if find_equipment(addon.charger_model, "charger"):
                rows.append((item, f"Page {pages['equipment']} + manufacturer data sheet", "Ready"))
            else:
                rows.append((item, f"Page {pages['equipment']}: add manufacturer sheets", "Attach"))
        elif section == "ventilation":
            if addon.location == "exterior_wall":
                rows.append((item, "Not required: the charger is outdoors", "Ready"))
            elif addon.venting_required is None:
                rows.append((item, "Only if this charger requires venting", "Check"))
            elif addon.venting_required:
                rows.append((item, "Venting required: add the mechanical plan behind the riser", "Open"))
            else:
                rows.append((item, "Not required: the charger needs no venting (625.52)", "Ready"))
        elif section == "one_line":
            rows.append((item, f"Page {pages['one_line']}: EV circuit in the conductor schedule", "Ready"))
        elif section == "burial":
            rows.append((item, f"Page {pages['one_line']}: {BURIAL_DEPTH_IN} in minimum cover" if addon.trench_ft
                         else "No underground run", "Ready"))
        elif section in pages:
            rows.append((item, f"Page {pages[section]}", "Ready"))
        else:
            rows.append((item, "Not in this packet: add it by hand", "Open"))
    return rows


def ev_scope(ev: EvCircuit) -> str:
    addon, circuit = ev.addon, ev.circuit
    model = f" ({addon.charger_model})" if addon.charger_model else ""
    kind = "hardwired" if addon.connection == "hardwired" else "on a receptacle"
    run = (f"{ev.wire_text} in {ev.interior_conduit} EMT" if not addon.trench_ft else
           f"{ev.wire_text}, {addon.trench_ft} ft underground in {ev.underground_conduit} PVC, the rest in "
           f"{ev.interior_conduit} EMT")
    disconnect = (f" Install a {ev.disconnect_amps} A disconnect for the charger (625.43)." if ev.disconnect_amps
                  else "")
    return (f"Install one {addon.charger_amps} A, 240 V Level 2 EV charger{model}, {kind}, "
            f"{LOCATION_LABELS[addon.location]}, on a new {circuit.breaker} A, 2-pole breaker in {ev.panel_name}: "
            f"{run}, {addon.run_ft} ft.{disconnect}")
