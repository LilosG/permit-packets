"""Each client signs in with their own password and sees only their own cities, logo and job types."""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from permit_packets.clients import ALL_JOB_TYPES, CLIENTS, Client
from permit_packets.jurisdictions import KNOWN
from tests.packet_helpers import complete_inputs, page_texts
from tests.api_helpers import with_pdf

PASSWORDS = {key: f"pw-{key}-0123456789" for key in CLIENTS if key != "demo"}
CITIES = {"erke": "nashville-tn", "elc": "san-francisco-ca", "thee-electrician": "san-francisco-ca", "jbee": "chandler-az", "bigred": "las-vegas-nv"}
LOGOS = {"erke": "erke.png", "elc": "elc.png", "thee-electrician": "thee.png", "jbee": "jbee.png", "bigred": "bigred.png"}
BY_KEY = {j.key: j for j in KNOWN.values()}
EXTRA_CITIES: dict[str, tuple[str, ...]] = {}
OTHER = {"erke": "mesa-az", "elc": "nashville-tn", "thee-electrician": "mesa-az", "jbee": "san-francisco-ca", "bigred": "mesa-az"}


@pytest.fixture(autouse=True)
def passwords(monkeypatch):
    monkeypatch.setenv("CLIENT_PASSWORDS", json.dumps(PASSWORDS))
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password")


def sign_in(password: str) -> TestClient:
    session = TestClient(app)
    assert session.post("/api/signin", json={"password": password}).status_code == 200
    return session


def payload(city_key: str, job_type: str = "ev_charger") -> dict:
    return complete_inputs(job_type, BY_KEY[city_key])


def text_of(pdf_b64: str) -> str:
    import base64
    return "\n".join(page_texts(base64.b64decode(pdf_b64)))


def test_the_clients_are_set_up():
    assert set(CLIENTS) == {"demo", *PASSWORDS}
    for key, city in CITIES.items():
        client = CLIENTS[key]
        assert client.jurisdiction_keys[0] == city
        assert client.jurisdiction_keys == (city,) + EXTRA_CITIES.get(key, ())
        assert client.job_types == ALL_JOB_TYPES
        assert client.logo == LOGOS[key]
        assert client.company_name and client.website.startswith("https://")


def test_a_wrong_password_is_refused():
    assert TestClient(app).post("/api/signin", json={"password": "nope"}).status_code == 401


@pytest.mark.parametrize("key", CITIES)
def test_client_sees_only_their_cities_logo_and_all_job_types(key):
    session = sign_in(PASSWORDS[key])
    info = session.get("/api/client").json()
    assert info["key"] == key and info["demo"] is False
    assert [c["key"] for c in info["cities"]] == [CITIES[key], *EXTRA_CITIES.get(key, ())]
    assert info["company_name"] == CLIENTS[key].company_name
    assert info["logo"] == (f"/assets/logos/{LOGOS[key]}" if LOGOS[key] else "")
    types = [t["key"] for t in session.get("/api/job-types").json()["job_types"]]
    assert types == list(ALL_JOB_TYPES)


@pytest.mark.parametrize("key", CITIES)
def test_client_gets_403_for_another_city(key):
    session = sign_in(PASSWORDS[key])
    other = payload(OTHER[key])
    assert session.post("/api/jobs/ev-charger/packet", json=other).status_code == 403
    assert session.post("/api/jobs/ev-charger/documents", json=other).status_code == 403
    assert session.post("/api/jobs/ev-charger/pdf", json=other).status_code == 403
    unknown = {**payload(CITIES[key]), "jurisdiction_key": "general", "city": "Nowhere", "state": "ZZ"}
    assert session.post("/api/jobs/ev-charger/packet", json=unknown).status_code == 403


@pytest.mark.parametrize("key", CITIES)
def test_client_packet_has_no_demo_marks_and_names_the_company(key):
    session = sign_in(PASSWORDS[key])
    text = text_of(with_pdf(session, "/api/jobs/ev-charger/packet", payload(CITIES[key]))["pdf"])
    assert "DEMO" not in text
    assert "NOT FOR SUBMISSION" not in text


