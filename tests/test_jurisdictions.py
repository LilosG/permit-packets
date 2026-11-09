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
