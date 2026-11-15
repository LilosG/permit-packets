import base64
import os
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from pypdf import PdfReader

from permit_packets.core.equipment import LIBRARY, attachment_span, find_equipment
from permit_packets.core.preview import packet_documents_zip

os.environ["DEMO_PASSWORD"] = "test-password"
from app import app  # noqa: E402
from tests.api_helpers import with_pdf


def test_every_library_item_has_its_data_sheet():
    for item in LIBRARY:
        assert item.data_sheet_path().is_file(), item.name
        assert len(PdfReader(str(item.data_sheet_path())).pages) >= 1


def test_models_are_found_by_name_or_alias():
    assert find_equipment("Tesla Wall Connector (Gen 3)", "charger").max_amps == 48
    assert find_equipment("tesla wall connector", "charger").data_sheet == "tesla-gen3-wall-connector.pdf"
    assert find_equipment("ChargePoint CPH50", "charger").name.startswith("ChargePoint")
    assert find_equipment("HOM3060M200PC", "panel").max_amps == 200
    assert find_equipment("Some other charger", "charger") is None
    assert find_equipment("", "charger") is None
    assert find_equipment("Tesla Wall Connector", "panel") is None


def test_index_lists_every_library_model():
    page = open("permit_packets/static/index.html").read()
    for item in LIBRARY:
        assert f'value="{item.name}"' in page




@pytest.fixture
def client():
    signed_in = TestClient(app)
    assert signed_in.post("/api/signin", json={"password": "test-password"}).status_code == 200
    return signed_in


def _ev(client, model):
    payload = dict(
        customer="Sample", address="123 Sample St", contractor="Sample Electric", license_number="ROC 000000",
        home={"square_feet": 2000, "range_va": 12000, "cooling_va": 7200}, service_amps=200,
        open_breaker_spaces=4, charger_amps=48, location="attached_garage", run_ft=30, trench_ft=0,
        charger_model=model,
    )
    return with_pdf(client, "/api/jobs/ev-charger/packet", payload)


def test_a_library_charger_attaches_its_data_sheet_after_the_equipment_page(client):
    body = _ev(client, "Tesla Wall Connector (Gen 3)")
    pdf = base64.b64decode(body["pdf"])
    pages = [page.extract_text() for page in PdfReader(BytesIO(pdf)).pages]
    equipment = next(i for i, text in enumerate(pages) if "Equipment Data" in text)
    assert "data sheet from the manufacturer follows this page" in pages[equipment]
    assert "Product Specifications" in pages[equipment + 1]
    assert "Pre-Submittal Review" in pages[-1]
    assert attachment_span(pdf) == (equipment + 1, 2)
    assert not any("data sheet" in flag for flag in body["flags"])
    with ZipFile(BytesIO(packet_documents_zip(pdf, tuple(d["file_stem"] for d in body["documents"])))) as archive:
        equipment_doc = PdfReader(BytesIO(archive.read("07-equipment-data.pdf")))
        assert len(equipment_doc.pages) == 3
        assert "Pre-Submittal Review" in PdfReader(BytesIO(archive.read("08-pre-submittal-review.pdf"))).pages[0].extract_text()


def test_an_unknown_charger_still_asks_for_its_data_sheet(client):
    body = _ev(client, "Acme Charger 9000")
    pdf = base64.b64decode(body["pdf"])
    assert attachment_span(pdf) is None
    assert any("Acme Charger 9000 data sheet" in flag for flag in body["flags"])


def test_the_panel_schedule_lists_entered_circuits_and_marks_the_new_breaker(client):
    payload_circuits = [{"label": "Range", "amps": 50, "poles": 2}, {"label": "Kitchen", "amps": 20, "poles": 1}]
    payload = dict(
        customer="Sample", address="123 Sample St", contractor="Sample Electric", license_number="ROC 000000",
        home={"square_feet": 2000, "range_va": 12000, "cooling_va": 7200}, service_amps=200,
        open_breaker_spaces=4, charger_amps=48, location="attached_garage", run_ft=30, trench_ft=0,
        existing_circuits=payload_circuits,
    )
    body = with_pdf(client, "/api/jobs/ev-charger/packet", payload)
    pages = [page.extract_text() for page in PdfReader(BytesIO(base64.b64decode(body["pdf"]))).pages]
    schedule = next(text for text in pages if "Panel Schedule" in text)
    assert "Range" in schedule and "50 A" in schedule and "EV charger, 48 A (this permit)" in schedule
    assert "Open spaces: 4 before, 2 after" in schedule
    assert "Enter the panel's existing circuits for the panel schedule." not in body["flags"]


