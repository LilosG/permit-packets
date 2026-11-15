"""Shared helpers: build a packet for any job type and read its pages."""
from __future__ import annotations

import json
from pathlib import Path

import pypdfium2

from permit_packets.core.equipment import attachment_span
from permit_packets.job_types import REGISTRY, PacketResult

from tests.test_ev_golden import GOLDEN, to_current_request

SAMPLES = Path(__file__).parent / "samples"
SAMPLE_FILES = {
    "ev_charger": "oro_valley_attached_no_plan", "service_upgrade": "service_upgrade", "subpanel": "subpanel",
    "appliance_circuit": "appliance_circuit",
}


def sample(key: str) -> dict:
    if key == "ev_charger":
        return to_current_request(json.loads((GOLDEN / "cases" / f"{SAMPLE_FILES[key]}.json").read_text()))
    return json.loads((SAMPLES / f"{SAMPLE_FILES[key]}.json").read_text())


def build(key: str, payload: dict) -> PacketResult:
    job_type = REGISTRY[key]
    return job_type.build_response(job_type.request_model.model_validate(payload))


def page_texts(pdf: bytes) -> list[str]:
    document = pypdfium2.PdfDocument(pdf)
    try:
        return [page.get_textpage().get_text_bounded() for page in document]
    finally:
        document.close()


def packet_pages(pdf: bytes) -> list[str]:
    """The text of every packet page, leaving out attached manufacturer data sheets."""
    texts = page_texts(pdf)
    span = attachment_span(pdf)
    if span:
        after, count = span
        return texts[:after] + texts[after + count:]
    return texts


def plan_for(key: str, scale: int = 30, parcel: str = "482-110-22-00") -> dict:
    """A to-scale plan with an aerial, lot and parcel number, marked the way each job type needs."""
    import base64
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (600, 600), "#8a9a7b").save(buffer, format="JPEG")
    markers = {
        "ev_charger": {"panel": [400, 500], "charger": [700, 300]},
        "service_upgrade": {"meter": [300, 500], "panel": [400, 500]},
        "subpanel": {"panel": [400, 500], "subpanel": [700, 300]},
        "appliance_circuit": {"panel": [400, 500], "appliance": [700, 300]},
    }[key]
    return {
        "scale_ft_per_in": scale, "markers": markers, "route": [[550, 500]],
        "buildings": [[[350, 350], [650, 350], [650, 650], [350, 650]]], "primary_building": 0,
        "lot": [[250, 250], [750, 250], [750, 750], [250, 750]], "parcel_number": parcel,
        "aerial_base64": base64.b64encode(buffer.getvalue()).decode(), "credits": ["Credit"],
    }


# Library models whose data sheets match the samples: a 200 A meter-main for the service upgrade (meter-main,
# 200 A, 200 A bus) and a 225 A main-lug load center for the subpanel (set to 225 A below).
LIBRARY_PANEL = "Milbank U5168-XTL-200 meter-main, 200 A"
LIBRARY_SUBPANEL = "Square D Homeline HOM3060L225PGC, 225 A main lug"


def complete_inputs(key: str, jurisdiction) -> dict:
    """Everything a packet can be asked: every field filled, a library charger or panel, the panel's
    existing circuits, the utility's fault current, a plan with a parcel number. In `jurisdiction`."""
    payload = {
        **sample(key),
        "jurisdiction_key": jurisdiction.key, "city": jurisdiction.name, "state": jurisdiction.state,
        "plan": plan_for(key, scale=jurisdiction.max_plan_scale_ft_per_in or 30),
        "existing_circuits": [{"label": "Kitchen counter", "amps": 20, "poles": 1},
                              {"label": "Range", "amps": 50, "poles": 2},
                              {"label": "Dryer", "amps": 30, "poles": 2}],
        "available_fault_current_a": 8_000, "equipment_aic_ka": 10,
        "panel_location": "Garage, east wall", "panel_main": "main breaker", "gec_size": "#4 Cu",
    }
    payload.pop("sheet_size", None)
    if key == "ev_charger":
        payload.update(charger_model="Tesla Wall Connector", charger_venting_required=False,
                       hoa_approval="not_required", panel_bus_amps=200)
    elif key == "service_upgrade":
        payload.update(panel_model=LIBRARY_PANEL, panel_bus_amps=payload["bus_amps"], surge_protection="type_2")
    elif key == "subpanel":
        payload.update(subpanel_model=LIBRARY_SUBPANEL, subpanel_amps=225, panel_bus_amps=200)
    else:
        payload.update(appliance_model="Sample Spa 4000", data_sheet_attached=True, panel_bus_amps=200)
    return payload
