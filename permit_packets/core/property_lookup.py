"""From a typed address to a property: city, building outlines, lot lines, aerial.

Sources were chosen so the result can go in a printed permit packet:
- US Census geocoder and FEMA/ORNL USA Structures are free public data.
- USGS National Map imagery is public domain.
- Lot lines come from county GIS, where the county is set up in COUNTIES.
- Mapbox satellite is used instead of USGS when MAPBOX_TOKEN is set.
- Photon, built on OpenStreetMap, suggests addresses as the tech types. The chosen
  address still goes through the Census geocoder, so a suggestion is never trusted
  on its own.
"""
from __future__ import annotations

import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO

import httpx
from PIL import Image, ImageFilter

from permit_packets.jurisdictions import Jurisdiction, jurisdiction_for
from permit_packets.core.property_plan import (
    FEET_PER_METER,
    PLAN_UNITS,
    PLAN_WIDTH_IN,
    Point,
    PlanView,
    centroid,
    clip_to,
    contains,
    ground_distance_ft,
    plan_scale,
)

PHOTON_URL = "https://photon.komoot.io/api/"
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
STRUCTURES_URL = (
    "https://services2.arcgis.com/FiaPA4ga0iQKduv3/ArcGIS/rest/services/USA_Structures_View/FeatureServer/0/query"
)
USGS_IMAGE_URL = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage"
# Local government orthophotos, much sharper than NAIP. Used first inside their coverage box.
# (west, south, east, north) in degrees, export URL, credit.
LOCAL_AERIALS = (
    (
        (-87.06, 35.96, -86.51, 36.41),
        "https://maps.nashville.gov/arcgis/rest/services/Imagery/2026Imagery_WGS84/MapServer/export",
        "Aerial: Metro Nashville-Davidson County, 2026 imagery",
    ),
    (
        (-84.33, 33.84, -75.46, 36.59),
        "https://services.nconemap.gov/secure/rest/services/Imagery/Orthoimagery_Latest/ImageServer/exportImage",
        "Aerial: NC OneMap, NC Orthoimagery Program (latest)",
    ),
)
MAPBOX_IMAGE_URL = "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom:.2f},0,0/{px}x{px}@2x"



def _quoted(text: str) -> str:
    return text.replace("'", "''")


@dataclass(frozen=True)
class County:
    """A county GIS layer. Only parcel and address fields are read, never owner fields."""
    url: str
    parcel_field: str
    credit: str
    address_fields: str
    address_where: Callable[[str, str], str]
    house_number: Callable[[dict], str]
    # Narrows an address match by street type, where a county has e.g. both 27th Ave and 27th St.
    type_where: Callable[[str], str] | None = None


