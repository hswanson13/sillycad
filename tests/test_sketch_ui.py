"""Headless tests for the main-window sketch lifecycle and controls."""

import os
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sillycad.core.features import SketchFeature
from sillycad.core.sketch import Line
from sillycad.gui.main_window import MainWindow
from sillycad.sketch_math import add_rectangle


@pytest.fixture(scope="module")
def app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class FakeViewer(QWidget):
    sig_topods_selected = Signal(list)
    marking_menu_requested = Signal(QPoint)
    plane_pick_cancelled = Signal()
    camera_changed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._display = SimpleNamespace(View=SimpleNamespace(Convert=lambda pixels: pixels / 10))

    def show_model(self, *args: object, **kwargs: object) -> None:
        pass

    def set_navigation_mode(self, mode: str) -> None:
        pass

    def set_plane_pick(self, active: bool) -> None:
        pass

    def animate_look_at(self, *args: object, **kwargs: object) -> None:
        pass

    def stop_camera_animation(self) -> None:
        pass

    def plane_name(self, shape: object) -> None:
        return None


class FakeScene:
    def __init__(
        self, viewer: FakeViewer, session: object, placement: object, offset: float
    ) -> None:
        self.viewer = viewer
        self.session = session
        self.show_constraints = True

    def redraw(self) -> None:
        pass

    def update_grid(self) -> None:
        pass

    def screen(self, anchor: object) -> QPointF:
        return QPointF(20, 20)


class FakeInteraction(QObject):
    coordinates = Signal(float, float)
    edit_dimension = Signal(str)
    marking_menu = Signal(QPoint)
    tool_changed = Signal(str)

    def __init__(self, scene: FakeScene, parent: QObject) -> None:
        super().__init__(parent)
        self.tool = "select"
        self.navigation = ""

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.tool_changed.emit(tool)

    def set_navigation(self, mode: str) -> None:
        self.navigation = mode

    def escape(self) -> None:
        pass

    def close(self) -> None:
        pass


