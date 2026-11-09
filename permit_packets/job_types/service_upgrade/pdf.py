"""Render a panel / service upgrade permit packet as an 8-page draft PDF.

The checklist comes from the job's jurisdiction. The site plan is the property
to scale when there's a plan, and a labeled schematic when there isn't.
"""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, Spacer

from permit_packets.core.conductors import wire_label
from permit_packets.core.pdf_base import (
    CELL_BOLD, CONTENT, COPPER, CREDIT, GREEN, H1, H2, INK, MUTED, PALE, SMALL, SOFT,
    _heads, _p, _table, application_page, build_document, cover_page, load_page, review_page,
)
from permit_packets.core.site_plan import AerialSitePlan, PlanMarker
from permit_packets.job_types.service_upgrade.calc import (
    BRAND_LABELS,
    ELECTRODE_LABELS,
    EQUIPMENT_LABELS,
    MATERIAL_ABBREVIATIONS,
    ServicePacket,
)

SECTION_PAGES = {
    "application": 2, "site_plan": 3, "one_line": 4, "load": 5, "utility": 6, "equipment": 7, "review": 8,
}
# Where each electrode hangs under the riser diagram, in the order it is drawn.
ELECTRODE_NOTES = {
    "rods": ("Ground rods", "(250.52(A)(5))"),
    "concrete_encased": ("Concrete-encased", "electrode (250.52(A)(3))"),
    "water_pipe": ("Metal water pipe", "(250.52(A)(1))"),
}


def _metal(packet: ServicePacket) -> str:
    return MATERIAL_ABBREVIATIONS[packet.job.material]


def _service_wire(packet: ServicePacket) -> str:
    return f"3 {wire_label(packet.conductor.size)} {_metal(packet)} THWN-2"


def _conduit_text(packet: ServicePacket) -> str:
    return f"{packet.conduit_size} {packet.job.conduit}" if packet.conduit_size else "Cable, no conduit"


def _title(packet: ServicePacket) -> str:
    kind = "Service Upgrade" if packet.job.scope == "upgrade" else "Panel Replacement"
    return f"{kind} Permit Packet"


def _drop(packet: ServicePacket) -> str:
    return packet.job.service_drop


class SitePlan(Flowable):
    """A schematic layout from the job details, not a survey."""

    scale = 2.75

    def __init__(self, packet: ServicePacket) -> None:
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

        c.setFillColor(PALE)
        c.setStrokeColor(INK)
        c.setLineWidth(1.2)
        c.rect(x(12), y(30), 54 * k, 44 * k, stroke=1, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8.2)
        c.drawCentredString(x(39), y(52) + 2, "EXISTING HOUSE")
        c.setFont("Helvetica", 7.2)
        c.drawCentredString(x(39), y(52) - 9, f"{job.home.square_feet:,} sq ft")

        c.setStrokeColor(MUTED)
        c.setFillColor(colors.white)
        c.setLineWidth(0.6)
        c.rect(x(50), y(0), 16 * k, 30 * k, stroke=1, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7)
        c.drawCentredString(x(58), y(14), "Driveway")
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(x(40), oy - 11, "STREET (front property line)")

        # The equipment sits on the right wall. A combo is one box; otherwise the meter is below the panel.
        combo = job.equipment == "meter_main"
        meter = (66, 58) if combo else (66, 66)
        panel = (66, 58) if combo else (66, 50)
        utility_end = (80, 66)

        c.setStrokeColor(MUTED)
        c.setLineWidth(1.6)
        if _drop(self.packet) == "underground":
            c.setDash(5, 3)
        c.line(x(utility_end[0]), y(utility_end[1]), x(meter[0]), y(meter[1]))
        c.setDash()

        if not combo:
            c.setStrokeColor(COPPER)
            c.setLineWidth(2.2)
            c.line(x(meter[0]), y(meter[1]), x(panel[0]), y(panel[1]))
        c.setFillColor(MUTED)
        c.rect(x(meter[0]) - 7, y(meter[1]) - 5, 7, 10, stroke=0, fill=1)
        c.setFillColor(COPPER)
        c.rect(x(panel[0]) - 7, y(panel[1]) - 5, 7, 10, stroke=0, fill=1)

        lx = x(80) + 20
        ly = y(112)
        items = [
            (MUTED, "Meter, existing location" if not job.relocated else "Meter, relocated"),
            (COPPER, f"Main panel, {job.new_service_amps} A (new)"),
        ]
        if combo:
            items = [(COPPER, f"Meter-main, {job.new_service_amps} A (new)")]
            if job.relocated:
                items[0] = (COPPER, f"Meter-main, {job.new_service_amps} A (new), relocated")
        c.setFont("Helvetica", 8)
        for i, (color, text) in enumerate(items):
            c.setFillColor(color)
            c.rect(lx, ly - i * 16, 8, 8, stroke=0, fill=1)
            c.setFillColor(INK)
            c.drawString(lx + 13, ly - i * 16, text)
        drop_y = ly - len(items) * 16
        c.setStrokeColor(MUTED)
        c.setLineWidth(1.6)
        if _drop(self.packet) == "underground":
            c.setDash(5, 3)
        c.line(lx - 2, drop_y + 3, lx + 10, drop_y + 3)
        c.setDash()
        c.setFillColor(INK)
        c.drawString(lx + 13, drop_y, "Underground lateral" if _drop(self.packet) == "underground"
                     else "Overhead service drop")
        note_y = drop_y
        c.setFont("Helvetica", 7.2)
        c.setFillColor(MUTED)
        for i, note in enumerate(["Schematic, not to scale.", "Field verify the locations.",
                                  f"Service conductors, {job.se_length_ft} ft."]):
            c.drawString(lx, note_y - 14 - i * 11, note)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(INK)
        c.drawString(lx, y(8), "N  ^  (plan up)")