COUNTIES = {
    "32003": County(
        "https://mapdata.lasvegasnevada.gov/clvgis/rest/services/AdministrativeBoundaries/Parcels/MapServer/0/query",
        "PARCEL", "Lot lines: Clark County Assessor, City of Las Vegas GIS", "STRNO",
        lambda number, street: f"STRNO={int(number)} AND STRNAME='{_quoted(street)}'",
        lambda attributes: str(attributes.get("STRNO") or ""),
    ),
    "04019": County(
        "https://gisdata.pima.gov/arcgis1/rest/services/GISOpenData/LandRecords/MapServer/12/query",
        "PARCEL", "Lot lines: Pima County GIS", "ADDRESS_OL",
        lambda number, street: f"ADDRESS_OL LIKE '{_quoted(number)} %{_quoted(street)}%'",
        lambda attributes: str(attributes.get("ADDRESS_OL") or "").split(" ", 1)[0],
    ),
    "47037": County(
        "https://maps.nashville.gov/arcgis/rest/services/Cadastral/Parcels/MapServer/0/query",
        "APN", "Lot lines: Metro Nashville Planning, Parcels", "PropHouse,PropAddr",
        lambda number, street: f"PropHouse='{_quoted(number)}' AND PropAddr LIKE '{_quoted(number)} %{_quoted(street)}%'",
        lambda attributes: str(attributes.get("PropHouse") or ""),
    ),
    "06075": County(
        "https://sfplanninggis.org/arcgiswa/rest/services/PlanningData/MapServer/23/query",
        "blklot", "Lot lines: San Francisco Planning, Parcels", "from_st,street",
        lambda number, street: f"street='{_quoted(street)}' AND from_st='{_quoted(number)}'",
        lambda attributes: str(attributes.get("from_st") or "").lstrip("0"),
        lambda street_type: f"st_type='{_quoted(street_type.upper())}'",
    ),
    "37119": County(
        "https://meckgis.mecklenburgcountync.gov/server/rest/services/TaxParcel_camadata/FeatureServer/0/query",
        "pid", "Lot lines: Mecklenburg County GIS", "streetnumber,streetname",
        lambda number, street: f"streetnumber='{_quoted(number)}' AND streetname LIKE '{_quoted(street)}%'",
        lambda attributes: str(attributes.get("streetnumber") or ""),
        lambda street_type: f"streetname LIKE '% {_quoted(street_type.upper())}'",
    ),
    "06073": County(
        "https://gis-public.sandiegocounty.gov/arcgis/rest/services/DPW/LEAMS_Reference/MapServer/16/query",
        "APN", "Lot lines: San Diego County GIS", "SITUS_ADDRESS",
        lambda number, street: f"SITUS_ADDRESS={int(number)} AND SITUS_STREET='{_quoted(street)}'",
        lambda attributes: str(attributes.get("SITUS_ADDRESS") or ""),
    ),
}

BUILDING_SEARCH_M = 90
# A better location for the address has to agree roughly with the Census street match.
MAX_LOCATION_DISAGREEMENT_FT = 2000
STRUCTURES_CREDIT = "Building outlines: FEMA/ORNL USA Structures"
USGS_CREDIT = "Map services and data available from U.S. Geological Survey, National Geospatial Program."
MAPBOX_CREDIT = "Imagery © Mapbox © OpenStreetMap © Maxar"
LOOKUP_TIMEOUT = httpx.Timeout(14, connect=6)
AERIAL_TIMEOUT = httpx.Timeout(40, connect=6)
AERIAL_PIXELS = 1400
JPEG_QUALITY = 78
USER_AGENT = "LilosGrowth-PermitPackets/1.0"
SUGGEST_TIMEOUT = httpx.Timeout(5, connect=3)
SUGGESTION_LIMIT = 5
STATE_CODES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
    "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
DIRECTION_WORDS = {
    "n": "n", "north": "n", "s": "s", "south": "s", "e": "e", "east": "e", "w": "w", "west": "w",
}
STREET_TYPES = {"st", "street", "ave", "avenue", "dr", "drive", "rd", "road", "ln", "lane", "ct", "court",
                "blvd", "boulevard", "way", "pl", "place", "cir", "circle"}
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
    house_number: str = ""
    street_name: str = ""
    street_type: str = ""  # Census suffixType, e.g. AVE or ST


@dataclass(frozen=True)
class Parcel:
    outline: list[LatLon]
    number: str
    house_number: str


@dataclass(frozen=True)
class FoundProperty:
    address: str
    city: str
    state: str
    county_fips: str
    house_number: str
    jurisdiction: Jurisdiction
    anchor: LatLon
    located_by: str  # county, map, street or tap
    address_confirmed: bool | None
    parcel_house_number: str
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


# Consolidated city-counties come back from the Census as e.g.
# "Nashville-Davidson metropolitan government (balance)". The city is the first name.
CONSOLIDATED_PLACE = re.compile(
    r"^([^-]+)-.*\b(metropolitan government|urban county|unified government|consolidated government)\b.*$",
    re.IGNORECASE,
)


