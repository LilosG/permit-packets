"""Render a subpanel / feeder permit packet as an 8-page draft PDF.

The checklist comes from the job's jurisdiction. The site plan is the property
to scale when there's a plan, and a labeled schematic when there isn't.
"""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, Spacer

from permit_packets.core.conductors import feeder_conductor, wire_label
from permit_packets.core.pdf_base import (
    CONTENT, COPPER, CREDIT, GREEN, H1, H2, INK, MUTED, PALE, SMALL, SOFT,
    _heads, _p, _table, application_page, build_document, cover_page, load_page, review_page,
)
from permit_packets.core.site_plan import AerialSitePlan, PlanMarker
from permit_packets.job_types.subpanel.calc import (
    BURIAL_COVER_IN,
    LOCATION_LABELS,
    MATERIAL_ABBREVIATIONS,
    SubpanelPacket,
)

SECTION_PAGES = {
    "application": 2, "site_plan": 3, "one_line": 4, "feeder": 5, "load": 6, "equipment": 7, "review": 8,
}
DEGREE = "\N{DEGREE SIGN}"


def _metal(packet: SubpanelPacket) -> str:
    return MATERIAL_ABBREVIATIONS[packet.job.material]


def _size(packet: SubpanelPacket) -> str:
    return wire_label(packet.feeder.conductor.size)


def _egc(packet: SubpanelPacket) -> str:
    return wire_label(packet.feeder.egc)


def _conduit(packet: SubpanelPacket) -> str:
    return f"{packet.conduit_size} {packet.job.conduit}"


def _wire_text(packet: SubpanelPacket) -> str:
    return f"2 {_size(packet)} {_metal(packet)} + {_size(packet)} neutral + {_egc(packet)} EGC"


def _feeder_label(packet: SubpanelPacket) -> str:
    return f"2 {_size(packet)} {_metal(packet)} + {_size(packet)} N + {_egc(packet)} EGC in {_conduit(packet)}"


class SitePlan(Flowable):
    """A schematic layout from the job details, not a survey."""

    scale = 2.75

    def __init__(self, packet: SubpanelPacket) -> None:
        super().__init__()
        self.packet = packet
        self.width = CONTENT
        self.height = 120 * self.scale + 36

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        k = self.scale
        ox = (CONTENT - 80 * k) / 2 - 40
        oy = 24
        x = lambda v: ox + v * k
        y = lambda v: oy + v * k
        job = self.packet.job

        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.setDash(6, 3)
        c.rect(x(0), y(0), 80 * k, 120 * k, stroke=1, fill=0)
        c.setDash()

        def building(bx, by, bw, bh, title, note=None, fill=PALE):
            c.setFillColor(fill)
            c.setStrokeColor(INK)
            c.setLineWidth(1.2)
            c.rect(x(bx), y(by), bw * k, bh * k, stroke=1, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8.2)
            for i, word in enumerate(title):
                c.drawCentredString(x(bx + bw / 2), y(by + bh / 2) + 2 - i * 10, word)
            if note:
                c.setFont("Helvetica", 7.2)
                c.drawCentredString(x(bx + bw / 2), y(by + bh / 2) - 9, note)

        building(12, 30, 54, 44, ["EXISTING HOUSE"], f"{job.home.square_feet:,} sq ft")
        panel = (66, 58)
        if job.location == "detached_building":
            building(44, 90, 26, 24, ["DETACHED", "BUILDING"], fill=colors.white)
            route = [panel, (74, 58), (74, 101), (70, 101)]
            subpanel = (70, 101)
        elif job.location == "attached_garage":
            building(12, 74, 30, 22, ["ATTACHED", "GARAGE"], fill=colors.white)
            # Inside the house, up through the shared wall to the garage.
            route = [panel, (38, 58), (38, 79), (40, 79)]
            subpanel = (42, 79)
        else:
            panel = (66, 66)
            route = [panel, (26, 66)]
            subpanel = (26, 66)

        c.setStrokeColor(MUTED)
        c.setFillColor(colors.white)
        c.setLineWidth(0.6)
        c.rect(x(50), y(0), 16 * k, 30 * k, stroke=1, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7)
        c.drawCentredString(x(58), y(14), "Driveway")
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(x(40), oy - 11, "STREET (front property line)")

        c.setStrokeColor(COPPER)
        c.setLineWidth(2.2)
        if job.trench_ft:
            c.setDash(7, 3)
        points = [(x(a), y(b)) for a, b in route]
        c.lines([(*points[i], *points[i + 1]) for i in range(len(points) - 1)])
        c.setDash()

        c.setFillColor(INK)
        c.rect(x(panel[0]) - 7, y(panel[1]) - 5, 7, 10, stroke=0, fill=1)
        c.setFillColor(GREEN)
        c.rect(x(subpanel[0]) - 7, y(subpanel[1]) - 5, 7, 10, stroke=0, fill=1)

        lx = x(80) + 20
        ly = y(112)
        items = [
            (INK, f"Main panel, {job.service_amps} A (existing)"),
            (GREEN, f"Subpanel, {job.subpanel_amps} A (new)"),
        ]
        c.setFont("Helvetica", 8)
        for i, (color, text) in enumerate(items):
            c.setFillColor(color)
            c.rect(lx, ly - i * 16, 8, 8, stroke=0, fill=1)
            c.setFillColor(INK)
            c.drawString(lx + 13, ly - i * 16, text)
        route_y = ly - len(items) * 16
        c.setStrokeColor(COPPER)
        c.setLineWidth(2.2)
        c.line(lx - 2, route_y + 3, lx + 10, route_y + 3)
        c.setFillColor(INK)
        c.drawString(lx + 13, route_y, f"New feeder, {job.run_ft} ft")
        c.setFont("Helvetica", 7.2)
        c.setFillColor(MUTED)
        notes = ["Schematic, not to scale.", "Field verify the route."]
        if job.trench_ft:
            notes.append(f"{job.trench_ft} ft underground (dashed).")
        for i, note in enumerate(notes):
            c.drawString(lx, route_y - 24 - i * 11, note)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(INK)
        c.drawString(lx, y(8), "N  ^  (plan up)")


