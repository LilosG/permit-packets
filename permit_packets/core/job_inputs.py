"""Turning a validated request into what a job needs: the sample-mode address and the plan."""
from __future__ import annotations

from fastapi import HTTPException, status

from permit_packets.core.layout import resolve_sheet, use_sheet
from permit_packets.core.pdf_base import blank_sheet_needed, use_blank_area
from permit_packets.core.property_plan import PropertyPlan
from permit_packets.core.schemas import JobRequestBase
from permit_packets.jurisdictions import jurisdiction_by_key

SAMPLE_PARCEL = "000-00-000-000"


def sample_address(request: JobRequestBase) -> str:
    """The address a sample-mode packet shows in place of the real one."""
    place = ", ".join(part for part in (request.city, request.state) if part)
    return f"123 Sample St, {place}" if place else "123 Sample St"


def property_plan(request: JobRequestBase, route_between: tuple[str, str] | None) -> PropertyPlan | None:
    """The request's plan as a PropertyPlan. Sample mode swaps the parcel number for a placeholder."""
    plan = request.plan
    if plan is None:
        return None
    try:
        aerial = plan.aerial_bytes()
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    city = jurisdiction_by_key(request.jurisdiction_key, request.city, request.state)
    limit = city.max_plan_scale_ft_per_in
    if limit and plan.scale_ft_per_in > limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{city.name} needs the site plan at 1 in = {limit} ft or closer (it prints at 1/8 in = 1 ft). "
            "Zoom the plan in and build again.")
    return PropertyPlan(
        scale_ft_per_in=plan.scale_ft_per_in, markers=plan.markers, route=plan.route,
        route_between=route_between,
        buildings=plan.buildings, primary_building=plan.primary_building, lot=plan.lot,
        parcel_number=SAMPLE_PARCEL if request.sample_mode else plan.parcel_number,
        aerial_jpeg=aerial, credits=plan.credits,
    )


def display_number(value: float) -> str:
    """A number the way the page prints it: 170.0 is 170."""
    return str(int(value)) if value == int(value) else str(value)


def build_on_sheet(request: JobRequestBase, build):
    """Run a job's build on the sheet the request asked for, else the city's: letter or tabloid.

    Every page is drawn natively at that size. The result's body says which sheet it is."""
    from permit_packets.job_types import PacketResult

    city = jurisdiction_by_key(request.jurisdiction_key, request.city, request.state)
    sheet = resolve_sheet(request.sheet_size, city)
    if sheet.key == "ansi_d":
        # Laid out on letter, then the drawing sheets go onto 22 x 34 in sheets with the city's blank
        # area on the cover, so no separate blank sheet is added.
        from permit_packets.core.drawing_sets import drawing_set
        from permit_packets.core.pdf_base import collect_page_titles

        with use_sheet(sheet), use_blank_area(None), collect_page_titles() as titles:
            result = build(request)
        pdf = drawing_set(result.pdf, titles, city.title_sheet_blank_area_in)
        return PacketResult(pdf=pdf, body={**result.body, "sheet_size": sheet.key})
    with use_sheet(sheet), use_blank_area(city.title_sheet_blank_area_in):
        result = build(request)
        body = {**result.body, "sheet_size": sheet.key}
        if blank_sheet_needed():
            documents = body["documents"]
            body["documents"] = [*documents, {"file_stem": f"{len(documents) + 1:02d}-reserved-for-dbi",
                                              "title": "Reserved for DBI"}]
    return PacketResult(pdf=result.pdf, body=body)
