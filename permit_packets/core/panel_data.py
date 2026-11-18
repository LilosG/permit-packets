"""What the one-line shows about the service and panel, and the checks that go with it."""
from __future__ import annotations

import re

from permit_packets.core.checks import Check
from permit_packets.core.conductors import gec_size as table_250_66_size
from permit_packets.core.conductors import service_conductor

MISSING_FAULT_CURRENT = "Enter the utility's available fault current"


def interrupting_rating_check(job) -> Check:
    """NEC 110.9 and 110.10: equipment must be rated to interrupt the fault current available at it."""
    fault = job.available_fault_current_a
    if not fault:
        return Check("Interrupting rating", MISSING_FAULT_CURRENT, False)
    rating = job.equipment_aic_ka * 1000
    if rating >= fault:
        return Check(
            "Interrupting rating",
            f"{job.equipment_aic_ka} kA ({rating:,} A) covers the {fault:,} A available (110.9, 110.10)", True)
    needed = -(-fault // 1000)
    return Check(
        "Interrupting rating",
        f"{job.equipment_aic_ka} kA ({rating:,} A) is below the {fault:,} A available: use equipment rated "
        f"{needed} kA or more (110.9, 110.10)", False)


# Smallest to largest, so a later size is the bigger wire.
SIZE_ORDER = ("14", "12", "10", "8", "6", "4", "3", "2", "1", "1/0", "2/0", "3/0", "4/0", "250", "300", "350", "400", "500", "600")
# NEC 250.66: the aluminum GEC that goes with each copper size.
ALUMINUM_FOR_COPPER = {"8": "6", "6": "4", "4": "2", "2": "1/0", "1/0": "3/0"}
GEC_FORMAT = "Enter it like #4 Cu"
_GEC = re.compile(r"^#?\s*(\d{1,3}(?:/0)?)\s*(?:awg|kcmil|mcm)?\s*(cu|copper|al|aluminum)?\.?$", re.I)


def parse_gec(text: str) -> tuple[str, str] | None:
    """(size, 'copper' or 'aluminum') from text like '#4 Cu', or None when it can't be read."""
    match = _GEC.match((text or "").strip())
    if not match or match.group(1) not in SIZE_ORDER:
        return None
    metal = (match.group(2) or "cu").lower()
    return match.group(1), "aluminum" if metal.startswith("al") else "copper"


def _label(size: str, material: str) -> str:
    return f"{'#' + size if int(size.split('/')[0]) < 250 else size + ' kcmil'} {'Al' if material == 'aluminum' else 'Cu'}"


def required_gec(service_amps: int, *, material: str = "copper", electrodes: tuple[str, ...] = ()) -> str | None:
    """The copper GEC NEC Table 250.66 asks for the service conductors, or None when the service is
    larger than this tool sizes. With the electrodes known, the largest any of them needs; the rod and
    concrete-encased limits only cut it down when every electrode has one."""
    try:
        conductor = service_conductor(service_amps, material)
        sizes = [table_250_66_size(conductor, material, electrode) for electrode in (electrodes or ("water_pipe",))]
    except ValueError:
        return None
    return max(sizes, key=SIZE_ORDER.index)


def gec_check(job, *, service_amps: int, material: str = "copper", electrodes: tuple[str, ...] = ()) -> Check | None:
    """The existing grounding electrode conductor against NEC Table 250.66, when one was entered."""
    if not job.gec_size:
        return None
    entered = parse_gec(job.gec_size)
    needed = required_gec(service_amps, material=material, electrodes=electrodes)
    if entered is None:
        return Check("Existing GEC", f"Can't read '{job.gec_size}'. {GEC_FORMAT}", False)
    if needed is None:
        return Check("Existing GEC", "This service is larger than the sizes this tool checks: verify against "
                     "Table 250.66 by hand", False)
    size, metal = entered
    minimum = needed if metal == "copper" else ALUMINUM_FOR_COPPER[needed]
    passed = SIZE_ORDER.index(size) >= SIZE_ORDER.index(minimum)
    required = _label(minimum, metal)
    if passed:
        return Check("Existing GEC", f"{_label(size, metal)}, meets {required} for a {service_amps} A service "
                     "(Table 250.66)", True)
    return Check("Existing GEC", f"{_label(size, metal)} is smaller than the {required} Table 250.66 requires "
                 f"for a {service_amps} A service", False)


def panel_flags(job, *, service_amps: int, material: str = "copper", electrodes: tuple[str, ...] = ()) -> list[str]:
    check = gec_check(job, service_amps=service_amps, material=material, electrodes=electrodes)
    flags = []
    if check is not None and not check.passed:
        flags.append(f"Existing grounding electrode conductor: {check.result}. Upsize it or replace it before submitting.")
    missing = [label for label, value in (
        ("location", job.panel_location), ("bus rating", panel_bus(job)), ("main type", job.panel_main),
        ("grounding electrode conductor size", job.gec_size)) if not value]
    if missing:
        flags.append("Enter the panel's " + ", ".join(missing) + " for the panel schedule and one-line.")
    return flags


def panel_bus(job) -> int | None:
    """The panel's bus rating: the form's field, or a service upgrade's own bus_amps."""
    return job.panel_bus_amps or getattr(job, "bus_amps", None)


def panel_header(job) -> list[tuple[str, str]]:
    """The panel details, label and value, for the panel schedule header and the one-line."""
    bus = panel_bus(job)
    return [
        ("Panel location", job.panel_location or "Not entered"),
        ("Bus rating", f"{bus} A" if bus else "Not entered"),
        ("Main", job.panel_main or "Not entered"),
        ("Existing GEC", job.gec_size or "Not entered"),
    ]


def one_line_data(job) -> list[str]:
    """The lines under the one-line diagram."""
    fault = job.available_fault_current_a
    details = dict(panel_header(job))
    return [
        f"Available fault current at the service: {f'{fault:,} A' if fault else 'not entered'}",
        f"Panel and breaker interrupting rating: {job.equipment_aic_ka} kA (NEC 110.9, 110.10)",
        f"Panel location: {details['Panel location']}",
        f"Panel bus rating: {details['Bus rating']}; main: {details['Main']}",
        f"Existing grounding electrode conductor: {details['Existing GEC']} (NEC 250.66)",
    ]


def checklist_row(job, section: str, page: int, *, burial: tuple[int, str] | None = None) -> tuple[str, str] | None:
    """The checklist row for the sections every packet's one-line covers, or None for any other section.

    `burial` is the page and line where a packet shows its underground cover (None: it shows none, so the row stays open).
    """
    if section == "fault_current":
        if not job.available_fault_current_a:
            return f"Page {page}: {MISSING_FAULT_CURRENT.lower()}", "Open"
        return (f"Page {page}: {job.available_fault_current_a:,} A available, "
                f"{job.equipment_aic_ka} kA equipment rating"), "Ready"
    if section == "panel_details":
        missing = [label for label, value in (
            ("location", job.panel_location), ("bus rating", panel_bus(job)), ("main type", job.panel_main)) if not value]
        if missing:
            return f"Page {page}: enter the panel's " + ", ".join(missing), "Open"
        return f"Page {page}: location, bus rating and main", "Ready"
    if section == "egc_size":
        return f"Page {page}: EGC size on the one-line", "Ready"
    if section == "burial":
        if not getattr(job, "trench_ft", 0):
            return "No underground run", "Ready"
        if burial is None:
            return "Not in this packet: add it by hand", "Open"
        return f"Page {burial[0]}: {burial[1]}", "Ready"
    return None
