"""Writes the golden EV cases and the packets they produce today.

Run once, against the app as it was before the job-type refactor:

    DEMO_PASSWORD=snap PYTHONPATH=. python tests/golden/make_snapshots.py

The case files are request payloads in the original /api/ev/* shape (the plan
uses "panel" and "charger"). The snapshots are the contract: every later
change has to reproduce them. tests/test_ev_golden.py replays the cases and
maps them to whatever the current routes expect.
"""
from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from pathlib import Path

import pypdfium2
from fastapi.testclient import TestClient
from PIL import Image

os.environ.setdefault("DEMO_PASSWORD", "snap")

from app import app  # noqa: E402  (needs DEMO_PASSWORD first)

HERE = Path(__file__).parent
CASES = HERE / "cases"
SNAPSHOTS = HERE / "snapshots"
SQUARE_LOT = [[250, 250], [750, 250], [750, 750], [250, 750]]
SAMPLE = dict(
    customer="Sample Homeowner", address="123 Sample St", contractor="Sample Electric, LLC",
    license_number="ROC 000000",
)


def aerial_base64() -> str:
    buffer = BytesIO()
    Image.new("RGB", (600, 600), "#8a9a7b").save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def cases() -> dict[str, dict]:
    aerial = aerial_base64()
    plain_home = {"square_feet": 2000, "range_va": 12000, "cooling_va": 7200}
    return {
        "oro_valley_attached_no_plan": {
            **SAMPLE, "jurisdiction_key": "oro-valley-az", "location": "attached_garage",
            "charger_amps": 40, "run_ft": 30, "trench_ft": 0, "service_amps": 200,
            "open_breaker_spaces": 4, "home": plain_home,
        },
        "el_cajon_detached_trench_plan": {
            **SAMPLE, "city": "El Cajon", "state": "CA", "jurisdiction_key": "el-cajon-ca",
            "location": "detached_garage", "charger_amps": 48, "run_ft": 120, "trench_ft": 80,
            "service_amps": 200, "open_breaker_spaces": 4, "home": plain_home,
            "plan": {
                "scale_ft_per_in": 30, "panel": [400, 500], "charger": [700, 300], "route": [[550, 500]],
                "buildings": [[[350, 350], [650, 350], [650, 650], [350, 650]]], "primary_building": 0,
                "lot": [[250, 250], [750, 250], [750, 750], [250, 750]], "parcel_number": "482-110-22-00",
                "aerial_base64": aerial, "credits": ["Credit"],
            },
        },
        "over_capacity_worst_case": {
            **SAMPLE, "jurisdiction_key": "oro-valley-az", "service_amps": 100, "open_breaker_spaces": 0,
            "charger_amps": 80, "connection": "receptacle", "run_ft": 400, "trench_ft": 300,
            "location": "detached_garage",
            "home": {"square_feet": 3100, "range_va": 12000, "dryer_va": 5000, "water_heater_va": 4500,
                     "cooling_va": 7200, "hot_tub_or_pool_va": 1800},
        },
        "las_vegas_general_sample_mode": {
            **SAMPLE, "city": "Las Vegas", "state": "NV", "sample_mode": True,
            "location": "exterior_wall", "charger_amps": 32, "run_ft": 40, "trench_ft": 0,
            "service_amps": 200, "open_breaker_spaces": 4, "home": plain_home,
            "plan": {
                "scale_ft_per_in": 30, "panel": [400, 500], "charger": [600, 500], "lot": SQUARE_LOT,
                "parcel_number": "138-31-614-010",
            },
        },
        "exterior_solar_model": {
            **SAMPLE, "jurisdiction_key": "oro-valley-az", "location": "exterior_wall",
            "charger_amps": 64, "connection": "hardwired", "has_solar": True,
            "charger_model": "Tesla Wall Connector", "run_ft": 45, "trench_ft": 0, "service_amps": 200,
            "open_breaker_spaces": 4,
            "home": {"square_feet": 2400, "range_va": 12000, "cooling_va": 7200},
        },
    }


def page_text(pdf: bytes) -> list[str]:
    document = pypdfium2.PdfDocument(pdf)
    try:
        return [page.get_textpage().get_text_bounded() for page in document]
    finally:
        document.close()


def snapshot(client: TestClient, payload: dict) -> dict:
    packet = client.post("/api/ev/packet", json=payload)
    assert packet.status_code == 200, packet.text
    body = packet.json()
    pdf = base64.b64decode(body["pdf"])
    documents = client.post("/api/ev/documents", json=payload)
    assert documents.status_code == 200, documents.text
    from zipfile import ZipFile

    return {
        "response": {key: value for key, value in body.items() if key not in {"pages", "pdf"}},
        "page_count": len(body["pages"]),
        "page_text": page_text(pdf),
        "zip_names": ZipFile(BytesIO(documents.content)).namelist(),
    }


def main() -> None:
    CASES.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    client = TestClient(app)
    password = os.environ["DEMO_PASSWORD"]
    assert client.post("/api/signin", json={"password": password}).status_code == 200
    for name, payload in cases().items():
        (CASES / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
        (SNAPSHOTS / f"{name}.json").write_text(
            json.dumps(snapshot(client, payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    main()
