"""Headless tests for the ribbon, browser and document state."""

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCC.Core.GeomAbs import GeomAbs_Cylinder
from OCC.Core.StdSelect import StdSelect_BRepOwner
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QApplication, QMenu, QToolButton, QWidget

from sillycad.core.document import Document
from sillycad.core.features import Pad, Pocket, SketchFeature
from sillycad.core.geometry import BASE_PLANES, Placement
from sillycad.core.sketch import Sketch
from sillycad.gui.browser import ModelBrowser
from sillycad.gui.main_window import MainWindow
from sillycad.gui.marking_menu import MarkingMenu
from sillycad.gui.sketch_session import SketchSession
from sillycad.gui.viewer import Viewer


@pytest.fixture(scope="session")
def app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class FakeViewer(QWidget):
    """Keep shell tests independent of an OpenGL window."""

    sig_topods_selected = Signal(list)
    marking_menu_requested = Signal(QPoint)
    plane_pick_cancelled = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.planes = True
        self.mode = ""
        self.view = ""
        self.navigation_mode = "orbit"
        self.picking_plane = False
        self.looked_at: tuple[Placement, float] | None = None

    def show_model(
        self, solid: object, sketches: list[object], planes: bool, fit: bool, **kwargs: object
    ) -> None:
        self.planes = planes

    def set_view(self, name: str) -> None:
        self.view = name

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def set_navigation_mode(self, mode: str) -> None:
        self.navigation_mode = mode

    def set_plane_pick(self, active: bool) -> None:
        self.picking_plane = active

    def plane_name(self, shape: object) -> str | None:
        return None

    def look_at(self, placement: Placement, offset: float = 0.0) -> None:
        self.looked_at = placement, offset


@pytest.fixture
def window(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    monkeypatch.setattr("sillycad.gui.main_window.Viewer", FakeViewer)
    window = MainWindow()
    window.recompute()
    yield window
    window.close()


def test_browser_nests_shared_sketches_and_preserves_selection(app: QApplication) -> None:
    shared = SketchFeature("s1", "Sketch1")
    loose = SketchFeature("s2", "Sketch2")
    doc = Document(
        [
            shared,
            Pad("p1", "Extrusion1", shared.id),
            Pocket("p2", "Extrusion2", shared.id),
            loose,
        ]
    )
    browser = ModelBrowser()
    browser.fill(doc, {"p2": "Cut failed"})
    root = browser.topLevelItem(0)
    assert [root.child(i).text(0) for i in range(root.childCount())] == [
        "Origin",
        "Extrusion1",
        "Extrusion2",
        "Sketch2",
    ]
    assert root.child(1).child(0).text(0) == "Sketch1"
    assert root.child(2).child(0).text(0) == "Sketch1"
    assert root.child(2).toolTip(0) == "Cut failed"
    assert not root.child(2).icon(0).isNull()

    browser.setCurrentItem(root.child(2).child(0))
    root.child(0).setExpanded(False)
    browser.fill(doc, {})
    assert browser.current_id() == shared.id
    assert browser.currentItem().parent().text(0) == "Extrusion2"
    assert not browser.topLevelItem(0).child(0).isExpanded()

    deleted = []
    browser.delete_requested.connect(deleted.append)
    browser.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.NoModifier))
    assert deleted == [shared.id]


def test_browser_sketch_context_menu_redefines_plane(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = ModelBrowser()
    sketch = SketchFeature("s1", "Sketch1")
    browser.fill(Document([sketch]), {})
    item = browser.topLevelItem(0).child(1)
    monkeypatch.setattr(browser, "itemAt", lambda pos: item)
    selected = []
    browser.plane_requested.connect(selected.append)

    labels = {}

    def choose() -> None:
        menu = next(
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, QMenu) and widget.isVisible()
        )
        actions = {action.text(): action for action in menu.actions()}
        labels.update({name: action.toolTip() for name, action in actions.items() if name})
        action = actions.get("Redefine (Change plane)…")
        if action is not None:
            action.trigger()
        menu.close()

    QTimer.singleShot(0, choose)
    browser._menu(QPoint())
    assert {"Edit Sketch", "Redefine (Change plane)…", "Rename", "Delete"} <= labels.keys()
    assert all("<b>" in text for text in labels.values())
    assert selected == [sketch.id]


