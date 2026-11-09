"""EV permit packets: the code math, the flags, the PDF and the routes."""
from __future__ import annotations

import base64
import os
import re
from io import BytesIO
from zipfile import ZipFile

import httpx
import pypdfium2
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import app

from permit_packets.core.circuits import WIRES, conduit_size, size_breaker, size_circuit, voltage_drop
from permit_packets.ev_charger import EvJob, build_ev_packet
from permit_packets.ev_packet_pdf import render_ev_packet_pdf
from permit_packets.jurisdictions import EL_CAJON, ORO_VALLEY, jurisdiction_for
from permit_packets.core.load_calculation import HomeLoads, LoadLine, calculate_load
from permit_packets.core.property_lookup import (
    AddressNotFound,
    COUNTIES,
    AerialUnavailable,
    fetch_aerial,
    find_property,
    property_at,
    suggest_addresses,
    tidy_address,
)
from permit_packets.core.property_plan import PlanView, PropertyPlan, clip_to, plan_scale, zoomed_scale

os.environ["DEMO_PASSWORD"] = "test-password"


@pytest.fixture
def client():
    signed_in = TestClient(app)
    assert signed_in.post("/api/signin", json={"password": "test-password"}).status_code == 200
    return signed_in


@pytest.fixture
def public_client():
    return TestClient(app)


HOME = HomeLoads(
    square_feet=3100, range_va=12000, dryer_va=5000, water_heater_va=4500, dishwasher_va=1200,
    disposal_va=900, microwave_va=1500, hot_tub_or_pool_va=1800, cooling_va=7200,
)


SQUARE_LOT = [[250, 250], [750, 250], [750, 750], [250, 750]]


def _aerial() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), "#556b2f").save(buffer, format="JPEG")
    return buffer.getvalue()


def _plan(**changes) -> PropertyPlan:
    values = dict(scale_ft_per_in=30, panel=(400, 500), charger=(600, 500), route=[(500, 400)],
                  buildings=[[(350, 350), (650, 350), (650, 650), (350, 650)]], primary_building=0,
                  lot=[tuple(point) for point in SQUARE_LOT], parcel_number="123-456", aerial_jpeg=_aerial(),
                  credits=["Credit"])
    return PropertyPlan(**{**values, **changes})


def _job(**changes) -> EvJob:
    values = dict(
        customer="Sample Homeowner", address="123 Sample St", contractor="Sample Electric, LLC",
        license_number="ROC 000000", home=HOME, service_amps=200, open_breaker_spaces=2,
        charger_amps=48, location="detached_garage", run_ft=58, trench_ft=55,
    )
    return EvJob(**{**values, **changes})


def _payload(**changes) -> dict:
    home = {"square_feet": 2000, "range_va": 12000, "cooling_va": 7200}
    values = dict(
        customer="Sample", address="123 Sample St", contractor="Sample Electric",
        license_number="ROC 000000", home=home, service_amps=200, open_breaker_spaces=4,
        charger_amps=40, location="attached_garage", run_ft=30, trench_ft=0,
    )
    return {**values, **changes}


def test_worked_load_calculation_matches_the_sample_packet():
    load = calculate_load(HOME, service_amps=200,
                          added_loads=[LoadLine("EV charger", "48 A", 11520)])
    assert load.subtotal_va == 40700
    assert load.demand_va == 22280
    assert load.total_va == 41000
    assert round(load.computed_amps, 1) == 170.8
    assert round(load.spare_amps, 1) == 29.2


def test_dryer_uses_nameplate_and_gas_counts_nothing():
    electric = calculate_load(HomeLoads(square_feet=1000, dryer_va=3000), service_amps=100)
    gas = calculate_load(HomeLoads(square_feet=1000), service_amps=100)
    assert electric.subtotal_va - gas.subtotal_va == 3000


def test_only_the_larger_of_heating_and_cooling_counts():
    load = calculate_load(HomeLoads(square_feet=1000, heating_va=9000, cooling_va=5000), service_amps=100)
    assert load.hvac_va == 9000
    assert load.hvac_label == "Heating"


