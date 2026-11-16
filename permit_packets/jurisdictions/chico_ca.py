"""Chico, CA: City of Chico Community Development Department, Building Division.

Code: California adopts the 2025 California Electrical Code (Title 24, Part 3, based on the 2023 NEC),
effective January 1, 2026. Chico's Forms page lists the 2025 CEC Part 3; Chico's own amendments, if any, are
not published with its forms, so the code note tells the electrician to confirm them.
Chico publishes no commercial EV charger or subpanel checklist, and no electrical plan checklist at all. What it
does publish for electrical work: the eTRAKiT online permit types (Electrical Commercial, with the subtypes EV Car
Charging Station, Additional Electrical Main and Electrical Permit Not Classified), the Digital Plan Submittal page,
and an Electric Service Questionnaire (form 71) that lists what a service or panel project's site plan shows and
says load calculations may be required. Every checklist below is that material plus the general NEC items for the
job, and says so. The EV checklist also follows the items California's expedited EV charging permit process
(Government Code 65850.7) asks for.
Utility: Pacific Gas & Electric serves Chico (listed on the Building Division page).
Plan format: Chico publishes no sheet size or scale for electrical plans, so none is set.
"""
from __future__ import annotations

from permit_packets.jurisdictions import SURGE_PROTECTION, Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"
SERVICE_UPGRADE = "service_upgrade"
SUBPANEL = "subpanel"
APPLIANCE_CIRCUIT = "appliance_circuit"
COMMERCIAL_SUBPANEL = "commercial_subpanel"
COMMERCIAL_EV_CHARGER = "commercial_ev_charger"

BUILDING_URL = "https://chicoca.gov/Departments/Community-Development/Building-Division/"
FORMS_URL = "https://chicoca.gov/Departments/Community-Development/Building-Division/Forms-Handouts-and-Policies/"
ETRAKIT_URL = "https://chicoca.gov/Departments/Community-Development/eTRAKiT-Help-and-Resources/"
PERMITS_ONLINE_URL = "https://chico.ca.us/__catapult_pages/9841b45d-4814-4071-91c1-f2dadb8f0387/Permits-Online.html"
DIGITAL_URL = "https://chico.ca.us/Departments/Community-Development/Building-Division/Digital-Plan-Submittal/index.html"

RESIDENTIAL_SOURCE_LABEL = ("Chico publishes no residential {job} checklist: its Electric Service Questionnaire and "
                            "online permit types, plus the general NEC items")


def _application_residential(subtype: str) -> Requirement:
    return Requirement(
        f"Permit application: eTRAKiT online permit, type Electrical Residential, {subtype}, or the application at "
        "the Permit Counter", "application", PERMITS_ONLINE_URL)


CODE_NOTE = (
    "California enforces the 2025 California Electrical Code (Title 24, Part 3, based on the 2023 NEC), effective "
    "January 1, 2026. Confirm any Chico amendments with the Building Division."
)
SOURCE_LABEL = ("Chico publishes no commercial {job} checklist: its Electric Service Questionnaire and online permit "
                "types, plus the general NEC items")

APPLICATION = Requirement(
    "Permit application: eTRAKiT online permit, type Electrical Commercial, or the application at the Permit Counter",
    "application", PERMITS_ONLINE_URL)
SITE_PLAN_SUBPANEL = Requirement(
    "Site plan showing the property, the buildings and the main panel, subpanel and feeder route",
    "site_plan", FORMS_URL)
SITE_PLAN_EV = Requirement(
    "Site plan showing the property, the buildings, the electrical panel and the EV charging spaces",
    "site_plan", FORMS_URL)
ONE_LINE_SUBPANEL = Requirement("One-line diagram with the feeder conductors, EGC and grounding", "one_line")
ONE_LINE_EV = Requirement(
    "One-line diagram with the charger circuit, breaker, conductors and any disconnect (CEC 625.43)", "one_line")
LOAD = Requirement(
    "Load calculation (Chico: load calculations may be required for a service or panel project)", "load", FORMS_URL)
LOAD_EV = Requirement(
    "Load calculation showing whether the service or panel needs an upgrade for the chargers (CEC Article 220)",
    "load", FORMS_URL)
FAULT_CURRENT = Requirement(
    "Available fault current and the panel and breaker interrupting rating (CEC 110.9, 110.10)", "fault_current")
EQUIPMENT = Requirement("Panel specifications and listing", "equipment")
EQUIPMENT_EV = Requirement("Charger make, model, rating and listing (CEC 625.5)", "equipment")
ACCESSIBILITY = Requirement(
    "Accessible charging space shown on the site plan (California Building Code Chapter 11B)", "accessibility")
BURIAL = Requirement("Trench and conduit cover shown (CEC 300.5)", "burial")

