"""Monte Sereno, CA: City of Monte Sereno Building Department, from its own handouts and municipal code, and PG&E.

Code: Monte Sereno Municipal Code Chapter 9.01 (Ord. NS-248, adopted November 18, 2025) adopts the 2025
California Electrical Code (Title 24, Part 3, based on the 2023 NEC) in its entirety. The chapter amends
the Building, Residential, Wildland-Urban Interface, Fire, Energy and Green Building codes, but not the
Electrical Code. The city's reach codes (rev. 1/2026: EV infrastructure and hot water recirculation) apply
to new construction only, not to additions, remodels or replacements.

What Monte Sereno publishes for these jobs: the Residential Electrical Vehicle Charger Installation handout
(rev. 1/2024) and the Residential Electrical Panel Replacement handout (rev. 1/2023). Both still cite the
2022 CEC; the requirements below that come from them are unchanged in the 2025 CEC sections they cite. EV
chargers and panel replacements are minor permits: online at epermits.montesereno.org or at City Hall, no
plans required unless noted. The panel handout's conductor, GEC and bonding tables stop at 200 A, so a
larger service is checked against the CEC tables directly. The city publishes no subpanel or 240 V circuit
handout, so those jobs use the general checklist with the city's code note.

Many Monte Sereno homes carry a Los Gatos mailing address (ZIP 95030): the permit area is the city limits,
so addresses count by where the Census places them, not by the city name in the address.

Utility: PG&E. Its Electric and Gas Service Requirements (Greenbook, TD-7001M, rev. 2026-04, effective June 22,
2026) set the Class 320 (400 A maximum, 320 A continuous) residential meter panel rules used for a 400 A
service.
"""
from __future__ import annotations

from permit_packets.jurisdictions import SURGE_PROTECTION, Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"
SERVICE_UPGRADE = "service_upgrade"

BUILDING_URL = "https://www.montesereno.org/2169/Building-Handouts"
EV_URL = "https://www.montesereno.org/DocumentCenter/View/4019/Electric-Vehicle-Charger-Installation"
PANEL_URL = "https://www.montesereno.org/DocumentCenter/View/3795/Electrical-Panel-Replacement"
APPLICATION_URL = "https://www.montesereno.org/DocumentCenter/View/4169/Building-Permit-Application"
REACH_CODES_URL = "https://www.montesereno.org/DocumentCenter/View/4360/Reach-Codes"
CODE_URL = ("https://gocodebook.com/library/us/ca/monte-sereno/title-9-buildings-and-construction/"
            "chapter-9.01-california-building-standards-code-1")
EPERMITS_URL = "https://epermits.montesereno.org/"
GREENBOOK_URL = "https://www.pge.com/assets/pge/docs/account/service-requests/greenbook-manual-full.pdf"
PGE_MATERIALS_URL = ("https://www.pge.com/assets/pge/docs/account/service-requests/"
                     "residential-panel-upgrade-material-list.pdf.coredownload.pdf")
# 2025 Reference Appendices (CEC-400-2025-010-AP), Joint Appendix JA2, Table 2-3: Los Gatos, the nearest listed
# location (Monte Sereno has no row). Cooling dry-bulb 0.5% 90 F, 1.0% 88 F, 2.0% 82 F.
DESIGN_TEMP_URL = "https://www.energy.ca.gov/sites/default/files/2025-07/CEC-400-2025-010-AP.pdf"

CODE_NOTE = (
    "Monte Sereno enforces the 2025 California Electrical Code (Title 24, Part 3, based on the 2023 NEC), adopted "
    "in its entirety with no local electrical amendments (Municipal Code 9.01.010, Ord. NS-248, November 18, 2025)."
)

APPLICATION = "application"

# Notes on every job
SMOKE_CO = Note(
    "always",
    "Monte Sereno: at the final inspection, give the inspector a completed Smoke Alarm and Carbon Monoxide Alarm "
    "Certification Form. Smoke alarms in each sleeping room, outside sleeping areas and on each story; CO alarms "
    "outside sleeping areas and on each story where the home has a fuel-burning appliance or an attached garage "
    "(CRC R314, R315).",
    PANEL_URL,
)
SUBMITTAL = Note(
    "always",
    "Monte Sereno: EV chargers and electrical panel replacements are minor permits, obtained online at "
    "epermits.montesereno.org or at City Hall (18041 Saratoga-Los Gatos Road). The handouts ask for 3 copies of each "
    "item for a counter submittal. A permit that goes to plan check is submitted online with the plans by file "
    "share link, the Building Permit Application and the plan check deposit.",
    BUILDING_URL,
)

