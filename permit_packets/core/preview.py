"""Page images and one-file-per-document downloads from a packet PDF."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pypdfium2

SCALE = 1.5
JPEG_QUALITY = 80
DOCUMENT_NAMES = (
    "01-checklist-and-checks", "02-permit-application-data", "03-site-plan", "04-one-line-diagram",
    "05-load-calculation", "06-equipment-data", "07-pre-submittal-review",
)


def packet_page_images(pdf: bytes) -> list[bytes]:
    document = pypdfium2.PdfDocument(pdf)
    try:
        images = []
        for page in document:
            buffer = BytesIO()
            page.render(scale=SCALE).to_pil().convert("RGB").save(
                buffer, format="JPEG", quality=JPEG_QUALITY,
            )
            images.append(buffer.getvalue())
        return images
    finally:
        document.close()


def packet_documents_zip(pdf: bytes) -> bytes:
    """Portals often want each document as its own upload."""
    source = pypdfium2.PdfDocument(pdf)
    buffer = BytesIO()
    try:
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            for index in range(len(source)):
                name = DOCUMENT_NAMES[index] if index < len(DOCUMENT_NAMES) else f"{index + 1:02d}-page"
                single = pypdfium2.PdfDocument.new()
                single.import_pages(source, [index])
                page = BytesIO()
                single.save(page)
                single.close()
                archive.writestr(f"{name}.pdf", page.getvalue())
    finally:
        source.close()
    return buffer.getvalue()
