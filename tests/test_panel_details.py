"""Item 5: panel details and the existing grounding electrode conductor, on every job type."""
import pytest
from pydantic import ValidationError

from permit_packets.core.panel_data import parse_gec, required_gec
from permit_packets.job_types import REGISTRY
from tests.packet_helpers import build, packet_pages, sample

ALL = sorted(REGISTRY)
DETAILS = {"panel_location": "Garage, east wall", "panel_bus_amps": 200, "panel_main": "main breaker",
           "gec_size": "#4 Cu"}


def _full(key: str, **changes) -> dict:
    payload = {**sample(key), **DETAILS, "service_amps": 200, **changes}
    if key == "service_upgrade":
        payload.pop("service_amps")
        payload["panel_bus_amps"] = payload.get("bus_amps", 200)
        payload["bus_amps"] = payload["panel_bus_amps"]
    return payload


def _gec(body: dict):
    return next((c for c in body["checks"] if c["name"] == "Existing GEC"), None)


def test_wire_sizes_read_the_way_electricians_write_them():
    assert parse_gec("#4 Cu") == ("4", "copper")
    assert parse_gec("4 AWG copper") == ("4", "copper")
    assert parse_gec("#6") == ("6", "copper")
    assert parse_gec("1/0 Al") == ("1/0", "aluminum")
    assert parse_gec("#6 Aluminum") == ("6", "aluminum")
    assert parse_gec("four gauge") is None and parse_gec("#5 Cu") is None


def test_table_250_66_by_service_size():
    assert required_gec(100) == "8" and required_gec(200) == "4" and required_gec(300) == "2" and required_gec(400) == "1/0"
    assert required_gec(800) is None
    assert required_gec(200, electrodes=("rods",)) == "6"
    assert required_gec(200, electrodes=("rods", "water_pipe")) == "4"


@pytest.mark.parametrize("key", ["ev_charger", "subpanel", "appliance_circuit"])
def test_a_gec_smaller_than_table_250_66_is_flagged_and_blocks(key):
    body = build(key, _full(key, gec_size="#6 Cu")).body
    assert _gec(body)["passed"] is False
    assert "#6 Cu is smaller than the #4 Cu Table 250.66 requires for a 200 A service" in _gec(body)["result"]
    assert any("Existing grounding electrode conductor" in flag for flag in body["flags"])
    assert body["ready"] is False


@pytest.mark.parametrize("key", ["ev_charger", "subpanel", "appliance_circuit"])
@pytest.mark.parametrize("entered", ["#4 Cu", "#2 Cu", "#2 Al", "1/0 Al"])
def test_a_gec_at_or_above_the_table_passes(key, entered):
    assert _gec(build(key, _full(key, gec_size=entered)).body)["passed"] is True


def test_an_aluminum_gec_needs_the_larger_size():
    assert _gec(build("ev_charger", _full("ev_charger", gec_size="#4 Al")).body)["passed"] is False


def test_a_100_amp_service_only_needs_an_8():
    body = build("ev_charger", _full("ev_charger", service_amps=100, gec_size="#8 Cu")).body
    assert _gec(body)["passed"] is True


def test_service_upgrade_checks_the_gec_against_the_new_service_and_electrodes():
    payload = _full("service_upgrade", gec_size="#6 Cu")
    payload["electrodes"] = ["rods"]
    assert _gec(build("service_upgrade", payload).body)["passed"] is True
    payload["electrodes"] = ["rods", "water_pipe"]
    assert _gec(build("service_upgrade", payload).body)["passed"] is False


def test_no_check_when_no_gec_was_entered():
    assert _gec(build("ev_charger", _full("ev_charger", gec_size="")).body) is None


def test_an_unreadable_gec_is_a_422():
    with pytest.raises(ValidationError):
        build("ev_charger", _full("ev_charger", gec_size="big wire"))
    with pytest.raises(ValidationError):
        build("ev_charger", _full("ev_charger", panel_main="main fuse"))


@pytest.mark.parametrize("key", ALL)
def test_the_panel_details_are_on_the_panel_schedule_and_the_one_line(key):
    pages = packet_pages(build(key, _full(key)).pdf)
    schedule = next(p for p in pages if "Panel Schedule" in p and "Circuit directory" in p)
    one_line = pages[3]
    for text in (schedule, one_line):
        assert "Garage, east wall" in text
        assert "200 A" in text and "main breaker" in text.lower()
        assert "#4 Cu" in text


def test_missing_panel_details_are_flagged_not_blocking():
    payload = {**sample("ev_charger")}
    body = build("ev_charger", payload).body
    assert any(flag.startswith("Enter the panel's location, bus rating, main type") for flag in body["flags"])
    assert "Not entered" in " ".join(packet_pages(build("ev_charger", payload).pdf))