# EV charger, from the Residential Electrical Vehicle Charger Installation handout (rev. 1/2024)
EV_CHECKLIST = Checklist(
    items=(
        Requirement("Building Permit Application, or the online EV Charger minor permit (epermits.montesereno.org)",
                    APPLICATION, EV_URL),
        Requirement("Electrical load calculation: the panel size, its existing load and the new charger circuit "
                    "(CEC 220)", "load", EV_URL),
        Requirement("Plan showing the charging equipment and every new or existing panel and subpanel",
                    "site_plan", EV_URL),
        Requirement("Charger listed by a nationally recognized testing laboratory (CEC 625.5; the handout cites "
                    "UL 2202, Level 2 wall chargers are listed to UL 2594)", "equipment", EV_URL),
        Requirement("Manufacturer's installation instructions", "equipment", EV_URL),
        Requirement("Indoors: charger labeled \"Ventilation Not Required\" where it stays visible (CEC 625.15)",
                    "ventilation", EV_URL),
    ),
    source_url=EV_URL,
    source_label="From Monte Sereno's Residential EV Charger Installation handout (rev. 1/2024)",
    code_note=CODE_NOTE,
    notes=(
        SUBMITTAL,
        Note("always", "Monte Sereno: one final inspection after all the work is complete.", EV_URL),
        SMOKE_CO,
        Note("indoor", "Monte Sereno: indoors, the charger's coupling (the connector) is stored 18 in to 48 in above "
             "the finished floor (CEC 625.50).", EV_URL),
        Note("outdoor", "Monte Sereno: outdoors, the charger's coupling (the connector) is stored 24 in to 48 in "
             "above finished grade (CEC 625.50).", EV_URL),
        Note("always", "Monte Sereno: where the charger can be hit by a vehicle, protect it with a barrier (CEC "
             "110.27), for example a 4 in concrete-filled steel pipe at least 40 in above the floor or grade, in a "
             "12 in diameter footing 3 ft deep.", EV_URL),
        Note("indoor", "Monte Sereno asks for a floor plan with the charger and the panels. The site plan marks "
             "both on the house; inside a garage, add a sketch of the garage wall with the charger and panel.",
             EV_URL),
    ),
)

