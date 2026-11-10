"""Render a 240 V appliance circuit permit packet as a 7-page draft PDF.

The checklist comes from the job's jurisdiction. The site plan is the property
to scale when there's a plan, and a labeled schematic when there isn't.
"""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, Spacer

from permit_packets.core.conductors import wire_label
from permit_packets.core.pdf_base import (
    CONTENT, COPPER, CREDIT, GREEN, H1, H2, INK, MUTED, PALE, SMALL, SOFT,
    _heads, _p, _table, application_page, build_document, cover_page, load_page, review_page,
)
from permit_packets.core.site_plan import AerialSitePlan, PlanMarker
from permit_packets.job_types.appliance_circuit.calc import (
    APPLIANCE_LABELS,
    APPLIANCE_TITLES,
    BURIAL_COVER_IN,
    DEGREE,
    LOCATION_LABELS,
    AppliancePacket,
    display_amps,
    sentence_case,
)

SECTION_PAGES = {"application": 2, "site_plan": 3, "one_line": 4, "load": 5, "equipment": 6, "review": 7}
LISTING_NOTE = "Attach the manufacturer's installation instructions and NRTL listing"


def _appliance(packet: AppliancePacket) -> str:
    return APPLIANCE_LABELS[packet.job.appliance]


def _size(packet: AppliancePacket) -> str:
    return wire_label(packet.branch.wire.size)


def _egc(packet: AppliancePacket) -> str:
    return wire_label(packet.branch.egc)


def _conduit(packet: AppliancePacket) -> str:
    return "cable" if packet.conduit_size is None else f"{packet.conduit_size} {packet.job.wiring}"


def _wire_text(packet: AppliancePacket) -> str:
    return f"{packet.job.conductors_in_conduit} {_size(packet)} Cu THWN-2 + {_egc(packet)} EGC"


def _circuit_label(packet: AppliancePacket) -> str:
    preposition = "as" if packet.conduit_size is None else "in"
    return f"{packet.job.conductors_in_conduit} {_size(packet)} Cu THWN-2 + {_egc(packet)} EGC {preposition} {_conduit(packet)}"


class SitePlan(Flowable):
    """A schematic layout from the job details, not a survey."""

    scale = 2.75

    def __init__(self, packet: AppliancePacket) -> None:
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
        if job.location == "detached":
            building(44, 90, 26, 24, ["DETACHED", "BUILDING"], fill=colors.white)
            route = [panel, (74, 58), (74, 101), (70, 101)]
            appliance = (70, 101)
        elif job.location == "outdoor":
            # Out through the wall and across to the pad beside the house.
            route = [panel, (73, 58), (73, 42)]
            appliance = (74, 42)
        else:
            panel = (66, 66)
            route = [panel, (26, 66)]
            appliance = (26, 66)

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
        c.rect(x(appliance[0]) - 7, y(appliance[1]) - 5, 7, 10, stroke=0, fill=1)

        lx = x(80) + 20
        ly = y(112)
        items = [
            (INK, f"Main panel, {job.service_amps} A (existing)"),
            (GREEN, f"{sentence_case(_appliance(self.packet))}, {display_amps(self.packet.load_amps)} A (new)"),
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
        c.drawString(lx + 13, route_y, f"New circuit, {job.run_ft} ft")
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


class OneLine(Flowable):
    def __init__(self, packet: AppliancePacket) -> None:
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

        xs = [0, 120]
        box(xs[0], "UTILITY METER", ["Existing", "120/240 V", "1-phase"])
        box(xs[1], "MAIN PANEL",
            [f"{job.service_amps} A service", f"New {packet.breaker} A, 2-pole",
             f"{job.open_breaker_spaces} spaces open"], SOFT)
        if job.has_disconnect:
            disconnect_x = 290
            box(disconnect_x, "DISCONNECT",
                [f"{packet.breaker} A, 240 V", "Within sight of", "the appliance"])
            xs.append(disconnect_x)
        appliance_x = CONTENT - box_w
        box(appliance_x, "APPLIANCE",
            [sentence_case(_appliance(packet)), f"{display_amps(packet.load_amps)} A, 240 V",
             f"{round(packet.load_amps * 240):,} VA"])
        xs.append(appliance_x)

        c.setStrokeColor(INK)
        c.setLineWidth(1.5)
        for left, right in zip(xs, xs[1:]):
            c.line(left + box_w, mid, right, mid)

        label_x = (xs[1] + box_w + xs[2]) / 2
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7.2)
        c.drawCentredString(label_x, mid + 27, f"{packet.breaker} A, 2-pole")
        c.setFont("Helvetica", 6.8)
        c.drawCentredString(label_x, mid + 17, f"{job.conductors_in_conduit} {_size(packet)} Cu THWN-2")
        c.drawCentredString(label_x, mid + 7, f"+ {_egc(packet)} EGC")
        preposition = "as" if packet.conduit_size is None else "in"
        c.drawCentredString(label_x, mid - 10, f"{preposition} {_conduit(packet)}")
        c.drawCentredString(label_x, mid - 20, f"{job.run_ft} ft, see schedule")

        ground_x = xs[1] + box_w / 2
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.2)
        c.line(ground_x, mid - box_h / 2, ground_x, mid - box_h / 2 - 16)
        for i, half in enumerate((13, 8, 3)):
            c.line(ground_x - half, mid - box_h / 2 - 16 - i * 4, ground_x + half, mid - box_h / 2 - 16 - i * 4)
        c.setFillColor(GREEN)
        c.setFont("Helvetica", 7)
        c.drawString(ground_x + 17, mid - box_h / 2 - 22, "Existing grounding electrode system")


