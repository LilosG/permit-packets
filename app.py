"""The private demo: a job form, the checks and the PDF download."""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from permit_packets.ev_charger import EvJob, EvPacket, build_ev_packet
from permit_packets.ev_packet_pdf import render_ev_packet_pdf
from permit_packets.load_calculation import HomeLoads
from permit_packets.preview import packet_page_images
from permit_packets.schemas import EvJobRequest

STATIC = Path(__file__).parent / "permit_packets" / "static"
USERNAME = "mike"
basic = HTTPBasic()


def require_login(credentials: HTTPBasicCredentials = Depends(basic)) -> None:
    password = os.environ.get("DEMO_PASSWORD")
    if not password:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "DEMO_PASSWORD is not set")
    valid = secrets.compare_digest(credentials.username.encode(), USERNAME.encode())
    valid &= secrets.compare_digest(credentials.password.encode(), password.encode())
    if not valid:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect login",
            headers={"WWW-Authenticate": "Basic"},
        )


app = FastAPI(
    title="Permit Packets",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    dependencies=[Depends(require_login)],
)


def _packet(payload: EvJobRequest) -> EvPacket:
    fields = payload.model_dump(exclude={"home"})
    return build_ev_packet(EvJob(home=HomeLoads(**payload.home.model_dump()), **fields))


@app.get("/")
def demo_page() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.post("/api/ev/check")
def check_ev_job(payload: EvJobRequest) -> dict:
    packet = _packet(payload)
    circuit = packet.circuit
    return {
        "ready": packet.ready,
        "computed_amps": round(packet.load.computed_amps, 1),
        "total_va": round(packet.load.total_va),
        "spare_amps": round(packet.load.spare_amps, 1),
        "breaker": circuit.breaker,
        "wire": f"#{circuit.wire.size} AWG Cu",
        "ground": f"#{circuit.ground} AWG Cu",
        "voltage_drop_percent": round(circuit.voltage_drop_percent, 1),
        "underground_conduit": packet.underground_conduit,
        "interior_conduit": packet.interior_conduit,
        "disconnect_amps": packet.disconnect_amps,
        "checks": [
            {"name": check.name, "result": check.result, "passed": check.passed}
            for check in packet.checks
        ],
        "flags": packet.flags,
    }


@app.post("/api/ev/preview")
def preview_ev_packet(payload: EvJobRequest) -> dict:
    pages = packet_page_images(render_ev_packet_pdf(_packet(payload)))
    return {"pages": [base64.b64encode(page).decode() for page in pages]}


@app.post("/api/ev/pdf")
def ev_packet_pdf(payload: EvJobRequest) -> Response:
    return Response(
        content=render_ev_packet_pdf(_packet(payload)),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="ev-permit-packet-demo.pdf"',
            "Cache-Control": "private, no-store",
        },
    )
