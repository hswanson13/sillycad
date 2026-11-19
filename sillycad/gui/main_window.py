"""Main window and app startup."""

import logging
import os
import sys

from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from sillycad.core.export import export_stl
from sillycad.core.geometry import make_box
from sillycad.gui.viewer import Viewer

log = logging.getLogger(__name__)

# Very important: the whole UI is in Comic Sans (with fallbacks if it's not installed).
UI_FONTS = ["Comic Sans MS", "Comic Neue", "Chalkboard SE"]


class MainWindow(QMainWindow):
    """Top-level window: menus, 3D view, status bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SillyCAD")
        self.viewer = Viewer(self)
        self.setCentralWidget(self.viewer)
        self.shape = make_box(40, 20, 10)  # M1 test box
        self._build_menus()
        self.statusBar().showMessage("Ready")

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        export = file_menu.addAction("Export &STL…")
        export.triggered.connect(self.export_stl)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)

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
    window.viewer.show_shape(window.shape)
    return app.exec()
