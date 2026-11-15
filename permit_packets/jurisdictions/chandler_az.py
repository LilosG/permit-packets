"""Chandler, AZ: City of Chandler Development Services issues residential electrical permits through Citizen Access.

Code: the 2024 International Codes and the 2023 NEC, with Chandler amendments, for plans submitted on or
after July 1, 2025 (Building Safety page). Chandler's NEC amendments (Chapter 29, Article III) touch these
jobs in one place: 110.3(C), where listing may be by a recognized lab or an agency the Building Official
approves. The others (210.8 exceptions, 406.12) do not change what a packet shows.
Chandler publishes no EV charger, service upgrade, subpanel or 240 V circuit checklist. What it publishes
for all residential electrical work is the "Electrical Permits" section of its Homeowner Building Permit
Manual, so every checklist below carries that section's items plus the general NEC items, and says so.
Utility: SRP and APS both serve Chandler; the Engineering & Design Standards Manual has the boundary map.
Plan format (sheet size, PDF) comes from the city's electronic plan review instructions. Chandler
publishes no stamp box and no signature rule for these plans, so none is set.
"""
from __future__ import annotations

from permit_packets.jurisdictions import SURGE_PROTECTION, Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"
SERVICE_UPGRADE = "service_upgrade"
SUBPANEL = "subpanel"
APPLIANCE_CIRCUIT = "appliance_circuit"

SAFETY_URL = ("https://www.chandleraz.gov/government/departments/development-services/"
              "building-safety-plan-review-permits-and-inspections")
MANUAL_URL = ("https://www.chandleraz.gov/sites/default/files/departments/development-services/"
              "City-of-Chandler-Home-Owners-Building-Permit-Manual.pdf")
AMENDMENTS_URL = ("https://www.chandleraz.gov/sites/default/files/departments/development-services/"
                  "City-of-Chandler-Amendments-to-the-2024-International-Codes.pdf")
SUBMITTAL_URL = "https://www.chandleraz.gov/sites/default/files/City-of-Chandler-Full-Electronic-Submittal-Instructions-April-2023.pdf"
QUICK_TIPS_URL = "https://www.chandleraz.gov/sites/default/files/Quick-Tips-for-Electronic-Submittal.pdf"
PORTAL_URL = "https://aca-prod.accela.com/CHANDLER/"
STANDARDS_URL = ("https://www.chandleraz.gov/sites/default/files/departments/development-services/"
                 "City-of-Chandler-Engineering-Design-Standards-Manual.pdf")

CODE_NOTE = (
    "Chandler enforces the 2024 International Codes and the 2023 NEC with Chandler amendments, for plans "
    "submitted on or after July 1, 2025."
)
SOURCE_LABEL = "From the City of Chandler Homeowner Building Permit Manual and adopted code amendments"

# The manual's "Electrical Permits" section is the city's published list for residential electrical work.
APPLICATION = Requirement("Citizen Access permit application: address, permit type and job valuation", "application",
                          QUICK_TIPS_URL)
SITE_PLAN = Requirement("Plot (site) plan showing property lines, buildings on the lot and the electrical equipment",
                        "site_plan", MANUAL_URL)
LOAD = Requirement("Load calculation (Chandler: load calculations may be required)", "load", MANUAL_URL)
ONE_LINE = Requirement("Plans show the size and type of conductors, the size and type of conduit, burial depth "
                       "and the length of each run", "one_line", MANUAL_URL)
PANEL_SCHEDULE = Requirement("Panel schedule showing existing and new breakers, and the subpanel if one is added",
                             "panel_details", MANUAL_URL)
EQUIPMENT = Requirement("Equipment specifications and listing by a recognized testing laboratory or an agency "
                        "the Building Official approves (Chandler NEC 110.3(C))", "equipment", AMENDMENTS_URL)
GEC = Requirement("Grounding electrode conductor and electrode shown: 8 ft ground rod with acorn clamp and "
                  "solid #4 AWG bare copper, or a concrete-encased (Ufer) electrode", "gec", MANUAL_URL)

NO_CHECKLIST = ("Chandler publishes no {job} checklist. These items are the \"Electrical Permits\" section of its "
                "Homeowner Building Permit Manual, which covers all residential electrical work, plus the general "
                "NEC items.")  # the code note is its own flag (checklist.code_note)
UTILITY_CHECK = Note(
    "always",
    "SRP and APS both serve Chandler. Confirm the utility on the customer's bill; the city's Engineering & "
    "Design Standards Manual has the electrical services boundary map (Figure 5-A).",
    STANDARDS_URL,
)
LABELS = Note("always", "Chandler manual: breakers in the service panel must suit the dead front and be labeled in "
              "permanent ink.", MANUAL_URL)
LISTING = Note("always", "Chandler NEC 110.3(C): product listing is by a recognized qualified electrical testing "
               "laboratory or another agency the Chandler Building Official approves.", AMENDMENTS_URL)
