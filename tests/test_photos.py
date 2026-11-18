"""Optional site photos: every job type takes them, they print after the packet's pages, and the server
strips what a phone embeds in a photo."""
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from pypdf import PdfReader

from permit_packets.core.schemas import MAX_PHOTOS, PhotoRequest

PASSWORD = "photos-demo-password"


def _image(width=1200, height=800, fmt="JPEG", color="#556677", exif=False) -> str:
    image = Image.new("RGB", (width, height), color)
    out = io.BytesIO()
    if exif:
        data = Image.Exif()
        data[0x010F] = "Camera Maker"  # Make
        data[0x8825] = {1: "N", 2: (37.0, 14.0, 24.0)}  # a GPS block
        image.save(out, fmt, exif=data)
    else:
        image.save(out, fmt)
    return base64.b64encode(out.getvalue()).decode()


def _photo(label="Existing meter and panel", **kwargs) -> dict:
    return {"label": label, "caption": "North wall", "image_base64": _image(**kwargs)}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("CLIENT_PASSWORDS", raising=False)
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    from app import app

    session = TestClient(app)
    assert session.post("/api/signin", json={"password": PASSWORD}).status_code == 200
    return session


def _ev_body(photos):
    return {
        "customer": "Sample Homeowner", "address": "123 Sample St", "city": "Chico", "state": "CA",
        "jurisdiction_key": "chico-ca", "contractor": "Sample Electric", "license_number": "000000",
        "home": {"square_feet": 1800, "range_va": 12000, "dryer_va": 5000, "water_heater_va": 4500,
                 "dishwasher_va": 1200, "cooling_va": 7200},
        "service_amps": 200, "open_breaker_spaces": 4, "charger_amps": 48, "charger_model": "Tesla Wall Connector (Gen 3)",
        "charger_venting_required": False, "hoa_approval": "not_required", "location": "exterior_wall", "run_ft": 40,
        "available_fault_current_a": 10000, "equipment_aic_ka": 10, "panel_location": "North wall",
        "panel_bus_amps": 200, "panel_main": "main breaker", "gec_size": "#4 Cu", "photos": photos,
    }


def _pages(client, body):
    pdf = client.post("/api/jobs/ev-charger/pdf", json=body)
    assert pdf.status_code == 200
    return PdfReader(io.BytesIO(pdf.content)).pages


def test_no_photos_adds_no_pages(client):
    without = len(_pages(client, _ev_body([])))
    assert not any("Site Photos" in (page.extract_text() or "") for page in _pages(client, _ev_body([])))
    assert without >= 8


def test_photos_print_four_to_a_page_after_the_packet(client):
    base = len(_pages(client, _ev_body([])))
    five = _pages(client, _ev_body([_photo() for _ in range(5)]))
    assert len(five) == base + 2
    for page in list(five)[-2:]:
        text = page.extract_text()
        assert "Site Photos" in text and "5 photos" in text
    assert "Existing meter and panel" in list(five)[-2].extract_text()


def test_packet_lists_a_document_for_each_photo_page(client):
    body = client.post("/api/jobs/ev-charger/packet", json=_ev_body([_photo() for _ in range(5)])).json()
    titles = [document["title"] for document in body["documents"]]
    assert titles[-2:] == ["Site Photos", "Site Photos"]
    stems = [document["file_stem"] for document in body["documents"]]
    assert stems[-2:] == [f"{len(stems) - 1:02d}-site-photos-1", f"{len(stems):02d}-site-photos-2"]


def test_photos_work_on_every_residential_job_type(client):
    from permit_packets.job_types import REGISTRY

    for slug in ("ev-charger",):
        assert slug in {job.slug for job in REGISTRY.values()}
    # Every job type builds through build_on_sheet, which sets the photos for its pages.
    import inspect

    from permit_packets.core import job_inputs

    assert "use_photos(request.photos)" in inspect.getsource(job_inputs.build_on_sheet)
    for job in REGISTRY.values():
        assert "photos" in job.request_model.model_fields, job.key


def test_phone_metadata_is_stripped_from_printed_photos(client):
    raw = _image(exif=True)
    assert b"Exif" in base64.b64decode(raw)
    from permit_packets.core.photos import prepare

    prepared = prepare(PhotoRequest(label="Other", image_base64=raw))
    with Image.open(io.BytesIO(prepared.jpeg)) as image:
        assert not image.getexif() and b"Exif" not in prepared.jpeg


def test_large_photos_are_shrunk_and_rotated_upright():
    from permit_packets.core.photos import LONG_SIDE_PX, prepare

    image = Image.new("RGB", (3000, 1000), "white")
    data = Image.Exif()
    data[0x0112] = 6  # rotated 90 degrees: the picture should come out tall
    out = io.BytesIO()
    image.save(out, "JPEG", exif=data)
    prepared = prepare(PhotoRequest(label="Other", image_base64=base64.b64encode(out.getvalue()).decode()))
    assert max(prepared.width, prepared.height) <= LONG_SIDE_PX
    assert prepared.height > prepared.width


def test_png_with_transparency_is_flattened_on_white():
    from permit_packets.core.photos import prepare

    image = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    out = io.BytesIO()
    image.save(out, "PNG")
    prepared = prepare(PhotoRequest(label="Other", image_base64=base64.b64encode(out.getvalue()).decode()))
    with Image.open(io.BytesIO(prepared.jpeg)) as flattened:
        assert flattened.getpixel((10, 10))[0] > 240


@pytest.mark.parametrize("bad", ["not base64 at all!" * 10, base64.b64encode(b"x" * 500).decode()])
def test_non_images_are_rejected(client, bad):
    body = _ev_body([{"label": "Other", "image_base64": bad}])
    assert client.post("/api/jobs/ev-charger/packet", json=body).status_code == 422


def test_gif_is_rejected():
    with pytest.raises(ValidationError):
        PhotoRequest(label="Other", image_base64=_image(fmt="GIF"))


def test_more_than_the_limit_is_rejected(client):
    body = _ev_body([_photo() for _ in range(MAX_PHOTOS + 1)])
    assert client.post("/api/jobs/ev-charger/packet", json=body).status_code == 422


def test_photos_that_together_exceed_a_request_are_rejected(client):
    import random

    random.seed(1)
    noise = Image.frombytes("RGB", (700, 700), bytes(random.getrandbits(8) for _ in range(700 * 700 * 3)))
    out = io.BytesIO()
    noise.save(out, "JPEG", quality=95)
    big = base64.b64encode(out.getvalue()).decode()
    assert 600_000 < len(big) < 900_000
    body = _ev_body([{"label": "Other", "image_base64": big} for _ in range(5)])
    response = client.post("/api/jobs/ev-charger/packet", json=body)
    assert response.status_code == 422 and "too large" in response.text


def test_photos_do_not_change_the_packet_checks(client):
    plain = client.post("/api/jobs/ev-charger/packet", json=_ev_body([])).json()
    with_photos = client.post("/api/jobs/ev-charger/packet", json=_ev_body([_photo()])).json()
    assert plain["checks"] == with_photos["checks"] and plain["ready"] == with_photos["ready"]
