"""Headless tests for the ribbon, browser and document state."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QToolButton, QWidget

from sillycad.core.document import Document
from sillycad.core.features import Pad, Pocket, SketchFeature
from sillycad.core.sketch import Sketch
from sillycad.gui.browser import ModelBrowser
from sillycad.gui.main_window import MainWindow
from sillycad.gui.sketch_editor import SketchEditor


@pytest.fixture(scope="session")
def app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class FakeViewer(QWidget):
    """Keep shell tests independent of an OpenGL window."""

    sig_topods_selected = Signal(list)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.planes = True
        self.mode = ""
        self.view = ""

    def show_model(self, solid: object, sketches: list[object], planes: bool, fit: bool) -> None:
        self.planes = planes

    def set_view(self, name: str) -> None:
        self.view = name

    def set_mode(self, mode: str) -> None:
        self.mode = mode


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


def test_sketch_editor_retains_both_redo_shortcuts(app: QApplication) -> None:
    editor = SketchEditor(Sketch(), "Sketch1")

    def add_point(sketch: Sketch) -> None:
        sketch.add_point(1, 2)

    editor.edit("Add point", add_point)
    editor.undo_stack.undo()
    redo = next(
        action
        for action in editor.findChildren(QAction)
        if QKeySequence("Ctrl+Shift+Z") in action.shortcuts()
    )
    assert QKeySequence("Ctrl+Y") in redo.shortcuts()
    redo.trigger()
    assert len(editor.sketch.geo) == 1
    editor.undo_stack.clear()
    editor.close()