def test_a_small_home_stays_inside_the_first_10000_va():
    load = calculate_load(HomeLoads(square_feet=1000), service_amps=100)
    assert load.subtotal_va == 7500
    assert load.remainder_va == 0
    assert load.demand_va == 7500


@pytest.mark.parametrize("amps,breaker", [(16, 20), (24, 30), (32, 40), (40, 50), (48, 60), (64, 80), (80, 100)])
def test_breaker_covers_125_percent_of_the_charger(amps, breaker):
    assert size_breaker(amps * 1.25) == breaker


@pytest.mark.parametrize("amps,wire,ground", [(32, "8", "10"), (40, "8", "10"), (48, "6", "10"), (64, "4", "8")])
def test_wire_and_ground_sizes(amps, wire, ground):
    circuit = size_circuit(amps, 20, continuous=True)
    assert (circuit.wire.size, circuit.ground) == (wire, ground)


def test_voltage_drop_matches_the_sample_packet():
    six = next(wire for wire in WIRES if wire.size == "6")
    volts, percent = voltage_drop(48, 58, six)
    assert round(volts, 1) == 2.7
    assert round(percent, 1) == 1.1


def test_a_long_run_upsizes_the_wire_for_voltage_drop():
    circuit = size_circuit(48, 200, continuous=True)
    assert circuit.upsized_for_voltage_drop
    assert circuit.wire.size == "4"
    assert round(circuit.voltage_drop_percent, 1) == 2.5


def test_conduit_has_a_three_quarter_inch_minimum_and_grows_with_wire():
    assert conduit_size(size_circuit(32, 20, continuous=True), "EMT") == '3/4"'
    assert conduit_size(size_circuit(80, 20, continuous=True), "PVC") == '1"'


def test_passing_job_has_no_fix_items():
    packet = build_ev_packet(_job())
    assert packet.ready
    assert packet.disconnect_amps == 60
    assert any("85% of capacity" in flag for flag in packet.flags)
    assert any("811" in flag for flag in packet.flags)


def test_overloaded_service_fails_and_explains_why():
    packet = build_ev_packet(_job(service_amps=100))
    assert not packet.ready
    assert any("over capacity by 70.8 A" in flag for flag in packet.flags)


def test_a_full_panel_fails_the_spaces_check():
    packet = build_ev_packet(_job(open_breaker_spaces=1))
    assert not packet.ready
    assert any("two open spaces" in flag for flag in packet.flags)


def test_attached_garage_under_60_amps_skips_the_disconnect():
    packet = build_ev_packet(_job(location="attached_garage", charger_amps=40, trench_ft=0))
    assert packet.disconnect_amps is None
    assert packet.underground_conduit is None
    assert not any("811" in flag for flag in packet.flags)


@pytest.mark.parametrize("location", ["attached_garage", "detached_garage", "exterior_wall"])
@pytest.mark.parametrize("trench_ft", [0, 40])
def test_pdf_is_seven_pages_for_every_layout(location, trench_ft):
    pdf = render_ev_packet_pdf(build_ev_packet(_job(location=location, trench_ft=trench_ft)))
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page[^s]", pdf)) == 7


def test_pdf_survives_markup_in_typed_text():
    pdf = render_ev_packet_pdf(build_ev_packet(_job(contractor="Smith & Sons <LLC>")))
    assert pdf.startswith(b"%PDF")


