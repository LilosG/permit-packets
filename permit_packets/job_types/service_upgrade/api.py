"""Panel / service upgrade: from a validated request to a packet and the JSON the page shows."""
from __future__ import annotations

from pydantic import BaseModel

from permit_packets.core.panel_schedule import existing_circuits
from permit_packets.core.conductors import wire_label
from permit_packets.core.job_inputs import build_on_sheet, display_number, property_plan, sample_address
from permit_packets.core.load_calculation import HomeLoads
from permit_packets.core.site_plan import printed_scale
from permit_packets.core.preview import pdf_page_count
from permit_packets.job_types import Document, PacketResult
from permit_packets.job_types.service_upgrade.calc import (
    FedPanel,
    MATERIAL_ABBREVIATIONS,
    PlannedLoadLine,
    ServiceJob,
    ServicePacket,
    build_service_packet,
)
from permit_packets.job_types.service_upgrade.pdf import (
    checklist_rows,
    application_fields,
    render_service_packet_pdf,
    scope_of_work,
)
from permit_packets.job_types.service_upgrade.ev_addon import EvAddOn
from permit_packets.job_types.service_upgrade.schema import ServiceUpgradeRequest
from permit_packets.jurisdictions import jurisdiction_by_key, jurisdiction_json

JOB_TYPE_KEY = "service_upgrade"
FEATURE_PAGE = 2  # the site plan, shown large in the preview
DOCUMENTS = (
    Document("01-checklist-and-checks", "Checklist and checks"),
    Document("02-permit-application-data", "Permit data"),
    Document("03-site-plan", "Site plan"),
    Document("04-riser-diagram", "Riser diagram"),
    Document("05-load-calculation", "Load calculation"),
    Document("06-panel-schedule", "Panel schedule"),
    Document("07-utility-service-request", "Utility request"),
    Document("08-equipment-data", "Equipment data"),
    Document("09-pre-submittal-review", "Pre-submittal review"),
)


def to_job(request: ServiceUpgradeRequest) -> ServiceJob:
    fields = request.model_dump(exclude={
        "home", "plan", "city", "state", "jurisdiction_key", "sample_mode", "planned_loads", "electrodes",
        "panels", "ev_charger",
    })
    fields["existing_circuits"] = existing_circuits(fields["existing_circuits"])
    fields.pop("sheet_size", None)  # applied to the finished PDF, not the job
    if request.sample_mode:
        fields["address"] = sample_address(request)
    plan = property_plan(request, ("meter", "panel"))
    if plan is not None and plan.markers["meter"] == plan.markers["panel"]:
        # A meter-main combo is one spot, so there is no route to measure.
        plan = property_plan(request, None)
    return ServiceJob(
        home=HomeLoads(**request.home.model_dump()),
        planned_loads=tuple(PlannedLoadLine(load.label, load.va) for load in request.planned_loads),
        electrodes=tuple(request.electrodes),
        panels=tuple(FedPanel(**panel.model_dump()) for panel in request.panels),
        ev=EvAddOn(**request.ev_charger.model_dump()) if request.ev_charger else None,
        jurisdiction=jurisdiction_by_key(request.jurisdiction_key, request.city, request.state),
        plan=plan,
        **fields,
    )


def _wire(packet: ServicePacket) -> str:
    return f"{wire_label(packet.conductor.size)} {MATERIAL_ABBREVIATIONS[packet.job.material]}"


def _feeder_wire(packet: ServicePacket) -> str:
    feeder = packet.feeders[0]
    return f"2 x {wire_label(feeder.conductor.size)} {MATERIAL_ABBREVIATIONS[packet.job.material]}"


def _summary(packet: ServicePacket) -> list[dict]:
    wire = ({"label": "Feeders", "value": _feeder_wire(packet)} if packet.job.dual
            else {"label": "Service wire", "value": _wire(packet)})
    return [
        {"label": "Calculated load", "value": f"{display_number(round(packet.load.computed_amps, 1))} A"},
        {"label": "New service", "value": f"{packet.job.new_service_amps} A"},
        wire,
        {"label": "GEC", "value": f"#{packet.largest_gec} Cu"},
    ]


def _build_steps(packet: ServicePacket, checklist_items: int, page_count: int) -> list[str]:
    job = packet.job
    site = (
        f"Site plan drawn to scale at 1 in = {printed_scale(job.plan)} ft"
        if job.plan else "Schematic site plan drawn"
    )
    return [
        f"{job.jurisdiction.label} checklist applied, {checklist_items} items",
        f"Load calculation: {display_number(round(packet.load.computed_amps, 1))} A on the new {job.new_service_amps} A service",
        (f"Two 200 A feeders sized: 3 {_feeder_wire(packet)[4:]} each" if job.dual
         else f"Service conductors sized: 3 {_wire(packet)}"),
        *([f"EV charger circuit sized: {packet.ev.circuit.breaker} A, #{packet.ev.circuit.wire.size} Cu"]
          if packet.ev else []),
        "Grounding electrode conductor sized",
        site,
        f"Permit and utility data filled in, {page_count} pages built",
    ]


def _submission_email(packet: ServicePacket) -> dict:
    job = packet.job
    kind = "service upgrade" if job.scope == "upgrade" else "panel replacement"
    if packet.ev:
        kind += " with an EV charger"
    return {
        "subject": f"{kind.capitalize()} permit submittal: {job.address}",
        "body": (
            f"Hello,\n\nAttached is an electrical permit submittal for a residential {kind}, "
            f"{job.existing_service_amps} A to {job.new_service_amps} A.\n\n"
            f"Address: {job.address}\nContractor: {job.contractor}, license {job.license_number}\n\n"
            f"Please let me know if anything else is needed.\n\nThank you,\n{job.contractor}"
        ),
    }


def _build_response(request: BaseModel) -> PacketResult:
    assert isinstance(request, ServiceUpgradeRequest)
    packet = build_service_packet(to_job(request))
    pdf = render_service_packet_pdf(packet)
    jurisdiction = packet.job.jurisdiction
    conduit = f"{packet.conduit_size} {packet.job.conduit}" if packet.conduit_size else None
    body = {
        "job_type": JOB_TYPE_KEY,
        "ready": packet.ready,
        "computed_amps": round(packet.load.computed_amps, 1),
        "new_service_amps": packet.job.new_service_amps,
        "service_conductor": _wire(packet),
        "conduit": conduit,
        "gec": {electrode: f"#{size} Cu" for electrode, size in packet.gecs.items()},
        "checks": [
            {"name": check.name, "result": check.result, "passed": check.passed}
            for check in packet.checks
        ],
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
