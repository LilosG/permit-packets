"""Builds the sample packets shown on the overview page, using the real engine on `main`.

Setup (once):
    git worktree add /tmp/main origin/main
    python3 -m venv /tmp/venv-main && /tmp/venv-main/bin/pip install -r /tmp/main/requirements.txt
Run from the overview branch:
    /tmp/venv-main/bin/python tools/build_samples.py --main /tmp/main --out .

For each job type it builds one packet through REGISTRY[key].build_response with sample_mode=True
(the address and parcel stay hidden), then writes
    samples/<slug>.pdf
    samples/<slug>/page-N.jpg      cover, site plan, the type's diagram page, load calculation
    samples/<slug>/thumb-N.jpg     the same pages at 850 px wide, cropped above the footer, for the page grid
The site plans use a real aerial photo when the lookup services answer, and the app's schematic
site plan otherwise. Nothing is written for a type whose packet fails to build.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

SAMPLE_ADDRESS = "1000 W Naranja Dr, Oro Valley, AZ 85737"
GOLDEN_EV_CASE = "oro_valley_attached_no_plan"
JPEG_QUALITY = 86      # matches the quantization tables of the earlier pages/*.jpg
RENDER_DPI = 200       # letter at 200 dpi is 1700 x 2200
DIAGRAM_TITLES = ("One-line diagram", "Riser diagram")

# Where each type's markers go on the primary building, in plan units (0-1000, north up, 40 ft/in).
# Checked by eye on the rendered site plan. A bend is a point the route passes through.
PLACEMENTS = {
    "ev_charger": {"markers": {"panel": (520, 634), "charger": (600, 638)}, "route": []},
    "service_upgrade": {"markers": {"meter": (340, 505), "panel": (340, 468)}, "route": []},
    "subpanel": {
        "markers": {"panel": (520, 634), "subpanel": (677, 642)},
        "route": [(520, 712), (677, 712)],
    },
    "appliance_circuit": {"markers": {"panel": (707, 540), "appliance": (815, 480)}, "route": []},
}


def load_requests(main: Path) -> dict[str, dict]:
    samples = main / "tests" / "samples"
    case = json.loads((main / "tests" / "golden" / "cases" / f"{GOLDEN_EV_CASE}.json").read_text("utf-8"))
    requests = {"ev_charger": case}
    for key, name in (("service_upgrade", "service_upgrade"), ("subpanel", "subpanel"),
                      ("appliance_circuit", "appliance_circuit")):
        requests[key] = json.loads((samples / f"{name}.json").read_text("utf-8"))
    return requests


def to_current_request(payload: dict) -> dict:
    """Same mapping as tests/test_ev_golden.py: a case in the original shape, as the routes take it."""
    plan = payload.get("plan")
    if plan is None:
        return payload
    markers = {name: plan[name] for name in ("panel", "charger")}
    rest = {key: value for key, value in plan.items() if key not in markers}
    return {**payload, "plan": {**rest, "markers": markers}}


def find_site():
    """The property and its aerial photo, or what could be fetched. Never raises."""
    from permit_packets.core.property_lookup import AerialUnavailable, fetch_aerial, find_property
    try:
        found = find_property(SAMPLE_ADDRESS)
    except Exception as error:  # network blocked, service down, address not found
        print(f"  property lookup failed ({type(error).__name__}: {error})")
        return None, None, None
    try:
        image, credit = fetch_aerial(found.view)
        return found, image, credit
    except (AerialUnavailable, Exception) as error:
        print(f"  aerial failed ({type(error).__name__}: {error}); using outlines only")
        return found, None, None


def plan_for(key: str, found, aerial: bytes | None, credit: str | None) -> dict | None:
    if found is None or found.primary_building is None:
        return None
    credits = [c for c in found.credits if not (aerial and c.startswith("Building"))]
    if credit:
        credits.append(credit)
    placement = PLACEMENTS[key]
    return {
        "scale_ft_per_in": found.view.scale_ft_per_in,
        "markers": {name: list(point) for name, point in placement["markers"].items()},
        "route": [list(point) for point in placement["route"]],
        "buildings": [[list(p) for p in b] for b in found.buildings],
        "primary_building": found.primary_building,
        "lot": [list(p) for p in found.lot],
        "parcel_number": found.parcel_number,
        "aerial_base64": base64.b64encode(aerial).decode() if aerial else None,
        "credits": credits,
    }


def content_bottom(image) -> int:
    """The last row of page content above the footer, in pixels."""
    gray = image.convert("L")
    limit = int(image.height * 0.85)
    for y in range(limit - 1, 0, -1):
        if gray.crop((0, y, image.width, y + 1)).getextrema()[0] < 235:
            return y
    return limit


def render_pages(pdf: bytes, wanted: list[int], folder: Path) -> None:
    import io
    import pypdfium2
    from PIL import Image
    folder.mkdir(parents=True, exist_ok=True)
    for old in [*folder.glob("page-*.jpg"), *folder.glob("thumb-*.jpg")]:
        old.unlink()
    document = pypdfium2.PdfDocument(pdf)
    try:
        images = {n: document[n - 1].render(scale=RENDER_DPI / 72).to_pil().convert("RGB") for n in wanted}
    finally:
        document.close()
    # One crop height for the four thumbnails, so the grid lines up.
    crop = min(max(content_bottom(image) for image in images.values()) + 40, images[wanted[0]].height)
    for number, image in images.items():
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        (folder / f"page-{number}.jpg").write_bytes(buffer.getvalue())
        thumb = image.crop((0, 0, image.width, crop)).resize((image.width // 2, crop // 2), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        thumb.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        (folder / f"thumb-{number}.jpg").write_bytes(buffer.getvalue())


def page_numbers(titles: list[str]) -> list[int]:
    """1-based pages: cover, site plan, the type's diagram, load calculation."""
    def at(title: str) -> int:
        return titles.index(title) + 1
    diagram = next(title for title in DIAGRAM_TITLES if title in titles)
    return [1, at("Site plan"), at(diagram), at("Load calculation")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--main", type=Path, default=Path("/tmp/main"), help="checkout of origin/main")
    parser.add_argument("--out", type=Path, default=Path("."), help="overview site folder")
    args = parser.parse_args()
    main_dir = args.main.resolve()
    sys.path.insert(0, str(main_dir))

    import pypdfium2
    from permit_packets.job_types import REGISTRY

    requests = load_requests(main_dir)
    print(f"Looking up {SAMPLE_ADDRESS} ...")
    found, aerial, credit = find_site()
    print("  real aerial photo" if aerial else "  NO aerial: schematic site plans")

    summary = {}
    for key, job_type in REGISTRY.items():
        payload = to_current_request(requests[key]) if key == "ev_charger" else dict(requests[key])
        payload["sample_mode"] = True
        plan = plan_for(key, found, aerial, credit)
        if plan:
            payload["plan"] = plan
        request = job_type.request_model.model_validate(payload)
        result = job_type.build_response(request)
        titles = [d["title"] for d in result.body["documents"]]
        pdf_path = args.out / "samples" / f"{job_type.slug}.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(result.pdf)
        pages = page_numbers(titles)
        render_pages(result.pdf, pages, args.out / "samples" / job_type.slug)
        count = len(pypdfium2.PdfDocument(result.pdf))
        summary[job_type.slug] = {"pages": count, "images": pages, "aerial": bool(aerial and plan)}
        print(f"  {job_type.slug}: {count} pages, images from pages {pages}, "
              f"{'real aerial' if aerial and plan else 'schematic'} site plan")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