def test_packet_route_returns_results_pages_and_pdf(client):
    response = client.post("/api/ev/packet", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert (body["breaker"], body["wire"]) == (50, "#8 AWG Cu")
    assert len(body["pages"]) == 7
    assert base64.b64decode(body["pages"][0]).startswith(b"\xff\xd8")
    assert base64.b64decode(body["pdf"]).startswith(b"%PDF")
    assert any(field["label"] == "Scope of work" for field in body["fields"])


def test_documents_route_returns_one_pdf_per_page(client):
    response = client.post("/api/ev/documents", json=_payload())
    assert response.status_code == 200
    names = ZipFile(BytesIO(response.content)).namelist()
    assert len(names) == 7
    assert names[2] == "03-site-plan.pdf"


def test_a_plan_with_an_aerial_goes_through_the_route(client):
    plan = {"scale_ft_per_in": 30, "panel": [400, 500], "charger": [600, 500], "lot": SQUARE_LOT,
            "aerial_base64": base64.b64encode(_aerial()).decode(), "credits": ["Credit"]}
    response = client.post("/api/ev/packet", json=_payload(plan=plan))
    assert response.status_code == 200
    assert len(response.json()["pages"]) == 7


def test_sample_mode_hides_the_address_and_parcel(client):
    plan = {"scale_ft_per_in": 30, "panel": [400, 500], "charger": [600, 500], "lot": SQUARE_LOT,
            "parcel_number": "13831614010"}
    body = _payload(address="309 Real St, Las Vegas, NV", city="Las Vegas", state="NV", plan=plan, sample_mode=True)
    response = client.post("/api/ev/packet", json=body).json()
    assert response["address"] == "123 Sample St, Las Vegas, NV"
    text = " ".join(page.get_textpage().get_text_bounded()
                    for page in pypdfium2.PdfDocument(base64.b64decode(response["pdf"])))
    assert "309 Real" not in text
    assert "13831614010" not in text
    assert "123 Sample St" in text


def test_routes_need_a_session(public_client):
    assert public_client.post("/api/ev/packet", json=_payload()).status_code == 401
    assert public_client.post("/api/property", json={"address": "123 Sample St"}).status_code == 401


def test_a_wrong_password_is_refused(public_client):
    assert public_client.post("/api/signin", json={"password": "wrong"}).status_code == 401


def test_a_forged_cookie_is_refused(public_client):
    public_client.cookies.set("permit_demo_session", "9999999999.abc")
    assert public_client.post("/api/ev/packet", json=_payload()).status_code == 401


def test_home_shows_sign_in_until_signed_in(public_client, client):
    assert "Sign in" in public_client.get("/").text
    page = client.get("/").text
    assert "Start with the address" in page
    assert "Approve packet" in page


def test_trench_longer_than_the_run_is_refused(client):
    assert client.post("/api/ev/packet", json=_payload(trench_ft=99)).status_code == 422


def test_charger_outside_level_2_range_is_refused(client):
    assert client.post("/api/ev/packet", json=_payload(charger_amps=200)).status_code == 422


@pytest.mark.parametrize("amps,wire", [(16, "12"), (20, "10"), (28, "8")])
def test_small_wire_stays_inside_the_breaker_limits(amps, wire):
    assert size_circuit(amps, 20, continuous=True).wire.size == wire


def test_upsized_wire_upsizes_the_ground():
    circuit = size_circuit(48, 200, continuous=True)
    assert (circuit.wire.size, circuit.ground) == ("4", "8")


def test_over_capacity_names_the_charger_that_fits():
    packet = build_ev_packet(_job(service_amps=150))
    assert not packet.ready
    assert any("A 24 A charger fits" in flag for flag in packet.flags)
    assert any("No common charger size fits" in flag
               for flag in build_ev_packet(_job(service_amps=125)).flags)


def test_receptacle_above_a_50_amp_circuit_must_be_hardwired():
    assert not build_ev_packet(_job(connection="receptacle", charger_amps=48)).ready
    allowed = build_ev_packet(_job(connection="receptacle", charger_amps=40))
    assert allowed.ready
    assert any("GFCI" in flag for flag in allowed.flags)


def test_solar_adds_a_flag():
    assert not any("solar" in flag for flag in build_ev_packet(_job()).flags)
    assert any("solar" in flag for flag in build_ev_packet(_job(has_solar=True)).flags)


def test_every_lot_line_keeps_its_dimension_when_a_marker_sits_on_it():
    plan = _plan(panel=(750, 500), charger=(600, 500), route=[])
    packet = build_ev_packet(_job(plan=plan, location="attached_garage", trench_ft=0, charger_amps=40))
    text = pypdfium2.PdfDocument(render_ev_packet_pdf(packet))[2].get_textpage().get_text_bounded()
    assert text.count("105 ft") == 4


def test_city_comes_from_the_address_and_unknown_cities_are_labeled():
    assert jurisdiction_for("Oro Valley", "AZ") is ORO_VALLEY
    assert jurisdiction_for("el cajon", "ca") is EL_CAJON
    other = jurisdiction_for("Mesa", "AZ")
    assert not other.known
    assert other.label == "Mesa, AZ"


def test_el_cajon_rules_reach_the_flags():
    packet = build_ev_packet(_job(jurisdiction=EL_CAJON, plan=_plan(parcel_number="")))
    assert any("parcel number" in flag for flag in packet.flags)
    assert any("within 50 ft" in flag for flag in packet.flags)
    assert any("2019 California" in flag for flag in packet.flags)


def test_plan_measures_route_and_setback_at_scale():
    plan = _plan(route=[])
    assert plan.feet_per_unit == 0.21
    assert plan.measured_route_ft == 42
    assert plan.charger_to_lot_line_ft == 32
    assert sorted(edge.length_ft for edge in plan.lot_edges) == [105, 105, 105, 105]


def test_scale_is_the_smallest_engineer_scale_that_fits():
    assert plan_scale(120) == 20
    assert plan_scale(170) == 30
    assert plan_scale(5000) == 100


def test_plan_view_puts_its_center_in_the_middle():
    view = PlanView(32.4, -110.9, 30)
    assert view.to_plan(32.4, -110.9) == (500.0, 500.0)
    assert view.to_plan(32.4005, -110.9)[1] < 500


@pytest.mark.parametrize("jurisdiction", [ORO_VALLEY, EL_CAJON])
@pytest.mark.parametrize("plan", [None, "aerial", "outlines"])
def test_worst_case_packet_stays_seven_pages(jurisdiction, plan):
    site = {"aerial": _plan(), "outlines": _plan(aerial_jpeg=None), None: None}[plan]
    job = _job(jurisdiction=jurisdiction, plan=site, service_amps=100, open_breaker_spaces=0, charger_amps=80,
               run_ft=400, trench_ft=300, connection="receptacle")
    pdf = render_ev_packet_pdf(build_ev_packet(job))
    assert len(re.findall(rb"/Type\s*/Page[^s]", pdf)) == 7


CENSUS_MATCH = {"result": {"addressMatches": [{
    "matchedAddress": "10 MAIN ST, ORO VALLEY, AZ, 85737",
    "coordinates": {"x": -110.97, "y": 32.40},
    "geographies": {"Incorporated Places": [{"NAME": "Oro Valley town"}], "Counties": [{"GEOID": "04019"}]},
}]}}
BOX = [[-110.9702, 32.3998], [-110.9698, 32.3998], [-110.9698, 32.4002], [-110.9702, 32.4002], [-110.9702, 32.3998]]
LOT_BOX = [[-110.9705, 32.3995], [-110.9695, 32.3995], [-110.9695, 32.4005], [-110.9705, 32.4005], [-110.9705, 32.3995]]


CENSUS_MATCH["result"]["addressMatches"][0]["addressComponents"] = {"streetName": "MAIN"}


def _lot(number: str = "10 MAIN ST") -> dict:
    return {"attributes": {"PARCEL": "224265700", "ADDRESS_OL": number}, "geometry": {"rings": [LOT_BOX]}}


def _services(request: httpx.Request, *, by_address=True, by_point=True, photon=()) -> httpx.Response:
    host = request.url.host
    if host == "geocoding.geo.census.gov":
        return httpx.Response(200, json=CENSUS_MATCH)
    if host == "photon.komoot.io":
        return httpx.Response(200, json={"features": list(photon)})
    if "USA_Structures" in request.url.path:
        return httpx.Response(200, json={"features": [
            {"attributes": {}, "geometry": {"rings": [[[x + .001, y] for x, y in BOX]]}},
            {"attributes": {}, "geometry": {"rings": [BOX]}},
        ]})
    if host == "gisdata.pima.gov":
        searched = "where" in request.url.params
        return httpx.Response(200, json={"features": [_lot()] if (by_address if searched else by_point) else []})
    return httpx.Response(404)


def _client(**options) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: _services(request, **options)))


