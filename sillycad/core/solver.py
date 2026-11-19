"""Solve sketches with planegcs (a binding of FreeCAD's PlaneGCS solver).

The planegcs system is rebuilt from the model on every solve. Sketches are
small, and this keeps the model the single source of truth. Dimension values
are fixed parameters (``add_fixed_param``) so the solver can't change them.
Angles are converted to radians here and nowhere else.
"""

import copy
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import planegcs as gcs

from sillycad.core.constants import SOLVER_TOLERANCE
from sillycad.core.sketch import (
    ORIGIN,
    X_AXIS,
    XY,
    Y_AXIS,
    Arc,
    Circle,
    Constraint,
    Curve,
    Point,
    Sketch,
    label,
)

log = logging.getLogger(__name__)

_Pair = Callable[[int, int], int]  # a planegcs two-curve constraint method
_GOOD = (gcs.SolveStatus.Success, gcs.SolveStatus.Converged)


@dataclass
class SolveResult:
    """Outcome of a solve. The sketch geometry only changes when ``solved`` is True."""

    solved: bool
    dof: int
    conflicting: list[str] = field(default_factory=list)  # constraint IDs
    redundant: list[str] = field(default_factory=list)  # constraint IDs
    message: str = ""

    @property
    def ok(self) -> bool:
        """Solved, with no conflicting or redundant constraints."""
        return self.solved and not self.conflicting and not self.redundant

    @property
    def fully_constrained(self) -> bool:
        """Solved with no problems and zero degrees of freedom."""
        return self.ok and self.dof == 0


def solve(sketch: Sketch) -> SolveResult:
    """Solve ``sketch`` in place.

    If the solve fails, the geometry is left exactly as it was (the last good
    state), and the result lists any conflicting constraints.
    """
    try:
        system = _System(sketch)
        status = system.gcs.solve()
        diagnosis = system.gcs.diagnose()
        conflicting = system.constraint_ids(diagnosis.conflicting)
        redundant = system.constraint_ids(diagnosis.redundant)
        solved = status in _GOOD and not conflicting and system.is_valid()
        if solved:
            system.write_back()
    except Exception as exc:  # planegcs raises on bad input; never crash the app
        log.exception("Sketch solve failed")
        return SolveResult(False, -1, message=f"Solver error: {exc}")

    log.debug("solve: %s, dof=%d", status, diagnosis.dof)
    result = SolveResult(solved, diagnosis.dof, conflicting, redundant)
    result.message = _message(result, sketch)
    return result


def drag(sketch: Sketch, points: dict[str, XY], radii: dict[str, float] | None = None) -> bool:
    """Move points (and circle radii) toward targets while keeping every constraint.

    Pinning the targets exactly works when the geometry is free enough. If
    that fails, pin only x, or only y, or just start the solver at the
    targets, and keep whichever lands closest. That way partly constrained
    geometry slides along whatever freedom it has. Updates the sketch in
    place and returns True if a good solution was found.
    """
    radii = radii or {}

    def gap(s: Sketch) -> float:
        return sum(math.dist(s.point(p), xy) for p, xy in points.items()) + sum(
            abs(s.radius(c) - r) for c, r in radii.items()
        )

    try:
        exact = _drag_attempt(sketch, points, radii, "xy")
        tries = [exact] if exact else [_drag_attempt(sketch, points, radii, m) for m in "xy-"]
    except Exception:  # never crash mid-drag
        log.exception("Drag solve failed")
        return False
    solutions = [t for t in tries if t is not None]
    if not solutions:
        return False
    sketch.geo = min(solutions, key=gap).geo
    return True


def _drag_attempt(
    sketch: Sketch, points: dict[str, XY], radii: dict[str, float], pins: str
) -> Sketch | None:
    """Solve a copy with the targets pinned in ``pins`` ("xy", "x", "y" or "-" for none)."""
    trial = copy.deepcopy(sketch)
    system = _System(trial)
    system.aim(points, radii, pins)
    if system.gcs.solve() in _GOOD and system.is_valid():
        system.write_back()
        return trial
    return None


