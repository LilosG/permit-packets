"""Page images of a packet, so it shows on screen in any browser."""
from __future__ import annotations

from io import BytesIO

import pypdfium2

SCALE = 1.6
JPEG_QUALITY = 82


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
