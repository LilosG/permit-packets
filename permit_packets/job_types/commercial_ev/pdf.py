"""Render a commercial Level 2 EV charger permit packet as an 8-page draft PDF.

The checklist comes from the job's jurisdiction. The site plan is the property to scale when there's a
plan, and a labeled schematic when there isn't.
"""
from __future__ import annotations

from reportlab.lib.units import inch
from reportlab.platypus import Spacer

from permit_packets.core.commercial_pdf import DEGREE, OneLineFlow, SchematicSite, phase_text, service_load_page
from permit_packets.core.conductors import wire_label
from permit_packets.core.equipment import attach_data_sheets, find_equipment
from permit_packets.core.panel_data import checklist_row as panel_row, one_line_data, panel_header
from permit_packets.core.panel_schedule import (
    PANEL_SCHEDULE_ITEM, ScheduleRow, existing_rows, panel_schedule_page, panel_schedule_row,
)
from permit_packets.core.pdf_base import (
    H1, H2, SMALL, _heads, _p, _table, application_page, build_document, content_w, cover_page,
    diagram, fit_page, GREEN, INK, review_page,
)
from permit_packets.core.site_plan import PlanMarker, printed_scale, site_plan_page
from permit_packets.core.title_block import title_block_for
from permit_packets.job_types.commercial_ev.calc import BURIAL_COVER_TEXT, LOCATION_LABELS, CommercialEvPacket

KEY = "commercial_ev_charger"
SECTION_PAGES = {
    "application": 2, "site_plan": 3, "one_line": 4, "load": 5, "panel_schedule": 6, "equipment": 7, "review": 8,
}
SHEET_TITLES = ["Checklist and Checks", "Permit Application Data", "Site Plan", "One-Line Diagram",
                "Load and Circuit Schedule", "Panel Schedule", "Equipment Data", "Pre-Submittal Review"]


def _charger_label(packet: CommercialEvPacket) -> str:
    job = packet.job
    return f"{job.charger_count} x {job.charger_amps} A Level 2 charger{'s' if job.charger_count > 1 else ''}"


def _checklist_row(packet: CommercialEvPacket, section: str) -> tuple[str, str]:
    job = packet.job
    plan = job.plan
    if section == "application":
        missing = job.jurisdiction.needs_parcel_number and not (plan and plan.parcel_number)
        return ("Page 2: add the parcel number" if missing else "Page 2: fields ready for the city's permit"), (
            "Open" if missing else "Ready")
    if section == "site_plan":
        if plan:
            return f"Page 3: to scale, 1 in = {printed_scale(plan)} ft", "Ready"
        return "Page 3: schematic only, replace it", "Open"
    if section == "equipment":
        if find_equipment(job.charger_model, "charger"):
            return f"Page {SECTION_PAGES['equipment']} + manufacturer data sheet", "Ready"
        if job.data_sheet_attached:
            return f"Page {SECTION_PAGES['equipment']} + data sheet attached by the electrician", "Ready"
        return f"Page {SECTION_PAGES['equipment']}: add manufacturer sheets", "Attach"
    if section == "accessibility":
        if job.accessible_spaces is None:
            return "Page 3: enter the accessible space count and show the space on the plan", "Open"
        return f"Page 3: {job.accessible_spaces} accessible space(s) noted, confirm against CBC 11B", "Ready"
    shown = panel_row(job, section, SECTION_PAGES["one_line"], burial=(SECTION_PAGES["load"], BURIAL_COVER_TEXT))
    if shown:
        return shown
    if section not in SECTION_PAGES:
        return "Not in this packet: add it by hand", "Open"
    return f"Page {SECTION_PAGES[section]}", "Ready"


def checklist_rows(packet: CommercialEvPacket) -> list[tuple[str, str, str]]:
    job = packet.job
    rows = [(requirement.item, *_checklist_row(packet, requirement.section))
            for requirement in job.jurisdiction.checklist_for(KEY).items]
    return rows + [(PANEL_SCHEDULE_ITEM, *panel_schedule_row(job, SECTION_PAGES["panel_schedule"]))]