def test_origin_plane_selection_and_visibility(window: MainWindow) -> None:
    viewer = window.viewer
    assert isinstance(viewer, FakeViewer)
    origin = window.tree.topLevelItem(0).child(0)
    assert [origin.child(i).text(0) for i in range(origin.childCount())] == [
        "XY Plane",
        "XZ Plane",
        "YZ Plane",
        "X Axis",
        "Y Axis",
        "Z Axis",
        "Center Point",
    ]
    plane = origin.child(1)
    window.tree.setCurrentItem(plane)
    window.tree.itemClicked.emit(plane, 0)
    assert window._picked_plane() == ("XZ", 0.0, None)
    assert window.tree.current_id() is None

    window.tree.planes_visibility_requested.emit()
    assert not window.show_planes.isChecked()
    assert not viewer.planes
    assert "Show Origin" in window.tree._origin_eye.toolTip()
    window.show_planes.trigger()
    assert window.show_planes.isChecked()
    assert viewer.planes
    assert "Hide Origin" in window.tree._origin_eye.toolTip()
    assert window._picked_plane() == ("XZ", 0.0, None)
    window._set_document(Document(), None)
    assert window._picked_plane() is None
    assert window.tree.currentItem() is None


def test_ribbon_actions_and_view_shortcuts(window: MainWindow) -> None:
    viewer = window.viewer
    assert isinstance(viewer, FakeViewer)
    assert [window.ribbon.tabs.tabText(i) for i in range(window.ribbon.tabs.count())] == [
        "3D Model",
        "View",
    ]
    assert {"new", "open", "save", "save_as", "export", "quit"} <= window.actions.keys()
    assert {"new_sketch", "extrude", "pad", "pocket", "revolve"} <= window.actions.keys()
    assert window.actions["extrude"].shortcut() == QKeySequence("E")
    assert window.actions["export"].shortcut() == QKeySequence("Ctrl+E")
    assert QKeySequence("Home") in window.actions["fit"].shortcuts()
    assert QKeySequence("F6") in window.actions["iso"].shortcuts()
    assert QKeySequence("Ctrl+Shift+Z") in window.actions["redo"].shortcuts()
    assert QKeySequence("Ctrl+Y") in window.actions["redo"].shortcuts()
    assert all(
        "<b>" in action.toolTip() and "Shortcut:" in action.toolTip()
        for action in window.actions.values()
    )
    assert window.ribbon.extrude_button.menu() is None
    file_button = window.ribbon.findChild(QToolButton, "fileButton")
    assert file_button is not None
    file_menu = file_button.menu()
    assert file_menu is not None
    export_menu = next(
        menu for action in file_menu.actions() if (menu := action.menu()) is not None
    )
    exported = []
    window.actions["export"].triggered.disconnect()
    window.actions["export"].triggered.connect(lambda: exported.append(True))
    export_menu.actions()[0].trigger()
    assert exported == [True]
    window.actions["wireframe"].trigger()
    assert viewer.mode == "wireframe"
    window.actions["shaded"].trigger()
    assert viewer.mode == "shaded"
    window.actions["iso"].trigger()
    assert viewer.view == "iso"


def test_document_tab_tracks_save_undo_and_redo(window: MainWindow, tmp_path: Path) -> None:
    window.change("Add sketch", lambda doc: doc.features.append(SketchFeature("s1", "Sketch1")))
    assert window.document_tabs.tabText(0) == "Untitled *"
    assert window.tree.topLevelItem(0).text(0) == "Untitled *"
    assert window._write(tmp_path / "part.sillycad")
    assert window.document_tabs.tabText(0) == "part.sillycad"

    window.rename_feature("s1", "Outline")
    assert window.document_tabs.tabText(0) == "part.sillycad *"
    window.undo_stack.undo()
    assert window.document_tabs.tabText(0) == "part.sillycad"
    assert window.doc.find("s1").name == "Sketch1"
    window.undo_stack.redo()
    assert window.document_tabs.tabText(0) == "part.sillycad *"
    window.undo_stack.undo()


def test_sketch_editor_retains_both_redo_shortcuts(window: MainWindow) -> None:
    editor = SketchSession(Sketch())
    window.undo_group.addStack(editor.undo_stack)
    window.undo_group.setActiveStack(editor.undo_stack)

    def add_point(sketch: Sketch) -> None:
        sketch.add_point(1, 2)

    editor.edit("Add point", add_point)
    editor.undo_stack.undo()
    redo = window.actions["redo"]
    assert QKeySequence("Ctrl+Shift+Z") in redo.shortcuts()
    assert QKeySequence("Ctrl+Y") in redo.shortcuts()
    redo.trigger()
    assert len(editor.sketch.geo) == 1
    window.undo_group.setActiveStack(window.undo_stack)
    window.undo_group.removeStack(editor.undo_stack)


