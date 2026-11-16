"""Commercial subpanel / feeder: from a validated request to a packet and the JSON the page shows."""
from __future__ import annotations

from pydantic import BaseModel

from permit_packets.core.commercial import SYSTEMS
from permit_packets.core.conductors import wire_label
from permit_packets.core.job_inputs import build_on_sheet, display_number, property_plan, sample_address
from permit_packets.core.panel_schedule import existing_circuits
from permit_packets.core.preview import pdf_page_count
from permit_packets.core.site_plan import printed_scale
from permit_packets.job_types import Document, PacketResult
from permit_packets.job_types.commercial_subpanel.calc import (
    MATERIAL_ABBREVIATIONS,
    CommercialSubpanelJob,
    CommercialSubpanelPacket,
    SubpanelLoadLine,
    build_commercial_subpanel_packet,
)
from permit_packets.job_types.commercial_subpanel.pdf import (
    application_fields,
    checklist_rows,
    render_commercial_subpanel_packet_pdf,
    scope_of_work,
)
from permit_packets.job_types.commercial_subpanel.schema import CommercialSubpanelRequest
from permit_packets.jurisdictions import jurisdiction_by_key, jurisdiction_json

JOB_TYPE_KEY = "commercial_subpanel"
FEATURE_PAGE = 2  # the site plan, shown large in the preview
DOCUMENTS = (
    Document("01-checklist-and-checks", "Checklist and checks"),
    Document("02-permit-application-data", "Permit data"),
    Document("03-site-plan", "Site plan"),
    Document("04-one-line-diagram", "One-line diagram"),
    Document("05-feeder-schedule", "Feeder schedule"),
    Document("06-load-calculation", "Load calculation"),
    Document("07-panel-schedule", "Panel schedule"),
    Document("08-equipment-data", "Equipment data"),
    Document("09-pre-submittal-review", "Pre-submittal review"),
)


def to_job(request: CommercialSubpanelRequest) -> CommercialSubpanelJob:
    fields = request.model_dump(exclude={
        "plan", "city", "state", "jurisdiction_key", "sample_mode", "loads", "system",
    })
    fields["existing_circuits"] = existing_circuits(fields["existing_circuits"])
    fields.pop("sheet_size", None)  # applied to the finished PDF, not the job
    if request.sample_mode:
        fields["address"] = sample_address(request)
    return CommercialSubpanelJob(
        system=SYSTEMS[request.system],
        loads=tuple(SubpanelLoadLine(load.label, load.kva, load.continuous) for load in request.loads),
        jurisdiction=jurisdiction_by_key(request.jurisdiction_key, request.city, request.state),
        plan=property_plan(request, ("panel", "subpanel")),
        **fields,
    )


def _wire(packet: CommercialSubpanelPacket) -> str:
    return f"{wire_label(packet.feeder.conductor.size)} {MATERIAL_ABBREVIATIONS[packet.job.material]}"


def _service_load(packet: CommercialSubpanelPacket) -> str:
    return display_number(round(packet.load.amps, 1))


def _drop_percent(packet: CommercialSubpanelPacket) -> str:
    return display_number(round(packet.feeder.vd_percent, 1))


def _summary(packet: CommercialSubpanelPacket) -> list[dict]:
    return [
        {"label": "Service load", "value": f"{_service_load(packet)} A"},
        {"label": "Feeder", "value": _wire(packet)},
        {"label": "Breaker", "value": f"{packet.job.feeder_breaker_amps} A, {packet.feeder.poles}-pole"},
        {"label": "Voltage drop", "value": f"{_drop_percent(packet)}%"},
    ]


def _build_steps(packet: CommercialSubpanelPacket, checklist_items: int, page_count: int) -> list[str]:
    job = packet.job
    site = (f"Site plan drawn to scale at 1 in = {printed_scale(job.plan)} ft" if job.plan
            else "Schematic site plan drawn")
    return [
        f"{job.jurisdiction.label} checklist applied, {checklist_items} items",
        f"Service load: {_service_load(packet)} A on a {job.service_amps} A, {job.system.volts} V service",
        f"Feeder sized: {job.system.hots} {_wire(packet)}, {wire_label(packet.feeder.egc)} EGC",
        f"Voltage drop: {_drop_percent(packet)}% over {job.run_ft} ft",
        site,
        f"Permit data filled in, {page_count} pages built",
    ]


def _submission_email(packet: CommercialSubpanelPacket) -> dict:
    job = packet.job
    return {
        "subject": f"Commercial subpanel permit submittal: {job.address}",
        "body": (
            f"Hello,\n\nAttached is an electrical permit submittal for a commercial subpanel, "
            f"{job.subpanel_amps} A, {job.system.label}, fed by a {job.feeder_breaker_amps} A breaker.\n\n"
            f"Address: {job.address}\nContractor: {job.contractor}, license {job.license_number}\n\n"
            f"Please let me know if anything else is needed.\n\nThank you,\n{job.contractor}"
        ),
    }


def _build_response(request: BaseModel) -> PacketResult:
    assert isinstance(request, CommercialSubpanelRequest)
    packet = build_commercial_subpanel_packet(to_job(request))
    pdf = render_commercial_subpanel_packet_pdf(packet)
    jurisdiction = packet.job.jurisdiction
    body = {
        "job_type": JOB_TYPE_KEY,
        "ready": packet.ready,
        "computed_amps": round(packet.load.amps, 1),
        "service_amps": packet.job.service_amps,
        "feeder_conductor": _wire(packet),
        "feeder_egc": f"{wire_label(packet.feeder.egc)} {MATERIAL_ABBREVIATIONS[packet.job.material]}",
        "conduit": f"{packet.conduit_size} {packet.job.conduit}",
        "voltage_drop_percent": round(packet.feeder.vd_percent, 1),
        "checks": [{"name": c.name, "result": c.result, "passed": c.passed} for c in packet.checks],
        "flags": packet.flags,
        "checklist_status": [
            {"item": item, "where": where, "status": status} for item, where, status in checklist_rows(packet)
        ],
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


def build_response(request: BaseModel) -> PacketResult:
    return build_on_sheet(request, _build_response)
