"""Residential 240 V appliance circuit permits: hot tub, sauna, heat pump, mini-split and others."""
from __future__ import annotations

from permit_packets.job_types import JobType, Marker
from permit_packets.job_types.appliance_circuit.api import DOCUMENTS, FEATURE_PAGE, build_response
from permit_packets.job_types.appliance_circuit.schema import ApplianceCircuitRequest

JOB_TYPE = JobType(
    key="appliance_circuit",
    slug="appliance-circuit",
    label="240 V circuit",
    short_label="240 V",
    blurb="Hot tub, sauna, heat pump or mini-split circuit with load calc and site plan",
    icon="circuit",
    markers=(
        Marker("panel", "Main panel", "P", "#15212c", "Tap the main panel"),
        Marker("appliance", "Appliance", "A", "#1f7a58", "Tap the appliance"),
    ),
    route_between=("panel", "appliance"),
    uses_home_loads=True,
    documents=DOCUMENTS,
    feature_page=FEATURE_PAGE,
    request_model=ApplianceCircuitRequest,
    build_response=build_response,
    zip_name="appliance-circuit-permit-documents-demo.zip",
)