def _cover(packet: CommercialEvPacket) -> list:
    job = packet.job
    jurisdiction = job.jurisdiction
    checklist_cell = (
        f"{jurisdiction.label}\n{jurisdiction.checklist_for(KEY).source_label}"
        if jurisdiction.known_for(KEY)
        else f"{jurisdiction.label}\nGeneral checklist, city rules added in setup"
    )
    parcel = f"\nParcel {job.plan.parcel_number}" if job.plan and job.plan.parcel_number else ""
    use = f"{job.building_use}\n" if job.building_use else ""
    return cover_page(
        title="Commercial EV Charger Permit Packet",
        address=job.address,
        job_cell=f"{use}{_charger_label(packet)}, {job.system.label}{parcel}\nCustomer: {job.customer}",
        contractor_cell=f"{job.contractor}\nLicense {job.license_number}",
        checklist_cell=checklist_cell,
        checklist_rows=checklist_rows(packet),
        checks=[(check.name, check.result, check.passed) for check in packet.checks],
        flags=packet.flags,
        stamp_box_in=job.jurisdiction.stamp_box_in,
    )


def scope_of_work(packet: CommercialEvPacket) -> str:
    job = packet.job
    model = f" ({job.charger_model})" if job.charger_model else ""
    circuit = packet.circuit
    route = f"Trench about {job.trench_ft} ft and run" if job.trench_ft else "Run"
    managed = (f" Limit the chargers to {job.managed_limit_amps} A with a listed energy management system."
               if job.load_management else "")
    disconnect = " Provide a readily accessible disconnect at each charger." if job.disconnect_required else ""
    service_note = ("No service upgrade." if packet.load.fits
                    else "Service capacity must be resolved before submittal.")
    count = job.charger_count
    return (
        f"Install {_charger_label(packet)}{model} at the {LOCATION_LABELS[job.location]}. Add {count} "
        f"{circuit.breaker} A, 2-pole breaker{'s' if count > 1 else ''} to the existing {job.service_amps} A "
        f"main panel. {route} {'a' if count == 1 else 'each'} new circuit up to {job.run_ft} ft, 2 "
        f"{wire_label(circuit.wire.size)} Cu + {wire_label(circuit.ground)} Cu ground, from the panel to "
        f"{'the charger' if count == 1 else 'its charger'}.{disconnect}{managed} {service_note}"
    )


def application_fields(packet: CommercialEvPacket) -> list[tuple[str, str]]:
    job = packet.job
    return [
        ("Project address", job.address),
        ("Parcel number", job.plan.parcel_number if job.plan and job.plan.parcel_number else "Not on file"),
        ("Jurisdiction", job.jurisdiction.label),
        ("Property owner or tenant", job.customer),
        ("Permit type", "Electrical, commercial: EV charging stations"),
        ("Building use", job.building_use or "Add the building use"),
        ("Electrical service", f"{job.system.label}, {job.service_amps} A"),
        ("Chargers", f"{job.charger_count} x {job.charger_model or 'add make and model'}, {job.charger_amps} A, "
                     f"{job.volts} V, {packet.total_charger_kw:.1f} kW total"),
        ("Contractor", job.contractor),
        ("License number", job.license_number),
    ]


def _application(packet: CommercialEvPacket) -> list:
    inspections = [
        ("Rough", "Conduit, wiring, grounding and bonding, before covering"),
        ("Final", "Chargers, breakers, labeling, directory, disconnects and working space on site"),
    ]
    if packet.job.trench_ft:
        inspections.insert(0, ("Underground", "Open trench, conduit and cover, before backfill"))
    return application_page(rows=application_fields(packet), scope=scope_of_work(packet), inspections=inspections)


def _site_plan(packet: CommercialEvPacket) -> list:
    job = packet.job
    plan = job.plan
    spaces = f"{job.charger_count} EV charging space{'s' if job.charger_count > 1 else ''}"
    if plan is None:
        kind = {"parking_lot": "ev_lot", "parking_garage": "inside", "building_wall": "exterior"}[job.location]
        return [
            _p("Site Plan", H1),
            _p("Shows the electrical panel, the EV charging spaces and the circuit route.", SMALL),
            Spacer(1, 10),
            diagram(SchematicSite(kind=kind, equipment=f"Chargers: {spaces} (new)",
                                  panel_text=f"Panel, {job.service_amps} A (existing)",
                                  route_text=f"New circuits, up to {job.run_ft} ft"), share=0.8),
        ]
    legend = ["P  Electrical panel (existing)", f"C  EV chargers, {job.charger_amps} A (new)"]
    if plan.route_points:
        legend.append(f"Circuit route, {plan.measured_route_ft} ft measured on plan")
    if plan.lot:
        legend.append("Dashed yellow: lot line")
    measures = [f"Longest circuit run: {job.run_ft} ft", spaces]
    if job.trench_ft:
        measures.append(f"Underground: {job.trench_ft} ft (dashed on the plan)")
    if job.accessible_spaces is not None:
        measures.append(f"Accessible charging spaces: {job.accessible_spaces}")
    return site_plan_page(
        address=job.address, plan=plan,
        markers=[PlanMarker(plan.markers["panel"], INK, "P"), PlanMarker(plan.markers["charger"], GREEN, "C")],
        underground=bool(job.trench_ft), legend=legend, measures=measures,
        outline_over_aerial=job.jurisdiction.outline_over_aerial,
    )


