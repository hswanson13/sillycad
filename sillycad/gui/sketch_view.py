"""The 2D sketch canvas: grid, zoom/pan, drawing tools, picking and dragging.

Scene coordinates are sketch millimetres with y pointing up (the view is
flipped). The scene is rebuilt from the model after every change; sketches
are small, so this is fast and keeps the model the single source of truth.
Picking is done with plain geometry math in pixels, not Qt item shapes.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QTransform, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from sillycad.core.sketch import (
    DIMENSIONS,
    ORIGIN,
    X_AXIS,
    XY,
    Y_AXIS,
    Arc,
    Circle,
    Constraint,
    Line,
    Point,
    Sketch,
)
from sillycad.gui import theme

if TYPE_CHECKING:
    from sillycad.gui.sketch_editor import SketchEditor

PICK_PX = 8  # how close (pixels) the mouse must be to pick or snap
DRAG_PX = 4  # how far (pixels) the mouse must move before a press becomes a drag
CLICKS_NEEDED = {"point": 1, "line": 2, "circle": 2, "arc": 3}

BACKGROUND = QColor(theme.SKETCH_BACKGROUND)
GRID_MINOR, GRID_MAJOR = QColor(theme.SKETCH_GRID_MINOR), QColor(theme.SKETCH_GRID_MAJOR)
AXIS_X, AXIS_Y = QColor(theme.SKETCH_AXIS_X), QColor(theme.SKETCH_AXIS_Y)
INK = QColor(theme.SKETCH_FREE)
DONE = QColor(theme.SUCCESS)
BAD = QColor(theme.ERROR)
PICKED = QColor(theme.SKETCH_SELECTED)
HOVER = QColor(theme.SKETCH_HOVER)
REFERENCE = QColor(theme.SKETCH_REFERENCE)


class SketchView(QGraphicsView):
    """Canvas for one sketch. All model changes go through the editor."""

    def __init__(self, editor: SketchEditor) -> None:
        super().__init__()
        self.editor = editor
        self.setScene(QGraphicsScene(self))
        self.scene().setSceneRect(-1e5, -1e5, 2e5, 2e5)  # huge, so panning never hits an edge
        self.setTransform(QTransform.fromScale(4, -4))  # 4 px per mm, y up
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setMouseTracking(True)

        self.tool = "select"
        self.clicks: list[tuple[XY, str | None]] = []  # placed points + what each snapped to
        self.mouse: XY = (0.0, 0.0)
        self.hover: str | None = None
        self.snap: tuple[XY, str | None] | None = None  # where a drawing click would snap to
        self._pan_from: QPointF | None = None
        self._press: tuple[QPointF, XY, str] | None = None  # view pos, sketch pos, picked ID
        self._drag_start: Sketch | None = None

    # ── Coordinates ─────────────────────────────────────────────────

    def zoom(self) -> float:
        """Pixels per millimetre."""
        return abs(self.transform().m11())

    def to_sketch(self, view_pos: QPointF) -> XY:
        p = self.mapToScene(view_pos.toPoint())
        return (p.x(), p.y())

    def fit(self) -> None:
        """Zoom to show the sketch and the face outline (or ±50 mm if there's nothing)."""
        s = self.editor.sketch
        xs, ys = [-10.0, 10.0], [-10.0, 10.0]
        for polyline in self.editor.reference:
            xs += [x for x, _ in polyline]
            ys += [y for _, y in polyline]
        for g in s.geo.values():
            if isinstance(g, Point):
                xs.append(g.x)
                ys.append(g.y)
            elif isinstance(g, Circle):
                cx, cy = s.point(g.center)
                xs += [cx - g.radius, cx + g.radius]
                ys += [cy - g.radius, cy + g.radius]
        if len(xs) == 2:
            xs, ys = [-50.0, 50.0], [-50.0, 50.0]
        rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        margin = 0.15 * max(rect.width(), rect.height())
        self.fitInView(
            rect.adjusted(-margin, -margin, margin, margin), Qt.AspectRatioMode.KeepAspectRatio
        )
        self.redraw()

    # ── Picking ─────────────────────────────────────────────────────

    def pick(self, view_pos: QPointF, points_only: bool = False) -> str | None:
        """ID of the thing under the mouse: a dimension label, point, curve or axis."""
        if not points_only:
            for item in self.items(view_pos.toPoint()):
                if item.data(0):
                    return item.data(0)
        s, (x, y) = self.editor.sketch, self.to_sketch(view_pos)
        tol = PICK_PX / self.zoom()
        best, best_d = None, tol
        points = [ORIGIN] + [g.id for g in s.geo.values() if isinstance(g, Point)]
        for pid in points:
            d = math.dist((x, y), s.point(pid))
            if d < best_d:
                best, best_d = pid, d
        if best or points_only:
            return best
        for g in s.geo.values():
            if not isinstance(g, Point):
                d = _curve_distance(s, g, (x, y))
                if d < best_d:
                    best, best_d = g.id, d
        for axis, d in ((X_AXIS, abs(y)), (Y_AXIS, abs(x))):
            if d < best_d:
                best, best_d = axis, d
        return best

    def snap_target(self, view_pos: QPointF) -> tuple[XY, str | None] | None:
        """A nearby sketch point (position and ID), or a corner of the face outline
        (position only: it's a guide, not sketch geometry). None if nothing is close."""
        pid = self.pick(view_pos, points_only=True)
        if pid:
            return self.editor.sketch.point(pid), pid
        mouse, tol = self.to_sketch(view_pos), PICK_PX / self.zoom()
        for polyline in self.editor.reference:
            for corner in (polyline[0], polyline[-1]):
                if math.dist(mouse, corner) < tol:
                    return corner, None
        return None

    def snapped(self, view_pos: QPointF) -> tuple[XY, str | None]:
        """Mouse position, snapped to a nearby point if there is one."""
        return self.snap_target(view_pos) or (self.to_sketch(view_pos), None)

    # ── Mouse and keys ──────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.2 ** (event.angleDelta().y() / 120)
        if 0.01 < self.zoom() * factor < 1e4:
            self.scale(factor, factor)
            self.redraw()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_from = pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.RightButton:
            self.escape()
        elif event.button() == Qt.MouseButton.LeftButton:
            if self.tool == "select":
                self._select_press(event)
            else:
                self.clicks.append(self.snapped(pos))
                if len(self.clicks) == CLICKS_NEEDED[self.tool]:
                    self._create_shape()
                self.redraw()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self.mouse = self.to_sketch(pos)
        if self._pan_from is not None:
            delta = pos - self._pan_from
            self._pan_from = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            return
        if self._press is not None:
            start_pos, _, picked = self._press
            moved = (pos - start_pos).manhattanLength() > DRAG_PX
            if self._drag_start is None and moved and picked in self.editor.sketch.geo:
                self._drag_start = self.editor.start_drag()
            if self._drag_start is not None:
                self._drag_to(self.mouse)
            return
        if self.tool != "select":
            self.snap = self.snap_target(pos)
            self.redraw()
            return
        hover = self.pick(pos)
        if hover != self.hover:
            self.hover = hover
            self.redraw()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_from = None
            self.unsetCursor()
        elif event.button() == Qt.MouseButton.LeftButton:
            if self._drag_start is not None:
                self.editor.finish_drag(self._drag_start)
            self._press = self._drag_start = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        picked = self.pick(event.position())
        if self.tool == "select" and picked in self.editor.sketch.constraints:
            self.editor.edit_dimension(picked)
        else:
            self.mousePressEvent(event)  # quick clicks while drawing still count

    def escape(self) -> None:
        """Esc / right-click: cancel the shape being drawn, then the tool, then the selection."""
        if self.clicks:
            self.clicks = []
        elif self.tool != "select":
            self.editor.set_tool("select")
        else:
            self.editor.set_selection([])
        self.redraw()

    def _select_press(self, event: QMouseEvent) -> None:
        picked = self.pick(event.position())
        selection = list(self.editor.selection)
        additive = event.modifiers() & (
            Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
        )
        if picked is None:
            if not additive:
                selection = []
        elif additive and picked in selection:
            selection.remove(picked)
        elif additive:
            selection.append(picked)
        elif picked not in selection:
            selection = [picked]
        self.editor.set_selection(selection)
        if picked:
            self._press = (event.position(), self.to_sketch(event.position()), picked)

    def _drag_to(self, mouse: XY) -> None:
        """Ask the editor to move the pressed item so it follows the mouse."""
        assert self._press is not None and self._drag_start is not None
        _, (px, py), picked = self._press
        start = self._drag_start
        g = start.geo[picked]
        dx, dy = mouse[0] - px, mouse[1] - py
        if isinstance(g, Point):
            self.editor.drag_to({picked: mouse})
        elif isinstance(g, Circle):
            self.editor.drag_to({}, {picked: math.dist(start.point(g.center), mouse)})
        else:  # lines and arcs move as a whole
            moved = {p: (start.point(p)[0] + dx, start.point(p)[1] + dy) for p in g.points}
            self.editor.drag_to(moved)

    def _create_shape(self) -> None:
        """Turn the placed clicks into geometry, snapping ends with coincident constraints."""
        tool, clicks = self.tool, self.clicks
        positions = [p for p, _ in clicks]
        snaps = [snap for _, snap in clicks]
        new_end: list[str] = []

        def build(s: Sketch) -> None:
            if tool == "point":
                ends = [s.add_point(*positions[0])]
            elif tool == "line":
                if math.dist(*positions) * self.zoom() < 2:
                    raise ValueError("That line is too short. Click two different spots.")
                gid = s.add_line(*positions[0], *positions[1])
                ends = s.geo[gid].points
            elif tool == "circle":
                radius = math.dist(*positions)
                if radius * self.zoom() < 2:
                    raise ValueError("That circle is too small.")
                gid = s.add_circle(*positions[0], radius)
                ends = [s.geo[gid].center, None]  # the rim click doesn't join anything
            else:
                center, start, end = positions
                radius = math.dist(center, start)
                if radius * self.zoom() < 2:
                    raise ValueError("That arc is too small.")
                end = _project(center, end, radius)
                gid = s.add_arc(*center, *start, *end)
                ends = [s.geo[gid].center, s.geo[gid].start, s.geo[gid].end]
            for pid, snap in zip(ends, snaps, strict=True):
                if pid and snap:
                    s.add_constraint("coincident", [pid, snap])
            new_end[:] = [ends[-1]]

        ok = self.editor.edit(f"Add {tool}", build)
        self.clicks = []
        if ok and tool == "line" and snaps[-1] is None:
            # Keep drawing: the next line starts where this one ended.
            self.clicks = [(positions[-1], new_end[0])]

    # ── Drawing ─────────────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, BACKGROUND)
        step = _grid_step(12 / self.zoom())
        leading_digit = round(step / 10 ** math.floor(math.log10(step)))
        major = step * (2 if leading_digit == 5 else 5)  # major lines at 5, 10, 50, 100...
        for spacing, color in ((step, GRID_MINOR), (major, GRID_MAJOR)):
            painter.setPen(QPen(color, 0))
            x = math.floor(rect.left() / spacing) * spacing
            lines = []
            while x <= rect.right():
                lines.append(QLineF(x, rect.top(), x, rect.bottom()))
                x += spacing
            y = math.floor(rect.top() / spacing) * spacing
            while y <= rect.bottom():
                lines.append(QLineF(rect.left(), y, rect.right(), y))
                y += spacing
            painter.drawLines(lines)
        for axis, line, color in (
            (X_AXIS, QLineF(rect.left(), 0, rect.right(), 0), AXIS_X),
            (Y_AXIS, QLineF(0, rect.top(), 0, rect.bottom()), AXIS_Y),
        ):
            painter.setPen(self._pen(axis, color, width=1.5))
            painter.drawLine(line)
        if self.editor.reference:  # outline of the face being sketched on: a grey guide
            guide = QPen(REFERENCE, 1.5)
            guide.setCosmetic(True)
            painter.setPen(guide)
            for polyline in self.editor.reference:
                painter.drawPolyline([QPointF(x, y) for x, y in polyline])

    def redraw(self) -> None:
        """Rebuild the scene from the model."""
        scene, s = self.scene(), self.editor.sketch
        scene.clear()
        for g in s.geo.values():
            if isinstance(g, Line | Circle | Arc):
                scene.addPath(_curve_path(s, g), self._pen(g.id, dashed=g.construction))
        for g in s.geo.values():
            if isinstance(g, Point):
                self._dot((g.x, g.y), self._color(g.id))
        self._dot((0, 0), self._color(ORIGIN), size=8)
        for c in s.constraints.values():
            if c.kind in DIMENSIONS:
                self._label(c)
        for xy in self.editor.problems:
            self._ring(xy, BAD)
        self._draw_preview()
        self.viewport().update()

    def _draw_preview(self) -> None:
        if self.tool == "select":
            return
        mouse = self.mouse
        if self.snap:
            mouse = self.snap[0]
            self._ring(mouse, HOVER)
        pts = [p for p, _ in self.clicks] + [mouse]
        pen = QPen(HOVER, 0, Qt.PenStyle.DashLine)
        path = QPainterPath()
        if len(pts) >= 2 and self.tool == "line":
            path.moveTo(*pts[0])
            path.lineTo(*pts[1])
        elif len(pts) >= 2 and self.tool == "circle":
            r = math.dist(pts[0], pts[1])
            path.addEllipse(QPointF(*pts[0]), r, r)
        elif len(pts) == 2 and self.tool == "arc":
            path.moveTo(*pts[0])
            path.lineTo(*pts[1])
        elif len(pts) == 3 and self.tool == "arc":
            r = math.dist(pts[0], pts[1])
            path = _arc_path(pts[0], r, pts[1], _project(pts[0], pts[2], r))
        self.scene().addPath(path, pen)

    def _color(self, gid: str) -> QColor:
        ed = self.editor
        if gid in ed.highlighted():
            return PICKED
        if gid == self.hover and self.tool == "select":
            return HOVER
        if gid in ed.bad_geometry:
            return BAD
        return DONE if ed.result.fully_constrained else INK

    def _pen(
        self, gid: str, color: QColor | None = None, width: float = 2, dashed: bool = False
    ) -> QPen:
        chosen = self._color(gid)
        if color is not None and chosen in (INK, DONE):
            chosen = color  # axes keep their own colour unless selected/hovered/bad
        pen = QPen(chosen, width)
        pen.setCosmetic(True)  # width in pixels, whatever the zoom
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    def _dot(self, xy: XY, color: QColor, size: float = 6) -> None:
        dot = QGraphicsEllipseItem(-size / 2, -size / 2, size, size)
        dot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        dot.setBrush(color)
        dot.setPen(Qt.PenStyle.NoPen)
        dot.setPos(*xy)
        self.scene().addItem(dot)

    def _ring(self, xy: XY, color: QColor) -> None:
        ring = QGraphicsEllipseItem(-8, -8, 16, 16)
        ring.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        ring.setPen(QPen(color, 2))
        ring.setPos(*xy)
        self.scene().addItem(ring)

    def _label(self, c: Constraint) -> None:
        """Dimension value in a little box; double-click it to edit."""
        text = QGraphicsSimpleTextItem(_dimension_text(c))
        color = self._color(c.id)
        if c.id in self.editor.bad_constraints:
            color = BAD
        text.setBrush(color)
        r = text.boundingRect().adjusted(-4, -2, 4, 2)
        box = QGraphicsRectItem(r)
        box.setBrush(QColor(theme.SKETCH_DIMENSION_BACKGROUND))
        box.setPen(QPen(color, 1))
        box.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        box.setTransform(QTransform.fromTranslate(-r.width() / 2, -r.height() / 2))
        text.setParentItem(box)
        box.setPos(*_label_anchor(self.editor.sketch, c, 24 / self.zoom()))
        for item in (box, text):
            item.setData(0, c.id)
            item.setToolTip("Double-click to change")
        self.scene().addItem(box)


# ── Geometry helpers ────────────────────────────────────────────────


def _grid_step(minimum: float) -> float:
    """Smallest 1/2/5 × 10ⁿ step that is at least ``minimum``."""
    exponent = math.floor(math.log10(minimum))
    for m in (1, 2, 5, 10):
        if m * 10**exponent >= minimum:
            return m * 10**exponent
    return 10 ** (exponent + 1)


def _project(center: XY, p: XY, radius: float) -> XY:
    """Point at ``radius`` from ``center`` in the direction of ``p``."""
    angle = math.atan2(p[1] - center[1], p[0] - center[0])
    return (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))


