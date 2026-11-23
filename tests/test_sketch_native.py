"""Opt-in real-window tests for native OCCT sketch interaction."""

import math
import os
from pathlib import Path

import pytest
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QImage, QPainter, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from sillycad.core.document import Document
from sillycad.core.features import Hole, Pad, Pocket, Revolve, SketchFeature
from sillycad.core.geometry import face_placement, volume
from sillycad.core.sketch import ORIGIN, Arc, Circle, Line, Point, Sketch
from sillycad.gui import theme
from sillycad.gui.hole_panel import HolePanel
from sillycad.gui.main_window import UI_FONTS, MainWindow
from sillycad.sketch_math import add_rectangle

pytestmark = pytest.mark.skipif(
    not os.environ.get("SILLYCAD_NATIVE_GUI_TESTS") or not os.environ.get("DISPLAY"),
    reason="requires an explicitly enabled native display",
)


def exercise_key_point_snapping(window: MainWindow, tmp_path: Path) -> None:
    """Exercise key-point feedback and constraints on an extruded face."""
    base = Sketch()
    add_rectangle(base, (0, 0), (60, 40))
    window._set_document(
        Document([SketchFeature("s1", "Sketch1", sketch=base), Pad("p1", "Pad1", "s1")]),
        None,
    )
    window._start_sketch("XY", 10, None)
    QTest.qWait(550)
    window.viewer.stop_camera_animation()
    mode = window._sketch_mode
    assert mode is not None
    mode.session.edit("Reference line", lambda sketch: sketch.add_line(10, 15, 40, 15))
    line = next(g for g in mode.session.sketch.geo.values() if isinstance(g, Line))
    mode.actions["point"].trigger()

    midpoint = mode.scene.screen((25, 15)).toPoint()
    QTest.mouseMove(window.viewer, midpoint + QPoint(3, 2), delay=20)
    target = mode.scene._snap_target
    assert target is not None and target.kind == "midpoint" and target.ref == line.id
    assert "snap" in mode.scene._objects
    image_path = tmp_path / "snap.png"
    assert window.viewer._display.View.Dump(str(image_path))
    image = QImage(str(image_path))
    assert not image.isNull()
    green_pixels = 0
    for y in range(midpoint.y() - 7, midpoint.y() + 8):
        for x in range(midpoint.x() - 7, midpoint.x() + 8):
            color = image.pixelColor(x, y)
            if color.green() > 100 and color.green() > 1.3 * max(color.red(), color.blue()):
                green_pixels += 1
    assert green_pixels >= 20
    QTest.mouseClick(window.viewer, Qt.MouseButton.LeftButton, pos=midpoint + QPoint(3, 2))
    point_id = next(
        c.refs[0] for c in mode.session.sketch.constraints.values() if c.kind == "midpoint"
    )
    assert mode.session.sketch.point(point_id) == pytest.approx((25, 15))
    mode.session.undo_stack.undo()
    assert point_id not in mode.session.sketch.geo
    mode.session.undo_stack.redo()
    assert point_id in mode.session.sketch.geo

    guide_midpoint = mode.scene.screen((0, 20)).toPoint()
    QTest.mouseMove(window.viewer, guide_midpoint + QPoint(2, 2), delay=20)
    target = mode.scene._snap_target
    assert target is not None and target.kind == "reference"
    assert target.point == pytest.approx((0, 20))
    old_constraints = len(mode.session.sketch.constraints)
    QTest.mouseClick(window.viewer, Qt.MouseButton.LeftButton, pos=guide_midpoint + QPoint(2, 2))
    assert len(mode.session.sketch.constraints) == old_constraints

    origin = mode.scene.screen((0, 0)).toPoint()
    QTest.mouseMove(window.viewer, origin + QPoint(2, 2), delay=20)
    target = mode.scene._snap_target
    assert target is not None and target.ref == ORIGIN
    mode.actions["select"].trigger()
    assert mode.scene._snap_target is None
    assert "snap" not in mode.scene._objects

    mode.actions["line"].trigger()
    QTest.mouseClick(
        window.viewer, Qt.MouseButton.LeftButton, pos=mode.scene.screen((10, 15)).toPoint()
    )
    QTest.mouseClick(
        window.viewer, Qt.MouseButton.LeftButton, pos=mode.scene.screen((60, 20)).toPoint()
    )
    new_line = [g for g in mode.session.sketch.geo.values() if isinstance(g, Line)][-1]
    assert mode.session.sketch.point(new_line.p2) == pytest.approx((60, 20))
    assert any(
        c.kind == "coincident" and set(c.refs) == {new_line.p1, line.p1}
        for c in mode.session.sketch.constraints.values()
    )
    assert mode.interaction.clicks

    mode.actions["circle"].trigger()
    QTest.mouseClick(window.viewer, Qt.MouseButton.LeftButton, pos=origin)
    QTest.mouseClick(
        window.viewer, Qt.MouseButton.LeftButton, pos=mode.scene.screen((8, 8)).toPoint()
    )
    circle = next(g for g in mode.session.sketch.geo.values() if isinstance(g, Circle))
    assert any(
        c.kind == "coincident" and set(c.refs) == {circle.center, ORIGIN}
        for c in mode.session.sketch.constraints.values()
    )

    mode.session.edit("Another line", lambda sketch: sketch.add_line(15, 30, 35, 30))
    midpoint_line = [g for g in mode.session.sketch.geo.values() if isinstance(g, Line)][-1]
    mode.actions["rectangle"].trigger()
    QTest.mousePress(
        window.viewer, Qt.MouseButton.LeftButton, pos=mode.scene.screen((25, 30)).toPoint()
    )
    QTest.mouseRelease(
        window.viewer, Qt.MouseButton.LeftButton, pos=mode.scene.screen((35, 35)).toPoint()
    )
    assert any(
        c.kind == "midpoint" and midpoint_line.id in c.refs
        for c in mode.session.sketch.constraints.values()
    )

    mode.session.edit("Arc target", lambda sketch: sketch.add_point(55, 10))
    mode.actions["arc"].trigger()
    for point in ((50, 5), (55, 5)):
        QTest.mouseClick(
            window.viewer, Qt.MouseButton.LeftButton, pos=mode.scene.screen(point).toPoint()
        )
    QTest.mouseMove(window.viewer, mode.scene.screen((55, 10)).toPoint(), delay=20)
    assert mode.scene._snap_target is None
    QTest.mouseClick(
        window.viewer, Qt.MouseButton.LeftButton, pos=mode.scene.screen((55, 10)).toPoint()
    )
    arc = next(g for g in mode.session.sketch.geo.values() if isinstance(g, Arc))
    assert not any(arc.end in c.refs for c in mode.session.sketch.constraints.values())

    mode.actions["finish"].trigger()