FORMAT = Note(
    "always",
    "Chandler electronic plan review: one flattened PDF with no layers or editable text, under 95 MB (the "
    "Quick Tips sheet says 99 MB: stay under 95), sheets of one standard size from 8.5 x 11 up to 30 x 42, and "
    "a file name that starts with a descriptor such as \"Electrical\", not the job name. Chandler publishes no "
    "stamp box or signature rule for these plans.",
    SUBMITTAL_URL,
)
AZ_811 = Note(
    "trench",
    "Contact Arizona 811 at least two full working days before digging (811 or (602) 263-1100 in "
    "Maricopa County).",
)


def _fallback(job: str) -> Note:
    return Note("always", NO_CHECKLIST.format(job=job), MANUAL_URL)


CHANDLER = Jurisdiction(
    key="chandler-az", name="Chandler", state="AZ", known=True,
    bbox=(-111.9956, 33.204, -111.7554, 33.3613), center=(-111.8414, 33.3023),  # Mapbox place bounds (west, south, east, north) and (lon, lat)
    department="City of Chandler Development Services, Building Safety",
    phone="(480) 782-3000",
    email="prod@chandleraz.gov",
    website=PORTAL_URL,
    website_label="Chandler Citizen Access",
    submit_how=(
        "Register for Citizen Access, create the permit with only the permit type and job valuation, and upload "
        "the plans as a flattened PDF. Pay plan review fees when you submit. Plan Reviewer of the Day: "
        "(480) 782-3078, prod@chandleraz.gov."
    ),
    needs_parcel_number=True,
    sheet_size="letter",  # Chandler takes any standard size from 8.5 x 11 up to 30 x 42 for building plans
    # Same weather station as Mesa: ASHRAE 2% annual cooling dry-bulb design temperature, Phoenix Sky Harbor
    # (WMO 722780). 109 F lies between the 1% (110.2 F) and 2.5% (108.1 F) values published for the station.
    design_ambient_f=109,
    design_ambient_source=(
        "https://ashrae-meteo.info/v3.0/index.php?lat=33.44&lng=-111.99&place=%27%27&wmo=722780&ashrae_version=2017"
    ),
    code_note=CODE_NOTE,
    utility="SRP (Salt River Project) or APS, by address",
    utility_short="SRP/APS",
    checklists={
        EV_CHARGER: Checklist(
            items=(APPLICATION, SITE_PLAN, LOAD, ONE_LINE, PANEL_SCHEDULE, EQUIPMENT),
            source_url=MANUAL_URL,
            source_label=SOURCE_LABEL,
            code_note=CODE_NOTE,
            notes=(_fallback("EV charger"), LISTING, LABELS, UTILITY_CHECK, FORMAT, AZ_811),
        ),
        SERVICE_UPGRADE: Checklist(
            items=(
                APPLICATION, SITE_PLAN, LOAD, ONE_LINE, PANEL_SCHEDULE, EQUIPMENT, GEC,
                Requirement("Utility service request to SRP or APS", "utility"),
                SURGE_PROTECTION,
            ),
            source_url=MANUAL_URL,
            source_label=SOURCE_LABEL,
            code_note=CODE_NOTE,
            notes=(
                _fallback("service upgrade"),
                Note("always", "2023 NEC 230.85: replacing the service equipment of a one- or two-family dwelling "
                     "requires an outdoor emergency disconnect, readily accessible and marked."),
                Note("always", "Chandler manual: an overhead service needs its point of attachment on the "
                     "weatherhead mast. Homes with metal water or gas piping have bonding requirements that vary "
                     "by pipe location: ask the Chandler plan review counter.", MANUAL_URL),
                LISTING, LABELS, UTILITY_CHECK, FORMAT,
            ),
        ),
        SUBPANEL: Checklist(
            items=(APPLICATION, SITE_PLAN, LOAD, ONE_LINE, PANEL_SCHEDULE, EQUIPMENT),
            source_url=MANUAL_URL,
            source_label=SOURCE_LABEL,
            code_note=CODE_NOTE,
            notes=(
                _fallback("subpanel"),
                Note("always", "Subpanel: keep the neutral and ground bars separate and remove the bonding screw or "
                     "strap. The neutral is bonded only at the service disconnect (NEC 250.24(A)(5), 250.142(B))."),
                LISTING, LABELS, UTILITY_CHECK, FORMAT, AZ_811,
            ),
        ),
        APPLIANCE_CIRCUIT: Checklist(
            items=(APPLICATION, SITE_PLAN, LOAD, ONE_LINE, PANEL_SCHEDULE, EQUIPMENT),
            source_url=MANUAL_URL,
            source_label=SOURCE_LABEL,
            code_note=CODE_NOTE,
            notes=(
                _fallback("240 V appliance circuit"),
                Note("always", "Air conditioners, heat pumps and motor-driven appliances need a disconnect within "
                     "sight of the unit (NEC 440.14, 422.31)."),
                LISTING, LABELS, UTILITY_CHECK, FORMAT, AZ_811,
            ),
        ),
    },
)