def test_find_property_uses_the_county_record_for_the_exact_house():
    found = find_property("10 Main St, Oro Valley, AZ", _client())
    assert found.address == "10 Main St, Oro Valley, AZ 85737"
    assert tidy_address("1200 N 3RD AVE, SAN DIEGO, CA, 92101") == "1200 N 3rd Ave, San Diego, CA 92101"
    assert found.jurisdiction is ORO_VALLEY
    assert found.located_by == "county"
    assert found.address_confirmed is True
    assert found.parcel_number == "224265700"
    assert len(found.lot) == 4
    assert found.buildings[found.primary_building]
    assert all(0 < value < 1000 for point in found.lot for value in point)


def test_the_house_point_from_the_map_beats_the_street_estimate():
    house = {"properties": {"housenumber": "10", "street": "Main Street"},
             "geometry": {"coordinates": [-110.9700, 32.4000]}}
    found = find_property("10 Main St", _client(by_address=False, photon=[house]))
    assert found.located_by == "map"


def test_a_far_away_house_with_the_same_number_is_ignored():
    house = {"properties": {"housenumber": "10", "street": "Main Street"},
             "geometry": {"coordinates": [-112.0, 33.4]}}
    found = find_property("10 Main St", _client(by_address=False, photon=[house]))
    assert found.located_by == "street"


