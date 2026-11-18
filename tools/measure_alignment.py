"""Measure how far each aerial and each building outline sits from the county parcel base, in feet.

Run by hand when a source is added or an offset looks wrong:

    pip install -r tools/requirements.txt
    PYTHONPATH=. python tools/measure_alignment.py parcels  nashville
    PYTHONPATH=. python tools/measure_alignment.py aerials  nashville
    MAPBOX_TOKEN=pk... PYTHONPATH=. python tools/measure_alignment.py aerials san_francisco

parcels  how far the building outlines sit from their parcels: the (east, north) shift that puts the most of
         each house inside the parcel that holds its center, over every parcel in a 1.5 km square.
aerials  how far each aerial sits from the building outlines: the shift of the outlines that lands them on the
         strongest picture edges, over many windows. The median is reported with the spread of the windows.

(aerial - parcels) is how far the picture sits from the parcel base. Outline errors cancel in that difference, so
it is what goes in AERIAL_SHIFT_FT. In San Francisco the outlines are the city's surveyed footprints, so the
aerial result is already against the parcel base.

A positive east shift means the thing moves east to land on the other. Spread above about 3 ft means the
measurement is not good enough to correct with.
"""
from __future__ import annotations

import math
import os
import random
import sys
from io import BytesIO

import httpx
import numpy as np
from PIL import Image, ImageFilter
from shapely.affinity import translate
from shapely.geometry import Polygon

from permit_packets.core import property_lookup as pl
from permit_packets.core.property_plan import PlanView, mercator

FT = 3.28084
CLIENT = httpx.Client(follow_redirects=True, timeout=60)
# name -> (county fips, latitude, longitude of a residential area, aerial sources to test)
AREAS = {
    "san_francisco": ("06075", 37.7761, -122.4327),
    "nashville": ("47037", 36.1520, -86.8000),
    "mesa": ("04013", 33.4200, -111.8000),
    "chandler": ("04013", 33.3050, -111.8400),
    "san_tan_valley": ("04021", 33.2050, -111.5200),
    "el_cajon": ("06073", 32.7950, -116.9600),
    "oro_valley": ("04019", 32.4160, -110.9500),
    "las_vegas": ("32003", 36.1470, -115.1700),
    "charlotte": ("37119", 35.2085, -80.8300),
    "bellevue": ("53033", 47.5880, -122.1180),
    "monte_sereno": ("06085", 37.2400, -121.9830),
}


def _local(lat0: float, lon0: float):
    kx, ky = 111320 * math.cos(math.radians(lat0)) * FT, 111320 * FT
    return lambda ring: [((lon - lon0) * kx, (lat - lat0) * ky) for lat, lon in ring]


def _windows(lat: float, lon: float, step_m: float = 520):
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            yield lat + i * step_m / 111320, lon + j * step_m / (111320 * math.cos(math.radians(lat)))


def _outlines(fips: str, lat: float, lon: float, radius_m: float) -> list[list[tuple[float, float]]]:
    return [pl._rings(f) for f in pl.buildings_around(CLIENT, (lat, lon), radius_m, fips) if len(pl._rings(f)) >= 4]


def parcel_pairs(fips: str, lat: float, lon: float, radius_m: float = 260):
    county, to_ft = pl.COUNTIES[fips], _local(lat, lon)
    response = CLIENT.get(county.url, params={
        "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326, "outSR": 4326,
        "distance": radius_m, "units": "esriSRUnit_Meter", "f": "json", "returnGeometry": "true",
        "spatialRel": "esriSpatialRelIntersects", "outFields": county.parcel_field, "resultRecordCount": 400,
    })
    parcels = [Polygon(to_ft(pl._rings(f))) for f in response.json().get("features", []) if len(pl._rings(f)) >= 4]
    parcels = [p for p in parcels if p.is_valid and 2500 < p.area < 30000]
    houses = [Polygon(to_ft(ring)) for ring in _outlines(fips, lat, lon, radius_m + 60)]
    houses = [h for h in houses if h.is_valid and 900 < h.area < 5000]
    pairs = []
    for house in houses:
        holding = [p for p in parcels if p.contains(house.centroid)]
        if len(holding) == 1 and house.intersection(holding[0]).area / house.area > 0.6:
            pairs.append((house, holding[0]))
    return pairs


def _fit(pairs, reach: int = 14):
    scores = {
        (dx, dy): sum(translate(h, dx, dy).intersection(p).area / h.area for h, p in pairs) / len(pairs)
        for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1)
    }
    best = max(scores, key=scores.get)
    return best, scores[best], scores[(0, 0)]


