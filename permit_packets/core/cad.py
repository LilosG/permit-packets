"""CAD export: the packet's drawing sheets as DXF files that open in AutoCAD.

The PDF is drawn with canvas calls. While a CadSink is collecting, the PDF canvas also notes each line,
box, circle, path and piece of text in absolute page points as it is drawn, so the DXF is the same drawing
as the PDF rather than a second drawing to keep in step. Nothing is recorded, and ezdxf is not imported,
unless a CAD file was asked for.

Two kinds of sheet come out:
- A sheet with a measured site plan: the plan is in model space in feet at true scale, and a layout at the
  sheet's size carries the title block and a viewport onto the plan at the printed scale.
- Every other drawing sheet (one-line, riser, schematic site plan): model space in plotted inches, so a
  unit is the inch the sheet prints at.
The panel schedule is built from its circuit rows, as a real grid of lines and text.
"""
from __future__ import annotations

import math
import zipfile
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from io import BytesIO, StringIO

CAD_SINK: ContextVar["CadSink | None"] = ContextVar("cad_sink", default=None)

# Sheets that become a file, by the sheet title in the title block.
SHEET_FILES = {"Site Plan": "site-plan", "One-Line Diagram": "one-line", "Riser Diagram": "riser"}

LAYERS = {
    "C-PROP-LINE": 3, "A-BLDG-OTLN": 8, "E-POWR-WIRE": 30, "E-POWR-EQPM": 5, "E-ANNO-SYMB": 1,
    "E-ANNO-TEXT": 7, "E-ANNO-LINE": 7, "G-ANNO-NPLT": 7, "G-ANNO-BORD": 8, "G-TTLB": 8,
    "E-PNLS-GRID": 7, "E-PNLS-TEXT": 7,
}
COPPER_RGB = (0xA8, 0x55, 0x1F)  # the conductor colour the drawings use; see pdf_base.COPPER


@dataclass
class CadPage:
    title: str
    ops: list[dict]
    size: tuple[float, float]  # the page's width and height in points
    site: dict | None = None  # {"origin": (x, y), "side": points, "ft_per_in": feet one inch of drawing covers}


@dataclass
class PanelData:
    panels: list[tuple[str, list]]
    header: list[tuple[str, str]] | None
    entered: bool
    landscape: bool
    spaces_note: str | None


@dataclass
class CadSink:
    pages: list[CadPage] = field(default_factory=list)
    panel_data: PanelData | None = None
    magnification: float = 1.0


@contextmanager
def collect_cad():
    sink = CadSink()
    token = CAD_SINK.set(sink)
    try:
        yield sink
    finally:
        CAD_SINK.reset(token)


def note_panels(panels, header, entered: bool, landscape: bool, spaces_note: str | None) -> None:
    sink = CAD_SINK.get()
    if sink is not None:
        sink.panel_data = PanelData(list(panels), header, entered, landscape, spaces_note)


def cad_layer(canvas, layer: str | None) -> None:
    """Name the layer the drawing calls that follow go on; None goes back to choosing by what they are."""
    if getattr(canvas, "_cad_on", False):
        canvas._cad_layer = layer


def cad_site(canvas, left: float, side: float, ft_per_in: float) -> None:
    """The calls that follow draw a measured plan, `side` points square with its lower left at `left`."""
    if getattr(canvas, "_cad_on", False):
        canvas._cad_space = "site"
        canvas._cad_site = {"origin": canvas._cad_point(left, 0), "side": side, "ft_per_in": ft_per_in}


def cad_site_end(canvas) -> None:
    if getattr(canvas, "_cad_on", False):
        canvas._cad_space = ""
        canvas._cad_layer = None


def _rgb(color) -> tuple[int, int, int] | None:
    try:
        return round(color.red * 255), round(color.green * 255), round(color.blue * 255)
    except AttributeError:
        return None


