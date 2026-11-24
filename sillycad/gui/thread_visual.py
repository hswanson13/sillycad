"""Non-modeling viewport linework for cosmetic internal threads.

Strokes are drawn only on the bore faces that survive in the body: each threaded
feature's coaxial cylinder or cone faces are found exactly, and helix samples are
kept where they fall inside a face's 2D outline. No 3D point-in-solid tests are
needed, so the display stays fast enough for live previews.
"""

import logging
import math
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property

from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
from OCC.Core.BRepTools import breptools
from OCC.Core.BRepTopAdaptor import BRepTopAdaptor_FClass2d
from OCC.Core.ElSLib import elslib
from OCC.Core.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder
from OCC.Core.gp import gp_Cone, gp_Cylinder, gp_Pnt, gp_Pnt2d, gp_Trsf
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_ON
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Face, TopoDS_Shape, topods

from sillycad.core.document import Document, Model, _through_all_length
from sillycad.core.features import Hole, Pocket, SketchFeature, bore_diameter
from sillycad.core.geometry import plane_trsf
from sillycad.core.profiles import sole_circular_profile
from sillycad.core.threads import resolve_thread

log = logging.getLogger(__name__)

_SEGMENTS_PER_TURN = 24
_MAX_FEATURE_TURNS = 48
_MAX_TOTAL_SEGMENTS = 2400
_TOLERANCE = 1e-4


@dataclass(frozen=True)
class _Bore:
    """A threaded bore in its sketch frame: depth runs along ``direction`` from the plane."""

    name: str
    center: tuple[float, float]
    radius: float
    taper: float  # diametral taper per unit depth
    pitch: float
    hand: int  # +1 or -1: the angular direction as depth increases
    start: float  # where the thread starts (below any recess)
    end: float
    direction: int
    transform: gp_Trsf

    def radius_at(self, depth: float) -> float:
        return self.radius - self.taper * (depth - self.start) / 2

    @cached_property
    def inverse(self) -> gp_Trsf:
        return self.transform.Inverted()

    def local(self, point: gp_Pnt) -> tuple[float, float]:
        """(radial distance, depth) of a model-space point."""
        p = point.Transformed(self.inverse)
        return math.hypot(p.X() - self.center[0], p.Y() - self.center[1]), self.direction * p.Z()

    def point(self, depth: float, angle: float, inset: float = 0.0) -> gp_Pnt:
        radius = self.radius_at(depth) - inset
        x = self.center[0] + radius * math.cos(angle)
        y = self.center[1] + radius * math.sin(angle)
        return gp_Pnt(x, y, self.direction * depth).Transformed(self.transform)


