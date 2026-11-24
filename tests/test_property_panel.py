"""Headless tests for docked solid-feature editing and history."""

import copy
import os
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Signal
from PySide6.QtGui import QCloseEvent, QShortcut
from PySide6.QtWidgets import QApplication, QToolButton, QWidget

from sillycad.core.document import Document
from sillycad.core.features import Hole, Pad, Pocket, Revolve, SketchFeature
from sillycad.core.geometry import Placement, volume
from sillycad.core.profiles import ProfileError
from sillycad.core.sketch import Circle, Sketch
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
        self.threads: list[object] = []

    def show_model(self, shape: object, *args: object, **kwargs: object) -> None:
        self.shape = shape
        self.fits.append(bool(kwargs.get("fit", args[2] if len(args) > 2 else False)))
        self.threads = kwargs.get("threads", [])

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


def block_with_centers() -> tuple[Document, str]:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    centers = Sketch()
    point = centers.add_point(10, 10)
    centers.add_point(20, 10)
    placement = SketchFeature("f3", "Centers", "XY", 10, centers)
    return Document([base, Pad("f2", "Block", "f1"), placement], next_id=4), point


def open_hole_panel(window: MainWindow) -> HolePanel:
    """Start the Hole command on the block's center sketch point."""
    doc, point = block_with_centers()
    window._set_document(doc, None)
    window.actions["hole"].trigger()
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    panel.sketch.setCurrentIndex(panel.sketch.findData("f3"))
    panel.point.setCurrentIndex(panel.point.findData(point))
    return panel


def test_hole_types_show_only_their_own_settings(window: MainWindow) -> None:
    panel = open_hole_panel(window)
    assert panel.types.value() == "simple" and panel.seat.value() == "simple"
    assert panel.size_group.isVisibleTo(panel) and not panel.thread_group.isVisibleTo(panel)
    assert not panel.fastener.isVisibleTo(panel) and not panel.seat_group.isVisibleTo(panel)
    panel.seat.buttons["countersink"].click()
    assert panel.seat_group.isVisibleTo(panel)
    assert not panel.seat_form.isRowVisible(panel.head_depth)
    assert panel.seat_form.isRowVisible(panel.angle)
    panel.seat.buttons["simple"].click()
    panel.types.buttons["clearance"].click()
    assert panel.fastener.isVisibleTo(panel) and not panel.size_group.isVisibleTo(panel)
    assert panel.clearance.currentData() == "M6"  # the 6 mm hole's fastener
    assert panel.diameter.value() == pytest.approx(6.6)
    assert volume(window.viewer.shape) == pytest.approx(8000 - 3.141592653589793 * 3.3**2 * 5)
    panel.types.buttons["tapped"].click()
    assert panel.thread_group.isVisibleTo(panel) and not panel.size_group.isVisibleTo(panel)
    assert panel.thread.designation.currentText() == "M6 x 1"
    assert panel.diameter.value() == pytest.approx(5)
    assert "Tap drill Ø5 mm" in panel.thread.info.text()
    assert not panel.message.text()
    assert len(window.viewer.threads) == 1
    panel.types.buttons["simple"].click()
    assert window.viewer.threads == []
    assert panel._current_feature().thread is None


def test_hole_preview_edit_thread_and_history(window: MainWindow) -> None:
    panel = open_hole_panel(window)
    panel.types.buttons["tapped"].click()
    panel.thread.thread_class.setCurrentText("6H")
    panel.thread.hand.setCurrentIndex(1)
    assert not panel.message.text()
    panel.ok.click()
    hole = window.doc.find("f4")
    assert isinstance(hole, Hole)
    assert hole.thread.designation == "M6 x 1" and hole.diameter == pytest.approx(5)
    assert hole.thread.thread_class == "6H" and hole.thread.left_hand
    assert not hole.clearance_size
    window.undo_stack.undo()
    assert window.doc.find("f4") is None
    assert window.viewer.threads == []
    window.undo_stack.redo()
    assert len(window.viewer.threads) == 1
    window.edit_feature("f4")
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    assert panel.types.value() == "tapped"
    assert panel.thread.thread_class.currentText() == "6H"
    assert panel.thread.hand.currentText() == "Left hand"
    panel.seat.buttons["counterbore"].click()
    panel.apply.click()
    assert window.doc.find("f4").style == "counterbore"
    panel.cancel.click()
    assert window.doc.find("f4").style == "counterbore"


