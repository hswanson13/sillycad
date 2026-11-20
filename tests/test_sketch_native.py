"""Opt-in real-window tests for native OCCT sketch interaction."""

import os
from pathlib import Path

import pytest
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from sillycad.core.document import Document
from sillycad.core.features import Pad, SketchFeature
from sillycad.core.geometry import face_placement, volume
from sillycad.core.sketch import Arc, Circle, Line, Point, Sketch
from sillycad.gui.dialogs import FeatureDialog
from sillycad.gui.main_window import MainWindow
from sillycad.sketch_math import add_rectangle

pytestmark = pytest.mark.skipif(
    not os.environ.get("SILLYCAD_NATIVE_GUI_TESTS") or not os.environ.get("DISPLAY"),
    reason="requires an explicitly enabled native display",
)


def test_native_sketch_on_face(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1300, 850)
    window.show()
    window.viewer.init()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window, 2000)
    QTest.qWait(100)
    try:
        base = Sketch()
        corners = [(0, 0), (60, 0), (60, 40), (0, 40)]
        for index, point in enumerate(corners):
            base.add_line(*point, *corners[(index + 1) % 4])
        window._set_document(
            Document([SketchFeature("s1", "Sketch1", sketch=base), Pad("p1", "Pad1", "s1")]),
            None,
        )
        explorer = TopExp_Explorer(window.model.shape, TopAbs_FACE)
        top = None
        while explorer.More():
            face = topods.Face(explorer.Current())
            placement = face_placement(face)
            if placement.normal == (0.0, 0.0, 1.0):
                top = face
                break
            explorer.Next()
        assert top is not None
        window.actions["new_sketch"].trigger()
        assert window._picking_plane
        window._picked([top])
        QTest.qWait(550)
        mode = window._sketch_mode
        assert mode is not None
        assert mode.session.reference
        corner = mode.session.reference[0][0]
        snapped, _ = mode.scene.snap(mode.scene.screen(corner))
        assert snapped == pytest.approx(corner)

        mode.actions["rectangle"].trigger()
        start = mode.scene.screen((10, 10)).toPoint()
        end = mode.scene.screen((45, 30)).toPoint()
        QTest.mousePress(window.viewer, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window.viewer, end, delay=20)
        QTest.mouseRelease(window.viewer, Qt.MouseButton.LeftButton, pos=end)
        assert sum(isinstance(item, Line) for item in mode.session.sketch.geo.values()) == 4
        assert len(mode.session.sketch.constraints) == 8
        assert mode.session.undo_stack.count() == 1
        assert mode.session.profile_text == "1 closed profile"

        line = next(item for item in mode.session.sketch.geo.values() if isinstance(item, Line))
        mode.session.set_selection([line.id])
        mode.actions["smart_dimension"].trigger()
        box = mode._dimension_input
        assert box is not None
        box.setText("35")
        QTest.keyClick(box, Qt.Key.Key_Return)
        dimension = next(
            constraint
            for constraint in mode.session.sketch.constraints.values()
            if constraint.kind == "distance"
        )
        assert dimension.value == 35
        mode.actions["select"].trigger()
        position = mode.scene.screen(mode.scene._anchors[dimension.id]).toPoint()
        QTest.mouseDClick(window.viewer, Qt.MouseButton.LeftButton, pos=position)
        box = mode._dimension_input
        assert box is not None
        box.setText("34")
        QTest.keyClick(box, Qt.Key.Key_Return)
        assert mode.session.sketch.constraints[dimension.id].value == 34

        horizontal = next(
            constraint
            for constraint in mode.session.sketch.constraints.values()
            if constraint.kind == "horizontal"
        )
        glyph = mode.scene.screen(mode.scene._anchors[horizontal.id])
        assert mode.scene.pick(QPointF(glyph)) == horizontal.id
        QTest.mouseClick(window.viewer, Qt.MouseButton.LeftButton, pos=glyph.toPoint())
        assert mode.session.selection == [horizontal.id]
        QTest.keyClick(window.viewer, Qt.Key.Key_Delete)
        assert horizontal.id not in mode.session.sketch.constraints
        QTest.keyClick(window.viewer, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert horizontal.id in mode.session.sketch.constraints
        QTest.keyClick(window.viewer, Qt.Key.Key_F9)
        assert not mode.scene.show_constraints
        QTest.keyClick(window.viewer, Qt.Key.Key_F8)
        assert mode.scene.show_constraints

        center = window.viewer.rect().center()
        original_grid = mode.scene._signatures["grid"]
        wheel = QWheelEvent(
            QPointF(center),
            QPointF(window.viewer.mapToGlobal(center)),
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        app.sendEvent(window.viewer, wheel)
        QTest.qWait(120)
        assert mode.scene._signatures["grid"] != original_grid
        zoomed_grid = mode.scene._signatures["grid"]
        QTest.mousePress(window.viewer, Qt.MouseButton.MiddleButton, pos=center)
        QTest.mouseMove(window.viewer, center + QPoint(40, 25), delay=20)
        QTest.mouseRelease(window.viewer, Qt.MouseButton.MiddleButton, pos=center + QPoint(40, 25))
        QTest.qWait(120)
        assert mode.scene._signatures["grid"] != zoomed_grid
        panned_grid = mode.scene._signatures["grid"]
        QTest.mousePress(window.viewer, Qt.MouseButton.RightButton, pos=center)
        QTest.mouseMove(window.viewer, center + QPoint(35, 40), delay=20)
        QTest.mouseRelease(window.viewer, Qt.MouseButton.RightButton, pos=center + QPoint(35, 40))
        QTest.qWait(120)
        assert mode.scene._signatures["grid"] != panned_grid
        QTest.mousePress(
            window.viewer,
            Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.ShiftModifier,
            center,
        )
        QTest.mouseMove(window.viewer, center + QPoint(30, 20), delay=20)
        QTest.mouseRelease(window.viewer, Qt.MouseButton.MiddleButton, pos=center + QPoint(30, 20))
        QTest.qWait(120)
        QTest.keyClick(window.viewer, Qt.Key.Key_F5)
        QTest.qWait(550)
        normal = mode.feature.placement().normal
        direction = window.viewer._display.View.Camera().Direction()
        assert (direction.X(), direction.Y(), direction.Z()) == pytest.approx(
            tuple(-value for value in normal), abs=1e-6
        )
        aligned_grid = mode.scene._signatures["grid"]
        window.actions["right"].trigger()
        assert mode.scene._signatures["grid"] == aligned_grid
        QTest.keyClick(window.viewer, Qt.Key.Key_F5)
        QTest.qWait(550)
        window.actions["fit"].trigger()
        assert window.viewer._display.View.Convert(window.viewer.width()) < 500

        mode.actions["finish"].trigger()
        assert window._sketch_mode is None
        assert len(window.doc.features) == 3
        window.actions["undo"].trigger()
        assert len(window.doc.features) == 2
        window.actions["redo"].trigger()
        assert len(window.doc.features) == 3

        sketch = window.doc.sketches()[-1]
        feature = Pad(window.doc.new_id(), "Extrusion2", sketch.id)
        dialog = FeatureDialog(feature, window.doc.sketches(), window._preview, window)
        assert not dialog.message.text()
        dialog.length.setValue(5)
        assert not dialog.message.text()
        window.change("Add Extrusion2", lambda doc: doc.features.append(dialog.feature))
        assert not window.model.errors
        expected_volume = volume(window.model.shape)
        path = tmp_path / "part.sillycad"
        assert window._write(path)
        window.open_path(path)
        assert not window.model.errors
        assert volume(window.model.shape) == pytest.approx(expected_volume)
        window.edit_feature(sketch.id)
        QTest.qWait(550)
        reopened = window._sketch_mode
        assert reopened is not None
        assert reopened.session.sketch.constraints[dimension.id].value == 34
        assert reopened.session.change_dimension(dimension.id, 33)
        reopened.actions["finish"].trigger()
        assert window.undo_stack.count() == 1
        window.actions["undo"].trigger()
        assert window.doc.find(sketch.id).sketch.constraints[dimension.id].value == 34
        window.actions["redo"].trigger()
        assert window.doc.find(sketch.id).sketch.constraints[dimension.id].value == 33
        assert window.save()
        stl = tmp_path / "part.stl"
        monkeypatch.setattr(
            "sillycad.gui.main_window.StlDialog.exec", lambda self: QDialog.Accepted
        )
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(stl), ""))
        window.export_stl()
        assert stl.stat().st_size > 84
        assert "triangles" in window.statusBar().currentMessage()
        exercise_drawing_tools(window)
    finally:
        if window._sketch_mode is not None:
            window._sketch_mode.session.undo_stack.setClean()
            window._sketch_mode.cancel()
        window.undo_stack.setClean()
        window.close()
        app.processEvents()


