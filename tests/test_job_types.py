"""The job-type registry, the client profile and the generic routes."""
import base64
import json
import re
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from permit_packets.clients import CLIENTS, Client, current_client
from permit_packets.job_types import REGISTRY, get_job_type

from tests.test_ev_golden import GOLDEN, to_current_request

os.environ["DEMO_PASSWORD"] = "test-password"

# One deterministic request per registered type, from the golden cases.
SAMPLE_CASES = {"ev_charger": "oro_valley_attached_no_plan"}


@pytest.fixture
def client() -> TestClient:
    signed_in = TestClient(app)
    assert signed_in.post("/api/signin", json={"password": "test-password"}).status_code == 200
    return signed_in


def _sample(key: str) -> dict:
    return to_current_request(json.loads((GOLDEN / "cases" / f"{SAMPLE_CASES[key]}.json").read_text()))


def test_job_types_lists_only_what_the_client_bought(client):
    body = client.get("/api/job-types").json()["job_types"]
    assert [job_type["key"] for job_type in body] == ["ev_charger"]
    ev = body[0]
    assert (ev["slug"], ev["short_label"], ev["icon"], ev["feature_page"]) == ("ev-charger", "EV", "ev", 2)
    assert ev["route_between"] == ["panel", "charger"]
    assert [marker["letter"] for marker in ev["markers"]] == ["P", "EV"]
    assert len(ev["documents"]) == 7


def test_job_types_need_a_session():
    assert TestClient(app).get("/api/job-types").status_code == 401
    assert TestClient(app).post("/api/jobs/ev-charger/packet", json={}).status_code == 401


def test_an_unknown_slug_is_a_404(client):
    assert client.post("/api/jobs/nope/packet", json={}).status_code == 404
    assert client.post("/api/jobs/nope/documents", json={}).status_code == 404


def test_a_registered_type_the_client_did_not_buy_is_a_404(client, monkeypatch):
    monkeypatch.setattr(app_module, "current_client", lambda: Client("other", "Other Co", ()))
    assert client.get("/api/job-types").json() == {"job_types": []}
    assert client.post("/api/jobs/ev-charger/packet", json=_sample("ev_charger")).status_code == 404
    assert client.post("/api/jobs/ev-charger/documents", json=_sample("ev_charger")).status_code == 404


def test_bad_input_is_a_422_not_a_500(client):
    assert client.post("/api/jobs/ev-charger/packet", json={}).status_code == 422
    assert client.post("/api/jobs/ev-charger/packet", json={**_sample("ev_charger"), "charger_amps": 5}).status_code == 422


def test_the_zip_keeps_its_name(client):
    response = client.post("/api/jobs/ev-charger/documents", json=_sample("ev_charger"))
    assert 'filename="ev-permit-documents-demo.zip"' in response.headers["content-disposition"]


def test_an_unknown_job_type_on_a_property_call_is_refused(client):
    assert client.post("/api/property", json={"address": "10 Main St", "job_type": "nope"}).status_code == 422


def test_the_default_client_is_the_demo(monkeypatch):
    monkeypatch.delenv("PERMIT_CLIENT", raising=False)
    assert current_client().key == "demo"
    assert current_client().job_types == ("ev_charger",)


def test_an_unknown_client_raises(monkeypatch):
    monkeypatch.setenv("PERMIT_CLIENT", "typo")
    with pytest.raises(ValueError, match="Unknown PERMIT_CLIENT"):
        current_client()


def test_a_client_with_an_unregistered_job_type_raises(monkeypatch):
    monkeypatch.setitem(CLIENTS, "broken", Client("broken", "Broken Co", ("roof_solar",)))
    monkeypatch.setenv("PERMIT_CLIENT", "broken")
    with pytest.raises(ValueError, match="unregistered job types: roof_solar"):
        current_client()


def test_slugs_and_keys_are_unique():
    assert len({job_type.slug for job_type in REGISTRY.values()}) == len(REGISTRY)
    for key, job_type in REGISTRY.items():
        assert job_type.key == key
        assert get_job_type(job_type.slug) is job_type


@pytest.mark.parametrize("key", sorted(REGISTRY))
def test_every_type_has_one_document_per_page(client, key):
    assert key in SAMPLE_CASES, "add a sample case for the new job type"
    job_type = REGISTRY[key]
    response = client.post(f"/api/jobs/{job_type.slug}/packet", json=_sample(key))
    assert response.status_code == 200
    body = response.json()
    assert len(job_type.documents) == len(body["pages"])
    assert body["documents"] == [
        {"file_stem": d.file_stem, "title": d.title} for d in job_type.documents]
    assert 0 <= body["feature_page"] < len(body["pages"])
    assert {marker.key for marker in job_type.markers} >= set(job_type.route_between or ())
    assert base64.b64decode(body["pdf"]).startswith(b"%PDF")


def test_ev_response_carries_the_review_copy(client):
    body = client.post("/api/jobs/ev-charger/packet", json=_sample("ev_charger")).json()
    assert [row["label"] for row in body["summary"]] == ["Service load", "Spare capacity", "Breaker", "Wire"]
    assert body["build_steps"][0] == "Oro Valley, AZ checklist applied, 7 items"
    assert body["build_steps"][-1] == "Permit data filled in, 7 pages built"
    assert body["build_steps"][3] == "Schematic site plan drawn"
    assert body["submission_email"]["subject"] == "EV charger permit submittal: 123 Sample St"
    assert body["submission_email"]["body"].endswith("Thank you,\nSample Electric, LLC")


def test_over_capacity_summary_names_the_overage(client):
    case = json.loads((GOLDEN / "cases" / "over_capacity_worst_case.json").read_text())
    body = client.post("/api/jobs/ev-charger/packet", json=to_current_request(case)).json()
    assert body["summary"][1]["label"] == "Over capacity by"
    assert body["summary"][1]["value"].endswith(" A")


def test_the_page_loads_its_assets_with_a_version(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "{{ASSET_VERSION}}" not in response.text
    versions = re.findall(r'(?:src|href)="/assets/[^"?]+\?v=([0-9a-f]{10})"', response.text)
    assert len(versions) == 3
    assert len(set(versions)) == 1
    assert versions[0] == app_module.ASSET_VERSION


def test_assets_are_served_but_the_pages_are_not(client):
    assert client.get("/assets/js/app.js").status_code == 200
    assert client.get("/assets/css/app.css").status_code == 200
    assert client.get("/assets/js/job-types/ev-charger.js").status_code == 200
    assert client.get("/assets/index.html").status_code == 404
    assert client.get("/assets/../index.html").status_code == 404
    assert client.get("/assets/signin.html").status_code == 404


def test_the_asset_version_follows_the_files(tmp_path, monkeypatch):
    (tmp_path / "a.js").write_text("one")
    monkeypatch.setattr(app_module, "ASSETS", tmp_path)
    first = app_module._asset_version()
    (tmp_path / "a.js").write_text("two")
    assert app_module._asset_version() != first
