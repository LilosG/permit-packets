"""Item 2: pages drawn natively at letter or tabloid, with a site plan scale that is true on both."""
import json
import re

import pypdfium2
import pytest

from permit_packets.core.layout import LETTER, TABLOID, resolve_sheet
from permit_packets.core.property_plan import PLAN_WIDTH_IN
from permit_packets.job_types import REGISTRY
from permit_packets.jurisdictions import ORO_VALLEY, Jurisdiction
from tests.packet_helpers import build, packet_pages, sample
from tests.test_ev_golden import GOLDEN, to_current_request

ALL = sorted(REGISTRY)
SIZES = {"letter": (612, 792), "tabloid": (1224, 792)}


def _plan(key: str, scale: int = 30) -> dict:
    import base64
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (600, 600), "#8a9a7b").save(buffer, format="JPEG")
    markers = {
        "ev_charger": {"panel": [400, 500], "charger": [700, 300]},
        "service_upgrade": {"meter": [300, 500], "panel": [400, 500]},
        "subpanel": {"panel": [400, 500], "subpanel": [700, 300]},
        "appliance_circuit": {"panel": [400, 500], "appliance": [700, 300]},
        "commercial_subpanel": {"panel": [400, 500], "subpanel": [700, 300]},
        "commercial_ev_charger": {"panel": [400, 500], "charger": [700, 300]},
    }[key]
    return {
        "scale_ft_per_in": scale, "markers": markers, "route": [[550, 500]],
        "buildings": [[[350, 350], [650, 350], [650, 650], [350, 650]]], "primary_building": 0,
        "lot": [[250, 250], [750, 250], [750, 750], [250, 750]], "parcel_number": "482-110-22-00",
        "aerial_base64": base64.b64encode(buffer.getvalue()).decode(), "credits": ["Credit"],
    }


def _page_sizes(pdf: bytes, count: int) -> list[tuple[int, int]]:
    document = pypdfium2.PdfDocument(pdf)
    try:
        return [(round(page.get_width()), round(page.get_height())) for page in list(document)[:count]]
    finally:
        document.close()


@pytest.mark.parametrize("size", ["letter", "tabloid"])
@pytest.mark.parametrize("key", ALL)
def test_every_packet_page_is_drawn_at_the_sheet_size(key, size):
    result = build(key, {**sample(key), "sheet_size": size})
    assert result.body["sheet_size"] == size
    count = len(packet_pages(result.pdf))
    assert count == len(result.body["documents"]), "one page per document, nothing spills over"
    assert set(_page_sizes(result.pdf, count)) == {SIZES[size]}


def test_attached_data_sheets_sit_on_the_packet_sheet_without_stretching():
    payload = {**sample("ev_charger"), "charger_model": "Tesla Wall Connector", "sheet_size": "tabloid"}
    result = build("ev_charger", payload)
    count = len(packet_pages(result.pdf))
    document = pypdfium2.PdfDocument(result.pdf)
    try:
        sizes = [(round(p.get_width()), round(p.get_height())) for p in document]
    finally:
        document.close()
    assert len(sizes) > count
    assert set(sizes) == {SIZES["tabloid"]}, "one sheet size for the whole PDF"
    # Placed at 100% or smaller, never enlarged: the page's drawn content fits inside the original size.
    from pypdf import PdfReader
    from io import BytesIO
    from permit_packets.core.equipment import attachment_span
    after, attached = attachment_span(result.pdf)
    page = PdfReader(BytesIO(result.pdf)).pages[after]
    assert page.mediabox.width == SIZES["tabloid"][0]


def test_the_request_overrides_the_city_default(monkeypatch):
    mesa_like = Jurisdiction(key="x", name="X", state="AZ", known=True, sheet_size="tabloid")
    assert resolve_sheet(None, mesa_like) is TABLOID
    assert resolve_sheet("letter", mesa_like) is LETTER
    assert resolve_sheet("tabloid", ORO_VALLEY) is TABLOID
    assert resolve_sheet(None, ORO_VALLEY) is LETTER


def test_a_city_that_wants_tabloid_gets_it_by_default(monkeypatch):
    from permit_packets.jurisdictions import KNOWN
    import dataclasses

    payload = {**sample("subpanel")}
    payload.pop("sheet_size", None)
    jurisdiction = KNOWN[(payload.get("city", "oro valley").lower(), payload.get("state", "AZ"))] \
        if payload.get("city") else ORO_VALLEY
    monkeypatch.setitem(KNOWN, (jurisdiction.name.lower(), jurisdiction.state),
                        dataclasses.replace(jurisdiction, sheet_size="tabloid"))
    result = build("subpanel", {**payload, "jurisdiction_key": jurisdiction.key,
                                "city": jurisdiction.name, "state": jurisdiction.state})
    assert result.body["sheet_size"] == "tabloid"


def _scale_bar_and_plan(pdf: bytes, page_index: int):
    """(bar length in points, plan square side in points) measured from the page's drawing."""
    document = pypdfium2.PdfDocument(pdf)
    try:
        page = document[page_index]
        text = page.get_textpage().get_text_bounded()
        paths = [obj.get_bounds() for obj in page.get_objects() if obj.type == pypdfium2.raw.FPDF_PAGEOBJ_PATH]
    finally:
        document.close()
    stated = int(re.search(r"1 in = (\d+) ft", text).group(1))
    halves = [(l, b, r, t) for l, b, r, t in paths if 3.5 <= t - b <= 5 and 30 <= r - l <= 60]
    bar = max(r for _, _, r, _ in halves) - min(l for l, _, _, _ in halves)
    plan = max((r - l for l, b, r, t in paths if abs((r - l) - (t - b)) < 1 and 400 < r - l < 700), default=None)
    return stated, bar, plan, text


@pytest.mark.parametrize("size", ["letter", "tabloid"])
@pytest.mark.parametrize("key", ALL)
def test_the_scale_bar_is_as_long_as_the_stated_scale_says(key, size):
    scale = 30
    payload = {**sample(key), "plan": _plan(key, scale), "sheet_size": size}
    result = build(key, payload)
    stated, bar, side, text = _scale_bar_and_plan(result.pdf, 2)
    assert f"Scale 1 in = {stated} ft when printed at 100%" in text
    # The bar is labelled with the feet one printed inch covers, so it must be one inch long.
    assert bar == pytest.approx(72, abs=1.5), f"scale bar is {bar:.1f} pt"
    # And the plan itself must cover exactly the ground the request's scale was made for.
    extent_ft = scale * PLAN_WIDTH_IN
    assert side is not None
    assert side / 72 * stated == pytest.approx(extent_ft, rel=0.01)
    if size == "letter":
        assert stated == scale and side == pytest.approx(7 * 72, abs=3)
    else:
        assert stated < scale and side > 7 * 72, "tabloid prints the plan larger"


def test_the_cover_and_the_build_steps_state_the_printed_scale():
    payload = {**sample("ev_charger"), "plan": _plan("ev_charger", 30), "sheet_size": "tabloid"}
    result = build("ev_charger", payload)
    stated = int(re.search(r"1 in = (\d+) ft", packet_pages(result.pdf)[2]).group(1))
    assert f"1 in = {stated} ft" in packet_pages(result.pdf)[0]
    assert any(f"1 in = {stated} ft" in step for step in result.body["build_steps"])
