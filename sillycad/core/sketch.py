"""2D sketch model: plain dataclasses with stable string IDs.

Coordinates are millimetres and angles are degrees. Lines, circles and arcs
refer to their points by ID. Every curve owns its own points; coincident
constraints join them (the same approach FreeCAD and SolveSpace use).

Every sketch also has three built-in references that constraints may use:
the origin point and the two sketch axes.
"""

import math
from dataclasses import dataclass, field

ORIGIN = "origin"
X_AXIS = "x_axis"
Y_AXIS = "y_axis"
REFERENCES = {ORIGIN, X_AXIS, Y_AXIS}
AXES = {X_AXIS, Y_AXIS}


@dataclass
class Point:
    id: str
    x: float
    y: float


@dataclass
class Line:
    id: str
    p1: str
    p2: str
    construction: bool = False

    @property
    def points(self) -> list[str]:
        return [self.p1, self.p2]


@dataclass
class Circle:
    id: str
    center: str
    radius: float
    construction: bool = False

    @property
    def points(self) -> list[str]:
        return [self.center]


@dataclass
class Arc:
    """Counter-clockwise arc from ``start`` to ``end`` around ``center``."""

    id: str
    center: str
    start: str
    end: str
    construction: bool = False

    @property
    def points(self) -> list[str]:
        return [self.center, self.start, self.end]


Curve = Line | Circle | Arc
Geometry = Point | Curve


@dataclass
class Constraint:
    """A geometric constraint or a dimension (``value`` in mm or degrees)."""

    id: str
    kind: str
    refs: list[str]
    value: float | None = None


# kind -> (what to select, allowed selections). Selection types are "point",
# "line" and "round" (circle or arc); a selection is sorted into that order.
RULES: dict[str, tuple[str, list[tuple[str, ...]]]] = {
    "coincident": ("two points", [("point", "point")]),
    "horizontal": ("a line or two points", [("line",), ("point", "point")]),
    "vertical": ("a line or two points", [("line",), ("point", "point")]),
    "parallel": ("two lines", [("line", "line")]),
    "perpendicular": ("two lines", [("line", "line")]),
    "equal": ("two lines, or two circles/arcs", [("line", "line"), ("round", "round")]),
    "point_on_line": ("a point and a line", [("point", "line")]),
    "tangent": (
        "a line and a circle/arc, or two circles/arcs",
        [("line", "round"), ("round", "round")],
    ),
    "midpoint": ("a point and a line", [("point", "line")]),
    "fix": ("a point", [("point",)]),
    "distance": (
        "a line, two points, or a point and a line",
        [("line",), ("point", "point"), ("point", "line")],
    ),
    "distance_x": ("a line or two points", [("line",), ("point", "point")]),
    "distance_y": ("a line or two points", [("line",), ("point", "point")]),
    "angle": ("two lines", [("line", "line")]),
    "radius": ("a circle or arc", [("round",)]),
    "diameter": ("a circle or arc", [("round",)]),
}
DIMENSIONS = {"distance", "distance_x", "distance_y", "angle", "radius", "diameter"}
_TYPE_ORDER = {"point": 0, "line": 1, "round": 2}
_LABELS = {
    "distance_x": "Horizontal distance",
    "distance_y": "Vertical distance",
    "point_on_line": "Point on line",
}

XY = tuple[float, float]


def label(kind: str) -> str:
    """Human-readable name of a constraint kind."""
    return _LABELS.get(kind, kind.capitalize())