def place_name(census_name: str) -> str:
    """The city a Census incorporated-place name stands for."""
    name = census_name.strip()
    consolidated = CONSOLIDATED_PLACE.match(name)
    if consolidated:
        return consolidated.group(1).strip()
    return re.sub(r"\s+(city|town|village|CDP|borough)$", "", name)


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
            "That exact address wasn't found. Check the street name, and include the city and state."
        )
    match = matches[0]
    geographies = match["geographies"]
    place = next(iter(geographies.get("Incorporated Places") or []), {})
    county = next(iter(geographies.get("Counties") or []), {})
    city = place_name(place.get("NAME", ""))
    parts = match["matchedAddress"].split(",")
    return Match(
        address=tidy_address(match["matchedAddress"]),
        latitude=match["coordinates"]["y"],
        longitude=match["coordinates"]["x"],
        city=city or county.get("NAME", ""),
        state=parts[-2].strip() if len(parts) >= 3 else "",
        county_fips=county.get("GEOID", ""),
        house_number=match["matchedAddress"].split(" ", 1)[0],
        street_name=match.get("addressComponents", {}).get("streetName", ""),
        street_type=match.get("addressComponents", {}).get("suffixType", ""),
    )


def _suggestion(properties: dict, house_number: str) -> str | None:
    """OpenStreetMap lacks many house numbers, so a street match takes the typed number."""
    state = STATE_CODES.get(properties.get("state", ""))
    street = properties.get("street") or (properties.get("name") if properties.get("type") == "street" else None)
    city = properties.get("city") or properties.get("town") or properties.get("district")
    number = properties.get("housenumber") or house_number
    if properties.get("countrycode") != "US" or not (state and street and city and number) or "@" in street:
        return None
    tail = f" {properties['postcode']}" if properties.get("postcode") else ""
    return f"{number} {street}, {city}, {state}{tail}"


