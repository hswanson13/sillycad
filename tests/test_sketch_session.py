"""Tests for local sketch editing and undo."""

import os

import pytest
from PySide6.QtWidgets import QApplication

from sillycad.core.sketch import ORIGIN, Circle, Line, Sketch
from sillycad.gui.sketch_session import SketchSession
from sillycad.sketch_math import add_rectangle


@pytest.fixture(scope="module")
def app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_rectangle_is_one_undoable_edit(app: QApplication) -> None:
    session = SketchSession(Sketch())
    assert session.edit("Add rectangle", lambda sketch: add_rectangle(sketch, (0, 0), (20, 10)))
    assert sum(isinstance(item, Line) for item in session.sketch.geo.values()) == 4
    assert len(session.sketch.constraints) == 8
    session.undo_stack.undo()
    assert not session.sketch.geo
    session.undo_stack.redo()
    assert sum(isinstance(item, Line) for item in session.sketch.geo.values()) == 4
    assert len(session.sketch.constraints) == 8


def test_smart_dimension_is_validated_and_undoable(app: QApplication) -> None:
    sketch = Sketch()
    circle = sketch.add_circle(3, 4, 5)
    session = SketchSession(sketch)
    session.set_selection([circle])
    kind, refs, value = session.constraint_trial("smart")
    assert (kind, refs, value) == ("diameter", [circle], 10)
    assert session.add_constraint(kind, refs, 12)
    cid = next(iter(session.sketch.constraints))
    assert session.sketch.constraints[cid].value == 12
    assert session.change_dimension(cid, 16)
    session.undo_stack.undo()
    assert session.sketch.constraints[cid].value == 12
    session.undo_stack.undo()
    assert not session.sketch.constraints


def test_invalid_constraint_and_edit_leave_the_sketch_unchanged(app: QApplication) -> None:
    session = SketchSession(Sketch())
    session.set_selection([ORIGIN])
    with pytest.raises(ValueError):
        session.constraint_trial("smart")
    messages = []
    session.message.connect(messages.append)
    assert not session.edit("Bad rectangle", lambda sketch: add_rectangle(sketch, (0, 0), (0, 10)))
    assert messages and not session.sketch.geo
    assert session.undo_stack.count() == 0


def test_drag_solves_and_commits_one_undo_step(app: QApplication) -> None:
    sketch = Sketch()
    line = sketch.add_line(0, 0, 10, 0)
    point = sketch.geo[line].p2
    session = SketchSession(sketch)
    before = session.start_drag()
    session.drag_to({point: (12, 4)})
    session.drag_to({point: (14, 8)})
    session.finish_drag(before)
    assert session.sketch.point(point) == pytest.approx((14, 8))
    assert session.undo_stack.count() == 1
    session.undo_stack.undo()
    assert session.sketch.point(point) == pytest.approx((10, 0))


def test_open_guide_warning_preserves_midpoint_and_radius_constraints(app: QApplication) -> None:
    sketch = Sketch()
    line = sketch.add_line(0, -5, 0, 5)
    circle = sketch.add_circle(0, 0, 100)
    curve = sketch.geo[circle]
    assert isinstance(curve, Circle)
    midpoint = sketch.add_constraint("midpoint", [curve.center, line])
    radius = sketch.add_constraint("radius", [circle], 100)
    session = SketchSession(sketch)
    assert session.result.ok
    assert "1 closed profile" in session.profile_text and "open" in session.profile_text.lower()
    assert len(session.problems) == 2
    session.set_selection([line])
    session.toggle_construction()
    assert session.profile_text == "1 closed profile"
    assert session.sketch.constraints[midpoint].refs == [curve.center, line]
    assert session.sketch.constraints[radius].value == 100
    session.undo_stack.undo()
    assert "open" in session.profile_text.lower()
