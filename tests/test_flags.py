"""Review flags across every city and every job type, including the job types a city publishes no checklist for
(those use the general checklist and are not in test_city_compliance)."""
import pytest

from permit_packets.job_types import REGISTRY
from permit_packets.jurisdictions import KNOWN
from tests.packet_helpers import build, complete_inputs

CASES = [(j, key) for j in KNOWN.values() for key in sorted(REGISTRY)]


@pytest.mark.parametrize("jurisdiction,key", CASES, ids=[f"{j.key}-{k}" for j, k in CASES])
def test_every_packet_builds_and_no_flag_is_printed_twice(jurisdiction, key):
    flags = build(key, complete_inputs(key, jurisdiction)).body["flags"]
    repeated = {flag for flag in flags if flags.count(flag) > 1}
    assert not repeated, repeated
    # A note's text must not be folded into another flag either (a code note inside the fallback note).
    for flag in flags:
        others = [other for other in flags if other != flag and flag in other]
        assert not others, f"{flag!r} is repeated inside {others!r}"


@pytest.mark.parametrize("location,shown,hidden", [
    ("attached_garage", "not less than 18 in and not more than 48 in above the finished floor", "above grade"),
    ("detached_garage", "not less than 18 in and not more than 48 in above the finished floor", "above grade"),
    ("exterior_wall", "at least 24 in above grade", "above the finished floor"),
])
def test_san_francisco_charger_height_follows_the_install_location(location, shown, hidden):
    sf = next(j for j in KNOWN.values() if j.key == "san-francisco-ca")
    flags = build("ev_charger", {**complete_inputs("ev_charger", sf), "location": location}).body["flags"]
    height = [flag for flag in flags if "coupling means" in flag]
    assert len(height) == 1 and shown in height[0] and hidden not in height[0], height


@pytest.mark.parametrize("location,rule", [
    ("outdoor", "within 20 ft (680.42, 680.22(A))"),
    ("indoor", "within 10 ft (680.43(A))"),
])
def test_spa_receptacle_rule_follows_indoor_or_outdoor(location, rule):
    nashville = next(j for j in KNOWN.values() if j.key == "nashville-tn")
    payload = {**complete_inputs("appliance_circuit", nashville), "appliance": "hot_tub", "location": location}
    flags = build("appliance_circuit", payload).body["flags"]
    receptacle = [flag for flag in flags if flag.startswith("Keep receptacles")]
    assert len(receptacle) == 1 and rule in receptacle[0], receptacle
