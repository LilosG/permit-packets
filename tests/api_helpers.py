"""Calls to the packet API that tests share."""
from __future__ import annotations

import base64


def with_pdf(client, packet_url: str, payload: dict) -> dict:
    """The review response plus the PDF from its own endpoint, as base64 under "pdf"."""
    response = client.post(packet_url, json=payload)
    assert response.status_code == 200, response.text
    pdf = client.post(packet_url.removesuffix("/packet") + "/pdf", json=payload)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    return {**response.json(), "pdf": base64.b64encode(pdf.content).decode()}
