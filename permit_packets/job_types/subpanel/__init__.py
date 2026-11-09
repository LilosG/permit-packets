"""Residential subpanel and feeder permits."""
from __future__ import annotations

from permit_packets.job_types import JobType, Marker
from permit_packets.job_types.subpanel.api import DOCUMENTS, FEATURE_PAGE, build_response
from permit_packets.job_types.subpanel.schema import SubpanelRequest

JOB_TYPE = JobType(
    key="subpanel",
    slug="subpanel",
    label="Subpanel / feeder",
    short_label="Subpanel",
    blurb="New subpanel with feeder sizing, voltage drop, load calc and site plan",
    icon="subpanel",
    markers=(
        Marker("panel", "Main panel", "P", "#15212c", "Tap the main panel"),
        Marker("subpanel", "Subpanel", "S", "#1f7a58", "Tap the subpanel"),
    ),
    route_between=("panel", "subpanel"),
    uses_home_loads=True,
    documents=DOCUMENTS,
    feature_page=FEATURE_PAGE,
    request_model=SubpanelRequest,
    build_response=build_response,
    zip_name="subpanel-permit-documents-demo.zip",
)
