"""Panel / service upgrade permits: the conductor math, the checks, the flags, the PDF and the routes."""
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

from permit_packets.core.conductors import (
    ALUMINUM_75C,
    COPPER_75C,
    gec_size,
    service_conductor,
    service_conduit,
    solar_fits,
)
from permit_packets.job_types import REGISTRY
from permit_packets.jurisdictions import ORO_VALLEY, jurisdiction_json

os.environ["DEMO_PASSWORD"] = "test-password"

SAMPLE = json.loads((Path(__file__).parent / "samples" / "service_upgrade.json").read_text())
PACKET_URL = "/api/jobs/service-upgrade/packet"
DOCUMENTS_URL = "/api/jobs/service-upgrade/documents"
STEMS = [
    "01-checklist-and-checks", "02-permit-application-data", "03-site-plan", "04-riser-diagram",
    "05-load-calculation", "06-utility-service-request", "07-equipment-data", "08-pre-submittal-review",
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
        "scale_ft_per_in": 30, "markers": markers or {"meter": [600, 500], "panel": [500, 500]},
        "lot": SQUARE_LOT, "parcel_number": "13831614010", "aerial_base64": _aerial(), "credits": ["Credit"],
    }


def _checks(body: dict) -> dict:
    return {check["name"]: check for check in body["checks"]}


# ---- Conductors, grounding, conduit and solar ----

@pytest.mark.parametrize("amps, copper, aluminum", [
    (100, "4", "2"), (125, "2", "1/0"), (150, "1", "2/0"), (200, "2/0", "4/0"), (225, "3/0", "250"),
])
def test_service_conductor_is_sized_at_83_percent(amps, copper, aluminum):
    assert service_conductor(amps, "copper").size == copper
    assert service_conductor(amps, "aluminum").size == aluminum
    assert service_conductor(amps, "copper").ampacity_75c >= 0.83 * amps


def test_aluminum_carries_less_than_copper_at_every_size():
    assert [c.size for c in COPPER_75C] == [a.size for a in ALUMINUM_75C]
    for copper, aluminum in zip(COPPER_75C, ALUMINUM_75C):
        assert aluminum.ampacity_75c < copper.ampacity_75c
        assert (aluminum.circular_mils, aluminum.area_sq_in) == (copper.circular_mils, copper.area_sq_in)


@pytest.mark.parametrize("amps, material, rods, concrete, water", [
    (200, "copper", "6", "4", "4"),
    (200, "aluminum", "6", "4", "4"),
    (100, "copper", "8", "8", "8"),
])
def test_gec_follows_the_electrode(amps, material, rods, concrete, water):
    conductor = service_conductor(amps, material)
    assert gec_size(conductor, material, "rods") == rods
    assert gec_size(conductor, material, "concrete_encased") == concrete
    assert gec_size(conductor, material, "water_pipe") == water


@pytest.mark.parametrize("size, material, table", [
    ("2", "copper", "8"), ("1", "copper", "6"), ("1/0", "copper", "6"), ("2/0", "copper", "4"),
    ("3/0", "copper", "4"), ("4/0", "copper", "2"), ("350", "copper", "2"),
    ("1/0", "aluminum", "8"), ("2/0", "aluminum", "6"), ("3/0", "aluminum", "6"),
    ("4/0", "aluminum", "4"), ("250", "aluminum", "4"), ("300", "aluminum", "2"),
])
def test_gec_table_rows(size, material, table):
    conductor = next(c for c in (COPPER_75C if material == "copper" else ALUMINUM_75C) if c.size == size)
    assert gec_size(conductor, material, "water_pipe") == table


@pytest.mark.parametrize("amps, material, pvc, emt", [
    (200, "copper", '1-1/2"', '1-1/2"'),
    (200, "aluminum", '2"', '2"'),
    (100, "copper", '1"', '1"'),
])
def test_service_conduit_holds_three_conductors(amps, material, pvc, emt):
    conductor = service_conductor(amps, material)
    assert service_conduit(conductor, "PVC") == pvc
    assert service_conduit(conductor, "EMT") == emt


@pytest.mark.parametrize("bus, main, pv, fits", [
    (200, 200, 40, True), (200, 200, 50, False), (225, 200, 70, True),
])
def test_solar_120_percent_rule(bus, main, pv, fits):
    assert solar_fits(bus, main, pv) is fits


# ---- The request ----