def exercise_line_inference(window: MainWindow, tmp_path: Path) -> None:
    """Verify aligned previews and constraints while sketching on a solid face."""
    base = Sketch()
    add_rectangle(base, (0, 0), (60, 40))
    window._set_document(
        Document([SketchFeature("s1", "Sketch1", sketch=base), Pad("p1", "Pad1", "s1")]),
        None,
    )
    window._start_sketch("XY", 10, None)
    QTest.qWait(550)
    window.viewer.stop_camera_animation()
    mode = window._sketch_mode
    assert mode is not None

    def position(point: tuple[float, float]) -> QPoint:
        return mode.scene.screen(point).toPoint()

    def click(point: tuple[float, float], modifiers: Qt.KeyboardModifier = Qt.NoModifier) -> None:
        QTest.mouseClick(window.viewer, Qt.MouseButton.LeftButton, modifiers, position(point))

    mode.actions["line"].trigger()
    click((10, 10))
    start = mode.interaction.clicks[0][0]
    QTest.mouseMove(window.viewer, position((40, 10.8)), delay=20)
    assert mode.scene._preview_aligned
    assert mode.scene._preview[0][1][1] == start[1]
    assert mode.scene._signatures["preview"][1] == theme.SKETCH_SNAP
    image_path = tmp_path / "alignment.png"
    assert window.viewer._display.View.Dump(str(image_path))
    image = QImage(str(image_path))
    line_pos = mode.scene.screen((25, start[1])).toPoint()
    green_pixels = 0
    for y in range(line_pos.y() - 3, line_pos.y() + 4):
        for x in range(line_pos.x() - 10, line_pos.x() + 11):
            color = image.pixelColor(x, y)
            if color.green() > 100 and color.green() > 1.3 * max(color.red(), color.blue()):
                green_pixels += 1
    assert green_pixels >= 10
    click((40, 10.8))
    first = next(g for g in mode.session.sketch.geo.values() if isinstance(g, Line))
    assert any(
        c.kind == "horizontal" and c.refs == [first.id]
        for c in mode.session.sketch.constraints.values()
    )
    assert mode.session.sketch.point(first.p1)[1] == pytest.approx(
        mode.session.sketch.point(first.p2)[1]
    )
    assert mode.interaction.clicks
    mode.session.undo_stack.undo()
    assert not mode.interaction.clicks
    assert first.id not in mode.session.sketch.geo
    mode.session.undo_stack.redo()
    assert first.id in mode.session.sketch.geo

    mode.actions["line"].trigger()
    click(mode.session.sketch.point(first.p2))
    QTest.mouseMove(window.viewer, position((40.8, 30)), delay=20)
    assert mode.scene._preview_aligned
    click((40.8, 30))
    vertical = [g for g in mode.session.sketch.geo.values() if isinstance(g, Line)][-1]
    assert any(
        c.kind == "vertical" and c.refs == [vertical.id]
        for c in mode.session.sketch.constraints.values()
    )
    assert mode.session.sketch.point(vertical.p1)[0] == pytest.approx(
        mode.session.sketch.point(vertical.p2)[0]
    )
    assert any(
        c.kind == "coincident" and set(c.refs) == {first.p2, vertical.p1}
        for c in mode.session.sketch.constraints.values()
    )

    mode.actions["line"].trigger()
    click((10, 25))
    QTest.mouseMove(window.viewer, position((30, 25.5)), delay=20)
    assert mode.scene._preview_aligned
    QTest.keyPress(window.viewer, Qt.Key.Key_Control)
    assert not mode.scene._preview_aligned
    assert mode.scene._signatures["preview"][1] == theme.SKETCH_HOVER
    QTest.keyRelease(window.viewer, Qt.Key.Key_Control)
    assert mode.scene._preview_aligned
    click((30, 25.5), Qt.KeyboardModifier.ControlModifier)
    free = [g for g in mode.session.sketch.geo.values() if isinstance(g, Line)][-1]
    assert not any(
        c.kind in ("horizontal", "vertical") and c.refs == [free.id]
        for c in mode.session.sketch.constraints.values()
    )
    assert abs(mode.session.sketch.point(free.p1)[1] - mode.session.sketch.point(free.p2)[1]) > 0.1

    mode.session.edit("Snap target", lambda sketch: sketch.add_point(50, 35.5))
    target = next(
        g
        for g in mode.session.sketch.geo.values()
        if isinstance(g, Point) and (g.x, g.y) == pytest.approx((50, 35.5))
    )
    mode.actions["line"].trigger()
    click((20, 35))
    QTest.mouseMove(window.viewer, position((50, 35.5)), delay=20)
    assert not mode.scene._preview_aligned
    assert mode.scene._snap_target is not None and mode.scene._snap_target.ref == target.id
    click((50, 35.5))
    snapped = [g for g in mode.session.sketch.geo.values() if isinstance(g, Line)][-1]
    assert mode.session.sketch.point(snapped.p2) == pytest.approx((50, 35.5))
    assert any(
        c.kind == "coincident" and target.id in c.refs
        for c in mode.session.sketch.constraints.values()
    )
    assert not any(
        c.kind in ("horizontal", "vertical") and c.refs == [snapped.id]
        for c in mode.session.sketch.constraints.values()
    )
    mode.actions["finish"].trigger()

    window._start_sketch("XZ", 0, None)
    QTest.qWait(550)
    mode = window._sketch_mode
    assert mode is not None
    center = window.viewer.rect().center()
    QTest.mousePress(
        window.viewer, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.ShiftModifier, center
    )
    QTest.mouseMove(window.viewer, center + QPoint(30, 20), delay=20)
    QTest.mouseRelease(window.viewer, Qt.MouseButton.MiddleButton, pos=center + QPoint(30, 20))
    mode.actions["line"].trigger()
    click((10, 3))
    start = mode.interaction.clicks[0][0]
    QTest.mouseMove(window.viewer, position((40, 3.8)), delay=20)
    assert mode.scene._preview_aligned
    assert mode.scene._preview[0][1][1] == start[1]
    click((40, 3.8))
    line = next(g for g in mode.session.sketch.geo.values() if isinstance(g, Line))
    assert any(
        c.kind == "horizontal" and c.refs == [line.id]
        for c in mode.session.sketch.constraints.values()
    )
    mode.actions["finish"].trigger()


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
        window.activateWindow()
        window.viewer.setFocus()
        assert QTest.qWaitForWindowActive(window, 2000)
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
        QTest.keyClick(window.viewer, Qt.Key.Key_E)
        panel = window._feature_panel
        assert panel is not None
        assert panel.feature.sketch_id == sketch.id
        assert not panel.message.text()
        panel.length.setValue(5)
        assert not panel.message.text()
        panel.length.setFocus()
        QTest.keyClick(panel.length, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        assert window._feature_panel is None
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
        exercise_feature_panels(window)
        exercise_drawing_tools(window)
        exercise_key_point_snapping(window, tmp_path)
        exercise_line_inference(window, tmp_path)
        exercise_hole_panel(window, tmp_path, app)
    finally:
        if window._sketch_mode is not None:
            window._sketch_mode.session.undo_stack.setClean()
            window._sketch_mode.cancel()
        window.undo_stack.setClean()
        window.close()
        app.processEvents()


def exercise_hole_panel(window: MainWindow, tmp_path: Path, app: QApplication) -> None:
    """Exercise a hole preview using the existing native OCCT window."""
    font = QFont()
    font.setFamilies(UI_FONTS)
    font.setStyleHint(QFont.StyleHint.Cursive)
    app.setFont(font)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)
    window.resize(1400, 1000)
    base = Sketch()
    add_rectangle(base, (0, 0), (60, 40))
    centers = Sketch()
    point = centers.add_point(30, 20)
    window._set_document(
        Document(
            [
                SketchFeature("f1", "Base", sketch=base),
                Pad("f2", "Block", "f1"),
                SketchFeature("f3", "Centers", "XY", 10, centers),
            ],
            4,
        ),
        None,
    )
    if window.actions["planes"].isChecked():
        window.actions["planes"].trigger()
    window.viewer.set_view("iso")
    window.actions["hole"].trigger()
    panel = window._feature_panel
    assert isinstance(panel, HolePanel)
    panel.point.setCurrentIndex(panel.point.findData(point))
    panel.style.setCurrentIndex(panel.style.findData("counterbore"))
    panel.thread.setChecked(True)
    panel.diameter.setValue(5)
    QTest.qWait(150)
    assert not panel.message.text()
    viewport_path = tmp_path / "u7-viewport.png"
    assert window.viewer._display.View.Dump(str(viewport_path))
    viewport = QImage(str(viewport_path))
    image = window.grab().toImage()
    painter = QPainter(image)
    painter.drawImage(window.viewer.mapTo(window, window.viewer.rect().topLeft()), viewport)
    painter.end()
    assert image.save(str(tmp_path / "u7-window-composite.png"))
    panel.ok.click()
    assert isinstance(window.doc.find("f4"), Hole)
    assert not window.model.errors
    assert volume(window.model.shape) < 24000


