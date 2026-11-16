"""The DXF export: offered only to clients who have it, one file per drawing, true to the printed sheets."""
import io
import json
import zipfile

import ezdxf
import pytest
from fastapi.testclient import TestClient

from app import app
from permit_packets.clients import CLIENTS
from permit_packets.jurisdictions import KNOWN
from tests.packet_helpers import complete_inputs

BY_KEY = {j.key: j for j in KNOWN.values()}
PASSWORDS = {key: f"pw-{key}-0123456789" for key in CLIENTS if key != "demo"}


@pytest.fixture(autouse=True)
def passwords(monkeypatch):
    monkeypatch.setenv("CLIENT_PASSWORDS", json.dumps(PASSWORDS))
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password")


def sign_in(key: str) -> TestClient:
    session = TestClient(app)
    assert session.post("/api/signin", json={"password": PASSWORDS[key]}).status_code == 200
    return session


def test_every_client_login_has_cad_files_but_the_demo_does_not():
    assert {key for key, client in CLIENTS.items() if client.cad} == set(PASSWORDS)
    assert sign_in("jacob").get("/api/client").json()["cad"] is True
    demo = TestClient(app)
    assert demo.post("/api/signin", json={"password": "demo-password"}).status_code == 200
    assert demo.get("/api/client").json()["cad"] is False


def test_the_demo_is_refused():
    demo = TestClient(app)
    demo.post("/api/signin", json={"password": "demo-password"})
    payload = complete_inputs("ev_charger", BY_KEY["nashville-tn"])
    assert demo.post("/api/jobs/ev-charger/cad", json=payload).status_code == 404


@pytest.mark.parametrize("key, city", [("erke", "nashville-tn"), ("elc", "san-francisco-ca"), ("jbee", "chandler-az")])
def test_other_cities_export(key, city):
    payload = complete_inputs("ev_charger", BY_KEY[city])
    response = sign_in(key).post("/api/jobs/ev-charger/cad", json=payload)
    assert response.status_code == 200, response.text
    assert len(zipfile.ZipFile(io.BytesIO(response.content)).namelist()) == 3


@pytest.mark.parametrize("job_type, slug, sheets", [
    ("ev_charger", "ev-charger", {"site-plan", "one-line", "panel-schedule"}),
    ("service_upgrade", "service-upgrade", {"site-plan", "riser", "panel-schedule"}),
])
def test_jacob_gets_a_dxf_per_drawing(job_type, slug, sheets):
    payload = complete_inputs(job_type, BY_KEY["bellevue-wa"])
    response = sign_in("jacob").post(f"/api/jobs/{slug}/cad", json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert {name.removeprefix(f"{slug}-permit-").removesuffix(".dxf") for name in archive.namelist()} == sheets
    for name in archive.namelist():
        doc = ezdxf.read(io.StringIO(archive.read(name).decode("utf-8")))
        assert not list(doc.audit().errors)
        assert len(doc.modelspace()) > 0


def test_the_site_plan_is_in_true_feet_with_a_sheet_layout():
    payload = complete_inputs("ev_charger", BY_KEY["bellevue-wa"])
    response = sign_in("jacob").post("/api/jobs/ev-charger/cad", json=payload)
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    doc = ezdxf.read(io.StringIO(archive.read("ev-charger-permit-site-plan.dxf").decode("utf-8")))
    assert doc.header["$INSUNITS"] == 2  # feet
    assert "SHEET" in doc.layouts.names()
    layers = {layer.dxf.name for layer in doc.layers}
    assert {"C-PROP-LINE", "E-POWR-WIRE", "G-ANNO-NPLT"} <= layers
    lot = [e for e in doc.modelspace().query("LWPOLYLINE") if e.dxf.layer == "C-PROP-LINE"][0]
    xs = [p[0] for p in lot.get_points()]
    labels = {t.dxf.text for t in doc.modelspace().query("TEXT")}
    assert f"{round(max(xs) - min(xs))} ft" in labels  # the drawn lot is as wide as its printed dimension