@pytest.mark.parametrize("changes", [
    {"scope": "upgrade", "existing_service_amps": 200, "new_service_amps": 200},
    {"scope": "upgrade", "existing_service_amps": 200, "new_service_amps": 150},
    {"scope": "replacement", "existing_service_amps": 100, "new_service_amps": 200},
    {"bus_amps": 150},
    {"plan": _plan(panel=[500, 500])},
    {"has_solar": True, "pv_breaker_amps": 0},
    {"electrodes": []},
    {"electrodes": ["rods", "rods"]},
    {"new_service_amps": 250},
    {"existing_service_amps": 90},
    {"se_length_ft": 0},
    {"planned_loads": [{"label": "Load", "va": 1000}] * 5},
])
def test_bad_input_is_a_422(client, changes):
    assert client.post(PACKET_URL, json=_payload(**changes)).status_code == 422


def test_a_bad_value_says_why_in_plain_words(client):
    response = client.post(PACKET_URL, json=_payload(scope="replacement"))
    assert "keeps the existing service size" in response.text


def test_a_same_size_replacement_is_accepted(client):
    body = _packet(client, scope="replacement", existing_service_amps=200, new_service_amps=200)
    assert body["fields"][4] == {"label": "Permit type", "value": "Electrical, residential panel replacement"}
    assert "Panel Replacement Permit Packet" in _text(body)


# ---- The packet ----

def test_packet_route_returns_eight_pages_and_the_response_contract(client):
    body = _packet(client)
    assert len(body["pages"]) == 8
    assert base64.b64decode(body["pdf"]).startswith(b"%PDF")
    assert body["job_type"] == "service_upgrade"
    assert body["ready"] is True
    assert [document["file_stem"] for document in body["documents"]] == STEMS
    assert body["feature_page"] == 2
    assert (body["computed_amps"], body["new_service_amps"]) == (158.3, 200)
    assert (body["service_conductor"], body["conduit"]) == ("#2/0 Cu", '1-1/2" PVC')
    assert body["gec"] == {"rods": "#6 Cu", "water_pipe": "#4 Cu"}
    assert [row["label"] for row in body["summary"]] == ["Calculated load", "New service", "Service wire", "GEC"]
    assert [row["value"] for row in body["summary"]] == ["158.3 A", "200 A", "#2/0 Cu", "#4 Cu"]
    assert body["build_steps"] == [
        "Oro Valley, AZ checklist applied, 6 items",
        "Load calculation: 158.3 A on the new 200 A service",
        "Service conductors sized: 3 #2/0 Cu",
        "Grounding electrode conductor sized",
        "Schematic site plan drawn",
        "Permit and utility data filled in, 8 pages built",
    ]
    assert body["submission_email"]["subject"] == "Service upgrade permit submittal: 123 Sample St"
    assert body["submission_email"]["body"].endswith("Thank you,\nSample Electric, LLC")
    labels = [field["label"] for field in body["fields"]]
    assert labels == ["Project address", "Parcel number", "Jurisdiction", "Property owner", "Permit type",
                      "Service", "Equipment", "Contractor", "License number", "Scope of work"]
    assert body["fields"][5]["value"] == "100 A to 200 A, 120/240 V single-phase"
    assert body["fields"][6]["value"] == "Add make and model"


def test_the_pdf_carries_the_service_pages(client):
    text = _text(_packet(client))
    for heading in ("Service Upgrade Permit Packet", "Permit Application Data", "Site Plan", "Riser Diagram",
                    "Load Calculation", "Utility Service Request Data", "Equipment Data", "Pre-Submittal Review"):
        assert heading in text
    assert "This page is not the utility" in text
    assert "DEMO PACKET: NOT FOR SUBMISSION" in text


def test_zip_has_one_file_per_page_and_keeps_its_name(client):
    response = client.post(DOCUMENTS_URL, json=_payload())
    assert response.status_code == 200
    assert 'filename="service-upgrade-permit-documents-demo.zip"' in response.headers["content-disposition"]
    assert ZipFile(BytesIO(response.content)).namelist() == [f"{stem}.pdf" for stem in STEMS]


def test_routes_need_a_session():
    assert TestClient(app).post(PACKET_URL, json=_payload()).status_code == 401
    assert TestClient(app).post(DOCUMENTS_URL, json=_payload()).status_code == 401


@pytest.mark.parametrize("plan", [
    None,
    _plan(),                                       # meter and panel apart: a measured route
    _plan(meter=[500, 500], panel=[500, 500]),     # a meter-main combo: one spot
])
def test_every_site_plan_stays_eight_pages(client, plan):
    changes = {"plan": plan} if plan else {}
    body = _packet(client, **changes)
    assert len(body["pages"]) == 8
    if plan:
        assert "Site plan drawn to scale at 1 in = 30 ft" in body["build_steps"]


