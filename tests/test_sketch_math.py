"""Headless tests for sketch interaction geometry."""

import math

import pytest

from sillycad.core.geometry import BASE_PLANES, Placement
from sillycad.core.sketch import ORIGIN, Arc, Circle, Line, Point, Sketch
from sillycad.core.solver import solve
from sillycad.sketch_math import (
    SnapTarget,
    add_rectangle,
    arc_sweep,
    constrain_snap,
    curve_distance,
    infer_dimension,
    infer_line_alignment,
    ray_to_sketch,
    sketch_to_world,
    snap_targets,
)


@pytest.mark.parametrize("plane", list(BASE_PLANES.values()))
def test_ray_plane_round_trip_with_offset(plane: Placement) -> None:
    point = (7.5, -12.0)
    world = sketch_to_world(point, plane, 3.0)
    ray = (0.25, 0.5, 1.0)
    if abs(sum(a * b for a, b in zip(ray, plane.normal, strict=True))) < 0.1:
        ray = plane.normal
    origin = tuple(a + 20 * b for a, b in zip(world, ray, strict=True))
    assert ray_to_sketch(origin, ray, plane, 3.0) == pytest.approx(point)


def test_ray_plane_round_trip_on_slanted_plane() -> None:
    plane = Placement((4, -2, 9), (0, math.sqrt(0.5), math.sqrt(0.5)), (1, 0, 0))
    world = sketch_to_world((5, 6), plane, 2)
    origin = tuple(a + b for a, b in zip(world, plane.normal, strict=True))
    assert ray_to_sketch(origin, plane.normal, plane, 2) == pytest.approx((5, 6))
    with pytest.raises(ValueError, match="edge-on"):
        ray_to_sketch((0, 0, 0), (1, 0, 0), plane)


def test_curve_picking_distances_and_arc_sweep() -> None:
    sketch = Sketch()
    line = sketch.add_line(0, 0, 10, 0)
    circle = sketch.add_circle(0, 0, 5)
    arc = sketch.add_arc(0, 0, 5, 0, 0, 5)
    assert curve_distance(sketch, sketch.geo[line], (5, 2)) == pytest.approx(2)
    assert curve_distance(sketch, sketch.geo[circle], (0, 7)) == pytest.approx(2)
    assert curve_distance(sketch, sketch.geo[arc], (-5, 0)) == pytest.approx(math.sqrt(50))
    assert arc_sweep((0, 0), (5, 0), (0, 5))[1] == pytest.approx(math.pi / 2)


def test_smart_dimension_inference() -> None:
    sketch = Sketch()
    line = sketch.add_line(0, 0, 10, 0)
    other = sketch.add_line(0, 0, 0, 10)
    circle = sketch.add_circle(0, 0, 5)
    arc = sketch.add_arc(0, 0, 5, 0, 0, 5)
    point = sketch.add_point(2, 3)
    assert infer_dimension(sketch, [line]) == "distance"
    assert infer_dimension(sketch, [circle]) == "diameter"
    assert infer_dimension(sketch, [arc]) == "radius"
    assert infer_dimension(sketch, [line, other]) == "angle"
    assert infer_dimension(sketch, [point, ORIGIN]) == "distance"
    assert infer_dimension(sketch, [point, line]) == "distance"
    with pytest.raises(ValueError, match="select"):
        infer_dimension(sketch, [circle, line])


def test_rectangle_is_four_constrained_lines_and_snaps() -> None:
    sketch = Sketch()
    lines = add_rectangle(sketch, (0, 0), (20, 10), start_snap=ORIGIN)
    assert len(lines) == 4
    assert all(isinstance(sketch.geo[line], Line) for line in lines)
    assert len(sketch.constraints) == 9
    assert solve(sketch).ok
    for i, line in enumerate(lines):
        assert sketch.point(sketch.geo[line].p2) == pytest.approx(
            sketch.point(sketch.geo[lines[(i + 1) % 4]].p1)
        )
    with pytest.raises(ValueError, match="nonzero"):
        add_rectangle(sketch, (0, 0), (0, 10))