class CadRecording:
    """Mixed into the PDF canvas. Records drawing calls only while a CadSink is collecting."""

    def _cad_init(self) -> None:
        self._cad_on = CAD_SINK.get() is not None
        self._cad_reset()

    def _cad_reset(self) -> None:
        self._cad_ops: list[dict] = []
        self._cad_layer: str | None = None
        self._cad_space = ""
        self._cad_site: dict | None = None

    def _cad_point(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self._currentMatrix
        return a * x + c * y + e, b * x + d * y + f

    def _cad_scale(self) -> float:
        a, b, c, d, *_ = self._currentMatrix
        return math.sqrt(abs(a * d - b * c))

    def _cad_note(self, kind: str, **data) -> None:
        self._cad_ops.append({
            "kind": kind, "layer": self._cad_layer, "space": self._cad_space,
            "stroke": _rgb(self._strokeColorObj), "fill": _rgb(self._fillColorObj),
            "width": self._lineWidth * self._cad_scale(), "dash": bool(self._lineDash), **data,
        })

    def _cad_shape(self, points, *, closed: bool, stroke, fill) -> None:
        self._cad_note("poly", pts=[self._cad_point(x, y) for x, y in points], closed=closed,
                       stroked=bool(stroke), filled=bool(fill))

    def _cad_text(self, x: float, y: float, text: str, align: str) -> None:
        a, b, *_ = self._currentMatrix
        self._cad_note("text", at=self._cad_point(x, y), text=str(text), align=align,
                       font=self._fontname, size=self._fontsize * self._cad_scale(),
                       angle=math.degrees(math.atan2(b, a)))

    def line(self, x1, y1, x2, y2):
        super().line(x1, y1, x2, y2)
        if self._cad_on:
            self._cad_shape([(x1, y1), (x2, y2)], closed=False, stroke=1, fill=0)

    def lines(self, linelist):
        super().lines(linelist)
        if self._cad_on:
            for x1, y1, x2, y2 in linelist:
                self._cad_shape([(x1, y1), (x2, y2)], closed=False, stroke=1, fill=0)

    def rect(self, x, y, width, height, stroke=1, fill=0):
        super().rect(x, y, width, height, stroke=stroke, fill=fill)
        if self._cad_on:
            self._cad_shape([(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
                            closed=True, stroke=stroke, fill=fill)

    def roundRect(self, x, y, width, height, radius, stroke=1, fill=0):
        super().roundRect(x, y, width, height, radius, stroke=stroke, fill=fill)
        if self._cad_on:  # corners are drawn square in CAD
            self._cad_shape([(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
                            closed=True, stroke=stroke, fill=fill)

    def circle(self, x_cen, y_cen, r, stroke=1, fill=0):
        super().circle(x_cen, y_cen, r, stroke=stroke, fill=fill)
        if self._cad_on:
            self._cad_note("circle", at=self._cad_point(x_cen, y_cen), radius=r * self._cad_scale(),
                           stroked=bool(stroke), filled=bool(fill))

    def drawPath(self, aPath, stroke=1, fill=0, fillMode=None):
        super().drawPath(aPath, stroke=stroke, fill=fill, fillMode=fillMode)
        if not self._cad_on:
            return
        points: list[tuple[float, float]] = []
        closed = False
        for code in aPath._code:
            parts = code.split()
            if not parts:
                continue
            op = parts[-1]
            if op in ("m", "l"):
                points.append((float(parts[0]), float(parts[1])))
            elif op == "c":  # a curve is kept by its end point
                points.append((float(parts[-3]), float(parts[-2])))
            elif op == "h":
                closed = True
        if len(points) > 1:
            self._cad_shape(points, closed=closed, stroke=stroke, fill=fill)

    def drawString(self, x, y, text, *args, **kwargs):
        super().drawString(x, y, text, *args, **kwargs)
        if self._cad_on:
            self._cad_text(x, y, text, "l")

    def drawCentredString(self, x, y, text, *args, **kwargs):
        super().drawCentredString(x, y, text, *args, **kwargs)
        if self._cad_on:
            self._cad_text(x, y, text, "c")

    def drawRightString(self, x, y, text, *args, **kwargs):
        super().drawRightString(x, y, text, *args, **kwargs)
        if self._cad_on:
            self._cad_text(x, y, text, "r")


# ---------------------------------------------------------------------------------------------- DXF

def _layer_for(op: dict) -> str:
    if op["layer"]:
        return op["layer"]
    if op["kind"] == "text":
        return "E-ANNO-TEXT"
    stroke, fill = op["stroke"], op["fill"]
    if op.get("stroked") and stroke is not None and all(abs(a - b) <= 6 for a, b in zip(stroke, COPPER_RGB)):
        return "E-POWR-WIRE"
    if op.get("filled") and fill is not None and fill != (255, 255, 255):
        return "E-POWR-EQPM"
    if op["kind"] == "poly" and op.get("stroked") and not op["closed"] and op["width"] >= 0.9:
        return "E-POWR-WIRE"  # a heavy open line on these sheets is a conductor or a riser
    return "E-ANNO-LINE"


def _lineweight(width_pt: float) -> int:
    from ezdxf.lldxf.const import VALID_DXF_LINEWEIGHTS

    hundredths_mm = width_pt * 0.3528 * 100
    return min((w for w in VALID_DXF_LINEWEIGHTS if w >= 0), key=lambda w: abs(w - hundredths_mm))


def _new_doc(units: int):
    import ezdxf

    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = units  # 1 inches, 2 feet
    doc.header["$MEASUREMENT"] = 0
    doc.styles.add("LILOS", font="arial.ttf")
    doc.styles.add("LILOS-BOLD", font="arialbd.ttf")
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)
    return doc


def _emit(ops: list[dict], target, to_xy, length: float, ltscale: float) -> None:
    """Draw recorded ops into `target`. `to_xy` maps a page point to drawing units; `length` is units per point."""
    from ezdxf.enums import TextEntityAlignment

    aligns = {"l": TextEntityAlignment.BOTTOM_LEFT, "c": TextEntityAlignment.BOTTOM_CENTER,
              "r": TextEntityAlignment.BOTTOM_RIGHT}
    for op in ops:
        layer = _layer_for(op)
        base = {"layer": layer}
        if op["kind"] == "text":
            if not op["text"].strip():
                continue
            color = op["fill"] or (0, 0, 0)
            if color == (255, 255, 255):
                continue
            height = op["size"] * length * 0.72  # a font's size is taller than its capitals
            entity = target.add_text(op["text"], height=height, rotation=op["angle"], dxfattribs={
                **base, "style": "LILOS-BOLD" if "Bold" in op["font"] else "LILOS", **_color_attrs(color)})
            entity.set_placement(to_xy(op["at"]), align=aligns[op["align"]])
            continue
        stroke, fill = op["stroke"], op["fill"]
        outline = {**base, "lineweight": _lineweight(op["width"]), **_color_attrs(stroke)}
        if op["dash"]:
            outline.update(linetype="DASHED", ltscale=ltscale)
        drawn_stroke = op.get("stroked") and stroke != (255, 255, 255)  # white strokes are halos on the photo
        # Pale panel fills are left out: behind text they would hide it on AutoCAD's black screen.
        drawn_fill = op.get("filled") and fill is not None and _luminance(fill) < 0.85
        if op["kind"] == "circle":
            cx, cy = to_xy(op["at"])
            radius = op["radius"] * length
            if drawn_fill:
                hatch = target.add_hatch(dxfattribs={**base, **_color_attrs(fill)})
                hatch.paths.add_edge_path().add_arc((cx, cy), radius, 0, 360)
            if drawn_stroke:
                target.add_circle((cx, cy), radius, dxfattribs=outline)
            continue
        points = [to_xy(p) for p in op["pts"]]
        if drawn_fill and op["closed"] and len(points) > 2:
            hatch = target.add_hatch(dxfattribs={**base, **_color_attrs(fill)})
            hatch.paths.add_polyline_path(points, is_closed=True)
        if drawn_stroke:
            target.add_lwpolyline(points, close=op["closed"], dxfattribs=outline)


def _luminance(color: tuple[int, int, int]) -> float:
    r, g, b = color
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _color_attrs(color: tuple[int, int, int] | None) -> dict:
    """The drawings' dark ink becomes AutoCAD's automatic colour (white on its black screen, black on paper),
    since navy would vanish on the black model space."""
    from ezdxf import colors as dxf_colors

    color = color or (0, 0, 0)
    if _luminance(color) < 0.33:
        return {"color": 7}
    return {"true_color": dxf_colors.rgb2int(color)}


def _doc_bytes(doc) -> bytes:
    buffer = StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode("utf-8")


def _sheet_dxf(page: CadPage, mag: float) -> bytes:
    site = page.site
    if site is None:
        doc = _new_doc(1)
        factor = mag / 72
        _emit(page.ops, doc.modelspace(), lambda p: (p[0] * factor, p[1] * factor), factor, 0.25)
        return _doc_bytes(doc)
    doc = _new_doc(2)
    ft = site["ft_per_in"]
    ox, oy = site["origin"]
    to_feet = lambda p: ((p[0] - ox) / 72 * ft, (p[1] - oy) / 72 * ft)
    _emit([o for o in page.ops if o["space"] == "site"], doc.modelspace(), to_feet, ft / 72, 0.25 * ft / mag)
    layout = doc.layouts.new("SHEET")
    width, height = page.size[0] / 72 * mag, page.size[1] / 72 * mag
    layout.page_setup(size=(width, height), margins=(0, 0, 0, 0), units="inch")
    factor = mag / 72
    _emit([o for o in page.ops if o["space"] != "site"], layout, lambda p: (p[0] * factor, p[1] * factor), factor, 0.25)
    side = site["side"]
    layout.add_viewport(
        center=((ox + side / 2) / 72 * mag, (oy + side / 2) / 72 * mag),
        size=(side / 72 * mag, side / 72 * mag),
        view_center_point=(side / 2 / 72 * ft, side / 2 / 72 * ft),
        view_height=side / 72 * ft,
    )
    doc.layout = layout  # open on the sheet
    return _doc_bytes(doc)


COLUMNS = (("CIRCUIT", 3.6), ("BREAKER", 0.9), ("POLES", 0.7), ("STATUS", 1.1))
ROW_H = 0.26
TEXT_H = 0.1
NUMBER_W = 0.5


def _panel_dxf(data: PanelData) -> bytes:
    from permit_packets.core.panel_schedule import FIELD_VERIFY, GRID_ROWS, ScheduleRow

    doc = _new_doc(1)
    msp = doc.modelspace()

    def text(x, y, value, *, bold=False, height=TEXT_H, layer="E-PNLS-TEXT"):
        if value:
            msp.add_text(str(value), height=height, dxfattribs={
                "layer": layer, "style": "LILOS-BOLD" if bold else "LILOS"}).set_placement((x, y))

    def line(x1, y1, x2, y2):
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "E-PNLS-GRID"})

    y = 0.0
    text(0, y, "PANEL SCHEDULE", bold=True, height=0.2)
    y -= 0.4
    if data.header:
        x = 0.0
        for label, value in data.header:
            text(x, y, label.upper(), height=0.07)
            text(x, y - 0.17, value, bold=True)
            x += 1.7
        y -= 0.5
    for heading, rows in data.panels:
        text(0, y, heading, bold=True, height=0.14)
        y -= 0.3
        numbered = not data.entered
        if numbered:
            blanks = [ScheduleRow("", "", 0, "") for _ in range(GRID_ROWS[data.landscape])]
            blanks[0] = ScheduleRow(FIELD_VERIFY, "", 0, "")
            rows = [*rows, *blanks]
        widths = ([NUMBER_W] if numbered else []) + [w for _, w in COLUMNS]
        heads = (["CKT"] if numbered else []) + [name for name, _ in COLUMNS]
        total = sum(widths)
        xs = [sum(widths[:i]) for i in range(len(widths) + 1)]
        top = y
        for x, head in zip(xs, heads):
            text(x + 0.06, y - 0.18, head, bold=True, height=0.08)
        y -= ROW_H
        line(0, y, total, y)
        for index, row in enumerate(rows, start=1):
            values = ([str(index)] if numbered else []) + [row.label, row.breaker, str(row.poles) if row.poles else "", row.status]
            for x, value in zip(xs, values):
                text(x + 0.06, y - 0.18, value, bold=row.status == "New")
            y -= ROW_H
            line(0, y, total, y)
        for x in xs:
            line(x, top, x, y)
        line(0, top, total, top)
        y -= 0.5
    if data.spaces_note:
        text(0, y, data.spaces_note)
        y -= 0.3
    return _doc_bytes(doc)


def dxf_files(sink: CadSink, stem: str) -> dict[str, bytes]:
    """Every file name with its DXF bytes."""
    files: dict[str, bytes] = {}
    for page in sink.pages:
        kind = SHEET_FILES.get(page.title)
        if not kind:
            continue
        name = f"{stem}-{kind}.dxf"
        number = 2
        while name in files:
            name = f"{stem}-{kind}-{number}.dxf"
            number += 1
        files[name] = _sheet_dxf(page, sink.magnification)
    if sink.panel_data:
        files[f"{stem}-panel-schedule.dxf"] = _panel_dxf(sink.panel_data)
    return files


def zip_files(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()
