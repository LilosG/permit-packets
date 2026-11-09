"""Every EV packet has to come out the way it did before the job-type refactor.

tests/golden/cases holds request payloads in the original shape, and
tests/golden/snapshots holds what the app produced for them. New response keys
are allowed; changed or missing ones are not.
"""
from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pypdfium2
import pytest
from fastapi.testclient import TestClient

from app import app

os.environ["DEMO_PASSWORD"] = "test-password"

GOLDEN = Path(__file__).parent / "golden"
CASE_NAMES = sorted(path.stem for path in (GOLDEN / "cases").glob("*.json"))
PACKET_URL = "/api/jobs/ev-charger/packet"
DOCUMENTS_URL = "/api/jobs/ev-charger/documents"


def to_current_request(payload: dict) -> dict:
    """Maps a case in the original request shape to what the routes take now."""
    plan = payload.get("plan")
    if plan is None:
        return payload
    markers = {name: plan[name] for name in ("panel", "charger")}
    rest = {key: value for key, value in plan.items() if key not in markers}
    return {**payload, "plan": {**rest, "markers": markers}}


@pytest.fixture(scope="module")
def client() -> TestClient:
    signed_in = TestClient(app)
    assert signed_in.post("/api/signin", json={"password": "test-password"}).status_code == 200
    return signed_in


def _load(folder: str, name: str) -> dict:
    return json.loads((GOLDEN / folder / f"{name}.json").read_text(encoding="utf-8"))


def test_every_case_has_a_snapshot():
    assert CASE_NAMES
    assert CASE_NAMES == sorted(path.stem for path in (GOLDEN / "snapshots").glob("*.json"))


@pytest.mark.parametrize("name", CASE_NAMES)
def test_packet_matches_its_snapshot(client, name):
    snapshot = _load("snapshots", name)
    request = to_current_request(_load("cases", name))
    response = client.post(PACKET_URL, json=request)
    assert response.status_code == 200
    body = response.json()
    for key, value in snapshot["response"].items():
        assert key in body, key
        assert body[key] == value, key
    assert len(body["pages"]) == snapshot["page_count"]
    document = pypdfium2.PdfDocument(base64.b64decode(body["pdf"]))
    try:
        text = [page.get_textpage().get_text_bounded() for page in document]
    finally:
        document.close()
    assert len(text) == snapshot["page_count"]
    for number, (got, want) in enumerate(zip(text, snapshot["page_text"]), start=1):
        assert got == want, f"page {number}"


@pytest.mark.parametrize("name", CASE_NAMES)
def test_documents_zip_matches_its_snapshot(client, name):
    snapshot = _load("snapshots", name)
    response = client.post(DOCUMENTS_URL, json=to_current_request(_load("cases", name)))
    assert response.status_code == 200
    assert ZipFile(BytesIO(response.content)).namelist() == snapshot["zip_names"]
