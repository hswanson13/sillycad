"""Headless tests for screen-space key-point snapping."""

import os

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from sillycad.core.sketch import Line, Sketch
from sillycad.gui.sketch_scene import PICK_PIXELS, SketchScene
from sillycad.gui.sketch_session import SketchSession
from sillycad.sketch_math import SnapTarget


@pytest.fixture(scope="module")
def app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class SnapScene(SketchScene):
    """A sketch scene with a predictable orthographic screen projection."""

    def __init__(self, sketch: Sketch, scale: float) -> None:
        self.session = SketchSession(sketch, [[(30, 0), (50, 0)]])
        self.scale = scale

    def screen(self, point: tuple[float, float]) -> QPointF:
        return QPointF(point[0] * self.scale, point[1] * self.scale)

    def to_sketch(self, point: QPointF) -> tuple[float, float]:
        return point.x() / self.scale, point.y() / self.scale


@pytest.mark.parametrize("scale", [0.5, 5.0, 40.0])
def test_snap_uses_screen_pixels_at_each_zoom(app: QApplication, scale: float) -> None:
    sketch = Sketch()
    line_id = sketch.add_line(10, 20, 20, 20)
    scene = SnapScene(sketch, scale)
    target_pos = scene.screen((15, 20))
    point, target = scene.snap(target_pos + QPointF(0, PICK_PIXELS - 1))
    assert point == pytest.approx((15, 20))
    assert target == SnapTarget((15, 20), "midpoint", line_id)
    _, target = scene.snap(target_pos + QPointF(0, PICK_PIXELS + 1))
    assert target is None


def test_snap_selects_nearest_point_and_prefers_sketch_points_on_ties(app: QApplication) -> None:
    sketch = Sketch()
    line_id = sketch.add_line(30, 0, 50, 0)
    line = sketch.geo[line_id]
    assert isinstance(line, Line)
    scene = SnapScene(sketch, 10)
    point, target = scene.snap(QPointF(301, 0))
    assert point == (30, 0)
    assert target == SnapTarget((30, 0), "point", line.p1)
    point, target = scene.snap(QPointF(400, 0))
    assert point == (40, 0)
    assert target == SnapTarget((40, 0), "midpoint", line_id)