def _sweep(center: XY, start: XY, end: XY) -> tuple[float, float]:
    """Start angle and counter-clockwise sweep (radians) of an arc."""
    a1 = math.atan2(start[1] - center[1], start[0] - center[0])
    a2 = math.atan2(end[1] - center[1], end[0] - center[0])
    return a1, (a2 - a1) % (2 * math.pi) or 2 * math.pi


def _arc_path(center: XY, radius: float, start: XY, end: XY) -> QPainterPath:
    a1, sweep = _sweep(center, start, end)
    steps = max(8, int(64 * sweep / (2 * math.pi)))
    path = QPainterPath()
    for i in range(steps + 1):
        a = a1 + sweep * i / steps
        x, y = center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)
        path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
    return path


def _curve_path(s: Sketch, g: Line | Circle | Arc) -> QPainterPath:
    path = QPainterPath()
    if isinstance(g, Line):
        (x1, y1), (x2, y2) = s.line_points(g.id)
        path.moveTo(x1, y1)
        path.lineTo(x2, y2)
    elif isinstance(g, Circle):
        path.addEllipse(QPointF(*s.point(g.center)), g.radius, g.radius)
    else:
        path = _arc_path(s.point(g.center), s.radius(g.id), s.point(g.start), s.point(g.end))
    return path


