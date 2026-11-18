"""Render a panel / service upgrade permit packet as an 8-page draft PDF.

The checklist comes from the job's jurisdiction. The site plan is the property
to scale when there's a plan, and a labeled schematic when there isn't.
"""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, Spacer

from permit_packets.core.conductors import wire_label
from permit_packets.core.equipment import attach_data_sheets, find_equipment
from permit_packets.core.panel_schedule import (
    PANEL_SCHEDULE_ITEM, ScheduleRow, existing_rows, panel_schedule_page, panel_schedule_row,
)
from permit_packets.core.pdf_base import (
    CELL_BOLD, CONTENT, COPPER, CREDIT, GREEN, H1, H2, INK, MUTED, PALE, SMALL, SOFT,
    diagram, fit_page, heat_block, _heads, _p, _table, content_w, application_page, build_document, cover_page, load_page, review_page,
)
from permit_packets.core.panel_data import checklist_row as panel_row, one_line_data, panel_header
from permit_packets.core.title_block import title_block_for
from permit_packets.core.site_plan import PlanMarker, plan_print, printed_scale, site_plan_page
from permit_packets.job_types.service_upgrade.calc import (
    BRAND_LABELS,
    ELECTRODE_LABELS,
    EQUIPMENT_LABELS,
    MATERIAL_ABBREVIATIONS,
    EMERGENCY_MARKINGS,
    SPD_LABELS,
    ServicePacket,
    emergency_line,
)