def exercise_feature_panels(window: MainWindow) -> None:
    """Verify Apply, Undo and Revolve against the native 3D preview."""
    base = Sketch()
    add_rectangle(base, (0, 0), (40, 20))
    hole = Sketch()
    add_rectangle(hole, (5, 5), (15, 10))
    window._set_document(
        Document(
            [
                SketchFeature("f1", "Sketch1", sketch=base),
                Pad("f2", "Extrusion1", "f1"),
                SketchFeature("f3", "Sketch2", "XY", 10, hole),
            ],
            next_id=4,
        ),
        None,
    )
    QTest.keyClick(window.viewer, Qt.Key.Key_E)
    panel = window._feature_panel
    assert panel is not None
    QTest.mouseClick(panel.cut, Qt.MouseButton.LeftButton)
    panel.extent.setCurrentIndex(panel.extent.findData("through_all"))
    assert not panel.message.text()
    QTest.mouseClick(panel.apply, Qt.MouseButton.LeftButton)
    assert panel is window._feature_panel
    assert isinstance(window.doc.features[-1], Pocket)
    assert volume(window.model.shape) == pytest.approx(7500)
    QTest.keyClick(window.viewer, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window._feature_panel is None
    assert len(window.doc.features) == 4
    QTest.keyClick(window.viewer, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert len(window.doc.features) == 3
    QTest.keyClick(window.viewer, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert len(window.doc.features) == 4
    QTest.keyClick(window.viewer, Qt.Key.Key_E)
    assert window._feature_panel is not None
    QTest.keyClick(window.viewer, Qt.Key.Key_Escape)
    assert window._feature_panel is None
    assert len(window.doc.features) == 4

    sketch = Sketch()
    add_rectangle(sketch, (10, 0), (15, 20))
    axis = sketch.add_line(-2, 0, -2, 10, construction=True)
    window._set_document(Document([SketchFeature("f1", "Sketch1", sketch=sketch)], next_id=2), None)
    QTest.keyClick(window.viewer, Qt.Key.Key_R)
    panel = window._feature_panel
    assert panel is not None
    panel.axis.setCurrentIndex(panel.axis.findData(axis))
    panel.extent.setCurrentIndex(panel.extent.findData("angle"))
    panel.angle.setValue(180)
    assert not panel.message.text()
    panel.angle.setFocus()
    QTest.keyClick(
        panel.angle,
        Qt.Key.Key_Enter,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.KeypadModifier,
    )
    revolution = window.doc.features[-1]
    assert isinstance(revolution, Revolve)
    assert revolution.axis == axis and revolution.angle == 180
    expected = math.pi * (17**2 - 12**2) * 20 / 2
    assert volume(window.model.shape) == pytest.approx(expected)
    window.edit_feature(revolution.id)
    panel = window._feature_panel
    assert panel is not None
    panel.extent.setCurrentIndex(panel.extent.findData("full"))
    panel.apply.click()
    assert volume(window.model.shape) == pytest.approx(expected * 2)
    panel.cancel.click()
    window.actions["undo"].trigger()
    assert volume(window.model.shape) == pytest.approx(expected)


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