def _checklist_row(packet: AppliancePacket, section: str) -> tuple[str, str]:
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
        return f"Page {SECTION_PAGES[section]}: add manufacturer sheets", "Attach"
    return f"Page {SECTION_PAGES[section]}", "Ready"


def _cover(packet: AppliancePacket) -> list:
    job = packet.job
    jurisdiction = job.jurisdiction
    checklist_cell = (
        f"{jurisdiction.label}\nFrom the city's published checklist"
        if jurisdiction.known_for("appliance_circuit")
        else f"{jurisdiction.label}\nGeneral checklist, city rules added in setup"
    )
    parcel = f"\nParcel {job.plan.parcel_number}" if job.plan and job.plan.parcel_number else ""
    return cover_page(
        title=f"{APPLIANCE_TITLES[job.appliance]} Circuit Permit Packet",
        address=job.address,
        job_cell=(f"{job.home.square_feet:,} sq ft home{parcel}\n"
                  f"{sentence_case(_appliance(packet))}, {LOCATION_LABELS[job.location]}\n"
                  f"Customer: {job.customer}"),
        contractor_cell=f"{job.contractor}\nLicense {job.license_number}",
        checklist_cell=checklist_cell,
        checklist_rows=[(requirement.item, *_checklist_row(packet, requirement.section))
                        for requirement in jurisdiction.checklist_for("appliance_circuit").items],
        checks=[(check.name, check.result, check.passed) for check in packet.checks],
        flags=packet.flags,
    )


def scope_of_work(packet: AppliancePacket) -> str:
    job = packet.job
    model = f" ({job.appliance_model})" if job.appliance_model else ""
    route = f"Trench about {job.trench_ft} ft and run" if job.trench_ft else "Run"
    destination = "a new disconnect, then to the appliance" if job.has_disconnect else "the appliance"
    service_note = (
        "No service upgrade."
        if packet.load.computed_amps <= job.service_amps
        else "Service capacity must be resolved before submittal."
    )
    return (
        f"Install one dedicated 240 V, {packet.breaker} A circuit for a {_appliance(packet)}{model} at the "
        f"{LOCATION_LABELS[job.location]}. "
        f"Add a {packet.breaker} A, 2-pole breaker to the existing {job.service_amps} A main panel. "
        f"{route} a new {job.run_ft} ft branch circuit, {_wire_text(packet)}, "
        f"{'as cable' if packet.conduit_size is None else f'in {_conduit(packet)} conduit'}, "
        f"from the main panel to {destination}. {service_note}"
    )


def application_fields(packet: AppliancePacket) -> list[tuple[str, str]]:
    job = packet.job
    return [
        ("Project address", job.address),
        ("Parcel number", job.plan.parcel_number if job.plan and job.plan.parcel_number else "Not on file"),
        ("Jurisdiction", job.jurisdiction.label),
        ("Property owner", job.customer),
        ("Permit type", f"Electrical, residential {_appliance(packet)} circuit"),
        (sentence_case(_appliance(packet)), job.appliance_model or "Add make and model"),
        ("Contractor", job.contractor),
        ("License number", job.license_number),
    ]


