"""The Photos pages: site photos the electrician attaches, printed after the packet's own pages.

Utilities and cities often ask for photos of the existing meter and panel, the proposed location and the
gas meter clearances. Photos are optional on every job type. Each one is re-encoded here, which drops its
EXIF data (a phone photo carries the GPS position of the house) and caps its size.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps
from reportlab.lib.units import inch
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import Spacer, Table, TableStyle

from permit_packets.core.layout import current_sheet

PHOTOS_TITLE = "Site Photos"
PER_PAGE = 4
LONG_SIDE_PX = 1600
JPEG_QUALITY = 82

PHOTOS: ContextVar[tuple | None] = ContextVar("photos", default=None)


@dataclass(frozen=True)
class PreparedPhoto:
    label: str
    caption: str
    jpeg: bytes
    width: int
    height: int


@contextmanager
def use_photos(photos):
    token = PHOTOS.set(tuple(photos) if photos else None)
    try:
        yield
    finally:
        PHOTOS.reset(token)


def prepare(photo) -> PreparedPhoto:
    """Upright, RGB, at most LONG_SIDE_PX on a side, with no metadata."""
    with Image.open(BytesIO(photo.image_bytes())) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, "white")
            background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
            image = background
        else:
            image = image.convert("RGB")
        image.thumbnail((LONG_SIDE_PX, LONG_SIDE_PX))
        out = BytesIO()
        image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return PreparedPhoto(photo.label, photo.caption, out.getvalue(), image.width, image.height)


def photo_page_count(photos) -> int:
    return -(-len(photos) // PER_PAGE) if photos else 0


def _cell(photo: PreparedPhoto, max_w: float, max_h: float) -> list:
    from permit_packets.core.pdf_base import CELL_BOLD, SMALL, _p

    scale = min(max_w / photo.width, max_h / photo.height)
    image = PdfImage(BytesIO(photo.jpeg), width=photo.width * scale, height=photo.height * scale)
    cell = [image, Spacer(1, 4), _p(photo.label, CELL_BOLD)]
    if photo.caption:
        cell.append(_p(photo.caption, SMALL))
    return cell


def photo_pages(photos) -> list[list]:
    """One list of flowables per page, up to PER_PAGE photos each, two across."""
    from permit_packets.core.pdf_base import H1, SMALL, _p

    prepared = [prepare(photo) for photo in photos]
    sheet = current_sheet()
    pages = []
    gap = 14.0
    col_w = (sheet.content_w - gap) / 2
    row_h = (sheet.content_h - 62) / 2
    for start in range(0, len(prepared), PER_PAGE):
        chunk = prepared[start:start + PER_PAGE]
        cells = [_cell(photo, col_w - 8, row_h - 44) for photo in chunk]
        rows = [cells[i:i + 2] for i in range(0, len(cells), 2)]
        rows = [row + [""] * (2 - len(row)) for row in rows]
        table = Table(rows, colWidths=[col_w, col_w], rowHeights=[row_h] * len(rows), hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), gap), ("RIGHTPADDING", (1, 0), (1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        pages.append([
            _p(PHOTOS_TITLE, H1),
            _p(f"Provided by the contractor. {len(prepared)} photo{'s' if len(prepared) != 1 else ''}. "
               "Replace with new photos if conditions change.", SMALL),
            Spacer(1, 8), table,
        ])
    return pages
