"""240 V appliance circuits: the branch math, the checks, the flags, the PDF and the routes."""
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
    BRANCH_COPPER,
    SMALL_CONDUCTOR_LIMIT,
    STANDARD_BREAKERS,
    branch_conduit,
    size_branch,
)
from permit_packets.job_types import REGISTRY
from permit_packets.jurisdictions import ORO_VALLEY, jurisdiction_json

os.environ["DEMO_PASSWORD"] = "test-password"

SAMPLE = json.loads((Path(__file__).parent / "samples" / "appliance_circuit.json").read_text())
PACKET_URL = "/api/jobs/appliance-circuit/packet"
DOCUMENTS_URL = "/api/jobs/appliance-circuit/documents"
STEMS = [
    "01-checklist-and-checks", "02-permit-application-data", "03-site-plan", "04-one-line-diagram",
    "05-load-calculation", "06-equipment-data", "07-pre-submittal-review",
]
SQUARE_LOT = [[250, 250], [750, 250], [750, 750], [250, 750]]
HEAT_PUMP = {"appliance": "heat_pump", "mca": 28.5, "mocp": 45, "location": "outdoor", "run_ft": 30,
             "trench_ft": 0, "wiring": "EMT"}
SAUNA = {"appliance": "sauna", "heater_kw": 6, "location": "indoor", "run_ft": 30, "trench_ft": 0}


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


def _check(body: dict, name: str) -> dict:
    return next(check for check in body["checks"] if check["name"] == name)


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
        "scale_ft_per_in": 30, "markers": markers or {"panel": [500, 500], "appliance": [600, 600]},
        "lot": SQUARE_LOT, "parcel_number": "13831614010", "aerial_base64": _aerial(), "credits": ["Credit"],
    }


def _branch(**changes):
    return size_branch(**{"terminals_75c": False, **changes})


def test_the_branch_tables_hold_the_code_values():
    assert [(w.size, w.ampacity_60c, w.ampacity_75c, w.circular_mils, w.area_sq_in) for w in BRANCH_COPPER] == [
        ("14", 15, 20, 4110, 0.0097), ("12", 20, 25, 6530, 0.0133), ("10", 30, 35, 10380, 0.0211),
        ("8", 40, 50, 16510, 0.0366), ("6", 55, 65, 26240, 0.0507), ("4", 70, 85, 41740, 0.0824),
        ("3", 85, 100, 52620, 0.0973), ("2", 95, 115, 66360, 0.1158), ("1", 110, 130, 83690, 0.1562),
    ]
    assert SMALL_CONDUCTOR_LIMIT == {"14": 15, "12": 20, "10": 30}
    assert STANDARD_BREAKERS == (15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 125)


def test_hot_tub_at_60c_is_6_awg_with_a_10_ground():
    branch = _branch(breaker=50, load_amps=40, run_ft=40)
    assert (branch.wire.size, branch.egc, branch.upsized) == ("6", "10", False)
    assert round(branch.vd_percent, 1) == 0.7


def test_hot_tub_at_75c_is_8_awg():
    assert _branch(breaker=50, load_amps=40, run_ft=40, terminals_75c=True).wire.size == "8"


@pytest.mark.parametrize("terminals_75c", [True, False])
def test_sauna_on_a_35_a_breaker_is_8_awg_because_of_240_4_d(terminals_75c):
    # #10 carries 35 A at 75 C, but 240.4(D) stops it at a 30 A breaker.
    assert _branch(breaker=35, load_amps=25, run_ft=40, terminals_75c=terminals_75c).wire.size == "8"


def test_mini_split_is_14_awg_on_a_25_a_breaker_with_the_ground_capped():
    branch = _branch(breaker=25, load_amps=15, run_ft=30, hvac_mca=15)
    assert (branch.wire.size, branch.egc) == ("14", "14")  # 250.122(A): no larger than the hots


def test_heat_pump_is_10_awg_with_a_10_ground():
    branch = _branch(breaker=45, load_amps=28.5, run_ft=30, hvac_mca=28.5)
    assert (branch.wire.size, branch.egc) == ("10", "10")


def test_a_long_hot_tub_run_is_upsized_with_its_ground():
    branch = _branch(breaker=50, load_amps=40, run_ft=200)
    assert (branch.wire.size, branch.egc, branch.upsized) == ("4", "8", True)
    assert branch.vd_percent <= 3


def test_voltage_drop_stops_at_the_largest_size():
    branch = _branch(breaker=60, load_amps=60, run_ft=500)
    assert branch.wire.size == "1"
    assert branch.vd_percent > 3


