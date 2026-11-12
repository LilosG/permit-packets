"""Nashville, TN (Metro Nashville-Davidson County): from Metro Codes' published guidance.

Metro does not publish a residential EV charger checklist. These items follow what
Metro Codes publishes for electrical submittals (its PV permit page asks for an
electrical diagram, spec sheets and a to-scale site plan), the ePermits user guide,
and the code list adopted by BL2025-898. Electric utility is Nashville Electric
Service (NES), which approves service work separately.
"""
from __future__ import annotations

from permit_packets.jurisdictions import Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"
SERVICE_UPGRADE = "service_upgrade"

ADOPTED_CODES_URL = "https://www.nashville.gov/departments/codes/codes-administration/adopted-codes-list"
EPERMITS_GUIDE_URL = "https://filetransfer.nashville.gov/Portals/0/SiteContent/Codes/docs/ePermitsUserGuide.pdf"
CODE_NOTE = "Metro Nashville enforces the 2023 NEC with local amendments (BL2025-898). Confirm amendments with Metro Codes."

LISTED_CONDUIT = Note(
    "always",
    "Metro Codes inspectors are rejecting unlisted PVC. Use conduit bearing an approved listing stamp.",
)
NO_PUBLISHED_EV_CHECKLIST = Note(
    "always",
    "Metro has no published residential EV checklist. Keep this packet in the job file and attach "
    "it in ePermits if the reviewer asks.",
)

NASHVILLE = Jurisdiction(
    key="nashville-tn", name="Nashville", state="TN", known=True,
    department="Metro Codes and Building Safety, Permit Issuance",
    phone="(615) 862-6517",
    email="permitissuance@nashville.gov",
    website="https://epermits.nashville.gov",
    website_label="Metro Nashville ePermits",
    submit_how=(
        "Apply in ePermits as a standalone electrical permit (not under a building permit), "
        "using the contractor's Metro-registered account. Schedule inspections in ePermits or at (615) 862-6560."
    ),
    needs_parcel_number=True,
    checklists={
        EV_CHARGER: Checklist(
            items=(
                Requirement("ePermits electrical application: address/parcel, scope, contract value and quantities", "application"),
                Requirement("Tennessee contractor license and Metro Codes electrical registration", "application"),
                Requirement("Load calculation with the charger at 100% of its rating (NEC 220, 625.42)", "load"),
                Requirement("One-line diagram with breaker, conductors, conduit and disconnect", "one_line"),
                Requirement("Charger data sheet and NRTL listing (UL 2594 / UL 2202)", "equipment"),
                Requirement("Site plan showing the panel, charger and route", "site_plan"),
            ),
            source_url=EPERMITS_GUIDE_URL,
            source_label="From Metro Codes' published guidance",
            code_note=CODE_NOTE,
            notes=(
                NO_PUBLISHED_EV_CHECKLIST,
                LISTED_CONDUIT,
                Note("disconnect", "NEC 625.43: the disconnect must be readily accessible and lockable open."),
                Note("trench", "Call Tennessee 811 at least 3 working days before trenching."),
            ),
        ),
        SERVICE_UPGRADE: Checklist(
            items=(
                Requirement("ePermits electrical application: address/parcel, scope, contract value and quantities", "application"),
                Requirement("Tennessee contractor license and Metro Codes electrical registration", "application"),
                Requirement("Load calculation", "load"),
                Requirement("Riser diagram with service conductors, grounding and bonding", "one_line"),
                Requirement("Panel and meter base specifications and listing", "equipment"),
                Requirement("Site plan showing the meter and main panel", "site_plan"),
                Requirement("Nashville Electric Service (NES) service request and disconnect/reconnect scheduling", "utility"),
            ),
            source_url=ADOPTED_CODES_URL,
            source_label="From Metro Codes' published guidance",
            code_note=CODE_NOTE,
            notes=(
                LISTED_CONDUIT,
                Note("always", "Build the meter base and service to NES Electric Service Guidelines (current version) and confirm with NES."),
            ),
        ),
    },
)
