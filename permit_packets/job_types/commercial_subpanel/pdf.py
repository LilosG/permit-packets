"""Render a commercial subpanel / feeder permit packet as a 9-page draft PDF.

The checklist comes from the job's jurisdiction. The site plan is the property to scale when there's a
plan, and a labeled schematic when there isn't.
"""
from __future__ import annotations

from reportlab.lib.units import inch
from reportlab.platypus import Spacer

from permit_packets.core.commercial_pdf import (
    DEGREE, OneLineFlow, SchematicSite, conductor_text, phase_text, service_load_page,
)
from permit_packets.core.conductors import wire_label
from permit_packets.core.equipment import attach_data_sheets, find_equipment
from permit_packets.core.panel_data import checklist_row as panel_row, one_line_data, panel_header
from permit_packets.core.panel_schedule import (
    PANEL_SCHEDULE_ITEM, ScheduleRow, existing_rows, panel_schedule_page, panel_schedule_row,
)
from permit_packets.core.pdf_base import (
    H1, H2, SMALL, _heads, _p, _table, application_page, build_document, content_w, cover_page, demo_title,
    diagram, fit_page, GREEN, INK, review_page,
)
from permit_packets.core.site_plan import PlanMarker, printed_scale, site_plan_page
from permit_packets.core.title_block import title_block_for
from permit_packets.job_types.commercial_subpanel.calc import (
    BURIAL_COVER_TEXT, LOCATION_LABELS, MATERIAL_ABBREVIATIONS, CommercialSubpanelPacket,
)

SECTION_PAGES = {
    "application": 2, "site_plan": 3, "one_line": 4, "feeder": 5, "load": 6, "panel_schedule": 7, "equipment": 8,
    "review": 9,
}
SHEET_TITLES = ["Checklist and Checks", "Permit Application Data", "Site Plan", "One-Line Diagram", "Feeder Schedule",
                "Load Calculation", "Panel Schedule", "Equipment Data", "Pre-Submittal Review"]


def _conduit(packet: CommercialSubpanelPacket) -> str:
    return packet.raceway_text or f"{packet.conduit_size} {packet.job.conduit}"


def _checklist_row(packet: CommercialSubpanelPacket, section: str) -> tuple[str, str]:
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
        if find_equipment(job.subpanel_model, "panel"):
            return f"Page {SECTION_PAGES['equipment']} + manufacturer data sheet", "Ready"
        if job.data_sheet_attached:
            return f"Page {SECTION_PAGES['equipment']} + data sheet attached by the electrician", "Ready"
        return f"Page {SECTION_PAGES['equipment']}: add manufacturer sheets", "Attach"
    shown = panel_row(job, section, SECTION_PAGES["one_line"], burial=(SECTION_PAGES["feeder"], BURIAL_COVER_TEXT))
    if shown:
        return shown
    if section not in SECTION_PAGES:
        # A requirement this packet has no page for is never shown as done.
        return "Not in this packet: add it by hand", "Open"
    return f"Page {SECTION_PAGES[section]}", "Ready"


def checklist_rows(packet: CommercialSubpanelPacket) -> list[tuple[str, str, str]]:
    job = packet.job
    rows = [(requirement.item, *_checklist_row(packet, requirement.section))
            for requirement in job.jurisdiction.checklist_for("commercial_subpanel").items]
    return rows + [(PANEL_SCHEDULE_ITEM, *panel_schedule_row(job, SECTION_PAGES["panel_schedule"]))]


def _cover(packet: CommercialSubpanelPacket) -> list:
    job = packet.job
    jurisdiction = job.jurisdiction
    checklist_cell = (
        f"{jurisdiction.label}\n{jurisdiction.checklist_for('commercial_subpanel').source_label}"
        if jurisdiction.known_for("commercial_subpanel")
        else f"{jurisdiction.label}\nGeneral checklist, city rules added in setup"
    )
    parcel = f"\nParcel {job.plan.parcel_number}" if job.plan and job.plan.parcel_number else ""
    use = f"{job.building_use}\n" if job.building_use else ""
    return cover_page(
        title="Commercial Subpanel Permit Packet",
        address=job.address,
        job_cell=f"{use}{job.subpanel_amps} A subpanel, {job.system.label}{parcel}\nCustomer: {job.customer}",
        contractor_cell=f"{job.contractor}\nLicense {job.license_number}",
        checklist_cell=checklist_cell,
        checklist_rows=checklist_rows(packet),
        checks=[(check.name, check.result, check.passed) for check in packet.checks],
        flags=packet.flags,
        stamp_box_in=job.jurisdiction.stamp_box_in,
    )