def _ground_symbol(c, x: float, top: float) -> float:
    """Three bars hanging from `top`. Returns where the symbol ends."""
    c.setStrokeColor(GREEN)
    c.setLineWidth(1.2)
    c.line(x, top, x, top - 16)
    for i, half in enumerate((13, 8, 3)):
        c.line(x - half, top - 16 - i * 4, x + half, top - 16 - i * 4)
    return top - 16 - 8


class OneLine(Flowable):
    def __init__(self, packet: SubpanelPacket) -> None:
        super().__init__()
        self.packet = packet
        self.width = CONTENT
        self.height = 170

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        packet = self.packet
        job = packet.job
        mid = 100
        box_w = 84
        box_h = 62

        def box(bx, title, lines, fill=colors.white):
            c.setFillColor(fill)
            c.setStrokeColor(INK)
            c.setLineWidth(1.3)
            c.roundRect(bx, mid - box_h / 2, box_w, box_h, 3, stroke=1, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7.6)
            c.drawCentredString(bx + box_w / 2, mid + box_h / 2 + 6, title)
            c.setFont("Helvetica", 7)
            for i, line in enumerate(lines):
                c.drawCentredString(bx + box_w / 2, mid + 8 - i * 10, line)

        xs = [0, 120, CONTENT - box_w]
        box(xs[0], "UTILITY METER", ["Existing", "120/240 V", "1-phase"])
        box(xs[1], f"MAIN PANEL {job.service_amps} A",
            [f"{job.service_amps} A service", f"New {job.feeder_breaker_amps} A, 2-pole",
             f"{job.open_breaker_spaces} spaces open"], SOFT)
        box(xs[2], f"SUBPANEL {job.subpanel_amps} A",
            [f"{job.subpanel_amps} A bus", f"{job.feeder_breaker_amps} A feeder breaker",
             LOCATION_LABELS[job.location].capitalize()])

        c.setStrokeColor(INK)
        c.setLineWidth(1.5)
        for left, right in zip(xs, xs[1:]):
            c.line(left + box_w, mid, right, mid)

        label_x = (xs[1] + box_w + xs[2]) / 2
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7.2)
        c.drawCentredString(label_x, mid + 15, f"Feeder, {job.feeder_breaker_amps} A 2-pole breaker")
        c.setFont("Helvetica", 6.8)
        c.drawCentredString(label_x, mid + 5, _feeder_label(packet))
        c.drawCentredString(label_x, mid - 10, f"{job.run_ft} ft, see schedule")

        main_ground = xs[1] + box_w / 2
        end = _ground_symbol(c, main_ground, mid - box_h / 2)
        c.setFillColor(GREEN)
        c.setFont("Helvetica", 7)
        c.drawString(main_ground + 17, end + 2, "Existing grounding electrode system")
        if job.location == "detached_building":
            sub_ground = xs[2] + box_w / 2
            end = _ground_symbol(c, sub_ground, mid - box_h / 2)
            c.setFillColor(GREEN)
            c.setFont("Helvetica", 7)
            c.drawRightString(sub_ground - 17, end + 2, "New grounding electrode (250.32(A))")
            c.drawRightString(sub_ground - 17, end - 8, "Neutral and ground separate")


