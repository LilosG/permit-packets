"""What each city asks for. Every entry comes from the city's own published checklist.

A new city is a new entry here, checked against its checklist and past approved
packets. Any other address gets the general checklist and says so.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Requirement:
    item: str
    section: str


@dataclass(frozen=True)
class Note:
    when: str  # always, disconnect or trench
    text: str


@dataclass(frozen=True)
class Jurisdiction:
    key: str
    name: str
    state: str
    known: bool
    checklist: tuple[Requirement, ...]
    code_name: str = "NEC"
    code_note: str = "Confirm the adopted code edition."
    department: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    website_label: str = ""
    submit_how: str = "Confirm how this city takes submittals."
    source_url: str = ""
    sets_required: int = 1
    needs_parcel_number: bool = False
    notes: tuple[Note, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.name}, {self.state}" if self.state else self.name


ORO_VALLEY = Jurisdiction(
    key="oro-valley-az", name="Oro Valley", state="AZ", known=True,
    department="Community and Economic Development, Permitting",
    phone="(520) 229-4800",
    email="permits@orovalleyaz.gov",
    website="https://www.orovalleyaz.gov/Government/Departments/Community-and-Economic-Development/Services/Customer-Portal",
    website_label="Oro Valley customer portal",
    submit_how="Email the PDFs to permits@orovalleyaz.gov, or bring hard copies to 11000 N. La Cañada Drive.",
    source_url="https://www.orovalleyaz.gov/files/assets/public/v/1/documents/community-and-economic-development/permitting-division/electric-car-charging-stations.pdf",
    code_note="The town's checklist cites the 2017 NEC. Confirm the edition in force.",
    sets_required=2,
    checklist=(
        Requirement("Completed building permit application, with Oro Valley business license and AZ registrar numbers", "application"),
        Requirement("Site plan showing the charger and main electrical panel", "site_plan"),
        Requirement("Charger design and UL listing information", "equipment"),
        Requirement("One-line diagram with conductors, conduit sizes and types, and overcurrent protection", "one_line"),
        Requirement("Load calculation for a new 240 V circuit", "load"),
        Requirement("Venting shown on the plans, if the charger requires it", "ventilation"),
        Requirement("HOA or subdivision rules", "hoa"),
    ),
    notes=(Note("always", "Hot climate: check the ambient temperature correction for conduit exposed to sun."),),
)

EL_CAJON = Jurisdiction(
    key="el-cajon-ca", name="El Cajon", state="CA", known=True,
    code_name="CEC",
    department="Community Development, Building Safety",
    phone="(619) 441-1726",
    website="https://elcajon.gov/your-government/departments/community-development/building-fire-safety-division/building-permits",
    website_label="El Cajon building permits",
    submit_how="The city's checklist doesn't say how to submit. Call Building Safety to confirm.",
    source_url="https://elcajon.gov/home/showpublisheddocument/26307/637914284204530000",
    code_note="The city's checklist cites the 2019 California Electrical Code. Confirm the edition in force.",
    needs_parcel_number=True,
    checklist=(
        Requirement("Permit application with address, parcel number, owner, contractor and license", "application"),
        Requirement("Charger model number, manufacturer specifications and installation guidelines", "equipment"),
        Requirement("Plug-In Electric Vehicle Load Calculator, with the charger at 100%", "load"),
        Requirement("Fully dimensioned site plan, drawn to scale, showing structures, the panel and the charger", "site_plan"),
        Requirement("Electrical plan with single-line diagram, conduit and conductor sizes", "one_line"),
        Requirement("NRTL listing mark on the charging equipment", "equipment"),
        Requirement("Mechanical plan, if indoor ventilation applies", "ventilation"),
    ),
    notes=(
        Note("disconnect", "El Cajon wants the disconnect readily accessible, in line of sight and within 50 ft of the charger."),
        Note("trench", "El Cajon wants trenching detailed on the plans, with 18 in minimum cover for direct burial."),
        Note("always", "Move the load figures onto El Cajon's own load calculator worksheet."),
    ),
)

KNOWN = {(j.name.lower(), j.state): j for j in (ORO_VALLEY, EL_CAJON)}

GENERAL_CHECKLIST = (
    Requirement("Permit application", "application"),
    Requirement("Site plan showing the charger and main panel", "site_plan"),
    Requirement("One-line diagram", "one_line"),
    Requirement("Load calculation", "load"),
    Requirement("Charger specifications and listing", "equipment"),
)


def jurisdiction_for(city: str | None, state: str | None) -> Jurisdiction:
    name = (city or "").strip()
    state = (state or "").strip().upper()
    known = KNOWN.get((name.lower(), state))
    if known:
        return known
    return Jurisdiction(
        key="general", name=name or "This area", state=state, known=False,
        checklist=GENERAL_CHECKLIST,
    )


def jurisdiction_by_key(key: str | None, city: str | None = None, state: str | None = None) -> Jurisdiction:
    for jurisdiction in KNOWN.values():
        if jurisdiction.key == key:
            return jurisdiction
    return jurisdiction_for(city, state)