def test_command_first_sketch_plane_and_cancel(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer = window.viewer
    assert isinstance(viewer, FakeViewer)
    started: list[tuple[str, float, Placement | None]] = []

    def start(plane: str, offset: float, face: Placement | None) -> None:
        started.append((plane, offset, face))
        window.cancel_plane_pick()

    monkeypatch.setattr(window, "_start_sketch", start)
    window.actions["pan"].trigger()
    assert viewer.navigation_mode == "pan"
    window.new_sketch()
    assert viewer.picking_plane
    assert viewer.navigation_mode == "orbit"
    assert "Select a plane or planar face" in window.statusBar().currentMessage()
    window.viewer.plane_pick_cancelled.emit()
    assert not viewer.picking_plane
    assert started == []

    window.new_sketch()
    window.actions["pan"].trigger()
    assert not viewer.picking_plane
    assert viewer.navigation_mode == "pan"

    window.new_sketch()
    origin = window.tree.topLevelItem(0).child(0)
    plane = origin.child(1)
    window.tree.itemClicked.emit(plane, 0)
    assert started == [("XZ", 0.0, None)]
    assert not viewer.picking_plane


def test_pick_first_and_look_at_selected_sketch(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer = window.viewer
    assert isinstance(viewer, FakeViewer)
    started: list[tuple[str, float, Placement | None]] = []

    def start(plane: str, offset: float, face: Placement | None) -> None:
        started.append((plane, offset, face))

    monkeypatch.setattr(window, "_start_sketch", start)
    window._select_plane("YZ")
    window.new_sketch()
    assert started == [("YZ", 0.0, None)]
    window.look_at()
    assert viewer.looked_at == (BASE_PLANES["YZ"], 0.0)

    sketch = SketchFeature("s1", "Sketch1", "XZ", 7.0)
    window._set_document(Document([sketch]), None)
    window.tree.select(sketch.id)
    window.look_at()
    assert viewer.looked_at == (BASE_PLANES["XZ"], 7.0)


def test_curved_face_is_rejected_while_waiting_for_a_plane(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    explorer = TopExp_Explorer(BRepPrimAPI_MakeCylinder(5, 10).Shape(), TopAbs_FACE)
    while explorer.More():
        face = topods.Face(explorer.Current())
        if BRepAdaptor_Surface(face).GetType() == GeomAbs_Cylinder:
            break
        explorer.Next()
    else:
        pytest.fail("The cylinder did not contain a curved face")
    started = []
    monkeypatch.setattr(window, "_start_sketch", lambda *args: started.append(args))
    window.new_sketch()
    window._picked([face])
    assert not started
    assert window._picking_plane
    assert "isn't flat" in window.statusBar().currentMessage()
    window.cancel_plane_pick()


def test_offset_sketch_uses_explicit_dialog(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[tuple[str, float, Placement | None]] = []

    class PlaneDialog:
        def __init__(
            self, parent: QWidget, plane: str, offset: float, has_face: bool = False
        ) -> None:
            assert (plane, offset, has_face) == ("XZ", 0.0, False)

        def exec(self) -> bool:
            return True

        def values(self) -> tuple[str, float]:
            return "XZ", 12.5

    def start(plane: str, offset: float, face: Placement | None) -> None:
        started.append((plane, offset, face))

    monkeypatch.setattr("sillycad.gui.main_window.SketchPlaneDialog", PlaneDialog)
    monkeypatch.setattr(window, "_start_sketch", start)
    window._select_plane("XZ")
    window.new_sketch_with_offset()
    assert started == [("XZ", 12.5, None)]


def test_marking_menu_actions_use_the_shared_commands(window: MainWindow) -> None:
    menu = MarkingMenu(window.actions, window)
    buttons = {button.text(): button for button in menu.findChildren(QToolButton)}
    assert set(buttons) == {
        "Start 2D Sketch",
        "Extrude",
        "Revolve",
        "Zoom All",
        "Home",
        "Look At",
        "Undo",
        "Planes and Origin",
    }
    buttons["Planes and Origin"].click()
    assert not window.show_planes.isChecked()
    assert not window.viewer.planes
    menu.close()


def test_viewport_plane_pick_is_cleared_after_redraw(window: MainWindow) -> None:
    window._select_plane("XY")
    assert window._picked_plane() == ("XY", 0.0, None)
    window.update_view()
    assert window._picked_plane() is None


def test_face_owner_is_not_downcast_to_a_view_cube(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer = Viewer()
    display = Mock()
    display.Context.HasDetected.return_value = True
    display.Context.DetectedOwner.return_value = StdSelect_BRepOwner(1)
    display.selected_shapes = []
    monkeypatch.setattr(viewer, "_display", display)
    viewer._press_at = QPointF(20, 30)
    selected = []
    viewer.sig_topods_selected.connect(selected.append)
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(20, 30),
        QPointF(20, 30),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    viewer.mouseReleaseEvent(event)
    display.Select.assert_called_once_with(20, 30)
    assert selected == [[]]


def test_right_click_cancels_plane_pick_without_opening_marking_menu(app: QApplication) -> None:
    viewer = Viewer()
    cancelled, menus = [], []
    viewer.plane_pick_cancelled.connect(lambda: cancelled.append(True))
    viewer.marking_menu_requested.connect(menus.append)
    viewer.set_plane_pick(True)
    viewer._press_at = QPointF(20, 30)
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(20, 30),
        QPointF(20, 30),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    viewer.mouseReleaseEvent(event)
    assert cancelled == [True]
    assert not menus