def test_a_worst_case_packet_still_fits_on_eight_pages(client):
    body = _packet(
        client, plan=_plan(), city="El Cajon", state="CA", jurisdiction_key="el-cajon-ca",
        equipment="main_panel", service_drop="underground", relocated=True, material="aluminum", conduit="EMT",
        electrodes=["rods", "concrete_encased", "water_pipe"], existing_brand="federal_pacific",
        has_solar=True, pv_breaker_amps=40, panel_model="Square D QO 40-space", utility="San Diego Gas & Electric",
        meter_number="1234567890",
        planned_loads=[{"label": f"Planned load {n}", "va": 5000} for n in range(4)],
    )
    assert len(body["pages"]) == 8


def test_markup_in_typed_text_does_not_break_the_pdf(client):
    body = _packet(client, panel_model="<b>Panel</b> & <i>co", utility="A&B <u>Power", customer="<x>")
    assert len(body["pages"]) == 8


# ---- The checks ----

def test_a_service_that_is_too_small_for_the_load_fails_and_is_not_ready(client):
    body = _packet(client, existing_service_amps=100, new_service_amps=125, bus_amps=125,
                   home={**SAMPLE["home"], "square_feet": 4000})
    assert body["ready"] is False
    capacity = _checks(body)["Service capacity"]
    assert capacity["passed"] is False
    assert capacity["result"].endswith("A computed on the new 125 A service")


def test_the_sample_job_passes_every_check(client):
    body = _packet(client)
    assert all(check["passed"] for check in body["checks"])
    assert _checks(body)["Service conductors"]["result"] == (
        "#2/0 Cu THWN-2, 175 A at 75\N{DEGREE SIGN}C, for 200 A x 83% = 166.0 A (310.12)")
    assert _checks(body)["Panel rating"]["result"] == "200 A bus, 200 A main"
    assert _checks(body)["Grounding electrode conductor"]["result"] == "Rods: #6 Cu; Water pipe: #4 Cu"
    assert _checks(body)["Conduit fill"]["result"] == '3 #2/0 in 1-1/2" PVC, 40% fill'
    assert "Solar (120% rule)" not in _checks(body)


def test_no_conduit_drops_the_conduit_check(client):
    body = _packet(client, conduit="none")
    assert "Conduit fill" not in _checks(body)
    assert body["conduit"] is None
    assert "without conduit" in next(f["value"] for f in body["fields"] if f["label"] == "Scope of work")


def test_aluminum_sizes_up_and_reads_kcmil(client):
    body = _packet(client, material="aluminum", existing_service_amps=200, new_service_amps=225, bus_amps=225)
    assert body["service_conductor"] == "250 kcmil Al"
    assert body["conduit"] == '2" PVC'
    assert "250 kcmil Al THWN-2" in _checks(body)["Service conductors"]["result"]


def test_the_solar_120_percent_rule_fails_as_a_check(client):
    body = _packet(client, has_solar=True, pv_breaker_amps=50)
    solar = _checks(body)["Solar (120% rule)"]
    assert solar["passed"] is False
    assert solar["result"] == "200 A main + 50 A PV = 250 A on a 200 A bus, limit 240 A"
    assert body["ready"] is False


def test_solar_that_fits_passes(client):
    body = _packet(client, has_solar=True, pv_breaker_amps=40)
    assert _checks(body)["Solar (120% rule)"]["passed"] is True
    assert body["ready"] is True


def test_a_larger_bus_makes_room_for_solar(client):
    body = _packet(client, has_solar=True, pv_breaker_amps=70, new_service_amps=200, bus_amps=225)
    assert _checks(body)["Solar (120% rule)"]["passed"] is True


# ---- The flags ----

SMOKE_CO = "California: permit work over $1,000 can trigger smoke and CO alarm requirements. Confirm with the city."


def test_california_adds_the_smoke_and_co_flag_and_nevada_does_not(client):
    california = _packet(client, city="El Cajon", state="CA", jurisdiction_key=None)
    nevada = _packet(client, city="Las Vegas", state="NV", jurisdiction_key=None)
    assert SMOKE_CO in california["flags"]
    assert SMOKE_CO not in nevada["flags"]
    assert "Smoke and CO alarm requirement confirmed" in _text(california)
    assert "Smoke and CO alarm requirement confirmed" not in _text(nevada)


def test_a_known_brand_is_named_in_a_flag_and_in_the_scope(client):
    body = _packet(client, existing_brand="federal_pacific")
    assert ("Existing panel is a Federal Pacific. Note it in the scope as the reason for replacement."
            in body["flags"])
    scope = next(f["value"] for f in body["fields"] if f["label"] == "Scope of work")
    assert "Federal Pacific" in scope
    assert not any("Existing panel is a" in flag for flag in _packet(client)["flags"])


