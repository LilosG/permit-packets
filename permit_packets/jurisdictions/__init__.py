"""What each city asks for. Every entry comes from the city's own published checklist.

A city carries one checklist per job type it has been set up for. A new city is
a new module here, checked against its checklists and past approved packets.
Any other address, or a job type a city has no checklist for, gets the general
checklist and says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CODE_NOTE = "Confirm the adopted code edition."


@dataclass(frozen=True)
class Requirement:
    item: str
    section: str


@dataclass(frozen=True)
class Note:
    when: str  # always, disconnect or trench
    text: str


@dataclass(frozen=True)
class Checklist:
    items: tuple[Requirement, ...]
    source_url: str = ""
    code_note: str = DEFAULT_CODE_NOTE
    notes: tuple[Note, ...] = ()
    source_label: str = "From the city's published checklist"


@dataclass(frozen=True)
class Jurisdiction:
    key: str
    name: str
    state: str
    known: bool
    code_name: str = "NEC"
    department: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    website_label: str = ""
    submit_how: str = "Confirm how this city takes submittals."
    sets_required: int = 1
    needs_parcel_number: bool = False
    utility: str = ""
    utility_short: str = ""
    checklists: dict[str, Checklist] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.name}, {self.state}" if self.state else self.name

    def checklist_for(self, job_type: str) -> Checklist:
        """This city's checklist for the job type, else the general one."""
        return self.checklists.get(job_type) or GENERAL_CHECKLISTS[job_type]

    def known_for(self, job_type: str) -> bool:
        """True only when this city's own checklist covers the job type."""
        return self.known and job_type in self.checklists


# The city modules import the classes above, so they come after them.
from permit_packets.jurisdictions.el_cajon_ca import EL_CAJON  # noqa: E402
from permit_packets.jurisdictions.general import GENERAL_CHECKLISTS  # noqa: E402
from permit_packets.jurisdictions.nashville_tn import NASHVILLE  # noqa: E402
from permit_packets.jurisdictions.oro_valley_az import ORO_VALLEY  # noqa: E402

KNOWN = {(j.name.lower(), j.state): j for j in (ORO_VALLEY, EL_CAJON, NASHVILLE)}


def jurisdiction_for(city: str | None, state: str | None) -> Jurisdiction:
    name = (city or "").strip()
    state = (state or "").strip().upper()
    known = KNOWN.get((name.lower(), state))
    if known:
        return known
    return Jurisdiction(key="general", name=name or "This area", state=state, known=False)


def jurisdiction_by_key(key: str | None, city: str | None = None, state: str | None = None) -> Jurisdiction:
    for jurisdiction in KNOWN.values():
        if jurisdiction.key == key:
            return jurisdiction
    return jurisdiction_for(city, state)


def jurisdiction_json(jurisdiction: Jurisdiction, job_type: str) -> dict:
    """What the page needs to know about a city, for one job type."""
    checklist = jurisdiction.checklist_for(job_type)
    return {
        "key": jurisdiction.key,
        "name": jurisdiction.name,
        "state": jurisdiction.state,
        "known": jurisdiction.known_for(job_type),
        "code_name": jurisdiction.code_name,
        "code_note": checklist.code_note,
        "department": jurisdiction.department,
        "phone": jurisdiction.phone,
        "email": jurisdiction.email,
        "website": jurisdiction.website,
        "website_label": jurisdiction.website_label,
        "submit_how": jurisdiction.submit_how,
        "source_url": checklist.source_url,
        "sets_required": jurisdiction.sets_required,
        "needs_parcel_number": jurisdiction.needs_parcel_number,
        "label": jurisdiction.label,
        "checklist": [requirement.item for requirement in checklist.items],
    }
