"""Per-job-type checklists: a city's own, else the general one."""
from permit_packets.jurisdictions import (
    ORO_VALLEY,
    Checklist,
    Requirement,
    jurisdiction_by_key,
    jurisdiction_for,
    jurisdiction_json,
)
from permit_packets.jurisdictions.general import GENERAL_CHECKLISTS


def test_a_known_city_without_a_checklist_for_a_job_type_falls_back_to_the_general_one(monkeypatch):
    general = Checklist(items=(Requirement("Permit application", "application"),))
    monkeypatch.setitem(GENERAL_CHECKLISTS, "dummy", general)
    assert ORO_VALLEY.known
    assert ORO_VALLEY.checklist_for("dummy") is general
    assert not ORO_VALLEY.known_for("dummy")
    assert ORO_VALLEY.known_for("ev_charger")
    assert ORO_VALLEY.checklist_for("ev_charger") is ORO_VALLEY.checklists["ev_charger"]
    assert jurisdiction_json(ORO_VALLEY, "dummy")["known"] is False
    assert jurisdiction_json(ORO_VALLEY, "dummy")["checklist"] == ["Permit application"]


def test_an_unknown_city_gets_the_general_checklist_and_says_so():
    yuma = jurisdiction_for("Yuma", "AZ")
    assert not yuma.known_for("ev_charger")
    assert yuma.checklist_for("ev_charger") is GENERAL_CHECKLISTS["ev_charger"]
    assert jurisdiction_by_key("nowhere", "Yuma", "AZ").label == "Yuma, AZ"


def test_jurisdiction_json_has_exactly_the_keys_the_page_reads():
    assert set(jurisdiction_json(ORO_VALLEY, "ev_charger")) == {
        "key", "name", "state", "known", "code_name", "code_note", "department", "phone", "email",
        "website", "website_label", "submit_how", "source_url", "sets_required", "needs_parcel_number",
        "label", "checklist",
    }
    body = jurisdiction_json(ORO_VALLEY, "ev_charger")
    assert body["known"] is True
    assert body["sets_required"] == 2
    assert body["source_url"].endswith("electric-car-charging-stations.pdf")
    assert len(body["checklist"]) == 7


def test_nashville_census_place_name_resolves_to_metro_nashville():
    from permit_packets.core.property_lookup import place_name
    from permit_packets.jurisdictions import NASHVILLE

    assert place_name("Nashville-Davidson metropolitan government (balance)") == "Nashville"
    assert place_name("Las Vegas city") == "Las Vegas"
    assert jurisdiction_for(place_name("Nashville-Davidson metropolitan government (balance)"), "TN") is NASHVILLE
    body = jurisdiction_json(NASHVILLE, "ev_charger")
    assert body["known"] is True
    assert body["needs_parcel_number"] is True
    assert "2023 NEC" in body["code_note"]
    assert jurisdiction_json(NASHVILLE, "service_upgrade")["known"] is True
    assert jurisdiction_json(NASHVILLE, "subpanel")["known"] is False


def test_a_nashville_view_uses_metro_aerial_first():
    from io import BytesIO

    import httpx
    from PIL import Image

    from permit_packets.core import property_lookup
    from permit_packets.core.property_plan import PlanView

    buffer = BytesIO()
    Image.effect_noise((10, 10), 60).convert("RGB").save(buffer, format="JPEG")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=buffer.getvalue())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        _, credit = property_lookup.fetch_aerial(PlanView(36.1499, -86.8258, 30), client)
        assert seen == ["maps.nashville.gov"]
        assert "Metro Nashville" in credit
        seen.clear()
        _, credit = property_lookup.fetch_aerial(PlanView(36.1699, -115.14, 30), client)
        assert seen and "maps.nashville.gov" not in seen


def test_san_francisco_uses_dbi_e02_and_pge():
    from permit_packets.core.property_lookup import COUNTIES, place_name
    from permit_packets.jurisdictions import SAN_FRANCISCO

    assert jurisdiction_for(place_name("San Francisco city"), "CA") is SAN_FRANCISCO
    body = jurisdiction_json(SAN_FRANCISCO, "ev_charger")
    assert body["known"] is True and body["code_name"] == "CEC"
    assert "2025 San Francisco Electrical Code" in body["code_note"]
    assert SAN_FRANCISCO.utility_short == "PG&E"
    assert "06075" in COUNTIES


def test_a_contractor_logo_goes_on_the_packet_and_bad_logos_are_refused():
    import base64
    import json
    from io import BytesIO
    from pathlib import Path

    from fastapi.testclient import TestClient
    from PIL import Image

    from app import app

    client = TestClient(app)
    assert client.post("/api/signin", json={"password": "test-password"}).status_code == 200
    case = json.loads((Path(__file__).parent / "golden/cases/las_vegas_general_sample_mode.json").read_text())
    case.pop("plan")
    buffer = BytesIO()
    Image.new("RGBA", (300, 120), (240, 120, 20, 255)).save(buffer, format="PNG")
    with_logo = client.post("/api/jobs/ev-charger/packet",
                            json={**case, "contractor_logo_base64": base64.b64encode(buffer.getvalue()).decode()})
    plain = client.post("/api/jobs/ev-charger/packet", json=case)
    assert with_logo.status_code == plain.status_code == 200
    assert len(with_logo.json()["pdf"]) > len(plain.json()["pdf"])
    bad = client.post("/api/jobs/ev-charger/packet",
                      json={**case, "contractor_logo_base64": base64.b64encode(b"not an image").decode()})
    assert bad.status_code == 422


def test_charlotte_uses_mecklenburg_tip_and_duke_energy():
    from permit_packets.core.property_lookup import COUNTIES, LOCAL_AERIALS, place_name
    from permit_packets.jurisdictions import CHARLOTTE

    assert jurisdiction_for(place_name("Charlotte city"), "NC") is CHARLOTTE
    assert CHARLOTTE.utility == "Duke Energy"
    assert jurisdiction_json(CHARLOTTE, "ev_charger")["known"] is True
    assert jurisdiction_json(CHARLOTTE, "service_upgrade")["known"] is True
    assert "2023 North Carolina Electrical Code" in jurisdiction_json(CHARLOTTE, "ev_charger")["code_note"]
    assert "37119" in COUNTIES
    assert any("nconemap" in url for _, url, _ in LOCAL_AERIALS)


def test_mesa_uses_mesa_electrical_code_amendments_and_srp():
    from permit_packets.core.property_lookup import COUNTIES, LOCAL_AERIALS, place_name
    from permit_packets.jurisdictions import MESA

    assert jurisdiction_for(place_name("Mesa city"), "AZ") is MESA
    assert MESA.utility_short == "SRP"
    ev = jurisdiction_json(MESA, "ev_charger")
    assert ev["known"] is True and "2023 NEC with Mesa amendments" in ev["code_note"]
    assert jurisdiction_json(MESA, "service_upgrade")["known"] is True
    assert "04013" in COUNTIES
    assert any("mcassessor" in url for _, url, _ in LOCAL_AERIALS)


def test_blank_aerial_is_skipped():
    from io import BytesIO

    from PIL import Image

    from permit_packets.core.property_lookup import _blank

    def jpg(color_or_image):
        out = BytesIO()
        (color_or_image if isinstance(color_or_image, Image.Image) else Image.new("RGB", (40, 40), color_or_image)).save(out, "JPEG")
        return out.getvalue()

    noisy = Image.effect_noise((40, 40), 60).convert("RGB")
    assert _blank(jpg((255, 255, 255)))
    assert not _blank(jpg(noisy))