def test_snap_targets_include_sketch_key_points_and_face_outline() -> None:
    sketch = Sketch()
    line_id = sketch.add_line(2, 4, 12, 8)
    circle_id = sketch.add_circle(20, 10, 4)
    arc_id = sketch.add_arc(30, 10, 35, 10, 30, 15)
    line, circle, arc = sketch.geo[line_id], sketch.geo[circle_id], sketch.geo[arc_id]
    assert isinstance(line, Line) and isinstance(circle, Circle) and isinstance(arc, Arc)
    targets = snap_targets(sketch, [[(40, 0), (50, 0)], [(60, 0), (65, 5), (70, 0)], []])
    assert SnapTarget((0, 0), "point", ORIGIN) in targets
    assert SnapTarget((2, 4), "point", line.p1) in targets
    assert SnapTarget((7, 6), "midpoint", line_id) in targets
    assert SnapTarget((20, 10), "point", circle.center) in targets
    assert SnapTarget((30, 10), "point", arc.center) in targets
    assert SnapTarget((35, 10), "point", arc.start) in targets
    assert SnapTarget((40, 0), "reference") in targets
    assert SnapTarget((45, 0), "reference") in targets
    assert SnapTarget((65, 0), "reference") not in targets


def test_snap_constraints_follow_points_and_line_midpoints() -> None:
    sketch = Sketch()
    line_id = sketch.add_line(0, 0, 20, 0)
    existing = sketch.geo[line_id]
    assert isinstance(existing, Line)
    point = sketch.add_point(10, 0)
    constrain_snap(sketch, point, SnapTarget((10, 0), "midpoint", line_id))
    center = sketch.add_point(0, 0)
    constrain_snap(sketch, center, SnapTarget((0, 0), "point", ORIGIN))
    guide_point = sketch.add_point(30, 0)
    constrain_snap(sketch, guide_point, SnapTarget((30, 0), "reference"))
    assert [c.kind for c in sketch.constraints.values()] == ["midpoint", "coincident"]
    end = sketch.geo[existing.p2]
    assert isinstance(end, Point)
    end.x = 30
    assert solve(sketch).ok
    a, b = sketch.line_points(line_id)
    assert sketch.point(point) == pytest.approx(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    assert sketch.point(center) == pytest.approx((0, 0))
    assert sketch.point(guide_point) == pytest.approx((30, 0))
    with pytest.raises(ValueError, match="no sketch reference"):
        constrain_snap(sketch, point, SnapTarget((0, 0), "point"))


def test_intersecting_sketch_lines_are_key_points() -> None:
    sketch = Sketch()
    first = sketch.add_line(0, 2, 10, 2)
    second = sketch.add_line(4, -3, 4, 9)
    sketch.add_line(20, 0, 20, 1)
    sketch.add_line(0, 4, 10, 4)
    targets = snap_targets(sketch, [])
    crossing = SnapTarget((4, 2), "intersection", first, second)
    assert crossing in targets
    assert not any(t.point == (20, 2) and t.kind == "intersection" for t in targets)
    point = sketch.add_point(*crossing.point)
    constrain_snap(sketch, point, crossing)
    assert [(c.kind, c.refs) for c in sketch.constraints.values()] == [
        ("point_on_line", [point, first]),
        ("point_on_line", [point, second]),
    ]


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("axis", ["horizontal", "vertical"])
def test_line_alignment_exact_five_degree_threshold(direction: int, axis: str) -> None:
    start = (4.0, -3.0)

    def endpoint(angle: float) -> tuple[float, float]:
        long = direction * 100
        short = 100 * math.tan(math.radians(angle))
        return (
            (start[0] + long, start[1] + short)
            if axis == "horizontal"
            else (start[0] + short, start[1] + long)
        )

    for angle in (0, 4.99, 5.0):
        point, alignment = infer_line_alignment(start, endpoint(angle))
        assert alignment == axis
        if axis == "horizontal":
            assert point == pytest.approx((endpoint(angle)[0], start[1]))
        else:
            assert point == pytest.approx((start[0], endpoint(angle)[1]))
    point, alignment = infer_line_alignment(start, endpoint(5.01))
    assert point == pytest.approx(endpoint(5.01))
    assert alignment is None


def test_line_alignment_leaves_zero_and_diagonal_lines_free() -> None:
    assert infer_line_alignment((1, 2), (1, 2)) == ((1, 2), None)
    assert infer_line_alignment((1, 2), (11, 12)) == ((11, 12), None)