def test_taper_tapped_hole_offers_pipe_threads_and_suggests_an_entrance(
    window: MainWindow,
) -> None:
    panel = open_hole_panel(window)
    panel.seat.buttons["counterbore"].click()
    panel.types.buttons["taper"].click()
    assert panel.seat.value() == "simple"
    assert not panel.seat.buttons["counterbore"].isEnabled()
    kinds = [panel.thread.kind.itemText(i) for i in range(panel.thread.kind.count())]
    assert kinds == ["NPT Pipe", "BSP Pipe", "Custom"]
    assert not panel.thread.form.isRowVisible(panel.thread.full_depth)
    assert panel.thread.form.isRowVisible(panel.thread.depth)
    panel.thread.size.setCurrentText("1/8")
    assert panel.thread.designation.currentText() == "1/8-27 NPT"
    assert panel.diameter.isEnabled()
    assert panel.diameter.value() == pytest.approx(8.61)
    panel.thread.depth.setValue(4)
    assert not panel.message.text()
    panel.diameter.setValue(8.5)  # the suggestion can be overridden
    panel.ok.click()
    hole = window.doc.find("f4")
    assert isinstance(hole, Hole)
    assert hole.thread.family == "NPT" and hole.thread.depth == 4
    assert hole.diameter == pytest.approx(8.5)
    assert not window.model.errors
    window.edit_feature("f4")
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    assert panel.types.value() == "taper"
    assert panel.diameter.value() == pytest.approx(8.5)  # a saved entrance is kept
    panel.cancel.click()


def test_tapped_hole_lists_only_parallel_threads(window: MainWindow) -> None:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    hole = Hole(
        "f3",
        "Hole",
        "",
        diameter=6,
        through_all=True,
        style="countersink",
        head_diameter=10,
        face=Placement((0, 0, 10), (0, 0, 1), (1, 0, 0)),
        center=(10, 10),
        thread=ThreadSpec("ISO metric", "M6 x 1"),
    )
    window._set_document(Document([base, Pad("f2", "Block", "f1"), hole], 4), None)
    window.edit_feature("f3")
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    kinds = [panel.thread.kind.itemText(i) for i in range(panel.thread.kind.count())]
    assert "NPT Pipe" not in kinds and "BSP Pipe" in kinds
    panel.thread.kind.setCurrentText("BSP Pipe")
    designations = [
        panel.thread.designation.itemText(i) for i in range(panel.thread.designation.count())
    ]
    assert all(text.startswith("G ") for text in designations)
    panel.cancel.click()
    assert window.doc.find("f3") == hole
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
    editor = ThreadEditor(spec, tapered=True)
    assert editor.value() == spec
    assert editor.form.isRowVisible(editor.major) and not editor.form.isRowVisible(editor.size)


def test_face_hole_can_be_repositioned_and_undo_redone(window: MainWindow) -> None:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    window._set_document(Document([base, Pad("f2", "Block", "f1")], 3), None)
    window.actions["hole"].trigger()
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    assert panel.feature.sketch_id == ""
    assert not panel.ok.isEnabled()
    assert "Click a planar face" in panel.message.text()
    face = Placement((0, 0, 10), (0, 0, 1), (1, 0, 0))
    panel.set_position(face, (10, 10))
    assert panel.ok.isEnabled() and not panel.message.text()
    panel.set_position(face, (20, 10))
    assert panel.feature.center == (20, 10)
    panel.ok.click()
    assert window.doc.find("f3").center == (20, 10)
    assert window.doc.find("f3").face == face
    window.edit_feature("f3")
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    panel.set_position(face, (30, 10))
    panel.ok.click()
    assert window.doc.find("f3").center == (30, 10)
    window.undo_stack.undo()
    assert window.doc.find("f3").center == (20, 10)
    window.undo_stack.redo()
    assert window.doc.find("f3").center == (30, 10)


def test_hole_sketch_point_and_free_position_are_distinct(window: MainWindow) -> None:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    centers = Sketch()
    point = centers.add_point(10, 10)
    top = SketchFeature("f3", "Top", "XY", 10, centers)
    window._set_document(Document([base, Pad("f2", "Block", "f1"), top], 4), None)
    window.actions["hole"].trigger()
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    panel.sketch.setCurrentIndex(panel.sketch.findData("f3"))
    assert not panel.ok.isEnabled() and not panel.apply.isEnabled()
    panel.findChild(QShortcut).activated.emit()
    assert window._feature_panel is panel and window.doc.find("f4") is None
    panel.set_position(None, (10, 10), point)
    assert panel.feature.point_id == point and panel.feature.center is None
    panel.set_position(None, (20, 10))
    assert panel.feature.point_id == "" and panel.feature.center == (20, 10)
    panel.ok.click()
    assert not window.model.errors
    window.doc.find("f3").sketch.geo[point].x = 15
    assert window.doc.find("f4").center == (20, 10)


