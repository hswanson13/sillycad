"""Features of the parametric history. M3 has sketches; solids come in M4."""

from dataclasses import dataclass, field

from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Compound

from sillycad.core.geometry import place_on_plane
from sillycad.core.profiles import curve_edge
from sillycad.core.sketch import Arc, Circle, Line, Sketch


@dataclass
class SketchFeature:
    """A 2D sketch on a base plane ("XY", "XZ" or "YZ"), moved ``offset`` mm along its normal."""

    id: str
    name: str
    plane: str = "XY"
    offset: float = 0.0
    sketch: Sketch = field(default_factory=Sketch)
    visible: bool = True

    def wires(self) -> TopoDS_Compound:
        """All sketch curves as edges in 3D, for display."""
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        for g in self.sketch.geo.values():
            if isinstance(g, Line | Arc | Circle):
                builder.Add(compound, curve_edge(self.sketch, g))
        return place_on_plane(compound, self.plane, self.offset)
