"""Las Vegas, NV: City of Las Vegas Department of Building & Safety.

Code: the 2023 NEC with the Southern Nevada amendments. The city's Industry Notice says the codes take effect
January 5, 2026, and a project first submitted on or after that date is designed to them.
Plans go in online through the city's Dashboard, as one flattened, unlocked PDF per discipline, drawn to scale on a
standard sheet such as 11 x 17 (ePlan Requirements); zip files are not accepted.
The city's Online Permits List says what is issued without plans. An electric meter tag, panel change or service
change is on it. Minor electrical of 12 devices or less is on it, but not a dedicated circuit to a fixed appliance:
"Any other work not listed ... would require a plan to be submitted and reviewed." So the EV charger, subpanel and
240 V appliance circuit need plans, and the service upgrade does not.
Las Vegas publishes no EV charger, subpanel or appliance circuit checklist. What it publishes for electrical plans is
the Residential Submittal Requirements (1.7 B, additions and alterations) and the Electrical Plans Submittal Guideline
(items A to G), so every checklist below carries those items and says so.
Utility: NV Energy (Southern Nevada Electric Service Requirements).
"""
from __future__ import annotations

from permit_packets.jurisdictions import SURGE_PROTECTION, Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"
SERVICE_UPGRADE = "service_upgrade"
SUBPANEL = "subpanel"
APPLIANCE_CIRCUIT = "appliance_circuit"

RESIDENTIAL_URL = "https://files.lasvegasnevada.gov/building-safety/Residential-Submittal-Requirements.pdf"
GUIDELINE_URL = "https://files.lasvegasnevada.gov/building-safety/Forms/Residential/Residential-Submittal-Guideline.pdf"
ELECTRICAL_URL = "https://files.lasvegasnevada.gov/building-safety/2017-NEC-Electrical-Plan-Submittal-Requirements.pdf"
EPLAN_URL = "https://files.lasvegasnevada.gov/building-safety/ePlan-Requirements.pdf"
NOTICE_URL = "https://files.lasvegasnevada.gov/building-safety/2025/Industry_Notice-2024_Code_Adoption.pdf"
ONLINE_LIST_URL = "https://www.lasvegasnevada.gov/Business/Permits-Licenses/Online-Permits-List"
DASHBOARD_URL = "https://www.lasvegasnevada.gov/Dashboard"
ESR_URL = ("https://www.nvenergy.com/publish/content/dam/nvenergy/brochures_arch/account-services/"
           "building-and-new-construction/electric-service-standards-south/ESR-202106-EDITION.pdf")
WEATHER_URL = "https://www.ncei.noaa.gov/pub/access/cebrequests/engineeringwx/ICAO_KLAS_EWD_IP.pdf"

CODE_NOTE = (
    "Las Vegas enforces the 2023 NEC with the Southern Nevada amendments for projects first submitted on or "
    "after January 5, 2026."
)
SOURCE_LABEL = "From the City of Las Vegas residential submittal requirements and electrical plans guideline"

APPLICATION = Requirement("Residential permit application, filled out completely and submitted with the online "
                          "application", "application", GUIDELINE_URL)
SITE_PLAN = Requirement("Site plan showing property lines, existing and proposed structures and the electrical "
                        "equipment", "site_plan", GUIDELINE_URL)
SERVICE_AND_SUBPANELS = Requirement("Size and location of the existing and proposed electrical service and "
                                    "sub-panels", "panel_details", RESIDENTIAL_URL)
LOAD = Requirement("Service load calculation covering the old and new loads (not required when adding five or "
                   "fewer devices)", "load", RESIDENTIAL_URL)
ONE_LINE = Requirement("Single-line diagram with the AIC rating and incoming fault current at each breaker or fuse",
                       "one_line", ELECTRICAL_URL)
PANEL_SCHEDULE = Requirement("Panel schedule and circuit descriptions with connected loads, panel ratings and "
                             "feeder size", "panel_details", ELECTRICAL_URL)
VOLTAGE_DROP = Requirement("Voltage drop calculations for feeders to sub-panels", "feeder", ELECTRICAL_URL)

NO_CHECKLIST = ("Las Vegas publishes no {job} checklist. These items are from its Residential Submittal "
                "Requirements (additions and alterations) and its Electrical Plans Submittal Guideline.")
EDITION = Note(
    "always",
    "The city's electrical plans guideline is still titled 2017 NEC; the 2023 NEC governs the design.",
    NOTICE_URL,
)
FORMAT = Note(
    "always",
    "Las Vegas ePlan: submit online at the city's Dashboard as one PDF per discipline, on a standard sheet size "
    "such as 11 x 17 or 24 x 36, landscape and drawn to scale (export without \"fit to page\"). No password-protected "
    "or locked PDFs, and no zip files.",
    EPLAN_URL,
)
UTILITY = Note(
    "always",
    "NV Energy serves Las Vegas. Its Southern Nevada Electric Service Requirements cover meter panels and service "
    "locations.",
    ESR_URL,
)
NO_PLANS_SERVICE = Note(
    "always",
    "Las Vegas issues an electric meter tag, panel change or service change online without plans, and asks you to "
    "schedule a 231 inspection for a service change. These drawings are not required for that permit.",
    ONLINE_LIST_URL,
)
PLANS_REQUIRED = Note(
    "always",
    "Las Vegas issues minor electrical online without plans only for 12 devices or less, and not for a dedicated "
    "circuit to a fixed appliance. Any other work needs plans submitted and reviewed.",
    ONLINE_LIST_URL,
)
CALL_811 = Note("trench", "Call 811 before digging.")