def _application(packet: AppliancePacket) -> list:
    inspections = [
        ("Rough", "Circuit wiring, conduit, grounding and bonding, before covering"),
        ("Final", "Breaker, disconnect, appliance, labeling, and manufacturer instructions on site"),
    ]
    if packet.job.trench_ft:
        inspections.insert(0, ("Underground", "Open trench, conduit and burial depth, before backfill"))
    return application_page(
        rows=application_fields(packet), scope=scope_of_work(packet), inspections=inspections)


def _plan_markers(packet: AppliancePacket) -> list[PlanMarker]:
    plan = packet.job.plan
    return [PlanMarker(plan.markers["panel"], INK, "P"), PlanMarker(plan.markers["appliance"], GREEN, "A")]


def _site_plan(packet: AppliancePacket) -> list:
    job = packet.job
    plan = job.plan
    if plan is None:
        return [
            _p("Site Plan", H1),
            _p(f"Shows the location of the main panel, the {_appliance(packet)} and the new circuit.", SMALL),
            Spacer(1, 10),
            SitePlan(packet),
        ]
    legend = [
        f"P  Main panel, {job.service_amps} A (existing)",
        f"A  {sentence_case(_appliance(packet))}, {display_amps(packet.load_amps)} A (new)",
    ]
    if plan.route_points:
        legend.append(
            f"New circuit {'underground' if job.trench_ft else 'route'}, {plan.measured_route_ft} ft measured on plan")
    if plan.lot:
        legend.append("Dashed yellow: lot line")
    measures = [f"Wire run with rises: {job.run_ft} ft"]
    if job.trench_ft:
        measures.append(f"Underground: {job.trench_ft} ft (dashed on the plan)")
    setback = plan.distance_to_lot_line_ft(plan.markers["appliance"])
    if setback is not None:
        measures.append(f"{sentence_case(_appliance(packet))} to nearest lot line: {setback} ft")
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


def _circuit_schedule(packet: AppliancePacket) -> list[tuple[str, str, str]]:
    job = packet.job
    branch = packet.branch
    column = 75 if job.terminals_75c else 60
    if job.is_hvac:
        sizing = f"Carries the {display_amps(job.mca)} A MCA (240.4(G), 440)"
    else:
        sizing = f"Carries the {packet.breaker} A breaker, within the 240.4(D) limit"
    hots = (
        "Upsized for voltage drop" if branch.upsized else sizing
    )
    ground = "Upsized with the hots (250.122(B))" if branch.upsized else "Table 250.122, no larger than the hots"
    trench = (
        f"{job.trench_ft} ft underground, {BURIAL_COVER_IN} in cover for PVC (300.5)"
        if job.trench_ft else "No underground run"
    )
    drop_ok = "Within 3%" if branch.vd_percent <= 3 else "Over 3%, fix before submittal"
    neutral = "Neutral for the appliance's 120 V part" if job.needs_neutral else "No neutral needed"
    return [
        ("Hot conductors", f"2 {_size(packet)} Cu THWN-2, {branch.wire.ampacity(job.terminals_75c)} A at {column}{DEGREE}C", hots),
        ("Neutral", f"{_size(packet)} Cu THWN-2" if job.needs_neutral else "None", neutral),
        ("Equipment ground", f"1 {_egc(packet)} Cu", ground),
        ("Conduit and fill", (f"{_conduit(packet)}, {job.conductors_in_conduit + 1} wires, 40% fill"
                              if packet.conduit_size else "Cable, no conduit fill"), "Chapter 9 Table 4"),
        ("Breaker", f"{packet.breaker} A, 2-pole", "Matched to the main panel"),
        ("Run", f"{job.run_ft} ft one way", "Field verify"),
        ("Trench and cover", trench, "Confirm for the wiring method used"),
        ("Voltage drop", f"{branch.vd_volts:.1f} V, {branch.vd_percent:.1f}% at {display_amps(packet.load_amps)} A", drop_ok),
        ("Terminal rating", f"Sized at the {column}{DEGREE}C column", "110.14(C)"),
    ]


