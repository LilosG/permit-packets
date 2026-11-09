"""The fallback checklist for each job type, for cities not set up yet."""
from __future__ import annotations

from permit_packets.jurisdictions import Checklist, Requirement

GENERAL_CHECKLISTS: dict[str, Checklist] = {
    "ev_charger": Checklist(items=(
        Requirement("Permit application", "application"),
        Requirement("Site plan showing the charger and main panel", "site_plan"),
        Requirement("One-line diagram", "one_line"),
        Requirement("Load calculation", "load"),
        Requirement("Charger specifications and listing", "equipment"),
    )),
}