def _message(result: SolveResult, sketch: Sketch) -> str:
    def names(ids: list[str]) -> str:
        return ", ".join(f"{label(sketch.constraints[i].kind)} ({i})" for i in ids)

    if result.conflicting:
        return f"Conflicting constraints: {names(result.conflicting)}. Delete one or undo."
    if result.redundant:
        return f"Redundant constraints: {names(result.redundant)}. Delete one."
    if not result.solved:
        return "Could not solve the sketch. Kept the last good shape."
    if not sketch.geo:
        return "Empty sketch: draw something"
    if result.dof == 0:
        return "Fully constrained"
    return f"{result.dof} degree{'s' if result.dof != 1 else ''} of freedom left"


class _System:
    """A planegcs sketch built from our model, with ID maps between the two."""

    def __init__(self, sketch: Sketch) -> None:
        self.sketch = sketch
        self.gcs = gcs.Sketch()
        self.points: dict[str, int] = {}
        self.lines: dict[str, int] = {}
        self.rounds: dict[str, int] = {}  # circles and arcs
        self.radius_params: dict[str, int] = {}  # circle ID -> its radius parameter
        self.tags: dict[int, str] = {}  # planegcs constraint tag -> our constraint ID

        self._add_references()
        for g in sketch.geo.values():
            if isinstance(g, Point):
                self.points[g.id] = self.gcs.add_point(g.x, g.y)
        for g in sketch.geo.values():
            if not isinstance(g, Point):
                self._add_curve(g)
        for c in sketch.constraints.values():
            for tag in self._add_constraint(c):
                self.tags[tag] = c.id

    def _add_references(self) -> None:
        g = self.gcs

        def fixed_point(x: float, y: float) -> int:
            return g.add_point_from_params(g.add_fixed_param(x), g.add_fixed_param(y))

        origin = fixed_point(0.0, 0.0)
        self.points[ORIGIN] = origin
        self.lines[X_AXIS] = g.add_line(origin, fixed_point(1.0, 0.0))
        self.lines[Y_AXIS] = g.add_line(origin, fixed_point(0.0, 1.0))

    def _add_curve(self, c: Curve) -> None:
        g, p = self.gcs, self.points
        if isinstance(c, Circle):
            self.radius_params[c.id] = g.add_param(c.radius)
            self.rounds[c.id] = g.add_circle(p[c.center], self.radius_params[c.id])
        elif isinstance(c, Arc):
            (cx, cy), (sx, sy) = self.sketch.point(c.center), self.sketch.point(c.start)
            ex, ey = self.sketch.point(c.end)
            start = math.atan2(sy - cy, sx - cx)
            end = math.atan2(ey - cy, ex - cx)
            if end <= start:
                end += 2 * math.pi  # arcs always run counter-clockwise
            radius = math.hypot(sx - cx, sy - cy)
            self.rounds[c.id] = g.add_arc(
                p[c.center], p[c.start], p[c.end],
                g.add_param(radius), g.add_param(start), g.add_param(end),
            )  # fmt: skip
        else:
            self.lines[c.id] = g.add_line(p[c.p1], p[c.p2])

    def _add_constraint(self, c: Constraint) -> list[int]:
        g, k, r = self.gcs, c.kind, c.refs
        P, L, R = self.points, self.lines, self.rounds
        if k == "coincident":
            return [g.coincident(P[r[0]], P[r[1]])]
        if k == "horizontal":
            return [g.horizontal(L[r[0]]) if len(r) == 1 else g.horizontal_points(P[r[0]], P[r[1]])]
        if k == "vertical":
            return [g.vertical(L[r[0]]) if len(r) == 1 else g.vertical_points(P[r[0]], P[r[1]])]
        if k == "parallel":
            return [g.parallel(L[r[0]], L[r[1]])]
        if k == "perpendicular":
            return [g.perpendicular(L[r[0]], L[r[1]])]
        if k == "equal":
            if r[0] in L:
                return [g.equal_length(L[r[0]], L[r[1]])]
            return [self._round_pair(g.equal_radius_cc, g.equal_radius_ca, g.equal_radius_aa, r)]
        if k == "point_on_line":
            return [g.point_on_line(P[r[0]], L[r[1]])]
        if k == "tangent":
            if r[0] in L:
                arc = isinstance(self.sketch.geo[r[1]], Arc)
                return [(g.tangent_line_arc if arc else g.tangent_line_circle)(L[r[0]], R[r[1]])]
            pair = (g.tangent_circle_circle, g.tangent_circle_arc, g.tangent_arc_arc)
            return [self._round_pair(*pair, r)]
        if k == "midpoint":
            line = self.sketch.geo[r[1]]
            return [g.symmetric_point(P[line.p1], P[line.p2], P[r[0]])]
        if k == "fix":
            x, y = self.sketch.point(r[0])
            return list(g.fix_point(P[r[0]], x, y))

        # Dimensions: the value is a fixed parameter the solver can't change.
        value = g.add_fixed_param(math.radians(c.value) if k == "angle" else c.value)
        if k == "distance":
            if len(r) == 1:
                line = self.sketch.geo[r[0]]
                return [g.p2p_distance(P[line.p1], P[line.p2], value)]
            if r[1] in L:
                return [g.p2l_distance(P[r[0]], L[r[1]], value)]
            return [g.p2p_distance(P[r[0]], P[r[1]], value)]
        if k in ("distance_x", "distance_y"):
            axis = 0 if k == "distance_x" else 1
            a = g.get_point_param_ids(P[r[0]])[axis]
            b = g.get_point_param_ids(P[r[1]])[axis]
            return [g.difference(a, b, value)]  # b - a = value
        if k == "angle":
            return [g.l2l_angle(L[r[0]], L[r[1]], value)]
        if k in ("radius", "diameter"):
            arc = isinstance(self.sketch.geo[r[0]], Arc)
            if k == "radius":
                return [(g.arc_radius if arc else g.circle_radius)(R[r[0]], value)]
            return [(g.arc_diameter if arc else g.circle_diameter)(R[r[0]], value)]
        raise ValueError(f"Unknown constraint kind: {k}")

    def _round_pair(self, cc: _Pair, ca: _Pair, aa: _Pair, refs: list[str]) -> int:
        """Call the circle-circle, circle-arc or arc-arc variant of a constraint."""
        a, b = refs
        a_arc = isinstance(self.sketch.geo[a], Arc)
        b_arc = isinstance(self.sketch.geo[b], Arc)
        if a_arc and not b_arc:
            a, b, a_arc, b_arc = b, a, b_arc, a_arc  # circle first
        fn = aa if a_arc else (ca if b_arc else cc)
        return fn(self.rounds[a], self.rounds[b])

    def aim(self, points: dict[str, XY], radii: dict[str, float], pins: str) -> None:
        """Start the solver at the drag targets and pin the coordinates named in ``pins``."""
        g = self.gcs
        for pid, (x, y) in points.items():
            px, py = g.get_point_param_ids(self.points[pid])
            g.set_param(px, x)
            g.set_param(py, y)
            if "x" in pins:
                g.coordinate_x(self.points[pid], g.add_fixed_param(x))
            if "y" in pins:
                g.coordinate_y(self.points[pid], g.add_fixed_param(y))
        for cid, r in radii.items():
            g.set_param(self.radius_params[cid], r)
            if pins != "-":
                g.circle_radius(self.rounds[cid], g.add_fixed_param(r))

    def constraint_ids(self, tags: list[int]) -> list[str]:
        """Our constraint IDs for planegcs tags, without duplicates."""
        return list(dict.fromkeys(self.tags[t] for t in tags if t in self.tags))

    def is_valid(self) -> bool:
        """Every constraint is satisfied and every radius is positive."""
        errors_ok = all(abs(self.gcs.constraint_error(t)) < SOLVER_TOLERANCE for t in self.tags)
        radii_ok = all(self._radius(gid) > SOLVER_TOLERANCE for gid in self.rounds)
        return errors_ok and radii_ok

    def _radius(self, gid: str) -> float:
        if isinstance(self.sketch.geo[gid], Arc):
            return self.gcs.get_arc(self.rounds[gid]).radius
        return self.gcs.get_circle(self.rounds[gid]).radius

    def write_back(self) -> None:
        """Copy solved values into the model."""
        for pid, point_id in self.points.items():
            if pid != ORIGIN:
                p = self.sketch.geo[pid]
                p.x, p.y = self.gcs.get_point(point_id)
        for gid in self.rounds:
            g = self.sketch.geo[gid]
            if isinstance(g, Circle):
                g.radius = self._radius(gid)
