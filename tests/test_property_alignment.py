"""The lot outline, building footprint and street have to line up on the plan, in every county we pull from.

Each case is one real residential parcel. tests/fixtures/alignment/<name>.json holds exactly what the public
services returned for it (Census geocode, county parcel layer, building outlines, Census street centerline),
with no owner data. The real find_property runs over those responses, so the county's coordinate system,
the reprojection to latitude and longitude and the scaling onto the 1000 unit plan are all exercised.

Tolerance is 3 ft, set by TOLERANCE_FT.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import httpx
import pytest

from permit_packets.core import property_lookup as pl
from permit_packets.core.property_plan import centroid, contains, distance_to_segment

FIXTURES = Path(__file__).parent / "fixtures" / "alignment"
TOLERANCE_FT = 3.0
# name -> (county fips, what the county calls the parcel service, native coordinate system of that layer)
CASES = {
    "san_francisco": ("06075", "San Francisco Planning parcels", "WGS84 degrees"),
    "nashville": ("47037", "Metro Nashville parcels", "TN State Plane ft (EPSG:2274)"),
    "mesa": ("04013", "Maricopa County Assessor parcels", "Web Mercator (EPSG:3857)"),
    "chandler": ("04013", "Maricopa County Assessor parcels", "Web Mercator (EPSG:3857)"),
    "san_tan_valley": ("04021", "Pinal parcels via Arizona Dept of Water Resources", "UTM 12N (EPSG:26912)"),
    "el_cajon": ("06073", "San Diego County parcels", "CA State Plane VI ft (EPSG:2230)"),
    "oro_valley": ("04019", "Pima County parcels", "AZ Central State Plane ft (EPSG:2868)"),
    "las_vegas": ("32003", "Clark County / City of Las Vegas parcels", "NV East State Plane ft (EPSG:3421)"),
    "charlotte": ("37119", "Mecklenburg County parcels", "NC State Plane ft (EPSG:2264)"),
    "bellevue": ("53033", "King County GIS parcels", "Web Mercator (EPSG:3857)"),
    "monte_sereno": ("06085", "County of Santa Clara GIS parcels", "Web Mercator (EPSG:3857)"),
    "chico": ("06007", "Butte County GIS parcels", "Web Mercator (EPSG:3857)"),
}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _client(fixture: dict, fips: str) -> httpx.Client:
    county_host = httpx.URL(pl.COUNTIES[fips].url).host
    census = {"result": {"addressMatches": [{
        "matchedAddress": fixture["census"]["matchedAddress"],
        "coordinates": fixture["census"]["coordinates"],
        "addressComponents": fixture["census"]["addressComponents"],
        "geographies": fixture["census"]["geographies"],
    }]}}

    def serve(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "geocoding.geo.census.gov":
            return httpx.Response(200, json=census)
        if host == county_host:
            return httpx.Response(200, json=fixture["parcel"])
        if host == httpx.URL(pl.SF_FOOTPRINTS_URL).host:
            return httpx.Response(200, json=fixture.get("footprints", {"features": []}))
        if host == httpx.URL(pl.STRUCTURES_URL).host:
            return httpx.Response(200, json=fixture.get("buildings", {"features": []}))
        return httpx.Response(200, json={"features": []})

    return httpx.Client(transport=httpx.MockTransport(serve))


def _distance_to_polygon(point, polygon) -> float:
    """0 inside the polygon, else the plan distance to its nearest edge."""
    if contains(polygon, point):
        return 0.0
    return min(distance_to_segment(point, a, b) for a, b in zip(polygon, polygon[1:] + polygon[:1]))


def _heading(a, b) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180


def _angle_between(first: float, second: float) -> float:
    gap = abs(first - second) % 180
    return min(gap, 180 - gap)


def measure(name: str) -> dict:
    """Run one case and return its alignment numbers in feet."""
    fips = CASES[name][0]
    fixture = _fixture(name)
    client = _client(fixture, fips)
    found = pl.find_property(fixture["address"], client)
    view, feet = found.view, found.view.feet_per_unit
    assert found.located_by == "county" and len(found.lot) >= 4, "the county parcel was not used"

    # Raw footprints, before the plan clips the house to its lot, so a misplaced outline is not hidden.
    lot_ll = [view.to_latlon(*point) for point in found.lot]
    features = pl.buildings_around(client, centroid(lot_ll), 90, fips)
    middle = centroid(lot_ll)
    inside = [
        feature for feature in features
        if contains(lot_ll, pl._center(feature)) or contains(pl._rings(feature), middle)
    ]
    house = pl.pick_building(inside, middle)
    assert house is not None, "no building outline sits on the lot"
    footprint = [view.to_plan(lat, lon) for lat, lon in pl._rings(house)]
    excursion = max(_distance_to_polygon(point, found.lot) for point in footprint) * feet

    # Frontage: the lot edge that runs along the address's street.
    street_paths = [[view.to_plan(lat, lon) for lon, lat in path] for path in fixture["street"]["paths"]]
    street_segments = [(a, b) for path in street_paths for a, b in zip(path, path[1:])]
    assert street_segments, "no street centerline in the fixture"
    best = None
    for a, b in zip(found.lot, found.lot[1:] + found.lot[:1]):
        if math.dist(a, b) * feet < 15:
            continue
        nearest = min(street_segments, key=lambda s: distance_to_segment(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), *s))
        if _angle_between(_heading(a, b), _heading(*nearest)) > 20:
            continue
        gap = distance_to_segment(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), *nearest) * feet
        if best is None or gap < best[0]:
            best = (gap, a, b)
    assert best is not None, "no lot edge runs along the street"
    street_gap, a, b = best
    # How far the house reaches past the front lot line, toward the street.
    inward = centroid(found.lot)
    side = (b[0] - a[0]) * (inward[1] - a[1]) - (b[1] - a[1]) * (inward[0] - a[0])
    length = math.dist(a, b)
    past_front = 0.0
    for point in footprint:
        signed = ((b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])) / length
        past_front = max(past_front, (-signed if side > 0 else signed) * feet)

    # The plan must hand back the county's own coordinates: plan -> latitude/longitude -> plan.
    round_trip = max(
        math.dist(view.to_plan(*view.to_latlon(*point)), point) for point in found.lot + footprint
    ) * feet
    return {
        "excursion_ft": excursion, "past_front_ft": past_front, "street_gap_ft": street_gap,
        "round_trip_ft": round_trip, "footprint_credit": pl.footprint_credit(fips, features),
        "scale": view.scale_ft_per_in,
    }


@pytest.mark.parametrize("name", sorted(CASES))
def test_lot_outline_lines_up_with_house_and_street(name):
    numbers = measure(name)
    assert numbers["round_trip_ft"] < 0.2, "plan coordinates drift from latitude/longitude"
    assert numbers["excursion_ft"] <= TOLERANCE_FT, (
        f"the house sticks {numbers['excursion_ft']:.1f} ft outside the lot outline")
    assert numbers["past_front_ft"] <= TOLERANCE_FT, (
        f"the house reaches {numbers['past_front_ft']:.1f} ft past the front property line")
    # A front lot line sits one right-of-way half width back from the street centerline.
    assert 8 <= numbers["street_gap_ft"] <= 80, f"front lot line is {numbers['street_gap_ft']:.0f} ft from the street"


def test_san_francisco_uses_the_citys_footprints_because_usa_structures_misses_the_lot():
    numbers = measure("san_francisco")
    assert "San Francisco" in numbers["footprint_credit"]


def test_every_county_source_has_an_alignment_case():
    covered = {fips for fips, _, _ in CASES.values()}
    assert covered == set(pl.COUNTIES), "a county was added without an alignment case"


def test_moving_the_view_center_moves_the_aerial_box_the_same_distance():
    """The aerial is asked for with the same box the plan is drawn in, so a shift moves them together."""
    view = pl.PlanView(37.776, -122.4327, 20)
    west, south, east, north = view.bbox()
    shifted = view.bbox((-20, 0))
    metres_per_foot = 1 / pl.FEET_PER_METER / math.cos(math.radians(view.latitude))
    assert shifted[0] - west == pytest.approx(-20 * metres_per_foot)
    assert shifted[3] - north == pytest.approx(0)
    assert east - west == pytest.approx(shifted[2] - shifted[0])


def _jpeg(color) -> bytes:
    from io import BytesIO
    from PIL import Image
    import random
    image = Image.new("RGB", (60, 60), color)
    pixels = image.load()
    for x in range(60):
        for y in range(60):
            pixels[x, y] = tuple(min(255, max(0, c + random.randint(-12, 12))) for c in color)
    out = BytesIO()
    image.save(out, "JPEG")
    return out.getvalue()


def test_parcels_are_never_moved_only_outlines_are():
    fixture = _fixture("nashville")
    client = _client(fixture, "47037")
    ring = fixture["parcel"]["features"][0]["geometry"]["rings"][0]
    found = pl.find_property(fixture["address"], client)
    back = [found.view.to_latlon(*p) for p in found.lot]
    assert max(
        pl.ground_distance_ft((lat, lon), (b_lat, b_lon))
        for (lon, lat), (b_lat, b_lon) in zip(ring[:-1], back)
    ) < 0.2


def test_outlines_move_by_the_measured_feet_inside_the_area_and_not_outside(monkeypatch):
    feature = {"geometry": {"rings": [[[-86.80, 36.15], [-86.80, 36.1501], [-86.7999, 36.15], [-86.80, 36.15]]]}}
    moved = pl._moved([feature], (36.15, -86.80))[0]["geometry"]["rings"][0][0]
    east = pl.ground_distance_ft((36.15, -86.80), (36.15, moved[0]))
    assert east == pytest.approx(4.0, abs=0.05)
    assert pl._moved([feature], (40.0, -100.0))[0] is feature


def test_san_francisco_aerial_is_asked_for_in_a_box_moved_by_the_measured_shift(monkeypatch):
    monkeypatch.delenv("MAPBOX_TOKEN", raising=False)
    seen = []

    def serve(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["bbox"])
        return httpx.Response(200, content=_jpeg((90, 90, 90)), headers={"content-type": "image/jpeg"})

    view = pl.PlanView(37.776, -122.4327, 20)
    pl.fetch_aerial(view, httpx.Client(transport=httpx.MockTransport(serve)))
    assert seen == [",".join(map(str, view.bbox((-20, 6))))]


def test_dark_aerials_are_lifted():
    from io import BytesIO
    from PIL import Image, ImageStat
    out = Image.open(BytesIO(pl._finish(_jpeg((35, 35, 40)))))
    assert ImageStat.Stat(out.convert("L")).mean[0] > 85


def test_local_orthophoto_is_asked_for_no_finer_than_it_can_draw():
    sizes = []

    def serve(request: httpx.Request) -> httpx.Response:
        sizes.append(int(request.url.params["size"].split(",")[0]))
        return httpx.Response(200, content=_jpeg((120, 110, 90)), headers={"content-type": "image/jpeg"})

    _, credit = pl.fetch_aerial(pl.PlanView(32.7935, -116.958, 30), httpx.Client(transport=httpx.MockTransport(serve)))
    assert "San Diego" in credit and sizes[0] < pl.AERIAL_PIXELS


def test_mapbox_goes_ahead_of_usgs_and_coarse_sources_but_not_sharp_local_orthophotos(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")

    def first_host(view) -> str:
        hosts = []

        def serve(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            return httpx.Response(200, content=_jpeg((120, 110, 90)), headers={"content-type": "image/jpeg"})

        pl.fetch_aerial(view, httpx.Client(transport=httpx.MockTransport(serve)))
        return hosts[0]

    assert first_host(pl.PlanView(36.17, -115.14, 30)) == "api.mapbox.com"      # Las Vegas, no local orthophoto
    assert first_host(pl.PlanView(37.776, -122.4327, 20)) == "api.mapbox.com"   # San Francisco
    assert first_host(pl.PlanView(36.15, -86.80, 30)) == "maps.nashville.gov"   # 15 cm local orthophoto


def _gradient_tile(column: int, row: int, size: int = 512) -> bytes:
    """A tile whose red channel counts global x pixels (three per step) and green counts global y, so where a
    stitched picture came from can be read back from its pixels."""
    import numpy as np
    from io import BytesIO
    from PIL import Image

    xs = (column * size + np.arange(size)) // 3 % 256
    ys = (row * size + np.arange(size)) // 3 % 256
    pixels = np.zeros((size, size, 3), dtype=np.uint8)
    pixels[:, :, 0] = xs[None, :]
    pixels[:, :, 1] = ys[:, None]
    pixels[:, :, 2] = 128
    out = BytesIO()
    Image.fromarray(pixels).save(out, "JPEG", quality=95, subsampling=0)
    return out.getvalue()


def _tile_server(requests: list[tuple[int, int, int]]):
    def serve(request: httpx.Request) -> httpx.Response:
        z, x, y = request.url.path.split("/v4/mapbox.satellite/")[1].split("@")[0].split("/")
        requests.append((int(z), int(x), int(y)))
        return httpx.Response(200, content=_gradient_tile(int(x), int(y)), headers={"content-type": "image/jpeg"})
    return httpx.Client(transport=httpx.MockTransport(serve))


def _picture(view: pl.PlanView, shifted: bool = True):
    from io import BytesIO
    from PIL import Image
    requests: list[tuple[int, int, int]] = []
    raw = pl._mapbox_aerial(_tile_server(requests), view, "pk.test", shifted=shifted)
    picture = Image.open(BytesIO(raw))
    picture.load()
    return picture, requests


def test_mapbox_zoom_fills_the_plan_at_full_resolution_within_the_tile_limit():
    """z19 stretched a 140 ft San Francisco view about 4x. The zoom is now picked to fill AERIAL_PIXELS, up to
    z20 at @2x (Mapbox's z21 detail), and stepped down only to stay inside MAPBOX_TILE_LIMIT."""
    from permit_packets.core.property_plan import ENGINEER_SCALES_FT_PER_IN
    for latitude, longitude in ((37.776, -122.4327), (36.17, -115.14), (33.4, -111.8), (35.2, -80.83)):
        for scale in ENGINEER_SCALES_FT_PER_IN:
            view = pl.PlanView(latitude, longitude, scale)
            zoom = pl.mapbox_zoom(view)
            assert zoom <= pl.MAPBOX_MAX_ZOOM and pl._tile_count(view.bbox(), zoom) <= pl.MAPBOX_TILE_LIMIT
            left, _, right, _ = pl._tile_span(view.bbox(), zoom)
            native_px = (right - left) * 512
            # Full resolution, unless already at Mapbox's finest zoom or one finer would break the tile limit.
            assert (native_px >= pl.AERIAL_PIXELS or zoom == pl.MAPBOX_MAX_ZOOM
                    or pl._tile_count(view.bbox(), zoom + 1) > pl.MAPBOX_TILE_LIMIT), (latitude, scale, zoom)
            # And not finer than needed: one zoom coarser would not fill the plan.
            assert (right - left) * 256 < pl.AERIAL_PIXELS, (latitude, scale, zoom)
    for latitude, longitude, scale in ((37.776, -122.4327, 20), (36.17, -115.14, 40), (33.4, -111.8, 100)):
        view = pl.PlanView(latitude, longitude, scale)
        picture, requests = _picture(view)
        assert {z for z, _, _ in requests} == {pl.mapbox_zoom(view, view.bbox(pl.shift_for(view, "mapbox")))}
        assert len(requests) <= pl.MAPBOX_TILE_LIMIT and picture.width == picture.height
    sf = pl.PlanView(37.776, -122.4327, 20)
    picture, _ = _picture(sf)
    assert picture.width >= 700, "the 140 ft San Francisco view should come from about 720 real pixels, not 360"


def test_aerial_is_encoded_once_at_full_chroma_and_sources_are_asked_for_lossless_png(monkeypatch):
    from io import BytesIO
    from PIL import Image
    monkeypatch.delenv("MAPBOX_TOKEN", raising=False)
    formats = []

    def serve(request: httpx.Request) -> httpx.Response:
        formats.append(request.url.params["format"])
        out = BytesIO()
        Image.new("RGB", (600, 600), (120, 110, 90)).save(out, "PNG")
        return httpx.Response(200, content=out.getvalue(), headers={"content-type": "image/png"})

    image, _ = pl.fetch_aerial(pl.PlanView(33.4152, -111.8315, 20), httpx.Client(transport=httpx.MockTransport(serve)))
    assert formats and set(formats) == {"png24"}
    picture = Image.open(BytesIO(image))
    assert picture.format == "JPEG" and picture.size == (pl.AERIAL_PIXELS, pl.AERIAL_PIXELS)
    assert picture.layer[0][1:3] == (1, 1), "chroma must not be subsampled"
    raw, _ = _picture(pl.PlanView(37.776, -122.4327, 20))
    assert raw.format == "PNG", "the stitched Mapbox crop must not be re-encoded as JPEG"


def test_stitched_mapbox_tiles_have_no_seam_where_two_tiles_meet():
    import numpy as np
    zoom, column = 19, 83_850
    longitude = column / 2 ** zoom * 360 - 180  # the left edge of a tile column, so the view straddles two tiles
    picture, requests = _picture(pl.PlanView(37.776, longitude, 20))
    assert len({x for _, x, _ in requests}) >= 2
    red = np.asarray(picture)[picture.height // 2, :, 0].astype(float)
    ahead = red[16:] - red[:-16]  # three pixels per red step, so 16 pixels is 16/3 steps wherever the row is
    clear = (red[:-16] > 12) & (red[16:] < 243) & (red[:-16] < red[16:] + 1)  # skip the places where red wraps
    assert clear.sum() > picture.width // 2
    assert np.abs(ahead[clear] - 16 / 3).max() < 3.5


def test_mapbox_shift_moves_the_picture_by_the_measured_feet():
    import numpy as np
    view = pl.PlanView(37.776, -122.4327, 20)  # inside the San Francisco shift box: 22 ft west, 9 ft north
    moved, _ = _picture(view)
    plain, _ = _picture(view, shifted=False)
    assert moved.size == plain.size
    centre = lambda im, band: float(np.asarray(im)[im.height // 2, im.width // 2, band])
    steps = lambda a, b: (a - b + 128) % 256 - 128  # the gradient wraps every 256 steps (768 px)
    metres_per_pixel = view.size_ft / pl.FEET_PER_METER / plain.width
    west_px = steps(centre(plain, 0), centre(moved, 0)) * 3   # red counts three pixels per step
    north_px = steps(centre(plain, 1), centre(moved, 1)) * 3
    assert west_px * metres_per_pixel * pl.FEET_PER_METER == pytest.approx(22, abs=1.5)
    assert north_px * metres_per_pixel * pl.FEET_PER_METER == pytest.approx(9, abs=1.5)


def _mapbox_features(*addresses: tuple[str, str, str, str]) -> dict:
    return {"features": [{"properties": {
        "name": street, "name_preferred": street,
        "context": {"place": {"name": city}, "region": {"region_code": state}, "postcode": {"name": postcode}},
    }} for street, city, state, postcode in addresses]}


def test_suggestions_come_from_mapbox_with_its_zip_codes_and_one_line_per_street_and_city(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    seen = []

    def serve(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=_mapbox_features(
            ("710 Steiner Street", "San Francisco", "CA", "94117"),
            ("710 Steiner Street", "San Francisco", "CA", "94115"),   # same street and city: dropped
            ("710 Steiner Street", "San Jose", "CA", "95115"),
            ("Steiner Street", "San Francisco", "CA", "94117"),        # no house number: not an address
        ))

    suggestions = pl.suggest_addresses("710 Steiner", httpx.Client(transport=httpx.MockTransport(serve)))
    assert suggestions == ["710 Steiner Street, San Francisco, CA 94117", "710 Steiner Street, San Jose, CA 95115"]
    assert [u.host for u in seen] == ["api.mapbox.com"]
    assert seen[0].params["access_token"] == "pk.test" and seen[0].params["country"] == "us"


def test_photon_is_used_for_suggestions_only_without_a_token(monkeypatch):
    hosts = []

    def serve(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200, json={"features": [{"properties": {
            "countrycode": "US", "housenumber": "710", "street": "Steiner Street", "city": "San Francisco",
            "state": "California", "postcode": "94115"}}]})

    client = httpx.Client(transport=httpx.MockTransport(serve))
    assert pl.suggest_addresses("710 Steiner", client) == ["710 Steiner Street, San Francisco, CA 94115"]
    assert hosts and set(hosts) == {"photon.komoot.io"}
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    hosts.clear()
    pl.suggest_addresses("710 Steiner", client)
    assert set(hosts) == {"api.mapbox.com"}


def test_a_failed_mapbox_lookup_gives_no_suggestions_and_does_not_fall_back_to_photon(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    hosts = []

    def serve(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(401)

    assert pl.suggest_addresses("710 Steiner", httpx.Client(transport=httpx.MockTransport(serve))) == []
    assert set(hosts) == {"api.mapbox.com"}


def test_suggestions_are_boxed_to_each_clients_city_and_keep_only_that_city(monkeypatch):
    from permit_packets.jurisdictions import CHANDLER, MESA

    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    asked = []

    def serve(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        return httpx.Response(200, json=_mapbox_features(
            ("1432 East 1st Street", "Mesa", "AZ", "85203"),
            ("1432 East 1st Street", "Mesa", "AZ", "85204"),       # same street and city: dropped
            ("1432 East 1st Street", "Gilbert", "AZ", "85233"),     # inside Mesa's box, not Mesa: dropped
            ("1432 East 1st Street", "Chandler", "AZ", "85225"),
            ("1432 East 1st Street", "Pueblo", "CO", "81001"),
        ))

    client = httpx.Client(transport=httpx.MockTransport(serve))
    suggestions = pl.suggest_addresses("1432 E 1st", client, areas=[MESA, CHANDLER])
    assert suggestions == ["1432 East 1st Street, Mesa, AZ 85203", "1432 East 1st Street, Chandler, AZ 85225"]
    assert len(asked) == 2  # one search per city
    by_box = {tuple(float(v) for v in call["bbox"].split(",")): call for call in asked}
    assert set(by_box) == {MESA.bbox, CHANDLER.bbox}
    assert by_box[MESA.bbox]["proximity"] == f"{MESA.center[0]},{MESA.center[1]}"
    assert by_box[CHANDLER.bbox]["proximity"] == f"{CHANDLER.center[0]},{CHANDLER.center[1]}"
    # With no areas (a client with no mapped city) the search is not boxed.
    asked.clear()
    pl.suggest_addresses("1432 E 1st", client)
    assert "bbox" not in asked[0] and "proximity" not in asked[0]


def test_photon_suggestions_are_kept_to_the_clients_city_too():
    from permit_packets.jurisdictions import SAN_FRANCISCO

    features = [{"properties": {"countrycode": "US", "housenumber": "710", "street": "Steiner Street", "city": city,
                                "state": state, "postcode": "00000"}}
                for city, state in (("San Jose", "California"), ("San Francisco", "California"))]
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"features": features})))
    assert pl.suggest_addresses("710 Steiner", client, areas=[SAN_FRANCISCO]) == [
        "710 Steiner Street, San Francisco, CA 00000"]


# (street, Mapbox's community label, (lon, lat), what the Census names the place at that spot)
_DAVIDSON = (
    ("4000 Murfreesboro Pike", "Antioch", (-86.6560, 36.0595), "Nashville-Davidson metropolitan government (balance)"),
    ("6000 Old Hickory Boulevard", "Hermitage", (-86.6120, 36.2000), "Nashville-Davidson metropolitan government (balance)"),
    ("2500 White Avenue", "Nashville", (-86.7700, 36.1170), "Berry Hill city"),       # its own permit office
    ("4500 Harding Pike", "Nashville", (-86.8560, 36.1020), "Belle Meade city"),      # mailed as Nashville, but Belle Meade
    ("100 Broadway", "Nashville", (-86.7770, 36.1620), "Nashville-Davidson metropolitan government (balance)"),
)


def _davidson_client(census_up: bool = True):
    from permit_packets.jurisdictions import NASHVILLE
    by_x = {round(point[0], 4): place for _, _, point, place in _DAVIDSON}
    searches, lookups = [], []

    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.mapbox.com":
            searches.append(dict(request.url.params))
            return httpx.Response(200, json={"features": [{
                "geometry": {"coordinates": list(point)},
                "properties": {"name": street, "name_preferred": street, "context": {
                    "place": {"name": community}, "region": {"region_code": "TN"}, "postcode": {"name": "37211"}}},
            } for street, community, point, _ in _DAVIDSON]})
        lookups.append(request.url.host)
        if not census_up:
            return httpx.Response(503)
        place = by_x[round(float(request.url.params["x"]), 4)]
        return httpx.Response(200, json={"result": {"geographies": {"Incorporated Places": [{"NAME": place}]}}})

    return httpx.Client(transport=httpx.MockTransport(serve)), NASHVILLE, searches, lookups


def test_nashville_suggestions_keep_davidson_county_communities_and_drop_satellite_cities(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    client, nashville, searches, lookups = _davidson_client()
    suggestions = pl.suggest_addresses("4000 Murf", client, areas=[nashville])
    assert suggestions == [
        "4000 Murfreesboro Pike, Antioch, TN 37211",
        "6000 Old Hickory Boulevard, Hermitage, TN 37211",
        "100 Broadway, Nashville, TN 37211",
    ]
    assert set(lookups) == {"geocoding.geo.census.gov"}  # decided by where the address is, not what Mapbox calls it
    assert tuple(float(v) for v in searches[0]["bbox"].split(",")) == nashville.bbox
    west, south, east, north = nashville.bbox
    assert west < -86.656 and east > -86.612 and north > 36.4 - 0.01  # Antioch, Hermitage and Joelton are inside the box


def test_nashville_falls_back_to_the_city_name_when_the_census_lookup_is_down(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    client, nashville, _, _ = _davidson_client(census_up=False)
    # Exact-name matching, as for every other city: only what Mapbox itself labels Nashville.
    assert pl.suggest_addresses("100 Broad", client, areas=[nashville]) == [
        "2500 White Avenue, Nashville, TN 37211", "4500 Harding Pike, Nashville, TN 37211",
        "100 Broadway, Nashville, TN 37211"]


def test_other_cities_still_match_by_exact_city_name_without_a_census_lookup(monkeypatch):
    from permit_packets.jurisdictions import MESA
    monkeypatch.setenv("MAPBOX_TOKEN", "pk.test")
    hosts = []

    def serve(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200, json=_mapbox_features(("1 Main Street", "Mesa", "AZ", "85201"),
                                                         ("2 Main Street", "Gilbert", "AZ", "85233")))

    out = pl.suggest_addresses("Main", httpx.Client(transport=httpx.MockTransport(serve)), areas=[MESA])
    assert out == ["1 Main Street, Mesa, AZ 85201"] and set(hosts) == {"api.mapbox.com"}
