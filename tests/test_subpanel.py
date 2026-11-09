"""Subpanel / feeder permits: the feeder math, the checks, the flags, the PDF and the routes."""
from __future__ import annotations

import base64
import json
import os
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pypdfium2
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import app

from permit_packets.core.checks import Check
from permit_packets.core.conductors import (
    ALUMINUM_K,
    COPPER_K,
    EGC_TABLE,
    feeder_conductor,
    feeder_conduit,
    feeder_voltage_drop,
    size_feeder,
)
from permit_packets.job_types import REGISTRY
from permit_packets.jurisdictions import ORO_VALLEY, jurisdiction_json

os.environ["DEMO_PASSWORD"] = "test-password"

SAMPLE = json.loads((Path(__file__).parent / "samples" / "subpanel.json").read_text())
PACKET_URL = "/api/jobs/subpanel/packet"
DOCUMENTS_URL = "/api/jobs/subpanel/documents"
STEMS = [
    "01-checklist-and-checks", "02-permit-application-data", "03-site-plan", "04-one-line-diagram",
    "05-feeder-schedule", "06-load-calculation", "07-equipment-data", "08-pre-submittal-review",
]
SQUARE_LOT = [[250, 250], [750, 250], [750, 750], [250, 750]]


@pytest.fixture
def client() -> TestClient:
    signed_in = TestClient(app)
    assert signed_in.post("/api/signin", json={"password": "test-password"}).status_code == 200
    return signed_in


def _payload(**changes) -> dict:
    return {**SAMPLE, **changes}


def _packet(client, **changes) -> dict:
    response = client.post(PACKET_URL, json=_payload(**changes))
    assert response.status_code == 200, response.text
    return response.json()


def _text(body: dict) -> str:
    document = pypdfium2.PdfDocument(base64.b64decode(body["pdf"]))
    try:
        return re.sub(r"\s+", " ", " ".join(page.get_textpage().get_text_bounded() for page in document))
    finally:
        document.close()


def _aerial() -> str:
    buffer = BytesIO()
    Image.new("RGB", (600, 600), "#8a9a7b").save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def _plan(**markers) -> dict:
    return {
        "scale_ft_per_in": 30, "markers": markers or {"panel": [500, 500], "subpanel": [600, 600]},
        "lot": SQUARE_LOT, "parcel_number": "13831614010", "aerial_base64": _aerial(), "credits": ["Credit"],
    }


def _checks(body: dict) -> dict:
    return {check["name"]: check for check in body["checks"]}


def test_check_moved_to_core_keeps_its_fields():
    from permit_packets.job_types.service_upgrade.calc import Check as ServiceCheck

    assert ServiceCheck is Check
    assert Check("Name", "Result", True) == Check(name="Name", result="Result", passed=True)


def test_the_egc_table_and_the_k_constants():
    assert EGC_TABLE[0] == (15, "14", "12")
    assert EGC_TABLE[-1] == (400, "3", "1")
    assert (COPPER_K, ALUMINUM_K) == (12.9, 21.2)


@pytest.mark.parametrize("breaker, copper, aluminum", [
    (60, "6", "4"), (100, "3", "1"), (125, "1", "2/0"), (150, "1/0", "3/0"), (200, "3/0", "250"),
])
def test_feeder_conductor_is_the_smallest_that_carries_the_breaker(breaker, copper, aluminum):
    assert feeder_conductor(breaker, "copper").size == copper
    assert feeder_conductor(breaker, "aluminum").size == aluminum


def test_a_whole_dwelling_feeder_takes_the_83_percent_rule():
    # 310.12: 200 A x 83% = 166 A, so 2/0 copper (175 A) and 4/0 aluminum (180 A) are enough.
    assert feeder_conductor(200, "copper", whole_dwelling=True).size == "2/0"
    assert feeder_conductor(200, "aluminum", whole_dwelling=True).size == "4/0"


def test_voltage_drop_uses_each_metals_constant():
    copper = feeder_conductor(100, "copper")
    volts, percent = feeder_voltage_drop(80, 150, copper, "copper")
    assert volts == pytest.approx(2 * 12.9 * 80 * 150 / 52620)
    assert percent == pytest.approx(volts / 240 * 100)
    aluminum_volts, _ = feeder_voltage_drop(80, 150, copper, "aluminum")
    assert aluminum_volts == pytest.approx(volts * 21.2 / 12.9)


