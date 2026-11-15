"""Vercel refuses a function response over 4.5 MB (FUNCTION_RESPONSE_PAYLOAD_TOO_LARGE). The heaviest job the
app accepts must stay well under it on both the review request and the PDF request."""
from __future__ import annotations

import base64
import json
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import app
from permit_packets.core.schemas import MAX_AERIAL_BASE64
from tests.test_ev_golden import GOLDEN, to_current_request

VERCEL_LIMIT = 4_500_000
HEADROOM = 0.85  # fail well before the limit, not at it


def _heaviest_aerial() -> str:
    """Random noise compresses worst of all: the largest aerial the API accepts, near MAX_AERIAL_BASE64."""
    rng = np.random.default_rng(0)
    image = Image.fromarray(rng.integers(0, 256, (1400, 1400, 3), dtype=np.uint8))
    for quality in range(60, 20, -5):
        out = BytesIO()
        image.save(out, "JPEG", quality=quality, subsampling=0)
        encoded = base64.b64encode(out.getvalue()).decode()
        if len(encoded) <= MAX_AERIAL_BASE64:
            return encoded
    raise AssertionError("could not make an aerial under the API limit")


@pytest.fixture
def client() -> TestClient:
    signed_in = TestClient(app)
    assert signed_in.post("/api/signin", json={"password": "test-password"}).status_code == 200
    return signed_in


def test_the_heaviest_ev_packet_fits_in_a_vercel_response_on_both_requests(client):
    job = to_current_request(json.loads((GOLDEN / "cases" / "el_cajon_detached_trench_plan.json").read_text()))
    job["charger_model"] = "Emporia Level 2 EV Charger"  # the largest data sheet in the library, 1.5 MB
    job["plan"]["aerial_base64"] = _heaviest_aerial()
    assert len(job["plan"]["aerial_base64"]) > 0.8 * MAX_AERIAL_BASE64

    review = client.post("/api/jobs/ev-charger/packet", json=job)
    pdf = client.post("/api/jobs/ev-charger/pdf", json=job)
    assert review.status_code == pdf.status_code == 200
    assert len(review.content) < HEADROOM * VERCEL_LIMIT, f"review response {len(review.content):,} bytes"
    assert len(pdf.content) < HEADROOM * VERCEL_LIMIT, f"PDF response {len(pdf.content):,} bytes"


def test_an_ordinary_packet_previews_at_the_sharp_setting(client):
    job = to_current_request(json.loads((GOLDEN / "cases" / "el_cajon_detached_trench_plan.json").read_text()))
    pages = client.post("/api/jobs/ev-charger/packet", json=job).json()["pages"]
    first = Image.open(BytesIO(base64.b64decode(pages[0])))
    assert first.width >= 8.5 * 72 * 2 - 1, "the first render setting is 2x (144 dpi)"
    assert first.layer[0][1:3] == (1, 1), "full chroma"


def test_the_heaviest_san_francisco_drawing_set_fits_on_both_requests(client):
    """22 x 34 in sheets: the aerial is placed once, not copied per sheet, so the PDF stays small."""
    from permit_packets.jurisdictions import jurisdiction_by_key
    from tests.packet_helpers import complete_inputs

    job = complete_inputs("ev_charger", jurisdiction_by_key("san-francisco-ca"))
    job["charger_model"] = "Emporia Level 2 EV Charger"
    job["plan"]["aerial_base64"] = _heaviest_aerial()
    review = client.post("/api/jobs/ev-charger/packet", json=job)
    pdf = client.post("/api/jobs/ev-charger/pdf", json=job)
    assert review.status_code == pdf.status_code == 200, review.text[:200]
    assert len(review.content) < HEADROOM * VERCEL_LIMIT, f"review response {len(review.content):,} bytes"
    assert len(pdf.content) < HEADROOM * VERCEL_LIMIT, f"PDF response {len(pdf.content):,} bytes"