def scope_of_work(packet: CommercialSubpanelPacket) -> str:
    job = packet.job
    model = f" ({job.subpanel_model})" if job.subpanel_model else ""
    route = f"Trench about {job.trench_ft} ft and run" if job.trench_ft else "Run"
    detached = (" Provide a disconnect at the building and ground it with its own grounding electrode."
                if job.location == "detached_building" else "")
    service_note = ("No service upgrade." if packet.load.fits
                    else "Service capacity must be resolved before submittal.")
    return (
        f"Install one {job.subpanel_amps} A, {job.system.label} subpanel{model} {LOCATION_LABELS[job.location]}. "
        f"Add a {job.feeder_breaker_amps} A, {packet.feeder.poles}-pole breaker to the existing "
        f"{job.service_amps} A main panel. {route} a new {job.run_ft} ft feeder, {conductor_text(packet.feeder)}, "
        f"in {_conduit(packet)}, from the main panel to the subpanel.{detached} "
        f"Keep neutral and ground separate in the subpanel. {service_note}"
    )


def application_fields(packet: CommercialSubpanelPacket) -> list[tuple[str, str]]:
    job = packet.job
    return [
        ("Project address", job.address),
        ("Parcel number", job.plan.parcel_number if job.plan and job.plan.parcel_number else "Not on file"),
        ("Jurisdiction", job.jurisdiction.label),
        ("Property owner or tenant", job.customer),
        ("Permit type", "Electrical, commercial: subpanel and feeder"),
        ("Building use", job.building_use or "Add the building use"),
        ("Electrical service", f"{job.system.label}, {job.service_amps} A"),
        ("Subpanel", f"{job.subpanel_model or 'Add make and model'}, {job.subpanel_amps} A"),
        ("Contractor", job.contractor),
        ("License number", job.license_number),
    ]


def _application(packet: CommercialSubpanelPacket) -> list:
    inspections = [
        ("Rough", "Feeder, subpanel enclosure, grounding and bonding, before covering"),
        ("Final", "Subpanel, breakers, labeling, directory and working space on site"),
    ]
    if packet.job.trench_ft:
        inspections.insert(0, ("Underground", "Open trench, conduit and cover, before backfill"))
    return application_page(rows=application_fields(packet), scope=scope_of_work(packet), inspections=inspections)


def _site_plan(packet: CommercialSubpanelPacket) -> list:
    job = packet.job
    plan = job.plan
    if plan is None:
        kind = {"inside_building": "inside", "exterior_wall": "exterior", "detached_building": "detached"}[job.location]
        return [
            _p("Site Plan", H1),
            _p("Shows the location of the main panel, the subpanel and the feeder route.", SMALL),
            Spacer(1, 10),
            diagram(SchematicSite(kind=kind, equipment=f"Subpanel, {job.subpanel_amps} A (new)",
                                  panel_text=f"Main panel, {job.service_amps} A (existing)",
                                  route_text=f"New feeder, {job.run_ft} ft"), share=0.8),
        ]
    legend = ["P  Main panel (existing)", f"S  Subpanel, {job.subpanel_amps} A (new)"]
    if plan.route_points:
        legend.append(f"Feeder route, {plan.measured_route_ft} ft measured on plan")
    if plan.lot:
        legend.append("Dashed yellow: lot line")
    measures = [f"Feeder run: {job.run_ft} ft"]
    if job.trench_ft:
        measures.append(f"Underground: {job.trench_ft} ft (dashed on the plan)")
    setback = plan.distance_to_lot_line_ft(plan.markers["subpanel"])
    if setback is not None:
        measures.append(f"Subpanel to nearest lot line: {setback} ft")
    return site_plan_page(
        address=job.address, plan=plan,
        markers=[PlanMarker(plan.markers["panel"], INK, "P"), PlanMarker(plan.markers["subpanel"], GREEN, "S")],
        underground=bool(job.trench_ft), legend=legend, measures=measures,
        outline_over_aerial=job.jurisdiction.outline_over_aerial,
    )


