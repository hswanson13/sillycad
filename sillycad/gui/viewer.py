"""3D viewport built on pythonocc's Qt viewer widget.

Mouse: left-drag orbits, middle-drag pans, right-drag or wheel zooms.
"""

from OCC.Display.backend import load_backend

load_backend("pyside6")  # must run before importing qtDisplay

from OCC.Core.TopoDS import TopoDS_Shape  # noqa: E402
from OCC.Display.qtDisplay import qtViewer3d  # noqa: E402


class Viewer(qtViewer3d):
    """The 3D view. Call ``init()`` once, after the window is shown."""

    def init(self) -> None:
        """Create the OCCT viewer. Needs a real native window, so call after show()."""
        self.InitDriver()

    def show_shape(self, shape: TopoDS_Shape) -> None:
        """Replace whatever is on screen with ``shape`` and fit it in view."""
        self._display.EraseAll()
        self._display.DisplayShape(shape, update=False)
        self._display.FitAll()