SECTION_PAGES = {
    "application": 2, "site_plan": 3, "one_line": 4, "load": 5, "panel_schedule": 6, "utility": 7, "equipment": 8,
    "review": 9,
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
    wire = f"3 {wire_label(packet.conductor.size)} {_metal(packet)} THWN-2"
    return f"{wire} + 1 #{packet.feeder_egc} {_metal(packet)} EGC" if packet.feeder_egc else wire


def _run_name(packet: ServicePacket) -> str:
    """What the measured run is: service conductors to a main panel, or a feeder from a meter-main to the panel."""
    return "Feeder, meter-main to panel" if packet.is_meter_main else "Service conductors"


def _utility_name(packet: ServicePacket) -> str:
    return packet.job.utility or packet.job.jurisdiction.utility


def _conduit_text(packet: ServicePacket) -> str:
    return f"{packet.conduit_size} {packet.raceway}" if packet.conduit_size else "Cable, no conduit"


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
                                  f"{_run_name(self.packet)}, {job.se_length_ft} ft."]):
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
            c.setFont("Helvetica", 6.6)
            c.drawCentredString(xs[1] + box_w / 2, mid - box_h / 2 - 9, "Outdoors: also the emergency")
            c.drawCentredString(xs[1] + box_w / 2, mid - box_h / 2 - 17, "disconnect (NEC 230.85)")
            box(xs[2], f"MAIN {job.new_service_amps} A",
                [f"{job.new_service_amps} A, 2-pole", "Main breaker", "in the meter-main"], SOFT)
        else:
            if packet.emergency == "meter_disconnect":
                box(xs[1], "METER + DISCONNECT",
                    ["Meter socket", f"{job.new_service_amps} A meter", "disconnect, outdoors"])
            else:
                box(xs[1], "METER", ["Utility meter", "Meter socket"])
            box(xs[2], f"MAIN {job.new_service_amps} A",
                [f"{job.new_service_amps} A, 2-pole", "Main breaker", "outdoor main panel" if job.main_outdoors
                 else "in the main panel"], SOFT)
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
        if packet.mast_conduit:  # the contractor's mast: weatherhead down to the meter
            c.drawCentredString(utility_x, mid - 10, f"Mast: 3 {wire_label(packet.conductor.size)} {_metal(packet)}")
            c.drawCentredString(utility_x, mid - 20, f"in {packet.mast_conduit} RMC")
        # Service conductors run meter to main panel. In a meter-main the meter and main share an enclosure and
        # the measured run is the feeder from the main to the panel.
        run_left = xs[2] if combo else xs[1]
        same_left = xs[1] if combo else xs[2]
        label_x = (run_left + box_w + run_left + box_w + gap) / 2
        wire = _service_wire(packet)
        if packet.feeder_egc:
            # Wires above the connecting line, conduit and length below it.
            c.setFont("Helvetica-Bold", 7.2)
            c.drawCentredString(label_x, mid + 24, "Feeder")
            c.setFont("Helvetica", 6.8)
            c.drawCentredString(label_x, mid + 14, f"3 {wire_label(packet.conductor.size)} {_metal(packet)} THWN-2")
            c.drawCentredString(label_x, mid + 5, f"+ 1 #{packet.feeder_egc} {_metal(packet)} EGC")
            c.drawCentredString(label_x, mid - 10, _conduit_text(packet))
            c.drawCentredString(label_x, mid - 20, f"{job.se_length_ft} ft")
        else:
            c.setFont("Helvetica-Bold", 7.2)
            c.drawCentredString(label_x, mid + 15, "Service conductors")
            c.setFont("Helvetica", 6.8)
            c.drawCentredString(label_x, mid + 5, wire)
            c.drawCentredString(label_x, mid - 10, _conduit_text(packet))
            c.drawCentredString(label_x, mid - 20, f"{job.se_length_ft} ft")
        same_x = (same_left + box_w + same_left + box_w + gap) / 2
        c.setFont("Helvetica", 6.4)
        c.setFillColor(MUTED)
        c.drawCentredString(same_x, mid - 10, "same enclosure")
        c.setFillColor(INK)

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
            return f"Page 3: to scale, 1 in = {printed_scale(plan)} ft", "Ready"
        return "Page 3: schematic only, replace it", "Open"
    if section == "surge":
        if job.surge_protection in SPD_LABELS:
            return f"Page {SECTION_PAGES['one_line']}: {SPD_LABELS[job.surge_protection]} SPD on the riser", "Ready"
        return f"Page {SECTION_PAGES['one_line']}: choose the surge protective device", "Open"
    if section == "emergency_disconnect":
        if job.scope == "replacement" and not job.relocated:
            return "Not required: same size service, nothing relocated", "Ready"
        if job.equipment == "meter_main":
            return (f"Page {SECTION_PAGES['one_line']}: the outdoor meter-main breaker is the emergency "
                    "disconnect"), "Ready"
        return f"Page {SECTION_PAGES['one_line']}: add an outdoor emergency disconnect (NEC 230.85)", "Open"
    if section == "gec":
        return f"Page {SECTION_PAGES['one_line']}: GEC sizes in the conductor schedule", "Ready"
    shown = panel_row(job, section, SECTION_PAGES["one_line"])
    if shown:
        return shown
    if section == "utility":
        return f"Page {SECTION_PAGES['utility']}: send to the utility", "Send"
    if section == "equipment":
        if find_equipment(job.panel_model, "panel"):
            return f"Page {SECTION_PAGES['equipment']} + manufacturer data sheet", "Ready"
        if job.data_sheet_attached:
            return f"Page {SECTION_PAGES['equipment']} + data sheet attached by the electrician", "Ready"
        return f"Page {SECTION_PAGES['equipment']}: add manufacturer sheets", "Attach"
    if section not in SECTION_PAGES:
        # A requirement this packet has no page for is never shown as done.
        return "Not in this packet: add it by hand", "Open"
    return f"Page {SECTION_PAGES[section]}", "Ready"


def checklist_rows(packet) -> list[tuple[str, str, str]]:
    """Every checklist line: the city's, then the panel schedule every packet carries."""
    job = packet.job
    rows = [(requirement.item, *_checklist_row(packet, requirement.section))
            for requirement in job.jurisdiction.checklist_for("service_upgrade").items]
    return rows + [(PANEL_SCHEDULE_ITEM, *panel_schedule_row(job, SECTION_PAGES["panel_schedule"]))]


