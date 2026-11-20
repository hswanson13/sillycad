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
from pathlib import Path

from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopoDS import TopoDS_Face, TopoDS_Shape, topods
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QFont,
    QKeySequence,
    QShortcut,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from sillycad.core import fileio
from sillycad.core.constants import STL_ANGULAR_DEFLECTION, STL_LINEAR_DEFLECTION
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
from sillycad.core.geometry import BASE_PLANES, Placement, outline_in_plane, volume
from sillycad.core.sketch import XY, Sketch
from sillycad.gui import theme
from sillycad.gui.browser import ModelBrowser
from sillycad.gui.commands import SnapshotCommand, redo_shortcuts
from sillycad.gui.dialogs import FeatureDialog, SketchPlaneDialog, StlDialog
from sillycad.gui.icons import icon
from sillycad.gui.marking_menu import MarkingMenu
from sillycad.gui.navigation import NavigationBar
from sillycad.gui.ribbon import Ribbon
from sillycad.gui.sketch_editor import SketchEditor
from sillycad.gui.viewer import Viewer

log = logging.getLogger(__name__)

# Very important: the whole UI is in Comic Sans (with fallbacks if it's not installed).
UI_FONTS = ["Comic Sans MS", "Comic Neue", "Chalkboard SE"]


class MainWindow(QMainWindow):
    """Feature tree on the left, 3D view in the middle."""

    def __init__(self) -> None:
        super().__init__()
        self.doc = Document()
        self.model = Model(None, {})
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(lambda _clean: self._update_title())
        self.path: Path | None = None  # where the document is saved
        self.stl_settings = (STL_LINEAR_DEFLECTION, STL_ANGULAR_DEFLECTION)
        self.picked_face: TopoDS_Face | None = None  # clicked in the 3D view, to sketch on
        self.picked_plane: str | None = None
        self._picking_plane = False

        self.viewer = Viewer(self)
        self.viewer.sig_topods_selected.connect(self._picked)
        self.viewer.marking_menu_requested.connect(self._show_marking_menu)
        self.viewer.plane_pick_cancelled.connect(self.cancel_plane_pick)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        viewport_layout = QHBoxLayout()
        viewport_layout.setContentsMargins(0, 0, 0, 0)
        viewport_layout.setSpacing(0)
        viewport_layout.addWidget(self.viewer, 1)
        center_layout.addLayout(viewport_layout, 1)
        self.document_tabs = QTabBar()
        self.document_tabs.setObjectName("documentTabs")
        self.document_tabs.setExpanding(False)
        self.document_tabs.addTab("Untitled")
        center_layout.addWidget(self.document_tabs)
        self.setCentralWidget(center)

        self.tree = ModelBrowser()
        self.tree.edit_requested.connect(self.edit_feature)
        self.tree.rename_requested.connect(self.rename_feature)
        self.tree.delete_requested.connect(self.delete_feature)
        self.tree.plane_requested.connect(self.change_plane)
        self.tree.plane_selected.connect(self._select_plane)
        self.tree.start_sketch_requested.connect(self._start_sketch_on_plane)
        self.tree.offset_sketch_requested.connect(self._start_offset_sketch_on_plane)
        self.tree.planes_visibility_requested.connect(self._toggle_planes)
        dock = QDockWidget("Model", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setWidget(self.tree)
        dock.setMinimumWidth(260)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.volume_status = QLabel()
        self.statusBar().addPermanentWidget(self.volume_status)
        self._build_actions()
        self.navigation = NavigationBar(self.actions, self)
        viewport_layout.addWidget(self.navigation)
        self._cancel_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._cancel_shortcut.activated.connect(self.cancel_plane_pick)
        self._update_title()

    # ── Actions and ribbon ──────────────────────────────────────────

    def _action(
        self,
        text: str,
        slot: Callable[[], object],
        icon_name: str,
        key: str = "",
        tip: str = "",
    ) -> QAction:
        action = QAction(icon(icon_name), text, self)
        if key:
            action.setShortcut(QKeySequence(key))
        shortcut = f"<br>Shortcut: {key}" if key else ""
        action.setToolTip(f"<b>{text}</b><br>{tip or text}.{shortcut}")

        def invoke() -> None:
            self.cancel_plane_pick()
            slot()

        action.triggered.connect(invoke)
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        actions = {
            "new": self._action("New", self.new_document, "new", "Ctrl+N", "Start a new part"),
            "open": self._action("Open…", self.open_document, "open", "Ctrl+O", "Open a part"),
            "save": self._action("Save", self.save, "save", "Ctrl+S", "Save the part"),
            "save_as": self._action(
                "Save As…", self.save_as, "save", "Ctrl+Shift+S", "Save under a new name"
            ),
            "export": self._action(
                "Export STL…", self.export_stl, "export", "Ctrl+E", "Export the body as STL"
            ),
            "quit": self._action("Quit", self.close, "document", "Ctrl+Q", "Close SillyCAD"),
            "new_sketch": self._action(
                "Start 2D Sketch", self.new_sketch, "sketch", "N", "Draw a sketch on a plane"
            ),
            "sketch_offset": self._action(
                "Sketch with Offset…",
                self.new_sketch_with_offset,
                "sketch",
                tip="Choose a sketch plane and offset",
            ),
            "extrude": self._action(
                "Extrude",
                lambda: self.ribbon.show_extrude_menu(),
                "pad",
                "E",
                "Choose whether to join or cut",
            ),
            "pad": self._action(
                "Join (Pad)…", lambda: self.add_solid(Pad), "pad", "P", "Add a sketch to the body"
            ),
            "pocket": self._action(
                "Cut (Pocket)…",
                lambda: self.add_solid(Pocket),
                "pocket",
                "O",
                "Cut a sketch out of the body",
            ),
            "revolve": self._action(
                "Revolve",
                lambda: self.add_solid(Revolve),
                "revolve",
                "R",
                "Spin a sketch around an axis",
            ),
            "fit": self._action(
                "Zoom All", lambda: self.viewer.set_view("fit"), "fit", "F", "Fit the model"
            ),
            "front": self._action(
                "Front",
                lambda: self.viewer.set_view("front"),
                "front",
                "1",
                "View the model from the front",
            ),
            "top": self._action(
                "Top", lambda: self.viewer.set_view("top"), "top", "2", "View the model from above"
            ),
            "right": self._action(
                "Right",
                lambda: self.viewer.set_view("right"),
                "right",
                "3",
                "View the model from the right",
            ),
            "iso": self._action(
                "Home",
                lambda: self.viewer.set_view("iso"),
                "iso",
                "0",
                "Show an isometric view and fit the model",
            ),
            "look_at": self._action(
                "Look At", self.look_at, "look_at", tip="Look straight at the selected plane"
            ),
            "orbit": self._action(
                "Orbit",
                lambda: self.viewer.set_navigation_mode("orbit"),
                "orbit",
                tip="Orbit by dragging with the left mouse button",
            ),
            "pan": self._action(
                "Pan",
                lambda: self.viewer.set_navigation_mode("pan"),
                "pan",
                tip="Pan by dragging with the left mouse button",
            ),
            "zoom": self._action(
                "Zoom",
                lambda: self.viewer.set_navigation_mode("zoom"),
                "zoom",
                tip="Zoom by dragging with the left mouse button",
            ),
            "shaded": self._action(
                "Shaded",
                lambda: self.viewer.set_mode("shaded"),
                "shaded",
                "S",
                "Display shaded surfaces",
            ),
            "wireframe": self._action(
                "Wireframe",
                lambda: self.viewer.set_mode("wireframe"),
                "wireframe",
                "W",
                "Display the model as edges",
            ),
            "sketches": self._action(
                "Sketches", self.update_view, "sketches", tip="Show or hide sketch wires"
            ),
            "planes": self._action(
                "Planes and Origin", self.update_view, "planes", tip="Show or hide work features"
            ),
        }
        actions["fit"].setShortcuts([QKeySequence("F"), QKeySequence("Home")])
        actions["iso"].setShortcuts([QKeySequence("0"), QKeySequence("F6")])
        actions["fit"].setToolTip("<b>Zoom All</b><br>Fit the model.<br>Shortcuts: F, Home")
        actions["iso"].setToolTip(
            "<b>Home</b><br>Show an isometric view and fit the model.<br>Shortcuts: 0, F6"
        )
        self._navigation_group = QActionGroup(self)
        for key in ("orbit", "pan", "zoom"):
            actions[key].setCheckable(True)
            self._navigation_group.addAction(actions[key])
        actions["orbit"].setChecked(True)
        undo = self.undo_stack.createUndoAction(self, "Undo")
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        undo.setIcon(icon("undo"))
        undo.setToolTip("<b>Undo</b><br>Undo the last change.<br>Shortcut: Ctrl+Z")
        redo = self.undo_stack.createRedoAction(self, "Redo")
        redo.setShortcuts(redo_shortcuts())
        redo.setIcon(icon("redo"))
        redo.setToolTip("<b>Redo</b><br>Redo the last undone change.<br>Shortcut: Ctrl+Shift+Z")
        undo.triggered.connect(self.cancel_plane_pick)
        redo.triggered.connect(self.cancel_plane_pick)
        self.addAction(undo)
        self.addAction(redo)
        actions.update(undo=undo, redo=redo)
        self.show_sketches = actions["sketches"]
        self.show_planes = actions["planes"]
        for toggle in (self.show_sketches, self.show_planes):
            toggle.setCheckable(True)
            toggle.setChecked(True)
        self.show_planes.toggled.connect(self.tree.set_planes_visible)
        self.actions = actions
        self.ribbon = Ribbon(actions, self)
        self.setMenuWidget(self.ribbon)

    def _toggle_planes(self) -> None:
        self.show_planes.trigger()

    def _select_plane(self, plane: str | None) -> None:
        self.picked_plane = plane
        if plane is not None:
            self.picked_face = None
            if self._picking_plane:
                self._start_sketch(plane, 0.0, None)
            else:
                self.statusBar().showMessage(f"{plane} plane picked. Click Start 2D Sketch.")

    def _start_sketch_on_plane(self, plane: str) -> None:
        waiting = self._picking_plane
        self._select_plane(plane)
        if not waiting:
            self.new_sketch()

    def _start_offset_sketch_on_plane(self, plane: str) -> None:
        self.cancel_plane_pick()
        self._select_plane(plane)
        self.new_sketch_with_offset()

    def _show_marking_menu(self, pos: QPoint) -> None:
        MarkingMenu(self.actions, self).exec(pos)

    def cancel_plane_pick(self) -> None:
        """Cancel command-first sketch plane selection."""
        if self._picking_plane:
            self._picking_plane = False
            self.viewer.set_plane_pick(False)
            self.statusBar().showMessage("Ready")

    def look_at(self) -> None:
        """Look directly at the selected plane, flat face or sketch."""
        selected = self._picked_plane()
        if selected is not None:
            name, offset, face = selected
            placement = face if name == "Face" else BASE_PLANES[name]
        else:
            if self.picked_face is not None:
                return
            sketch = self.doc.find(self.tree.current_id() or "")
            if not isinstance(sketch, SketchFeature):
                self.statusBar().showMessage("Select a plane, planar face or sketch for Look At.")
                return
            placement, offset = sketch.placement(), sketch.offset
        if placement is not None:
            self.viewer.look_at(placement, offset)
            self.statusBar().showMessage("Looking at the selected plane.")

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
        self.volume_status.setText(
            f"Body volume: {volume(self.model.shape):,.1f} mm³"
            if self.model.shape is not None
            else ""
        )
        if self.model.errors:
            fid, message = next(iter(self.model.errors.items()))
            self.statusBar().showMessage(f"⚠ {self.doc.find(fid).name} failed: {message}")
        else:
            self.statusBar().showMessage("Ready")

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
        if self.tree.current_plane() != self.picked_plane:
            self.picked_plane = None

    def _picked(self, shapes: list[TopoDS_Shape]) -> None:
        plane = next(
            (name for shape in shapes if (name := self.viewer.plane_name(shape)) is not None),
            None,
        )
        if plane is not None:
            self._select_plane(plane)
            return
        faces = [topods.Face(s) for s in shapes if s.ShapeType() == TopAbs_FACE]
        self.picked_face = faces[0] if faces else None
        self.picked_plane = None
        if self.picked_face is not None:
            selection = self._picked_plane()
            if selection is not None and self._picking_plane:
                self._start_sketch(*selection)
            elif selection is not None:
                self.statusBar().showMessage("Face picked. Click Start 2D Sketch (N).")
        elif self._picking_plane:
            self.statusBar().showMessage("Select a plane or planar face (Esc to cancel).")

    def _picked_plane(self) -> tuple[str, float, Placement | None] | None:
        """Return the selected base plane or the plane of a picked flat face."""
        if self.picked_plane is not None:
            return self.picked_plane, 0.0, None
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
        """Start immediately on the selected plane, or ask the user to pick one."""
        selection = self._picked_plane()
        if selection is not None:
            self._start_sketch(*selection)
            return
        self.actions["orbit"].trigger()
        self._picking_plane = True
        self.viewer.set_plane_pick(True)
        self.statusBar().showMessage("Select a plane or planar face (Esc to cancel).")

    def new_sketch_with_offset(self) -> None:
        """Open the explicit plane and offset chooser."""
        self.cancel_plane_pick()
        plane, offset, face = self._picked_plane() or ("XY", 0.0, None)
        dialog = SketchPlaneDialog(self, plane, offset, has_face=face is not None)
        if not dialog.exec():
            return
        plane, offset = dialog.values()
        self._start_sketch(plane, offset, face)

    def _start_sketch(self, plane: str, offset: float, face: Placement | None) -> None:
        self.cancel_plane_pick()
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
        name = "Revolution" if kind is Revolve else "Extrusion"
        feature = kind(self.doc.new_id(), self.doc.new_name(name), sketch.id)
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

    # ── Files ───────────────────────────────────────────────────────

    def _update_title(self) -> None:
        name = self.path.name if self.path else "Untitled"
        unsaved = "" if self.undo_stack.isClean() else " *"
        self.setWindowTitle(f"{name}{unsaved} — SillyCAD")
        self.document_tabs.setTabText(0, f"{name}{unsaved}")
        self.tree.set_document_name(f"{name}{unsaved}")

    def _set_document(self, doc: Document, path: Path | None) -> None:
        self.cancel_plane_pick()
        self.doc, self.path = doc, path
        self.picked_face = None
        self.picked_plane = None
        self.tree.setCurrentItem(None)
        self.undo_stack.clear()
        self.model = Model(None, {})
        self.recompute(fit=True)
        self._update_title()

    def maybe_save(self) -> bool:
        """Offer to save unsaved changes. Returns False if the user cancels."""
        if self.undo_stack.isClean():
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self, "Unsaved changes",
            f"Save changes to {self.path.name if self.path else 'this part'}?",
            buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save,
        )  # fmt: skip
        if answer == buttons.Save:
            return self.save()
        return answer == buttons.Discard

    def new_document(self) -> None:
        if self.maybe_save():
            self._set_document(Document(), None)

    def open_document(self) -> None:
        if not self.maybe_save():
            return
        folder = str(self.path.parent if self.path else Path.cwd())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", folder, f"SillyCAD (*{fileio.SUFFIX});;All files (*)"
        )
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        try:
            doc = fileio.load(path)
        except ValueError as exc:
            QMessageBox.critical(self, "Can't open file", f"{path.name}: {exc}")
            return
        self._set_document(doc, path)

    def save(self) -> bool:
        """Save to the current file (asks for a name the first time). True if saved."""
        return self._write(self.path) if self.path else self.save_as()

    def save_as(self) -> bool:
        start = str(self.path or Path.cwd() / f"part{fileio.SUFFIX}")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save As", start, f"SillyCAD (*{fileio.SUFFIX})"
        )
        if not path:
            return False
        path = Path(path)
        if path.suffix != fileio.SUFFIX:
            path = path.with_name(path.name + fileio.SUFFIX)
        return self._write(path)

    def _write(self, path: Path) -> bool:
        try:
            fileio.save(self.doc, path)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Couldn't save {path.name}: {exc}")
            return False
        self.path = path
        self.undo_stack.setClean()
        self._update_title()
        self.statusBar().showMessage(f"Saved {path}")
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.maybe_save():
            event.ignore()
            return
        self.undo_stack.cleanChanged.disconnect()  # no title updates while Qt tears down
        event.accept()

    def export_stl(self) -> None:
        """Ask for quality settings and a file name, then export the body as binary STL."""
        if self.model.shape is None:
            QMessageBox.information(self, "Export STL", "There's no solid to export yet.")
            return
        dialog = StlDialog(self, *self.stl_settings)
        if not dialog.exec():
            return
        self.stl_settings = dialog.values()
        start = str(self.path.with_suffix(".stl") if self.path else Path.cwd() / "part.stl")
        path, _ = QFileDialog.getSaveFileName(self, "Export STL", start, "STL (*.stl)")
        if not path:
            return
        if not path.lower().endswith(".stl"):
            path += ".stl"
        try:
            count = export_stl(self.model.shape, path, *self.stl_settings)
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
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    window.resize(1300, 850)
    window.show()
    window.viewer.init()
    window.recompute(fit=True)
    if len(sys.argv) > 1:  # python -m sillycad part.sillycad
        window.open_path(Path(sys.argv[1]))
    return app.exec()
