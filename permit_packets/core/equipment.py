"""Equipment library: common chargers and panels, with the manufacturer's data sheet attached
behind the packet's equipment page when the job names one of them.

Every data sheet in data_sheets/ is the manufacturer's own published PDF, unchanged except for
page selection (the Tesla Gen 3 sheet is the specification and breaker pages of Tesla's manual).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PageObject, PdfReader, PdfWriter, Transformation

DATA_SHEETS = Path(__file__).parent / "data_sheets"
ATTACHMENTS_KEY = "/PacketAttachments"


def attachment_span(pdf: bytes) -> tuple[int, int] | None:
    """(pages before the attachments, attached page count), if data sheets were attached."""
    value = (PdfReader(BytesIO(pdf)).metadata or {}).get(ATTACHMENTS_KEY)
    if not value:
        return None
    after, count = str(value).split(":")
    return int(after), int(count)


@dataclass(frozen=True)
class Equipment:
    kind: str            # "charger" or "panel"
    name: str            # what the electrician picks, e.g. "Tesla Wall Connector (Gen 3)"
    max_amps: int
    listing: str
    data_sheet: str      # file name in data_sheets/
    aliases: tuple[str, ...] = ()
    # Panels only, from the manufacturer's data sheet: bus rating, main type and size, enclosure, and
    # whether it is a meter-main (meter socket and main breaker in one outdoor enclosure).
    bus_amps: int | None = None
    main: str | None = None  # "breaker" or "lug"
    main_amps: int | None = None
    outdoor: bool = False
    meter_main: bool = False

    def data_sheet_path(self) -> Path:
        return DATA_SHEETS / self.data_sheet


CHARGERS = (
    Equipment("charger", "Tesla Wall Connector (Gen 3)", 48, "cULus E351001, UL 2594",
              "tesla-gen3-wall-connector.pdf", ("tesla wall connector", "tesla gen 3", "tesla gen3")),
    Equipment("charger", "Tesla Universal Wall Connector", 48, "cULus E351001, UL 2594, UL 2231",
              "tesla-universal-wall-connector.pdf", ("tesla universal",)),
    Equipment("charger", "ChargePoint Home Flex (CPH50)", 50, "UL and cUL listed, UL 2594, UL 2231-1, UL 2231-2",
              "chargepoint-home-flex.pdf", ("chargepoint home flex", "chargepoint", "cph50")),
    Equipment("charger", "Emporia Level 2 EV Charger", 48, "UL listed, UL 2594",
              "emporia-classic-ev-charger.pdf", ("emporia",)),
    Equipment("charger", "Wallbox Pulsar Plus (North America)", 48, "UL 2594, UL 2231 (NRTL)",
              "wallbox-pulsar-plus.pdf", ("wallbox pulsar plus", "pulsar plus", "wallbox")),
)

PANELS = (
    # Data sheet: 225 A bus, 200 A 2-pole main breaker, NEMA 1 indoor enclosure.
    Equipment("panel", "Square D Homeline HOM3060M200PC, 200 A main breaker", 200, "UL listed, file E-6294 (UL 67)",
              "square-d-homeline-hom3060m200pc.pdf", ("hom3060m200pc", "square d homeline 200"),
              bus_amps=225, main="breaker", main_amps=200),
    # Data sheet: 225 A bus, main lugs (no main breaker), NEMA 1 indoor enclosure.
    Equipment("panel", "Square D Homeline HOM3060L225PGC, 225 A main lug", 225, "UL listed, file E-6294 (UL 67)",
              "square-d-homeline-hom3060l225pgc.pdf", ("hom3060l225pgc", "square d homeline 225"),
              bus_amps=225, main="lug"),
    # Data sheet: meter socket with a 200 A main breaker and 8 branch circuits, 200 A continuous, Type 3R.
    Equipment("panel", "Milbank U5168-XTL-200 meter-main, 200 A", 200, "UL listed, Type 3R",
              "milbank-u5168-xtl-200.pdf", ("u5168 xtl 200", "u5168xtl200", "milbank u5168"),
              bus_amps=200, main="breaker", main_amps=200, outdoor=True, meter_main=True),
)

LIBRARY = CHARGERS + PANELS


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def find_equipment(model: str, kind: str) -> Equipment | None:
    """The library entry a typed or picked model name stands for, if any."""
    wanted = _normal(model)
    if not wanted:
        return None
    for item in LIBRARY:
        if item.kind != kind:
            continue
        if wanted == _normal(item.name) or any(wanted == _normal(alias) for alias in item.aliases):
            return item
    for item in LIBRARY:
        if item.kind == kind and any(_normal(alias) in wanted for alias in (item.name, *item.aliases)):
            return item
    return None


DATA_SHEET_MARGIN_PT = 18.0  # a quarter inch all round when a data sheet is fitted to the packet's sheet


def _add_on_packet_sheet(writer: PdfWriter, page: PageObject, width: float, height: float) -> None:
    """A manufacturer's page centered on a sheet the packet's size, scaled down only if it doesn't fit.

    Cities that take one combined PDF want every sheet one standard size (Chandler: one size from
    8.5 x 11 up to 30 x 42), and manufacturers print on whatever size they like."""
    box = page.mediabox  # library data sheets are unrotated (tests/test_equipment.py)
    w, h = float(box.width), float(box.height)
    room_w, room_h = width - 2 * DATA_SHEET_MARGIN_PT, height - 2 * DATA_SHEET_MARGIN_PT
    scale = min(1.0, room_w / w, room_h / h)
    x = (width - w * scale) / 2 - float(box.left) * scale
    y = (height - h * scale) / 2 - float(box.bottom) * scale
    sheet = writer.add_blank_page(width=width, height=height)
    sheet.merge_transformed_page(page, Transformation().scale(scale).translate(x, y))


def attach_data_sheets(packet_pdf: bytes, sheets: list[Equipment], *, after_title: str) -> bytes:
    """Insert each data sheet right after the packet page whose text starts with after_title."""
    if not sheets:
        return packet_pdf
    packet = PdfReader(BytesIO(packet_pdf))
    insert_at = len(packet.pages)
    for index, page in enumerate(packet.pages):
        if after_title in (page.extract_text() or ""):
            insert_at = index + 1
            break
    writer = PdfWriter()
    for page in packet.pages[:insert_at]:
        writer.add_page(page)
    size = packet.pages[0].mediabox
    width, height = float(size.width), float(size.height)
    for sheet in sheets:
        for page in PdfReader(str(sheet.data_sheet_path())).pages:
            _add_on_packet_sheet(writer, page, width, height)
    for page in packet.pages[insert_at:]:
        writer.add_page(page)
    metadata = {key: str(value) for key, value in (packet.metadata or {}).items()}
    attached = sum(len(PdfReader(str(sheet.data_sheet_path())).pages) for sheet in sheets)
    # Lets the one-file-per-document download keep the data sheets with the equipment page.
    metadata[ATTACHMENTS_KEY] = f"{insert_at}:{attached}"
    writer.add_metadata(metadata)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def library_json() -> dict:
    return {kind: [item.name for item in LIBRARY if item.kind == kind] for kind in ("charger", "panel")}
