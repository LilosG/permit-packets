"""Panel / service upgrade permits: the conductor math, the checks, the flags, the PDF and the routes."""
from __future__ import annotations

import pytest

from permit_packets.core.conductors import (
    ALUMINUM_75C,
    COPPER_75C,
    gec_size,
    service_conductor,
    service_conduit,
    solar_fits,
)


# ---- Conductors, grounding, conduit and solar ----

@pytest.mark.parametrize("amps, copper, aluminum", [
    (100, "4", "2"), (125, "2", "1/0"), (150, "1", "2/0"), (200, "2/0", "4/0"), (225, "3/0", "250"),
])
def test_service_conductor_is_sized_at_83_percent(amps, copper, aluminum):
    assert service_conductor(amps, "copper").size == copper
    assert service_conductor(amps, "aluminum").size == aluminum
    assert service_conductor(amps, "copper").ampacity_75c >= 0.83 * amps


def test_aluminum_carries_less_than_copper_at_every_size():
    assert [c.size for c in COPPER_75C] == [a.size for a in ALUMINUM_75C]
    for copper, aluminum in zip(COPPER_75C, ALUMINUM_75C):
        assert aluminum.ampacity_75c < copper.ampacity_75c
        assert (aluminum.circular_mils, aluminum.area_sq_in) == (copper.circular_mils, copper.area_sq_in)


@pytest.mark.parametrize("amps, material, rods, concrete, water", [
    (200, "copper", "6", "4", "4"),
    (200, "aluminum", "6", "4", "4"),
    (100, "copper", "8", "8", "8"),
])
def test_gec_follows_the_electrode(amps, material, rods, concrete, water):
    conductor = service_conductor(amps, material)
    assert gec_size(conductor, material, "rods") == rods
    assert gec_size(conductor, material, "concrete_encased") == concrete
    assert gec_size(conductor, material, "water_pipe") == water


@pytest.mark.parametrize("size, material, table", [
    ("2", "copper", "8"), ("1", "copper", "6"), ("1/0", "copper", "6"), ("2/0", "copper", "4"),
    ("3/0", "copper", "4"), ("4/0", "copper", "2"), ("350", "copper", "2"),
    ("1/0", "aluminum", "8"), ("2/0", "aluminum", "6"), ("3/0", "aluminum", "6"),
    ("4/0", "aluminum", "4"), ("250", "aluminum", "4"), ("300", "aluminum", "2"),
])
def test_gec_table_rows(size, material, table):
    conductor = next(c for c in (COPPER_75C if material == "copper" else ALUMINUM_75C) if c.size == size)
    assert gec_size(conductor, material, "water_pipe") == table


@pytest.mark.parametrize("amps, material, pvc, emt", [
    (200, "copper", '1-1/2"', '1-1/2"'),
    (200, "aluminum", '2"', '2"'),
    (100, "copper", '1"', '1"'),
])
def test_service_conduit_holds_three_conductors(amps, material, pvc, emt):
    conductor = service_conductor(amps, material)
    assert service_conduit(conductor, "PVC") == pvc
    assert service_conduit(conductor, "EMT") == emt


@pytest.mark.parametrize("bus, main, pv, fits", [
    (200, 200, 40, True), (200, 200, 50, False), (225, 200, 70, True),
])
def test_solar_120_percent_rule(bus, main, pv, fits):
    assert solar_fits(bus, main, pv) is fits
