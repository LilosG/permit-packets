"""Subpanel / feeder: from a validated request to a packet and the JSON the page shows."""
from __future__ import annotations

from pydantic import BaseModel

from permit_packets.core.conductors import wire_label
from permit_packets.core.job_inputs import display_number, property_plan, sample_address
from permit_packets.core.load_calculation import HomeLoads
from permit_packets.core.preview import pdf_page_count
from permit_packets.job_types import Document, PacketResult
from permit_packets.job_types.subpanel.calc import (
    MATERIAL_ABBREVIATIONS,
    SubpanelJob,
    SubpanelLoadLine,
    SubpanelPacket,
    build_subpanel_packet,
)
from permit_packets.job_types.subpanel.pdf import (
    application_fields,
    render_subpanel_packet_pdf,
    scope_of_work,
)
from permit_packets.job_types.subpanel.schema import SubpanelRequest
from permit_packets.jurisdictions import jurisdiction_by_key, jurisdiction_json

JOB_TYPE_KEY = "subpanel"
FEATURE_PAGE = 2  # the site plan, shown large in the preview
DOCUMENTS = (
    Document("01-checklist-and-checks", "Checklist and checks"),
    Document("02-permit-application-data", "Permit data"),
    Document("03-site-plan", "Site plan"),
    Document("04-one-line-diagram", "One-line diagram"),
    Document("05-feeder-schedule", "Feeder schedule"),
    Document("06-load-calculation", "Load calculation"),
    Document("07-equipment-data", "Equipment data"),
    Document("08-pre-submittal-review", "Pre-submittal review"),
)


def to_job(request: SubpanelRequest) -> SubpanelJob:
    fields = request.model_dump(exclude={
        "home", "plan", "city", "state", "jurisdiction_key", "sample_mode", "loads",
    })
    if request.sample_mode:
        fields["address"] = sample_address(request)
    return SubpanelJob(
        home=HomeLoads(**request.home.model_dump()),
        loads=tuple(SubpanelLoadLine(load.label, load.va) for load in request.loads),
        jurisdiction=jurisdiction_by_key(request.jurisdiction_key, request.city, request.state),
        plan=property_plan(request, ("panel", "subpanel")),
        **fields,
    )


def _wire(packet: SubpanelPacket) -> str:
    return f"{wire_label(packet.feeder.conductor.size)} {MATERIAL_ABBREVIATIONS[packet.job.material]}"


def _service_load(packet: SubpanelPacket) -> str:
    return display_number(round(packet.load.computed_amps, 1))


def _drop_percent(packet: SubpanelPacket) -> str:
    return display_number(round(packet.feeder.vd_percent, 1))


def _summary(packet: SubpanelPacket) -> list[dict]:
    return [
        {"label": "Service load", "value": f"{_service_load(packet)} A"},
        {"label": "Feeder", "value": _wire(packet)},
        {"label": "Breaker", "value": f"{packet.job.feeder_breaker_amps} A"},
        {"label": "Voltage drop", "value": f"{_drop_percent(packet)}%"},
    ]


def _build_steps(packet: SubpanelPacket, checklist_items: int, page_count: int) -> list[str]:
    job = packet.job
    site = (
        f"Site plan drawn to scale at 1 in = {job.plan.scale_ft_per_in} ft"
        if job.plan else "Schematic site plan drawn"
    )
    return [
        f"{job.jurisdiction.label} checklist applied, {checklist_items} items",
        f"Load calculation: {_service_load(packet)} A on a {job.service_amps} A service",
        f"Feeder sized: 2 {_wire(packet)}, {wire_label(packet.feeder.egc)} EGC",
        f"Voltage drop: {_drop_percent(packet)}% over {job.run_ft} ft",
        site,
        f"Permit data filled in, {page_count} pages built",
    ]


def _submission_email(packet: SubpanelPacket) -> dict:
    job = packet.job
    return {
        "subject": f"Subpanel permit submittal: {job.address}",
        "body": (
            f"Hello,\n\nAttached is an electrical permit submittal for a residential subpanel, "
            f"{job.subpanel_amps} A, fed by a {job.feeder_breaker_amps} A breaker.\n\n"
            f"Address: {job.address}\nContractor: {job.contractor}, license {job.license_number}\n\n"
            f"Please let me know if anything else is needed.\n\nThank you,\n{job.contractor}"
        ),
    }


def build_response(request: BaseModel) -> PacketResult:
    assert isinstance(request, SubpanelRequest)
    packet = build_subpanel_packet(to_job(request))
    pdf = render_subpanel_packet_pdf(packet)
    jurisdiction = packet.job.jurisdiction
    body = {
        "job_type": JOB_TYPE_KEY,
        "ready": packet.ready,
        "computed_amps": round(packet.load.computed_amps, 1),
        "service_amps": packet.job.service_amps,
        "feeder_conductor": _wire(packet),
        "feeder_egc": f"{wire_label(packet.feeder.egc)} {MATERIAL_ABBREVIATIONS[packet.job.material]}",
        "conduit": f"{packet.conduit_size} {packet.job.conduit}",
        "voltage_drop_percent": round(packet.feeder.vd_percent, 1),
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