def _curve_distance(s: Sketch, g: Line | Circle | Arc, p: XY) -> float:
    """Distance (mm) from ``p`` to a curve."""
    if isinstance(g, Line):
        a, b = s.line_points(g.id)
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)
        t = min(1.0, max(0.0, t))
        return math.dist(p, (a[0] + t * dx, a[1] + t * dy))
    center = s.point(g.center)
    radius = s.radius(g.id)
    if isinstance(g, Circle):
        return abs(math.dist(p, center) - radius)
    start, end = s.point(g.start), s.point(g.end)
    a1, sweep = _sweep(center, start, end)
    a = math.atan2(p[1] - center[1], p[0] - center[0])
    if (a - a1) % (2 * math.pi) <= sweep:
        return abs(math.dist(p, center) - radius)
    return min(math.dist(p, start), math.dist(p, end))


def _dimension_text(c: Constraint) -> str:
    value = f"{round(c.value, 3):g}"
    return {
        "distance_x": f"↔ {value}",
        "distance_y": f"↕ {value}",
        "angle": f"{value}°",
        "radius": f"R{value}",
        "diameter": f"⌀{value}",
    }.get(c.kind, value)


def _label_anchor(s: Sketch, c: Constraint, nudge: float) -> XY:
    """Where a dimension label goes (sketch mm). ``nudge`` is ~24 px in mm."""

    def mid(a: XY, b: XY) -> XY:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    r = c.refs
    if c.kind in ("radius", "diameter"):
        g = s.geo[r[0]]
        center, radius = s.point(g.center), s.radius(g.id)
        angle = math.pi / 4
        if isinstance(g, Arc):
            a1, sweep = _sweep(center, s.point(g.start), s.point(g.end))
            angle = a1 + sweep / 2
        return (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))
    if c.kind == "angle":
        (a1, a2), (b1, b2) = s.line_points(r[0]), s.line_points(r[1])
        return mid(mid(a1, a2), mid(b1, b2))
    if c.kind in ("distance_x", "distance_y"):  # below / left, so they don't cover lengths
        m = mid(s.point(r[0]), s.point(r[1]))
        return (m[0], m[1] - nudge) if c.kind == "distance_x" else (m[0] - nudge, m[1])
    if len(r) == 1:  # a line's length: just off its middle
        a, b = s.line_points(r[0])
        length = math.dist(a, b) or 1
        m = mid(a, b)
        return (m[0] - (b[1] - a[1]) / length * nudge, m[1] + (b[0] - a[0]) / length * nudge)
    if s.ref_type(r[1]) == "line":  # point to line: halfway to the foot of the perpendicular
        p, (a, b) = s.point(r[0]), s.line_points(r[1])
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)
        return mid(p, (a[0] + t * dx, a[1] + t * dy))
    return mid(s.point(r[0]), s.point(r[1]))
