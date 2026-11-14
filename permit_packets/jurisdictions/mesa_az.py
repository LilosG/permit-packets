"""Mesa, AZ: City of Mesa Development Services issues residential electrical permits through DIMES.

Code: the 2024 I-Codes and the 2023 NEC with Mesa amendments (the "Mesa Electrical Code"),
for applications submitted on or after January 8, 2026. Mesa's amendments go past the base
NEC in three places that touch these jobs: EMT needs an additional equipment grounding
conductor (250.118(A)(4)), service disconnect labels must be engraved or raised and fastened
with screws or rivets (230.70(B)), and an EVSE over 60 A or 150 V to ground needs a lockable
disconnect 15 to 50 ft away with a plaque showing where it is (625.43).
Utility: SRP serves most of Mesa; downtown is Mesa Electric and parts of the city are APS.
"""
from __future__ import annotations

from permit_packets.jurisdictions import Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"
SERVICE_UPGRADE = "service_upgrade"

DIMES_URL = "https://aca-prod.accela.com/MESA/Default.aspx"
NEC_AMENDMENTS_URL = (
    "https://www.mesaaz.gov/files/assets/public/v/3/business-development/devsvcs/codeamendments/"
    "2023-nec-amendment.pdf"
)
CODE_NOTE = (
    "Mesa enforces the 2024 International Codes and the 2023 NEC with Mesa amendments "
    "(the Mesa Electrical Code), for applications submitted on or after January 8, 2026."
)
SOURCE_LABEL = "From City of Mesa Development Services and the Mesa Electrical Code"

UTILITY_CHECK = Note(
    "always",
    "SRP serves most of Mesa. Downtown Mesa is served by Mesa Electric and some areas by APS: "
    "confirm the utility on the customer's bill.",
)
AZ_811 = Note(
    "trench",
    "Contact Arizona 811 at least two full working days before digging (811 or (602) 263-1100 in "
    "Maricopa County).",
)

MESA = Jurisdiction(
    key="mesa-az", name="Mesa", state="AZ", known=True,
    department="City of Mesa Development Services, Building Safety",
    phone="(480) 644-4273",
    email="PermitServices@mesaaz.gov",
    website=DIMES_URL,
    website_label="DIMES (Mesa online permits)",
    submit_how=(
        "Apply in DIMES and upload every document as a PDF labeled Construction Documents, with the "
        "Contractor Licensure Verification Form. Pay fees, request inspections and print the approved "
        "set for the job site from the same DIMES record."
    ),
    needs_parcel_number=True,
    utility="SRP (Salt River Project)",
    utility_short="SRP",
    checklists={
        EV_CHARGER: Checklist(
            items=(
                Requirement("DIMES residential electrical permit: address/APN, scope and valuation", "application"),
                Requirement("Contractor Licensure Verification Form and Arizona ROC electrical license", "application"),
                Requirement("Load calculation with the charger at 100% of its rating (NEC 220, 625.42)", "load"),
                Requirement("One-line diagram with breaker, conductors, conduit and a separate EGC in EMT "
                            "(Mesa 250.118(A)(4))", "one_line"),
                Requirement("Charger data sheet and NRTL listing (UL 2594 / UL 2202)", "equipment"),
                Requirement("Site plan showing the panel, charger and route", "site_plan"),
            ),
            source_url=NEC_AMENDMENTS_URL,
            source_label=SOURCE_LABEL,
            code_note=CODE_NOTE,
            notes=(
                Note("always", "Mesa Electrical Code 250.118(A)(4): EMT counts as the equipment grounding "
                     "path only with an additional equipment grounding conductor pulled in it."),
                Note("disconnect", "Mesa Electrical Code 625.43: over 60 A or 150 V to ground, the EVSE "
                     "disconnect must be lockable open, 15 to 50 ft from the equipment, with a plaque on "
                     "the equipment showing where it is."),
                Note("always", "Mesa summers pass 115°F: apply the ambient temperature correction "
                     "(NEC 310.15(B)(1)) to conductors in conduit exposed to the sun."),
                UTILITY_CHECK,
                AZ_811,
            ),
        ),
        SERVICE_UPGRADE: Checklist(
            items=(
                Requirement("DIMES residential electrical permit: address/APN, scope, new service size and valuation", "application"),
                Requirement("Contractor Licensure Verification Form and Arizona ROC electrical license", "application"),
                Requirement("Load calculation", "load"),
                Requirement("Riser diagram with service conductors, grounding and bonding", "one_line"),
                Requirement("Panel and meter socket listing; meter socket per SRP Electric Service Specifications", "equipment"),
                Requirement("Site plan showing the meter and main panel", "site_plan"),
                Requirement("SRP service request; SRP reconnects after Mesa sends its clearance", "utility"),
            ),
            source_url=NEC_AMENDMENTS_URL,
            source_label=SOURCE_LABEL,
            code_note=CODE_NOTE,
            notes=(
                Note("always", "Mesa Electrical Code 230.70(B): service disconnect labels need engraved or "
                     "raised letters fastened with screws or rivets. Plastic tape labels are not accepted."),
                Note("always", "2023 NEC 230.67: surge protection (SPD) is required on a dwelling service "
                     "that is replaced or upgraded."),
                Note("always", "2023 NEC 230.85: one- and two-family dwellings need an outdoor emergency "
                     "disconnect, readily accessible and marked."),
                Note("always", "SRP reconnects only after Mesa passes the service inspection and sends its "
                     "clearance; SRP asks to allow three to four days for the clearance to process."),
                Note("always", "Mesa's Residential Utility Repair permit in DIMES lists installing a residential "
                     "200 A panel with no plan upload. Confirm with Permit Services that the scope fits it."),
                UTILITY_CHECK,
            ),
        ),
    },
)
