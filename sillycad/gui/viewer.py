"""3D viewport built on pythonocc's Qt viewer widget.

Mouse: left-drag orbits, middle-drag pans, right-drag or wheel zooms.
"""

from OCC.Display.backend import load_backend

load_backend("pyside6")  # must run before importing qtDisplay

from OCC.Core.AIS import AIS_TextLabel, AIS_Trihedron  # noqa: E402
from OCC.Core.Bnd import Bnd_Box  # noqa: E402
from OCC.Core.BRepBndLib import brepbndlib  # noqa: E402
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeFace  # noqa: E402
from OCC.Core.Geom import Geom_Axis2Placement  # noqa: E402
from OCC.Core.gp import gp_Ax2, gp_Pln, gp_Pnt  # noqa: E402
from OCC.Core.TopoDS import TopoDS_Shape  # noqa: E402
from OCC.Display.OCCViewer import rgb_color  # noqa: E402
from OCC.Display.qtDisplay import qtViewer3d  # noqa: E402

from sillycad.core.geometry import plane_axes, plane_trsf  # noqa: E402

SKETCH_COLOR = rgb_color(0.1, 0.3, 1.0)
PLANE_COLORS = {"XY": (0.25, 0.45, 0.95), "XZ": (0.25, 0.7, 0.3), "YZ": (0.9, 0.3, 0.3)}


class Viewer(qtViewer3d):
    """The 3D view. Call ``init()`` once, after the window is shown."""

    def init(self) -> None:
        """Create the OCCT viewer. Needs a real native window, so call after show()."""
        self.InitDriver()

    def show_model(
        self,
        solid: TopoDS_Shape | None,
        sketches: list[TopoDS_Shape],
        planes: bool = True,
        fit: bool = False,
    ) -> None:
        """Replace what's on screen: the body, sketch wires, base planes and origin axes."""
        display = self._display
        display.EraseAll()
        size = _model_size(solid)
        if planes:
            self._show_planes(size)
        trihedron = AIS_Trihedron(Geom_Axis2Placement(gp_Ax2()))
        trihedron.SetSize(size * 0.6)
        display.Context.Display(trihedron, False)
        if solid is not None:
            display.DisplayShape(solid, update=False)  # default material shades nicely
        for wires in sketches:
            display.DisplayShape(wires, color=SKETCH_COLOR, update=False)
        if fit:
            display.FitAll()
        display.Repaint()

    def _show_planes(self, size: float) -> None:
        for name, color in PLANE_COLORS.items():
            face = BRepBuilderAPI_MakeFace(gp_Pln(plane_axes(name)), 0, size, 0, size).Face()
            self._display.DisplayShape(
                face, color=rgb_color(*color), transparency=0.85, update=False
            )
            label = AIS_TextLabel()
            label.SetText(name)
            label.SetPosition(gp_Pnt(size, size, 0).Transformed(plane_trsf(name)))
            label.SetColor(rgb_color(*color))
            label.SetHeight(16)
            self._display.Context.Display(label, False)

    def set_view(self, name: str) -> None:
        """Standard view: "front", "top", "right", "iso" or "fit"."""
        display = self._display
        {
            "front": display.View_Front,
            "top": display.View_Top,
            "right": display.View_Right,
            "iso": display.View_Iso,
            "fit": lambda: None,
        }[name]()
        display.FitAll()


def _model_size(solid: TopoDS_Shape | None) -> float:
    """A size for the planes and axes that suits the model (at least 30 mm)."""
    if solid is None:
        return 30.0
    box = Bnd_Box()
    brepbndlib.Add(solid, box)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return max(30.0, 0.7 * max(x1, y1, z1, -x0, -y0, -z0))