def _street_words(text: str) -> tuple[list[str], str | None]:
    """The words that name the street, and any direction typed: 'e naranja dr' is (naranja, e)."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    if words and words[0][0].isdigit():
        words = words[1:]
    direction = next((DIRECTION_WORDS[word] for word in words[:1] if word in DIRECTION_WORDS), None)
    return [word for word in words if word not in DIRECTION_WORDS and word not in STREET_TYPES], direction


def _fits(properties: dict, house_number: str, wanted: list[str], direction: str | None) -> bool:
    street = str(properties.get("street") or properties.get("name") or "").lower().split()
    if house_number and properties.get("housenumber") not in (None, house_number):
        return False
    place = street + str(properties.get("city") or "").lower().split()
    # The first two words name the street. Later ones may be a city with another postal name.
    if not all(any(word.startswith(part) for word in place) for part in wanted[:2]):
        return False
    found = next((DIRECTION_WORDS[word] for word in street[:1] if word in DIRECTION_WORDS), None)
    return not (direction and found and direction != found)


def _photon_search(client: httpx.Client, text: str) -> list[dict]:
    response = client.get(PHOTON_URL, timeout=SUGGEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, params=[
        ("q", text), ("limit", 20), ("lang", "en"), ("layer", "house"), ("layer", "street"),
        ("bbox", "-125,24,-66,50"),
    ])
    response.raise_for_status()
    return response.json().get("features", [])


def suggest_addresses(text: str, client: httpx.Client | None = None) -> list[str]:
    """Best effort: when this fails the tech can still type the whole address."""
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    leading = re.match(r"\s*(\d+[A-Za-z]?)\s", text)
    house_number = leading.group(1) if leading else ""
    wanted, direction = _street_words(text)
    suggestions: list[str] = []
    searches = [text, text[leading.end():]] if leading else [text]
    try:
        for search in searches:
            for feature in _photon_search(client, search):
                properties = feature.get("properties", {})
                suggestion = _suggestion(properties, house_number)
                if suggestion and suggestion not in suggestions and _fits(properties, house_number, wanted, direction):
                    suggestions.append(suggestion)
            if suggestions:
                break
    except (httpx.HTTPError, ValueError):
        pass
    finally:
        if owns_client:
            client.close()
    return suggestions[:SUGGESTION_LIMIT]


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


def buildings_around(client: httpx.Client, point: LatLon, radius_m: float) -> list[dict]:
    return _arcgis_features(client, STRUCTURES_URL, {
        "geometry": f"{point[1]},{point[0]}", "distance": round(radius_m),
        "units": "esriSRUnit_Meter", "outFields": "SQFEET",
    })


def pick_building(features: list[dict], point: LatLon) -> dict | None:
    """The building holding the point, else the closest one."""
    if not features:
        return None
    holding = [feature for feature in features if contains(_rings(feature), point)]
    return min(holding or features, key=lambda feature: ground_distance_ft(point, _center(feature)))


def _center(feature: dict) -> LatLon:
    return centroid(_rings(feature))


def _parcel_fields(county: County) -> str:
    return f"{county.parcel_field},{county.address_fields}"


def _parcel(county: County, feature: dict) -> Parcel:
    attributes = feature["attributes"]
    return Parcel(
        _rings(feature), str(attributes.get(county.parcel_field) or "").strip(), county.house_number(attributes),
    )


def parcel_at(client: httpx.Client, county_fips: str, point: LatLon) -> Parcel | None:
    county = COUNTIES.get(county_fips)
    if not county:
        return None
    features = _arcgis_features(client, county.url, {
        "geometry": f"{point[1]},{point[0]}", "outFields": _parcel_fields(county),
    })
    return _parcel(county, features[0]) if features else None


def parcel_for_address(client: httpx.Client, match: Match) -> Parcel | None:
    county = COUNTIES.get(match.county_fips)
    if not county or not match.house_number.isdigit() or not match.street_name:
        return None
    features = _arcgis_features(client, county.url, {
        "where": county.address_where(match.house_number, match.street_name) + (
            f" AND {county.type_where(match.street_type)}" if county.type_where and match.street_type else ""),
        "outFields": _parcel_fields(county),
    })
    features = [feature for feature in features if _rings(feature)]
    return _parcel(county, features[0]) if len(features) == 1 else None


def map_location(client: httpx.Client, match: Match, address: str) -> LatLon | None:
    """The house's own map point, when OpenStreetMap has this exact number."""
    try:
        response = client.get(PHOTON_URL, timeout=SUGGEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, params={
            "q": address, "limit": 5, "lang": "en", "layer": "house", "bbox": "-125,24,-66,50",
        })
        response.raise_for_status()
        features = response.json().get("features", [])
    except (httpx.HTTPError, ValueError):
        return None
    street = match.street_name.lower()
    for feature in features:
        properties = feature.get("properties", {})
        if properties.get("housenumber") != match.house_number:
            continue
        if not street or street not in str(properties.get("street", "")).lower():
            continue
        longitude, latitude = feature["geometry"]["coordinates"]
        point = (latitude, longitude)
        if ground_distance_ft(point, (match.latitude, match.longitude)) <= MAX_LOCATION_DISAGREEMENT_FT:
            return point
    return None


def _extent_ft(points: list[LatLon]) -> tuple[float, LatLon]:
    south, north = min(p[0] for p in points), max(p[0] for p in points)
    west, east = min(p[1] for p in points), max(p[1] for p in points)
    tall = ground_distance_ft((south, west), (north, west))
    wide = ground_distance_ft((south, west), (south, east))
    return max(tall, wide), ((south + north) / 2, (west + east) / 2)


