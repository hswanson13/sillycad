"""Main window and app startup."""

import logging
import os
import sys

from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from sillycad.core.export import export_stl
from sillycad.core.features import SketchFeature
from sillycad.core.geometry import make_box
from sillycad.core.sketch import Sketch
from sillycad.gui.dialogs import SketchPlaneDialog
from sillycad.gui.sketch_editor import SketchEditor
from sillycad.gui.viewer import Viewer

log = logging.getLogger(__name__)

# Very important: the whole UI is in Comic Sans (with fallbacks if it's not installed).
UI_FONTS = ["Comic Sans MS", "Comic Neue", "Chalkboard SE"]


class MainWindow(QMainWindow):
    """Top-level window: menus, toolbar, 3D view, status bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SillyCAD")
        self.viewer = Viewer(self)
        self.setCentralWidget(self.viewer)
        self.shape = make_box(40, 20, 10)  # test box until solids arrive in M4
        self.sketches: list[SketchFeature] = []
        self._build_menus()
        self.statusBar().showMessage("Ready. Click New Sketch to start drawing.")

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        export = file_menu.addAction("Export &STL…")
        export.triggered.connect(self.export_stl)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)

        bar = self.addToolBar("Main")
        bar.setMovable(False)
        new_sketch = bar.addAction("New Sketch")
        new_sketch.setToolTip("Draw a 2D sketch on a base plane")
        new_sketch.triggered.connect(self.new_sketch)
        self.show_sketches = bar.addAction("Show Sketches")
        self.show_sketches.setCheckable(True)
        self.show_sketches.setChecked(True)
        self.show_sketches.toggled.connect(lambda _on: self.update_view())

    def update_view(self, fit: bool = False) -> None:
        """Redraw the 3D view from the current model."""
        wires = []
        if self.show_sketches.isChecked():
            for feature in self.sketches:
                try:
                    wires.append(feature.wires())
                except Exception:  # an OCCT failure in one sketch shouldn't hide the rest
                    log.exception("Could not draw %s", feature.name)
        see_through = 0.7 if wires else None  # M3 only: so sketches aren't hidden in the test box
        self.viewer.show(self.shape, wires, fit, see_through)

    def new_sketch(self) -> None:
        """Ask for a plane, then open the sketch editor."""
        dialog = SketchPlaneDialog(self)
        if not dialog.exec():
            return
        plane, offset = dialog.values()
        name = f"Sketch{len(self.sketches) + 1}"
        editor = SketchEditor(Sketch(), name, self)
        editor.finished.connect(
            lambda sketch: self._add_sketch(
                SketchFeature(name.lower(), name, plane, offset, sketch)
            )
        )
        editor.show()

    def _add_sketch(self, feature: SketchFeature) -> None:
        self.sketches.append(feature)
        self.update_view()
        self.statusBar().showMessage(f"Added {feature.name} on {feature.plane}.")

    def export_stl(self) -> None:
        """Ask for a file name and export the current shape as binary STL."""
        path, _ = QFileDialog.getSaveFileName(self, "Export STL", "model.stl", "STL (*.stl)")
        if not path:
            return
        if not path.lower().endswith(".stl"):
            path += ".stl"
        try:
            count = export_stl(self.shape, path)
        except Exception as exc:  # OCCT errors surface here
            log.exception("STL export failed")
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage(f"Exported {count} triangles to {path}")


def run() -> int:
    """Start the app and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # OCCT draws into an X11 window; on Wayland this makes Qt use XWayland.
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    app = QApplication(sys.argv)
    font = QFont()
    font.setFamilies(UI_FONTS)
    font.setStyleHint(QFont.StyleHint.Cursive)
    app.setFont(font)

    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    window.viewer.init()
    window.update_view(fit=True)
    return app.exec()