def test_an_all_number_8_gec_adds_the_protection_flag(client):
    body = _packet(client, existing_service_amps=60, new_service_amps=100, bus_amps=100,
                   electrodes=["rods", "concrete_encased", "water_pipe"])
    assert body["gec"] == {"rods": "#8 Cu", "concrete_encased": "#8 Cu", "water_pipe": "#8 Cu"}
    assert "A #8 grounding electrode conductor must be protected in raceway or armor (250.64(B))." in body["flags"]
    assert not any("#8 grounding" in flag for flag in _packet(client)["flags"])


def test_the_drop_decides_which_clearance_flag_shows(client):
    overhead = _packet(client)["flags"]
    underground = _packet(client, service_drop="underground")["flags"]
    assert any(flag.startswith("Confirm mast, weatherhead") for flag in overhead)
    assert not any(flag.startswith("Confirm the lateral") for flag in overhead)
    assert any(flag.startswith("Confirm the lateral conduit") for flag in underground)
    assert not any(flag.startswith("Confirm mast") for flag in underground)


def test_flags_come_in_the_order_the_job_needs_them(client):
    flags = _packet(client, relocated=True, has_solar=True, pv_breaker_amps=40)["flags"]
    assert flags[0].startswith("Check the existing loads")
    assert flags[1].startswith("Submit the utility service request (page 6)")
    assert flags[3].startswith("Relocating the meter")
    assert flags[-1] == "Confirm the adopted code edition."
    assert flags[-2].startswith("This site plan is a schematic")
    assert flags[-3].startswith("This home has solar")


def test_a_plan_removes_the_schematic_flag(client):
    assert not any("schematic" in flag for flag in _packet(client, plan=_plan())["flags"])


# ---- Cities, sample mode and the registry ----

def test_oro_valley_falls_back_to_the_general_service_checklist(client):
    body = _packet(client)
    assert body["jurisdiction"]["known"] is False
    assert body["jurisdiction"]["checklist"] == [
        "Permit application",
        "Site plan showing the meter and main panel",
        "Riser diagram with service conductors, grounding and bonding",
        "Load calculation",
        "Panel and meter equipment specifications and listing",
        "Utility service request",
    ]
    assert "General checklist, city rules added in setup" in _text(body)
    assert "Page 6: send to the utility" in _text(body)
    assert jurisdiction_json(ORO_VALLEY, "service_upgrade")["known"] is False
    assert jurisdiction_json(ORO_VALLEY, "ev_charger")["known"] is True
    assert "service_upgrade" not in ORO_VALLEY.checklists


def test_sample_mode_hides_the_address_and_parcel(client):
    body = _packet(client, address="309 Real St, Las Vegas, NV", city="Las Vegas", state="NV",
                   jurisdiction_key=None, plan=_plan(), sample_mode=True)
    assert body["address"] == "123 Sample St, Las Vegas, NV"
    text = _text(body)
    assert "309 Real" not in text
    assert "13831614010" not in text
    assert "123 Sample St" in text
    assert "000-00-000-000" in text


def test_a_real_address_and_parcel_show_without_sample_mode(client):
    text = _text(_packet(client, address="309 Real St, Las Vegas, NV", plan=_plan()))
    assert "309 Real" in text
    assert "13831614010" in text


def test_the_job_types_list_is_ev_then_service(client):
    job_types = client.get("/api/job-types").json()["job_types"]
    assert [job_type["key"] for job_type in job_types] == ["ev_charger", "service_upgrade"]
    service = job_types[1]
    assert (service["slug"], service["label"], service["short_label"], service["icon"]) == (
        "service-upgrade", "Panel / service upgrade", "Service", "panel")
    assert [marker["letter"] for marker in service["markers"]] == ["M", "P"]
    assert [marker["key"] for marker in service["markers"]] == ["meter", "panel"]
    assert service["route_between"] == ["meter", "panel"]
    assert service["uses_home_loads"] is True
    assert service["feature_page"] == 2
    assert [document["file_stem"] for document in service["documents"]] == STEMS
    assert [document["title"] for document in service["documents"]] == [
        "Checklist and checks", "Permit data", "Site plan", "Riser diagram", "Load calculation",
        "Utility request", "Equipment data", "Pre-submittal review"]
    assert REGISTRY["service_upgrade"].zip_name == "service-upgrade-permit-documents-demo.zip"
