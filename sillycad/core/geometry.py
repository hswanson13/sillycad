"""Small OCCT helpers: sketch planes, placement, volume, outlines."""

import math
from dataclasses import dataclass

from OCC.Core.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.GeomAbs import GeomAbs_Line, GeomAbs_Plane
from OCC.Core.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCC.Core.GProp import GProp_GProps
from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
from OCC.Core.TopExp import topexp
from OCC.Core.TopoDS import TopoDS_Face, TopoDS_Shape, topods
from OCC.Core.TopTools import TopTools_IndexedMapOfShape

from sillycad.core.constants import POINT_TOLERANCE

XYZ = tuple[float, float, float]


@dataclass
class Placement:
    """A sketch plane in 3D: an origin, the normal, and the sketch's x direction."""

    origin: XYZ
    normal: XYZ
    x_dir: XYZ


# Base planes. The sketch y direction is normal × x:
#   XY: sketch x = X, y = Y, normal +Z (seen from the top)
#   XZ: sketch x = X, y = Z, normal -Y (seen from the front)
#   YZ: sketch x = Y, y = Z, normal +X (seen from the right)
BASE_PLANES = {
    "XY": Placement((0, 0, 0), (0, 0, 1), (1, 0, 0)),
    "XZ": Placement((0, 0, 0), (0, -1, 0), (1, 0, 0)),
    "YZ": Placement((0, 0, 0), (1, 0, 0), (0, 1, 0)),
}


def make_box(dx: float, dy: float, dz: float) -> TopoDS_Shape:
    """Return an axis-aligned box with one corner at the origin (mm)."""
    return BRepPrimAPI_MakeBox(dx, dy, dz).Shape()


def volume(shape: TopoDS_Shape) -> float:
    """Return the volume of a solid in mm³."""
    props = GProp_GProps()
    brepgprop.VolumeProperties(shape, props)
    return props.Mass()


def plane_axes(placement: Placement, offset: float = 0.0) -> gp_Ax3:
    """Coordinate system of a sketch plane, moved ``offset`` mm along its normal."""
    origin = gp_Pnt(*placement.origin).Translated(gp_Vec(*placement.normal) * offset)
    return gp_Ax3(origin, gp_Dir(*placement.normal), gp_Dir(*placement.x_dir))


def plane_trsf(placement: Placement, offset: float = 0.0) -> gp_Trsf:
    """Transform from sketch coordinates (z = 0) to the sketch plane in 3D."""
    trsf = gp_Trsf()
    trsf.SetDisplacement(gp_Ax3(), plane_axes(placement, offset))
    return trsf


def place_on_plane(shape: TopoDS_Shape, placement: Placement, offset: float = 0.0) -> TopoDS_Shape:
    """Move a shape built in sketch coordinates (z = 0) onto a sketch plane."""
    return BRepBuilderAPI_Transform(shape, plane_trsf(placement, offset), True).Shape()


def face_placement(face: TopoDS_Face) -> Placement:
    """The plane of a flat face, with its normal pointing out of the material.

    The origin is the world origin projected onto the plane. On an upright
    or slanted face, sketch "up" is world up (+Z); on a horizontal face,
    sketch x is world X. So sketches read naturally when you look at the face.
    Raises ValueError if the face isn't flat.
    """
    surface = BRepAdaptor_Surface(face)
    if surface.GetType() != GeomAbs_Plane:
        raise ValueError("That face isn't flat. Pick a flat face to sketch on.")
    plane = surface.Plane()
    n = plane.Axis().Direction()
    if face.Orientation() == TopAbs_REVERSED:
        n.Reverse()
    normal = _clean((n.X(), n.Y(), n.Z()))
    p = plane.Location()
    distance = p.X() * normal[0] + p.Y() * normal[1] + p.Z() * normal[2]
    origin = _clean(tuple(distance * c for c in normal))
    if abs(normal[2]) < 0.9:  # upright or slanted: sketch y = world up, x = y × normal
        y_dir = _project((0.0, 0.0, 1.0), normal)
        x_dir = _cross(y_dir, normal)
    else:  # horizontal: sketch x = world X
        x_dir = _project((1.0, 0.0, 0.0), normal)
    return Placement(origin, normal, _clean(x_dir))


def outline_in_plane(
    shape: TopoDS_Shape, placement: Placement, offset: float = 0.0
) -> list[list[tuple[float, float]]]:
    """Edges of ``shape`` that lie in the sketch plane, as polylines in sketch mm.

    Used to show the face you're sketching on as a guide in the sketch editor.
    """
    to_sketch = plane_trsf(placement, offset).Inverted()
    edges = TopTools_IndexedMapOfShape()  # each edge once (faces share edges)
    topexp.MapShapes(shape, TopAbs_EDGE, edges)
    polylines = []
    for i in range(1, edges.Size() + 1):
        curve = BRepAdaptor_Curve(topods.Edge(edges.FindKey(i)))
        steps = 1 if curve.GetType() == GeomAbs_Line else 48
        u0, u1 = curve.FirstParameter(), curve.LastParameter()
        points = [
            curve.Value(u0 + (u1 - u0) * i / steps).Transformed(to_sketch) for i in range(steps + 1)
        ]
        if all(abs(p.Z()) < POINT_TOLERANCE for p in points):
            polylines.append([(p.X(), p.Y()) for p in points])
    return polylines


def _project(v: XYZ, normal: XYZ) -> XYZ:
    """``v`` flattened onto the plane with this normal, as a unit vector."""
    along = sum(a * b for a, b in zip(v, normal, strict=True))
    flat = [a - along * b for a, b in zip(v, normal, strict=True)]
    length = math.sqrt(sum(c * c for c in flat))
    return (flat[0] / length, flat[1] / length, flat[2] / length)


def _cross(a: XYZ, b: XYZ) -> XYZ:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _clean(v: tuple[float, ...]) -> XYZ:
    """Round away floating-point fuzz (1e-12) so planes compare and save cleanly."""
    return tuple(round(c, 9) + 0.0 for c in v)  # + 0.0 turns -0.0 into 0.0
