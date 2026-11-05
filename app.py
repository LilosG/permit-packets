"""The private demo: address to property, job to packet, packet to submission."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from permit_packets.ev_charger import EvJob, EvPacket, build_ev_packet
from permit_packets.ev_packet_pdf import application_fields, render_ev_packet_pdf, scope_of_work
from permit_packets.jurisdictions import Jurisdiction, jurisdiction_by_key
from permit_packets.load_calculation import HomeLoads
from permit_packets.preview import packet_documents_zip, packet_page_images
from permit_packets.property_lookup import AddressNotFound, AerialUnavailable, fetch_aerial, find_property
from permit_packets.property_plan import PlanView, PropertyPlan
from permit_packets.schemas import AerialRequest, EvJobRequest, LoginRequest, LookupRequest

STATIC = Path(__file__).parent / "permit_packets" / "static"
SESSION_COOKIE = "permit_demo_session"
SESSION_SECONDS = 12 * 60 * 60

app = FastAPI(title="Permit Packets", docs_url=None, redoc_url=None, openapi_url=None)


def _demo_password() -> str:
    password = os.environ.get("DEMO_PASSWORD")
    if not password:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "DEMO_PASSWORD is not set")
    return password


def _signature(expires: str, password: str) -> str:
    return hmac.new(password.encode(), f"session:{expires}".encode(), hashlib.sha256).hexdigest()


def _signed_in(request: Request) -> bool:
    expires, _, signature = request.cookies.get(SESSION_COOKIE, "").partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return False
    return secrets.compare_digest(signature, _signature(expires, _demo_password()))


def require_session(request: Request) -> None:
    if not _signed_in(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC / name, headers={"Cache-Control": "no-store"})


@app.get("/")
def demo_page(request: Request) -> FileResponse:
    return _page("index.html" if _signed_in(request) else "signin.html")


@app.post("/api/signin")
def sign_in(payload: LoginRequest, request: Request, response: Response) -> dict:
    password = _demo_password()
    if not secrets.compare_digest(payload.password.encode(), password.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That password isn't right")
    expires = str(int(time.time()) + SESSION_SECONDS)
    response.set_cookie(
        SESSION_COOKIE, f"{expires}.{_signature(expires, password)}", max_age=SESSION_SECONDS,
        httponly=True, samesite="lax",
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
    )
    return {"ok": True}


def _jurisdiction_json(jurisdiction: Jurisdiction) -> dict:
    return {
        **{key: value for key, value in asdict(jurisdiction).items() if key not in {"checklist", "notes"}},
        "label": jurisdiction.label,
        "checklist": [requirement.item for requirement in jurisdiction.checklist],
    }


@app.post("/api/property", dependencies=[Depends(require_session)])
def look_up_property(payload: LookupRequest) -> dict:
    try:
        found = find_property(payload.address)
    except AddressNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    return {
        "address": found.address,
        "city": found.city,
        "state": found.state,
        "jurisdiction": _jurisdiction_json(found.jurisdiction),
        "view": {
            "latitude": found.view.latitude,
            "longitude": found.view.longitude,
            "scale_ft_per_in": found.view.scale_ft_per_in,
            "feet_per_unit": found.view.feet_per_unit,
        },
        "buildings": found.buildings,
        "primary_building": found.primary_building,
        "lot": found.lot,
        "parcel_number": found.parcel_number,
        "credits": found.credits,
    }


@app.post("/api/property/aerial", dependencies=[Depends(require_session)])
def property_aerial(payload: AerialRequest) -> dict:
    view = PlanView(payload.latitude, payload.longitude, payload.scale_ft_per_in)
    try:
        image, credit = fetch_aerial(view)
    except AerialUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    return {"image": base64.b64encode(image).decode(), "credit": credit}


def _plan(payload: EvJobRequest) -> PropertyPlan | None:
    plan = payload.plan
    if plan is None:
        return None
    try:
        aerial = plan.aerial_bytes()
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return PropertyPlan(
        scale_ft_per_in=plan.scale_ft_per_in, panel=plan.panel, charger=plan.charger, route=plan.route,
        buildings=plan.buildings, primary_building=plan.primary_building, lot=plan.lot,
        parcel_number=plan.parcel_number, aerial_jpeg=aerial, credits=plan.credits,
    )


def _packet(payload: EvJobRequest) -> EvPacket:
    fields = payload.model_dump(exclude={"home", "plan", "city", "state", "jurisdiction_key"})
    return build_ev_packet(EvJob(
        home=HomeLoads(**payload.home.model_dump()),
        jurisdiction=jurisdiction_by_key(payload.jurisdiction_key, payload.city, payload.state),
        plan=_plan(payload),
        **fields,
    ))


@app.post("/api/ev/packet", dependencies=[Depends(require_session)])
def build_packet(payload: EvJobRequest) -> dict:
    packet = _packet(payload)
    pdf = render_ev_packet_pdf(packet)
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
        "jurisdiction": _jurisdiction_json(packet.job.jurisdiction),
        "fields": [
            *({"label": label, "value": value} for label, value in application_fields(packet)),
            {"label": "Scope of work", "value": scope_of_work(packet)},
        ],
        "pages": [base64.b64encode(page).decode() for page in packet_page_images(pdf)],
        "pdf": base64.b64encode(pdf).decode(),
    }


@app.post("/api/ev/documents", dependencies=[Depends(require_session)])
def packet_documents(payload: EvJobRequest) -> Response:
    return Response(
        content=packet_documents_zip(render_ev_packet_pdf(_packet(payload))),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="ev-permit-documents-demo.zip"',
            "Cache-Control": "private, no-store",
        },
    )
