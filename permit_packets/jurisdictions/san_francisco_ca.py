"""San Francisco, CA: from DBI Information Sheet E-02 (Electric Vehicle Charging Station Checklist).

Code: the 2025 San Francisco Electrical Code, which is the 2025 California Electrical Code
(the 2023 NEC with California amendments) plus San Francisco amendments, operative
January 1, 2026. Registered contractors apply online through PermitSF; DBI issues an
electrical trade permit for an EV charger instantly. Utility is PG&E.
"""
from __future__ import annotations

from permit_packets.jurisdictions import Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"

E02_URL = "https://sfmta.com/media/36888/download"
CODE_NOTE = (
    "San Francisco enforces the 2025 San Francisco Electrical Code: the 2025 California "
    "Electrical Code (2023 NEC base) with local amendments, operative January 1, 2026."
)

SAN_FRANCISCO = Jurisdiction(
    key="san-francisco-ca", name="San Francisco", state="CA", known=True,
    code_name="CEC",
    department="Department of Building Inspection (DBI), Permit Services",
    phone="(628) 652-3720",
    website="https://sf.gov/apply-electrical-permit",
    website_label="DBI electrical permits (PermitSF)",
    submit_how=(
        "A DBI-registered contractor applies online through PermitSF. DBI issues an electrical trade "
        "permit for an EV charger instantly. Have the work inspected before covering wiring."
    ),
    needs_parcel_number=True,
    utility="Pacific Gas and Electric (PG&E)",
    utility_short="PG&E",
    checklists={
        EV_CHARGER: Checklist(
            items=(
                Requirement("Application: address, block/lot, owner, contractor, license number and phone", "application"),
                Requirement("Existing load, electrical service and equipment documented", "load"),
                Requirement("Load calculation (CEC 220), unless the registered contractor verifies one charger fits the panel", "load"),
                Requirement("One-line diagram: charger, panel, raceway, wire types and sizes, main breaker and service voltage", "one_line"),
                Requirement("Site plan, approximately to scale: panel, meter and charger", "site_plan"),
                Requirement("Charger manufacturer specifications and installation guidelines", "equipment"),
                Requirement("NRTL listing mark on all equipment (UL 2594 / UL 2202)", "equipment"),
                Requirement("Mechanical ventilation, only if the manufacturer requires it", "ventilation"),
            ),
            source_url=E02_URL,
            source_label="From DBI Information Sheet E-02",
            code_note=CODE_NOTE,
            notes=(
                Note("always", "Mount the connector holster 18 to 48 in above the floor indoors, or 24 to 48 in "
                     "above grade outdoors (CEC 625.50)."),
                Note("always", "Equipment must be permanently connected and fastened in place per the "
                     "manufacturer's instructions (DBI E-02)."),
                Note("disconnect", "DBI E-02: over 60 A or 150 V to ground, the disconnect must be readily "
                     "accessible, within sight of and within 50 ft of the charger, and lockable open (CEC 625.43)."),
                Note("trench", "Trenching per CEC 300.5: call USA North 811 at least 2 working days before digging."),
            ),
        ),
    },
)