def test_demo_login_has_every_city_and_no_demo_marks():
    session = sign_in("demo-password")
    info = session.get("/api/client").json()
    assert info["demo"] is True
    assert {c["key"] for c in info["cities"]} == set(BY_KEY)
    text = text_of(with_pdf(session, "/api/jobs/ev-charger/packet", payload("oro-valley-az"))["pdf"])
    assert "DEMO" not in text
    assert "NOT FOR SUBMISSION" not in text


def test_a_session_cannot_be_moved_to_another_client():
    session = sign_in(PASSWORDS["erke"])
    cookie = session.cookies.get("permit_demo_session")
    expires, _, rest = cookie.partition(".")
    forged = f"{expires}.demo.{rest.partition('.')[2]}"
    other = TestClient(app)
    other.cookies.set("permit_demo_session", forged)
    assert other.get("/api/job-types").status_code == 401


def test_overrides_beat_the_city_default():
    sf = BY_KEY["san-francisco-ca"]
    plain = Client("x", "X", ())
    assert plain.sheet_size_for(sf) == sf.sheet_size and plain.single_pdf_only_for(sf) == sf.single_pdf_only
    assert Client("x", "X", (), sheet_size="tabloid").sheet_size_for(sf) == "tabloid"
    assert Client("x", "X", (), single_pdf_only=not sf.single_pdf_only).single_pdf_only_for(sf) is (not sf.single_pdf_only)


def test_bad_client_passwords_json_is_a_503(monkeypatch):
    monkeypatch.setenv("CLIENT_PASSWORDS", "not json")
    assert TestClient(app).post("/api/signin", json={"password": "x"}).status_code == 503


def _title(pdf_b64: str) -> str:
    import base64
    import pypdfium2
    document = pypdfium2.PdfDocument(base64.b64decode(pdf_b64))
    try:
        return document.get_metadata_dict().get("Title", "")
    finally:
        document.close()


@pytest.mark.parametrize("job_type,slug", [
    ("ev_charger", "ev-charger"), ("service_upgrade", "service-upgrade"),
    ("subpanel", "subpanel"), ("appliance_circuit", "appliance-circuit"),
])
def test_no_login_puts_demo_in_titles_or_zip_names(job_type, slug):
    client_session, demo_session = sign_in(PASSWORDS["erke"]), sign_in("demo-password")
    mine = with_pdf(client_session, f"/api/jobs/{slug}/packet", payload("nashville-tn", job_type))
    demo = with_pdf(demo_session, f"/api/jobs/{slug}/packet", payload("nashville-tn", job_type))
    assert "demo" not in _title(mine["pdf"]).lower()
    assert "demo" not in _title(demo["pdf"]).lower()
    mine_zip = client_session.post(f"/api/jobs/{slug}/documents", json=payload("nashville-tn", job_type))
    demo_zip = demo_session.post(f"/api/jobs/{slug}/documents", json=payload("nashville-tn", job_type))
    assert "demo" not in mine_zip.headers["content-disposition"]
    assert mine_zip.headers["content-disposition"].endswith('-documents.zip"')
    assert "demo" not in demo_zip.headers["content-disposition"]
    assert demo_zip.headers["content-disposition"].endswith('-documents.zip"')


def _sheet_size(response) -> str:
    return response.json()["sheet_size"]


def test_request_sheet_size_overrides_client_and_city_for_client_logins(monkeypatch):
    session = sign_in(PASSWORDS["elc"])  # San Francisco's default is its own sheet size
    city_default = BY_KEY["san-francisco-ca"].sheet_size
    other = "letter" if city_default == "tabloid" else "tabloid"
    base = payload("san-francisco-ca")
    base.pop("sheet_size", None)
    assert _sheet_size(session.post("/api/jobs/ev-charger/packet", json=base)) == city_default
    assert _sheet_size(session.post("/api/jobs/ev-charger/packet", json={**base, "sheet_size": other})) == other
    # A client override beats the city default, and the request still beats the client override.
    monkeypatch.setitem(CLIENTS, "elc", Client(**{**CLIENTS["elc"].__dict__, "sheet_size": other}))
    assert _sheet_size(session.post("/api/jobs/ev-charger/packet", json=base)) == other
    assert _sheet_size(session.post("/api/jobs/ev-charger/packet", json={**base, "sheet_size": city_default})) == city_default


