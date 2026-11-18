"""Commercial subpanel and feeder permits: 3-phase or single-phase, for a building that is not a dwelling."""
from __future__ import annotations

from permit_packets.job_types import JobType, Marker
from permit_packets.job_types.commercial_subpanel.api import DOCUMENTS, FEATURE_PAGE, build_response
from permit_packets.job_types.commercial_subpanel.schema import CommercialSubpanelRequest

JOB_TYPE = JobType(
    key="commercial_subpanel",
    slug="commercial-subpanel",
    label="Panel / subpanel",
    short_label="Commercial subpanel",
    blurb="New 3-phase or single-phase subpanel with feeder sizing, voltage drop, service load and site plan",
    icon="subpanel",
    markers=(
        Marker("panel", "Main panel", "P", "#15212c", "Tap the main panel"),
        Marker("subpanel", "Subpanel", "S", "#1f7a58", "Tap the subpanel"),
    ),
    route_between=("panel", "subpanel"),
    uses_home_loads=False,
    documents=DOCUMENTS,
    feature_page=FEATURE_PAGE,
    request_model=CommercialSubpanelRequest,
    build_response=build_response,
    zip_name="commercial-subpanel-permit-documents.zip",
    occupancy="commercial",
)
