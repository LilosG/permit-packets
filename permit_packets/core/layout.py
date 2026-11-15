"""Page geometry: where the content frame and the title block sit on a sheet."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from reportlab.lib.units import inch


@dataclass(frozen=True)
class Sheet:
    key: str
    width: float
    height: float
    margin: float = 0.7 * inch
    top_margin: float = 0.6 * inch
    block_h: float = 66.0       # height of the title block
    block_y: float = 30.0       # from the bottom edge to the bottom of the title block
    gap: float = 8.0            # between the title block and the content frame

    @property
    def landscape(self) -> bool:
        return self.width > self.height

    @property
    def content_w(self) -> float:
        return self.width - 2 * self.margin

    @property
    def frame_y(self) -> float:
        return self.block_y + self.block_h + self.gap

    @property
    def content_h(self) -> float:
        return self.height - self.top_margin - self.frame_y


LETTER = Sheet("letter", 612.0, 792.0)  # 8.5 x 11, portrait
TABLOID = Sheet("tabloid", 1224.0, 792.0, block_h=58.0)  # 11 x 17, landscape
# A 22 x 34 in drawing set: pages are laid out on letter, then the drawing sheets are printed at
# PRINT_MAGNIFICATION on 22 x 34 sheets (core/drawing_sets.py). Supplemental pages stay 8.5 x 11.
ANSI_D = Sheet("ansi_d", 612.0, 792.0)
SHEETS = {"letter": LETTER, "tabloid": TABLOID, "ansi_d": ANSI_D}
PRINT_MAGNIFICATION = {"ansi_d": 2.5}


def print_magnification(sheet: "Sheet | None" = None) -> float:
    """How much larger than drawn a drawing sheet prints: 2.5 on a 22 x 34 set, else 1."""
    return PRINT_MAGNIFICATION.get((sheet or current_sheet()).key, 1.0)


def resolve_sheet(asked: str | None, jurisdiction) -> Sheet:
    """The sheet the request asked for, else the city's preference."""
    return SHEETS.get(asked or "") or SHEETS.get(jurisdiction.sheet_size, LETTER)

_CURRENT: ContextVar[Sheet] = ContextVar("sheet", default=LETTER)


def current_sheet() -> Sheet:
    return _CURRENT.get()


def content_w() -> float:
    return current_sheet().content_w


@contextmanager
def use_sheet(sheet: Sheet):
    token = _CURRENT.set(sheet)
    try:
        yield sheet
    finally:
        _CURRENT.reset(token)
