"""Local wiring and service amendments: San Francisco (SFEC 230.43, 352.10, 340.10), Metro Nashville
(Metro Code 16.20.150) and the NEC 230.85 outdoor emergency disconnect everywhere."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from permit_packets.job_types import REGISTRY
from permit_packets.jurisdictions import jurisdiction_by_key
from tests.packet_helpers import complete_inputs

BUILDERS = {"service_upgrade": "build_service_packet", "subpanel": "build_subpanel_packet",
            "appliance_circuit": "build_appliance_packet"}


def build(key, payload):
    """The calculated packet for a request, as the API builds it (no PDF)."""
    api = importlib.import_module(f"permit_packets.job_types.{key}.api")
    calc = importlib.import_module(f"permit_packets.job_types.{key}.calc")
    job = api.to_job(REGISTRY[key].request_model.model_validate(payload))
    return SimpleNamespace(packet=getattr(calc, BUILDERS[key])(job))

SF = jurisdiction_by_key("san-francisco-ca")
NASHVILLE = jurisdiction_by_key("nashville-tn")
MESA = jurisdiction_by_key("mesa-az")


def _check(result, name):
    return next(check for check in result.packet.checks if check.name == name)


def _service(jurisdiction, **changes):
    return build("service_upgrade", {**complete_inputs("service_upgrade", jurisdiction), **changes})


@pytest.mark.parametrize("chosen", ["PVC", "EMT", "none"])
def test_sf_service_conductors_are_drawn_in_rmc_at_1_1_4_minimum(chosen):
    result = _service(SF, equipment="main_panel", conduit=chosen, new_service_amps=100, existing_service_amps=60,
                      bus_amps=100, panel_bus_amps=100)
    packet = result.packet
    assert packet.raceway == "RMC"
    assert packet.conduit_size == '1-1/4"'
    assert "1-1/4\" minimum" in _check(result, "Conduit fill").result
    assert any("230.43" in flag and "RMC" in flag for flag in packet.flags)


def test_sf_service_in_rmc_is_kept_and_not_flagged():
    packet = _service(SF, equipment="main_panel", conduit="RMC").packet
    assert packet.raceway == "RMC"
    assert not any("allows only" in flag for flag in packet.flags)


def test_sf_meter_main_feeder_goes_to_emt_not_pvc():
    packet = _service(SF, equipment="meter_main", conduit="PVC").packet
    assert packet.raceway == "EMT"
    assert any("352.10" in flag for flag in packet.flags)


def test_other_cities_keep_the_electricians_raceway_and_size():
    packet = _service(MESA, equipment="main_panel", conduit="PVC", new_service_amps=100, existing_service_amps=60,
                      bus_amps=100, panel_bus_amps=100).packet
    assert packet.raceway == "PVC"
    assert packet.conduit_size == '1"'  # 3 #4 Cu at 40% fill; no local minimum outside San Francisco
    assert not any("allows only" in flag for flag in packet.flags)


def test_indoor_main_panel_gets_an_outdoor_meter_disconnect_on_the_riser_and_scope():
    from permit_packets.job_types.service_upgrade.pdf import scope_of_work
    result = _service(MESA, equipment="main_panel", main_outdoors=False)
    assert result.packet.emergency == "meter_disconnect"
    assert "METER DISCONNECT, NOT SERVICE EQUIPMENT" in _check(result, "Emergency disconnect").result
    assert "meter disconnect" in scope_of_work(result.packet)


@pytest.mark.parametrize("changes", [{"equipment": "meter_main"}, {"equipment": "main_panel", "main_outdoors": True}])
def test_an_outdoor_main_breaker_is_the_emergency_disconnect(changes):
    result = _service(MESA, **changes)
    assert result.packet.emergency == "main"
    assert "EMERGENCY DISCONNECT, SERVICE DISCONNECT" in _check(result, "Emergency disconnect").result


def test_nashville_indoor_main_must_be_within_5_ft_of_the_meter():
    near = _service(NASHVILLE, equipment="main_panel", main_outdoors=False, se_length_ft=5)
    far = _service(NASHVILLE, equipment="main_panel", main_outdoors=False, se_length_ft=8)
    assert _check(near, "Main disconnect distance").passed
    assert not _check(far, "Main disconnect distance").passed
    outdoor = _service(NASHVILLE, equipment="main_panel", main_outdoors=True, se_length_ft=8)
    assert "Main disconnect distance" not in [check.name for check in outdoor.packet.checks]


def test_nashville_service_upgrade_carries_the_metro_amendments():
    packet = _service(NASHVILLE, electrodes=["rods"]).packet
    text = " ".join(packet.flags)
    for section in ("110.14(D)", "210.52(J)", "250.50", "210.12: AFCI breakers are optional", "230.70(A)(1)"):
        assert section in text, section
    assert "Confirm the city's position" not in text
    with_cee = _service(NASHVILLE, electrodes=["rods", "concrete_encased"]).packet
    assert "250.50" not in " ".join(with_cee.flags)


def test_nashville_subpanel_and_appliance_skip_the_nes_release_but_keep_torque_and_multipole():
    for key in ("subpanel", "appliance_circuit"):
        flags = " ".join(build(key, complete_inputs(key, NASHVILLE)).packet.flags)
        assert "NES requires an inspection" not in flags
        assert "110.14(D)" in flags and "240.8" in flags


def test_ev_disconnect_notes_carry_lockable_and_plaque():
    for jurisdiction in (SF, NASHVILLE):
        notes = [note.text for note in jurisdiction.checklist_for("ev_charger").notes if note.when == "disconnect"]
        assert any("lockable" in text and "plaque" in text for text in notes), jurisdiction.name


def _appliance(jurisdiction, **changes):
    return build("appliance_circuit", {**complete_inputs("appliance_circuit", jurisdiction), **changes})


def test_sf_outdoor_pvc_circuit_is_pvc_underground_and_emt_above():
    packet = _appliance(SF, wiring="PVC", location="outdoor", run_ft=60, trench_ft=30).packet
    assert "PVC underground" in packet.raceway_text and "EMT above ground" in packet.raceway_text
    packet = _appliance(SF, wiring="PVC", location="outdoor", run_ft=60, trench_ft=0).packet
    assert packet.raceway_text.endswith("EMT")


def test_sf_outdoor_cable_is_redrawn_in_emt_and_indoor_cable_is_nm():
    outdoor = _appliance(SF, wiring="cable", location="outdoor", trench_ft=0).packet
    assert outdoor.job.wiring == "EMT" and outdoor.conduit_size
    assert any("340.10" in flag for flag in outdoor.flags)
    indoor = _appliance(SF, wiring="cable", location="indoor", trench_ft=0, appliance="sauna", heater_kw=6,
                        nameplate_amps=None, gfci=None, disconnect_distance_ft=None).packet
    assert indoor.cable_type == "NM-B"


def test_cable_is_sized_at_60c_even_with_75c_terminals():
    packet = _appliance(MESA, wiring="cable", location="indoor", trench_ft=0, terminals_75c=True, appliance="sauna",
                        heater_kw=9, nameplate_amps=None, gfci=None, disconnect_distance_ft=None).packet
    assert packet.job.terminals_75c is False
    assert any("60" in flag and "334.80" in flag for flag in packet.flags)


def test_sf_subpanel_feeder_keeps_pvc_underground_only():
    packet = build("subpanel", {**complete_inputs("subpanel", SF), "conduit": "PVC", "run_ft": 80,
                                "trench_ft": 40, "location": "detached_building"}).packet
    assert "PVC underground" in packet.raceway_text and "EMT above ground" in packet.raceway_text
