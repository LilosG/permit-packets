"""Local amendments to the NEC wiring methods: which raceway a run is actually drawn in.

Most cities enforce the NEC wiring methods as published, so the electrician's choice stands.
San Francisco amends them (SFEC 230.43, 352.10, 340.10): service-entrance conductors go in RMC or IMC
above ground, PVC stays underground or in concrete, and no cable type is allowed for a 240 V circuit
outdoors. Where the choice is not allowed, the packet draws the method the city allows and says why.
"""
from __future__ import annotations

from dataclasses import dataclass

from permit_packets.jurisdictions import Jurisdiction


@dataclass(frozen=True)
class Raceway:
    kind: str  # "PVC", "EMT", "RMC", "IMC" or "cable"
    note: str | None = None  # why the drawn method differs from the one chosen


def service_raceway(jurisdiction: Jurisdiction, chosen: str) -> Raceway:
    """Service-entrance conductors from the meter to the main, above ground. `chosen` may be "none" (cable)."""
    allowed = jurisdiction.service_raceways
    if not allowed:
        return Raceway("cable" if chosen == "none" else chosen)
    if chosen in allowed:
        return Raceway(chosen)
    minimum = f", {jurisdiction.min_service_raceway} minimum" if jurisdiction.min_service_raceway else ""
    return Raceway(allowed[0], (
        f"{jurisdiction.name} allows only {' or '.join(allowed)} above ground for service-entrance conductors "
        f"(local amendments to 230.43 and 352.10), so the service conductors are drawn in "
        f"{allowed[0]}{minimum}."))


def above_ground(jurisdiction: Jurisdiction, chosen: str, what: str) -> Raceway:
    """A feeder or branch circuit above ground. `what` names the run in the note, e.g. "feeder"."""
    if chosen == "PVC" and jurisdiction.pvc_underground_only:
        return Raceway("EMT", (
            f"{jurisdiction.name} allows PVC only underground or in concrete (local amendment to 352.10), so the "
            f"above-ground {what} is drawn in EMT."))
    return Raceway(chosen)


def outdoor_cable(jurisdiction: Jurisdiction, chosen: str, outdoors: bool) -> Raceway:
    """A 240 V branch circuit the electrician wants in cable."""
    if chosen == "cable" and outdoors and not jurisdiction.cable_outdoors:
        return Raceway("EMT", (
            f"{jurisdiction.name} allows no cable type for a 240 V circuit outdoors (UF only at 50 V or less, "
            "local amendment to 340.10; NM is not for wet locations), so the circuit is drawn in EMT."))
    return Raceway(chosen)