def _cover(packet: ServicePacket) -> list:
    job = packet.job
    jurisdiction = job.jurisdiction
    checklist_cell = (
        f"{jurisdiction.label}\n{jurisdiction.checklist_for('service_upgrade').source_label}"
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
        checklist_rows=checklist_rows(packet),
        checks=[(check.name, check.result, check.passed) for check in packet.checks],
        flags=packet.flags,
        stamp_box_in=job.jurisdiction.stamp_box_in,
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
    utility = _utility_name(packet) or "the utility"
    run = (f"{_service_wire(packet)} in {packet.conduit_size} {packet.raceway} conduit"
           if packet.conduit_size else f"{_service_wire(packet)} as cable, without conduit")
    mast = (f"Install a new service mast and weatherhead with 3 {wire_label(packet.conductor.size)} {_metal(packet)} "
            f"THWN-2 service-entrance conductors in {packet.mast_conduit} RMC down to the "
            f"{'meter-main' if packet.is_meter_main else 'meter'}. " if packet.mast_conduit else "")
    if job.service_drop == "overhead" and not packet.mast_conduit:
        mast = "Keep the existing service mast and conductors; confirm they are rated for the service. "
    if packet.is_meter_main:
        conductors = (f"{mast}The {job.service_drop} service lands in the meter-main. Run a feeder from the meter-main to "
                      f"the panel, {run}, {job.se_length_ft} ft, with the panel's neutral isolated from ground "
                      f"(NEC 250.24(A)(5)). ")
    else:
        conductors = (f"{mast}Run new service entrance conductors, {run}, {job.se_length_ft} ft from the meter to the "
                      f"main, from an {job.service_drop} service. ")
    return (
        f"{opening}{relocated}. {conductors}{emergency_line(job, packet.emergency)}. "
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
            diagram(SitePlan(packet), share=0.8),
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
    measures = [f"{_run_name(packet)}: {job.se_length_ft} ft"]
    setback = plan.distance_to_lot_line_ft(plan.markers["panel"])
    if setback is not None:
        measures.append(f"Panel to nearest lot line: {setback} ft")
    return site_plan_page(
        address=job.address, plan=plan, markers=_plan_markers(packet), underground=job.service_drop == "underground",
        legend=legend, measures=measures, outline_over_aerial=job.jurisdiction.outline_over_aerial,
    )


def _emergency_legend(packet: ServicePacket) -> list[str]:
    """One short line: the full marking is in the checks, the scope and the equipment page."""
    if packet.emergency == "main":
        return ["Emergency disconnect: the main breaker, outdoors (230.85(1))"]
    return ["Emergency disconnect: meter disconnect, outdoors (230.85(2))"]


def _surge_line(job) -> list[str]:
    if job.surge_protection not in SPD_LABELS:
        return []
    return [f"Surge protective device: {SPD_LABELS[job.surge_protection]}, at the service (NEC 230.67)"]


def _riser(packet: ServicePacket) -> list:
    job = packet.job
    rows = [
        [_run_name(packet), f"{_service_wire(packet)}, {packet.conductor.ampacity_75c} A at 75\N{DEGREE SIGN}C",
         _conduit_text(packet),
         f"{job.new_service_amps} A, 2-pole main" + (" in the meter-main" if packet.is_meter_main else "")],
    ]
    if packet.emergency == "meter_disconnect":
        rows.insert(0, ["Meter disconnect", f"{job.new_service_amps} A, outdoor", "At the meter",
                        "Emergency disconnect (230.85(2))"])
    if packet.mast_conduit:
        rows.insert(0, ["Service mast, weatherhead to meter",
                        f"3 {wire_label(packet.conductor.size)} {_metal(packet)} THWN-2, {packet.conductor.ampacity_75c} A "
                        f"at 75\N{DEGREE SIGN}C", f"{packet.mast_conduit} RMC mast, weatherhead",
                        "Overload protection at the main (230.90)"])
    rows += [
        [f"GEC to {ELECTRODE_LABELS[electrode].lower()}", f"1 #{size} Cu",
         "Raceway or armor (250.64(B))" if size == "8" else "Per 250.64(B)",
         "Listed clamp or weld (250.70)"]
        for electrode, size in packet.gecs.items()
    ]
    story = [
        _p("Riser Diagram", H1),
        _p("Service conductors, conduit, grounding electrode conductors and bonding.", SMALL),
        Spacer(1, 10),
        diagram(Riser(packet), legend=one_line_data(packet.job) + _emergency_legend(packet) + _surge_line(job)),
        Spacer(1, 10),
        _p("Conductor and conduit schedule", H2),
        _table([_heads("Segment", "Conductors", "Conduit", "Protection")]
               + [[_p(cell) for cell in row] for row in rows],
               [1.6 * inch, 1.9 * inch, 1.6 * inch, content_w() - 5.1 * inch]),
    ]
    return fit_page(story + heat_block(packet.heat, job.jurisdiction))


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
        ("Utility", _utility_name(packet) or "Add the utility"),
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
        _table([[_p(a, CELL_BOLD), _p(b)] for a, b in rows], [2.4 * inch, content_w() - 2.4 * inch], head=False),
    ]


def _main_text(job, sheet) -> str:
    """The main as the data sheet has it; a main-lug panel has no main breaker to print."""
    if sheet and sheet.main == "lug":
        return "main lugs (no main breaker)"
    return f"{sheet.main_amps if sheet and sheet.main_amps else job.new_service_amps} A main breaker"


def _equipment(packet: ServicePacket) -> list:
    job = packet.job
    jurisdiction_code = job.jurisdiction.code_name
    sheet = find_equipment(job.panel_model, "panel")
    extra = []
    if packet.emergency == "meter_disconnect":
        extra.append(("Meter disconnect", f"{job.new_service_amps} A, outdoor, suitable for use as service equipment, "
                     f"marked \"{EMERGENCY_MARKINGS['meter_disconnect']}\"", f"{jurisdiction_code} 230.85(2)"))
    rows = [
        ("New service equipment",
         f"{sheet.name if sheet else job.panel_model or 'Add make and model'}, "
         f"{sheet.bus_amps if sheet and sheet.bus_amps else job.bus_amps} A bus, {_main_text(job, sheet)}, "
         f"{EQUIPMENT_LABELS[job.equipment].lower()}",
         sheet.listing if sheet else "Attach manufacturer data and NRTL listing"),
        (_run_name(packet),
         f"{_service_wire(packet)}, {_conduit_text(packet)}, {job.se_length_ft} ft",
         f"Listed, {jurisdiction_code} 310.12"),
        ("Grounding",
         "; ".join(f"{ELECTRODE_LABELS[electrode]}, #{size} Cu" for electrode, size in packet.gecs.items()),
         f"{jurisdiction_code} 250.66"),
    ] + extra
    return [
        _p("Equipment Data", H1),
        _p(f"The {sheet.name} data sheet from the manufacturer follows this page." if sheet else
           "Attach the manufacturer's data sheets and listing information behind this page.", SMALL),
        Spacer(1, 10),
        _table([_heads("Item", "Specification", "Listing")] + [[_p(a), _p(b), _p(c)] for a, b, c in rows],
               [1.5 * inch, content_w() - 3.4 * inch, 1.9 * inch]),
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


def _panel_schedule(packet: ServicePacket) -> list:
    job = packet.job
    rows = existing_rows(job.existing_circuits, status="Transferred")
    rows += [ScheduleRow(f"{item.label} ({item.va:,} VA)", "Space reserved", 2 if item.va > 2400 else 1, "Planned")
             for item in job.planned_loads]
    return panel_schedule_page(
        [(f"New panel, {job.bus_amps} A bus, {job.new_service_amps} A main", rows)],
        entered=bool(job.existing_circuits),
        header=panel_header(job),
    )


def render_service_packet_pdf(packet: ServicePacket) -> bytes:
    pdf = build_document(
        [_cover(packet), _application(packet), _site_plan(packet), _riser(packet),
         _load(packet), _panel_schedule(packet), _utility(packet), _equipment(packet), _review(packet)],
        title=_title(packet),
        block=title_block_for(packet.job),
        sheet_titles=["Checklist and Checks","Permit Application Data","Site Plan","Riser Diagram","Load Calculation","Panel Schedule","Utility Service Request","Equipment Data","Pre-Submittal Review"],
    )
    sheet = find_equipment(packet.job.panel_model, "panel")
    return attach_data_sheets(pdf, [sheet] if sheet else [], after_title="Equipment Data")
