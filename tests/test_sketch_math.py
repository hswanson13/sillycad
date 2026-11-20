"""Headless tests for sketch interaction geometry."""

import math

import pytest

from sillycad.core.geometry import BASE_PLANES, Placement
from sillycad.core.sketch import ORIGIN, Line, Sketch
from sillycad.core.solver import solve
from sillycad.sketch_math import (
    add_rectangle,
    arc_sweep,
    curve_distance,
    infer_dimension,
    ray_to_sketch,
    sketch_to_world,
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