def test_conduit_holds_the_wires_and_the_ground():
    branch = _branch(breaker=50, load_amps=40, run_ft=40)
    assert branch_conduit(branch, 3, "PVC") == '3/4"'
    assert branch_conduit(branch, 4, "PVC") == '1"'


def test_a_hot_tub_with_no_nameplate_amps_is_a_422(client):
    payload = _payload()
    del payload["nameplate_amps"]
    assert client.post(PACKET_URL, json=payload).status_code == 422


@pytest.mark.parametrize("changes", [
    {"appliance": "sauna", "heater_kw": None},
    {"appliance": "heat_pump", "mca": 30, "mocp": None},
    {"gfci": None},
    {"disconnect_distance_ft": None},
])
def test_the_inputs_for_the_chosen_appliance_are_required(client, changes):
    payload = {**_payload(), **changes}
    if changes.get("appliance"):
        payload["nameplate_amps"] = None
    assert client.post(PACKET_URL, json=payload).status_code == 422


def test_a_heat_pump_with_mca_over_mocp_is_a_422(client):
    response = client.post(PACKET_URL, json=_payload(**{**HEAT_PUMP, "mca": 50}))
    assert response.status_code == 422
    assert "MCA can't be larger" in response.text


def test_a_trench_longer_than_the_run_is_a_422(client):
    response = client.post(PACKET_URL, json=_payload(run_ft=20, trench_ft=25))
    assert response.status_code == 422
    assert "underground part can't be longer" in response.text


def test_a_plan_without_an_appliance_marker_is_a_422(client):
    response = client.post(PACKET_URL, json=_payload(plan=_plan(panel=[500, 500], subpanel=[600, 600])))
    assert response.status_code == 422
    assert "appliance marker" in response.text


def test_values_out_of_range_are_a_422(client):
    for changes in ({"nameplate_amps": 0}, {"run_ft": 0}, {"service_amps": 30}, {"appliance": "kiln"},
                    {"wiring": "romex"}, {"location": "attic"}):
        assert client.post(PACKET_URL, json=_payload(**changes)).status_code == 422, changes


def test_the_sample_hot_tub_is_sized_and_ready(client):
    body = _packet(client)
    assert body["ready"] is True
    assert _check(body, "Breaker")["result"] == "50 A for a 40 A continuous load"
    assert _check(body, "Conductors")["result"] == "#6 Cu THWN-2, 55 A at 60\N{DEGREE SIGN}C"
    assert _check(body, "Voltage drop")["result"] == "1.6 V, 0.7% over 40 ft"
    assert _check(body, "Conduit fill")["result"] == "4 wires in 3/4\" PVC, 40% fill"
    assert _check(body, "GFCI protection")["passed"] is True
    assert _check(body, "Disconnect distance")["result"] == "8 ft from the spa, 5 ft minimum"
    assert body["conductor"] == "#6 Cu"
    assert body["egc"] == "#10 Cu"


def test_the_house_load_includes_the_appliance_at_100_percent(client):
    with_tub = _packet(client)["computed_amps"]
    without = _packet(client, nameplate_amps=1)["computed_amps"]
    assert round(with_tub - without, 1) == 39.0  # 40 A less 1 A


def test_hvac_breaker_is_the_largest_standard_size_within_the_mocp(client):
    body = _packet(client, **{**HEAT_PUMP, "mocp": 47})
    assert _check(body, "Breaker")["result"] == "45 A, nameplate max 47 A (440.22)"
    assert _check(body, "Breaker")["passed"] is True
    assert body["breaker_amps"] == 45


def test_hvac_breaker_below_the_mca_fails(client):
    body = _packet(client, **{**HEAT_PUMP, "mca": 46, "mocp": 47})
    assert _check(body, "Breaker")["passed"] is False
    assert body["ready"] is False


def test_a_manufacturer_breaker_below_the_minimum_fails(client):
    body = _packet(client, manufacturer_breaker=40)
    assert _check(body, "Breaker")["result"] == "40 A for a 40 A continuous load"
    assert _check(body, "Breaker")["passed"] is False
    assert body["ready"] is False


def test_a_manufacturer_breaker_at_the_minimum_or_above_passes(client):
    assert _check(_packet(client, manufacturer_breaker=60), "Breaker")["passed"] is True
    assert _packet(client, manufacturer_breaker=60)["breaker_amps"] == 60