def _checklist_row(packet: SubpanelPacket, section: str) -> tuple[str, str]:
    job = packet.job
    plan = job.plan
    if section == "application":
        missing = job.jurisdiction.needs_parcel_number and not (plan and plan.parcel_number)
        return "Page 2: add the parcel number" if missing else "Page 2: fields ready for the city's form", (
            "Open" if missing else "Ready")
    if section == "site_plan":
        if plan:
            return f"Page 3: to scale, 1 in = {plan.scale_ft_per_in} ft", "Ready"
        return "Page 3: schematic only, replace it", "Open"
    if section == "equipment":
        return "Page 7: add manufacturer sheets", "Attach"
    return f"Page {SECTION_PAGES[section]}", "Ready"


def _cover(packet: SubpanelPacket) -> list:
    job = packet.job
    jurisdiction = job.jurisdiction
    checklist_cell = (
        f"{jurisdiction.label}\n{jurisdiction.checklist_for('subpanel').source_label}"
        if jurisdiction.known_for("subpanel")
        else f"{jurisdiction.label}\nGeneral checklist, city rules added in setup"
    )
    parcel = f"\nParcel {job.plan.parcel_number}" if job.plan and job.plan.parcel_number else ""
    return cover_page(
        title="Subpanel Permit Packet",
        address=job.address,
        job_cell=(f"{job.home.square_feet:,} sq ft home{parcel}\n"
                  f"{job.subpanel_amps} A subpanel, {LOCATION_LABELS[job.location]}\n"
                  f"Customer: {job.customer}"),
        contractor_cell=f"{job.contractor}\nLicense {job.license_number}",
        checklist_cell=checklist_cell,
        checklist_rows=[(requirement.item, *_checklist_row(packet, requirement.section))
                        for requirement in jurisdiction.checklist_for("subpanel").items],
        checks=[(check.name, check.result, check.passed) for check in packet.checks],
        flags=packet.flags,
    )


def scope_of_work(packet: SubpanelPacket) -> str:
    job = packet.job
    model = f" ({job.subpanel_model})" if job.subpanel_model else ""
    route = f"Trench about {job.trench_ft} ft and run" if job.trench_ft else "Run"
    detached = (
        " Ground the building with its own grounding electrode and a disconnect at the building."
        if job.location == "detached_building" else ""
    )
    service_note = (
        "No service upgrade."
        if packet.load.computed_amps <= job.service_amps
        else "Service capacity must be resolved before submittal."
    )
    return (
        f"Install one {job.subpanel_amps} A, 120/240 V subpanel{model} at the {LOCATION_LABELS[job.location]}. "
        f"Add a {job.feeder_breaker_amps} A, 2-pole breaker to the existing {job.service_amps} A main panel. "
        f"{route} a new {job.run_ft} ft feeder, {_wire_text(packet)}, in {_conduit(packet)} conduit, "
        f"from the main panel to the subpanel.{detached} "
        f"Keep neutral and ground separate in the subpanel. {service_note}"
    )


