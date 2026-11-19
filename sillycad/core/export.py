"""Binary STL export."""

import logging
import math
import struct
from pathlib import Path

from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.BRepTools import breptools
from OCC.Core.StlAPI import StlAPI_Writer
from OCC.Core.TopoDS import TopoDS_Shape

from sillycad.core.constants import STL_ANGULAR_DEFLECTION, STL_LINEAR_DEFLECTION

log = logging.getLogger(__name__)


def export_stl(
    shape: TopoDS_Shape,
    path: str | Path,
    linear_deflection: float = STL_LINEAR_DEFLECTION,
    angular_deflection: float = STL_ANGULAR_DEFLECTION,
) -> int:
    """Mesh ``shape`` and write it to ``path`` as binary STL.

    ``linear_deflection`` is in mm, ``angular_deflection`` in degrees.
    Returns the number of triangles written. Raises RuntimeError on failure.
    """
    path = Path(path)
    breptools.Clean(shape)  # drop any old (display) mesh so these settings apply
    mesh = BRepMesh_IncrementalMesh(
        shape, linear_deflection, False, math.radians(angular_deflection), True
    )
    if not mesh.IsDone():
        raise RuntimeError("Meshing the shape failed.")

    writer = StlAPI_Writer()
    writer.SetASCIIMode(False)
    if not writer.Write(shape, str(path)):
        raise RuntimeError(f"Could not write STL file: {path}")

    count = stl_triangle_count(path)
    log.info("Exported %d triangles to %s", count, path)
    return count


def stl_triangle_count(path: str | Path) -> int:
    """Read the triangle count from a binary STL header."""
    with open(path, "rb") as f:
        f.seek(80)  # skip the 80-byte header
        return struct.unpack("<I", f.read(4))[0]
