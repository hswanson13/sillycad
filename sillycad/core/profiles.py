"""Turn a sketch into closed profiles: OCCT faces in sketch coordinates (z = 0).

Non-construction lines, arcs and circles are joined end to end into loops.
Independent open curves can accompany closed loops but do not form faces.
A loop inside another loop becomes a hole; a loop inside a hole becomes a new
face again. Problems raise ProfileError with the trouble spots, never crash.
"""

import math
from dataclasses import dataclass

from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeVertex,
    BRepBuilderAPI_MakeWire,
)
from OCC.Core.BRepClass import BRepClass_FaceClassifier
from OCC.Core.BRepExtrema import BRepExtrema_DistShapeShape
from OCC.Core.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
from OCC.Core.ShapeFix import ShapeFix_Face
from OCC.Core.TopAbs import TopAbs_IN
from OCC.Core.TopoDS import TopoDS_Edge, TopoDS_Face, TopoDS_Vertex, TopoDS_Wire

from sillycad.core.constants import POINT_TOLERANCE
from sillycad.core.sketch import XY, Arc, Circle, Line, Sketch


class ProfileError(ValueError):
    """The sketch can't become faces. ``points`` are the trouble spots (sketch mm)."""

    def __init__(self, message: str, points: list[XY] | None = None) -> None:
        super().__init__(message)
        self.points = points or []


@dataclass(frozen=True)
class ProfileAnalysis:
    """Closed faces and independent open curves excluded from those faces."""

    faces: list[TopoDS_Face]
    open_curves: frozenset[str]
    open_ends: list[XY]

    def warning(self) -> str:
        count = len(self.open_curves)
        if not count:
            return ""
        return (
            f"{count} open curve{'s' if count != 1 else ''} not included in the profile. "
            "Make guides construction geometry or close them."
        )


def analyze_profiles(sketch: Sketch) -> ProfileAnalysis:
    """Find closed faces and report independent open curves. Raises ProfileError."""
    curves = [g for g in sketch.geo.values() if isinstance(g, Line | Arc | Circle)]
    curves = [c for c in curves if not c.construction]
    if not curves:
        raise ProfileError("No profile yet: draw a closed shape (construction lines don't count).")
    loops = _Loops(sketch, curves)
    _check_crossings(loops.edges)
    return ProfileAnalysis(_faces(loops.wires, loops.samples), loops.open_curves, loops.open_ends)


def find_profiles(sketch: Sketch) -> list[TopoDS_Face]:
    """Return the closed profiles of ``sketch`` as faces. Raises ProfileError."""
    return analyze_profiles(sketch).faces


def sole_circular_profile(sketch: Sketch) -> Circle | None:
    """Return the only profile curve if it is a circle, ignoring independent open curves."""
    analysis = analyze_profiles(sketch)
    curves = [
        curve
        for curve in sketch.geo.values()
        if isinstance(curve, Line | Arc | Circle)
        and not curve.construction
        and curve.id not in analysis.open_curves
    ]
    return curves[0] if len(curves) == 1 and isinstance(curves[0], Circle) else None


def curve_edge(sketch: Sketch, curve: Line | Arc | Circle) -> TopoDS_Edge:
    """A standalone OCCT edge for one sketch curve (used for drawing sketches in 3D)."""
    if isinstance(curve, Line):
        p1, p2 = sketch.line_points(curve.id)
        return BRepBuilderAPI_MakeEdge(_pnt(p1), _pnt(p2)).Edge()
    if isinstance(curve, Circle):
        return BRepBuilderAPI_MakeEdge(_circ(sketch.point(curve.center), curve.radius)).Edge()
    circ = _circ(sketch.point(curve.center), sketch.radius(curve.id))
    start, end = sketch.point(curve.start), sketch.point(curve.end)
    return BRepBuilderAPI_MakeEdge(circ, _pnt(start), _pnt(end)).Edge()


