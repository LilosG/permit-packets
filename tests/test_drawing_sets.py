"""San Francisco's 22 x 34 in drawing set (DBI Information Sheet E-01 and DBI's PDF rules): sheet sizes,
1/8 in minimum text, the 1/8 in = 1 ft site plan, the 2 x 2 in stamp area on every sheet and the
8.5 x 11 in agency area on the cover."""
from __future__ import annotations

import pypdfium2
import pypdfium2.raw as raw
import pytest
from fastapi import HTTPException

from permit_packets.core.drawing_sets import DRAWING_TITLES, STAMP_SIDE, STAMP_X, STAMP_Y
from permit_packets.jurisdictions import jurisdiction_by_key
from tests.packet_helpers import build, complete_inputs, page_texts

SF = jurisdiction_by_key("san-francisco-ca")
KEYS = ("ev_charger", "service_upgrade", "subpanel", "appliance_circuit")
D = (1584, 2448)
FLAT_CAPITALS = "EHIKLMNTFZ"  # flat top and bottom: the glyph box is the capital height


@pytest.fixture(scope="module", params=KEYS)
def packet(request):
    result = build(request.param, complete_inputs(request.param, SF))
    document = pypdfium2.PdfDocument(result.pdf)
    yield request.param, result, document
    document.close()


def _d_pages(document):
    return [page for page in document if (round(page.get_width()), round(page.get_height())) == D]


def test_drawings_are_22_x_34_and_forms_stay_letter(packet):
    _, result, document = packet
    texts = page_texts(result.pdf)
    for page, text in zip(document, texts):
        size = (round(page.get_width()), round(page.get_height()))
        drawing = any(f"SHEET TITLE\r\n{title}" in text or f"SHEET TITLE {title}" in text for title in DRAWING_TITLES)
        if drawing:
            assert size == D, text[:80]
    assert (round(document[0].get_width()), round(document[0].get_height())) == D
    assert len(_d_pages(document)) >= 5


def test_every_drawing_sheet_prints_capitals_at_least_one_eighth_inch(packet):
    _, _, document = packet
    for number, page in enumerate(_d_pages(document), 1):
        text = page.get_textpage()
        heights = [(text.get_charbox(i)[3] - text.get_charbox(i)[1]) / 72 for i in range(text.count_chars())
                   if chr(raw.FPDFText_GetUnicode(text, i)) in FLAT_CAPITALS]
        assert heights and min(heights) >= 0.125, f"drawing sheet {number}: {min(heights):.3f} in"


def test_every_drawing_sheet_has_the_2_inch_stamp_area_in_the_same_spot(packet):
    _, _, document = packet
    for page in _d_pages(document):
        boxes = [o.get_bounds() for o in page.get_objects() if o.type == raw.FPDF_PAGEOBJ_PATH]
        assert any(abs(l - STAMP_X) < 2 and abs(b - STAMP_Y) < 2 and abs(r - l - STAMP_SIDE) < 2.5
                   and abs(t - b - STAMP_SIDE) < 2.5 for l, b, r, t in boxes)
        assert "DBI stamp" in page.get_textpage().get_text_bounded()


def test_the_cover_carries_the_8_5_x_11_agency_area_at_true_size(packet):
    _, _, document = packet
    cover = document[0]
    boxes = [o.get_bounds() for o in cover.get_objects() if o.type == raw.FPDF_PAGEOBJ_PATH]
    assert any(abs(r - l - 612) < 2.5 and abs(t - b - 792) < 2.5 for l, b, r, t in boxes)
    assert "Empty 8.5 in x 11 in area" in cover.get_textpage().get_text_bounded()


def test_the_site_plan_prints_at_one_eighth_inch_to_the_foot(packet):
    _, result, _ = packet
    text = " ".join(page_texts(result.pdf))
    assert "1 in = 8 ft (1/8 in = 1 ft)" in text


def test_the_flags_move_to_the_review_page(packet):
    key, result, _ = packet
    texts = page_texts(result.pdf)
    assert "items for the electrician are on the Pre-Submittal Review page" in texts[0]
    review = texts[-1]
    assert "Flagged for your review" in review
    assert "Check the existing loads against the home" in review


def test_a_plan_smaller_than_one_eighth_inch_to_the_foot_is_refused():
    payload = complete_inputs("service_upgrade", SF)
    payload["plan"]["scale_ft_per_in"] = 30
    with pytest.raises(HTTPException) as refused:
        build("service_upgrade", payload)
    assert refused.value.status_code == 422 and "1 in = 20 ft" in refused.value.detail


def test_other_cities_stay_on_their_sheet():
    result = build("ev_charger", complete_inputs("ev_charger", jurisdiction_by_key("nashville-tn")))
    document = pypdfium2.PdfDocument(result.pdf)
    try:
        assert {(round(p.get_width()), round(p.get_height())) for p in (document[i] for i in range(3))} == {(612, 792)}
    finally:
        document.close()
