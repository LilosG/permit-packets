"""240 V appliance circuit: from a validated request to a packet and the JSON the page shows."""
from __future__ import annotations

from fastapi import HTTPException, status
from pydantic import BaseModel

from permit_packets.core.conductors import wire_label
from permit_packets.core.job_inputs import display_number, property_plan, sample_address
from permit_packets.core.load_calculation import HomeLoads
from permit_packets.core.preview import pdf_page_count
from permit_packets.job_types import Document, PacketResult
from permit_packets.job_types.appliance_circuit.calc import (
    APPLIANCE_LABELS,
    ApplianceJob,
    AppliancePacket,
    build_appliance_packet,
    sentence_case,
)
from permit_packets.job_types.appliance_circuit.pdf import (
    application_fields,
    render_appliance_packet_pdf,
    scope_of_work,
)
from permit_packets.job_types.appliance_circuit.schema import ApplianceCircuitRequest
from permit_packets.jurisdictions import jurisdiction_by_key, jurisdiction_json

JOB_TYPE_KEY = "appliance_circuit"
FEATURE_PAGE = 2  # the site plan, shown large in the preview
DOCUMENTS = (
    Document("01-checklist-and-checks", "Checklist and checks"),
    Document("02-permit-application-data", "Permit data"),
    Document("03-site-plan", "Site plan"),
    Document("04-one-line-diagram", "One-line diagram"),
    Document("05-load-calculation", "Load calculation"),
    Document("06-equipment-data", "Equipment data"),
    Document("07-pre-submittal-review", "Pre-submittal review"),
)
HAS_NEUTRAL_BY_DEFAULT = ("hot_tub", "other")


def to_job(request: ApplianceCircuitRequest) -> ApplianceJob:
    fields = request.model_dump(exclude={
        "home", "plan", "city", "state", "jurisdiction_key", "sample_mode", "needs_neutral",
    })
    if request.sample_mode:
        fields["address"] = sample_address(request)
    needs_neutral = (
        request.appliance in HAS_NEUTRAL_BY_DEFAULT if request.needs_neutral is None else request.needs_neutral
    )
    return ApplianceJob(
        home=HomeLoads(**request.home.model_dump()),
        jurisdiction=jurisdiction_by_key(request.jurisdiction_key, request.city, request.state),
        plan=property_plan(request, ("panel", "appliance")),
        needs_neutral=needs_neutral,
        **fields,
    )


def _wire(packet: AppliancePacket) -> str:
    return wire_label(packet.branch.wire.size)


def _service_load(packet: AppliancePacket) -> str:
    return display_number(round(packet.load.computed_amps, 1))


def _drop_percent(packet: AppliancePacket) -> str:
    return display_number(round(packet.branch.vd_percent, 1))


def _summary(packet: AppliancePacket) -> list[dict]:
    return [
        {"label": "Service load", "value": f"{_service_load(packet)} A"},
        {"label": "Breaker", "value": f"{packet.breaker} A"},
        {"label": "Wire", "value": _wire(packet)},
        {"label": "Voltage drop", "value": f"{_drop_percent(packet)}%"},
    ]


def _build_steps(packet: AppliancePacket, checklist_items: int, page_count: int) -> list[str]:
    job = packet.job
    site = (
        f"Site plan drawn to scale at 1 in = {job.plan.scale_ft_per_in} ft"
        if job.plan else "Schematic site plan drawn"
    )
    return [
        f"{job.jurisdiction.label} checklist applied, {checklist_items} items",
        f"Load calculation: {_service_load(packet)} A on a {job.service_amps} A service",
        f"Circuit sized: {packet.breaker} A breaker, {_wire(packet)} Cu",
        f"Voltage drop: {_drop_percent(packet)}% over {job.run_ft} ft",
        site,
        f"Permit data filled in, {page_count} pages built",
    ]


def _submission_email(packet: AppliancePacket) -> dict:
    job = packet.job
    appliance = APPLIANCE_LABELS[job.appliance]
    return {
        "subject": f"{sentence_case(appliance)} circuit permit submittal: {job.address}",
        "body": (
            f"Hello,\n\nAttached is an electrical permit submittal for a residential {appliance} circuit, "
            f"a {packet.breaker} A, 240 V branch circuit.\n\n"
            f"Address: {job.address}\nContractor: {job.contractor}, license {job.license_number}\n\n"
            f"Please let me know if anything else is needed.\n\nThank you,\n{job.contractor}"
        ),
    }


def build_response(request: BaseModel) -> PacketResult:
    assert isinstance(request, ApplianceCircuitRequest)
    try:
        packet = build_appliance_packet(to_job(request))
    except ValueError as error:
        # A load too big for the wire and breaker tables is a bad request, not a server fault.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    pdf = render_appliance_packet_pdf(packet)
    jurisdiction = packet.job.jurisdiction
    body = {
        "job_type": JOB_TYPE_KEY,
        "ready": packet.ready,
        "computed_amps": round(packet.load.computed_amps, 1),
        "service_amps": packet.job.service_amps,
        "load_amps": round(packet.load_amps, 1),
        "breaker_amps": packet.breaker,
        "conductor": f"{_wire(packet)} Cu",
        "egc": f"{wire_label(packet.branch.egc)} Cu",
        "conduit": "cable" if packet.conduit_size is None else f"{packet.conduit_size} {packet.job.wiring}",
        "voltage_drop_percent": round(packet.branch.vd_percent, 1),
        "checks": [
            {"name": check.name, "result": check.result, "passed": check.passed}
            for check in packet.checks
        ],
        "flags": packet.flags,
        "jurisdiction": jurisdiction_json(jurisdiction, JOB_TYPE_KEY),
        "address": packet.job.address,
        "fields": [
            *({"label": label, "value": value} for label, value in application_fields(packet)),
            {"label": "Scope of work", "value": scope_of_work(packet)},
        ],
        "documents": [{"file_stem": d.file_stem, "title": d.title} for d in DOCUMENTS],
        "feature_page": FEATURE_PAGE,
        "summary": _summary(packet),
        "build_steps": _build_steps(
            packet, len(jurisdiction.checklist_for(JOB_TYPE_KEY).items), pdf_page_count(pdf)),
        "submission_email": _submission_email(packet),
    }
    return PacketResult(pdf=pdf, body=body)
