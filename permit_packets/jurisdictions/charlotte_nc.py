"""Charlotte, NC: Mecklenburg County Code Enforcement (LUESA) issues every building and trade
permit in the county, Charlotte included.

Code: the 2023 North Carolina Electrical Code (2023 NEC with NC amendments), mandatory
January 1, 2025. Stand-alone residential electrical work that needs no building permit or
plan review is permitted instantly online through Trade Internet Permitting (TIP) on the
contractor dashboard, with fees drawn from the contractor's County bond/trust account.
The county publishes no residential EV or service-upgrade checklist, so these items follow
what any reviewer or inspector asks of a stand-alone trade permit. Utility: Duke Energy.
"""
from __future__ import annotations

from permit_packets.jurisdictions import Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"
SERVICE_UPGRADE = "service_upgrade"

TIP_URL = "https://code.mecknc.gov/permitting/tip"
CODE_CHANGES_URL = "https://code.mecknc.gov/site-menu/code-change-central"
CODE_NOTE = (
    "Mecklenburg County enforces the 2023 North Carolina Electrical Code "
    "(2023 NEC with NC amendments), mandatory since January 1, 2025."
)
SOURCE_LABEL = "From Mecklenburg County Code Enforcement guidance"

NO_PUBLISHED_CHECKLIST = Note(
    "always",
    "Mecklenburg publishes no residential checklist for this work. Keep this packet in the job "
    "file for the inspector and any reviewer.",
)
NC_811 = Note("trench", "Call NC 811 at least 3 full working days before digging.")

CHARLOTTE = Jurisdiction(
    key="charlotte-nc", name="Charlotte", state="NC", known=True,
    department="Mecklenburg County Code Enforcement (LUESA)",
    phone="(980) 314-2633",
    website=TIP_URL,
    website_label="Trade Internet Permitting (TIP)",
    submit_how=(
        "Apply on the County contractor dashboard through Trade Internet Permitting (TIP): the "
        "permit issues instantly and the fee is drawn from the contractor's County bond/trust account. "
        "Request inspections from the same dashboard."
    ),
    needs_parcel_number=True,
    utility="Duke Energy",
    utility_short="Duke Energy",
    checklists={
        EV_CHARGER: Checklist(
            items=(
                Requirement("TIP stand-alone electrical permit: address/parcel, scope and valuation", "application"),
                Requirement("NC electrical contractor license and County bond/trust account", "application"),
                Requirement("Load calculation with the charger at 100% of its rating (NEC 220, 625.42)", "load"),
                Requirement("One-line diagram with breaker, conductors, conduit, and disconnect (if required)", "one_line"),
                Requirement("Charger data sheet and NRTL listing (UL 2594 / UL 2202)", "equipment"),
                Requirement("Site plan showing the panel, charger and route", "site_plan"),
            ),
            source_url=TIP_URL,
            source_label=SOURCE_LABEL,
            code_note=CODE_NOTE,
            notes=(
                NO_PUBLISHED_CHECKLIST,
                Note("always", "Commercial or multifamily EV work can trigger City of Charlotte zoning "
                     "review (CLTZR); a home charger does not."),
                Note("disconnect", "NEC 625.43: over 60 A or 150 V to ground, the disconnect must be "
                     "readily accessible and lockable open."),
                NC_811,
            ),
        ),
        SERVICE_UPGRADE: Checklist(
            items=(
                Requirement("TIP stand-alone electrical permit: address/parcel, scope, new service size and valuation", "application"),
                Requirement("NC electrical contractor license and County bond/trust account", "application"),
                Requirement("Load calculation", "load"),
                Requirement("Riser diagram with service conductors, grounding and bonding", "one_line"),
                Requirement("Panel and meter base specifications and listing", "equipment"),
                Requirement("Site plan showing the meter and main panel", "site_plan"),
                Requirement("Duke Energy service request and disconnect/reconnect scheduling", "utility"),
            ),
            source_url=CODE_CHANGES_URL,
            source_label=SOURCE_LABEL,
            code_note=CODE_NOTE,
            notes=(
                NO_PUBLISHED_CHECKLIST,
                Note("always", "2023 NEC 230.67: surge protection (SPD) is required on a dwelling service "
                     "that is replaced or upgraded."),
                Note("always", "2023 NEC 230.85: one- and two-family dwellings need an outdoor emergency "
                     "disconnect, readily accessible and marked."),
                Note("always", "Coordinate the meter pull, disconnect and reconnect with Duke Energy before "
                     "scheduling the work."),
            ),
        ),
    },
)