@pytest.fixture
def window(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    monkeypatch.setattr("sillycad.gui.main_window.Viewer", FakeViewer)
    monkeypatch.setattr("sillycad.gui.sketch_mode.SketchScene", FakeScene)
    monkeypatch.setattr("sillycad.gui.sketch_mode.SketchInteraction", FakeInteraction)
    window = MainWindow()
    window.recompute()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_contextual_sketch_finish_and_undo(window: MainWindow) -> None:
    window._start_sketch("XY", 0.0, None)
    mode = window._sketch_mode
    assert mode is not None
    assert window.ribbon.tabs.tabText(window.ribbon.tabs.currentIndex()) == "Sketch"
    assert not mode.actions["constraint_controls"].isChecked()
    assert window.undo_group.activeStack() is mode.session.undo_stack
    assert not window.actions["pad"].isEnabled()
    mode.actions["rectangle"].trigger()
    assert mode.interaction.tool == "rectangle"
    mode.session.edit("Rectangle", lambda sketch: add_rectangle(sketch, (0, 0), (20, 10)))
    assert window.document_tabs.tabText(0) == "Untitled *"
    window.actions["undo"].trigger()
    assert not mode.session.sketch.geo
    window.actions["redo"].trigger()
    assert len(mode.session.sketch.constraints) == 8
    mode.actions["finish"].trigger()
    assert window._sketch_mode is None
    assert isinstance(window.doc.features[0], SketchFeature)
    assert window.undo_group.activeStack() is window.undo_stack
    assert window.ribbon.tabs.count() == 2
    assert window.actions["pad"].isEnabled()
    window.actions["undo"].trigger()
    assert not window.doc.features
    window.actions["redo"].trigger()
    assert len(window.doc.features) == 1


def test_constraint_visibility_and_smart_dimension(window: MainWindow) -> None:
    window._start_sketch("XY", 0.0, None)
    mode = window._sketch_mode
    assert mode is not None
    assert mode.constraints.isHidden()
    mode.constraint_list_toggle.click()
    assert not mode.constraints.isHidden()
    mode.constraint_list_toggle.click()
    assert mode.constraints.isHidden()
    mode.session.edit("Rectangle", lambda sketch: add_rectangle(sketch, (0, 0), (20, 10)))
    line = next(g for g in mode.session.sketch.geo.values() if isinstance(g, Line))
    mode.actions["hide_glyphs"].trigger()
    assert not mode.scene.show_constraints
    mode.actions["show_glyphs"].trigger()
    assert mode.scene.show_constraints
    mode.session.set_selection([line.id])
    mode.actions["smart_dimension"].trigger()
    box = mode._dimension_input
    assert box is not None
    box.setText("25")
    box.returnPressed.emit()
    assert any(
        c.kind == "distance" and c.value == 25 for c in mode.session.sketch.constraints.values()
    )
    mode.actions["finish"].trigger()


def test_sketch_navigation_and_construction_state(window: MainWindow) -> None:
    window.actions["pan"].trigger()
    window._start_sketch("XY", 0.0, None)
    mode = window._sketch_mode
    assert mode is not None
    assert not any(window.actions[key].isChecked() for key in ("pan", "zoom", "orbit"))
    window.actions["zoom"].trigger()
    assert mode.interaction.navigation == "zoom"
    mode.actions["line"].trigger()
    assert not window.actions["zoom"].isChecked()
    mode.interaction.set_tool("select")
    assert mode.actions["select"].isChecked()
    mode.session.edit("Rectangle", lambda sketch: add_rectangle(sketch, (0, 0), (20, 10)))
    line = next(g for g in mode.session.sketch.geo.values() if isinstance(g, Line))
    mode.session.set_selection([line.id])
    mode.actions["construction"].trigger()
    assert mode.actions["construction"].isChecked()
    assert mode.session.sketch.geo[line.id].construction
    mode.session.set_selection([])
    assert not mode.actions["construction"].isChecked()
    mode.actions["finish"].trigger()
    assert window.actions["pan"].isChecked()


def test_redundant_constraint_feedback(window: MainWindow) -> None:
    window._start_sketch("XY", 0.0, None)
    mode = window._sketch_mode
    assert mode is not None
    mode.session.edit("Rectangle", lambda sketch: add_rectangle(sketch, (0, 0), (20, 10)))
    lines = [g for g in mode.session.sketch.geo.values() if isinstance(g, Line)]
    mode.session.edit(
        "Redundant parallel",
        lambda sketch: sketch.add_constraint("parallel", [lines[0].id, lines[2].id]),
    )
    assert mode.session.bad_constraints
    assert window.volume_status.text() == "Over constrained"
    assert any(mode.constraints.item(i).toolTip() for i in range(mode.constraints.count()))
    mode.session.undo_stack.undo()
    assert not mode.session.bad_constraints
    mode.actions["finish"].trigger()


def test_cancel_dirty_sketch_requires_confirmation(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window._start_sketch("XY", 0.0, None)
    mode = window._sketch_mode
    assert mode is not None
    mode.session.edit("Point", lambda sketch: sketch.add_point(1, 2))
    monkeypatch.setattr(window, "confirm_discard_sketch", lambda: False)
    mode.cancel()
    assert window._sketch_mode is mode
    monkeypatch.setattr(window, "confirm_discard_sketch", lambda: True)
    mode.cancel()
    assert window._sketch_mode is None
    assert not window.doc.features
    assert window.document_tabs.tabText(0) == "Untitled"


def test_close_with_dirty_sketch_can_be_cancelled(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window._start_sketch("XY", 0.0, None)
    mode = window._sketch_mode
    assert mode is not None
    mode.session.edit("Point", lambda sketch: sketch.add_point(1, 2))
    monkeypatch.setattr(window, "confirm_discard_sketch", lambda: False)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert window._sketch_mode is mode
    mode.session.undo_stack.setClean()
    mode.cancel()