class Riser(Flowable):
    """Utility to meter to main to panel, with the grounding electrodes hung below."""

    def __init__(self, packet: ServicePacket) -> None:
        super().__init__()
        self.packet = packet
        self.width = CONTENT
        self.height = 222

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        packet = self.packet
        job = packet.job
        mid = 170
        box_w = 74
        box_h = 62
        gap = (CONTENT - 4 * box_w) / 3
        xs = [i * (box_w + gap) for i in range(4)]

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

        combo = job.equipment == "meter_main"
        box(xs[0], f"UTILITY ({_drop(packet)})", ["Utility service", "120/240 V", "1-phase"])
        if combo:
            box(xs[1], "METER-MAIN", ["Meter socket", "and main breaker", "in one enclosure"])
            box(xs[2], f"MAIN {job.new_service_amps} A",
                [f"{job.new_service_amps} A, 2-pole", "Main breaker", "in the meter-main"], SOFT)
        else:
            box(xs[1], "METER", ["Utility meter", "Meter socket"])
            box(xs[2], f"MAIN {job.new_service_amps} A",
                [f"{job.new_service_amps} A, 2-pole", "Main breaker", "in the main panel"], SOFT)
        box(xs[3], f"PANEL {job.bus_amps} A bus",
            ["New panel", f"{job.bus_amps} A bus", "Branch circuits"])

        c.setStrokeColor(INK)
        c.setLineWidth(1.5)
        for left, right in zip(xs, xs[1:]):
            c.line(left + box_w, mid, right, mid)

        c.setFillColor(INK)
        utility_x = (xs[0] + box_w + xs[1]) / 2
        c.setFont("Helvetica-Bold", 7.2)
        c.drawCentredString(utility_x, mid + 15, "Service")
        c.setFont("Helvetica", 6.8)
        c.drawCentredString(utility_x, mid + 5, "overhead drop" if _drop(packet) == "overhead" else "lateral")
        label_x = (xs[1] + box_w + xs[2]) / 2
        c.setFont("Helvetica-Bold", 7.2)
        c.drawCentredString(label_x, mid + 15, "Service conductors")
        c.setFont("Helvetica", 6.8)
        c.drawCentredString(label_x, mid + 5, _service_wire(packet))
        c.drawCentredString(label_x, mid - 10, _conduit_text(packet))
        c.drawCentredString(label_x, mid - 20, f"{job.se_length_ft} ft")

        # Grounding electrode conductor down from the main to a rail, then one drop to each electrode.
        main_x = xs[2] + box_w / 2
        rail_y = 104
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.2)
        c.line(main_x, mid - box_h / 2, main_x, rail_y)
        count = len(packet.gecs)
        spacing = 118
        centers = [main_x + (index - (count - 1) / 2) * spacing for index in range(count)]
        if count > 1:
            c.line(centers[0], rail_y, centers[-1], rail_y)
        c.setFillColor(GREEN)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(main_x + 6, rail_y + 8, "Grounding electrode conductor")
        for center, (electrode, size) in zip(centers, packet.gecs.items()):
            c.setStrokeColor(GREEN)
            c.setLineWidth(1.2)
            c.line(center, rail_y, center, rail_y - 18)
            for i, half in enumerate((13, 8, 3)):
                c.line(center - half, rail_y - 18 - i * 4, center + half, rail_y - 18 - i * 4)
            first, second = ELECTRODE_NOTES[electrode]
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(center, rail_y - 42, f"{first}: #{size} Cu")
            c.setFont("Helvetica", 6.8)
            c.drawCentredString(center, rail_y - 52, second)
        c.setFillColor(GREEN)
        c.setFont("Helvetica", 7.2)
        c.drawString(0, 14, "Bond: water pipe, gas pipe")


