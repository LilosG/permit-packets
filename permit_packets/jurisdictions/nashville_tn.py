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
CODE_NOTE = "Metro Nashville enforces the 2023 NEC with local amendments in Metro Code 16.20.150 (BL2025-898)."
AMENDMENTS_URL = "https://nashville.legistar.com/gateway.aspx?m=l&id=/matter.aspx?key=19170"

LISTED_CONDUIT = Note(
    "always",
    "Metro Codes inspectors are rejecting unlisted PVC. Use conduit bearing an approved listing stamp.",
)
TORQUE = Note(
    "always",
    "Metro amendment to 110.14(D): use a calibrated torque tool on specified terminations, and mark "
    "service and feeder terminations after torquing, before inspection.",
)
POWER_FOR_FINAL = Note("always", "Metro amendment to 110.12: power must be on at the building for the final inspection.")
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
                TORQUE,
                POWER_FOR_FINAL,
                Note("disconnect", "Metro's amended 625.43: EVSE over 60 A or 150 V to ground needs a readily "
                     "accessible disconnect, lockable open. One- and two-family dwellings need no separate emergency disconnect."),
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
                TORQUE,
                POWER_FOR_FINAL,
                Note("always", "Metro amendment to 230.1: NES sets the meter base location."),
                Note("always", "Metro amendment to 230.70(A)(1): the main disconnect must be within 5 ft of where "
                     "the service conductors leave the meter base."),
                Note("always", "Metro amendment to 230.43: service entrance conductors in conduit on brick, stone, "
                     "masonry or metal walls."),
                Note("always", "Metro amendment to 250.50: bond all grounding electrodes; a concrete-encased "
                     "electrode must be visible at the service inspection where reachable."),
                Note("always", "Build the meter base and service to NES Electric Service Guidelines (current version) and confirm with NES."),
            ),
        ),
    },
)