def test_a_short_copper_feeder_is_not_upsized():
    feeder = size_feeder(100, "copper", 80, 150)
    assert (feeder.conductor.size, feeder.egc, feeder.upsized) == ("3", "8", False)
    assert feeder.vd_percent == pytest.approx(2.45, abs=0.01)


def test_a_long_copper_feeder_is_upsized_and_the_egc_follows():
    feeder = size_feeder(100, "copper", 80, 250)
    assert (feeder.conductor.size, feeder.egc, feeder.upsized) == ("1", "6", True)
    assert feeder.vd_percent <= 3


def test_an_aluminum_feeder_keeps_its_size_when_the_drop_is_fine():
    feeder = size_feeder(100, "aluminum", 80, 100)
    assert (feeder.conductor.size, feeder.egc, feeder.upsized) == ("1", "6", False)


def test_sizing_stops_at_350_kcmil_and_reports_the_drop_it_could_not_fix():
    feeder = size_feeder(200, "aluminum", 200, 500)
    assert feeder.conductor.size == "350"
    assert feeder.upsized
    assert feeder.vd_percent > 3


def test_the_upsized_egc_never_exceeds_the_hots():
    for ft in (50, 200, 350, 500):
        feeder = size_feeder(60, "copper", 60, ft)
        from permit_packets.core.conductors import _ground_properties
        assert _ground_properties(feeder.egc)[0] <= feeder.conductor.circular_mils


@pytest.mark.parametrize("breaker, ft, conduit, size", [
    (100, 1, "PVC", '1"'),    # 3 x #3 + #8 = 0.3285 sq in
    (60, 1, "PVC", '3/4"'),   # 3 x #6 + #10 = 0.1732 sq in
    (100, 1, "EMT", '1"'),
])
def test_feeder_conduit_holds_three_conductors_and_the_ground(breaker, ft, conduit, size):
    feeder = size_feeder(breaker, "copper", 1, ft)
    assert feeder_conduit(feeder, conduit) == size


# ---- Bad input ----

@pytest.mark.parametrize("changes", [
    {"subpanel_amps": 60, "feeder_breaker_amps": 100},   # breaker larger than the subpanel
    {"run_ft": 50, "trench_ft": 60},                      # trench longer than the run
    {"whole_dwelling": True},                             # sample is a detached building
    {"plan": _plan(panel=[500, 500])},                    # no subpanel marker
    {"plan": _plan(subpanel=[500, 500])},                 # no panel marker
    {"subpanel_amps": 175},
    {"feeder_breaker_amps": 80},
    {"service_amps": 50},
    {"run_ft": 0},
    {"loads": [{"label": "Load", "va": 1000}] * 7},
])
def test_bad_input_is_a_422(client, changes):
    assert client.post(PACKET_URL, json=_payload(**changes)).status_code == 422


def test_a_bad_value_says_why_in_plain_words(client):
    response = client.post(PACKET_URL, json=_payload(subpanel_amps=60))
    assert "can't be larger than the subpanel" in response.text


def test_whole_dwelling_is_accepted_in_the_same_building(client):
    body = _packet(client, location="same_building", trench_ft=0, whole_dwelling=True,
                   subpanel_amps=200, feeder_breaker_amps=200, material="aluminum", loads=[])
    assert body["feeder_conductor"] == "#4/0 Al"


def test_defaults_are_aluminum_and_pvc(client):
    payload = {k: v for k, v in _payload().items() if k not in ("material", "conduit")}
    body = client.post(PACKET_URL, json=payload).json()
    assert body["feeder_conductor"] == "#1 Al"
    assert body["conduit"].endswith(" PVC")


# ---- The sample packet ----

