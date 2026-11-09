"""Residential Level 2 EV charger permits."""
from __future__ import annotations

from permit_packets.job_types import JobType, Marker
from permit_packets.job_types.ev_charger.api import DOCUMENTS, FEATURE_PAGE, build_response
from permit_packets.job_types.ev_charger.schema import EvChargerRequest

JOB_TYPE = JobType(
    key="ev_charger",
    slug="ev-charger",
    label="EV charger",
    short_label="EV",
    blurb="Level 2 charger with load calc, one-line and site plan",
    icon="ev",
    markers=(
        Marker("panel", "Main panel", "P", "#15212c", "Tap the main panel"),
        Marker("charger", "Charger", "EV", "#c8682a", "Tap the charger"),
    ),
    route_between=("panel", "charger"),
    uses_home_loads=True,
    documents=DOCUMENTS,
    feature_page=FEATURE_PAGE,
    request_model=EvChargerRequest,
    build_response=build_response,
    zip_name="ev-permit-documents-demo.zip",
)
