"""Page images and one-file-per-document downloads from a packet PDF."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pypdfium2

# Preview renders, sharpest first: 144 dpi at full chroma (no 4:2:0 subsampling, which smears thin colored
# plan lines and the aerial). A packet whose pages would pass PREVIEW_BUDGET_BYTES steps down, so the review
# response stays well under Vercel's 4.5 MB function response limit (base64 adds a third). The third step is
# the old 108 dpi setting. (scale, JPEG quality, chroma subsampling)
RENDERS = ((2.0, 85, 0), (2.0, 75, 0), (1.5, 80, 2), (1.5, 65, 2))
PREVIEW_BUDGET_BYTES = 2_500_000


LETTER_WIDTH_PT = 612.0


def _render(document: pypdfium2.PdfDocument, scale: float, quality: int, subsampling: int) -> list[bytes]:
    images = []
    for page in document:
        buffer = BytesIO()
        # Every page previews at the width a letter page gets, so a 22 x 34 in sheet stays a sane size.
        page_scale = scale * min(1.0, LETTER_WIDTH_PT / page.get_width())
        page.render(scale=page_scale).to_pil().convert("RGB").save(
            buffer, format="JPEG", quality=quality, subsampling=subsampling,
        )
        images.append(buffer.getvalue())
    return images


def packet_page_images(pdf: bytes) -> list[bytes]:
    document = pypdfium2.PdfDocument(pdf)
    try:
        for settings in RENDERS:
            images = _render(document, *settings)
            if sum(map(len, images)) <= PREVIEW_BUDGET_BYTES:
                break
        return images
    finally:
        document.close()


def pdf_page_count(pdf: bytes) -> int:
    document = pypdfium2.PdfDocument(pdf)
    try:
        return len(document)
    finally:
        document.close()


def _document_pages(page_count: int, attachments: tuple[int, int] | None) -> list[list[int]]:
    """One document per packet page; attached data sheets ride with the page they follow."""
    documents: list[list[int]] = []
    index = 0
    while index < page_count:
        pages = [index]
        if attachments and index == attachments[0] - 1:
            pages += list(range(index + 1, min(index + 1 + attachments[1], page_count)))
        documents.append(pages)
        index = pages[-1] + 1
    return documents


def packet_documents_zip(pdf: bytes, file_stems: tuple[str, ...]) -> bytes:
    """Portals often want each document as its own upload, one file per page."""
    from permit_packets.core.equipment import attachment_span

    source = pypdfium2.PdfDocument(pdf)
    buffer = BytesIO()
    try:
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            for index, pages in enumerate(_document_pages(len(source), attachment_span(pdf))):
                name = file_stems[index] if index < len(file_stems) else f"{index + 1:02d}-page"
                single = pypdfium2.PdfDocument.new()
                single.import_pages(source, pages)
                page = BytesIO()
                single.save(page)
                single.close()
                archive.writestr(f"{name}.pdf", page.getvalue())
    finally:
        source.close()
    return buffer.getvalue()
