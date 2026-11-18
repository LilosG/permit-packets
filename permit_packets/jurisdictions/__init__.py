"""What each city asks for. Every entry comes from the city's own published checklist.

A city carries one checklist per job type it has been set up for. A new city is
a new module here, checked against its checklists and past approved packets.
Any other address, or a job type a city has no checklist for, gets the general
checklist and says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

DEFAULT_CODE_NOTE = "Confirm the adopted code edition."
# Job types for a building that is not a dwelling. State amendments written for dwellings don't apply to them.
COMMERCIAL_JOB_TYPES = ("commercial_subpanel", "commercial_ev_charger")


@dataclass(frozen=True)
class Requirement:
    item: str
    section: str
    source: str = ""  # URL of the page or form this item comes from


# NEC 230.67 (2020 NEC and later, so every city here): a dwelling service that is replaced or upgraded gets a
# Type 1 or Type 2 surge protective device. A city's own checklist may carry a sourced copy of it instead.
SURGE_PROTECTION = Requirement(
    "Surge protective device, Type 1 or Type 2, shown on the riser (NEC 230.67)", "surge")


@dataclass(frozen=True)
class Note:
    when: str  # always, disconnect, trench, indoor or outdoor (EV charger location)
    text: str
    source: str = ""  # URL of the page or form this note comes from


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
    # City limits box (west, south, east, north) and center (lon, lat), used to keep address suggestions in the city.
    bbox: tuple[float, float, float, float] | None = None
    center: tuple[float, float] | None = None
    # True where the permit area is not the city's name: addresses count when the Census places their coordinates
    # in this jurisdiction (Nashville: all of Davidson County except the satellite cities with their own offices).
    permit_area_by_location: bool = False
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
    sheet_size: str = "letter"  # "tabloid" for 11" x 17" sheets; "ansi_d" for a 22" x 34" drawing set
    # The largest site plan scale the city accepts, in feet per inch as drawn on letter. None: any.
    max_plan_scale_ft_per_in: int | None = None
    # Side, in inches, of the empty square the city reserves for its stamp on the cover sheet.
    stamp_box_in: float | None = None
    # (width, height) in inches of the empty area the city reserves on the title sheet for agency stamps.
    # Drawn beside the stamp box on the cover when it fits, else on a blank sheet at the end of the packet.
    title_sheet_blank_area_in: tuple[float, float] | None = None
    # True where the city takes one combined PDF and refuses plan sheets uploaded as separate files.
    single_pdf_only: bool = False
    # ASHRAE 2% annual cooling dry-bulb design temperature (F) for the station nearest the city. Outdoor
    # and sun-exposed conductors are corrected for it (NEC 310.15(B)(1)). None: not set up for this city.
    design_ambient_f: int | None = None
    design_ambient_source: str = ""  # where that figure comes from, a URL
    # What that figure is, as printed on the packet after "Design ambient NN F (NN C):".
    design_ambient_label: str = "ASHRAE 2% annual cooling dry-bulb"
    # True where the house outline is drawn over the aerial: only where outlines were measured to sit on the
    # county parcels (tools/measure_alignment.py) and tree cover hides roofs in the photo.
    outline_over_aerial: bool = False
    # Where the utility publishes the meter sockets and meter-main combos it accepts: their catalog numbers and
    # the list's URL. A service upgrade with a meter-main then has to name one of them. None: not checked.
    approved_meter_mains: tuple[str, ...] | None = None
    approved_meter_mains_source: str = ""
    # What this city enforces, for job types it publishes no checklist for (they use the general one).
    code_note: str = ""
    # Local amendments to the NEC wiring methods. Empty or False: the NEC as published.
    service_raceways: tuple[str, ...] = ()  # raceways allowed above ground for service-entrance conductors
    min_service_raceway: str = ""  # smallest raceway for service-entrance conductors, e.g. '1-1/4"'
    pvc_underground_only: bool = False  # PVC only underground or in concrete; metal raceway above ground
    cable_outdoors: bool = True  # False where no cable type is allowed for a 240 V circuit outdoors
    wiring_source: str = ""  # URL of the amendments behind the four fields above
    # Local service rules. None or empty: the NEC as published.
    max_meter_to_main_ft: int | None = None  # main disconnect within this distance of where conductors enter
    concrete_encased_note: str = ""  # shown when a service upgrade has no concrete-encased electrode
    afci_note: str = ""  # replaces the general AFCI flag on a service upgrade
    fallback_notes: tuple[Note, ...] = ()
    checklists: dict[str, Checklist] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.name}, {self.state}" if self.state else self.name

    def checklist_for(self, job_type: str) -> Checklist:
        """This city's checklist for the job type, else the general NEC one, plus the state's amendments."""
        base = self.checklists.get(job_type)
        if base is None:
            base = GENERAL_CHECKLISTS[job_type]
            if self.known and (self.code_note or self.fallback_notes):
                base = replace(
                    base,
                    source_label="General NEC checklist (the city publishes none for this job)",
                    code_note=self.code_note or base.code_note,
                    notes=base.notes + (Note(
                        "always",
                        f"{self.name} publishes no {job_type.replace('_', ' ')} checklist. This is the general NEC "
                        "checklist."  # the code note is its own flag (checklist.code_note), so it is not repeated here
                    ),) + self.fallback_notes,
                )
        amendments = () if job_type in COMMERCIAL_JOB_TYPES else STATE_AMENDMENTS.get(self.state, ())
        added = tuple(note for note in amendments if note not in base.notes)
        return replace(base, notes=base.notes + added) if added else base

    def known_for(self, job_type: str) -> bool:
        """True only when this city's own checklist covers the job type."""
        return self.known and job_type in self.checklists


# The city modules import the classes above, so they come after them.
from permit_packets.jurisdictions.bellevue_wa import BELLEVUE  # noqa: E402
from permit_packets.jurisdictions.chandler_az import CHANDLER  # noqa: E402
from permit_packets.jurisdictions.chico_ca import CHICO  # noqa: E402
from permit_packets.jurisdictions.charlotte_nc import CHARLOTTE  # noqa: E402
from permit_packets.jurisdictions.el_cajon_ca import EL_CAJON  # noqa: E402
from permit_packets.jurisdictions.general import GENERAL_CHECKLISTS, STATE_AMENDMENTS  # noqa: E402
from permit_packets.jurisdictions.las_vegas_nv import LAS_VEGAS  # noqa: E402
from permit_packets.jurisdictions.mesa_az import MESA  # noqa: E402
from permit_packets.jurisdictions.monte_sereno_ca import MONTE_SERENO  # noqa: E402
from permit_packets.jurisdictions.nashville_tn import NASHVILLE  # noqa: E402
from permit_packets.jurisdictions.oro_valley_az import ORO_VALLEY  # noqa: E402
from permit_packets.jurisdictions.san_francisco_ca import SAN_FRANCISCO  # noqa: E402

KNOWN = {(j.name.lower(), j.state): j for j in (ORO_VALLEY, EL_CAJON, NASHVILLE, SAN_FRANCISCO, CHARLOTTE, MESA, CHANDLER, BELLEVUE, LAS_VEGAS, CHICO, MONTE_SERENO)}


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
        "single_pdf_only": jurisdiction.single_pdf_only,
        "sheet_size": jurisdiction.sheet_size,
        "label": jurisdiction.label,
        "checklist": [requirement.item for requirement in checklist.items],
    }