def test_hole_apply_updates_placement_body(window: MainWindow) -> None:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    window._set_document(Document([base, Pad("f2", "Block", "f1")], 3), None)
    window.actions["hole"].trigger()
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    panel.set_position(Placement((0, 0, 10), (0, 0, 1), (1, 0, 0)), (10, 10))
    panel.apply.click()
    assert window._hole_placement.body.IsSame(window.model.shape)
    assert window.doc.find("f3") is not None
    panel.cancel.click()
    assert window.doc.find("f3") is not None


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
    assert panel.message.objectName() == "errorLabel"
    assert not panel.profile_notice.text()
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
    assert not window._feature_panel.profile_notice.text()
    window.actions["redo"].trigger()
    assert window._feature_panel is None
    assert window.doc.find("f2").name == "Renamed"


def test_extrude_defaults_to_new_circle_with_open_guide_and_warns(window: MainWindow) -> None:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    sketch = Sketch()
    line = sketch.add_line(20, 0, 20, 10)
    circle = sketch.add_circle(20, 5, 100)
    curve = sketch.geo[circle]
    assert isinstance(curve, Circle)
    center = curve.center
    sketch.add_constraint("midpoint", [center, line])
    sketch.add_constraint("radius", [circle], 100)
    face_sketch = SketchFeature("f3", "Circle", "XZ", 0, sketch)
    window._set_document(Document([base, Pad("f2", "Block", "f1"), face_sketch], 4), None)

    window.add_solid(Pad)
    panel = window._feature_panel
    assert isinstance(panel, FeaturePanel)
    assert panel.feature.sketch_id == "f3"
    assert not panel.message.text()
    assert panel.ok.isEnabled()
    assert panel.profile_notice.objectName() == "hintLabel"
    assert "open" in panel.profile_notice.text().lower()
    assert "click ok" in panel.profile_notice.text().lower()
    assert volume(window.viewer.shape) == pytest.approx(8000 + 100000 * 3.141592653589793)
    panel.cut.click()
    panel.thread_group.setChecked(True)
    assert panel.thread.kind.currentText() == "Custom"
    assert "No standard thread fits" in panel.thread.info.text()
    assert "custom thread designation" in panel.message.text()
    assert not panel.profile_notice.text()
    panel.thread_group.setChecked(False)
    assert not panel.message.text() and panel.profile_notice.text()
    panel.join.click()
    panel.sketch.setCurrentIndex(panel.sketch.findData("f1"))
    assert not panel.message.text() and not panel.profile_notice.text()
    panel.sketch.setCurrentIndex(panel.sketch.findData("f3"))
    assert "click ok" in panel.profile_notice.text().lower()
    panel.ok.click()
    assert not window.model.errors
    assert window.doc.find("f3").sketch == sketch
    window.undo_stack.undo()
    assert window.doc.find("f3").sketch == sketch
    window.undo_stack.redo()
    assert not window.model.errors


