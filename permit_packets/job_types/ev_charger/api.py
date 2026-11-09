"""EV charger: from a validated request to a packet and the JSON the page shows."""
from __future__ import annotations

from pydantic import BaseModel

from permit_packets.core.job_inputs import display_number, property_plan, sample_address
from permit_packets.core.load_calculation import HomeLoads
from permit_packets.core.preview import pdf_page_count
from permit_packets.job_types import Document, PacketResult
from permit_packets.job_types.ev_charger.calc import EvJob, EvPacket, build_ev_packet
from permit_packets.job_types.ev_charger.pdf import application_fields, render_ev_packet_pdf, scope_of_work
from permit_packets.job_types.ev_charger.schema import EvChargerRequest
from permit_packets.jurisdictions import jurisdiction_by_key, jurisdiction_json

JOB_TYPE_KEY = "ev_charger"
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


def to_job(request: EvChargerRequest) -> EvJob:
    fields = request.model_dump(exclude={"home", "plan", "city", "state", "jurisdiction_key", "sample_mode"})
    if request.sample_mode:
        fields["address"] = sample_address(request)
    return EvJob(
        home=HomeLoads(**request.home.model_dump()),
        jurisdiction=jurisdiction_by_key(request.jurisdiction_key, request.city, request.state),
        plan=property_plan(request, ("panel", "charger")),
        **fields,
    )


def _summary(packet: EvPacket) -> list[dict]:
    computed = round(packet.load.computed_amps, 1)
    spare = round(packet.load.spare_amps, 1)
    circuit = packet.circuit
    return [
        {"label": "Service load", "value": f"{display_number(computed)} A"},
        {"label": "Over capacity by", "value": f"{display_number(-spare)} A"} if spare < 0
        else {"label": "Spare capacity", "value": f"{display_number(spare)} A"},
        {"label": "Breaker", "value": f"{circuit.breaker} A"},
        {"label": "Wire", "value": f"#{circuit.wire.size} AWG"},
    ]


def _build_steps(packet: EvPacket, checklist_items: int, page_count: int) -> list[str]:
    job = packet.job
    circuit = packet.circuit
    site = (
        f"Site plan drawn to scale at 1 in = {job.plan.scale_ft_per_in} ft"
        if job.plan else "Schematic site plan drawn"
    )
    return [
        f"{job.jurisdiction.label} checklist applied, {checklist_items} items",
        f"Load calculation: {display_number(round(packet.load.computed_amps, 1))} A on a {job.service_amps} A service",
        f"Circuit sized: {circuit.breaker} A breaker, #{circuit.wire.size} AWG Cu",
        site,
        f"Permit data filled in, {page_count} pages built",
    ]


def _submission_email(packet: EvPacket) -> dict:
    job = packet.job
    return {
        "subject": f"EV charger permit submittal: {job.address}",
        "body": (
            "Hello,\n\nAttached is an electrical permit submittal for a residential EV charger.\n\n"
            f"Address: {job.address}\nContractor: {job.contractor}, license {job.license_number}\n\n"
            f"Please let me know if anything else is needed.\n\nThank you,\n{job.contractor}"
        ),
    }


def build_response(request: BaseModel) -> PacketResult:
    assert isinstance(request, EvChargerRequest)
    packet = build_ev_packet(to_job(request))
    pdf = render_ev_packet_pdf(packet)
    circuit = packet.circuit
    jurisdiction = packet.job.jurisdiction
    body = {
        "job_type": JOB_TYPE_KEY,
        "ready": packet.ready,
        "computed_amps": round(packet.load.computed_amps, 1),
        "total_va": round(packet.load.total_va),
        "spare_amps": round(packet.load.spare_amps, 1),
        "breaker": circuit.breaker,
        "wire": f"#{circuit.wire.size} AWG Cu",
        "ground": f"#{circuit.ground} AWG Cu",
        "voltage_drop_percent": round(circuit.voltage_drop_percent, 1),
        "underground_conduit": packet.underground_conduit,
        "interior_conduit": packet.interior_conduit,
        "disconnect_amps": packet.disconnect_amps,
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