def _one_line(packet: AppliancePacket) -> list:
    job = packet.job
    rows = [["Branch circuit", _wire_text(packet), _conduit(packet), f"{packet.breaker} A, 2-pole"]]
    return [
        _p("One-Line Diagram", H1),
        _p("Main panel, breaker, disconnect, conductors and the appliance.", SMALL),
        Spacer(1, 10),
        OneLine(packet),
        Spacer(1, 6),
        _p("Conductor and conduit schedule", H2),
        _table([_heads("Segment", "Conductors", "Conduit", "Protection")]
               + [[_p(cell) for cell in row] for row in rows],
               [1.4 * inch, 2.4 * inch, 1.3 * inch, CONTENT - 5.1 * inch]),
        Spacer(1, 10),
        _p("Circuit schedule", H2),
        _table([_heads("Item", "Specification", "Basis")]
               + [[_p(a), _p(b), _p(c)] for a, b, c in _circuit_schedule(packet)],
               [1.5 * inch, CONTENT - 4.2 * inch, 2.7 * inch]),
    ]


def _load(packet: AppliancePacket) -> list:
    job = packet.job
    load = packet.load
    spare = (
        f"{load.spare_amps:.1f} A on the {job.service_amps} A service"
        if load.spare_amps >= 0
        else f"Over by {-load.spare_amps:.1f} A, so this needs a fix before submittal"
    )
    return load_page(
        load,
        method=f"Optional dwelling method, {job.jurisdiction.code_name} 220.82, with the {_appliance(packet)} "
               "added at 100% of nameplate. Confirm the method the city accepts.",
        service_rows=[
            ("Existing service", f"{job.service_amps} A, {load.percent_of_service:.0f}% used by this load"),
            ("Spare capacity", spare),
            (f"{sentence_case(_appliance(packet))} circuit", f"{display_amps(packet.load_amps)} A, {packet.breaker} A breaker"),
        ],
    )


def _nameplate(packet: AppliancePacket) -> str:
    job = packet.job
    if job.appliance == "sauna":
        return f"{display_amps(job.heater_kw)} kW heater, {display_amps(packet.load_amps)} A at 240 V"
    if job.is_hvac:
        return f"MCA {display_amps(job.mca)} A, max breaker (MOCP) {job.mocp} A"
    manufacturer = (
        f", manufacturer breaker {job.manufacturer_breaker} A" if job.manufacturer_breaker else ""
    )
    return f"Nameplate {display_amps(job.nameplate_amps)} A at 240 V{manufacturer}"


def _equipment(packet: AppliancePacket) -> list:
    job = packet.job
    code = job.jurisdiction.code_name
    rows = [
        (sentence_case(_appliance(packet)), job.appliance_model or "Add make and model", LISTING_NOTE),
        ("Nameplate data used", _nameplate(packet), "From the nameplate"),
        ("Breaker", f"{packet.breaker} A, 2-pole, matched to the main panel", "Listed for the panel"),
        ("Branch conductors", f"{_wire_text(packet)}, {_conduit(packet)}", f"Listed, {code} 310.16"),
    ]
    if job.appliance == "hot_tub":
        protection = {"breaker": "GFCI breaker", "spa_pack": "Listed spa pack", "none": "None"}[job.gfci]
        rows.append(("GFCI protection", protection, f"{code} 680.44"))
        rows.append(("Disconnect", f"Within sight of the spa, {job.disconnect_distance_ft} ft away", f"{code} 680.13"))
    elif job.is_hvac:
        rows.append(("Disconnect", "Within sight of the outdoor unit", f"{code} 440.14"))
    return [
        _p("Equipment Data", H1),
        _p("Attach the manufacturer's data sheets and listing information behind this page.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Listing")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, CONTENT - 3.4 * inch, 1.9 * inch]),
    ]


def _review(packet: AppliancePacket) -> list:
    job = packet.job
    items = [
        "Existing loads match the home",
        "Open spaces in the main panel",
        "Breaker matches the nameplate",
        f"Equipment terminal rating confirmed, {75 if job.terminals_75c else 60}{DEGREE}C column",
    ]
    if job.trench_ft:
        items.append("Route and trench depth")
    if job.appliance == "hot_tub":
        items += ["Spa bonding done to the manufacturer's instructions", "GFCI protection and disconnect distance"]
    elif job.appliance == "sauna":
        items.append("Heater instructions followed, including wire type and no receptacles in the room")
    elif job.is_hvac:
        items.append("Disconnect within sight of the unit and a 120 V service receptacle")
    items += ["Equipment data attached", "Code edition confirmed with the city"]
    return review_page(items)


def render_appliance_packet_pdf(packet: AppliancePacket) -> bytes:
    return build_document(
        [_cover(packet), _application(packet), _site_plan(packet), _one_line(packet),
         _load(packet), _equipment(packet), _review(packet)],
        title=f"{APPLIANCE_TITLES[packet.job.appliance]} Circuit Permit Packet (demo)",
    )
