"""Qt-free geometry helpers for sketch interaction."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sillycad.core.geometry import Placement
from sillycad.core.sketch import AXES, ORIGIN, XY, Arc, Circle, Constraint, Line, Point, Sketch

XYZ = tuple[float, float, float]


@dataclass(frozen=True)
class SnapTarget:
    """A key point and the sketch reference, if any, that can constrain it."""

    point: XY
    kind: Literal["point", "midpoint", "reference"]
    ref: str | None = None


def snap_targets(sketch: Sketch, reference: Sequence[Sequence[XY]]) -> list[SnapTarget]:
    """Find sketch key points and the available key points of face-outline guides."""
    targets = [SnapTarget((0.0, 0.0), "point", ORIGIN)]
    targets.extend(
        SnapTarget((item.x, item.y), "point", item.id)
        for item in sketch.geo.values()
        if isinstance(item, Point)
    )
    for item in sketch.geo.values():
        if isinstance(item, Line):
            a, b = sketch.line_points(item.id)
            targets.append(SnapTarget(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), "midpoint", item.id))
    for polyline in reference:
        if len(polyline) < 2:
            continue
        a, b = polyline[0], polyline[-1]
        targets.extend((SnapTarget(a, "reference"), SnapTarget(b, "reference")))
        if len(polyline) == 2:
            targets.append(SnapTarget(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), "reference"))
    return targets


def constrain_snap(sketch: Sketch, point: str, target: SnapTarget | None) -> None:
    """Constrain a new point to a sketch target; guides are positional only."""
    if target is None or target.kind == "reference":
        return
    if target.ref is None:
        raise ValueError("The snap target has no sketch reference.")
    sketch.add_constraint(
        "coincident" if target.kind == "point" else "midpoint", [point, target.ref]
    )


def _dot(a: XYZ, b: XYZ) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _unit(vector: XYZ) -> XYZ:
    length = math.sqrt(_dot(vector, vector))
    if length < 1e-12:
        raise ValueError("The sketch plane has an invalid direction.")
    return vector[0] / length, vector[1] / length, vector[2] / length


def _frame(placement: Placement, offset: float) -> tuple[XYZ, XYZ, XYZ, XYZ]:
    normal = _unit(placement.normal)
    projection = _dot(placement.x_dir, normal)
    x_axis = _unit(
        (
            placement.x_dir[0] - projection * normal[0],
            placement.x_dir[1] - projection * normal[1],
            placement.x_dir[2] - projection * normal[2],
        )
    )
    y_axis = (
        normal[1] * x_axis[2] - normal[2] * x_axis[1],
        normal[2] * x_axis[0] - normal[0] * x_axis[2],
        normal[0] * x_axis[1] - normal[1] * x_axis[0],
    )
    origin = (
        placement.origin[0] + offset * placement.normal[0],
        placement.origin[1] + offset * placement.normal[1],
        placement.origin[2] + offset * placement.normal[2],
    )
    return origin, x_axis, y_axis, normal


def sketch_to_world(point: XY, placement: Placement, offset: float = 0.0) -> XYZ:
    """Convert a sketch point to its 3D plane."""
    origin, x_axis, y_axis, _ = _frame(placement, offset)
    return (
        origin[0] + point[0] * x_axis[0] + point[1] * y_axis[0],
        origin[1] + point[0] * x_axis[1] + point[1] * y_axis[1],
        origin[2] + point[0] * x_axis[2] + point[1] * y_axis[2],
    )


def ray_to_sketch(
    ray_origin: XYZ, ray_direction: XYZ, placement: Placement, offset: float = 0.0
) -> XY:
    """Intersect a view ray with a sketch plane and return its coordinates.

    An edge-on plane raises ``ValueError`` so the user can return to sketch view.
    """
    origin, x_axis, y_axis, normal = _frame(placement, offset)
    direction = _unit(ray_direction)
    denominator = _dot(direction, normal)
    if abs(denominator) < 1e-10:
        raise ValueError("The sketch plane is edge-on. Use Look At to face it.")
    delta = (
        origin[0] - ray_origin[0],
        origin[1] - ray_origin[1],
        origin[2] - ray_origin[2],
    )
    distance = _dot(delta, normal) / denominator
    on_plane = (
        ray_origin[0] + distance * direction[0] - origin[0],
        ray_origin[1] + distance * direction[1] - origin[1],
        ray_origin[2] + distance * direction[2] - origin[2],
    )
    return _dot(on_plane, x_axis), _dot(on_plane, y_axis)


def curve_distance(sketch: Sketch, curve: Line | Circle | Arc, point: XY) -> float:
    """Return the shortest distance from a sketch point to a curve."""
    if isinstance(curve, Line):
        a, b = sketch.line_points(curve.id)
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)
        t = min(1.0, max(0.0, t))
        return math.dist(point, (a[0] + t * dx, a[1] + t * dy))
    center = sketch.point(curve.center)
    radius = sketch.radius(curve.id)
    if isinstance(curve, Circle):
        return abs(math.dist(point, center) - radius)
    start, end = sketch.point(curve.start), sketch.point(curve.end)
    start_angle, sweep = arc_sweep(center, start, end)
    angle = math.atan2(point[1] - center[1], point[0] - center[0])
    if (angle - start_angle) % (2 * math.pi) <= sweep:
        return abs(math.dist(point, center) - radius)
    return min(math.dist(point, start), math.dist(point, end))


def arc_sweep(center: XY, start: XY, end: XY) -> tuple[float, float]:
    """Return the start angle and counter-clockwise sweep in radians."""
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
    return start_angle, (end_angle - start_angle) % (2 * math.pi) or 2 * math.pi


def project_to_circle(center: XY, point: XY, radius: float) -> XY:
    """Project a point radially onto a circle."""
    angle = math.atan2(point[1] - center[1], point[0] - center[0])
    return center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)


def dimension_anchor(sketch: Sketch, constraint: Constraint, nudge: float) -> XY:
    """Choose a label position near the geometry measured by a dimension."""

    def mid(a: XY, b: XY) -> XY:
        return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2

    refs = constraint.refs
    if constraint.kind in ("radius", "diameter"):
        curve = sketch.geo[refs[0]]
        if not isinstance(curve, Circle | Arc):
            raise ValueError("A radius or diameter dimension needs a circle or arc.")
        center, radius = sketch.point(curve.center), sketch.radius(curve.id)
        angle = math.pi / 4
        if isinstance(curve, Arc):
            start, sweep = arc_sweep(center, sketch.point(curve.start), sketch.point(curve.end))
            angle = start + sweep / 2
        return center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)
    if constraint.kind == "angle":
        a, b = sketch.line_points(refs[0]), sketch.line_points(refs[1])
        return mid(mid(*a), mid(*b))
    if constraint.kind in ("distance_x", "distance_y"):
        center = mid(sketch.point(refs[0]), sketch.point(refs[1]))
        return (
            (center[0], center[1] - nudge)
            if constraint.kind == "distance_x"
            else (center[0] - nudge, center[1])
        )
    if len(refs) == 1:
        a, b = sketch.line_points(refs[0])
        length = math.dist(a, b) or 1
        center = mid(a, b)
        return (
            center[0] - (b[1] - a[1]) / length * nudge,
            center[1] + (b[0] - a[0]) / length * nudge,
        )
    if sketch.ref_type(refs[1]) == "line":
        point, (a, b) = sketch.point(refs[0]), sketch.line_points(refs[1])
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)
        return mid(point, (a[0] + t * dx, a[1] + t * dy))
    return mid(sketch.point(refs[0]), sketch.point(refs[1]))


def infer_dimension(sketch: Sketch, selection: Sequence[str]) -> str:
    """Choose the existing dimension type appropriate for selected geometry."""
    try:
        types = sorted(sketch.ref_type(item) for item in selection)
    except KeyError as exc:
        raise ValueError(str(exc)) from None
    if types == ["line"] and selection[0] not in AXES:
        return "distance"
    if types == ["round"]:
        return "diameter" if isinstance(sketch.geo[selection[0]], Circle) else "radius"
    if types == ["line", "line"]:
        return "angle"
    if types in (["point", "point"], ["line", "point"]):
        return "distance"
    raise ValueError(
        "Dimension: select a line, circle, arc, two lines, or two points / point and line."
    )


def add_rectangle(
    sketch: Sketch, start: XY, end: XY, start_snap: str | None = None, end_snap: str | None = None
) -> list[str]:
    """Add four connected, horizontal/vertical lines for opposite corners."""
    if abs(end[0] - start[0]) < 1e-9 or abs(end[1] - start[1]) < 1e-9:
        raise ValueError("A rectangle needs two different corners and nonzero width and height.")
    corners = [start, (end[0], start[1]), end, (start[0], end[1])]
    lines = [sketch.add_line(*corners[i], *corners[(i + 1) % 4]) for i in range(4)]
    for i, line in enumerate(lines):
        sketch.add_constraint(
            "coincident", [sketch.geo[line].p2, sketch.geo[lines[(i + 1) % 4]].p1]
        )
        sketch.add_constraint("horizontal" if i % 2 == 0 else "vertical", [line])
    for point, snap in ((sketch.geo[lines[0]].p1, start_snap), (sketch.geo[lines[2]].p1, end_snap)):
        if snap:
            sketch.add_constraint("coincident", [point, snap])
    return lines