def test_packet_route_returns_eight_pages_and_the_response_contract(client):
    body = _packet(client)
    assert len(body["pages"]) == 8
    assert base64.b64decode(body["pdf"]).startswith(b"%PDF")
    assert body["job_type"] == "subpanel"
    assert body["ready"] is True
    assert [document["file_stem"] for document in body["documents"]] == STEMS
    assert body["feature_page"] == 2
    assert (body["computed_amps"], body["service_amps"]) == (137.8, 200)
    assert (body["feeder_conductor"], body["conduit"]) == ("#3 Cu", '1" PVC')
    assert [row["label"] for row in body["summary"]] == ["Service load", "Feeder", "Breaker", "Voltage drop"]
    assert [row["value"] for row in body["summary"]] == ["137.8 A", "#3 Cu", "100 A", "0.5%"]
    assert body["build_steps"] == [
        "Oro Valley, AZ checklist applied, 5 items",
        "Load calculation: 137.8 A on a 200 A service",
        "Feeder sized: 2 #3 Cu, #8 EGC",
        "Voltage drop: 0.5% over 90 ft",
        "Schematic site plan drawn",
        "Permit data filled in, 8 pages built",
    ]
    assert body["submission_email"]["subject"] == "Subpanel permit submittal: 123 Sample St"
    assert body["submission_email"]["body"].endswith("Thank you,\nSample Electric, LLC")
    labels = [field["label"] for field in body["fields"]]
    assert labels == ["Project address", "Parcel number", "Jurisdiction", "Property owner", "Permit type",
                      "Subpanel", "Contractor", "License number", "Scope of work"]
    assert body["fields"][4]["value"] == "Electrical, residential subpanel and feeder"
    assert body["fields"][5]["value"] == "Add make and model, 100 A"


def test_the_sample_checks_read_as_specified(client):
    checks = _checks(_packet(client))
    assert [name for name in checks] == [
        "Service capacity", "Panel spaces", "Feeder breaker", "Feeder conductors", "Feeder load",
        "Voltage drop", "Conduit fill"]
    assert checks["Service capacity"]["result"] == "137.8 A computed on the 200 A service"
    assert checks["Panel spaces"]["result"] == "4 open, 2 needed"
    assert checks["Feeder breaker"]["result"] == "100 A breaker on a 100 A subpanel"
    assert checks["Feeder conductors"]["result"] == "2 #3 Cu + #3 neutral + #8 EGC, 100 A at 75\N{DEGREE SIGN}C"
    assert checks["Feeder load"]["result"] == "27.5 A of 100 A"
    assert checks["Voltage drop"]["result"] == "1.2 V, 0.5% over 90 ft"
    assert checks["Conduit fill"]["result"] == '4 wires in 1" PVC, 40% fill'
    assert all(check["passed"] for check in checks.values())


def test_the_pdf_carries_the_subpanel_pages(client):
    text = _text(_packet(client))
    for heading in ("Subpanel Permit Packet", "Permit Application Data", "Site Plan", "One-Line Diagram",
                    "Feeder Schedule", "Load Calculation", "Equipment Data", "Pre-Submittal Review"):
        assert heading in text
    assert "DEMO PACKET: NOT FOR SUBMISSION" in text
    assert "100 A subpanel, detached building" in text
    assert "Underground" in text
    assert "Grounding electrode and disconnect at the building" in text
    assert "Attach manufacturer data and NRTL listing" in text
    assert "with the subpanel loads added at 100% of nameplate" in text


def test_zip_has_one_file_per_page_and_keeps_its_name(client):
    response = client.post(DOCUMENTS_URL, json=_payload())
    assert response.status_code == 200
    assert 'filename="subpanel-permit-documents-demo.zip"' in response.headers["content-disposition"]
    assert ZipFile(BytesIO(response.content)).namelist() == [f"{stem}.pdf" for stem in STEMS]


def test_routes_need_a_session():
    assert TestClient(app).post(PACKET_URL, json=_payload()).status_code == 401
    assert TestClient(app).post(DOCUMENTS_URL, json=_payload()).status_code == 401


@pytest.mark.parametrize("changes", [
    {},
    {"plan": _plan()},
    {"location": "same_building", "trench_ft": 0, "plan": _plan()},
    {"location": "attached_garage", "trench_ft": 0},
    {"location": "same_building", "trench_ft": 0},
])
def test_every_site_plan_stays_eight_pages(client, changes):
    body = _packet(client, **changes)
    assert len(body["pages"]) == 8
    if changes.get("plan"):
        assert "Site plan drawn to scale at 1 in = 30 ft" in body["build_steps"]


