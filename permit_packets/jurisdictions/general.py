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
    "service_upgrade": Checklist(items=(
        Requirement("Permit application", "application"),
        Requirement("Site plan showing the meter and main panel", "site_plan"),
        Requirement("Riser diagram with service conductors, grounding and bonding", "one_line"),
        Requirement("Load calculation", "load"),
        Requirement("Panel and meter equipment specifications and listing", "equipment"),
        Requirement("Utility service request", "utility"),
    )),
    "subpanel": Checklist(items=(
        Requirement("Permit application", "application"),
        Requirement("Site plan showing the main panel, subpanel and feeder route", "site_plan"),
        Requirement("One-line diagram with feeder conductors, EGC and grounding", "one_line"),
        Requirement("Load calculation", "load"),
        Requirement("Panel specifications and listing", "equipment"),
    )),
    "appliance_circuit": Checklist(items=(
        Requirement("Permit application", "application"),
        Requirement("Site plan showing the panel and the appliance", "site_plan"),
        Requirement("One-line diagram with conductors, breaker and disconnect", "one_line"),
        Requirement("Load calculation", "load"),
        Requirement("Manufacturer specifications and listing", "equipment"),
    )),
}
