"""The fallback checklist for each job type, for cities not set up yet."""
from __future__ import annotations

from permit_packets.jurisdictions import SURGE_PROTECTION, Checklist, Note, Requirement

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
        SURGE_PROTECTION,
    ), notes=(
        # NEC 230.85, in the 2020 and 2023 NEC (every city here is on one of them).
        Note("always", "NEC 230.85: replacing the service equipment of a one- or two-family dwelling requires an "
                       "outdoor emergency disconnect, readily accessible and marked."),
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

# What a state adds to every permit in it, on top of a city's own checklist or the general one. A city
# that publishes no checklist gets the general NEC checklist plus the notes for its state.
STATE_AMENDMENTS: dict[str, tuple[Note, ...]] = {
    "CA": (
        Note("always", "California: permit work over $1,000 can trigger smoke and CO alarm requirements. "
                       "Confirm with the city."),
    ),
}