def assemble_property(
    client: httpx.Client,
    *,
    address: str,
    city: str,
    state: str,
    county_fips: str,
    house_number: str,
    point: LatLon,
    located_by: str,
    parcel: Parcel | None = None,
    scale: int | None = None,
    center: LatLon | None = None,
) -> FoundProperty:
    radius = max(BUILDING_SEARCH_M, (scale or 0) * PLAN_WIDTH_IN / FEET_PER_METER * 0.75)
    features = buildings_around(client, point, radius)
    primary = pick_building(features, point)
    anchor = _center(primary) if primary and located_by == "street" else point
    parcel = parcel or parcel_at(client, county_fips, anchor)
    lot = parcel.outline if parcel else []
    if lot and primary:
        middle = centroid(lot)
        inside = [
            feature for feature in features
            if contains(lot, _center(feature)) or contains(_rings(feature), middle)
        ]
        primary = pick_building(inside, middle) or primary

    frame = lot or (_rings(primary) if primary else [])
    extent, frame_center = _extent_ft(frame) if frame else (0, anchor)
    if not lot:
        extent = max(extent, 150)
    view = PlanView(*(center or frame_center), scale or plan_scale(extent))

    buildings: list[list[Point]] = []
    primary_index = None
    for feature in features:
        outline = [view.to_plan(lat, lon) for lat, lon in _rings(feature)]
        if not all(0 <= value <= PLAN_UNITS for value in centroid(outline)):
            continue
        if feature is primary:
            primary_index = len(buildings)
            if lot:
                outline = clip_to(outline, [view.to_plan(lat, lon) for lat, lon in lot])
        buildings.append(outline)

    credits = [STRUCTURES_CREDIT] if features else []
    if lot:
        credits.append(COUNTIES[county_fips].credit)
    on_record = parcel.house_number if parcel else ""
    return FoundProperty(
        address=address, city=city, state=state, county_fips=county_fips, house_number=house_number,
        jurisdiction=jurisdiction_for(city, state), anchor=anchor, located_by=located_by,
        address_confirmed=(on_record == house_number) if on_record and house_number else None,
        parcel_house_number=on_record, view=view, buildings=buildings, primary_building=primary_index,
        lot=[view.to_plan(lat, lon) for lat, lon in lot],
        parcel_number=parcel.number if parcel else "", credits=credits,
    )


def find_property(address: str, client: httpx.Client | None = None) -> FoundProperty:
    """Locate the house itself. The Census only estimates a position along the street."""
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        match = geocode(client, address)
        parcel = parcel_for_address(client, match)
        map_point = None if parcel else map_location(client, match, match.address)
        if parcel:
            point, located_by = centroid(parcel.outline), "county"
        elif map_point:
            point, located_by = map_point, "map"
        else:
            point, located_by = (match.latitude, match.longitude), "street"
        return assemble_property(
            client, address=match.address, city=match.city, state=match.state,
            county_fips=match.county_fips, house_number=match.house_number,
            point=point, located_by=located_by, parcel=parcel,
        )
    finally:
        if owns_client:
            client.close()


def property_at(
    *,
    address: str,
    city: str,
    state: str,
    county_fips: str,
    house_number: str,
    point: LatLon,
    located_by: str,
    scale: int | None = None,
    center: LatLon | None = None,
    client: httpx.Client | None = None,
) -> FoundProperty:
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        return assemble_property(
            client, address=address, city=city, state=state, county_fips=county_fips,
            house_number=house_number, point=point, located_by=located_by, scale=scale, center=center,
        )
    finally:
        if owns_client:
            client.close()


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


def _local_aerial(client: httpx.Client, view: PlanView) -> tuple[bytes, str] | None:
    """A local government orthophoto covering the view, if one is set up."""
    for (west, south, east, north), url, credit in LOCAL_AERIALS:
        if not (west <= view.longitude <= east and south <= view.latitude <= north):
            continue
        x_min, y_min, x_max, y_max = view.bbox()
        response = client.get(url, timeout=AERIAL_TIMEOUT, params={
            "bbox": f"{x_min},{y_min},{x_max},{y_max}", "bboxSR": 102100, "imageSR": 102100,
            "size": f"{AERIAL_PIXELS},{AERIAL_PIXELS}", "format": "jpg", "f": "image",
        })
        response.raise_for_status()
        if not response.headers.get("content-type", "").startswith("image/"):
            raise httpx.HTTPError("no image returned")
        return response.content, credit
    return None


def fetch_aerial(view: PlanView, client: httpx.Client | None = None) -> tuple[bytes, str]:
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    token = os.environ.get("MAPBOX_TOKEN")
    try:
        try:
            local = _local_aerial(client, view)
            if local:
                return _finish(local[0]), local[1]
        except (httpx.HTTPError, OSError):
            pass
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