def _one_line(packet: CommercialEvPacket) -> list:
    job = packet.job
    circuit = packet.circuit
    system = job.system
    run_detail = [f"2 {wire_label(circuit.wire.size)} Cu + {wire_label(circuit.ground)} Cu G",
                  f"{packet.underground_conduit + ' PVC' if packet.underground_conduit else packet.interior_conduit + ' EMT'}",
                  f"{job.run_ft} ft"]
    boxes = [
        ("UTILITY METER", ["Existing", system.label.split(",")[0], phase_text(system)], False),
        (f"MAIN PANEL {job.service_amps} A",
         [f"{job.service_amps} A service", f"New {circuit.breaker} A, 2-pole x {job.charger_count}",
          f"{job.open_breaker_spaces} spaces open"], True),
        (f"EV CHARGER x {job.charger_count}",
         [f"{job.charger_amps} A, {job.volts} V", f"{job.charger_kw:.1f} kW each",
          "Disconnect (625.43)" if job.disconnect_required else LOCATION_LABELS[job.location].capitalize()], False),
    ]
    runs = [("Service", ["Existing"], system.hots),
            (f"Circuit, {circuit.breaker} A 2-pole", run_detail, 2, False)]
    grounds = [(1, "Existing grounding electrode system")]
    rows = [["Charger circuit", f"2 {wire_label(circuit.wire.size)} Cu + {wire_label(circuit.ground)} Cu ground",
             packet.underground_conduit + " PVC underground" if packet.underground_conduit
             else f"{packet.interior_conduit} EMT",
             f"{circuit.breaker} A, 2-pole"]]
    if job.load_management:
        rows.append(["Energy management system", f"Holds the chargers to {job.managed_limit_amps} A",
                     "Listed for the purpose (625.42)", "Settings on the plans"])
    story = [
        _p("One-Line Diagram", H1),
        _p(f"{system.label}: panel, EV charger circuit and grounding. One of {job.charger_count} identical "
           "circuits is shown.", SMALL),
        Spacer(1, 10),
        diagram(OneLineFlow(boxes, runs, grounds), legend=one_line_data(job)),
        Spacer(1, 10),
        _p("Conductor and conduit schedule", H2),
        _table([_heads("Segment", "Conductors", "Conduit", "Protection")]
               + [[_p(cell) for cell in row] for row in rows],
               [1.4 * inch, 2.4 * inch, 1.5 * inch, content_w() - 5.3 * inch]),
    ]
    return fit_page(story)