def test_a_sauna_is_continuous_and_sized_from_its_kw(client):
    body = _packet(client, **SAUNA)
    assert _check(body, "Breaker")["result"] == "35 A for a 25 A continuous load"
    assert body["conductor"] == "#8 Cu"  # 240.4(D) keeps #10 off a 35 A breaker
    assert [check["name"] for check in body["checks"]] == [
        "Service capacity", "Panel spaces", "Breaker", "Conductors", "Voltage drop", "Conduit fill"]


def test_other_appliance_continuous_is_the_users_call(client):
    other = {"appliance": "other", "nameplate_amps": 30, "location": "indoor", "run_ft": 30, "trench_ft": 0}
    assert _check(_packet(client, **other), "Breaker")["result"] == "30 A for a 30 A non-continuous load"
    assert _check(_packet(client, **other, continuous=True), "Breaker")["result"] == (
        "40 A for a 30 A continuous load")


def test_the_neutral_changes_the_wire_count(client):
    with_neutral = _packet(client)
    without = _packet(client, needs_neutral=False)
    assert "3 #6 Cu THWN-2" in _text(with_neutral)
    assert "2 #6 Cu THWN-2" in _text(without)
    assert _check(without, "Conduit fill")["result"].startswith("3 wires")
    assert _check(_packet(client, **HEAT_PUMP), "Conduit fill")["result"].startswith("3 wires")


def test_cable_has_no_conduit_fill_check(client):
    body = _packet(client, wiring="cable", trench_ft=0)
    assert "Conduit fill" not in [check["name"] for check in body["checks"]]
    assert body["conduit"] == "cable"
    assert "as cable" in _text(body)


def test_75c_terminals_size_the_wire_at_the_75c_column(client):
    body = _packet(client, terminals_75c=True)
    assert body["conductor"] == "#8 Cu"
    assert _check(body, "Conductors")["result"] == "#8 Cu THWN-2, 50 A at 75\N{DEGREE SIGN}C"
    assert "Wire sized at the 75\N{DEGREE SIGN}C column. Confirm the equipment's terminal rating (110.14(C))." in body["flags"]


def test_a_long_run_is_upsized_and_flagged(client):
    body = _packet(client, run_ft=200, trench_ft=0, wiring="EMT")
    assert (body["conductor"], body["egc"]) == ("#4 Cu", "#8 Cu")
    assert "Circuit upsized to #4 for voltage drop, so the EGC is #8 to match (250.122(B))." in body["flags"]


def test_voltage_drop_still_over_3_percent_at_the_largest_size_is_flagged(client):
    body = _packet(client, appliance="other", nameplate_amps=60, run_ft=500, trench_ft=0, wiring="cable",
                   gfci=None, disconnect_distance_ft=None)
    assert body["conductor"] == "#1 Cu"
    assert _check(body, "Voltage drop")["passed"] is False
    assert any(flag.startswith("Voltage drop is") and "largest size" in flag for flag in body["flags"])


def test_a_load_no_listed_wire_can_carry_is_a_422_not_a_500(client):
    # 100 A continuous needs a 125 A breaker, which #1 copper can't carry at the 60 C column.
    response = client.post(PACKET_URL, json=_payload(
        appliance="other", nameplate_amps=100, continuous=True, trench_ft=0, gfci=None,
        disconnect_distance_ft=None))
    assert response.status_code == 422
    assert "carries a 125 A circuit at the 60\N{DEGREE SIGN}C column" in response.text
    assert client.post(PACKET_URL, json=_payload(
        appliance="other", nameplate_amps=100, continuous=True, trench_ft=0, gfci=None,
        disconnect_distance_ft=None, terminals_75c=True)).status_code == 200


def test_an_over_capacity_service_says_so(client):
    body = _packet(client, service_amps=100)
    assert _check(body, "Service capacity")["passed"] is False
    assert any(flag.startswith("The service is over capacity by") and "220.87" in flag for flag in body["flags"])


def test_too_few_open_spaces_fails(client):
    assert _check(_packet(client, open_breaker_spaces=1), "Panel spaces")["passed"] is False


def test_hot_tub_gfci_none_fails(client):
    body = _packet(client, gfci="none")
    assert _check(body, "GFCI protection")["passed"] is False
    assert body["ready"] is False
    assert _check(_packet(client, gfci="breaker"), "GFCI protection")["passed"] is True