def exercise_drawing_tools(window: MainWindow) -> None:
    """Exercise all native drawing tools on an empty part."""
    window._set_document(Document(), None)
    window._start_sketch("XY", 0.0, None)
    QTest.qWait(550)
    mode = window._sketch_mode
    assert mode is not None

    def click(point: tuple[float, float]) -> None:
        QTest.mouseClick(
            window.viewer, Qt.MouseButton.LeftButton, pos=mode.scene.screen(point).toPoint()
        )

    mode.actions["line"].trigger()
    click((-30, -20))
    click((-10, -20))
    assert len(mode.interaction.clicks) == 1
    QTest.mouseClick(
        window.viewer,
        Qt.MouseButton.RightButton,
        pos=mode.scene.screen((-10, -20)).toPoint(),
    )
    assert not mode.interaction.clicks
    assert mode.session.problems
    assert "problem-rings" in mode.scene._objects
    mode.actions["circle"].trigger()
    click((20, 20))
    click((30, 20))
    mode.actions["arc"].trigger()
    click((20, -20))
    click((30, -20))
    click((20, -10))
    mode.actions["point"].trigger()
    click((-20, 20))
    geometry = mode.session.sketch.geo.values()
    assert sum(isinstance(item, Line) for item in geometry) == 1
    assert sum(isinstance(item, Circle) for item in geometry) == 1
    assert sum(isinstance(item, Arc) for item in geometry) == 1
    assert sum(isinstance(item, Point) for item in geometry) >= 1
    assert mode.session.profile_text != "1 closed profile"

    circle = next(item for item in geometry if isinstance(item, Circle))
    mode.session.set_selection([circle.id])
    QTest.keyClick(window.viewer, Qt.Key.Key_G)
    assert mode.session.sketch.geo[circle.id].construction
    assert mode.actions["construction"].isChecked()
    mode.actions["finish"].trigger()
    assert len(window.doc.features) == 1

    window._set_document(Document(), None)
    window._start_sketch("XY", 10000.0, None)
    QTest.qWait(550)
    mode = window._sketch_mode
    assert mode is not None
    mode.session.edit(
        "Large rectangle", lambda sketch: add_rectangle(sketch, (10000, 10000), (10100, 10050))
    )
    window.actions["fit"].trigger()
    pos = mode.scene.screen((10050, 10025))
    assert window.viewer.rect().contains(pos.toPoint())
    assert mode.scene.to_sketch(pos) == pytest.approx((10050, 10025), abs=50)
    assert mode.scene._signatures["grid"]
    mode.actions["finish"].trigger()