SUBMITTAL = Note(
    "always",
    "Chico takes applications, plans and documents in digital format: apply through eTRAKiT, or use Digital Plan "
    "Submittal (PDF or Word files, with the permit application on a first submittal). Plan check correspondence is "
    "sent by email.",
    DIGITAL_URL,
)
UTILITY = Note("always", "Pacific Gas & Electric serves Chico: 1-800-743-5000.", BUILDING_URL)
SERVICE_QUESTIONNAIRE = Note(
    "always",
    "Chico's Electric Service Questionnaire (form 71) also asks the site plan to show easements, dimensions to "
    "property lines, the street name, a north arrow, and the service and meter locations. Add what the plan lacks, "
    "and a floor plan for interior work.",
    FORMS_URL,
)
EV_FRAMEWORK = Note(
    "always",
    "Chico publishes no EV charging checklist or forms on its site. California Government Code 65850.7 requires an "
    "expedited, checklist-based EV charging permit process, so this checklist follows the items that process asks "
    "for. Confirm them with the Building Division.",
)

PANEL_SCHEDULE = Requirement("Panel schedule with the panel's existing and new circuits (NEC 408.4)", "panel_details")
SITE_PLAN_HOME = Requirement(
    "Site plan showing the property, the buildings and the electrical equipment", "site_plan", FORMS_URL)
LOAD_HOME = Requirement(
    "Load calculation (Chico: load calculations may be required for a service or panel project)", "load", FORMS_URL)
ONE_LINE_HOME = Requirement("One-line diagram with conductors, breaker and grounding", "one_line")


def _residential(job: str, application: Requirement, *extra: Requirement, trench: bool = False) -> Checklist:
    items = (application, SITE_PLAN_HOME, ONE_LINE_HOME, LOAD_HOME, FAULT_CURRENT, PANEL_SCHEDULE, *extra)
    if trench:
        items += (BURIAL,)
    return Checklist(items=items, source_url=FORMS_URL, source_label=RESIDENTIAL_SOURCE_LABEL.format(job=job),
                     code_note=CODE_NOTE, notes=(SUBMITTAL, UTILITY, SERVICE_QUESTIONNAIRE))


CHICO = Jurisdiction(
    key="chico-ca", name="Chico", state="CA", known=True,
    # Approximate extent of the city (west, south, east, north) and (lon, lat), used only to keep address suggestions
    # near Chico; the permit area still comes from the address.
    bbox=(-121.92, 39.67, -121.74, 39.81), center=(-121.8375, 39.7285),
    department="City of Chico Community Development Department, Building Division",
    phone="(530) 879-6700",
    website="https://chicoca.gov/eTRAKiT",
    website_label="Chico eTRAKiT",
    submit_how=(
        "Apply through eTRAKiT (permit type Electrical Commercial) or use Digital Plan Submittal on the Building "
        "Division page, attaching the permit application on a first submittal. The Permit Counter is at the Chico "
        "Municipal Building, 411 Main Street, 2nd Floor."
    ),
    needs_parcel_number=False,
    code_note=CODE_NOTE,
    utility="Pacific Gas & Electric",
    utility_short="PG&E",
    checklists={
        EV_CHARGER: _residential(
            "EV charger", _application_residential("subtype EV Car Charging Station"), trench=True),
        SERVICE_UPGRADE: _residential(
            "service upgrade", _application_residential("subtype Upgrade Electrical Main"),
            Requirement("Utility service request to PG&E", "utility"), SURGE_PROTECTION),
        SUBPANEL: _residential(
            "subpanel", _application_residential("with the subtype that fits (Chico's list has no subpanel subtype: "
                                                 "ask the Building Division)"), trench=True),
        APPLIANCE_CIRCUIT: _residential(
            "240 V appliance circuit",
            _application_residential("subtype New Wiring Circuit, or Spa Single Outlet for a spa")),
        COMMERCIAL_SUBPANEL: Checklist(
            items=(APPLICATION, SITE_PLAN_SUBPANEL, ONE_LINE_SUBPANEL, LOAD, FAULT_CURRENT, EQUIPMENT, BURIAL),
            source_url=FORMS_URL, source_label=SOURCE_LABEL.format(job="subpanel"), code_note=CODE_NOTE,
            notes=(SUBMITTAL, UTILITY, SERVICE_QUESTIONNAIRE),
        ),
        COMMERCIAL_EV_CHARGER: Checklist(
            items=(APPLICATION, SITE_PLAN_EV, ONE_LINE_EV, LOAD_EV, FAULT_CURRENT, EQUIPMENT_EV, ACCESSIBILITY, BURIAL),
            source_url=ETRAKIT_URL, source_label=SOURCE_LABEL.format(job="EV charger"), code_note=CODE_NOTE,
            notes=(EV_FRAMEWORK, SUBMITTAL, UTILITY, SERVICE_QUESTIONNAIRE),
        ),
    },
)