def test_hot_tub_disconnect_under_5_ft_fails(client):
    body = _packet(client, disconnect_distance_ft=3)
    assert _check(body, "Disconnect distance")["result"] == "3 ft from the spa, 5 ft minimum"
    assert _check(body, "Disconnect distance")["passed"] is False
    assert _check(_packet(client, disconnect_distance_ft=5), "Disconnect distance")["passed"] is True


def test_hot_tub_flags(client):
    flags = _packet(client)["flags"]
    assert "Bond the spa's metal parts and equipment per the manufacturer and 680.42/680.26." in flags
    assert "The disconnect must be within sight of the spa." in flags
    assert "Call 811 before trenching. Confirm 18 in of cover for PVC (300.5)." in flags
    assert flags[0] == "Check the existing loads against the home. They drive the service result."
    assert flags[-1] == "Confirm the adopted code edition."


def test_outdoor_sauna_adds_the_building_permit_flag(client):
    note = "An outdoor or freestanding sauna can also need a building permit for the structure."
    assert note not in _packet(client, **SAUNA)["flags"]
    assert note in _packet(client, **{**SAUNA, "location": "outdoor"})["flags"]
    assert note in _packet(client, **{**SAUNA, "location": "detached"})["flags"]


@pytest.mark.parametrize("appliance", ["heat_pump", "mini_split"])
def test_hvac_adds_the_disconnect_and_receptacle_flags(client, appliance):
    flags = _packet(client, **{**HEAT_PUMP, "appliance": appliance})["flags"]
    assert "Put a disconnect within sight of the outdoor unit (440.14)." in flags
    assert "Add a 120 V service receptacle within 25 ft of the unit (210.63)." in flags
    assert not any("spa" in flag for flag in flags)


def test_flags_that_do_not_apply_stay_out(client):
    flags = _packet(client, **{**HEAT_PUMP, "run_ft": 10})["flags"]
    assert not any("811" in flag for flag in flags)
    assert not any("upsized" in flag for flag in flags)
    assert not any("over capacity" in flag for flag in flags)
    assert "Size the circuit from the appliance's nameplate and instructions." in _packet(
        client, appliance="other", nameplate_amps=30, trench_ft=0)["flags"]


def test_california_and_schematic_flags(client):
    body = _packet(client, city="El Cajon", state="CA", jurisdiction_key=None)
    assert any(flag.startswith("California:") for flag in body["flags"])
    assert "This site plan is a schematic. Replace it with the property's plan before submitting." in body["flags"]
    assert not any(flag.startswith("California:") for flag in _packet(client)["flags"])


def test_a_plan_replaces_the_schematic_flag_and_shows_the_parcel(client):
    body = _packet(client, plan=_plan())
    assert not any("schematic" in flag for flag in body["flags"])
    assert "13831614010" in _text(body)


def test_sample_mode_hides_the_address_and_parcel(client):
    body = _packet(client, address="309 Real St, Las Vegas, NV", city="Las Vegas", state="NV",
                   jurisdiction_key=None, plan=_plan(), sample_mode=True)
    assert body["address"] == "123 Sample St, Las Vegas, NV"
    text = _text(body)
    assert "309 Real" not in text
    assert "13831614010" not in text
    assert "000-00-000-000" in text


def test_the_route_returns_seven_pages_the_stems_and_the_zip_name(client):
    body = _packet(client)
    assert len(body["pages"]) == 7
    assert [document["file_stem"] for document in body["documents"]] == STEMS
    assert body["feature_page"] == 2
    response = client.post(DOCUMENTS_URL, json=_payload())
    assert 'filename="appliance-circuit-permit-documents-demo.zip"' in response.headers["content-disposition"]
    names = ZipFile(BytesIO(response.content)).namelist()
    assert [name.split(".")[0] for name in names] == STEMS


@pytest.mark.parametrize("changes, title", [
    ({}, "Hot Tub Circuit Permit Packet"),
    (SAUNA, "Sauna Circuit Permit Packet"),
    (HEAT_PUMP, "Heat Pump Circuit Permit Packet"),
    ({**HEAT_PUMP, "appliance": "mini_split"}, "Mini-Split Circuit Permit Packet"),
    ({"appliance": "other", "nameplate_amps": 30, "trench_ft": 0}, "240 V Appliance Circuit Permit Packet"),
])
def test_the_title_follows_the_appliance(client, changes, title):
    body = _packet(client, **changes)
    assert title in _text(body)
    document = pypdfium2.PdfDocument(base64.b64decode(body["pdf"]))
    try:
        assert document.get_metadata_dict()["Title"] == f"{title} (demo)"
    finally:
        document.close()


