"""Panel schedule: the panel's circuit directory with the new work marked, for every job type.

The schedule lists the existing circuits only as the electrician entered them. When none were
entered it prints an empty directory grid marked "Field verify and fill in" and the packet is not
ready: circuits are never worked out from the load calculation, because a made-up directory on a
permit drawing is worse than a blank one.
"""
from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.units import inch
from reportlab.platypus import KeepInFrame, Spacer, Table, TableStyle

from permit_packets.core.cad import note_panels
from permit_packets.core.checks import Check
from permit_packets.core.layout import current_sheet
from permit_packets.core.pdf_base import BODY, CELL_BOLD, H1, H2, SMALL, TIGHT, _heads, _p, _table, content_w

DIRECTORY_NOTE = ("Update the panel directory on site so every circuit is legibly identified "
                  "(NEC 408.4(A)).")
MISSING_FLAG = "Enter the panel's existing circuits for the panel schedule."
FIELD_VERIFY = "Field verify and fill in"
PANEL_SCHEDULE_ITEM = "Panel schedule with the panel's existing circuits (NEC 408.4)"
GRID_ROWS = {False: 20, True: 40}  # blank circuit lines when none were entered, portrait and landscape


@dataclass(frozen=True)
class ExistingCircuit:
    label: str
    amps: int
    poles: int = 1


@dataclass(frozen=True)
class ScheduleRow:
    label: str
    breaker: str
    poles: int
    status: str  # New, Existing, Transferred, Planned


def existing_rows(entered: tuple[ExistingCircuit, ...], status: str = "Existing") -> list[ScheduleRow]:
    """The circuits the electrician entered, and nothing else."""
    return [ScheduleRow(c.label, f"{c.amps} A", c.poles, status) for c in entered]


def existing_circuits(entered: list[dict]) -> tuple[ExistingCircuit, ...]:
    return tuple(ExistingCircuit(**circuit) for circuit in entered)


def panel_schedule_check(job) -> Check:
    if job.existing_circuits:
        count = len(job.existing_circuits)
        return Check("Panel schedule", f"{count} existing circuit{'s' if count != 1 else ''} entered", True)
    return Check("Panel schedule", MISSING_FLAG, False)


def panel_schedule_row(job, page: int) -> tuple[str, str]:
    """The cover checklist's (where, status) for the panel schedule."""
    if job.existing_circuits:
        return f"Page {page}: existing circuits as entered", "Ready"
    return f"Page {page}: {FIELD_VERIFY.lower()}", "Open"


def _rows_table(rows: list[ScheduleRow], width: float, *, numbered_from: int | None = None):
    head = ["Circuit", "Breaker", "Poles", "Status"]
    body = [_heads(*(["Ckt"] + head if numbered_from is not None else head))]
    for index, row in enumerate(rows):
        bold = row.status == "New"
        cell = (lambda text: _p(text, CELL_BOLD)) if bold else _p
        cells = [cell(row.label), cell(row.breaker), cell(str(row.poles) if row.poles else ""), cell(row.status)]
        if numbered_from is not None:
            cells.insert(0, _p(str(numbered_from + index)))
        body.append(cells)
    if numbered_from is None:
        return _table(body, [width - 3.3 * inch, 1.3 * inch, 0.8 * inch, 1.2 * inch])
    return _table(body, [0.5 * inch, width - 3.8 * inch, 1.3 * inch, 0.8 * inch, 1.2 * inch], extra=TIGHT)


def _two_columns(left, right, width: float, gap: float):
    each = (width - gap) / 2
    return Table([[left, right]], colWidths=[each + gap, each],
                 style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))


def _panel_tables(rows: list[ScheduleRow], *, entered: bool):
    """One table on letter. On a tabloid sheet a long directory runs in two columns side by side.

    Without entered circuits the new work leads and an empty numbered directory follows."""
    sheet = current_sheet()
    width = sheet.content_w
    if not entered:
        count = GRID_ROWS[sheet.landscape]
        blanks = [ScheduleRow("", "", 0, "") for _ in range(count)]
        blanks[0] = ScheduleRow(FIELD_VERIFY, "", 0, "")
        if sheet.landscape:
            half = count // 2
            each = (width - 18) / 2
            left = [*rows, *blanks[:half]]
            return _two_columns(_rows_table(left, each, numbered_from=1),
                                _rows_table(blanks[half:], each, numbered_from=half + 1), width, 18)
        return _rows_table([*rows, *blanks], width, numbered_from=1)
    if not sheet.landscape or len(rows) < 12:
        return _rows_table(rows, width)
    half = -(-len(rows) // 2)
    each = (width - 18) / 2
    return _two_columns(_rows_table(rows[:half], each), _rows_table(rows[half:], each), width, 18)


def _header_table(header: list[tuple[str, str]]):
    from permit_packets.core.pdf_base import LABEL

    return _table([[_p(label.upper(), LABEL) for label, _ in header], [_p(value, CELL_BOLD) for _, value in header]],
                  [content_w() / len(header)] * len(header))


def panel_schedule_page(panels: list[tuple[str, list[ScheduleRow]]], *, entered: bool,
                        spaces_note: str | None = None, header: list[tuple[str, str]] | None = None) -> list:
    """One table per panel. `panels` pairs a heading (e.g. "Main panel, 200 A") with its rows.

    Rows are the new work and, when `entered`, the existing circuits as the electrician gave them."""
    note_panels(panels, header, entered, current_sheet().landscape, spaces_note)
    story = [
        _p("Panel Schedule", H1),
        _p("Circuit directory with the new work marked. "
           + ("Existing circuits as entered by the electrician." if entered else
              f"{FIELD_VERIFY}: no existing circuits were entered, so the directory is left blank rather "
              "than guessed. Enter the panel's circuits in the form to print them here."), SMALL),
        Spacer(1, 8),
    ]
    if header:
        story += [_header_table(header), Spacer(1, 8)]
    for index, (heading, rows) in enumerate(panels):
        # Only the first panel is the one whose existing circuits are entered.
        story += [_p(heading, H2), _panel_tables(rows, entered=entered or index > 0), Spacer(1, 10)]
    if spaces_note:
        story.append(_p(spaces_note, BODY))
        story.append(Spacer(1, 4))
    story.append(_p(DIRECTORY_NOTE, SMALL))
    # One sheet however many circuits or panels: a long directory shrinks to fit.
    sheet = current_sheet()
    return [KeepInFrame(sheet.content_w, sheet.content_h - 4, story, mode="shrink")]
