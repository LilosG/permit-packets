"""Commercial feeder and service-load math, checked against hand-worked NEC examples."""
import math

import pytest

from permit_packets.core import commercial as c

S208 = c.SYSTEMS["208y120"]
S480 = c.SYSTEMS["480y277"]
S1PH = c.SYSTEMS["120_240"]


def test_line_current_of_a_balanced_three_phase_load():
    # 75 kVA at 208 V: 75,000 / (1.732 x 208) = 208.2 A.  100 kVA at 480 V: 120.3 A.
    assert c.SYSTEMS["208y120"].amps(75_000) == pytest.approx(208.2, abs=0.05)
    assert S480.amps(100_000) == pytest.approx(120.3, abs=0.05)
    assert S1PH.amps(24_000) == pytest.approx(100.0)
    assert S208.va(100) == pytest.approx(36_027, abs=1)


def test_three_phase_voltage_drop_matches_the_hand_calculation():
    # 100 A, 100 ft, #1 Cu (83,690 cmil), K 12.9: 1.732 x 12.9 x 100 x 100 / 83,690 = 2.67 V = 1.28% of 208 V.
    number1 = next(w for w in c.COPPER if w.size == "1")
    volts, percent = c.voltage_drop(100, 100, number1, "copper", S208)
    assert volts == pytest.approx(2.670, abs=0.005)
    assert percent == pytest.approx(1.284, abs=0.005)
    # The same run single-phase doubles the length instead of multiplying by 1.732.
    one_phase, _ = c.voltage_drop(100, 100, number1, "copper", S1PH)
    assert one_phase == pytest.approx(2 * 12.9 * 100 * 100 / 83_690, abs=0.005)
    # 480 V drops the same volts but a smaller share of the voltage.
    assert c.voltage_drop(100, 100, number1, "copper", S480)[1] == pytest.approx(2.670 / 480 * 100, abs=0.005)


def test_a_100_amp_copper_feeder_is_number_3_with_an_8_ground():
    feeder = c.size_feeder(100, "copper", 80, 150, S208)
    assert feeder.conductor.size == "3"
    assert feeder.conductor.ampacity_75c == 100
    assert feeder.egc == "8"
    assert not feeder.upsized
    assert feeder.vd_percent == pytest.approx(2.45, abs=0.02)
    assert feeder.poles == 3


def test_a_long_aluminum_feeder_is_upsized_and_its_ground_grows_with_it():
    # 100 A breaker, 100 A load, 300 ft, aluminum: #1 Al starts the search and drops 6.3%; 4/0 Al is the first
    # size within 3% (2.5%). The EGC grows from #6 in proportion to the hots (250.122(B)): #2.
    feeder = c.size_feeder(100, "aluminum", 100, 300, S208)
    assert feeder.start.size == "1"
    assert feeder.conductor.size == "4/0"
    assert feeder.upsized
    assert feeder.vd_percent == pytest.approx(2.5, abs=0.05)
    assert feeder.egc == "2"
    assert c.feeder_conduit(feeder, "PVC") == '2-1/2"'  # 4 x 0.3237 + 0.1158 = 1.41 sq in, 40% fill
    assert c.feeder_conduit(feeder, "EMT") == '2-1/2"'


def test_a_single_phase_feeder_carries_two_hots_and_a_neutral():
    feeder = c.size_feeder(100, "copper", 80, 50, S1PH)
    assert feeder.poles == 2
    # 3 x 0.0973 + 0.0366 (#8 EGC) = 0.3285 sq in, just inside 1 in PVC (0.333 at 40% fill).
    assert c.feeder_conduit(feeder, "PVC") == '1"'


def test_the_ground_table_extends_past_400_amps():
    assert c.egc_size(300, "copper") == "4" and c.egc_size(300, "aluminum") == "2"
    assert c.egc_size(500, "copper") == "2" and c.egc_size(500, "aluminum") == "1/0"


def test_breaker_sizes_and_the_limit_of_one_set():
    assert c.next_standard(126) == 150
    assert c.next_standard(100) == 100
    with pytest.raises(ValueError):
        c.next_standard(351)
    with pytest.raises(ValueError):
        c.size_feeder(350, "aluminum", 300, 50, S208)  # 500 kcmil Al is 310 A: needs parallel sets


def test_service_load_uses_measured_demand_at_125_percent_and_continuous_loads_at_125_percent():
    load = c.ServiceLoad(
        system=S208, service_amps=200, existing_kva=40, existing_basis="utility_12_month",
        lines=(c.new_load_line("EV chargers", 5_000, continuous=True),
               c.new_load_line("Shop circuits", 3_000, continuous=False)),
    )
    # 40 kVA x 125% = 50,000 VA; 5,000 x 125% = 6,250; 3,000 at 100%.
    assert load.existing_va == 50_000
    assert load.new_va == 9_250
    assert load.total_va == 59_250
    assert load.amps == pytest.approx(59_250 / (math.sqrt(3) * 208), abs=0.01)
    assert load.amps == pytest.approx(164.5, abs=0.1)
    assert load.spare_amps == pytest.approx(35.5, abs=0.1)
    assert load.fits


def test_a_calculated_existing_load_is_not_inflated():
    load = c.ServiceLoad(system=S480, service_amps=100, existing_kva=50, existing_basis="calculated", lines=())
    assert load.existing_va == 50_000
    assert load.amps == pytest.approx(60.1, abs=0.05)
    over = c.ServiceLoad(system=S208, service_amps=100, existing_kva=50, existing_basis="utility_12_month", lines=())
    assert not over.fits