def test_a_street_estimate_says_when_the_parcel_is_someone_else():
    def other_parcel(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gisdata.pima.gov":
            return httpx.Response(200, json={
                "features": [] if "where" in request.url.params else [_lot("99 MAIN ST")]})
        return _services(request)

    found = find_property("10 Main St", httpx.Client(transport=httpx.MockTransport(other_parcel)))
    assert found.located_by == "street"
    assert found.address_confirmed is False
    assert found.parcel_house_number == "99"


def test_tapping_a_house_moves_to_it(client, monkeypatch):
    seen = {}

    def fake(**fields):
        seen.update(fields)
        return property_at(client=_client(), **fields)

    monkeypatch.setattr("app.property_at", fake)
    body = {"address": "10 Main St", "city": "Oro Valley", "state": "AZ", "county_fips": "04019",
            "house_number": "10", "latitude": 32.4, "longitude": -110.97, "anchor_latitude": 32.4,
            "anchor_longitude": -110.97, "scale_ft_per_in": 30, "tap": [500, 500]}
    response = client.post("/api/property/view", json=body)
    assert response.status_code == 200
    assert seen["located_by"] == "tap"
    assert seen["point"] == pytest.approx((32.4, -110.97))
    zoomed = client.post("/api/property/view", json={**body, "tap": None, "zoom": 1})
    assert zoomed.json()["view"]["scale_ft_per_in"] == 40


def test_a_merged_building_is_trimmed_at_the_lot_line():
    lot = [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)]
    merged = [(200.0, 150.0), (500.0, 150.0), (500.0, 250.0), (200.0, 250.0)]
    assert max(point[0] for point in clip_to(merged, lot)) == 300


def test_zoom_stops_at_the_ends_of_the_scale_list():
    assert zoomed_scale(20, -1) == 20
    assert zoomed_scale(30, 1) == 40
    assert zoomed_scale(100, 1) == 100


def test_only_parcel_and_address_fields_are_requested_from_the_county():
    seen = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _services(request)

    find_property("10 Main St, Oro Valley, AZ", httpx.Client(transport=httpx.MockTransport(spy)))
    county = [request for request in seen if request.url.host == "gisdata.pima.gov"]
    assert county
    assert {request.url.params["outFields"] for request in county} == {"PARCEL,ADDRESS_OL"}


def test_clark_county_reads_only_parcel_and_address_fields():
    county = COUNTIES["32003"]
    assert county.parcel_field == "PARCEL"
    assert county.address_fields == "STRNO"
    assert county.address_where("10", "O'NEIL") == "STRNO=10 AND STRNAME='O''NEIL'"


