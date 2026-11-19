"""Main window and app startup.

The document is plain data. Every user edit goes through ``change()``, which
snapshots the document for undo and then recomputes the model from scratch.
"""

import copy
import dataclasses
import logging
import os
import sys
from collections.abc import Callable

from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopoDS import TopoDS_Face, TopoDS_Shape, topods
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QKeySequence, QUndoStack
from PySide6.QtWidgets import QApplication, QDockWidget, QFileDialog, QMainWindow, QMessageBox

from sillycad.core.document import Document, Model, recompute
from sillycad.core.export import export_stl
from sillycad.core.features import (
    Pad,
    Pocket,
    Revolve,
    SketchFeature,
    SolidFeature,
    plane_from_face,
)
from sillycad.core.geometry import Placement, outline_in_plane, volume
from sillycad.core.sketch import XY, Sketch
from sillycad.gui.commands import SnapshotCommand
from sillycad.gui.dialogs import FeatureDialog, SketchPlaneDialog
from sillycad.gui.feature_tree import FeatureTree
from sillycad.gui.sketch_editor import SketchEditor
from sillycad.gui.viewer import Viewer

log = logging.getLogger(__name__)

# Very important: the whole UI is in Comic Sans (with fallbacks if it's not installed).
UI_FONTS = ["Comic Sans MS", "Comic Neue", "Chalkboard SE"]