class _Loops:
    """Join curves end to end into closed wires.

    Ends closer than POINT_TOLERANCE share one OCCT vertex, so the wires are
    connected exactly.
    """

    def __init__(self, sketch: Sketch, curves: list[Line | Arc | Circle]) -> None:
        self.sketch = sketch
        self.nodes: list[XY] = []
        self.vertices: list[TopoDS_Vertex] = []
        self.edges: list[list[tuple[TopoDS_Edge, int, int]]] = []  # per loop: (edge, node, node)
        self.wires: list[TopoDS_Wire] = []
        self.samples: list[XY] = []  # one point on each loop

        ends: dict[int, list[tuple[Line | Arc, int]]] = {}  # node -> [(curve, other node)]
        for c in curves:
            if isinstance(c, Circle):
                self._add_circle(c)
                continue
            a, b = self._node(self._start(c)), self._node(self._end(c))
            if a == b:
                raise ProfileError("A line or arc has zero length.", [self.nodes[a]])
            ends.setdefault(a, []).append((c, b))
            ends.setdefault(b, []).append((c, a))

        loose_nodes = [n for n, cs in ends.items() if len(cs) == 1]
        self.open_ends = [self.nodes[n] for n in loose_nodes]
        branches = [self.nodes[n] for n, cs in ends.items() if len(cs) > 2]
        if branches:
            raise ProfileError(
                "More than two edges meet at a point (red ring in the sketch). "
                "Make the extra lines construction lines.",
                branches,
            )
        open_nodes: set[int] = set()
        pending = list(loose_nodes)
        while pending:
            node = pending.pop()
            if node not in open_nodes:
                open_nodes.add(node)
                pending.extend(other for _, other in ends[node] if other not in open_nodes)
        self._walk({node: links for node, links in ends.items() if node not in open_nodes})
        if not self.wires and self.open_ends:
            raise ProfileError(
                f"Open profile: {len(self.open_ends)} loose end(s) (red rings in the sketch). "
                "Join them to other ends: draw onto the point, or add Coincident.",
                self.open_ends,
            )
        open_edges: list[tuple[TopoDS_Edge, int, int]] = []
        open_curves: set[str] = set()
        for node, links in ends.items():
            if node in open_nodes:
                for curve, other in links:
                    if curve.id not in open_curves:
                        open_edges.append((self._edge(curve, node, other), node, other))
                        open_curves.add(curve.id)
        self.open_curves = frozenset(open_curves)
        if open_edges:
            self.edges.append(open_edges)

    def _start(self, c: Line | Arc) -> XY:
        return self.sketch.point(c.p1 if isinstance(c, Line) else c.start)

    def _end(self, c: Line | Arc) -> XY:
        return self.sketch.point(c.p2 if isinstance(c, Line) else c.end)

    def _node(self, xy: XY) -> int:
        for i, n in enumerate(self.nodes):
            if math.dist(n, xy) < POINT_TOLERANCE:
                return i
        self.nodes.append(xy)
        self.vertices.append(BRepBuilderAPI_MakeVertex(_pnt(xy)).Vertex())
        return len(self.nodes) - 1

    def _add_circle(self, c: Circle) -> None:
        center = self.sketch.point(c.center)
        edge = BRepBuilderAPI_MakeEdge(_circ(center, c.radius)).Edge()
        self.edges.append([(edge, -1, -1)])
        self.wires.append(BRepBuilderAPI_MakeWire(edge).Wire())
        self.samples.append((center[0] + c.radius, center[1]))

    def _walk(self, ends: dict[int, list[tuple[Line | Arc, int]]]) -> None:
        """Follow each loop around. Every node has exactly two curves at this point."""
        used: set[str] = set()
        for first_node, first_curves in ends.items():
            if first_curves[0][0].id in used:
                continue
            loop: list[tuple[TopoDS_Edge, int, int]] = []
            node, (curve, nxt) = first_node, first_curves[0]
            while True:
                used.add(curve.id)
                loop.append((self._edge(curve, node, nxt), node, nxt))
                node = nxt
                if node == first_node:
                    break
                curve, nxt = next((c, o) for c, o in ends[node] if c.id not in used)
            wire = BRepBuilderAPI_MakeWire()
            for edge, _, _ in loop:
                wire.Add(edge)
            self.edges.append(loop)
            self.wires.append(wire.Wire())
            self.samples.append(self.nodes[first_node])

    def _edge(self, c: Line | Arc, a: int, b: int) -> TopoDS_Edge:
        """Edge for curve ``c`` running between nodes ``a`` and ``b`` (either direction)."""
        va, vb = self.vertices[a], self.vertices[b]
        if isinstance(c, Line):
            return BRepBuilderAPI_MakeEdge(va, vb).Edge()
        circ = _circ(self.sketch.point(c.center), self.sketch.radius(c.id))
        if self._node(self._start(c)) != a:
            va, vb = vb, va  # an OCCT circle edge runs counter-clockwise, like our arcs
        return BRepBuilderAPI_MakeEdge(circ, va, vb).Edge()


def _check_crossings(loops: list[list[tuple[TopoDS_Edge, int, int]]]) -> None:
    """Raise if any two edges cross or touch, except neighbours at their shared end."""
    edges = [e for loop in loops for e in loop]
    spots: list[XY] = []
    for i, (e1, a1, b1) in enumerate(edges):
        for e2, a2, b2 in edges[i + 1 :]:
            if {a1, b1} & {a2, b2} - {-1}:
                continue  # neighbours share an end point
            dist = BRepExtrema_DistShapeShape(e1, e2)
            if dist.IsDone() and dist.Value() < POINT_TOLERANCE:
                p = dist.PointOnShape1(1)
                spots.append((p.X(), p.Y()))
    if spots:
        raise ProfileError(
            "The profile crosses itself (red rings in the sketch). "
            "Edges may only meet at their ends.",
            spots,
        )


def _faces(wires: list[TopoDS_Wire], samples: list[XY]) -> list[TopoDS_Face]:
    """Nest loops: even depth = outer boundary, odd depth = hole in its parent."""
    plain = [BRepBuilderAPI_MakeFace(w, True).Face() for w in wires]

    def inside(i: int, j: int) -> bool:
        classifier = BRepClass_FaceClassifier(plain[j], _pnt(samples[i]), POINT_TOLERANCE)
        return classifier.State() == TopAbs_IN

    parents = [[j for j in range(len(wires)) if j != i and inside(i, j)] for i in range(len(wires))]
    depth = [len(p) for p in parents]
    faces = []
    for i in range(len(wires)):
        if depth[i] % 2:
            continue  # a hole; added to its parent below
        maker = BRepBuilderAPI_MakeFace(plain[i])
        for j in range(len(wires)):
            if depth[j] == depth[i] + 1 and i in parents[j]:
                maker.Add(wires[j])
        fix = ShapeFix_Face(maker.Face())
        fix.FixOrientation()  # holes must run opposite to the outer boundary
        faces.append(fix.Face())
    return faces


def _pnt(xy: XY) -> gp_Pnt:
    return gp_Pnt(xy[0], xy[1], 0.0)


def _circ(center: XY, radius: float) -> gp_Circ:
    return gp_Circ(gp_Ax2(_pnt(center), gp_Dir(0, 0, 1)), radius)