def measure_parcels(name: str) -> None:
    fips, lat, lon = AREAS[name]
    pairs = [pair for la, lo in _windows(lat, lon) for pair in parcel_pairs(fips, la, lo)]
    if len(pairs) < 25:
        print(f"{name}: only {len(pairs)} house/parcel pairs, not enough"); return
    (east, north), best, zero = _fit(pairs)
    boots = np.array([_fit([random.choice(pairs) for _ in pairs])[0] for _ in range(8)])
    print(f"{name}: {len(pairs)} pairs. Outlines shift ({east}, {north}) ft east/north to fit parcels; "
          f"inside-parcel share {zero:.3f} -> {best:.3f}; bootstrap spread ({boots[:, 0].std():.1f}, {boots[:, 1].std():.1f}) ft")


def _edge_shift(image: Image.Image, box: tuple[float, float, float, float], rings, reach: int = 40):
    """Shift of the outlines, in feet east and north, that lands them on the strongest picture edges."""
    pixels = np.asarray(image.convert("L").filter(ImageFilter.GaussianBlur(1.2)), dtype=float)
    gy, gx = np.gradient(pixels)
    strength = np.hypot(gx, gy)
    x0, y0, x1, y1 = box
    size = pixels.shape[0]
    per_pixel = (x1 - x0) / size
    mid_lat = math.degrees(2 * math.atan(math.exp(((y0 + y1) / 2) / 6378137)) - math.pi / 2)
    cos_lat = math.cos(math.radians(mid_lat))
    points = []
    for ring in rings:
        merc = [mercator(la, lo) for la, lo in ring]
        for p, q in zip(merc, merc[1:] + merc[:1]):
            steps = max(2, int(math.dist(p, q) / (per_pixel * cos_lat) / 2))
            points += [(p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])) for t in np.linspace(0, 1, steps, endpoint=False)]
    points = np.array(points)
    margin = reach / FT / cos_lat + per_pixel * 3
    points = points[(points[:, 0] > x0 + margin) & (points[:, 0] < x1 - margin)
                    & (points[:, 1] > y0 + margin) & (points[:, 1] < y1 - margin)]
    if len(points) < 30:
        return None
    per_ft = 1 / FT / cos_lat
    best, zero = (-1.0, 0, 0), 0.0
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            cols = ((points[:, 0] + dx * per_ft - x0) / per_pixel).astype(int)
            rows = ((y1 - (points[:, 1] + dy * per_ft)) / per_pixel).astype(int)
            score = strength[rows, cols].mean()
            zero = score if (dx, dy) == (0, 0) else zero
            best = max(best, (score, dx, dy))
    return best[1], best[2], best[0] / max(zero, 1e-9)


def _aerial_sources(token: str | None):
    sources = {"usgs": (pl.USGS_IMAGE_URL, {"interpolation": "RSP_BilinearInterpolation"})}
    for _, url, _ in pl.LOCAL_AERIALS:
        sources[url.split("/")[2]] = (url, {})
    return sources


def measure_aerials(name: str) -> None:
    fips, lat, lon = AREAS[name]
    token = os.environ.get("MAPBOX_TOKEN")
    results: dict[str, list[tuple[int, int]]] = {}
    for la, lo in _windows(lat, lon, 420):
        rings = _outlines(fips, la, lo, 200)
        if len(rings) < 10:
            continue
        x, y = mercator(la, lo)
        half = 230 / FT / math.cos(math.radians(la))
        box = (x - half, y - half, x + half, y + half)
        if token:
            try:
                view = PlanView(la, lo, 40)  # a 280 ft square, so the window matches the box above closely
                image_bytes = pl._mapbox_aerial(CLIENT, view, token, shifted=False)
                found = _edge_shift(Image.open(BytesIO(image_bytes)), view.bbox(), rings)
                if found and found[2] >= 1.15:
                    results.setdefault("mapbox", []).append(found[:2])
            except Exception:
                pass
        for label, (url, extra) in _aerial_sources(token).items():
            try:
                response = CLIENT.get(url, params={
                    "bbox": ",".join(map(str, box)), "bboxSR": 102100, "imageSR": 102100, "size": "1400,1400",
                    "format": "jpg", "f": "image", **extra})
                image = Image.open(BytesIO(response.content))
            except Exception:
                continue
            if pl._blank(response.content):
                continue
            found = _edge_shift(image, box, rings)
            if found and found[2] >= 1.15:  # the best fit has to beat no shift by 15 percent
                results.setdefault(label, []).append(found[:2])
    for label, shifts in results.items():
        a = np.array(shifts)
        print(f"{name} {label}: {len(a)} windows. Outlines shift median ({np.median(a[:, 0]):.0f}, {np.median(a[:, 1]):.0f}) ft "
              f"east/north to match the picture; spread ({a[:, 0].std():.1f}, {a[:, 1].std():.1f}) ft")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("parcels", "aerials") or sys.argv[2] not in AREAS:
        sys.exit(__doc__)
    (measure_parcels if sys.argv[1] == "parcels" else measure_aerials)(sys.argv[2])
