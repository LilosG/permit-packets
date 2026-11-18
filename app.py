"""The private demo: address to property, job to packet, packet to submission."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
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

from permit_packets.clients import CLIENTS, DEFAULT_CLIENT, Client, validate
from permit_packets.core.cad import collect_cad, dxf_files, zip_files
from permit_packets.core.pdf_base import COMPANY_NAME, CONTRACTOR_LOGO
from permit_packets.core.preview import packet_documents_zip, packet_page_images
from permit_packets.jurisdictions import KNOWN, jurisdiction_by_key
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
KNOWN_BY_KEY = {j.key: j for j in KNOWN.values()}
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


def _client_passwords() -> dict[str, str]:
    """Each client's password: CLIENT_PASSWORDS ({"client_key": "password"}) plus DEMO_PASSWORD for the demo."""
    passwords: dict[str, str] = {}
    raw = os.environ.get("CLIENT_PASSWORDS")
    if raw:
        try:
            loaded = json.loads(raw)
            if not isinstance(loaded, dict) or not all(isinstance(v, str) and v for v in loaded.values()):
                raise ValueError
        except ValueError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CLIENT_PASSWORDS is not valid JSON") from error
        passwords.update({key: value for key, value in loaded.items() if key in CLIENTS})
    if os.environ.get("DEMO_PASSWORD"):
        passwords.setdefault(DEFAULT_CLIENT, os.environ["DEMO_PASSWORD"])
    if not passwords:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No passwords are set")
    return passwords


def _signature(expires: str, client_key: str, password: str) -> str:
    return hmac.new(password.encode(), f"session:{expires}:{client_key}".encode(), hashlib.sha256).hexdigest()


def session_client(request: Request) -> Client | None:
    """The client this session signed in as, or None when not signed in."""
    expires, _, rest = request.cookies.get(SESSION_COOKIE, "").partition(".")
    client_key, _, signature = rest.partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return None
    password = _client_passwords().get(client_key)
    if password is None or client_key not in CLIENTS:
        return None
    if not secrets.compare_digest(signature, _signature(expires, client_key, password)):
        return None
    return validate(CLIENTS[client_key])


def require_session(request: Request) -> Client:
    client = session_client(request)
    if client is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
    return client


def _allowed_city(client: Client, jurisdiction) -> None:
    if not client.allows(jurisdiction.key):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"{jurisdiction.label} isn't one of the cities set up for {client.company_name}")


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC / name, headers={"Cache-Control": "no-store"})


@app.get("/")
def demo_page(request: Request) -> Response:
    if session_client(request) is None:
        return _page("signin.html")
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-store"})


@app.get("/dashboard")
def dashboard_page(request: Request) -> Response:
    if session_client(request) is None:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return _page("dashboard.html")


@app.post("/api/signin")
def sign_in(payload: LoginRequest, request: Request, response: Response) -> dict:
    entered = payload.password.encode()
    matched = None
    for client_key, password in _client_passwords().items():  # no early exit: every password is compared
        if secrets.compare_digest(entered, password.encode()) and matched is None:
            matched = client_key
    if matched is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That password isn't right")
    expires = str(int(time.time()) + SESSION_SECONDS)
    response.set_cookie(
        SESSION_COOKIE, f"{expires}.{matched}.{_signature(expires, matched, _client_passwords()[matched])}",
        max_age=SESSION_SECONDS, httponly=True, samesite="lax",
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
    )
    return {"ok": True}


@app.post("/api/signout")
def sign_out(request: Request) -> Response:
    """End this session and go back to the sign-in page. A plain form post, so it works without scripts."""
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, samesite="lax",
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _sample_address(jurisdiction_key: str) -> str:
    city = KNOWN_BY_KEY[jurisdiction_key]
    return f"123 Sample St, {city.name}, {city.state}"


@app.get("/api/client")
def client_info(client: Client = Depends(require_session)) -> dict:
    cities = [KNOWN_BY_KEY[key] for key in client.jurisdiction_keys if key in KNOWN_BY_KEY]
    return {
        "key": client.key,
        "company_name": client.company_name,
        "website": client.website,
        "logo": f"/assets/logos/{client.logo}" if client.logo else "",
        "demo": client.is_demo,
        "cad": client.cad,
        "sheet_size": client.sheet_size or "",
        "cities": [
            {"key": c.key, "name": c.name, "state": c.state, "label": c.label, "sample_address": _sample_address(c.key)}
            for c in cities
        ],
    }


@app.post("/api/property/suggest", dependencies=[Depends(require_session)])
def address_suggestions(payload: SuggestRequest, client: Client = Depends(require_session)) -> dict:
    # Only the signed-in client's cities; the demo login lists all of them.
    cities = [KNOWN_BY_KEY[key] for key in client.jurisdiction_keys if key in KNOWN_BY_KEY]
    return {"suggestions": suggest_addresses(payload.text, areas=cities)}


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
def look_up_property(payload: LookupRequest, client: Client = Depends(require_session)) -> dict:
    job_type = _known_job_type(payload.job_type)
    try:
        found = find_property(payload.address)
    except AddressNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    _allowed_city(client, found.jurisdiction)
    return _property_json(found, job_type)