def _checklist_row(packet: ServicePacket, section: str) -> tuple[str, str]:
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
    if section == "utility":
        return "Page 6: send to the utility", "Send"
    if section == "equipment":
        return "Page 7: add manufacturer sheets", "Attach"
    return f"Page {SECTION_PAGES[section]}", "Ready"


def _cover(packet: ServicePacket) -> list:
    job = packet.job
    jurisdiction = job.jurisdiction
    checklist_cell = (
        f"{jurisdiction.label}\nFrom the city's published checklist"
        if jurisdiction.known_for("service_upgrade")
        else f"{jurisdiction.label}\nGeneral checklist, city rules added in setup"
    )
    parcel = f"\nParcel {job.plan.parcel_number}" if job.plan and job.plan.parcel_number else ""
    return cover_page(
        title=_title(packet),
        address=job.address,
        job_cell=(f"{job.home.square_feet:,} sq ft home{parcel}\n"
                  f"{job.existing_service_amps} A to {job.new_service_amps} A, {_drop(packet)}\n"
                  f"Customer: {job.customer}"),
        contractor_cell=f"{job.contractor}\nLicense {job.license_number}",
        checklist_cell=checklist_cell,
        checklist_rows=[(requirement.item, *_checklist_row(packet, requirement.section))
                        for requirement in jurisdiction.checklist_for("service_upgrade").items],
        checks=[(check.name, check.result, check.passed) for check in packet.checks],
        flags=packet.flags,
    )


def _electrode_scope(packet: ServicePacket) -> str:
    parts = [f"{ELECTRODE_LABELS[electrode].lower()} (#{size} Cu)" for electrode, size in packet.gecs.items()]
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]


def scope_of_work(packet: ServicePacket) -> str:
    job = packet.job
    equipment = "a meter-main combination" if job.equipment == "meter_main" else "a main panel with a separate meter"
    model = f" ({job.panel_model})" if job.panel_model else ""
    if job.scope == "upgrade":
        opening = (f"Upgrade the existing {job.existing_service_amps} A, 120/240 V single-phase service "
                   f"to {job.new_service_amps} A. Install {equipment}{model} with a {job.new_service_amps} A main breaker")
    else:
        opening = (f"Replace the existing {job.existing_service_amps} A main panel with a new "
                   f"{job.new_service_amps} A, 120/240 V single-phase panel{model}. Install {equipment} "
                   f"with a {job.new_service_amps} A main breaker")
    relocated = ", relocating the meter" if job.relocated else ""
    brand = (f" The existing {BRAND_LABELS[job.existing_brand]} panel is being replaced for that reason."
             if job.existing_brand in BRAND_LABELS else "")
    utility = job.utility or "the utility"
    run = (f"{_service_wire(packet)} in {packet.conduit_size} {job.conduit} conduit"
           if packet.conduit_size else f"{_service_wire(packet)} as cable, without conduit")
    return (
        f"{opening}{relocated}. Run new service entrance conductors, {run}, "
        f"{job.se_length_ft} ft from the meter to the main, from an {job.service_drop} service. "
        f"Ground the service with {_electrode_scope(packet)}. Bond the water pipe and the gas pipe. "
        f"Transfer the existing branch circuits to the new panel. "
        f"Coordinate the disconnect and reconnect with {utility}.{brand}"
    )


