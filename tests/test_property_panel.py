"""Headless tests for docked solid-feature editing and history."""

import copy
import os
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QToolButton, QWidget

from sillycad.core.document import Document
from sillycad.core.features import Hole, Pad, Pocket, Revolve, SketchFeature
from sillycad.core.geometry import volume
from sillycad.core.sketch import Sketch
from sillycad.core.threads import ThreadSpec
from sillycad.gui.hole_panel import HolePanel
from sillycad.gui.main_window import MainWindow
from sillycad.gui.property_panel import FeaturePanel
from sillycad.gui.thread_editor import ThreadEditor


@pytest.fixture(scope="module")
def app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class FakeViewer(QWidget):
    sig_topods_selected = Signal(list)
    marking_menu_requested = Signal(QPoint)
    plane_pick_cancelled = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.shape = None
        self.fits: list[bool] = []

    def show_model(self, shape: object, *args: object, **kwargs: object) -> None:
        self.shape = shape
        self.fits.append(bool(kwargs.get("fit", args[2] if len(args) > 2 else False)))

    def set_navigation_mode(self, mode: str) -> None:
        pass

    def set_plane_pick(self, active: bool) -> None:
        pass

    def plane_name(self, shape: object) -> None:
        return None


@pytest.fixture
def window(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    monkeypatch.setattr("sillycad.gui.main_window.Viewer", FakeViewer)
    window = MainWindow()
    window.recompute()
    yield window
    window._cancel_feature_panel()
    window.undo_stack.setClean()
    window.close()


def rectangle(x0: float, y0: float, x1: float, y1: float) -> Sketch:
    sketch = Sketch()
    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for index, point in enumerate(points):
        sketch.add_line(*point, *points[(index + 1) % 4])
    return sketch


def test_preview_cancel_and_visibility_do_not_change_document(window: MainWindow) -> None:
    sketch = SketchFeature("f1", "Sketch1", sketch=rectangle(0, 0, 40, 20))
    window._set_document(Document([sketch], next_id=2), None)
    before = copy.deepcopy(window.doc)
    window.actions["extrude"].trigger()
    panel = window._feature_panel
    assert panel is not None
    assert panel.feature.id == "f2"
    assert panel.feature.name == "Extrusion1"
    assert all(
        "<b>" in button.toolTip() and "Shortcut:" in button.toolTip()
        for button in (panel.join, panel.cut, panel.ok, panel.cancel, panel.apply)
    )
    file_button = window.ribbon.findChild(QToolButton, "fileButton")
    export_menu = next(action.menu() for action in file_button.menu().actions() if action.menu())
    assert not export_menu.actions()[0].isEnabled()
    assert window.model_dock.windowTitle() == "Extrusion1"
    assert window.model.shape is None
    assert volume(window.viewer.shape) == pytest.approx(8000)
    assert window.viewer.fits[-1]
    panel.length.setValue(20)
    assert volume(window.viewer.shape) == pytest.approx(16000)
    assert not window.viewer.fits[-1]
    window.actions["planes"].trigger()
    assert volume(window.viewer.shape) == pytest.approx(16000)
    panel.cancel.click()
    assert window.doc == before
    assert window.viewer.shape is None
    assert window.undo_stack.count() == 0
    assert window.model_dock.windowTitle() == "Model"
    assert window.actions["new_sketch"].isEnabled()
    assert export_menu.actions()[0].isEnabled()
    window.add_solid(Pad)
    assert window.actions["undo"].isEnabled()
    window._picked([])
    assert "Property Panel" in window.statusBar().currentMessage()
    window.actions["undo"].trigger()
    assert window._feature_panel is None
    assert window.doc == before


def test_feature_ids_are_reserved_only_on_commit_and_not_reused_after_undo(
    window: MainWindow,
) -> None:
    sketch = SketchFeature("f1", "Sketch1", sketch=rectangle(0, 0, 40, 20))
    window._set_document(Document([sketch], next_id=2), None)

    window.add_solid(Pad)
    assert window._feature_panel is not None
    window._feature_panel.cancel.click()
    assert window.doc.next_id == 2

    window.add_solid(Pad)
    assert window._feature_panel is not None
    window._feature_panel.ok.click()
    assert window.doc.find("f2") is not None
    assert window.doc.next_id == 3

    window.undo_stack.undo()
    assert window.doc.find("f2") is None
    assert window.doc.next_id == 3
    window.add_solid(Pad)
    assert window._feature_panel is not None
    assert window._feature_panel.feature.id == "f3"
    window._feature_panel.ok.click()
    assert window.doc.find("f3") is not None


def test_join_cut_options_preview_and_edit_lock(window: MainWindow) -> None:
    base = SketchFeature("f1", "Sketch1", sketch=rectangle(0, 0, 40, 20))
    hole = SketchFeature("f3", "Sketch2", "XY", 10, rectangle(5, 5, 15, 10))
    window._set_document(Document([base, Pad("f2", "Extrusion1", base.id), hole], next_id=4), None)
    window.add_solid(Pad)
    panel = window._feature_panel
    assert panel is not None
    assert panel.feature.sketch_id == hole.id
    panel.cut.click()
    panel.length.setValue(5)
    assert isinstance(panel.feature, Pocket)
    assert volume(window.viewer.shape) == pytest.approx(7750)
    panel.extent.setCurrentIndex(panel.extent.findData("through_all"))
    assert panel.feature.through_all
    assert not panel.length.isEnabled()
    assert volume(window.viewer.shape) == pytest.approx(7500)
    panel.direction.setCurrentIndex(panel.direction.findData("flipped"))
    assert panel.feature.reversed
    panel.direction.setCurrentIndex(panel.direction.findData("default"))
    panel.ok.click()
    pocket = window.doc.features[-1]
    assert isinstance(pocket, Pocket)
    assert pocket.through_all and not pocket.reversed
    assert volume(window.model.shape) == pytest.approx(7500)

    window.edit_feature(pocket.id)
    panel = window._feature_panel
    assert panel is not None and panel.editing
    assert panel.cut.isEnabled() and not panel.join.isEnabled()
    assert panel.extent.currentData() == "through_all"
    panel.extent.setCurrentIndex(panel.extent.findData("distance"))
    panel.length.setValue(5)
    panel.apply.click()
    assert isinstance(window.doc.find(pocket.id), Pocket)
    assert not window.doc.find(pocket.id).through_all
    assert panel is window._feature_panel
    panel.length.setValue(3)
    panel.cancel.click()
    assert window.doc.find(pocket.id).length == 5
    window.actions["undo"].trigger()
    assert window.doc.find(pocket.id).through_all


def test_hole_preview_edit_clearance_thread_and_history(window: MainWindow) -> None:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    centers = Sketch()
    point = centers.add_point(10, 10)
    centers.add_point(20, 10)
    placement = SketchFeature("f3", "Centers", "XY", 10, centers)
    window._set_document(Document([base, Pad("f2", "Block", "f1"), placement], next_id=4), None)
    window.actions["hole"].trigger()
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    assert panel.feature.sketch_id == "f3"
    panel.point.setCurrentIndex(panel.point.findData(point))
    panel.clearance.setCurrentIndex(panel.clearance.findData("M6"))
    assert panel.diameter.value() == pytest.approx(6.6)
    assert not panel.diameter.isEnabled()
    assert volume(window.viewer.shape) == pytest.approx(8000 - 3.141592653589793 * 3.3**2 * 5)
    panel.thread.setChecked(True)
    assert "clearance" in panel.message.text()
    panel.clearance.setCurrentIndex(0)
    panel.diameter.setValue(5)
    panel.thread.thread_class.setText("6H")
    panel.thread.left_hand.setChecked(True)
    assert not panel.message.text()
    panel.ok.click()
    hole = window.doc.find("f4")
    assert isinstance(hole, Hole)
    assert hole.thread.designation == "M6 x 1"
    assert hole.thread.thread_class == "6H" and hole.thread.left_hand
    window.undo_stack.undo()
    assert window.doc.find("f4") is None
    window.undo_stack.redo()
    window.edit_feature("f4")
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    assert panel.thread.isChecked()
    assert panel.thread.thread_class.text() == "6H"
    panel.style.setCurrentIndex(panel.style.findData("counterbore"))
    panel.apply.click()
    assert window.doc.find("f4").style == "counterbore"
    panel.cancel.click()
    assert window.doc.find("f4").style == "counterbore"


def test_existing_circle_cut_cosmetic_thread_panel(window: MainWindow) -> None:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    circle = Sketch()
    circle.add_circle(10, 10, 2.5)
    profile = SketchFeature("f3", "Circle", "XY", 10, circle)
    cut = Pocket("f4", "Cut", "f3", length=5)
    window._set_document(Document([base, Pad("f2", "Block", "f1"), profile, cut], next_id=5), None)
    window.edit_feature("f4")
    panel = window._feature_panel
    assert isinstance(panel, FeaturePanel)
    panel.thread.setChecked(True)
    panel.thread.thread_class.setText("6H")
    assert not panel.message.text()
    panel.ok.click()
    saved = window.doc.find("f4")
    assert isinstance(saved, Pocket)
    assert saved.thread.designation == "M6 x 1"
    assert saved.thread.thread_class == "6H"
    assert volume(window.model.shape) == pytest.approx(8000 - 3.141592653589793 * 2.5**2 * 5)


def test_tapered_thread_requires_explicit_depth_in_hole_panel(window: MainWindow) -> None:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    centers = Sketch()
    point = centers.add_point(10, 10)
    window._set_document(
        Document(
            [base, Pad("f2", "Block", "f1"), SketchFeature("f3", "Centers", "XY", 10, centers)],
            next_id=4,
        ),
        None,
    )
    window.actions["hole"].trigger()
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    panel.point.setCurrentIndex(panel.point.findData(point))
    panel.thread.setChecked(True)
    panel.thread.family.setCurrentText("NPT")
    panel.thread.designation.setCurrentText("1/8-27 NPT")
    assert "explicit thread depth" in panel.message.text()
    panel.diameter.setValue(8)
    panel.thread.full_depth.setChecked(False)
    panel.thread.depth.setValue(4)
    assert not panel.message.text()
    panel.ok.click()
    hole = window.doc.find("f4")
    assert isinstance(hole, Hole)
    assert hole.thread.family == "NPT" and hole.thread.depth == 4
    assert not window.model.errors


def test_custom_thread_editor_preserves_precision(app: QApplication) -> None:
    spec = ThreadSpec(
        "Custom",
        "Special",
        depth=4,
        custom_major=10.12345,
        custom_pitch=0.3175,
        custom_taper=0.0625,
    )
    editor = ThreadEditor(spec)
    assert editor.value() == spec


def test_apply_creates_distinct_features_and_undo_cancels_active_panel(
    window: MainWindow,
) -> None:
    base = SketchFeature("f1", "Sketch1", sketch=rectangle(0, 0, 40, 20))
    hole = SketchFeature("f2", "Sketch2", "XY", 10, rectangle(5, 5, 15, 10))
    window._set_document(Document([base, hole], next_id=3), None)
    window.add_solid(Pad)
    panel = window._feature_panel
    assert panel is not None
    panel.sketch.setCurrentIndex(panel.sketch.findData(base.id))
    panel.apply.click()
    assert panel is window._feature_panel
    assert window.doc.features[-1].id == "f3"
    assert panel.feature.id == "f4"
    assert panel.feature.name == "Extrusion2"
    panel.sketch.setCurrentIndex(panel.sketch.findData(hole.id))
    panel.cut.click()
    panel.extent.setCurrentIndex(panel.extent.findData("through_all"))
    panel.apply.click()
    assert window.doc.features[-1].id == "f4"
    assert isinstance(window.doc.features[-1], Pocket)
    assert volume(window.model.shape) == pytest.approx(7500)
    assert panel.feature.id == "f5"
    assert window.actions["undo"].text() == "Undo"
    window.actions["undo"].trigger()
    assert window._feature_panel is None
    assert len(window.doc.features) == 4
    assert window.actions["undo"].text().startswith("Undo Add ")
    window.actions["undo"].trigger()
    assert len(window.doc.features) == 3
    window.actions["redo"].trigger()
    assert len(window.doc.features) == 4


def test_revolve_axis_extent_and_missing_reference(app: QApplication) -> None:
    sketch = rectangle(2, 0, 5, 10)
    axis = sketch.add_line(-2, 0, -2, 5, construction=True)
    source = SketchFeature("f1", "Sketch1", sketch=sketch)
    previews = []
    panel = FeaturePanel(
        Revolve("f2", "Revolution1", source.id, axis=axis, angle=180),
        [source],
        lambda feature: previews.append(feature) or None,
    )
    assert panel.axis.currentData() == axis
    assert panel.extent.currentData() == "angle"
    assert panel.angle.value() == 180
    panel.extent.setCurrentIndex(panel.extent.findData("full"))
    assert panel.feature.angle == 360
    assert not panel.angle.isEnabled()
    panel.extent.setCurrentIndex(panel.extent.findData("angle"))
    assert panel.feature.angle == 180
    assert previews[-1].axis == axis
    panel.deleteLater()

    invalid = FeaturePanel(
        Revolve("f3", "Revolution2", source.id, axis="missing"),
        [source],
        lambda feature: f"Invalid axis: {feature.axis}",
        editing=True,
    )
    assert invalid.feature.axis == "missing"
    assert "missing" in invalid.message.text()
    invalid.axis.setCurrentIndex(invalid.axis.findData("x_axis"))
    assert invalid.feature.axis == "x_axis"
    invalid.deleteLater()

    missing_sketch = FeaturePanel(
        Pad("f4", "Extrusion2", "missing"),
        [source],
        lambda feature: f"Invalid sketch: {feature.sketch_id}",
        editing=True,
    )
    assert missing_sketch.feature.sketch_id == "missing"
    assert "missing" in missing_sketch.message.text()
    missing_sketch.sketch.setCurrentIndex(missing_sketch.sketch.findData(source.id))
    assert missing_sketch.feature.sketch_id == source.id
    missing_sketch.deleteLater()


def test_symmetric_join_and_invalid_feature_feedback(window: MainWindow) -> None:
    sketch = SketchFeature("f1", "Sketch1", sketch=rectangle(0, 0, 40, 20))
    window._set_document(Document([sketch], next_id=2), None)
    window.add_solid(Pad)
    panel = window._feature_panel
    assert panel is not None
    panel.direction.setCurrentIndex(panel.direction.findData("flipped"))
    panel.direction.setCurrentIndex(panel.direction.findData("symmetric"))
    assert panel.feature.symmetric and panel.feature.reversed
    panel.cut.click()
    assert isinstance(panel.feature, Pocket)
    assert panel.direction.findData("symmetric") == -1
    assert "first solid" in panel.message.text()
    panel.ok.click()
    assert window.model.errors
    assert "failed" in window.statusBar().currentMessage()
    assert isinstance(window.doc.features[-1], Pocket)


def test_edit_preserves_symmetric_reversed_and_history_order(window: MainWindow) -> None:
    sketch = SketchFeature("f1", "Sketch1", sketch=rectangle(0, 0, 40, 20))
    pad = Pad("f2", "Extrusion1", sketch.id, reversed=True, symmetric=True)
    later = SketchFeature("f3", "Sketch2", sketch=rectangle(1, 1, 5, 5))
    window._set_document(Document([sketch, pad, later], next_id=4), None)
    window.edit_feature(pad.id)
    panel = window._feature_panel
    assert panel is not None
    assert panel.sketch.findData(later.id) == -1
    assert panel.feature == pad
    panel.ok.click()
    assert window.doc.find(pad.id) == pad
    assert window.undo_stack.count() == 0


def test_unique_closed_profile_and_external_undo(window: MainWindow) -> None:
    closed = SketchFeature("f1", "Closed", sketch=rectangle(0, 0, 40, 20))
    open_sketch = Sketch()
    open_sketch.add_line(0, 0, 1, 1)
    incomplete = SketchFeature("f2", "Open", sketch=open_sketch)
    window._set_document(Document([closed, incomplete], next_id=3), None)
    window.change("Rename", lambda doc: setattr(doc.find("f2"), "name", "Renamed"))
    window.add_solid(Pad)
    panel = window._feature_panel
    assert panel is not None and panel.feature.sketch_id == closed.id
    window.undo_stack.undo()
    assert window._feature_panel is None
    assert window.doc.find("f2").name == "Open"
    assert window.viewer.shape is None
    window.tree.select("f2")
    window.add_solid(Pad)
    assert window._feature_panel.feature.sketch_id == "f2"
    assert window._feature_panel.message.text()
    window.actions["redo"].trigger()
    assert window._feature_panel is None
    assert window.doc.find("f2").name == "Renamed"


def test_close_cancel_keeps_active_panel(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    sketch = SketchFeature("f1", "Sketch1", sketch=rectangle(0, 0, 40, 20))
    window._set_document(Document([sketch], next_id=2), None)
    window.add_solid(Pad)
    panel = window._feature_panel
    monkeypatch.setattr(window, "maybe_save", lambda: False)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert window._feature_panel is panel
