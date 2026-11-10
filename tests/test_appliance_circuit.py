"""240 V appliance circuits: the branch math, the checks, the flags, the PDF and the routes."""
from __future__ import annotations

import pytest

from permit_packets.core.conductors import (
    BRANCH_COPPER,
    SMALL_CONDUCTOR_LIMIT,
    STANDARD_BREAKERS,
    branch_conduit,
    size_branch,
)


def _branch(**changes):
    return size_branch(**{"terminals_75c": False, **changes})


def test_the_branch_tables_hold_the_code_values():
    assert [(w.size, w.ampacity_60c, w.ampacity_75c, w.circular_mils, w.area_sq_in) for w in BRANCH_COPPER] == [
        ("14", 15, 20, 4110, 0.0097), ("12", 20, 25, 6530, 0.0133), ("10", 30, 35, 10380, 0.0211),
        ("8", 40, 50, 16510, 0.0366), ("6", 55, 65, 26240, 0.0507), ("4", 70, 85, 41740, 0.0824),
        ("3", 85, 100, 52620, 0.0973), ("2", 95, 115, 66360, 0.1158), ("1", 110, 130, 83690, 0.1562),
    ]
    assert SMALL_CONDUCTOR_LIMIT == {"14": 15, "12": 20, "10": 30}
    assert STANDARD_BREAKERS == (15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 125)


def test_hot_tub_at_60c_is_6_awg_with_a_10_ground():
    branch = _branch(breaker=50, load_amps=40, run_ft=40)
    assert (branch.wire.size, branch.egc, branch.upsized) == ("6", "10", False)
    assert round(branch.vd_percent, 1) == 0.7


def test_hot_tub_at_75c_is_8_awg():
    assert _branch(breaker=50, load_amps=40, run_ft=40, terminals_75c=True).wire.size == "8"


@pytest.mark.parametrize("terminals_75c", [True, False])
def test_sauna_on_a_35_a_breaker_is_8_awg_because_of_240_4_d(terminals_75c):
    # #10 carries 35 A at 75 C, but 240.4(D) stops it at a 30 A breaker.
    assert _branch(breaker=35, load_amps=25, run_ft=40, terminals_75c=terminals_75c).wire.size == "8"


def test_mini_split_is_14_awg_on_a_25_a_breaker_with_the_ground_capped():
    branch = _branch(breaker=25, load_amps=15, run_ft=30, hvac_mca=15)
    assert (branch.wire.size, branch.egc) == ("14", "14")  # 250.122(A): no larger than the hots


def test_heat_pump_is_10_awg_with_a_10_ground():
    branch = _branch(breaker=45, load_amps=28.5, run_ft=30, hvac_mca=28.5)
    assert (branch.wire.size, branch.egc) == ("10", "10")


def test_a_long_hot_tub_run_is_upsized_with_its_ground():
    branch = _branch(breaker=50, load_amps=40, run_ft=200)
    assert (branch.wire.size, branch.egc, branch.upsized) == ("4", "8", True)
    assert branch.vd_percent <= 3


def test_voltage_drop_stops_at_the_largest_size():
    branch = _branch(breaker=60, load_amps=60, run_ft=500)
    assert branch.wire.size == "1"
    assert branch.vd_percent > 3


def test_conduit_holds_the_wires_and_the_ground():
    branch = _branch(breaker=50, load_amps=40, run_ft=40)
    assert branch_conduit(branch, 3, "PVC") == '3/4"'
    assert branch_conduit(branch, 4, "PVC") == '1"'