def test_a_worst_case_packet_still_fits_on_eight_pages(client):
    body = _packet(
        client, plan=_plan(), city="El Cajon", state="CA", jurisdiction_key="el-cajon-ca",
        subpanel_amps=200, feeder_breaker_amps=200, material="aluminum", conduit="EMT", run_ft=500,
        trench_ft=500, open_breaker_spaces=0, subpanel_model="Square D QO 40-space",
        loads=[{"label": f"Planned load {n}", "va": 9000} for n in range(6)],
    )
    assert len(body["pages"]) == 8


def test_markup_in_typed_text_does_not_break_the_pdf(client):
    body = _packet(client, subpanel_model="<b>Panel</b> & <i>co", customer="<x>",
                   loads=[{"label": "<u>Shop & co", "va": 3000}])
    assert len(body["pages"]) == 8


# ---- The checks ----

def test_a_feeder_load_over_the_breaker_fails_and_is_not_ready(client):
    body = _packet(client, subpanel_amps=60, feeder_breaker_amps=60, loads=[{"label": "Welder", "va": 20000}])
    check = _checks(body)["Feeder load"]
    assert check["passed"] is False
    assert check["result"] == "83.3 A of 60 A"
    assert body["ready"] is False


def test_a_service_too_small_for_the_load_fails(client):
    body = _packet(client, service_amps=100)
    assert _checks(body)["Service capacity"]["passed"] is False
    assert any(flag.startswith("The service is over capacity by 37.8 A.") for flag in body["flags"])
    assert not any("over capacity" in flag for flag in _packet(client)["flags"])


def test_one_open_space_fails_the_panel_spaces_check(client):
    check = _checks(_packet(client, open_breaker_spaces=1))["Panel spaces"]
    assert (check["result"], check["passed"]) == ("1 open, 2 needed", False)


def test_a_long_small_feeder_is_upsized_and_the_flag_names_the_egc(client):
    body = _packet(client, location="same_building", trench_ft=0, subpanel_amps=60, feeder_breaker_amps=60,
                   material="copper", run_ft=400, loads=[{"label": "Welder", "va": 12000}])
    # #6 would carry 60 A but drops 5% over 400 ft; #1 holds it under 3%. The #10 ground grows to #4.
    assert body["feeder_conductor"] == "#1 Cu"
    assert body["feeder_egc"] == "#4 Cu"
    assert "Feeder upsized to #1 for voltage drop, so the EGC is #4 to match (250.122(B))." in body["flags"]
    assert _checks(body)["Voltage drop"]["passed"] is True


def test_a_feeder_still_over_3_percent_at_350_kcmil_fails(client):
    body = _packet(client, location="same_building", trench_ft=0, subpanel_amps=200, feeder_breaker_amps=200,
                   material="aluminum", run_ft=500, service_amps=400,
                   loads=[{"label": "Load", "va": 48000}])
    assert _checks(body)["Voltage drop"]["passed"] is False
    assert any(flag.startswith("Voltage drop is 5.0% even at the largest size.") for flag in body["flags"])
    assert body["ready"] is False


def test_no_loads_assumes_80_percent_of_the_breaker_and_says_so(client):
    body = _packet(client, loads=[])
    assert _checks(body)["Feeder load"]["result"] == "80.0 A of 100 A"
    assert "No loads listed, so the feeder load assumes 80% of the breaker. Add the planned loads." in body["flags"]
    assert not any("No loads listed" in flag for flag in _packet(client)["flags"])


# ---- The flags ----

def test_detached_adds_the_250_32_flag_and_same_building_does_not(client):
    detached = _packet(client)["flags"]
    assert any("250.32(A)" in flag and "225.31" in flag for flag in detached)
    same = _packet(client, location="same_building", trench_ft=0)["flags"]
    assert not any("250.32" in flag for flag in same)
    garage = _packet(client, location="attached_garage", trench_ft=0)["flags"]
    assert not any("250.32" in flag for flag in garage)


def test_trenching_adds_the_811_flag(client):
    flag = "Call 811 before trenching. Confirm 18 in of cover for PVC (300.5)."
    assert flag in _packet(client)["flags"]
    assert flag not in _packet(client, trench_ft=0)["flags"]


