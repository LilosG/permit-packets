"""400 A services (a Class 320 meter-main with two 200 A service disconnects), an EV charger installed with a
service upgrade, and Monte Sereno, CA, where both came up together."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app import app
from permit_packets.core.conductors import gec_size, service_conductor, service_conduit
from permit_packets.core.equipment import find_equipment
from permit_packets.jurisdictions import KNOWN, jurisdiction_for
from permit_packets.jurisdictions.monte_sereno_ca import MONTE_SERENO
from tests.api_helpers import with_pdf
from tests.packet_helpers import complete_inputs

os.environ["DEMO_PASSWORD"] = "test-password"
PACKET_URL = "/api/jobs/service-upgrade/packet"
METER_MAIN_400 = "Siemens MK0402L1400SCS meter-main, 400 A (Class 320), two 200 A mains"
PANEL_200 = "Square D Homeline HOM3060M200PC, 200 A main breaker"
CHARGER = "Tesla Wall Connector (Gen 3)"


@pytest.fixture
def client() -> TestClient:
    signed_in = TestClient(app)
    assert signed_in.post("/api/signin", json={"password": "test-password"}).status_code == 200
    return signed_in


def _payload(jurisdiction=MONTE_SERENO, **changes) -> dict:
    payload = complete_inputs("service_upgrade", jurisdiction)
    payload.update(
        existing_service_amps=200, new_service_amps=400, equipment="meter_main", bus_amps=400,
        panel_model=METER_MAIN_400, panel_bus_amps=225, equipment_aic_ka=22, service_drop="underground",
        panels=[{"model": PANEL_200, "bus_amps": 225, "location": "Garage, north wall", "feeder_ft": 10},
                {"model": PANEL_200, "bus_amps": 225, "location": "Garage, north wall", "feeder_ft": 14}],
        ev_charger={"charger_model": CHARGER, "charger_amps": 48, "run_ft": 22, "location": "exterior_wall",
                    "venting_required": False},
        planned_loads=[], gec_size="#1/0 Cu",
    )
    payload["plan"]["markers"].update(panel_two=[520, 500], charger=[540, 480])
    payload.update(changes)
    return payload


def _checks(body: dict) -> dict:
    return {check["name"]: check for check in body["checks"]}


# The conductor tables, now up to 600 kcmil.

def test_a_400_amp_service_takes_400_kcmil_copper_or_600_kcmil_aluminum_at_83_percent():
    # NEC 310.12: 400 A x 83% = 332 A. Table 310.16, 75 C: 400 kcmil Cu 335 A, 600 kcmil Al 340 A.
    assert service_conductor(400, "copper").size == "400"
    assert service_conductor(400, "aluminum").size == "600"


def test_table_250_66_gives_a_1_0_copper_gec_for_over_350_through_600_kcmil():
    copper, aluminum = service_conductor(400, "copper"), service_conductor(400, "aluminum")
    assert gec_size(copper, "copper", "water_pipe") == "1/0"
    assert gec_size(aluminum, "aluminum", "water_pipe") == "1/0"
    # 250.66(A) and (B): a rod never needs more than #6, concrete-encased never more than #4.
    assert gec_size(copper, "copper", "rods") == "6"
    assert gec_size(copper, "copper", "concrete_encased") == "4"


def test_aluminum_over_250_through_500_kcmil_takes_a_2_copper_gec():
    # Table 250.66: aluminum over 250 kcmil through 500 kcmil is #2 Cu (it used to stop at 350 here).
    assert gec_size(service_conductor(300, "aluminum"), "aluminum", "water_pipe") == "2"


def test_a_400_kcmil_mast_fits_2_1_2_inch_rmc():
    # Chapter 9: 3 x 0.5863 sq in = 1.759 sq in; 2-1/2 in RMC holds 1.946 sq in at 40%.
    assert service_conduit(service_conductor(400, "copper"), "RMC") == '2-1/2"'


# The 400 A packet

def test_a_400_amp_upgrade_feeds_two_panels_from_two_200_amp_mains(client):
    body = with_pdf(client, PACKET_URL, _payload())
    checks = _checks(body)
    assert body["ready"] is True, [c for c in body["checks"] if not c["passed"]]
    assert checks["Service disconnects"]["passed"]
    assert "each in its own compartment (230.71(B))" in checks["Service disconnects"]["result"]
    # Each feeder is sized at 75 C for its 200 A main (310.16), not at 83%: it does not carry the whole home.
    for name in ("Feeder, main 1 to panel 1", "Feeder, main 2 to panel 2"):
        assert checks[name]["result"].startswith("#3/0 Cu THWN-2 + #6 EGC, 200 A at 75")
    assert checks["Grounding electrode conductor"]["result"] == "Rods: #6 Cu; Water pipe: #1/0 Cu"
    assert "outdoor emergency disconnects" in checks["Emergency disconnect"]["result"]
    assert body["new_service_amps"] == 400


def test_each_main_carries_its_own_panel(client):
    body = with_pdf(client, PACKET_URL, _payload())
    checks = _checks(body)
    assert "the home's existing loads (220.82)" in checks["Main 1 load"]["result"]
    # Panel 2 carries the 48 A charger at 100%: 11,520 VA / 240 V = 48 A.
    assert checks["Main 2 load"]["result"].startswith("48.0 A of new loads")


def test_400_amps_needs_a_meter_main_and_its_two_panels(client):
    assert client.post(PACKET_URL, json=_payload(equipment="main_panel")).status_code == 422
    assert client.post(PACKET_URL, json=_payload(panels=[])).status_code == 422


def test_two_panels_are_only_for_400_amps(client):
    payload = _payload(new_service_amps=200, bus_amps=200, panel_model=PANEL_200, panel_bus_amps=200)
    assert client.post(PACKET_URL, json=payload).status_code == 422


def test_a_meter_main_without_two_service_disconnects_fails_the_check(client):
    body = with_pdf(client, PACKET_URL, _payload(panel_model="Milbank U5168-XTL-200 meter-main, 200 A"))
    check = _checks(body)["Service disconnects"]
    assert check["passed"] is False and "does not have two 200 A service disconnects" in check["result"]


def test_an_unlisted_meter_main_is_flagged_to_confirm_230_71(client):
    body = with_pdf(client, PACKET_URL, _payload(panel_model="Brand X 400 A meter-main", data_sheet_attached=True))
    assert any("two 200 A service disconnects, each in its own" in flag for flag in body["flags"])


def test_the_siemens_meter_main_is_in_the_library_as_class_320_with_two_mains():
    sheet = find_equipment(METER_MAIN_400, "panel")
    assert sheet is not None and sheet.class_320 and sheet.service_disconnects == 2 and sheet.main_amps == 200
    assert sheet.data_sheet_path().exists()


def test_the_400_amp_packet_attaches_the_meter_main_panel_and_charger_sheets(client):
    from tests.test_service_upgrade import _text
    text = _text(with_pdf(client, PACKET_URL, _payload()))
    assert "MK0402L1400SCS" in text and "Homeline" in text and "Wall Connector" in text
    assert "METER-MAIN, CLASS 320" in text
    assert "Panel 2, 225 A bus, fed from main 2 (200 A), new" in text


# The EV charger with the upgrade

def test_the_ev_charger_is_sized_and_on_panel_2(client):
    body = with_pdf(client, PACKET_URL, _payload())
    check = _checks(body)["EV circuit"]
    assert check["passed"]
    assert check["result"].startswith("60 A breaker in Panel 2 for 48 A x 125% (625.42); #6 Cu")
    statuses = {row["item"]: row["status"] for row in body["checklist_status"]}
    ev_rows = [item for item in statuses if item.startswith("EV charger: ")]
    assert ev_rows and all(statuses[item] == "Ready" for item in ev_rows)


def test_the_ev_charger_can_go_with_a_200_amp_upgrade_too(client):
    payload = complete_inputs("service_upgrade", MONTE_SERENO)
    payload["planned_loads"] = []
    payload["ev_charger"] = {"charger_model": CHARGER, "charger_amps": 40, "run_ft": 30, "location": "attached_garage",
                             "venting_required": False}
    payload["plan"]["markers"]["charger"] = [540, 480]
    body = with_pdf(client, PACKET_URL, payload)
    assert body["ready"] is True
    assert _checks(body)["EV circuit"]["result"].startswith("50 A breaker in the new panel")


def test_an_ev_charger_entered_twice_is_refused(client):
    payload = _payload(planned_loads=[{"label": "EV charger", "va": 11520}])
    assert client.post(PACKET_URL, json=payload).status_code == 422


def test_an_unmarked_charger_leaves_the_plan_row_open(client):
    payload = _payload()
    del payload["plan"]["markers"]["charger"]
    body = with_pdf(client, PACKET_URL, payload)
    rows = {row["item"]: row for row in body["checklist_status"]}
    plan_row = next(row for item, row in rows.items() if item.startswith("EV charger: Plan showing"))
    assert plan_row["status"] == "Open" and "mark the charger" in plan_row["where"]


# Monte Sereno

def test_monte_sereno_is_known_for_ev_chargers_and_service_upgrades():
    assert MONTE_SERENO in KNOWN.values()
    assert MONTE_SERENO.known_for("ev_charger") and MONTE_SERENO.known_for("service_upgrade")
    assert not MONTE_SERENO.known_for("subpanel")
    assert jurisdiction_for("Monte Sereno", "CA") is MONTE_SERENO


def test_monte_sereno_checklists_come_from_its_own_handouts_and_pge():
    ev = MONTE_SERENO.checklist_for("ev_charger")
    service = MONTE_SERENO.checklist_for("service_upgrade")
    assert "4019/Electric-Vehicle-Charger-Installation" in ev.source_url
    assert "3795/Electrical-Panel-Replacement" in service.source_url
    sources = {requirement.source for requirement in service.items if requirement.source}
    assert any("greenbook" in source for source in sources)
    assert "2025 California Electrical Code" in MONTE_SERENO.code_note and "NS-248" in MONTE_SERENO.code_note


def test_monte_sereno_counts_los_gatos_mailing_addresses_by_location():
    # Monte Sereno homes often carry a Los Gatos 95030 address; the Census place decides the city.
    assert MONTE_SERENO.permit_area_by_location


def test_monte_sereno_uses_los_gatos_title_24_design_temperature():
    assert MONTE_SERENO.design_ambient_f == 88
    assert "Los Gatos" in MONTE_SERENO.design_ambient_label


def test_monte_sereno_class_320_rules_are_in_the_service_notes():
    notes = " ".join(note.text for note in MONTE_SERENO.checklist_for("service_upgrade").notes)
    assert "Class 320" in notes and "320 Amperes Continuous" in notes
    assert "36 in horizontally from the gas meter" in notes