def test_an_unknown_address_says_so():
    empty = httpx.MockTransport(lambda request: httpx.Response(200, json={"result": {"addressMatches": []}}))
    with pytest.raises(AddressNotFound, match="wasn't found"):
        find_property("nowhere", httpx.Client(transport=empty))


def test_a_lookup_survives_when_the_county_is_down():
    def county_down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500) if request.url.host == "gisdata.pima.gov" else _services(request)

    found = find_property("10 Main St, Oro Valley, AZ", httpx.Client(transport=httpx.MockTransport(county_down)))
    assert found.lot == []
    assert found.parcel_number == ""
    assert found.address_confirmed is None
    assert found.buildings


def test_aerial_comes_back_as_jpeg_with_a_credit():
    image = httpx.MockTransport(lambda request: httpx.Response(
        200, content=_aerial(), headers={"content-type": "image/jpeg"}))
    jpeg, credit = fetch_aerial(PlanView(32.4, -110.9, 30), httpx.Client(transport=image))
    assert jpeg.startswith(b"\xff\xd8")
    assert "U.S. Geological Survey" in credit


def test_mapbox_is_used_first_when_a_token_is_set(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    hosts = []

    def serve(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200, content=_aerial(), headers={"content-type": "image/jpeg"})

    _, credit = fetch_aerial(PlanView(32.4, -110.9, 30), httpx.Client(transport=httpx.MockTransport(serve)))
    assert hosts == ["api.mapbox.com"]
    assert "Mapbox" in credit


def test_a_failed_aerial_is_reported():
    down = httpx.MockTransport(lambda request: httpx.Response(502))
    with pytest.raises(AerialUnavailable):
        fetch_aerial(PlanView(32.4, -110.9, 30), httpx.Client(transport=down))


def _photon(*features: dict) -> httpx.Client:
    body = {"features": [{"properties": {"countrycode": "US", **feature}} for feature in features]}
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))


def test_suggestions_read_as_full_addresses_and_drop_repeats():
    house = {"housenumber": "15917", "street": "Hidden Valley Drive", "city": "Poway",
             "state": "California", "postcode": "92064"}
    assert suggest_addresses("15917 Hidden", _photon(house, house)) == [
        "15917 Hidden Valley Drive, Poway, CA 92064"]


def test_a_street_match_takes_the_typed_house_number():
    street = {"type": "street", "name": "Oak Street", "city": "Mesa", "state": "Arizona"}
    assert suggest_addresses("412 Oak St", _photon(street)) == ["412 Oak Street, Mesa, AZ"]


def test_suggestions_drop_other_streets_numbers_and_directions():
    assert suggest_addresses("123 Main St", _photon(
        {"housenumber": "110", "street": "Inner Campus Drive", "city": "Austin", "state": "Texas"},
        {"housenumber": "123", "street": "Main Street", "city": "Boston", "state": "Massachusetts"},
    )) == ["123 Main Street, Boston, MA"]
    assert suggest_addresses("500 E Washington", _photon(
        {"housenumber": "500", "street": "West Washington Avenue", "city": "El Cajon", "state": "California"},
    )) == []


def test_suggestions_need_every_typed_street_word():
    assert suggest_addresses("309 Onyx Crest", _photon(
        {"type": "street", "name": "Onyx Way", "city": "Las Vegas", "state": "Nevada"},
        {"type": "street", "name": "Onyx Crest Street", "city": "Las Vegas", "state": "Nevada"},
    )) == ["309 Onyx Crest Street, Las Vegas, NV"]


def test_suggestions_skip_anything_outside_the_us_or_without_a_city():
    assert suggest_addresses("12 Main", _photon(
        {"countrycode": "CA", "housenumber": "12", "street": "Main St", "city": "Toronto", "state": "Ontario"},
        {"housenumber": "12", "street": "Main St", "state": "Texas"},
    )) == []


def test_suggestions_fail_quietly():
    down = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    assert suggest_addresses("12 Main", down) == []


def test_suggest_route_needs_a_session(public_client):
    assert public_client.post("/api/property/suggest", json={"text": "12 Main"}).status_code == 401
