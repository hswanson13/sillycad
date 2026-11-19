"""Features of the parametric history: Sketch, Pad, Pocket and Revolve.

Features are plain data (dataclasses with stable IDs). ``document.recompute``
turns them into a solid. Lengths are mm and angles degrees; radians only at
the OCCT boundary.
"""

import math
from dataclasses import dataclass, field

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCC.Core.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Face, TopoDS_Shape

from sillycad.core.constants import POINT_TOLERANCE
from sillycad.core.geometry import place_on_plane, plane_axes, plane_trsf
from sillycad.core.profiles import curve_edge, find_profiles
from sillycad.core.sketch import X_AXIS, XY, Y_AXIS, Arc, Circle, Line, Sketch


class FeatureError(Exception):
    """A feature can't be built. The message is shown to the user."""


@dataclass
class SketchFeature:
    """A 2D sketch on a base plane ("XY", "XZ" or "YZ"), moved ``offset`` mm along its normal."""

    id: str
    name: str
    plane: str = "XY"
    offset: float = 0.0
    sketch: Sketch = field(default_factory=Sketch)

    def wires(self) -> TopoDS_Compound:
        """All sketch curves as edges in 3D, for display."""
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        for g in self.sketch.geo.values():
            if isinstance(g, Line | Arc | Circle):
                builder.Add(compound, curve_edge(self.sketch, g))
        return place_on_plane(compound, self.plane, self.offset)

    def faces(self) -> list[TopoDS_Face]:
        """Closed profiles as faces in 3D. Raises ProfileError."""
        return [place_on_plane(f, self.plane, self.offset) for f in find_profiles(self.sketch)]

    def normal(self) -> gp_Vec:
        return gp_Vec(plane_axes(self.plane).Direction())


@dataclass
class Pad:
    """Extrude a sketch's profiles and add them to the body."""

    id: str
    name: str
    sketch_id: str
    length: float = 10.0
    reversed: bool = False
    symmetric: bool = False  # half the length each side of the sketch plane


@dataclass
class Pocket:
    """Extrude a sketch's profiles and cut them out of the body (into the material)."""

    id: str
    name: str
    sketch_id: str
    length: float = 5.0
    through_all: bool = False
    reversed: bool = False


@dataclass
class Revolve:
    """Revolve a sketch's profiles around an axis and add them to the body.

    ``axis`` is "x_axis", "y_axis" or the ID of a construction line in the sketch.
    """

    id: str
    name: str
    sketch_id: str
    axis: str = Y_AXIS
    angle: float = 360.0


Feature = SketchFeature | Pad | Pocket | Revolve
SolidFeature = Pad | Pocket | Revolve


def pad_shape(pad: Pad, sk: SketchFeature) -> TopoDS_Shape:
    """The solid a Pad adds."""
    _check_length(pad.length)
    direction = sk.normal() * (-1 if pad.reversed else 1)
    start = -pad.length / 2 if pad.symmetric else 0.0
    return _extrude(sk.faces(), direction, start, pad.length)


def pocket_shape(pocket: Pocket, sk: SketchFeature, through_all_length: float) -> TopoDS_Shape:
    """The solid a Pocket removes. By default it goes into the material, against the normal."""
    length = through_all_length if pocket.through_all else pocket.length
    _check_length(length)
    direction = sk.normal() * (1 if pocket.reversed else -1)
    return _extrude(sk.faces(), direction, 0.0, length)


def revolve_shape(rev: Revolve, sk: SketchFeature) -> TopoDS_Shape:
    """The solid a Revolve adds."""
    if not 0 < rev.angle <= 360:
        raise FeatureError("The angle must be more than 0° and at most 360°.")
    a, b = revolve_axis(sk.sketch, rev.axis)
    _check_axis_clear(sk.sketch, a, b)
    faces = sk.faces()
    axis = gp_Ax1(gp_Pnt(a[0], a[1], 0), gp_Dir(b[0] - a[0], b[1] - a[1], 0))
    axis = axis.Transformed(plane_trsf(sk.plane, sk.offset))
    angle = math.radians(rev.angle)
    return fuse_all([BRepPrimAPI_MakeRevol(face, axis, angle).Shape() for face in faces])


def revolve_axis(sketch: Sketch, axis: str) -> tuple[XY, XY]:
    """Two points on a revolve axis, in sketch coordinates."""
    if axis in (X_AXIS, Y_AXIS):
        return sketch.line_points(axis)
    line = sketch.geo.get(axis)
    if not isinstance(line, Line) or not line.construction:
        raise FeatureError("The revolve axis must be a sketch axis or a construction line.")
    a, b = sketch.line_points(axis)
    if math.dist(a, b) < POINT_TOLERANCE:
        raise FeatureError("The axis line has zero length.")
    return a, b


def fuse_all(shapes: list[TopoDS_Shape]) -> TopoDS_Shape:
    result = shapes[0]
    for shape in shapes[1:]:
        result = BRepAlgoAPI_Fuse(result, shape).Shape()
    return result


def _check_length(length: float) -> None:
    if not length > 0:
        raise FeatureError("The length must be more than 0 mm.")


def _extrude(
    faces: list[TopoDS_Face], direction: gp_Vec, start: float, length: float
) -> TopoDS_Shape:
    shapes = []
    for face in faces:
        if start:
            shift = gp_Trsf()
            shift.SetTranslation(direction * start)
            face = BRepBuilderAPI_Transform(face, shift, True).Shape()
        shapes.append(BRepPrimAPI_MakePrism(face, direction * length).Shape())
    return fuse_all(shapes)


def _check_axis_clear(sketch: Sketch, a: XY, b: XY) -> None:
    """Raise if profile geometry lies on both sides of the axis line."""
    length = math.dist(a, b)
    dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length

    def side(p: XY) -> float:  # signed distance from the axis
        return dx * (p[1] - a[1]) - dy * (p[0] - a[0])

    sides: list[float] = []
    for g in sketch.geo.values():
        if not isinstance(g, Line | Arc | Circle) or g.construction:
            continue
        if isinstance(g, Line):
            sides += [side(p) for p in sketch.line_points(g.id)]
        elif isinstance(g, Circle):
            s = side(sketch.point(g.center))
            sides += [s - g.radius, s + g.radius]
        else:
            c, r = sketch.point(g.center), sketch.radius(g.id)
            start = math.atan2(sketch.point(g.start)[1] - c[1], sketch.point(g.start)[0] - c[0])
            end = math.atan2(sketch.point(g.end)[1] - c[1], sketch.point(g.end)[0] - c[0])
            sweep = (end - start) % (2 * math.pi) or 2 * math.pi
            for i in range(65):
                t = start + sweep * i / 64
                sides.append(side((c[0] + r * math.cos(t), c[1] + r * math.sin(t))))
    if sides and min(sides) < -POINT_TOLERANCE and max(sides) > POINT_TOLERANCE:
        raise FeatureError(
            "The axis crosses the profile. Keep the profile on one side of the axis."
        )
