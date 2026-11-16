"""Commercial Level 2 EV charger permits: one or many chargers on a commercial building's service."""
from __future__ import annotations

from permit_packets.job_types import JobType, Marker
from permit_packets.job_types.commercial_ev.api import DOCUMENTS, FEATURE_PAGE, build_response
from permit_packets.job_types.commercial_ev.schema import CommercialEvRequest

JOB_TYPE = JobType(
    key="commercial_ev_charger",
    slug="commercial-ev-charger",
    label="EV charger",
    short_label="Commercial EV charger",
    blurb="Level 2 chargers for a commercial building: circuits, service load, load management and site plan",
    icon="ev",
    markers=(
        Marker("panel", "Electrical panel", "P", "#15212c", "Tap the electrical panel"),
        Marker("charger", "EV chargers", "C", "#1f7a58", "Tap the charging spaces"),
    ),
    route_between=("panel", "charger"),
    uses_home_loads=False,
    documents=DOCUMENTS,
    feature_page=FEATURE_PAGE,
    request_model=CommercialEvRequest,
    build_response=build_response,
    zip_name="commercial-ev-charger-permit-documents-demo.zip",
    occupancy="commercial",
)
