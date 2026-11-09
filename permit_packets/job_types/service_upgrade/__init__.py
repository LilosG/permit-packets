"""Residential panel and service upgrade permits."""
from __future__ import annotations

from permit_packets.job_types import JobType, Marker
from permit_packets.job_types.service_upgrade.api import DOCUMENTS, FEATURE_PAGE, build_response
from permit_packets.job_types.service_upgrade.schema import ServiceUpgradeRequest

JOB_TYPE = JobType(
    key="service_upgrade",
    slug="service-upgrade",
    label="Panel / service upgrade",
    short_label="Service",
    blurb="Service or panel replacement with load calc, riser diagram and utility request",
    icon="panel",
    markers=(
        Marker("meter", "Meter", "M", "#566572", "Tap the meter"),
        Marker("panel", "Main panel", "P", "#15212c", "Tap the main panel (same spot for a meter-main combo)"),
    ),
    route_between=("meter", "panel"),
    uses_home_loads=True,
    documents=DOCUMENTS,
    feature_page=FEATURE_PAGE,
    request_model=ServiceUpgradeRequest,
    build_response=build_response,
    zip_name="service-upgrade-permit-documents-demo.zip",
)
