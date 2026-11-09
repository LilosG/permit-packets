"""Oro Valley, AZ: from the town's published checklists."""
from __future__ import annotations

from permit_packets.jurisdictions import Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"

ORO_VALLEY = Jurisdiction(
    key="oro-valley-az", name="Oro Valley", state="AZ", known=True,
    department="Community and Economic Development, Permitting",
    phone="(520) 229-4800",
    email="permits@orovalleyaz.gov",
    website="https://www.orovalleyaz.gov/Government/Departments/Community-and-Economic-Development/Services/Customer-Portal",
    website_label="Oro Valley customer portal",
    submit_how="Email the PDFs to permits@orovalleyaz.gov, or bring hard copies to 11000 N. La Cañada Drive.",
    sets_required=2,
    checklists={
        EV_CHARGER: Checklist(
            items=(
                Requirement("Completed building permit application, with Oro Valley business license and AZ registrar numbers", "application"),
                Requirement("Site plan showing the charger and main electrical panel", "site_plan"),
                Requirement("Charger design and UL listing information", "equipment"),
                Requirement("One-line diagram with conductors, conduit sizes and types, and overcurrent protection", "one_line"),
                Requirement("Load calculation for a new 240 V circuit", "load"),
                Requirement("Venting shown on the plans, if the charger requires it", "ventilation"),
                Requirement("HOA or subdivision rules", "hoa"),
            ),
            source_url="https://www.orovalleyaz.gov/files/assets/public/v/1/documents/community-and-economic-development/permitting-division/electric-car-charging-stations.pdf",
            code_note="The town's checklist cites the 2017 NEC. Confirm the edition in force.",
            notes=(Note("always", "Hot climate: check the ambient temperature correction for conduit exposed to sun."),),
        ),
    },
)