def test_without_entered_circuits_the_schedule_is_a_blank_grid_and_the_packet_is_not_ready(client):
    body = _ev(client, "")
    pages = [page.extract_text() for page in PdfReader(BytesIO(base64.b64decode(body["pdf"]))).pages]
    schedule = next(text for text in pages if "Circuit directory" in text)
    assert "Field verify and fill in" in schedule
    assert "Kitchen small-appliance" not in schedule and "General lighting" not in schedule
    assert "Verify on site" not in schedule
    assert "Enter the panel's existing circuits for the panel schedule." in body["flags"]
    panel = next(check for check in body["checks"] if check["name"] == "Panel schedule")
    assert panel["passed"] is False and body["ready"] is False
    row = next(r for r in body["checklist_status"] if r["item"].startswith("Panel schedule"))
    assert row["status"] == "Open" and "field verify" in row["where"]


def test_tabloid_draws_every_page_natively_at_11_x_17(client):
    payload = dict(
        customer="Sample", address="123 Sample St", contractor="Sample Electric", license_number="ROC 000000",
        home={"square_feet": 2000, "range_va": 12000, "cooling_va": 7200}, service_amps=200,
        open_breaker_spaces=4, charger_amps=48, location="attached_garage", run_ft=30, trench_ft=0,
        sheet_size="tabloid",
    )
    body = with_pdf(client, "/api/jobs/ev-charger/packet", payload)
    assert body["sheet_size"] == "tabloid"
    sheets = PdfReader(BytesIO(base64.b64decode(body["pdf"]))).pages
    assert len(sheets) == len(body["pages"])
    assert {(float(s.mediabox.width), float(s.mediabox.height)) for s in sheets} == {(1224.0, 792.0)}
    zipped = client.post("/api/jobs/ev-charger/documents", json=payload).content
    with ZipFile(BytesIO(zipped)) as archive:
        site_plan = PdfReader(BytesIO(archive.read("03-site-plan.pdf"))).pages[0]
        assert (float(site_plan.mediabox.width), float(site_plan.mediabox.height)) == (1224.0, 792.0)


def test_letter_is_the_default_sheet(client):
    assert _ev(client, "")["sheet_size"] == "letter"


def test_measured_demand_220_87_can_carry_a_home_the_220_82_calculation_rejects(client):
    payload = dict(
        customer="Sample", address="123 Sample St", contractor="Sample Electric", license_number="ROC 000000",
        home={"square_feet": 3500, "range_va": 12000, "dryer_va": 5000, "water_heater_va": 4500, "cooling_va": 10000,
              "hot_tub_or_pool_va": 6000},
        service_amps=100, open_breaker_spaces=4, charger_amps=32, location="attached_garage", run_ft=30, trench_ft=0,
    )
    without = client.post("/api/jobs/ev-charger/packet", json=payload).json()
    assert without["ready"] is False
    body = with_pdf(client, "/api/jobs/ev-charger/packet", {**payload, "peak_demand_kw": 9.5})
    capacity = next(check for check in body["checks"] if check["name"] == "Service capacity")
    # 9.5 kW x 1.25 = 11,875 VA, plus 32 A x 240 V x 1.25 = 9,600 VA: 21,475 VA / 240 V = 89.5 A
    assert capacity["result"] == "89.5 A by measured demand (220.87) on a 100 A service"
    assert capacity["passed"] is True
    assert len(body["pages"]) == len(without["pages"])
    assert any("relies on measured demand" in flag for flag in body["flags"])
    pages = [page.extract_text() for page in PdfReader(BytesIO(base64.b64decode(body["pdf"]))).pages]
    load_page = next(text for text in pages if "Load Calculation" in text)
    assert "measured demand (NEC 220.87)" in load_page and "89.5 A" in load_page


def test_library_data_sheets_are_unrotated_so_they_place_as_drawn():
    from pypdf import PdfReader
    from permit_packets.core.equipment import LIBRARY
    for item in LIBRARY:
        assert all(page.rotation == 0 for page in PdfReader(str(item.data_sheet_path())).pages), item.name