def _one_line(packet: CommercialSubpanelPacket) -> list:
    job = packet.job
    feeder = packet.feeder
    system = job.system
    boxes = [
        ("UTILITY METER", ["Existing", f"{system.label.split(',')[0]}", phase_text(system)], False),
        (f"MAIN PANEL {job.service_amps} A",
         [f"{job.service_amps} A service", f"New {job.feeder_breaker_amps} A, {feeder.poles}-pole",
          f"{job.open_breaker_spaces} spaces open"], True),
        (f"SUBPANEL {job.subpanel_amps} A",
         [f"{job.subpanel_amps} A bus", f"{job.feeder_breaker_amps} A feeder breaker",
          LOCATION_LABELS[job.location].capitalize()], False),
    ]
    runs = [("Service", ["Existing"], system.hots),
            (f"Feeder, {job.feeder_breaker_amps} A {feeder.poles}-pole",
             [conductor_text(feeder), _conduit(packet), f"{job.run_ft} ft"], system.hots)]
    grounds = [(1, "Existing grounding electrode system")]
    if job.location == "detached_building":
        grounds.append((2, "New grounding electrode (250.32)"))
    rows = [["Feeder", conductor_text(feeder), _conduit(packet), f"{job.feeder_breaker_amps} A, {feeder.poles}-pole"]]
    if job.location == "detached_building":
        rows.append(["Grounding electrode", "Electrode per 250.52, GEC per 250.66", "As required (250.64)",
                     "Listed clamp or weld (250.70)"])
    story = [
        _p("One-Line Diagram", H1),
        _p(f"{system.label}: main panel, feeder conductors, subpanel and grounding.", SMALL),
        Spacer(1, 10),
        diagram(OneLineFlow(boxes, runs, grounds), legend=one_line_data(job)),
        Spacer(1, 10),
        _p("Conductor and conduit schedule", H2),
        _table([_heads("Segment", "Conductors", "Conduit", "Protection")]
               + [[_p(cell) for cell in row] for row in rows],
               [1.4 * inch, 2.4 * inch, 1.5 * inch, content_w() - 5.3 * inch]),
    ]
    return fit_page(story)


def _feeder_schedule(packet: CommercialSubpanelPacket) -> list:
    job = packet.job
    feeder = packet.feeder
    metal = MATERIAL_ABBREVIATIONS[job.material]
    size, ground = wire_label(feeder.conductor.size), wire_label(feeder.egc)
    hots = (f"Upsized from {wire_label(feeder.start.size)} for voltage drop" if feeder.upsized
            else f"{job.feeder_breaker_amps} A breaker (215.3, 240.4)")
    trench = (f"{job.trench_ft} ft underground. {BURIAL_COVER_TEXT}" if job.trench_ft else "No underground run")
    drop_ok = "Within 3%" if feeder.vd_percent <= 3 else "Over 3%, fix before submittal"
    formula = "1.732 x K x I x L / CM" if job.system.phases == 3 else "2 x K x I x L / CM"
    rows = [
        ("Phase conductors", f"{job.system.hots} {size} {metal} THWN-2, {feeder.conductor.ampacity_75c} A at 75{DEGREE}C", hots),
        ("Neutral", f"1 {size} {metal} THWN-2, full size", "Same size as the hots (220.61)"),
        ("Equipment ground", f"1 {ground} Cu" if job.material == "copper" else f"1 {ground} Al",
         "Upsized with the hots (250.122(B))" if feeder.upsized else "Table 250.122"),
        ("Conduit and fill", f"{_conduit(packet)}, {job.system.hots + 1} wires, 40% fill", "Chapter 9 Table 4"),
        ("Run", f"{job.run_ft} ft one way", "Field verify"),
        ("Trench and cover", trench, "Confirm for the conduit type used"),
        ("Voltage drop", f"{feeder.vd_volts:.1f} V, {feeder.vd_percent:.1f}% at {packet.feeder_load_amps:.1f} A",
         f"{drop_ok} ({formula})"),
        ("Terminal rating", f"Breaker and panel terminals rated 75{DEGREE}C", "110.14(C)"),
    ]
    return [
        _p("Feeder Schedule", H1),
        _p("Conductors, conduit, run, cover and voltage drop for the feeder to the subpanel.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Basis")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, content_w() - 3.9 * inch, 2.4 * inch]),
    ]