# Panel / service upgrade, from the Residential Electrical Panel Replacement handout (rev. 1/2023) and PG&E
SERVICE_CHECKLIST = Checklist(
    items=(
        Requirement("Building Permit Application, or the online Electrical Panel Replacement minor permit "
                    "(epermits.montesereno.org)", APPLICATION, PANEL_URL),
        Requirement("Site plan showing the meter and the main panel", "site_plan", PANEL_URL),
        Requirement("Riser diagram: service conductors and conduit (1-1/4 in minimum), grounding electrode "
                    "conductor and bonding (CEC Article 230, 250.66)", "one_line", PANEL_URL),
        Requirement("Load calculation sizing the new service (CEC 220; the handout: a larger service is sized "
                    "from the actual load calculation)", "load", PANEL_URL),
        Requirement("Available fault current and the equipment interrupting rating (CEC 110.9, 110.10)",
                    "fault_current"),
        Requirement("Outdoor emergency disconnect for the one-family dwelling, marked (CEC 230.85)",
                    "emergency_disconnect"),
        SURGE_PROTECTION,
        Requirement("Service equipment specifications and listing", "equipment", PANEL_URL),
        Requirement("PG&E service application for the upgrade (Your Projects or 1-877-743-7782)", "utility",
                    GREENBOOK_URL),
    ),
    source_url=PANEL_URL,
    source_label="From Monte Sereno's Residential Electrical Panel Replacement handout (rev. 1/2023) and PG&E",
    code_note=CODE_NOTE,
    notes=(
        SUBMITTAL,
        Note("always", "Monte Sereno: two inspections. The utility release inspection, with the new panel in and the "
             "dead-front off (the inspector won't remove it), after which the inspector gives you the utility "
             "release form for PG&E; then the final. Stucco repairs need a wire lath inspection.", PANEL_URL),
        SMOKE_CO,
        Note("always", "Monte Sereno: the main service runs in rigid conduit. EMT is allowed where the service drop "
             "attaches to the building; service-entrance cable is allowed with approved fittings (a rain-tight "
             "service head or a taped or painted gooseneck). Service conduit 1-1/4 in minimum.", PANEL_URL),
        Note("always", "Monte Sereno: service drop conductors 3 ft above a roof sloped 4:12 or more (18 in where "
             "they enter through the overhang), 10 ft above ground, and 3 ft from doors and windows (CEC 230.24). "
             "Mark the neutral white at both terminals (200.6(B)).", PANEL_URL),
        Note("always", "Monte Sereno and PG&E: the meter is 48 in to 66 in above grade (PG&E's Greenbook Table 7-2 "
             "allows up to 75 in for a Class 320 panel), not on an exterior wall next to a bedroom or bedroom closet, "
             "and at least 36 in horizontally from the gas meter and piping. Breaker handles no higher than "
             "6 ft 7 in (CEC 240.24(A)); 30 in wide by 36 in deep working space with 6 ft 6 in headroom (110.26).",
             PANEL_URL),
        Note("always", "Monte Sereno: the grounding electrode conductor runs continuous from the panel to a ground rod "
             "and to the cold water pipe, bonded within the first 5 ft of water piping into the building; the water "
             "pipe needs the supplemental electrode. A rod is listed copper, at least 5/8 in diameter, with 8 ft in "
             "contact with soil, its top flush with grade or protected (CEC 250.52, 250.53, 250.64, 250.68(C)).",
             PANEL_URL),
        Note("always", "Monte Sereno: bond the hot, cold and gas lines at the water heater with a continuous jumper, "
             "and install an intersystem bonding termination outside the service or meter enclosure (CEC "
             "250.104, 250.94).", PANEL_URL),
        Note("always", "PG&E: an upgrade must meet every current Greenbook requirement, including clearances, and "
             "PG&E may need new service conductors at the applicant's cost (Greenbook Table 3-1). An "
             "underground-fed panel needs a cable termination compartment separate from the meter socket.",
             GREENBOOK_URL),
        Note("always", "PG&E, for a 400 A service: the meter panel is Class 320, marked \"320 Amperes Continuous\" or "
             "\"400 Amperes Maximum (320 Amperes Continuous)\", with a main breaker and test-bypass facilities "
             "for manual bypass links, for residential use only (Greenbook 7.1, 7.13). Underground, PG&E's "
             "Class 320 material list calls for 3 in conduit and 350 kcmil aluminum per phase with a 4/0 neutral.",
             PGE_MATERIALS_URL),
    ),
)

GENERAL_NOTES = (
    Note("always", "Monte Sereno publishes no handout for this job. This is the general CEC checklist; confirm "
         "with the Building Department whether it is a minor permit or goes to plan check.", BUILDING_URL),
    SMOKE_CO,
)

MONTE_SERENO = Jurisdiction(
    key="monte-sereno-ca", name="Monte Sereno", state="CA", known=True,
    # City Area extent from Santa Clara County GIS (basic/SCCCityLimits, layer 3), and its middle.
    bbox=(-122.0052, 37.2265, -121.9694, 37.2527), center=(-121.9873, 37.2396),
    permit_area_by_location=True,  # Los Gatos mailing addresses inside the city limits
    code_name="CEC",
    department="City of Monte Sereno Building Department",
    phone="(408) 354-7635",
    email="buildingdepartment@cityofmontesereno.org",
    website=EPERMITS_URL,
    website_label="Monte Sereno online permits",
    submit_how=(
        "Apply online at epermits.montesereno.org (EV Charger and Electrical Panel Replacement are minor "
        "permits), or at City Hall, 18041 Saratoga-Los Gatos Road. Schedule inspections online."
    ),
    needs_parcel_number=True,
    design_ambient_f=88,
    design_ambient_source=DESIGN_TEMP_URL,
    design_ambient_label="California Energy Code Joint Appendix JA2, Table 2-3, Los Gatos, 1.0% cooling dry-bulb",
    code_note=CODE_NOTE,
    min_service_raceway='1-1/4"',
    wiring_source=PANEL_URL,
    fallback_notes=GENERAL_NOTES,
    utility="Pacific Gas and Electric (PG&E)",
    utility_short="PG&E",
    checklists={EV_CHARGER: EV_CHECKLIST, SERVICE_UPGRADE: SERVICE_CHECKLIST},
)
