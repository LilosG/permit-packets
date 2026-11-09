"""Subpanel / feeder permits: the feeder math, the checks, the flags, the PDF and the routes."""
from __future__ import annotations

import pytest

from permit_packets.core.checks import Check
from permit_packets.core.conductors import (
    ALUMINUM_K,
    COPPER_K,
    EGC_TABLE,
    feeder_conductor,
    feeder_conduit,
    feeder_voltage_drop,
    size_feeder,
)


def test_check_moved_to_core_keeps_its_fields():
    from permit_packets.job_types.service_upgrade.calc import Check as ServiceCheck

    assert ServiceCheck is Check
    assert Check("Name", "Result", True) == Check(name="Name", result="Result", passed=True)


def test_the_egc_table_and_the_k_constants():
    assert EGC_TABLE[0] == (15, "14", "12")
    assert EGC_TABLE[-1] == (400, "3", "1")
    assert (COPPER_K, ALUMINUM_K) == (12.9, 21.2)


@pytest.mark.parametrize("breaker, copper, aluminum", [
    (60, "6", "4"), (100, "3", "1"), (125, "1", "2/0"), (150, "1/0", "3/0"), (200, "3/0", "250"),
])
def test_feeder_conductor_is_the_smallest_that_carries_the_breaker(breaker, copper, aluminum):
    assert feeder_conductor(breaker, "copper").size == copper
    assert feeder_conductor(breaker, "aluminum").size == aluminum


def test_a_whole_dwelling_feeder_takes_the_83_percent_rule():
    # 310.12: 200 A x 83% = 166 A, so 2/0 copper (175 A) and 4/0 aluminum (180 A) are enough.
    assert feeder_conductor(200, "copper", whole_dwelling=True).size == "2/0"
    assert feeder_conductor(200, "aluminum", whole_dwelling=True).size == "4/0"


def test_voltage_drop_uses_each_metals_constant():
    copper = feeder_conductor(100, "copper")
    volts, percent = feeder_voltage_drop(80, 150, copper, "copper")
    assert volts == pytest.approx(2 * 12.9 * 80 * 150 / 52620)
    assert percent == pytest.approx(volts / 240 * 100)
    aluminum_volts, _ = feeder_voltage_drop(80, 150, copper, "aluminum")
    assert aluminum_volts == pytest.approx(volts * 21.2 / 12.9)


def test_a_short_copper_feeder_is_not_upsized():
    feeder = size_feeder(100, "copper", 80, 150)
    assert (feeder.conductor.size, feeder.egc, feeder.upsized) == ("3", "8", False)
    assert feeder.vd_percent == pytest.approx(2.45, abs=0.01)


def test_a_long_copper_feeder_is_upsized_and_the_egc_follows():
    feeder = size_feeder(100, "copper", 80, 250)
    assert (feeder.conductor.size, feeder.egc, feeder.upsized) == ("1", "6", True)
    assert feeder.vd_percent <= 3


def test_an_aluminum_feeder_keeps_its_size_when_the_drop_is_fine():
    feeder = size_feeder(100, "aluminum", 80, 100)
    assert (feeder.conductor.size, feeder.egc, feeder.upsized) == ("1", "6", False)


def test_sizing_stops_at_350_kcmil_and_reports_the_drop_it_could_not_fix():
    feeder = size_feeder(200, "aluminum", 200, 500)
    assert feeder.conductor.size == "350"
    assert feeder.upsized
    assert feeder.vd_percent > 3


def test_the_upsized_egc_never_exceeds_the_hots():
    for ft in (50, 200, 350, 500):
        feeder = size_feeder(60, "copper", 60, ft)
        from permit_packets.core.conductors import _ground_properties
        assert _ground_properties(feeder.egc)[0] <= feeder.conductor.circular_mils


@pytest.mark.parametrize("breaker, ft, conduit, size", [
    (100, 1, "PVC", '1"'),    # 3 x #3 + #8 = 0.3285 sq in
    (60, 1, "PVC", '3/4"'),   # 3 x #6 + #10 = 0.1732 sq in
    (100, 1, "EMT", '1"'),
])
def test_feeder_conduit_holds_three_conductors_and_the_ground(breaker, ft, conduit, size):
    feeder = size_feeder(breaker, "copper", 1, ft)
    assert feeder_conduit(feeder, conduit) == size