def _fallback(job: str) -> Note:
    return Note("always", NO_CHECKLIST.format(job=job), RESIDENTIAL_URL)


LAS_VEGAS = Jurisdiction(
    key="las-vegas-nv", name="Las Vegas", state="NV", known=True,
    # Approximate extent of the city (west, south, east, north) and (lon, lat), used only to keep address suggestions
    # near Las Vegas; the permit area still comes from the address.
    bbox=(-115.37, 35.99, -114.99, 36.35), center=(-115.1398, 36.1699),
    department="City of Las Vegas Department of Building & Safety",
    phone="(702) 229-6251",
    email="techs@lasvegasnevada.gov",
    website=DASHBOARD_URL,
    website_label="Las Vegas Dashboard",
    submit_how=(
        "Create an account at the city's Dashboard (lasvegasnevada.gov/dashboard), choose Building Permits with "
        "Plans, and upload the PDF. Plan review comments are at lasvegasnevada.gov/CheckStatus and fees at "
        "lasvegasnevada.gov/PayPermit."
    ),
    needs_parcel_number=False,
    sheet_size="tabloid",  # the ePlan page names 11 x 17 and 24 x 36; 11 x 17 prints on one sheet of paper
    single_pdf_only=True,  # one PDF per discipline, no zip files
    # NOAA Engineering Weather Data, McCarran Intl (KLAS): 1.0% dry-bulb design temperature. The packet's conductor
    # correction normally uses the 2% value, which this page does not list, so the hotter 1% value is used.
    design_ambient_f=107,
    design_ambient_source=WEATHER_URL,
    design_ambient_label="NOAA Engineering Weather Data, McCarran Intl, 1.0% dry-bulb",
    code_note=CODE_NOTE,
    utility="NV Energy",
    utility_short="NV Energy",
    checklists={
        EV_CHARGER: Checklist(
            items=(APPLICATION, SITE_PLAN, SERVICE_AND_SUBPANELS, LOAD, ONE_LINE, PANEL_SCHEDULE),
            source_url=RESIDENTIAL_URL, source_label=SOURCE_LABEL, code_note=CODE_NOTE,
            notes=(_fallback("EV charger"), PLANS_REQUIRED, EDITION, FORMAT, UTILITY, CALL_811),
        ),
        SERVICE_UPGRADE: Checklist(
            items=(
                APPLICATION, SERVICE_AND_SUBPANELS, LOAD, ONE_LINE, PANEL_SCHEDULE,
                Requirement("Utility service request to NV Energy", "utility"),
                SURGE_PROTECTION,
            ),
            source_url=RESIDENTIAL_URL, source_label=SOURCE_LABEL, code_note=CODE_NOTE,
            notes=(
                _fallback("service upgrade"), NO_PLANS_SERVICE, EDITION, FORMAT, UTILITY,
                Note("always", "2023 NEC 230.85: replacing the service equipment of a one- or two-family dwelling "
                     "requires an outdoor emergency disconnect, readily accessible and marked."),
            ),
        ),
        SUBPANEL: Checklist(
            items=(APPLICATION, SITE_PLAN, SERVICE_AND_SUBPANELS, LOAD, ONE_LINE, PANEL_SCHEDULE, VOLTAGE_DROP),
            source_url=RESIDENTIAL_URL, source_label=SOURCE_LABEL, code_note=CODE_NOTE,
            notes=(
                _fallback("subpanel"), PLANS_REQUIRED, EDITION, FORMAT, UTILITY,
                Note("always", "Subpanel: keep the neutral and ground bars separate and remove the bonding screw or "
                     "strap. The neutral is bonded only at the service disconnect (NEC 250.24(A)(5), 250.142(B))."),
                CALL_811,
            ),
        ),
        APPLIANCE_CIRCUIT: Checklist(
            items=(APPLICATION, SITE_PLAN, SERVICE_AND_SUBPANELS, LOAD, ONE_LINE, PANEL_SCHEDULE),
            source_url=RESIDENTIAL_URL, source_label=SOURCE_LABEL, code_note=CODE_NOTE,
            notes=(
                _fallback("240 V appliance circuit"), PLANS_REQUIRED, EDITION, FORMAT, UTILITY,
                Note("always", "Air conditioners, heat pumps and motor-driven appliances need a disconnect within "
                     "sight of the unit (NEC 440.14, 422.31)."),
                CALL_811,
            ),
        ),
    },
)