def test_profile_analysis_failure_remains_an_error(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    sketch = rectangle(0, 0, 40, 20)
    sketch.add_line(5, 5, 10, 5)
    window._set_document(Document([SketchFeature("f1", "Sketch", sketch=sketch)], 2), None)
    window.add_solid(Pad)
    panel = window._feature_panel
    assert isinstance(panel, FeaturePanel) and panel.profile_notice.text()

    def fail_analysis(_sketch: Sketch) -> None:
        raise ProfileError("Profile analysis failed")

    with monkeypatch.context() as patch:
        patch.setattr("sillycad.gui.property_panel.analyze_profiles", fail_analysis)
        panel._profile_warnings.clear()
        panel.length.setValue(11)
        assert "profile analysis failed" in panel.message.text().lower()
        assert not panel.profile_notice.text()

    panel.length.setValue(12)
    assert not panel.message.text()
    assert "click ok" in panel.profile_notice.text().lower()


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


def circle_cut_document(*radii: float, thread: ThreadSpec | None = None) -> Document:
    base = SketchFeature("f1", "Base", sketch=rectangle(0, 0, 40, 20))
    features: list = [base, Pad("f2", "Block", "f1")]
    for index, radius in enumerate(radii):
        sketch = Sketch()
        sketch.add_circle(10, 10, radius)
        features.append(SketchFeature(f"f{3 + index}", f"Circle{index}", "XY", 10, sketch))
    cut_id = f"f{3 + len(radii)}"
    features.append(Pocket(cut_id, "Cut", "f3", through_all=True, thread=thread))
    return Document(features, 4 + len(radii))


def test_cut_thread_lists_only_sizes_that_fit_its_circle(window: MainWindow) -> None:
    window._set_document(circle_cut_document(2, 4.25), None)
    window.edit_feature("f5")
    panel = window._feature_panel
    assert isinstance(panel, FeaturePanel)
    assert panel.thread_group.title() == "Thread (Ø4 mm hole)"
    panel.thread_group.setChecked(True)
    sizes = [panel.thread.size.itemText(i) for i in range(panel.thread.size.count())]
    assert sizes == ["M4.5", "M5"]
    assert panel.thread.designation.currentText() == "M5 x 0.8"
    assert not panel.message.text()
    assert len(window.viewer.threads) == 1
    panel.thread.kind.setCurrentText("Unified Inch")
    assert panel.thread.designation.currentText() == "#10-24 UNC"
    panel.thread.kind.setCurrentText("ISO Metric")
    panel.sketch.setCurrentIndex(panel.sketch.findData("f4"))
    assert panel.thread_group.title() == "Thread (Ø8.5 mm hole)"
    assert panel.thread.designation.currentText() == "M10 x 1.5"
    panel.ok.click()
    assert window.doc.find("f5").thread.designation == "M10 x 1.5"
    assert volume(window.model.shape) == pytest.approx(8000 - 3.141592653589793 * 4.25**2 * 10)


def test_mismatched_cut_thread_is_corrected_when_edited(window: MainWindow) -> None:
    window._set_document(circle_cut_document(2, thread=ThreadSpec("ISO metric", "M2 x 0.25")), None)
    assert "Try M5 x 0.8" in window.model.errors["f4"]
    window.edit_feature("f4")
    panel = window._feature_panel
    assert isinstance(panel, FeaturePanel)
    assert panel.thread.designation.currentText() == "M5 x 0.8"
    assert "M2 x 0.25 does not fit here" in panel.thread.info.text()
    assert not panel.message.text()
    panel.ok.click()
    assert not window.model.errors


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
    panel.thread_group.setChecked(True)
    assert panel.thread.thread_class.currentText() == "6H"
    assert not panel.message.text()
    panel.ok.click()
    saved = window.doc.find("f4")
    assert isinstance(saved, Pocket)
    assert saved.thread.designation == "M6 x 1"
    assert saved.thread.thread_class == "6H"
    assert volume(window.model.shape) == pytest.approx(8000 - 3.141592653589793 * 2.5**2 * 5)


def test_hole_thread_follows_the_fastener_size(window: MainWindow) -> None:
    panel = open_hole_panel(window)
    panel.diameter.setValue(10)
    panel.types.buttons["tapped"].click()
    assert panel.thread.size.currentText() == "M10"
    assert panel.thread.designation.currentText() == "M10 x 1.5"
    assert panel.diameter.value() == pytest.approx(8.5)
    designations = [
        panel.thread.designation.itemText(i) for i in range(panel.thread.designation.count())
    ]
    assert designations == ["M10 x 1.5", "M10 x 1.25", "M10 x 1", "M10 x 0.75"]
    panel.thread.designation.setCurrentText("M10 x 1.25")
    assert panel.diameter.value() == pytest.approx(8.75)
    panel.thread.kind.setCurrentText("Unified Inch")
    assert panel.thread.designation.currentText() == "3/8-16 UNC"
    panel.thread.kind.setCurrentText("ISO Metric")
    assert panel.thread.designation.currentText() == "M10 x 1.5"
    panel.types.buttons["clearance"].click()
    assert panel.clearance.currentData() == "M10"
    panel.types.buttons["tapped"].click()
    assert panel.thread.designation.currentText() == "M10 x 1.5"
    panel.types.buttons["simple"].click()
    panel.diameter.setValue(12)
    panel.types.buttons["tapped"].click()
    assert panel.thread.designation.currentText() == "M12 x 1.75"
    panel.thread.size.setCurrentText("M8")
    assert panel.thread.designation.currentText() == "M8 x 1.25"
    assert not panel.message.text()
    panel.ok.click()
    hole = window.doc.find("f4")
    assert isinstance(hole, Hole)
    assert hole.diameter == pytest.approx(6.75) and not hole.clearance_size
    assert len(window.viewer.threads) == 1