@dataclass
class Sketch:
    """Geometry and constraints of one 2D sketch."""

    geo: dict[str, Geometry] = field(default_factory=dict)
    constraints: dict[str, Constraint] = field(default_factory=dict)
    next_id: int = 1

    def new_id(self, prefix: str) -> str:
        """Return a fresh ID like ``p12``. IDs are never reused within a sketch."""
        new = f"{prefix}{self.next_id}"
        self.next_id += 1
        return new

    # ── Geometry ────────────────────────────────────────────────────

    def add_point(self, x: float, y: float) -> str:
        """Add a point and return its ID."""
        pid = self.new_id("p")
        self.geo[pid] = Point(pid, x, y)
        return pid

    def add_line(
        self, x1: float, y1: float, x2: float, y2: float, construction: bool = False
    ) -> str:
        """Add a line (and its two end points) and return the line ID."""
        p1, p2 = self.add_point(x1, y1), self.add_point(x2, y2)
        lid = self.new_id("l")
        self.geo[lid] = Line(lid, p1, p2, construction)
        return lid

    def add_circle(self, cx: float, cy: float, radius: float, construction: bool = False) -> str:
        """Add a circle (and its center point) and return the circle ID."""
        center = self.add_point(cx, cy)
        cid = self.new_id("c")
        self.geo[cid] = Circle(cid, center, radius, construction)
        return cid

    def add_arc(
        self,
        cx: float,
        cy: float,
        sx: float,
        sy: float,
        ex: float,
        ey: float,
        construction: bool = False,
    ) -> str:
        """Add a counter-clockwise arc from start to end around center. Returns the arc ID."""
        center, start, end = self.add_point(cx, cy), self.add_point(sx, sy), self.add_point(ex, ey)
        aid = self.new_id("a")
        self.geo[aid] = Arc(aid, center, start, end, construction)
        return aid

    def delete(self, ids: list[str]) -> None:
        """Delete geometry and everything that depends on it.

        Deleting a point deletes the curve it belongs to; deleting a curve
        deletes its points; constraints on anything deleted go too.
        Constraint IDs may be passed as well.
        """
        doomed = set(ids) - REFERENCES
        curves = [g for g in self.geo.values() if not isinstance(g, Point)]
        doomed |= {c.id for c in curves if doomed & set(c.points)}
        for c in curves:
            if c.id in doomed:
                doomed |= set(c.points)
        for gid in doomed:
            self.geo.pop(gid, None)
            self.constraints.pop(gid, None)
        for cid in [c.id for c in self.constraints.values() if doomed & set(c.refs)]:
            del self.constraints[cid]

    def point(self, pid: str) -> XY:
        """Coordinates of a point (the origin included)."""
        if pid == ORIGIN:
            return (0.0, 0.0)
        p = self.geo[pid]
        return (p.x, p.y)

    def line_points(self, lid: str) -> tuple[XY, XY]:
        """End point coordinates of a line (the axes included)."""
        if lid == X_AXIS:
            return (0.0, 0.0), (1.0, 0.0)
        if lid == Y_AXIS:
            return (0.0, 0.0), (0.0, 1.0)
        line = self.geo[lid]
        return self.point(line.p1), self.point(line.p2)

    def radius(self, gid: str) -> float:
        """Radius of a circle or arc."""
        g = self.geo[gid]
        if isinstance(g, Circle):
            return g.radius
        return math.dist(self.point(g.center), self.point(g.start))

    def ref_type(self, gid: str) -> str:
        """Selection type of an entity: "point", "line" or "round"."""
        if gid == ORIGIN:
            return "point"
        if gid in AXES:
            return "line"
        g = self.geo.get(gid)
        if isinstance(g, Point):
            return "point"
        if isinstance(g, Line):
            return "line"
        if isinstance(g, Circle | Arc):
            return "round"
        raise KeyError(f"Unknown sketch item: {gid}")

    # ── Constraints ─────────────────────────────────────────────────

    def add_constraint(self, kind: str, refs: list[str], value: float | None = None) -> str:
        """Add a constraint on the selected entities and return its ID.

        The selection may be in any order. Dimensions without a ``value``
        take the current measurement, so adding one never moves geometry.
        Raises ValueError with a user-facing message for invalid selections.
        """
        refs = self._check_selection(kind, refs)
        if kind in DIMENSIONS:
            refs = self._orient(kind, refs)
            if value is None:
                value = self.measure(kind, refs)
            check_value(kind, value)
        cid = self.new_id("k")
        self.constraints[cid] = Constraint(cid, kind, refs, value)
        return cid

    def set_value(self, cid: str, value: float) -> None:
        """Change a dimension's value. Raises ValueError if it's not allowed."""
        constraint = self.constraints[cid]
        check_value(constraint.kind, value)
        constraint.value = value

    def measure(self, kind: str, refs: list[str]) -> float:
        """Current value of a dimension on ``refs`` (mm or degrees)."""
        if kind == "distance":
            if len(refs) == 1:
                return math.dist(*self.line_points(refs[0]))
            if self.ref_type(refs[1]) == "line":
                return _point_line_distance(self.point(refs[0]), *self.line_points(refs[1]))
            return math.dist(self.point(refs[0]), self.point(refs[1]))
        if kind in ("distance_x", "distance_y"):
            axis = 0 if kind == "distance_x" else 1
            return self.point(refs[1])[axis] - self.point(refs[0])[axis]
        if kind == "angle":
            (a1, a2), (b1, b2) = self.line_points(refs[0]), self.line_points(refs[1])
            da = (a2[0] - a1[0], a2[1] - a1[1])
            db = (b2[0] - b1[0], b2[1] - b1[1])
            cross = da[0] * db[1] - da[1] * db[0]
            dot = da[0] * db[0] + da[1] * db[1]
            return math.degrees(math.atan2(cross, dot))
        if kind == "radius":
            return self.radius(refs[0])
        if kind == "diameter":
            return 2 * self.radius(refs[0])
        raise ValueError(f"{label(kind)} is not a dimension.")

    def _check_selection(self, kind: str, refs: list[str]) -> list[str]:
        if kind not in RULES:
            raise ValueError(f"Unknown constraint: {kind}")
        name, (need, signatures) = label(kind), RULES[kind]
        if len(set(refs)) != len(refs):
            raise ValueError(f"{name} needs {need}, not the same item twice.")
        try:
            ordered = sorted(refs, key=lambda r: _TYPE_ORDER[self.ref_type(r)])
        except KeyError as exc:
            raise ValueError(str(exc)) from None
        if tuple(self.ref_type(r) for r in ordered) not in signatures:
            raise ValueError(f"{name} needs {need}.")
        if all(r in REFERENCES for r in refs):
            raise ValueError(f"{name} needs at least one sketch item, not just the origin/axes.")
        segment_use = kind in ("equal", "midpoint") or (kind in DIMENSIONS and len(refs) == 1)
        if segment_use and AXES & set(refs):
            raise ValueError(f"{name} can't use an axis that way.")
        return ordered

    def _orient(self, kind: str, refs: list[str]) -> list[str]:
        """Order dimension references so the measured value is positive."""
        if kind in ("distance_x", "distance_y"):
            if len(refs) == 1:  # a line: measure between its end points
                line = self.geo[refs[0]]
                refs = [line.p1, line.p2]
            if self.measure(kind, refs) < 0:
                refs = [refs[1], refs[0]]
        elif kind == "angle" and self.measure(kind, refs) < 0:
            refs = [refs[1], refs[0]]
        return refs


def check_value(kind: str, value: float) -> None:
    """Raise ValueError if ``value`` is not allowed for a dimension of ``kind``."""
    if not math.isfinite(value):
        raise ValueError("Please enter a number.")
    if kind in ("distance", "radius", "diameter") and value <= 0:
        raise ValueError(f"{label(kind)} must be greater than zero.")


def _point_line_distance(p: XY, a: XY, b: XY) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return abs(dx * (p[1] - a[1]) - dy * (p[0] - a[0])) / math.hypot(dx, dy)
