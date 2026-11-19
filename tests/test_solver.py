"""Sketch model and planegcs solver tests (headless)."""

import copy
import math

import pytest
from pytest import approx

from sillycad.core.sketch import ORIGIN, X_AXIS, Sketch
from sillycad.core.solver import drag, solve


def rectangle(width: float | None = 40.0, height: float | None = 20.0) -> tuple[Sketch, list[str]]:
    """A rough 4-line rectangle: corners joined, sides H/V, bottom-left on the origin."""
    s = Sketch()
    corners = [(1, 1), (35, 2), (36, 25), (0, 22)]
    lines = [s.add_line(*corners[i], *corners[(i + 1) % 4]) for i in range(4)]
    for i in range(4):
        s.add_constraint("coincident", [s.geo[lines[i]].p2, s.geo[lines[(i + 1) % 4]].p1])
    s.add_constraint("horizontal", [lines[0]])
    s.add_constraint("horizontal", [lines[2]])
    s.add_constraint("vertical", [lines[1]])
    s.add_constraint("vertical", [lines[3]])
    s.add_constraint("coincident", [s.geo[lines[0]].p1, ORIGIN])
    if width is not None:
        s.add_constraint("distance", [lines[0]], width)
    if height is not None:
        s.add_constraint("distance", [lines[1]], height)
    return s, lines


def test_fully_constrained_rectangle() -> None:
    s, lines = rectangle()
    result = solve(s)
    assert result.fully_constrained
    assert result.message == "Fully constrained"
    corners = [s.point(s.geo[line].p1) for line in lines]
    for corner, expected in zip(corners, [(0, 0), (40, 0), (40, 20), (0, 20)], strict=True):
        assert corner == approx(expected, abs=1e-9)


def test_under_constrained_rectangle_reports_dof() -> None:
    s, _ = rectangle(width=None, height=None)
    result = solve(s)
    assert result.ok
    assert result.dof == 2  # width and height are still free
    assert result.message == "2 degrees of freedom left"


def test_conflict_is_detected_and_geometry_is_kept() -> None:
    s, lines = rectangle()
    solve(s)
    before = copy.deepcopy(s.geo)
    corner_a, corner_c = s.geo[lines[0]].p1, s.geo[lines[1]].p2
    bad = s.add_constraint("distance", [corner_a, corner_c], 50)  # diagonal must be ~44.7
    result = solve(s)
    assert not result.solved
    assert bad in result.conflicting
    assert "Conflicting" in result.message
    assert s.geo == before  # nothing moved: last good state kept


def test_redundant_constraint_is_detected() -> None:
    s, lines = rectangle()
    extra = s.add_constraint("parallel", [lines[0], lines[2]])  # already both horizontal
    result = solve(s)
    assert extra in result.redundant
    assert not result.ok


def test_new_dimension_takes_current_value() -> None:
    s = Sketch()
    line = s.add_line(0, 0, 30, 40)
    cid = s.add_constraint("distance", [line])
    assert s.constraints[cid].value == approx(50)
    solve(s)
    p1, p2 = s.line_points(line)
    assert (*p1, *p2) == approx((0, 0, 30, 40))


def test_circle_diameter_and_center_distances() -> None:
    s = Sketch()
    circle = s.add_circle(3, 4, 2)
    center = s.geo[circle].center
    s.add_constraint("distance_x", [ORIGIN, center], 10)
    s.add_constraint("distance_y", [center, ORIGIN], 5)  # selection order doesn't matter
    s.add_constraint("diameter", [circle], 12)
    result = solve(s)
    assert result.fully_constrained
    assert s.point(center) == approx((10, 5))
    assert s.geo[circle].radius == approx(6)


def test_angle_is_in_degrees() -> None:
    s = Sketch()
    a, b = s.add_line(0, 0, 10, 0), s.add_line(0, 0, 8, 3)
    s.add_constraint("coincident", [s.geo[a].p1, ORIGIN])
    s.add_constraint("coincident", [s.geo[b].p1, ORIGIN])
    s.add_constraint("horizontal", [a])
    s.add_constraint("angle", [a, b], 30)
    assert solve(s).ok
    (x1, y1), (x2, y2) = s.line_points(b)
    assert math.degrees(math.atan2(y2 - y1, x2 - x1)) == approx(30)


def test_line_tangent_to_arc() -> None:
    s = Sketch()
    line = s.add_line(0, 0, 10, 0.5)
    arc = s.add_arc(10, 5, 10.2, 0, 15, 5)
    s.add_constraint("coincident", [s.geo[line].p2, s.geo[arc].start])
    s.add_constraint("tangent", [arc, line])
    assert solve(s).ok
    (ax, ay), (bx, by) = s.line_points(line)
    cx, cy = s.point(s.geo[arc].center)
    distance = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / math.hypot(bx - ax, by - ay)
    assert distance == approx(s.radius(arc))