def application_fields(packet: ServicePacket) -> list[tuple[str, str]]:
    job = packet.job
    kind = "service upgrade" if job.scope == "upgrade" else "panel replacement"
    return [
        ("Project address", job.address),
        ("Parcel number", job.plan.parcel_number if job.plan and job.plan.parcel_number else "Not on file"),
        ("Jurisdiction", job.jurisdiction.label),
        ("Property owner", job.customer),
        ("Permit type", f"Electrical, residential {kind}"),
        ("Service", f"{job.existing_service_amps} A to {job.new_service_amps} A, 120/240 V single-phase"),
        ("Equipment", job.panel_model or "Add make and model"),
        ("Contractor", job.contractor),
        ("License number", job.license_number),
    ]


def _application(packet: ServicePacket) -> list:
    return application_page(
        rows=application_fields(packet),
        scope=scope_of_work(packet),
        inspections=[
            ("Service", "New equipment, grounding and bonding, before the utility reconnects"),
            ("Final", "Panel, breakers, labeling, and working space on site"),
        ],
    )


def _plan_markers(packet: ServicePacket) -> list[PlanMarker]:
    plan = packet.job.plan
    meter, panel = plan.markers["meter"], plan.markers["panel"]
    if meter == panel:
        return [PlanMarker(panel, INK, "M/P")]
    return [PlanMarker(meter, MUTED, "M"), PlanMarker(panel, INK, "P")]


def _site_plan(packet: ServicePacket) -> list:
    job = packet.job
    plan = job.plan
    if plan is None:
        return [
            _p("Site Plan", H1),
            _p("Shows the location of the meter, the main panel and the service.", SMALL),
            Spacer(1, 10),
            SitePlan(packet),
        ]
    together = plan.markers["meter"] == plan.markers["panel"]
    legend = ["M/P  Meter and main panel, same spot" if together else "M  Meter",
              f"P  Main panel, {job.new_service_amps} A (new)"]
    if together:
        legend = [legend[0], f"Main, {job.new_service_amps} A (new)"]
    elif plan.route_points:
        legend.append(f"Meter to panel, {plan.measured_route_ft} ft measured on plan")
    if plan.lot:
        legend.append("Dashed yellow: lot line")
    measures = [f"Service conductors: {job.se_length_ft} ft"]
    setback = plan.distance_to_lot_line_ft(plan.markers["panel"])
    if setback is not None:
        measures.append(f"Panel to nearest lot line: {setback} ft")
    measures.append(f"Scale 1 in = {plan.scale_ft_per_in} ft when printed at 100%")
    measures.append("Not a survey. Field verify all dimensions.")
    return [
        _p("Site Plan", H1),
        _p(job.address + (f". Parcel {plan.parcel_number}." if plan.parcel_number else "."), SMALL),
        Spacer(1, 6),
        AerialSitePlan(plan, markers=_plan_markers(packet), underground=job.service_drop == "underground", width=CONTENT),
        Spacer(1, 6),
        _table([[_p("\n".join(legend)), _p("\n".join(measures))]], [CONTENT / 2, CONTENT / 2], head=False),
        Spacer(1, 3),
        _p(". ".join(credit.rstrip(".") for credit in plan.credits) + ".", CREDIT),
    ]


def _riser(packet: ServicePacket) -> list:
    job = packet.job
    rows = [
        ["Service conductors", f"{_service_wire(packet)}, {packet.conductor.ampacity_75c} A at 75\N{DEGREE SIGN}C",
         _conduit_text(packet), f"{job.new_service_amps} A, 2-pole main"],
    ]
    rows += [
        [f"GEC to {ELECTRODE_LABELS[electrode].lower()}", f"1 #{size} Cu",
         "Raceway or armor (250.64(B))" if size == "8" else "Per 250.64(B)",
         "Listed clamp or weld (250.70)"]
        for electrode, size in packet.gecs.items()
    ]
    return [
        _p("Riser Diagram", H1),
        _p("Service conductors, conduit, grounding electrode conductors and bonding.", SMALL),
        Spacer(1, 10),
        Riser(packet),
        Spacer(1, 10),
        _p("Conductor and conduit schedule", H2),
        _table([_heads("Segment", "Conductors", "Conduit", "Protection")]
               + [[_p(cell) for cell in row] for row in rows],
               [1.6 * inch, 1.9 * inch, 1.6 * inch, CONTENT - 5.1 * inch]),
    ]


