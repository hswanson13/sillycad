"""Native OCCT presentations and picking for one sketch plane."""

import math

from OCC.Core.AIS import AIS_InteractiveObject, AIS_Point, AIS_Shape, AIS_TextLabel
from OCC.Core.Aspect import Aspect_TOL_DASH, Aspect_TOL_SOLID, Aspect_TOM_BALL
from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.Geom import Geom_CartesianPoint
from OCC.Core.gp import gp_Pnt
from OCC.Core.Graphic3d import Graphic3d_ZLayerId_Topmost, Graphic3d_ZLayerId_TopOSD
from OCC.Core.Prs3d import Prs3d_LineAspect, Prs3d_PointAspect
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_sRGB
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Shape
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from sillycad.core.geometry import Placement, place_on_plane
from sillycad.core.profiles import curve_edge
from sillycad.core.sketch import DIMENSIONS, ORIGIN, XY, Arc, Circle, Constraint, Line, Point
from sillycad.gui import theme
from sillycad.gui.sketch_session import SketchSession
from sillycad.gui.viewer import Viewer
from sillycad.sketch_math import (
    SnapTarget,
    curve_distance,
    dimension_anchor,
    ray_to_sketch,
    sketch_to_world,
    snap_targets,
)

PICK_PIXELS = 8.0
_GLYPHS = {
    "coincident": "●",
    "horizontal": "H",
    "vertical": "V",
    "parallel": "∥",
    "perpendicular": "⊥",
    "equal": "=",
    "point_on_line": "○",
    "tangent": "T",
    "midpoint": "M",
    "fix": "F",
}


def _color(name: str) -> Quantity_Color:
    color = QColor(name)
    return Quantity_Color(color.redF(), color.greenF(), color.blueF(), Quantity_TOC_sRGB)