def test_fix_and_midpoint() -> None:
    s = Sketch()
    line = s.add_line(0, 0, 10, 0)
    point = s.add_point(3, 2)
    s.add_constraint("fix", [s.geo[line].p1])
    s.add_constraint("fix", [s.geo[line].p2])
    s.add_constraint("midpoint", [line, point])
    result = solve(s)
    assert result.fully_constrained
    assert s.point(point) == approx((5, 0))


def test_equal_radius_circle_and_arc() -> None:
    s = Sketch()
    circle = s.add_circle(0, 0, 5)
    arc = s.add_arc(20, 0, 23, 0, 20, 3)
    s.add_constraint("equal", [arc, circle])
    s.add_constraint("radius", [circle], 4)
    assert solve(s).ok
    assert s.radius(arc) == approx(4)


def test_constraints_on_axis() -> None:
    s = Sketch()
    line = s.add_line(1, 2, 9, 3)
    s.add_constraint("parallel", [line, X_AXIS])
    s.add_constraint("distance", [s.geo[line].p1, X_AXIS], 7)
    assert solve(s).ok
    (_, y1), (_, y2) = s.line_points(line)
    assert (y1, y2) == approx((7, 7))


def test_invalid_selections_give_friendly_errors() -> None:
    s = Sketch()
    line = s.add_line(0, 0, 10, 0)
    with pytest.raises(ValueError, match="Parallel needs two lines"):
        s.add_constraint("parallel", [line])
    with pytest.raises(ValueError, match="Radius needs a circle or arc"):
        s.add_constraint("radius", [line])
    with pytest.raises(ValueError, match="not just the origin/axes"):
        s.add_constraint("perpendicular", [X_AXIS, "y_axis"])
    with pytest.raises(ValueError, match="greater than zero"):
        s.add_constraint("distance", [line], -5)


def test_delete_line_removes_its_points_and_constraints() -> None:
    s, lines = rectangle()
    gone = s.geo[lines[0]]
    s.delete([lines[0]])
    assert lines[0] not in s.geo
    assert gone.p1 not in s.geo and gone.p2 not in s.geo
    for c in s.constraints.values():
        assert not {lines[0], gone.p1, gone.p2} & set(c.refs)


def test_drag_free_point_goes_exactly_to_mouse() -> None:
    s = Sketch()
    line = s.add_line(0, 0, 10, 0)
    s.add_constraint("fix", [s.geo[line].p1])
    assert drag(s, {s.geo[line].p2: (50, 30)})
    assert s.point(s.geo[line].p2) == approx((50, 30))
    assert s.point(s.geo[line].p1) == approx((0, 0))


def test_drag_slides_along_remaining_freedom() -> None:
    s, lines = rectangle(height=None)  # width fixed, height free
    solve(s)
    corner = s.geo[lines[1]].p2
    assert drag(s, {corner: (50, 30)})
    assert s.point(corner) == approx((40, 30))  # x is held by the width, y follows the mouse


def test_drag_cannot_move_fully_constrained_point() -> None:
    s, lines = rectangle()
    solve(s)
    corner = s.geo[lines[1]].p2
    drag(s, {corner: (50, 30)})
    assert s.point(corner) == approx((40, 20))


def test_drag_circle_radius() -> None:
    s = Sketch()
    circle = s.add_circle(0, 0, 5)
    assert drag(s, {}, {circle: 8})
    assert s.geo[circle].radius == approx(8)


def test_duplicate_and_contradictory_constraints_are_refused() -> None:
    s = Sketch()
    line = s.add_line(0, 0, 10, 1)
    s.add_constraint("horizontal", [line])
    with pytest.raises(ValueError, match="already has a Horizontal"):
        s.add_constraint("horizontal", [line])
    with pytest.raises(ValueError, match="both horizontal and vertical"):
        s.add_constraint("vertical", [line])


def test_drag_slides_when_closing_corner_is_on_origin() -> None:
    """Regression: the walkthrough rectangle (both ends on the origin) must still slide."""
    s = Sketch()
    corners = [(0, 0), (60, 0), (60, 20), (0, 20)]
    lines = [s.add_line(*corners[i], *corners[(i + 1) % 4]) for i in range(4)]
    s.add_constraint("coincident", [s.geo[lines[0]].p1, ORIGIN])
    for i in range(3):
        s.add_constraint("coincident", [s.geo[lines[i + 1]].p1, s.geo[lines[i]].p2])
    s.add_constraint("coincident", [s.geo[lines[3]].p2, ORIGIN])
    for line, kind in zip(lines, ["horizontal", "vertical"] * 2, strict=True):
        s.add_constraint(kind, [line])
    s.add_constraint("distance", [lines[0]], 60)
    assert solve(s).dof == 1
    corner = s.geo[lines[1]].p2
    assert drag(s, {corner: (67, 34)})
    assert s.point(corner) == approx((60, 34))
