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
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from permit_packets.clients import current_client
from permit_packets.core.pdf_base import CONTRACTOR_LOGO
from permit_packets.core.preview import packet_documents_zip, packet_page_images
from permit_packets.core.property_lookup import (
    AddressNotFound,
    AerialUnavailable,
    FoundProperty,
    fetch_aerial,
    find_property,
    property_at,
    suggest_addresses,
)
from permit_packets.core.property_plan import PlanView, zoomed_scale
from permit_packets.core.schemas import (
    AerialRequest,
    LoginRequest,
    LookupRequest,
    PropertyViewRequest,
    SuggestRequest,
)
from permit_packets.job_types import REGISTRY, JobType, PacketResult, get_job_type
from permit_packets.jurisdictions import jurisdiction_json

STATIC = Path(__file__).parent / "permit_packets" / "static"
ASSETS = STATIC / "assets"
SESSION_COOKIE = "permit_demo_session"
SESSION_SECONDS = 12 * 60 * 60

app = FastAPI(title="Permit Packets", docs_url=None, redoc_url=None, openapi_url=None)


def _asset_version() -> str:
    """A short hash of the asset files, so a changed file gets a new URL."""
    digest = hashlib.sha256()
    for path in sorted(ASSETS.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(ASSETS).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


ASSET_VERSION = _asset_version()
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{ASSET_VERSION}}", ASSET_VERSION)
# Only the assets folder is public. The pages themselves stay behind the sign-in.
app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")


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
def demo_page(request: Request) -> Response:
    if not _signed_in(request):
        return _page("signin.html")
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-store"})


@app.get("/dashboard")
def dashboard_page(request: Request) -> Response:
    if not _signed_in(request):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return _page("dashboard.html")


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


@app.post("/api/property/suggest", dependencies=[Depends(require_session)])
def address_suggestions(payload: SuggestRequest) -> dict:
    return {"suggestions": suggest_addresses(payload.text)}


def _known_job_type(key: str) -> str:
    if key not in REGISTRY:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown job type")
    return key


def _property_json(found: FoundProperty, job_type: str) -> dict:
    return {
        "address": found.address,
        "city": found.city,
        "state": found.state,
        "county_fips": found.county_fips,
        "house_number": found.house_number,
        "located_by": found.located_by,
        "address_confirmed": found.address_confirmed,
        "parcel_house_number": found.parcel_house_number,
        "anchor": {"latitude": found.anchor[0], "longitude": found.anchor[1]},
        "jurisdiction": jurisdiction_json(found.jurisdiction, job_type),
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


@app.post("/api/property", dependencies=[Depends(require_session)])
def look_up_property(payload: LookupRequest) -> dict:
    job_type = _known_job_type(payload.job_type)
    try:
        return _property_json(find_property(payload.address), job_type)
    except AddressNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error


@app.post("/api/property/view", dependencies=[Depends(require_session)])
def change_property_view(payload: PropertyViewRequest) -> dict:
    fields = dict(
        address=payload.address, city=payload.city, state=payload.state,
        county_fips=payload.county_fips, house_number=payload.house_number,
    )
    job_type = _known_job_type(payload.job_type)
    view = PlanView(payload.latitude, payload.longitude, payload.scale_ft_per_in)
    if payload.tap:
        return _property_json(
            property_at(**fields, point=view.to_latlon(*payload.tap), located_by="tap"), job_type)
    scale = zoomed_scale(payload.scale_ft_per_in, payload.zoom or 0)
    return _property_json(property_at(
        **fields, point=(payload.anchor_latitude, payload.anchor_longitude), located_by=payload.located_by,
        scale=scale, center=(payload.latitude, payload.longitude),
    ), job_type)


@app.post("/api/property/aerial", dependencies=[Depends(require_session)])
def property_aerial(payload: AerialRequest) -> dict:
    view = PlanView(payload.latitude, payload.longitude, payload.scale_ft_per_in)
    try:
        image, credit = fetch_aerial(view)
    except AerialUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    return {"image": base64.b64encode(image).decode(), "credit": credit}


def _enabled_job_type(slug: str) -> JobType:
    job_type = get_job_type(slug)
    if job_type is None or job_type.key not in current_client().job_types:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That job type isn't available")
    return job_type


def _job_type_json(job_type: JobType) -> dict:
    return {
        "key": job_type.key,
        "slug": job_type.slug,
        "label": job_type.label,
        "short_label": job_type.short_label,
        "blurb": job_type.blurb,
        "icon": job_type.icon,
        "markers": [asdict(marker) for marker in job_type.markers],
        "route_between": list(job_type.route_between) if job_type.route_between else None,
        "uses_home_loads": job_type.uses_home_loads,
        "documents": [asdict(document) for document in job_type.documents],
        "feature_page": job_type.feature_page,
    }


@app.get("/api/job-types", dependencies=[Depends(require_session)])
def job_types() -> dict:
    return {"job_types": [_job_type_json(REGISTRY[key]) for key in current_client().job_types]}


MAX_LOGO_BASE64 = 700_000


def _contractor_logo(payload: dict[str, Any]) -> bytes | None:
    """The optional contractor logo: a PNG or JPEG, base64, shown on the cover and page headers."""
    encoded = payload.pop("contractor_logo_base64", None)
    if not encoded:
        return None
    if not isinstance(encoded, str) or len(encoded) > MAX_LOGO_BASE64:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The logo must be a PNG or JPEG under 500 KB")
    try:
        logo = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The logo is not valid base64") from error
    if not (logo.startswith(b"\x89PNG") or logo.startswith(b"\xff\xd8")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The logo must be a PNG or JPEG")
    return logo


def _build(slug: str, payload: dict[str, Any]) -> tuple[JobType, PacketResult]:
    job_type = _enabled_job_type(slug)
    logo = _contractor_logo(payload)
    try:
        request = job_type.request_model.model_validate(payload)
    except ValidationError as error:
        raise RequestValidationError(error.errors(include_url=False)) from error
    token = CONTRACTOR_LOGO.set(logo)
    try:
        return job_type, job_type.build_response(request)
    finally:
        CONTRACTOR_LOGO.reset(token)


@app.post("/api/jobs/{slug}/packet", dependencies=[Depends(require_session)])
def build_packet(slug: str, payload: dict[str, Any] = Body(...)) -> dict:
    _, result = _build(slug, payload)
    return {
        **result.body,
        "pages": [base64.b64encode(page).decode() for page in packet_page_images(result.pdf)],
        "pdf": base64.b64encode(result.pdf).decode(),
    }


@app.post("/api/jobs/{slug}/documents", dependencies=[Depends(require_session)])
def packet_documents(slug: str, payload: dict[str, Any] = Body(...)) -> Response:
    job_type, result = _build(slug, payload)
    stems = tuple(document.file_stem for document in job_type.documents)
    return Response(
        content=packet_documents_zip(result.pdf, stems),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{job_type.zip_name}"',
            "Cache-Control": "private, no-store",
        },
    )