class SketchScene:
    """Draw and pick sketch geometry in the native 3D viewport."""

    def __init__(
        self, viewer: Viewer, session: SketchSession, placement: Placement, offset: float
    ) -> None:
        self.viewer = viewer
        self.session = session
        self.placement = placement
        self.offset = offset
        self.context = viewer._display.Context
        self.hover: str | None = None
        self.show_constraints = True
        self._objects: dict[str, AIS_InteractiveObject] = {}
        self._signatures: dict[str, object] = {}
        self._anchors: dict[str, XY] = {}
        self._preview: list[tuple[XY, XY]] = []
        self._preview_aligned = False
        self._snap_target: SnapTarget | None = None
        self._static_geometry()
        self.update_grid()
        self.redraw()

    def world(self, point: XY) -> tuple[float, float, float]:
        """Transform sketch coordinates onto the 3D plane."""
        return sketch_to_world(point, self.placement, self.offset)

    def screen(self, point: XY) -> QPointF:
        """Project sketch coordinates into viewport pixels."""
        x, y = self.viewer._display.View.Convert(*self.world(point))
        return QPointF(x, y)

    def to_sketch(self, point: QPointF) -> XY:
        """Intersect the screen ray with the sketch plane."""
        x, y, z, vx, vy, vz = self.viewer._display.View.ConvertWithProj(
            round(point.x()), round(point.y())
        )
        return ray_to_sketch((x, y, z), (vx, vy, vz), self.placement, self.offset)

    def tolerance(self, point: QPointF, pixels: float = PICK_PIXELS) -> float:
        """Estimate the sketch-space tolerance corresponding to a screen distance."""
        center = self.to_sketch(point)
        across = self.to_sketch(point + QPointF(pixels, 0))
        down = self.to_sketch(point + QPointF(0, pixels))
        return max(math.dist(center, across), math.dist(center, down))

    def pick(self, point: QPointF, *, points_only: bool = False) -> str | None:
        """Find the nearest sketch point, curve, axis or constraint glyph."""
        sketch = self.session.sketch
        if not points_only:
            for cid, anchor in reversed(list(self._anchors.items())):
                pos = self.screen(anchor)
                if math.hypot(point.x() - pos.x(), point.y() - pos.y()) <= 12:
                    return cid
        best, distance = None, PICK_PIXELS
        points = [(ORIGIN, (0.0, 0.0))]
        points.extend(
            (item.id, (item.x, item.y)) for item in sketch.geo.values() if isinstance(item, Point)
        )
        for gid, xy in points:
            pos = self.screen(xy)
            gap = math.hypot(point.x() - pos.x(), point.y() - pos.y())
            if gap < distance:
                best, distance = gid, gap
        if best or points_only:
            return best
        xy, tolerance = self.to_sketch(point), self.tolerance(point)
        best, distance = None, tolerance
        for geometry in sketch.geo.values():
            if isinstance(geometry, Line | Circle | Arc):
                gap = curve_distance(sketch, geometry, xy)
                if gap < distance:
                    best, distance = geometry.id, gap
        for axis, gap in (("x_axis", abs(xy[1])), ("y_axis", abs(xy[0]))):
            if gap < distance:
                best, distance = axis, gap
        return best

    def snap(self, point: QPointF) -> tuple[XY, SnapTarget | None]:
        """Snap to the closest key point in screen pixels, independent of zoom."""
        best, distance = None, PICK_PIXELS
        for target in snap_targets(self.session.sketch, self.session.reference):
            pos = self.screen(target.point)
            gap = math.hypot(point.x() - pos.x(), point.y() - pos.y())
            if gap < distance:
                best, distance = target, gap
        return (best.point, best) if best is not None else (self.to_sketch(point), None)

    def _display(self, key: str, item: AIS_InteractiveObject) -> None:
        item.SetZLayer(Graphic3d_ZLayerId_Topmost)
        self.context.Display(item, False)
        self.context.Deactivate(item)
        self._objects[key] = item

    def _linework(self, segments: list[tuple[XY, XY]]) -> TopoDS_Shape:
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        for a, b in segments:
            if math.dist(a, b) > 1e-9:
                edge = BRepBuilderAPI_MakeEdge(
                    gp_Pnt(*self.world(a)), gp_Pnt(*self.world(b))
                ).Edge()
                builder.Add(compound, edge)
        return compound

    def _static_geometry(self) -> None:
        reference = [
            (a, b)
            for polyline in self.session.reference
            for a, b in zip(polyline, polyline[1:], strict=False)
        ]
        if reference:
            item = AIS_Shape(self._linework(reference))
            item.SetColor(_color(theme.SKETCH_REFERENCE))
            self._display("reference", item)

    def update_grid(self) -> None:
        """Fit the grid and axes to the current view without adding them to Fit All."""
        try:
            corners = [
                self.to_sketch(QPointF(x, y))
                for x in (0, self.viewer.width())
                for y in (0, self.viewer.height())
            ]
        except ValueError:
            return  # The plane can temporarily be edge-on while orbiting.
        xs, ys = zip(*corners, strict=True)
        span = max(max(xs) - min(xs), max(ys) - min(ys))
        if not math.isfinite(span) or not 1e-9 <= span <= 1e9:
            return
        raw = span / 20
        unit = 10 ** math.floor(math.log10(raw))
        step = next(multiple * unit for multiple in (1, 2, 5, 10) if multiple * unit >= raw)
        xmin, xmax = math.floor(min(xs) / step) * step, math.ceil(max(xs) / step) * step
        ymin, ymax = math.floor(min(ys) / step) * step, math.ceil(max(ys) / step) * step
        grid = [
            ((i * step, ymin), (i * step, ymax))
            for i in range(math.floor(xmin / step), math.ceil(xmax / step) + 1)
            if i
        ]
        grid.extend(
            ((xmin, i * step), (xmax, i * step))
            for i in range(math.floor(ymin / step), math.ceil(ymax / step) + 1)
            if i
        )
        self._auxiliary("grid", grid, theme.SKETCH_GRID_MAJOR, infinite=True)
        self._auxiliary("axis-x", [((xmin, 0), (xmax, 0))], theme.SKETCH_AXIS_X, infinite=True)
        self._auxiliary("axis-y", [((0, ymin), (0, ymax))], theme.SKETCH_AXIS_Y, infinite=True)
        self.redraw()

    def _curve(self, key: str, geometry: Line | Circle | Arc, color: str) -> None:
        sketch = self.session.sketch
        coordinates = tuple(sketch.point(point) for point in geometry.points)
        signature = (
            coordinates,
            sketch.radius(geometry.id) if isinstance(geometry, Circle) else None,
            color,
            geometry.construction,
        )
        if self._signatures.get(key) == signature:
            return
        if isinstance(geometry, Line) and math.dist(*coordinates) < 1e-9:
            self._remove(key)
            return
        shape = place_on_plane(curve_edge(sketch, geometry), self.placement, self.offset)
        item = self._objects.get(key)
        if not isinstance(item, AIS_Shape):
            item = AIS_Shape(shape)
            self._display(key, item)
        else:
            item.SetShape(shape)
        color_value = _color(color)
        item.SetColor(color_value)
        item.Attributes().SetLineAspect(
            Prs3d_LineAspect(
                color_value, Aspect_TOL_DASH if geometry.construction else Aspect_TOL_SOLID, 2.0
            )
        )
        self.context.Redisplay(item, False)
        self._signatures[key] = signature

    def _point(self, key: str, xy: XY, color: str, *, marker: bool = False) -> None:
        signature = (xy, color, marker)
        if self._signatures.get(key) == signature:
            return
        geometry = Geom_CartesianPoint(gp_Pnt(*self.world(xy)))
        item = self._objects.get(key)
        if not isinstance(item, AIS_Point):
            item = AIS_Point(geometry)
            self._display(key, item)
        else:
            item.SetComponent(geometry)
        color_value = _color(color)
        item.SetColor(color_value)
        if marker:
            item.SetZLayer(Graphic3d_ZLayerId_TopOSD)
            item.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TOM_BALL, color_value, 3.0))
        self.context.Redisplay(item, False)
        self._signatures[key] = signature

    def _label(self, key: str, xy: XY, text: str, color: str) -> None:
        signature = (xy, text, color)
        if self._signatures.get(key) == signature:
            return
        item = self._objects.get(key)
        if not isinstance(item, AIS_TextLabel):
            item = AIS_TextLabel()
            item.SetFont(self.viewer._font)
            item.SetHeight(14)
            self._display(key, item)
        item.SetText(text)
        item.SetPosition(gp_Pnt(*self.world(xy)))
        item.SetColor(_color(color))
        self.context.Redisplay(item, False)
        self._signatures[key] = signature

    def _remove(self, key: str) -> None:
        item = self._objects.pop(key, None)
        if item is not None:
            self.context.Remove(item, False)
        self._signatures.pop(key, None)

    def _constraint_anchor(self, constraint: Constraint, nudge: float) -> XY:
        sketch = self.session.sketch
        if constraint.kind in DIMENSIONS:
            return dimension_anchor(sketch, constraint, nudge * 2)
        ref = constraint.refs[0]
        if sketch.ref_type(ref) == "point":
            x, y = sketch.point(ref)
        elif sketch.ref_type(ref) == "line":
            a, b = sketch.line_points(ref)
            x, y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        else:
            curve = sketch.geo[ref]
            if not isinstance(curve, Circle | Arc):
                raise ValueError(f"Unknown round geometry: {ref}")
            x, y = sketch.point(curve.center)
        return x + nudge, y + nudge

    def set_preview(
        self,
        segments: list[tuple[XY, XY]],
        snap: SnapTarget | None = None,
        *,
        aligned: bool = False,
    ) -> None:
        """Display temporary drawing geometry and its current snap marker."""
        self._preview = segments
        self._preview_aligned = aligned
        self._snap_target = snap
        self.redraw()

    def clear_snap(self) -> None:
        """Hide the snap marker while retaining any drawing preview."""
        if self._snap_target is None:
            return
        self._snap_target = None
        self.redraw()

    def _auxiliary(
        self,
        key: str,
        segments: list[tuple[XY, XY]],
        color: str,
        *,
        infinite: bool = False,
        width: float | None = None,
    ) -> None:
        signature = (tuple(segments), color, width)
        if self._signatures.get(key) == signature:
            return
        shape = self._linework(segments)
        item = self._objects.get(key)
        if not isinstance(item, AIS_Shape):
            item = AIS_Shape(shape)
            item.SetInfiniteState(infinite)
            self._display(key, item)
        else:
            item.SetShape(shape)
        color_value = _color(color)
        item.SetColor(color_value)
        if width is not None:
            item.Attributes().SetLineAspect(Prs3d_LineAspect(color_value, Aspect_TOL_SOLID, width))
        self.context.Redisplay(item, False)
        self._signatures[key] = signature

    def _dimension_lines(self, constraint: Constraint, anchor: XY) -> list[tuple[XY, XY]]:
        sketch = self.session.sketch
        refs = constraint.refs
        if constraint.kind in ("radius", "diameter"):
            curve = sketch.geo[refs[0]]
            if not isinstance(curve, Circle | Arc):
                raise ValueError("A radius or diameter dimension needs a circle or arc.")
            center = sketch.point(curve.center)
            other = (
                (2 * center[0] - anchor[0], 2 * center[1] - anchor[1])
                if constraint.kind == "diameter"
                else center
            )
            return [(other, anchor)]
        if constraint.kind == "angle":
            a, b = sketch.line_points(refs[0]), sketch.line_points(refs[1])
            return [(a[0], anchor), (b[0], anchor)]
        if len(refs) == 1:
            a, b = sketch.line_points(refs[0])
        elif sketch.ref_type(refs[1]) == "line":
            a = sketch.point(refs[0])
            p, q = sketch.line_points(refs[1])
            dx, dy = q[0] - p[0], q[1] - p[1]
            t = ((a[0] - p[0]) * dx + (a[1] - p[1]) * dy) / ((dx * dx + dy * dy) or 1)
            b = p[0] + t * dx, p[1] + t * dy
        else:
            a, b = sketch.point(refs[0]), sketch.point(refs[1])
        if constraint.kind == "distance_x":
            a2, b2 = (a[0], anchor[1]), (b[0], anchor[1])
        elif constraint.kind == "distance_y":
            a2, b2 = (anchor[0], a[1]), (anchor[0], b[1])
        else:
            dx, dy = anchor[0] - (a[0] + b[0]) / 2, anchor[1] - (a[1] + b[1]) / 2
            a2, b2 = (a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy)
        return [(a, a2), (b, b2), (a2, b2)]

    def redraw(self) -> None:
        """Update changed presentations without rebuilding the part or viewer."""
        sketch, session = self.session.sketch, self.session
        alive = {"grid", "axis-x", "axis-y", "reference"}
        selected = session.highlighted()
        if self._snap_target is not None and self._snap_target not in snap_targets(
            sketch, session.reference
        ):
            self._snap_target = None

        def color(gid: str) -> str:
            if gid in selected:
                return theme.ACCENT
            if gid == self.hover:
                return theme.SKETCH_HOVER
            if gid in session.bad_geometry or gid in session.bad_constraints:
                return theme.ERROR
            return theme.SUCCESS if session.result.fully_constrained else theme.SKETCH_FREE

        for geometry in sketch.geo.values():
            key = "geometry:" + geometry.id
            alive.add(key)
            if isinstance(geometry, Point):
                self._point(key, (geometry.x, geometry.y), color(geometry.id))
            else:
                self._curve(key, geometry, color(geometry.id))
        alive.add("geometry:origin")
        self._point("geometry:origin", (0, 0), color(ORIGIN))

        self._anchors.clear()
        nudge = self.viewer._display.View.Convert(12)
        if self._preview:
            alive.add("preview")
            self._auxiliary(
                "preview",
                self._preview,
                theme.SKETCH_SNAP if self._preview_aligned else theme.SKETCH_HOVER,
                width=2.0,
            )
        if self._snap_target is not None:
            alive.add("snap")
            self._point("snap", self._snap_target.point, theme.SKETCH_SNAP, marker=True)
        if session.problems:
            radius = self.viewer._display.View.Convert(8)
            rings = []
            for x, y in session.problems:
                points = [
                    (
                        x + radius * math.cos(i * math.tau / 32),
                        y + radius * math.sin(i * math.tau / 32),
                    )
                    for i in range(33)
                ]
                rings.extend(zip(points, points[1:], strict=False))
            alive.add("problem-rings")
            self._auxiliary("problem-rings", rings, theme.ERROR)
        for constraint in sketch.constraints.values():
            if constraint.kind not in DIMENSIONS and not self.show_constraints:
                continue
            anchor = self._constraint_anchor(constraint, nudge)
            self._anchors[constraint.id] = anchor
            display_color = color(constraint.id)
            if constraint.kind in DIMENSIONS:
                if constraint.value is None:
                    raise ValueError(f"Dimension {constraint.id} has no value.")
                if (
                    constraint.id not in selected
                    and constraint.id != self.hover
                    and constraint.id not in session.bad_constraints
                ):
                    display_color = theme.TEXT
                value = f"{round(constraint.value, 3):g}"
                text = {"angle": f"{value}°", "radius": f"R{value}", "diameter": f"⌀{value}"}.get(
                    constraint.kind, value
                )
                lines_key = "dimension-lines:" + constraint.id
                alive.add(lines_key)
                self._auxiliary(lines_key, self._dimension_lines(constraint, anchor), display_color)
            else:
                text = _GLYPHS[constraint.kind]
            key = "constraint:" + constraint.id
            alive.add(key)
            self._label(key, anchor, text, display_color)
        for key in set(self._objects) - alive:
            self._remove(key)
        self.viewer._display.View.Redraw()

    def clear(self) -> None:
        """Remove sketch presentations without affecting the part or ViewCube."""
        for key in list(self._objects):
            self._remove(key)
        self.viewer._display.View.Redraw()