def application_fields(packet: SubpanelPacket) -> list[tuple[str, str]]:
    job = packet.job
    return [
        ("Project address", job.address),
        ("Parcel number", job.plan.parcel_number if job.plan and job.plan.parcel_number else "Not on file"),
        ("Jurisdiction", job.jurisdiction.label),
        ("Property owner", job.customer),
        ("Permit type", "Electrical, residential subpanel and feeder"),
        ("Subpanel", f"{job.subpanel_model or 'Add make and model'}, {job.subpanel_amps} A"),
        ("Contractor", job.contractor),
        ("License number", job.license_number),
    ]


def _application(packet: SubpanelPacket) -> list:
    inspections = [
        ("Rough", "Feeder, subpanel enclosure, grounding and bonding, before covering"),
        ("Final", "Subpanel, breakers, labeling, and working space on site"),
    ]
    if packet.job.trench_ft:
        inspections.insert(0, ("Underground", "Open trench, conduit and burial depth, before backfill"))
    return application_page(
        rows=application_fields(packet), scope=scope_of_work(packet), inspections=inspections)


def _plan_markers(packet: SubpanelPacket) -> list[PlanMarker]:
    plan = packet.job.plan
    return [PlanMarker(plan.markers["panel"], INK, "P"), PlanMarker(plan.markers["subpanel"], GREEN, "S")]


def _site_plan(packet: SubpanelPacket) -> list:
    job = packet.job
    plan = job.plan
    if plan is None:
        return [
            _p("Site Plan", H1),
            _p("Shows the location of the main panel, the subpanel and the feeder route.", SMALL),
            Spacer(1, 10),
            SitePlan(packet),
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
    measures.append(f"Scale 1 in = {plan.scale_ft_per_in} ft when printed at 100%")
    measures.append("Not a survey. Field verify all dimensions.")
    return [
        _p("Site Plan", H1),
        _p(job.address + (f". Parcel {plan.parcel_number}." if plan.parcel_number else "."), SMALL),
        Spacer(1, 6),
        AerialSitePlan(plan, markers=_plan_markers(packet), underground=bool(job.trench_ft), width=CONTENT),
        Spacer(1, 6),
        _table([[_p("\n".join(legend)), _p("\n".join(measures))]], [CONTENT / 2, CONTENT / 2], head=False),
        Spacer(1, 3),
        _p(". ".join(credit.rstrip(".") for credit in plan.credits) + ".", CREDIT),
    ]


def _one_line(packet: SubpanelPacket) -> list:
    job = packet.job
    rows = [
        ["Feeder", _wire_text(packet), _conduit(packet), f"{job.feeder_breaker_amps} A, 2-pole"],
    ]
    if job.location == "detached_building":
        rows.append(["Grounding electrode", "Electrode per 250.52, GEC per 250.66", "As required (250.64)",
                     "Listed clamp or weld (250.70)"])
    return [
        _p("One-Line Diagram", H1),
        _p("Main panel, feeder conductors, subpanel and grounding.", SMALL),
        Spacer(1, 10),
        OneLine(packet),
        Spacer(1, 10),
        _p("Conductor and conduit schedule", H2),
        _table([_heads("Segment", "Conductors", "Conduit", "Protection")]
               + [[_p(cell) for cell in row] for row in rows],
               [1.4 * inch, 2.2 * inch, 1.5 * inch, CONTENT - 5.1 * inch]),
    ]


def _feeder_schedule(packet: SubpanelPacket) -> list:
    job = packet.job
    feeder = packet.feeder
    metal = _metal(packet)
    basis = (
        f"{job.feeder_breaker_amps} A breaker x 83% (310.12, whole dwelling)"
        if job.whole_dwelling else f"{job.feeder_breaker_amps} A breaker (240.4)"
    )
    ground = "Upsized with the hots (250.122(B))" if feeder.upsized else "Table 250.122"
    hots = (
        f"Upsized from {wire_label(_start_size(packet))} for voltage drop" if feeder.upsized else basis
    )
    trench = (
        f"{job.trench_ft} ft underground, {BURIAL_COVER_IN} in cover for PVC (300.5)"
        if job.trench_ft else "No underground run"
    )
    drop_ok = "Within 3%" if feeder.vd_percent <= 3 else "Over 3%, fix before submittal"
    rows = [
        ("Phase conductors", f"2 {_size(packet)} {metal} THWN-2, {feeder.conductor.ampacity_75c} A at 75{DEGREE}C", hots),
        ("Neutral", f"1 {_size(packet)} {metal} THWN-2, full size", "Same size as the hots"),
        ("Equipment ground", f"1 {_egc(packet)} {metal}", ground),
        ("Conduit and fill", f"{_conduit(packet)}, 4 wires, 40% fill", "Chapter 9 Table 4"),
        ("Run", f"{job.run_ft} ft one way", "Field verify"),
        ("Trench and cover", trench, "Confirm for the conduit type used"),
        ("Voltage drop",
         f"{feeder.vd_volts:.1f} V, {feeder.vd_percent:.1f}% at {packet.feeder_load_amps:.1f} A", drop_ok),
        ("Terminal rating", f"Breaker and panel terminals rated 75{DEGREE}C", "110.14(C)"),
    ]
    return [
        _p("Feeder Schedule", H1),
        _p("Conductors, conduit, run, cover and voltage drop for the feeder to the subpanel.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Basis")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, CONTENT - 3.9 * inch, 2.4 * inch]),
    ]


