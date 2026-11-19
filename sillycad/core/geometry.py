"""Small OCCT helpers shared by features, export and tests."""

from OCC.Core.BRepGProp import brepgprop
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.GProp import GProp_GProps
from OCC.Core.TopoDS import TopoDS_Shape


def make_box(dx: float, dy: float, dz: float) -> TopoDS_Shape:
    """Return an axis-aligned box with one corner at the origin (mm)."""
    return BRepPrimAPI_MakeBox(dx, dy, dz).Shape()


def volume(shape: TopoDS_Shape) -> float:
    """Return the volume of a solid in mm³."""
    props = GProp_GProps()
    brepgprop.VolumeProperties(shape, props)
    return props.Mass()