def _load(packet: ServicePacket) -> list:
    job = packet.job
    load = packet.load
    existing = packet.existing_load
    spare = (
        f"{load.spare_amps:.1f} A on the new service"
        if load.spare_amps >= 0
        else f"Over by {-load.spare_amps:.1f} A, so this needs a fix before submittal"
    )
    return load_page(
        load,
        method=f"Optional dwelling method, {job.jurisdiction.code_name} 220.82, with planned loads added at 100% "
               f"of nameplate, on the new {job.new_service_amps} A service. Confirm the method the city accepts.",
        service_rows=[
            ("New service", f"{job.new_service_amps} A"),
            ("Existing service", f"{job.existing_service_amps} A, {existing.percent_of_service:.0f}% used by this load"),
            ("Spare capacity", spare),
        ],
    )


def _utility(packet: ServicePacket) -> list:
    job = packet.job
    rows = [
        ("Utility", job.utility or "Add the utility"),
        ("Service address", job.address),
        ("Customer", job.customer),
        ("Meter number", job.meter_number or "Add from the meter"),
        ("Existing service", f"{job.existing_service_amps} A"),
        ("New service", f"{job.new_service_amps} A, 120/240 V single-phase"),
        ("Service type", "Overhead" if job.service_drop == "overhead" else "Underground"),
        ("Meter location", "Relocated, needs the utility's approval" if job.relocated else "Same location"),
        ("Contractor and license", f"{job.contractor}, license {job.license_number}"),
        ("Requested disconnect", "Date and time: ______________________"),
        ("Requested reconnect", "Date and time: ______________________"),
    ]
    return [
        _p("Utility Service Request Data", H1),
        _p("Prepared for transfer to the utility's service request. This page is not the utility's form.", SMALL),
        Spacer(1, 10),
        _table([[_p(a, CELL_BOLD), _p(b)] for a, b in rows], [2.4 * inch, CONTENT - 2.4 * inch], head=False),
    ]


def _equipment(packet: ServicePacket) -> list:
    job = packet.job
    jurisdiction_code = job.jurisdiction.code_name
    rows = [
        ("New service equipment",
         f"{job.panel_model or 'Add make and model'}, {job.bus_amps} A bus, {job.new_service_amps} A main, "
         f"{EQUIPMENT_LABELS[job.equipment].lower()}",
         "Attach manufacturer data and NRTL listing"),
        ("Service conductors",
         f"{_service_wire(packet)}, {_conduit_text(packet)}, {job.se_length_ft} ft",
         f"Listed, {jurisdiction_code} 310.12"),
        ("Grounding",
         "; ".join(f"{ELECTRODE_LABELS[electrode]}, #{size} Cu" for electrode, size in packet.gecs.items()),
         f"{jurisdiction_code} 250.66"),
    ]
    return [
        _p("Equipment Data", H1),
        _p("Attach the manufacturer's data sheets and listing information behind this page.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Listing")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, CONTENT - 3.4 * inch, 1.9 * inch]),
    ]


def _review(packet: ServicePacket) -> list:
    items = [
        "Existing loads match the home",
        "Utility service request submitted",
        "Service conductor size and material confirmed",
        "Grounding electrodes verified on site",
        "Water and gas bonds in place",
        "Working space at the panel",
        "Equipment data attached",
        "Code edition confirmed with the city",
    ]
    if packet.job.has_solar:
        items.append("Solar 120% rule confirmed")
    if packet.job.jurisdiction.state == "CA":
        items.append("Smoke and CO alarm requirement confirmed")
    return review_page(items)


def render_service_packet_pdf(packet: ServicePacket) -> bytes:
    return build_document(
        [_cover(packet), _application(packet), _site_plan(packet), _riser(packet),
         _load(packet), _utility(packet), _equipment(packet), _review(packet)],
        title=f"{_title(packet)} (demo)",
    )