def _load(packet: CommercialSubpanelPacket) -> list:
    job = packet.job
    load = packet.load
    spare = (f"{load.spare_amps:.1f} A on the {job.service_amps} A service" if load.fits
             else f"Over by {-load.spare_amps:.1f} A, so this needs a fix before submittal")
    feeder_load = (f"{packet.feeder_load_amps:.1f} A, assumed at 80% of the breaker" if packet.loads_assumed
                   else f"{packet.feeder_load_amps:.1f} A from the loads listed")
    return service_load_page(
        load,
        method=("Existing load from measured maximum demand at 125% (NEC 220.87), or the electrician's own "
                "Article 220 calculation, plus the new subpanel loads with continuous loads at 125%. "
                f"Balanced {job.system.label} load. Confirm the method the city accepts."),
        result_rows=[
            ("Existing service", f"{job.service_amps} A, {load.percent_of_service:.0f}% used by this load"),
            ("Spare capacity", spare),
            ("Subpanel feeder load", feeder_load),
        ],
    )


def _equipment(packet: CommercialSubpanelPacket) -> list:
    job = packet.job
    sheet = find_equipment(job.subpanel_model, "panel")
    rows = [
        ("Subpanel",
         f"{sheet.name if sheet else job.subpanel_model or 'Add make and model'}, "
         f"{sheet.bus_amps if sheet and sheet.bus_amps else job.subpanel_amps} A bus, {job.system.label}",
         sheet.listing if sheet else "Attach manufacturer data and NRTL listing"),
        ("Feeder breaker", f"{job.feeder_breaker_amps} A, {packet.feeder.poles}-pole, matched to the main panel",
         "Listed for the panel"),
        ("Feeder conductors", f"{conductor_text(packet.feeder)}, {_conduit(packet)}",
         f"Listed, {job.jurisdiction.code_name} 310.16"),
    ]
    return [
        _p("Equipment Data", H1),
        _p(f"The {sheet.name} data sheet from the manufacturer follows this page." if sheet else
           "Attach the manufacturer's data sheets and listing information behind this page.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Listing")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, content_w() - 3.4 * inch, 1.9 * inch]),
    ]


def _review(packet: CommercialSubpanelPacket) -> list:
    job = packet.job
    items = ["Existing demand data matches the building", "Open spaces in the main panel"]
    if job.trench_ft:
        items.append("Feeder route, trench and cover")
    if job.location == "detached_building":
        items.append("Grounding electrode and disconnect at the building")
    items += [f"Terminal ratings, 75{DEGREE}C", "Arc-flash and phase identification labels",
              "Equipment data attached", "Code edition confirmed with the city"]
    return review_page(items)


def _panel_schedule(packet: CommercialSubpanelPacket) -> list:
    job = packet.job
    poles = packet.feeder.poles
    main = existing_rows(job.existing_circuits)
    main.append(ScheduleRow(f"Feeder to the {job.subpanel_amps} A subpanel (this permit)",
                            f"{job.feeder_breaker_amps} A", poles, "New"))
    sub = [ScheduleRow(f"{item.label} ({item.kva:g} kVA)", "Size per load", 0, "New")
           for item in job.loads] or [ScheduleRow("Circuits to be added", "Size per load", 1, "New")]
    return panel_schedule_page(
        [(f"Main panel, {job.service_amps} A, {job.system.label}", main), (f"Subpanel, {job.subpanel_amps} A", sub)],
        entered=bool(job.existing_circuits),
        spaces_note=f"Main panel open spaces: {job.open_breaker_spaces} before, "
                    f"{max(job.open_breaker_spaces - job.spaces_needed, 0)} after the feeder breaker.",
        header=panel_header(job),
    )


def render_commercial_subpanel_packet_pdf(packet: CommercialSubpanelPacket) -> bytes:
    pdf = build_document(
        [_cover(packet), _application(packet), _site_plan(packet), _one_line(packet), _feeder_schedule(packet),
         _load(packet), _panel_schedule(packet), _equipment(packet), _review(packet)],
        title=demo_title("Commercial Subpanel Permit Packet"),
        block=title_block_for(packet.job),
        sheet_titles=SHEET_TITLES,
    )
    sheet = find_equipment(packet.job.subpanel_model, "panel")
    return attach_data_sheets(pdf, [sheet] if sheet else [], after_title="Equipment Data")
