"""Conductor temperature correction for runs outdoors or in the sun (NEC 310.15(B)(1)).

THWN-2 is a 90 C wire, so the correction factor multiplies its 90 C ampacity from Table 310.16.
The result can never count for more than the 75 C (or 60 C) column the equipment terminals are rated
for (110.14(C)), so the corrected ampacity is capped there. A conductor whose corrected ampacity is
below what it must carry is too small and the next size up is used.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DEGREE = "\N{DEGREE SIGN}"

# NEC 310.15(B)(1), the 90 C column: (highest ambient in the row, in C, correction factor).
# Rows read 21-25, 26-30, 31-35 and so on; 26-30 C is the table's own 30 C reference.
CORRECTION_90C = (
    (25, 1.04), (30, 1.00), (35, 0.96), (40, 0.91), (45, 0.87), (50, 0.82), (55, 0.76),
    (60, 0.71), (65, 0.65), (70, 0.58), (75, 0.50), (80, 0.41), (85, 0.29),
)

# NEC Table 310.16, the 90 C column, THWN-2 (size: amps).
AMPACITY_90C = {
    "copper": {"14": 25, "12": 30, "10": 40, "8": 55, "6": 75, "4": 95, "3": 115, "2": 130, "1": 145,
               "1/0": 170, "2/0": 195, "3/0": 225, "4/0": 260, "250": 290, "300": 320, "350": 350,
               "400": 380, "500": 430, "600": 475},
    "aluminum": {"12": 25, "10": 35, "8": 45, "6": 60, "4": 75, "3": 85, "2": 100, "1": 115,
                 "1/0": 135, "2/0": 150, "3/0": 175, "4/0": 205, "250": 230, "300": 260, "350": 280,
                 "400": 305, "500": 350, "600": 385},
}
METAL = {"copper": "Cu", "aluminum": "Al"}


def celsius(fahrenheit: float) -> float:
    return (fahrenheit - 32) * 5 / 9


def correction_factor(ambient_f: float) -> float:
    """The 90 C correction factor for the ambient, taking the row the temperature falls in."""
    ambient_c = math.ceil(celsius(ambient_f))
    for limit, factor in CORRECTION_90C:
        if ambient_c <= limit:
            return factor
    raise ValueError(f"{ambient_f:g}{DEGREE}F is above the NEC 310.15(B)(1) table")


def size_label(size: str) -> str:
    return f"{size} kcmil" if int(size.split("/")[0]) >= 250 else f"#{size}"


@dataclass(frozen=True)
class HeatCalc:
    size: str
    material: str
    ambient_f: int
    factor: float
    base_90c: int          # Table 310.16, 90 C column
    corrected_a: float     # base x factor, before the termination limit
    cap_a: int             # the termination column's ampacity
    cap_column: int        # 75, or 60 where the terminals are only rated for that
    carries_a: float       # what the conductor must carry: the breaker, or the MCA on a motor load
    carries_label: str

    @property
    def usable_a(self) -> float:
        """The corrected ampacity, limited to the termination column."""
        return min(self.corrected_a, self.cap_a)

    @property
    def passed(self) -> bool:
        return self.usable_a >= self.carries_a

    @property
    def ambient_c(self) -> float:
        return celsius(self.ambient_f)

    @property
    def wire(self) -> str:
        return f"{size_label(self.size)} {METAL[self.material]} THWN-2"

    @property
    def line(self) -> str:
        """The calculation, in one line, for the one-line page and the check."""
        limited = (f", limited to {self.cap_a} A by the {self.cap_column}{DEGREE}C terminals"
                   if self.corrected_a > self.cap_a else "")
        return (f"{self.wire}: {self.base_90c} A at 90{DEGREE}C x {self.factor:.2f} "
                f"({self.ambient_f}{DEGREE}F, {self.ambient_c:.1f}{DEGREE}C) = {self.corrected_a:.1f} A"
                f"{limited}; {self.carries_label} {self.carries_a:g} A: {'OK' if self.passed else 'TOO SMALL'}")


def heat_calc(
    size: str, material: str, ambient_f: int, *, cap_a: int, cap_column: int = 75,
    carries_a: float, carries_label: str = "breaker",
) -> HeatCalc:
    return HeatCalc(
        size=size, material=material, ambient_f=ambient_f, factor=correction_factor(ambient_f),
        base_90c=AMPACITY_90C[material][size], corrected_a=AMPACITY_90C[material][size] * correction_factor(ambient_f),
        cap_a=cap_a, cap_column=cap_column, carries_a=carries_a, carries_label=carries_label,
    )


def survives(
    size: str, material: str, ambient_f: int | None, *, cap_a: int, cap_column: int = 75,
    carries_a: float,
) -> bool:
    """True when no temperature correction applies, or the corrected ampacity still carries the load."""
    if ambient_f is None:
        return True
    return heat_calc(size, material, ambient_f, cap_a=cap_a, cap_column=cap_column, carries_a=carries_a).passed


def exposure_flags(job) -> list[str]:
    """Where a run is outdoors but the city has no design temperature set, say the correction is still owed."""
    if job.sun_exposed and job.jurisdiction.design_ambient_f is None:
        return ["Part of this run is outdoors or in the sun. Apply the NEC 310.15(B)(1) temperature correction "
                "for the site's design ambient: this city's design temperature isn't set up yet."]
    return []
