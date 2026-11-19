"""Small OCCT helpers shared by features, export and tests."""

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCC.Core.GProp import GProp_GProps
from OCC.Core.TopoDS import TopoDS_Shape

# Base planes: (normal, sketch x direction). The sketch y direction is normal × x.
#   XY: sketch x = X, y = Y, normal +Z
#   XZ: sketch x = X, y = Z, normal -Y
#   YZ: sketch x = Y, y = Z, normal +X
PLANES: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "XY": ((0, 0, 1), (1, 0, 0)),
    "XZ": ((0, -1, 0), (1, 0, 0)),
    "YZ": ((1, 0, 0), (0, 1, 0)),
}


def make_box(dx: float, dy: float, dz: float) -> TopoDS_Shape:
    """Return an axis-aligned box with one corner at the origin (mm)."""
    return BRepPrimAPI_MakeBox(dx, dy, dz).Shape()


def volume(shape: TopoDS_Shape) -> float:
    """Return the volume of a solid in mm³."""
    props = GProp_GProps()
    brepgprop.VolumeProperties(shape, props)
    return props.Mass()


def plane_axes(plane: str, offset: float = 0.0) -> gp_Ax3:
    """Coordinate system of a base plane, moved ``offset`` mm along its normal."""
    normal, x_dir = PLANES[plane]
    origin = gp_Pnt(0, 0, 0).Translated(gp_Vec(*normal) * offset)
    return gp_Ax3(origin, gp_Dir(*normal), gp_Dir(*x_dir))


def place_on_plane(shape: TopoDS_Shape, plane: str, offset: float = 0.0) -> TopoDS_Shape:
    """Move a shape built in sketch coordinates (z = 0) onto a base plane."""
    trsf = gp_Trsf()
    trsf.SetDisplacement(gp_Ax3(), plane_axes(plane, offset))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()
