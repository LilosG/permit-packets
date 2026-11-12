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
    mesa = jurisdiction_for("Mesa", "AZ")
    assert not mesa.known_for("ev_charger")
    assert mesa.checklist_for("ev_charger") is GENERAL_CHECKLISTS["ev_charger"]
    assert jurisdiction_by_key("nowhere", "Mesa", "AZ").label == "Mesa, AZ"


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
    Image.new("RGB", (10, 10)).save(buffer, format="JPEG")
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