def test_the_always_flags_come_in_order(client):
    flags = _packet(client)["flags"]
    expected = [
        "Check the existing loads against the home. They drive the service result.",
        "Keep neutral and ground separate in the subpanel. No neutral-to-ground bond (250.24(A)(5)).",
        "Confirm the breaker and panel terminals are rated 75\N{DEGREE SIGN}C (110.14(C)).",
        "Keep the working space in front of both panels clear: 30 in wide, 36 in deep (110.26).",
        "New branch circuits in the subpanel need GFCI and AFCI protection where required (210.8, 210.12).",
    ]
    positions = [flags.index(flag) for flag in expected]
    assert positions == sorted(positions)
    assert flags[-1] == "Confirm the adopted code edition."


def test_california_adds_the_smoke_and_co_flag_and_arizona_does_not(client):
    smoke = "California: permit work over $1,000 can trigger smoke and CO alarm requirements. Confirm with the city."
    assert smoke in _packet(client, city="El Cajon", state="CA", jurisdiction_key="el-cajon-ca")["flags"]
    assert smoke not in _packet(client)["flags"]


def test_a_plan_removes_the_schematic_flag(client):
    schematic = "This site plan is a schematic. Replace it with the property's plan before submitting."
    assert schematic in _packet(client)["flags"]
    assert schematic not in _packet(client, plan=_plan())["flags"]


# ---- Cities, sample mode and the registry ----

def test_oro_valley_falls_back_to_the_general_subpanel_checklist(client):
    body = _packet(client)
    assert body["jurisdiction"]["known"] is False
    assert body["jurisdiction"]["checklist"] == [
        "Permit application",
        "Site plan showing the main panel, subpanel and feeder route",
        "One-line diagram with feeder conductors, EGC and grounding",
        "Load calculation",
        "Panel specifications and listing",
    ]
    assert "General checklist, city rules added in setup" in _text(body)
    assert jurisdiction_json(ORO_VALLEY, "subpanel")["known"] is False
    assert jurisdiction_json(ORO_VALLEY, "ev_charger")["known"] is True
    assert "subpanel" not in ORO_VALLEY.checklists


def test_sample_mode_hides_the_address_and_parcel(client):
    body = _packet(client, address="309 Real St, Las Vegas, NV", city="Las Vegas", state="NV",
                   jurisdiction_key=None, plan=_plan(), sample_mode=True)
    assert body["address"] == "123 Sample St, Las Vegas, NV"
    text = _text(body)
    assert "309 Real" not in text
    assert "13831614010" not in text
    assert "000-00-000-000" in text


def test_the_job_types_list_has_ev_service_and_subpanel(client):
    job_types = client.get("/api/job-types").json()["job_types"]
    assert [job_type["key"] for job_type in job_types] == ["ev_charger", "service_upgrade", "subpanel"]
    subpanel = job_types[2]
    assert (subpanel["slug"], subpanel["label"], subpanel["short_label"], subpanel["icon"]) == (
        "subpanel", "Subpanel / feeder", "Subpanel", "subpanel")
    assert subpanel["blurb"] == "New subpanel with feeder sizing, voltage drop, load calc and site plan"
    assert [marker["letter"] for marker in subpanel["markers"]] == ["P", "S"]
    assert [marker["key"] for marker in subpanel["markers"]] == ["panel", "subpanel"]
    assert subpanel["route_between"] == ["panel", "subpanel"]
    assert subpanel["uses_home_loads"] is True
    assert subpanel["feature_page"] == 2
    assert [document["title"] for document in subpanel["documents"]] == [
        "Checklist and checks", "Permit data", "Site plan", "One-line diagram", "Feeder schedule",
        "Load calculation", "Equipment data", "Pre-submittal review"]
    assert REGISTRY["subpanel"].zip_name == "subpanel-permit-documents-demo.zip"


def test_the_signed_in_page_loads_the_subpanel_script_with_a_version(client):
    page = client.get("/").text
    assert re.search(r'src="/assets/js/job-types/subpanel\.js\?v=[0-9a-f]{10}"', page)
    assert page.index("subpanel.js") < page.index("/assets/js/app.js")
    assert 'data-job-type="subpanel"' in page
    assert client.get("/assets/js/job-types/subpanel.js").status_code == 200