def _load(packet: CommercialEvPacket) -> list:
    job = packet.job
    load = packet.load
    circuit = packet.circuit
    spare = (f"{load.spare_amps:.1f} A on the {job.service_amps} A service" if load.fits
             else f"Over by {-load.spare_amps:.1f} A, so this needs a fix before submittal")
    drop_ok = "Within 3%" if circuit.voltage_drop_percent <= 3 else "Over 3%, fix before submittal"
    trench = (f"{job.trench_ft} ft underground. {BURIAL_COVER_TEXT}" if job.trench_ft else "No underground run")
    method = (f"Existing load from measured maximum demand at 125% (NEC 220.87), or the electrician's own Article 220 "
              f"calculation, plus the chargers as continuous loads at 125% (625.41). Balanced {job.system.label} load. "
              "Confirm the method the city accepts.")
    if job.load_management:
        method = method.replace("plus the chargers as continuous loads at 125% (625.41)",
                                "plus the chargers at the current their energy management system holds them to (625.42)")
    page = service_load_page(
        load, method=method,
        result_rows=[("Existing service", f"{job.service_amps} A, {load.percent_of_service:.0f}% used by this load"),
                     ("Spare capacity", spare)],
        title="Load Calculation and Circuit Schedule",
    )
    rows = [
        ("Branch circuit", f"{job.charger_amps} A x 125% = {circuit.required_amps:.0f} A, {circuit.breaker} A 2-pole breaker",
         "625.41, 210.20(A)"),
        ("Conductors", f"2 {wire_label(circuit.wire.size)} Cu THWN-2, {circuit.wire.ampacity_75c} A at 75{DEGREE}C + "
                       f"{wire_label(circuit.ground)} Cu ground",
         "Upsized for voltage drop (250.122(B))" if circuit.upsized_for_voltage_drop else "Table 310.16, 250.122"),
        ("Conduit and fill", f"{packet.underground_conduit + ' PVC' if packet.underground_conduit else packet.interior_conduit + ' EMT'}, 3 wires, 40% fill",
         "Chapter 9 Table 4"),
        ("Run", f"Up to {job.run_ft} ft one way", "Field verify"),
        ("Trench and cover", trench, "Confirm for the conduit type used"),
        ("Voltage drop", f"{circuit.voltage_drop_volts:.1f} V, {circuit.voltage_drop_percent:.1f}% at "
                         f"{job.charger_amps} A", f"{drop_ok} (2 x K x I x L / CM)"),
        ("Disconnect", "Required, charger over 60 A" if job.disconnect_required else "Not required, 60 A or less",
         "625.43"),
    ]
    return [*page, Spacer(1, 12), _p("Charger circuit schedule", H2),
            _table([_heads("Item", "Specification", "Basis")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
                   [1.4 * inch, content_w() - 3.6 * inch, 2.2 * inch])]


def _panel_schedule(packet: CommercialEvPacket) -> list:
    job = packet.job
    main = existing_rows(job.existing_circuits)
    main += [ScheduleRow(f"EV charger {i} ({job.charger_amps} A)", f"{packet.circuit.breaker} A", 2, "New")
             for i in range(1, job.charger_count + 1)]
    return panel_schedule_page(
        [(f"Panel, {job.service_amps} A, {job.system.label}", main)],
        entered=bool(job.existing_circuits),
        spaces_note=f"Open spaces: {job.open_breaker_spaces} before, "
                    f"{max(job.open_breaker_spaces - job.spaces_needed, 0)} after the charger breakers.",
        header=panel_header(job),
    )


def _equipment(packet: CommercialEvPacket) -> list:
    job = packet.job
    sheet = find_equipment(job.charger_model, "charger")
    rows = [
        ("EV charger",
         f"{sheet.name if sheet else job.charger_model or 'Add make and model'}, {job.charger_amps} A, {job.volts} V",
         sheet.listing if sheet else "Attach manufacturer data and NRTL listing (625.5)"),
        ("Charger breaker", f"{packet.circuit.breaker} A, 2-pole, matched to the panel", "Listed for the panel"),
        ("Conductors", f"2 {wire_label(packet.circuit.wire.size)} Cu + {wire_label(packet.circuit.ground)} Cu ground",
         f"Listed, {job.jurisdiction.code_name} 310.16"),
    ]
    if job.load_management:
        rows.append(("Energy management", f"Holds the chargers to {job.managed_limit_amps} A",
                     "Listed for the purpose (625.42)"))
    return [
        _p("Equipment Data", H1),
        _p(f"The {sheet.name} data sheet from the manufacturer follows this page." if sheet else
           "Attach the manufacturer's data sheets and listing information behind this page.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Listing")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, content_w() - 3.4 * inch, 1.9 * inch]),
    ]


def _review(packet: CommercialEvPacket) -> list:
    job = packet.job
    items = ["Existing demand data matches the building", "Open spaces in the panel",
             "Charger make, model and listing", "Accessible charging space and path of travel"]
    if job.trench_ft:
        items.append("Circuit route, trench and cover")
    if job.disconnect_required:
        items.append("Disconnect location at each charger")
    if job.load_management:
        items.append("Energy management system settings")
    items += [f"Terminal ratings, {75}{DEGREE}C", "Panel directory updated", "Code edition confirmed with the city"]
    return review_page(items)


def render_commercial_ev_packet_pdf(packet: CommercialEvPacket) -> bytes:
    pdf = build_document(
        [_cover(packet), _application(packet), _site_plan(packet), _one_line(packet), _load(packet),
         _panel_schedule(packet), _equipment(packet), _review(packet)],
        title="Commercial EV Charger Permit Packet",
        block=title_block_for(packet.job),
        sheet_titles=SHEET_TITLES,
    )
    sheet = find_equipment(packet.job.charger_model, "charger")
    return attach_data_sheets(pdf, [sheet] if sheet else [], after_title="Equipment Data")
