"""3D viewport built on pythonocc's Qt viewer widget.

Mouse: left-drag orbits, middle-drag pans, right-drag or wheel zooms.
"""

from OCC.Display.backend import load_backend

load_backend("pyside6")  # must run before importing qtDisplay

from OCC.Core.TopoDS import TopoDS_Shape  # noqa: E402
from OCC.Display.qtDisplay import qtViewer3d  # noqa: E402

SKETCH_COLOR = "BLUE"


class Viewer(qtViewer3d):
    """The 3D view. Call ``init()`` once, after the window is shown."""

    def init(self) -> None:
        """Create the OCCT viewer. Needs a real native window, so call after show()."""
        self.InitDriver()

    def show(
        self,
        solid: TopoDS_Shape | None,
        sketches: list[TopoDS_Shape],
        fit: bool = False,
        transparency: float | None = None,
    ) -> None:
        """Replace what's on screen with the solid and the sketch wires."""
        display = self._display
        display.EraseAll()
        if solid is not None:
            display.DisplayShape(solid, transparency=transparency, update=False)
        for wires in sketches:
            display.DisplayShape(wires, color=SKETCH_COLOR, update=False)
        if fit:
            display.FitAll()
        display.Repaint()