def _start_size(packet: SubpanelPacket) -> str:
    """The size the breaker alone calls for, before any voltage drop upsizing."""
    job = packet.job
    return feeder_conductor(job.feeder_breaker_amps, job.material, job.whole_dwelling).size


def _load(packet: SubpanelPacket) -> list:
    job = packet.job
    load = packet.load
    spare = (
        f"{load.spare_amps:.1f} A on the {job.service_amps} A service"
        if load.spare_amps >= 0
        else f"Over by {-load.spare_amps:.1f} A, so this needs a fix before submittal"
    )
    feeder_load = (
        f"{packet.feeder_load_amps:.1f} A, assumed at 80% of the breaker" if packet.loads_assumed
        else f"{packet.feeder_load_amps:.1f} A from the loads listed"
    )
    return load_page(
        load,
        method=f"Optional dwelling method, {job.jurisdiction.code_name} 220.82, with the subpanel loads added "
               "at 100% of nameplate. Confirm the method the city accepts.",
        service_rows=[
            ("Existing service", f"{job.service_amps} A, {load.percent_of_service:.0f}% used by this load"),
            ("Spare capacity", spare),
            ("Subpanel feeder load", feeder_load),
        ],
    )


def _equipment(packet: SubpanelPacket) -> list:
    job = packet.job
    code = job.jurisdiction.code_name
    rows = [
        ("Subpanel",
         f"{job.subpanel_model or 'Add make and model'}, {job.subpanel_amps} A bus, "
         f"{job.feeder_breaker_amps} A feeder breaker",
         "Attach manufacturer data and NRTL listing"),
        ("Feeder breaker", f"{job.feeder_breaker_amps} A, 2-pole, matched to the main panel", "Listed for the panel"),
        ("Feeder conductors", f"{_wire_text(packet)}, {_conduit(packet)}", f"Listed, {code} 310.16"),
    ]
    return [
        _p("Equipment Data", H1),
        _p("Attach the manufacturer's data sheets and listing information behind this page.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Listing")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, CONTENT - 3.4 * inch, 1.9 * inch]),
    ]


def _review(packet: SubpanelPacket) -> list:
    job = packet.job
    items = ["Existing loads match the home", "Open spaces in the main panel"]
    if job.trench_ft:
        items.append("Feeder route and trench depth")
    if job.location == "detached_building":
        items.append("Grounding electrode and disconnect at the building")
    items += [
        f"Terminal ratings, 75{DEGREE}C",
        "Equipment data attached",
        "Code edition confirmed with the city",
    ]
    return review_page(items)


def render_subpanel_packet_pdf(packet: SubpanelPacket) -> bytes:
    return build_document(
        [_cover(packet), _application(packet), _site_plan(packet), _one_line(packet),
         _feeder_schedule(packet), _load(packet), _equipment(packet), _review(packet)],
        title="Subpanel Permit Packet (demo)",
    )
