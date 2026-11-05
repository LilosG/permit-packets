"""From a typed address to a property: city, building outlines, lot lines, aerial.

Sources were chosen so the result can go in a printed permit packet:
- US Census geocoder and FEMA/ORNL USA Structures are free public data.
- USGS National Map imagery is public domain.
- Lot lines come from county GIS, where the county is set up in COUNTY_PARCELS.
- Mapbox satellite is used instead of USGS when MAPBOX_TOKEN is set.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from io import BytesIO

import httpx
from PIL import Image, ImageFilter

from permit_packets.jurisdictions import Jurisdiction, jurisdiction_for
from permit_packets.property_plan import (
    PLAN_UNITS,
    Point,
    PlanView,
    centroid,
    ground_distance_ft,
    plan_scale,
)

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
STRUCTURES_URL = (
    "https://services2.arcgis.com/FiaPA4ga0iQKduv3/ArcGIS/rest/services/USA_Structures_View/FeatureServer/0/query"
)
USGS_IMAGE_URL = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage"
MAPBOX_IMAGE_URL = "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom:.2f},0,0/{px}x{px}@2x"

# County GIS layers with lot lines, by county FIPS. Only the parcel number is read.
COUNTY_PARCELS = {
    "04019": ("https://gisdata.pima.gov/arcgis1/rest/services/GISOpenData/LandRecords/MapServer/12/query",
              "PARCEL", "Lot lines: Pima County GIS"),
    "06073": ("https://gis-public.sandiegocounty.gov/arcgis/rest/services/DPW/LEAMS_Reference/MapServer/16/query",
              "APN", "Lot lines: San Diego County GIS"),
}

BUILDING_SEARCH_M = 90
STRUCTURES_CREDIT = "Building outlines: FEMA/ORNL USA Structures"
USGS_CREDIT = "Map services and data available from U.S. Geological Survey, National Geospatial Program."
MAPBOX_CREDIT = "Imagery © Mapbox © OpenStreetMap © Maxar"
LOOKUP_TIMEOUT = httpx.Timeout(14, connect=6)
AERIAL_TIMEOUT = httpx.Timeout(40, connect=6)
AERIAL_PIXELS = 1400
JPEG_QUALITY = 78
DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
LatLon = tuple[float, float]


class AddressNotFound(Exception):
    pass


class AerialUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Match:
    address: str
    latitude: float
    longitude: float
    city: str
    state: str
    county_fips: str


@dataclass(frozen=True)
class FoundProperty:
    address: str
    city: str
    state: str
    jurisdiction: Jurisdiction
    view: PlanView
    buildings: list[list[Point]]
    primary_building: int | None
    lot: list[Point]
    parcel_number: str
    credits: list[str]


def tidy_address(matched: str) -> str:
    """The Census writes addresses in capitals: 12 N OAK ST, TUCSON, AZ, 85701."""
    def word(match: re.Match) -> str:
        text = match.group(0)
        return text if text in DIRECTIONS else text.capitalize()

    parts = [part.strip() for part in matched.split(",")]
    if len(parts) < 4:
        return matched
    street, city, state, zip_code = parts[0], parts[1], parts[-2], parts[-1]
    return f"{re.sub(r'\b[0-9]*[A-Z]+\b', word, street)}, {city.title()}, {state} {zip_code}"


def geocode(client: httpx.Client, address: str) -> Match:
    try:
        response = client.get(CENSUS_URL, timeout=LOOKUP_TIMEOUT, params={
            "address": address, "benchmark": "Public_AR_Current", "vintage": "Current_Current",
            "format": "json", "layers": "all",
        })
        response.raise_for_status()
        matches = response.json()["result"]["addressMatches"]
    except (httpx.HTTPError, KeyError, ValueError) as error:
        raise AddressNotFound("The address service didn't respond. Try again.") from error
    if not matches:
        raise AddressNotFound(
            "That address wasn't found. Check the street, city and state, or use the sample layout."
        )
    match = matches[0]
    geographies = match["geographies"]
    place = next(iter(geographies.get("Incorporated Places") or []), {})
    county = next(iter(geographies.get("Counties") or []), {})
    city = re.sub(r"\s+(city|town|village|CDP|borough)$", "", place.get("NAME", ""))
    parts = match["matchedAddress"].split(",")
    return Match(
        address=tidy_address(match["matchedAddress"]),
        latitude=match["coordinates"]["y"],
        longitude=match["coordinates"]["x"],
        city=city or county.get("NAME", ""),
        state=parts[-2].strip() if len(parts) >= 3 else "",
        county_fips=county.get("GEOID", ""),
    )


def _rings(feature: dict) -> list[LatLon]:
    ring = feature.get("geometry", {}).get("rings", [[]])[0]
    return [(lat, lon) for lon, lat in ring[:-1]]


def _arcgis_features(client: httpx.Client, url: str, params: dict) -> list[dict]:
    try:
        response = client.get(url, timeout=LOOKUP_TIMEOUT, params={
            "geometryType": "esriGeometryPoint", "inSR": 4326, "outSR": 4326, "f": "json",
            "returnGeometry": "true", "spatialRel": "esriSpatialRelIntersects", **params,
        })
        response.raise_for_status()
        return response.json().get("features", [])
    except (httpx.HTTPError, ValueError):
        return []


def nearby_buildings(client: httpx.Client, match: Match) -> list[dict]:
    return _arcgis_features(client, STRUCTURES_URL, {
        "geometry": f"{match.longitude},{match.latitude}", "distance": BUILDING_SEARCH_M,
        "units": "esriSRUnit_Meter", "outFields": "PROP_ADDR,SQFEET",
    })


def pick_building(features: list[dict], match: Match) -> dict | None:
    """The building at this address: its house number, else the closest to the point."""
    if not features:
        return None
    number = match.address.split(" ", 1)[0]
    same_number = [
        feature for feature in features
        if (feature["attributes"].get("PROP_ADDR") or "").split(" ", 1)[0] == number
    ]

    def distance(feature: dict) -> float:
        return ground_distance_ft((match.latitude, match.longitude), _center(feature))

    return min(same_number or features, key=distance)


def _center(feature: dict) -> LatLon:
    return centroid(_rings(feature))


def parcel_at(client: httpx.Client, county_fips: str, point: LatLon) -> tuple[list[LatLon], str]:
    county = COUNTY_PARCELS.get(county_fips)
    if not county:
        return [], ""
    url, number_field, _ = county
    features = _arcgis_features(client, url, {
        "geometry": f"{point[1]},{point[0]}", "outFields": number_field,
    })
    if not features:
        return [], ""
    feature = features[0]
    return _rings(feature), str(feature["attributes"].get(number_field) or "").strip()


def _extent_ft(points: list[LatLon]) -> tuple[float, LatLon]:
    south, north = min(p[0] for p in points), max(p[0] for p in points)
    west, east = min(p[1] for p in points), max(p[1] for p in points)
    tall = ground_distance_ft((south, west), (north, west))
    wide = ground_distance_ft((south, west), (south, east))
    return max(tall, wide), ((south + north) / 2, (west + east) / 2)


def find_property(address: str, client: httpx.Client | None = None) -> FoundProperty:
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        match = geocode(client, address)
        features = nearby_buildings(client, match)
        primary = pick_building(features, match)
        anchor = _center(primary) if primary else (match.latitude, match.longitude)
        lot, parcel_number = parcel_at(client, match.county_fips, anchor)
    finally:
        if owns_client:
            client.close()

    frame = lot or (_rings(primary) if primary else [])
    extent, center = _extent_ft(frame) if frame else (0, anchor)
    if not lot:
        extent = max(extent, 150)
    view = PlanView(center[0], center[1], plan_scale(extent))

    plan_lot = [view.to_plan(lat, lon) for lat, lon in lot]
    buildings: list[list[Point]] = []
    primary_index = None
    for feature in features:
        outline = [view.to_plan(lat, lon) for lat, lon in _rings(feature)]
        visible = all(0 <= value <= PLAN_UNITS for value in centroid(outline))
        if not visible:
            continue
        if feature is primary:
            primary_index = len(buildings)
        buildings.append(outline)

    credits = [STRUCTURES_CREDIT] if features else []
    if lot:
        credits.append(COUNTY_PARCELS[match.county_fips][2])
    return FoundProperty(
        address=match.address, city=match.city, state=match.state,
        jurisdiction=jurisdiction_for(match.city, match.state),
        view=view, buildings=buildings, primary_building=primary_index,
        lot=plan_lot, parcel_number=parcel_number, credits=credits,
    )


def _finish(image_bytes: bytes) -> bytes:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    if image.width != AERIAL_PIXELS:
        image = image.resize((AERIAL_PIXELS, AERIAL_PIXELS), Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def _mapbox_aerial(client: httpx.Client, view: PlanView, token: str) -> bytes:
    pixels = 1000
    meters_per_pixel = view.size_ft / 3.28084 / pixels
    zoom = math.log2(78271.517 * math.cos(math.radians(view.latitude)) / meters_per_pixel)
    response = client.get(
        MAPBOX_IMAGE_URL.format(lon=view.longitude, lat=view.latitude, zoom=zoom, px=pixels),
        params={"access_token": token, "attribution": "false", "logo": "false"},
        timeout=AERIAL_TIMEOUT,
    )
    response.raise_for_status()
    return response.content


def _usgs_aerial(client: httpx.Client, view: PlanView) -> bytes:
    west, south, east, north = view.bbox()
    response = client.get(USGS_IMAGE_URL, timeout=AERIAL_TIMEOUT, params={
        "bbox": f"{west},{south},{east},{north}", "bboxSR": 102100, "imageSR": 102100,
        "size": "1000,1000", "format": "jpg", "f": "image",
        "interpolation": "RSP_BilinearInterpolation",
    })
    response.raise_for_status()
    if not response.headers.get("content-type", "").startswith("image/"):
        raise httpx.HTTPError("no image returned")
    return response.content


def fetch_aerial(view: PlanView, client: httpx.Client | None = None) -> tuple[bytes, str]:
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    token = os.environ.get("MAPBOX_TOKEN")
    try:
        if token:
            try:
                return _finish(_mapbox_aerial(client, view, token)), MAPBOX_CREDIT
            except (httpx.HTTPError, OSError):
                pass
        for _ in range(2):
            try:
                return _finish(_usgs_aerial(client, view)), USGS_CREDIT
            except (httpx.HTTPError, OSError):
                continue
    finally:
        if owns_client:
            client.close()
    raise AerialUnavailable("The aerial photo didn't load. The plan still works from the building and lot data.")