@app.post("/api/property/view", dependencies=[Depends(require_session)])
def change_property_view(payload: PropertyViewRequest, client: Client = Depends(require_session)) -> dict:
    fields = dict(
        address=payload.address, city=payload.city, state=payload.state,
        county_fips=payload.county_fips, house_number=payload.house_number,
    )
    job_type = _known_job_type(payload.job_type)
    view = PlanView(payload.latitude, payload.longitude, payload.scale_ft_per_in)
    if payload.tap:
        found = property_at(**fields, point=view.to_latlon(*payload.tap), located_by="tap")
    else:
        scale = zoomed_scale(payload.scale_ft_per_in, payload.zoom or 0)
        found = property_at(
            **fields, point=(payload.anchor_latitude, payload.anchor_longitude), located_by=payload.located_by,
            scale=scale, center=(payload.latitude, payload.longitude),
        )
    _allowed_city(client, found.jurisdiction)
    return _property_json(found, job_type)


@app.post("/api/property/aerial", dependencies=[Depends(require_session)])
def property_aerial(payload: AerialRequest) -> dict:
    view = PlanView(payload.latitude, payload.longitude, payload.scale_ft_per_in)
    try:
        image, credit = fetch_aerial(view)
    except AerialUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    return {"image": base64.b64encode(image).decode(), "credit": credit}


def _enabled_job_type(slug: str, client: Client) -> JobType:
    job_type = get_job_type(slug)
    if job_type is None or job_type.key not in client.job_types:
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
        "occupancy": job_type.occupancy,
    }


@app.get("/api/job-types", dependencies=[Depends(require_session)])
def job_types(client: Client = Depends(require_session)) -> dict:
    return {"job_types": [_job_type_json(REGISTRY[key]) for key in client.job_types]}


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


def _build(slug: str, payload: dict[str, Any], client: Client) -> tuple[JobType, PacketResult]:
    job_type = _enabled_job_type(slug, client)
    city = jurisdiction_by_key(payload.get("jurisdiction_key"), payload.get("city"), payload.get("state"))
    _allowed_city(client, city)
    logo = _contractor_logo(payload)
    if not client.is_demo:  # a client's packets carry their own logo and the city's rules, not a link's
        logo = client.logo_bytes()
        if client.sheet_size and not payload.get("sheet_size"):
            payload["sheet_size"] = client.sheet_size  # the request's own choice still wins
    try:
        request = job_type.request_model.model_validate(payload)
    except ValidationError as error:
        raise RequestValidationError(error.errors(include_url=False)) from error
    tokens = (
        (CONTRACTOR_LOGO, CONTRACTOR_LOGO.set(logo)),
        (COMPANY_NAME, COMPANY_NAME.set(client.company_name)),
    )
    try:
        return job_type, job_type.build_response(request)
    finally:
        for var, token in tokens:
            var.reset(token)


# The review screen and the PDF come from two requests. Vercel caps a function response at 4.5 MB, and the page
# images plus the base64 PDF (data sheets included) reached about 4.1 MB in one response. The browser asks for
# both at once; each rebuilds the packet from the same job, so they show the same packet.
@app.post("/api/jobs/{slug}/packet", dependencies=[Depends(require_session)])
def build_packet(slug: str, payload: dict[str, Any] = Body(...), client: Client = Depends(require_session)) -> dict:
    _, result = _build(slug, payload, client)
    return {
        **result.body,
        "pages": [base64.b64encode(page).decode() for page in packet_page_images(result.pdf)],
    }


@app.post("/api/jobs/{slug}/pdf", dependencies=[Depends(require_session)])
def packet_pdf(slug: str, payload: dict[str, Any] = Body(...), client: Client = Depends(require_session)) -> Response:
    """The packet as one PDF file, sent as bytes rather than base64 (a third smaller)."""
    _, result = _build(slug, payload, client)
    return Response(
        content=result.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "Cache-Control": "private, no-store"},
    )


@app.post("/api/jobs/{slug}/cad", dependencies=[Depends(require_session)])
def packet_cad(slug: str, payload: dict[str, Any] = Body(...), client: Client = Depends(require_session)) -> Response:
    """The packet's drawings as DXF files in a ZIP, built only when asked for and only for clients who have it."""
    if not client.cad:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CAD files aren't set up for this account")
    with collect_cad() as cad:
        job_type, _ = _build(slug, payload, client)
    files = dxf_files(cad, f"{job_type.slug}-permit")
    if not files:
        raise HTTPException(status.HTTP_409_CONFLICT, "This packet has no drawings to export")
    return Response(
        content=zip_files(files),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{job_type.slug}-permit-cad.zip"',
            "Cache-Control": "private, no-store",
        },
    )


@app.post("/api/jobs/{slug}/documents", dependencies=[Depends(require_session)])
def packet_documents(slug: str, payload: dict[str, Any] = Body(...), client: Client = Depends(require_session)) -> Response:
    _enabled_job_type(slug, client)
    city = jurisdiction_by_key(payload.get("jurisdiction_key"), payload.get("city"), payload.get("state"))
    _allowed_city(client, city)
    if client.single_pdf_only_for(city):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{city.name} takes one combined PDF and does not accept plan sheets as separate files",
        )
    job_type, result = _build(slug, payload, client)
    zip_name = job_type.zip_name
    stems = tuple(document.file_stem for document in job_type.documents)
    return Response(
        content=packet_documents_zip(result.pdf, stems),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_name}"',
            "Cache-Control": "private, no-store",
        },
    )