def test_address_suggestions_are_limited_to_the_signed_in_clients_cities_and_the_demo_gets_all(monkeypatch):
    asked = []
    monkeypatch.setattr(app_module, "suggest_addresses", lambda text, client=None, areas=None: asked.append(
        [area.key for area in areas]) or ["suggested"])
    body = {"text": "710 Steiner"}
    assert sign_in(PASSWORDS["elc"]).post("/api/property/suggest", json=body).json() == {"suggestions": ["suggested"]}
    sign_in(PASSWORDS["jbee"]).post("/api/property/suggest", json=body)
    sign_in("demo-password").post("/api/property/suggest", json=body)
    assert asked[0] == ["san-francisco-ca"]
    assert asked[1] == ["chandler-az"]
    assert asked[2] == [j.key for j in KNOWN.values()]
    assert all(j.bbox and j.center for j in KNOWN.values())


def test_sign_out_is_in_the_header_of_every_page_and_lets_a_different_client_sign_in():
    browser = sign_in(PASSWORDS["elc"])
    for page in ("/", "/dashboard"):
        html = browser.get(page).text
        assert 'action="/api/signout"' in html and "Sign out" in html, page
    assert browser.get("/api/client").json()["key"] == "elc"

    out = browser.post("/api/signout", follow_redirects=False)
    assert out.status_code == 303 and out.headers["location"] == "/"
    cleared = out.headers["set-cookie"]
    assert app_module.SESSION_COOKIE in cleared and ("Max-Age=0" in cleared or "expires=" in cleared.lower())
    # The browser now has no session: the API refuses and the pages are the sign-in page again.
    assert browser.get("/api/client").status_code == 401
    assert 'id="signin"' in browser.get("/").text and "Sign out" not in browser.get("/").text
    assert browser.get("/dashboard", follow_redirects=False).status_code == 303

    # The same browser can sign in as someone else, and sees only their cities.
    assert browser.post("/api/signin", json={"password": PASSWORDS["jbee"]}).status_code == 200
    info = browser.get("/api/client").json()
    assert info["key"] == "jbee" and [c["key"] for c in info["cities"]] == ["chandler-az"]


def test_signing_out_when_not_signed_in_still_goes_to_the_sign_in_page():
    response = TestClient(app).post("/api/signout", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/"


def _commercial_payload(key: str) -> dict:
    sample = json.loads((Path(__file__).parent / "samples" / f"{key}.json").read_text())
    return {**sample, "jurisdiction_key": "chico-ca", "city": "Chico", "state": "CA"}


def test_ross_gets_residential_and_commercial_in_chico_only():
    session = sign_in(PASSWORDS["ross"])
    info = session.get("/api/client").json()
    assert info["key"] == "ross" and info["company_name"] == "Ross Constructors Inc" and info["demo"] is False
    assert [c["key"] for c in info["cities"]] == ["chico-ca"]
    types = session.get("/api/job-types").json()["job_types"]
    assert [t["occupancy"] for t in types] == ["residential"] * 4 + ["commercial"] * 2
    assert session.post("/api/jobs/ev-charger/packet", json=payload("mesa-az")).status_code == 403
    for slug, key in (("commercial-subpanel", "commercial_subpanel"), ("commercial-ev-charger", "commercial_ev_charger")):
        body = with_pdf(session, f"/api/jobs/{slug}/packet", _commercial_payload(key))
        assert "DEMO PACKET: NOT FOR SUBMISSION" not in text_of(body["pdf"])
        assert body["jurisdiction"]["name"] == "Chico"
        assert session.post(f"/api/jobs/{slug}/cad", json=_commercial_payload(key)).status_code == 200
    residential = with_pdf(session, "/api/jobs/ev-charger/packet", payload("chico-ca"))
    assert residential["jurisdiction"]["name"] == "Chico"


def test_existing_clients_never_see_commercial():
    for key in CITIES:
        assert not set(CLIENTS[key].job_types) & {"commercial_subpanel", "commercial_ev_charger"}
