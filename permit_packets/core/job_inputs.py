"""Turning a validated request into what a job needs: the sample-mode address and the plan."""
from __future__ import annotations

from fastapi import HTTPException, status

from permit_packets.core.property_plan import PropertyPlan
from permit_packets.core.schemas import JobRequestBase

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