def thread_linework(doc: Document, model: Model) -> list[TopoDS_Shape]:
    """Make non-selectable thread strokes on surviving bore walls, not solid geometry."""
    if model.shape is None:
        return []
    bores = [
        bore
        for feature in doc.features
        if isinstance(feature, Hole | Pocket)
        and feature.thread is not None
        and feature.id not in model.errors
        and (bore := _bore(doc, model.shape, feature)) is not None
    ]
    if not bores:
        return []
    shown = max(1, _MAX_TOTAL_SEGMENTS // _SEGMENTS_PER_TURN)
    if len(bores) > shown:
        log.warning(
            "Cosmetic thread display is limited to %d features; %d were omitted.",
            shown,
            len(bores) - shown,
        )
        bores = bores[:shown]
    turns = min(_MAX_FEATURE_TURNS, shown // len(bores))
    faces = list(_faces(model.shape))
    return [strokes for bore in bores if (strokes := _strokes(bore, _walls(faces, bore), turns))]


def _bore(doc: Document, body: TopoDS_Shape, feature: Hole | Pocket) -> _Bore | None:
    """The threaded bore of a valid feature, or None if it has nothing to show."""
    assert feature.thread is not None
    if isinstance(feature, Hole) and not feature.sketch_id:
        if feature.face is None or feature.center is None:
            return None
        sketch = SketchFeature("", "", plane="Face", face=feature.face)
    elif isinstance(sketch := doc.find(feature.sketch_id), SketchFeature):
        pass
    else:
        return None
    if isinstance(feature, Hole):
        center = feature.center or sketch.sketch.point(feature.point_id)
        diameter = bore_diameter(feature)
        recess = {
            "counterbore": feature.head_depth,
            "spotface": feature.head_depth,
            "countersink": (feature.head_diameter - diameter)
            / (2 * math.tan(math.radians(feature.countersink_angle / 2))),
        }.get(feature.style, 0.0)
    else:
        circle = sole_circular_profile(sketch.sketch)
        if circle is None:
            return None
        center, diameter, recess = sketch.sketch.point(circle.center), 2 * circle.radius, 0.0
    size = resolve_thread(feature.thread)
    cutter = _through_all_length(body, sketch) if feature.through_all else feature.length
    length = min(feature.thread.depth or math.inf, cutter - recess)
    if length <= 0:
        return None
    direction = 1 if feature.reversed else -1
    return _Bore(
        feature.name,
        center,
        diameter / 2,
        size.taper,
        size.pitch,
        direction * (-1 if feature.thread.left_hand else 1),
        recess,
        recess + length,
        direction,
        plane_trsf(sketch.placement(), sketch.offset),
    )


def _faces(shape: TopoDS_Shape) -> Iterator[TopoDS_Face]:
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        yield topods.Face(explorer.Current())
        explorer.Next()


class _Wall:
    """A bore face that answers whether a point on its surface lies inside its outline."""

    def __init__(self, face: TopoDS_Face, surface: gp_Cylinder | gp_Cone, bore: _Bore) -> None:
        self._surface = surface
        self._outline = BRepTopAdaptor_FClass2d(face, 1e-7)
        box = Bnd_Box()
        brepbndlib.Add(face, box)
        x0, y0, z0, x1, y1, z1 = box.Get()
        corners = [gp_Pnt(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        depths = [bore.local(corner)[1] for corner in corners]
        self.first, self.last = min(depths), max(depths)

    def contains(self, point: gp_Pnt) -> bool:
        u, v = elslib.Parameters(self._surface, point)
        return self._outline.Perform(gp_Pnt2d(u, v)) in (TopAbs_IN, TopAbs_ON)


def _walls(faces: list[TopoDS_Face], bore: _Bore) -> list[_Wall]:
    """The body's cylinder and cone faces that form this bore's threaded length."""
    walls = []
    for face in faces:
        adaptor = BRepAdaptor_Surface(face)
        kind = adaptor.GetType()
        if kind not in (GeomAbs_Cylinder, GeomAbs_Cone):
            continue
        surface = adaptor.Cylinder() if kind == GeomAbs_Cylinder else adaptor.Cone()
        axis = surface.Axis().Transformed(bore.inverse)
        location = axis.Location()
        coaxial = abs(abs(axis.Direction().Z()) - 1) < 1e-9 and (
            math.dist((location.X(), location.Y()), bore.center) < _TOLERANCE
        )
        if not coaxial:
            continue
        u0, u1, v0, v1 = breptools.UVBounds(face)
        radius, depth = bore.local(adaptor.Value((u0 + u1) / 2, (v0 + v1) / 2))
        if abs(radius - bore.radius_at(depth)) > _TOLERANCE * max(1, bore.radius):
            continue  # a counterbore, countersink, or the straight bore past a taper
        wall = _Wall(face, surface, bore)
        if wall.first < bore.end and wall.last > bore.start:
            walls.append(wall)
    return walls


def _strokes(bore: _Bore, walls: list[_Wall], turns: int) -> TopoDS_Compound | None:
    """Helix polylines on the walls; long threads show evenly spaced turns, ends included."""
    if not walls:
        return None
    first = max(bore.start, min(wall.first for wall in walls))
    last = min(bore.end, max(wall.last for wall in walls))
    count = math.ceil((last - first) / bore.pitch - _TOLERANCE)
    shown = range(count) if count <= turns else _spread(count, turns)
    step = bore.pitch / _SEGMENTS_PER_TURN
    if step <= math.ulp(max(abs(first), abs(last))):
        log.warning("Thread pitch for %s is too small to display at this scale.", bore.name)
        return None
    inset = min(0.01, bore.radius * 0.002)
    compound, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(compound)
    edges = 0
    for turn in shown:
        run = BRepBuilderAPI_MakePolygon()
        for i in range(_SEGMENTS_PER_TURN + 1):
            depth = min(first + (turn * _SEGMENTS_PER_TURN + i) * step, last)
            angle = bore.hand * math.tau * (depth - bore.start) / bore.pitch
            if bore.radius_at(depth) > inset and any(
                wall.contains(bore.point(depth, angle)) for wall in walls
            ):
                run.Add(bore.point(depth, angle, inset))
                continue
            edges += _flush(builder, compound, run)
            run = BRepBuilderAPI_MakePolygon()
        edges += _flush(builder, compound, run)
    return compound if edges else None


def _spread(count: int, turns: int) -> list[int]:
    """``turns`` indices spread evenly over ``range(count)``, including both ends."""
    if turns < 2:
        return [0]
    return sorted({round(i * (count - 1) / (turns - 1)) for i in range(turns)})


def _flush(
    builder: BRep_Builder, compound: TopoDS_Compound, run: BRepBuilderAPI_MakePolygon
) -> int:
    """Add a finished polyline run to the compound; return 1 if it had any segment."""
    if not run.IsDone():
        return 0
    builder.Add(compound, run.Wire())
    return 1