def test_the_cover_and_pages_carry_the_details(client):
    text = _text(_packet(client, appliance_model="Acme Spa 500"))
    assert "2,400 sq ft home" in text
    assert "Hot tub, outdoor" in text
    assert "Customer: Sample Homeowner" in text
    assert "3 #6 Cu THWN-2 + #10 EGC in 3/4\" PVC" in text or "3 #6 Cu THWN-2 + #10 EGC" in text
    assert "Acme Spa 500" in text
    assert "Attach the manufacturer's installation instructions and NRTL listing" in text
    assert "Optional dwelling method, NEC 220.82, with the hot tub added at 100% of nameplate." in text
    assert "Electrical, residential hot tub circuit" in text
    assert "Underground" in text  # trenching adds that inspection


def test_no_trench_means_no_underground_inspection(client):
    text = _text(_packet(client, trench_ft=0))
    assert "Underground" not in text


def test_the_review_page_follows_the_appliance(client):
    assert "Spa bonding" in _text(_packet(client))
    assert "Heater instructions followed" in _text(_packet(client, **SAUNA))
    assert "120 V service receptacle" in _text(_packet(client, **HEAT_PUMP))


def test_the_response_contract_matches_subpanel(client):
    body = _packet(client)
    assert [row["label"] for row in body["summary"]] == ["Service load", "Breaker", "Wire", "Voltage drop"]
    assert [row["value"] for row in body["summary"]][1:] == ["50 A", "#6", "0.7%"]
    assert body["build_steps"][0] == "Oro Valley, AZ checklist applied, 5 items"
    assert body["build_steps"][2] == "Circuit sized: 50 A breaker, #6 Cu"
    assert body["build_steps"][3] == "Voltage drop: 0.7% over 40 ft"
    assert body["build_steps"][4] == "Schematic site plan drawn"
    assert body["build_steps"][-1] == "Permit data filled in, 7 pages built"
    assert body["submission_email"]["subject"] == "Hot tub circuit permit submittal: 123 Sample St"
    assert body["submission_email"]["body"].endswith("Thank you,\nSample Electric, LLC")
    assert {field["label"] for field in body["fields"]} >= {"Permit type", "Scope of work"}
    permit_type = next(f["value"] for f in body["fields"] if f["label"] == "Permit type")
    assert permit_type == "Electrical, residential hot tub circuit"
    assert _packet(client, **HEAT_PUMP)["submission_email"]["subject"].startswith("Heat pump circuit permit")
    assert _packet(client, appliance="other", nameplate_amps=30, trench_ft=0)["submission_email"][
        "subject"].startswith("240 V appliance circuit permit")


def test_oro_valley_falls_back_to_the_general_checklist():
    assert jurisdiction_json(ORO_VALLEY, "appliance_circuit")["known"] is False
    assert jurisdiction_json(ORO_VALLEY, "ev_charger")["known"] is True
    assert "appliance_circuit" not in ORO_VALLEY.checklists
    assert jurisdiction_json(ORO_VALLEY, "appliance_circuit")["checklist"] == [
        "Permit application", "Site plan showing the panel and the appliance",
        "One-line diagram with conductors, breaker and disconnect", "Load calculation",
        "Manufacturer specifications and listing"]


def test_the_job_types_list_has_the_four_types_in_order(client):
    job_types = client.get("/api/job-types").json()["job_types"]
    assert [job_type["key"] for job_type in job_types] == [
        "ev_charger", "service_upgrade", "subpanel", "appliance_circuit"]
    circuit = job_types[3]
    assert (circuit["slug"], circuit["label"], circuit["short_label"], circuit["icon"]) == (
        "appliance-circuit", "240 V circuit", "240 V", "circuit")
    assert circuit["blurb"] == "Hot tub, sauna, heat pump or mini-split circuit with load calc and site plan"
    assert [marker["key"] for marker in circuit["markers"]] == ["panel", "appliance"]
    assert [marker["letter"] for marker in circuit["markers"]] == ["P", "A"]
    assert circuit["route_between"] == ["panel", "appliance"]
    assert circuit["uses_home_loads"] is True
    assert circuit["feature_page"] == 2
    assert [document["title"] for document in circuit["documents"]] == [
        "Checklist and checks", "Permit data", "Site plan", "One-line diagram", "Load calculation",
        "Equipment data", "Pre-submittal review"]
    assert REGISTRY["appliance_circuit"].zip_name == "appliance-circuit-permit-documents-demo.zip"