class MainWindow(QMainWindow):
    """Feature tree on the left, 3D view in the middle."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SillyCAD")
        self.doc = Document()
        self.model = Model(None, {})
        self.undo_stack = QUndoStack(self)
        self.picked_face: TopoDS_Face | None = None  # clicked in the 3D view, to sketch on

        self.viewer = Viewer(self)
        self.viewer.sig_topods_selected.connect(self._picked)
        self.setCentralWidget(self.viewer)
        self.tree = FeatureTree()
        self.tree.edit_requested.connect(self.edit_feature)
        self.tree.rename_requested.connect(self.rename_feature)
        self.tree.delete_requested.connect(self.delete_feature)
        self.tree.plane_requested.connect(self.change_plane)
        dock = QDockWidget("Features", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setWidget(self.tree)
        dock.setMinimumWidth(260)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._build_actions()

    # ── Menus and toolbar ───────────────────────────────────────────

    def _action(
        self, text: str, slot: Callable[[], object], key: str = "", tip: str = ""
    ) -> QAction:
        action = QAction(text, self)
        if key:
            action.setShortcut(QKeySequence(key))
        action.setToolTip(f"{tip or text} ({key})" if key else tip or text)
        action.triggered.connect(lambda _checked=False: slot())
        return action

    def _build_actions(self) -> None:
        new_sketch = self._action(
            "New Sketch", self.new_sketch, "N", "Draw a 2D sketch on a base plane"
        )
        pad = self._action("Pad", lambda: self.add_solid(Pad), "P", "Extrude a sketch into a solid")
        pocket = self._action(
            "Pocket", lambda: self.add_solid(Pocket), "O", "Cut a sketch out of the body"
        )
        revolve = self._action(
            "Revolve", lambda: self.add_solid(Revolve), "R", "Spin a sketch around an axis"
        )
        undo = self.undo_stack.createUndoAction(self, "Undo")
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        redo = self.undo_stack.createRedoAction(self, "Redo")
        redo.setShortcuts([QKeySequence(QKeySequence.StandardKey.Redo), QKeySequence("Ctrl+Y")])
        views = [
            self._action("Fit All", lambda: self.viewer.set_view("fit"), "F"),
            self._action("Front", lambda: self.viewer.set_view("front"), "1"),
            self._action("Top", lambda: self.viewer.set_view("top"), "2"),
            self._action("Right", lambda: self.viewer.set_view("right"), "3"),
            self._action("Iso", lambda: self.viewer.set_view("iso"), "0"),
        ]
        self.show_sketches = self._action(
            "Show Sketches", self.update_view, tip="Show sketch wires"
        )
        self.show_planes = self._action("Show Planes", self.update_view, tip="Show base planes")
        for toggle in (self.show_sketches, self.show_planes):
            toggle.setCheckable(True)
            toggle.setChecked(True)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self._action("Export &STL…", self.export_stl))
        file_menu.addSeparator()
        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([undo, redo])
        create_menu = self.menuBar().addMenu("&Create")
        create_menu.addActions([new_sketch, pad, pocket, revolve])
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addActions([*views, self.show_sketches, self.show_planes])

        bar = self.addToolBar("Main")
        bar.setMovable(False)
        bar.addActions([new_sketch, pad, pocket, revolve])
        bar.addSeparator()
        bar.addActions([undo, redo])
        bar.addSeparator()
        bar.addActions(views)
        bar.addSeparator()
        bar.addActions([self.show_sketches, self.show_planes])

    # ── Model ───────────────────────────────────────────────────────

    def change(self, text: str, edit: Callable[[Document], object]) -> None:
        """Apply one undoable edit to the document, then recompute."""
        before = copy.deepcopy(self.doc)
        edit(self.doc)
        self.undo_stack.push(SnapshotCommand(text, before, copy.deepcopy(self.doc), self._restore))
        self.recompute()

    def _restore(self, doc: Document) -> None:
        self.doc = doc
        self.recompute()

    def recompute(self, fit: bool = False) -> None:
        """Rebuild the body from the feature list and refresh the tree and view."""
        first_solid = self.model.shape is None
        self.model = recompute(self.doc)
        self.tree.fill(self.doc, self.model.errors)
        self.update_view(fit=fit or (first_solid and self.model.shape is not None))
        if self.model.errors:
            fid, message = next(iter(self.model.errors.items()))
            self.statusBar().showMessage(f"⚠ {self.doc.find(fid).name} failed: {message}")
        elif self.model.shape is not None:
            self.statusBar().showMessage(f"Body volume: {volume(self.model.shape):,.1f} mm³")
        else:
            self.statusBar().showMessage("Ready. Click New Sketch to start.")

    def update_view(self, fit: bool = False, model: Model | None = None) -> None:
        """Redraw the 3D view (optionally for a preview model)."""
        model = model or self.model
        wires = []
        if self.show_sketches.isChecked():
            for sketch in self.doc.sketches():
                try:
                    wires.append(sketch.wires())
                except Exception:  # one broken sketch shouldn't hide the rest
                    log.exception("Could not draw %s", sketch.name)
        self.viewer.show_model(model.shape, wires, self.show_planes.isChecked(), fit)
        self.picked_face = None  # redrawing clears the 3D selection

    def _picked(self, shapes: list[TopoDS_Shape]) -> None:
        faces = [topods.Face(s) for s in shapes if s.ShapeType() == TopAbs_FACE]
        self.picked_face = faces[0] if faces else None
        if self.picked_face is not None:
            self.statusBar().showMessage("Face picked. Click New Sketch (N) to sketch on it.")

    def _picked_plane(self) -> tuple[str, float, Placement | None] | None:
        """(plane, offset, face plane) of the picked face, if a flat one is picked."""
        if self.picked_face is None:
            return None
        try:
            return plane_from_face(self.picked_face)
        except ValueError as exc:  # curved face
            self.statusBar().showMessage(str(exc))
            return None

    def _outline(self, sketch: SketchFeature) -> list[list[XY]]:
        """Edges of the body (as it is just before this sketch) lying in the sketch's plane."""
        index = next(
            (i for i, f in enumerate(self.doc.features) if f.id == sketch.id),
            len(self.doc.features),
        )
        body = recompute(Document(self.doc.features[:index])).shape
        if body is None:
            return []
        try:
            return outline_in_plane(body, sketch.placement(), sketch.offset)
        except Exception:  # the guide is a nicety; never block sketching over it
            log.exception("Could not find the face outline")
            return []

    def _preview(self, feature: SolidFeature) -> str | None:
        """Show what the document would look like with ``feature``; return its error."""
        trial = copy.deepcopy(self.doc)
        if trial.find(feature.id):
            trial.replace(feature)
        else:
            trial.features.append(feature)
        model = recompute(trial)
        self.update_view(model=model)
        return model.errors.get(feature.id)

    # ── Feature commands ────────────────────────────────────────────

    def new_sketch(self) -> None:
        """Ask for a plane (the picked face is offered first), then open the sketch editor."""
        plane, offset, face = self._picked_plane() or ("XY", 0.0, None)
        dialog = SketchPlaneDialog(self, plane, offset, has_face=face is not None)
        if not dialog.exec():
            return
        plane, offset = dialog.values()
        feature = SketchFeature(
            self.doc.new_id(), self.doc.new_name("Sketch"), plane, offset,
            face=face if plane == "Face" else None,
        )  # fmt: skip
        editor = SketchEditor(Sketch(), feature.name, self, self._outline(feature))
        editor.finished.connect(
            lambda sketch: self.change(
                f"Add {feature.name}",
                lambda d: d.features.append(dataclasses.replace(feature, sketch=sketch)),
            )
        )
        editor.show()

    def add_solid(self, kind: type[SolidFeature]) -> None:
        sketch = self._default_sketch()
        if sketch is None:
            QMessageBox.information(self, kind.__name__, "Draw a sketch first (New Sketch).")
            return
        feature = kind(self.doc.new_id(), self.doc.new_name(kind.__name__), sketch.id)
        dialog = FeatureDialog(feature, self.doc.sketches(), self._preview, self)
        if dialog.exec():
            new = dialog.feature
            self.change(f"Add {new.name}", lambda d: d.features.append(new))
            self.tree.select(new.id)
        else:
            self.update_view()  # drop the preview

    def _default_sketch(self) -> SketchFeature | None:
        """The selected sketch, else the newest sketch nothing uses yet, else the newest."""
        selected = self.doc.find(self.tree.current_id() or "")
        if isinstance(selected, SketchFeature):
            return selected
        sketches = self.doc.sketches()
        unused = [s for s in sketches if not self.doc.users(s.id)]
        return (unused or sketches or [None])[-1]

    def edit_feature(self, fid: str) -> None:
        f = self.doc.find(fid)
        if isinstance(f, SketchFeature):
            editor = SketchEditor(f.sketch, f.name, self, self._outline(f))
            editor.finished.connect(
                lambda sketch: self.change(
                    f"Edit {f.name}", lambda d: setattr(d.find(fid), "sketch", sketch)
                )
            )
            editor.show()
        elif f is not None:
            dialog = FeatureDialog(f, self.doc.sketches(before=fid), self._preview, self)
            if dialog.exec():
                self.change(f"Edit {f.name}", lambda d: d.replace(dialog.feature))
            else:
                self.update_view()

    def rename_feature(self, fid: str, name: str) -> None:
        f = self.doc.find(fid)
        if f is None or not name or name == f.name:
            self.tree.fill(self.doc, self.model.errors)
            return
        if any(other.name == name for other in self.doc.features):
            self.statusBar().showMessage(f"There's already a feature called {name}.")
            self.tree.fill(self.doc, self.model.errors)
            return
        self.change(f"Rename {f.name}", lambda d: setattr(d.find(fid), "name", name))

    def delete_feature(self, fid: str) -> None:
        f = self.doc.find(fid)
        if f is None:
            return
        users = self.doc.users(fid)
        if users:
            names = ", ".join(u.name for u in users)
            answer = QMessageBox.question(
                self, "Delete sketch?", f"{names} {'is' if len(users) == 1 else 'are'} built from "
                f"{f.name} and will be deleted too. Continue?",
            )  # fmt: skip
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.change(f"Delete {f.name}", lambda d: d.delete(fid))

    def change_plane(self, fid: str) -> None:
        f = self.doc.find(fid)
        if not isinstance(f, SketchFeature):
            return
        plane, offset, face = self._picked_plane() or (f.plane, f.offset, f.face)
        dialog = SketchPlaneDialog(self, plane, offset, has_face=face is not None)
        if not dialog.exec():
            return
        plane, offset = dialog.values()

        def move(d: Document) -> None:
            sketch = d.find(fid)
            sketch.plane, sketch.offset = plane, offset
            sketch.face = face if plane == "Face" else None

        self.change(f"Move {f.name}", move)

    def export_stl(self) -> None:
        """Ask for a file name and export the body as binary STL."""
        if self.model.shape is None:
            QMessageBox.information(self, "Export STL", "There's no solid to export yet.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export STL", "model.stl", "STL (*.stl)")
        if not path:
            return
        if not path.lower().endswith(".stl"):
            path += ".stl"
        try:
            count = export_stl(self.model.shape, path)
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
    window.resize(1300, 850)
    window.show()
    window.viewer.init()
    window.recompute(fit=True)
    return app.exec()
