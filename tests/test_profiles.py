"""Profile detection: sketch loops -> faces, with clear errors."""

import math

import pytest
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps
from pytest import approx

from sillycad.core.features import SketchFeature
from sillycad.core.geometry import BASE_PLANES, place_on_plane
from sillycad.core.profiles import ProfileError, analyze_profiles, find_profiles
from sillycad.core.sketch import Sketch


def area(shape) -> float:  # noqa: ANN001
    props = GProp_GProps()
    brepgprop.SurfaceProperties(shape, props)
    return props.Mass()


def polygon(s: Sketch, corners: list[tuple[float, float]], construction: bool = False) -> None:
    """Closed polygon of lines whose ends meet exactly."""
    for i, a in enumerate(corners):
        s.add_line(*a, *corners[(i + 1) % len(corners)], construction=construction)


def test_rectangle_is_one_face() -> None:
    s = Sketch()
    polygon(s, [(0, 0), (40, 0), (40, 20), (0, 20)])
    faces = find_profiles(s)
    assert len(faces) == 1
    assert area(faces[0]) == approx(800)


def test_circle_inside_rectangle_is_a_hole() -> None:
    s = Sketch()
    polygon(s, [(0, 20), (40, 20), (40, 0), (0, 0)])  # clockwise: orientation doesn't matter
    s.add_circle(10, 10, 5)
    faces = find_profiles(s)
    assert len(faces) == 1
    assert area(faces[0]) == approx(800 - math.pi * 25)


def test_island_inside_hole_is_its_own_face() -> None:
    s = Sketch()
    polygon(s, [(0, 0), (100, 0), (100, 100), (0, 100)])
    s.add_circle(50, 50, 30)
    s.add_circle(50, 50, 10)
    faces = find_profiles(s)
    assert len(faces) == 2
    assert sorted(area(f) for f in faces) == approx(sorted([math.pi * 100, 10000 - math.pi * 900]))


def test_slot_with_arcs() -> None:
    s = Sketch()  # two half circles joined by two lines
    s.add_line(0, 0, 20, 0)
    s.add_arc(20, 5, 20, 0, 20, 10)
    s.add_line(20, 10, 0, 10)
    s.add_arc(0, 5, 0, 10, 0, 0)
    (face,) = find_profiles(s)
    assert area(face) == approx(200 + math.pi * 25)


def test_construction_lines_are_ignored() -> None:
    s = Sketch()
    polygon(s, [(0, 0), (10, 0), (10, 10), (0, 10)])
    s.add_line(-5, 5, 15, 5, construction=True)
    assert len(find_profiles(s)) == 1


def test_open_profile_is_reported_with_its_loose_ends() -> None:
    s = Sketch()
    s.add_line(0, 0, 10, 0)
    s.add_line(10, 0, 10, 10)
    with pytest.raises(ProfileError, match="Open profile") as err:
        find_profiles(s)
    assert sorted(err.value.points) == [(0, 0), (10, 10)]


def test_closed_circle_can_coexist_with_an_independent_open_line() -> None:
    s = Sketch()
    line = s.add_line(0, -5, 0, 5)
    s.add_circle(0, 0, 100)
    analysis = analyze_profiles(s)
    (face,) = analysis.faces
    assert area(face) == approx(math.pi * 100**2)
    assert analysis.open_curves == frozenset({line})
    assert analysis.open_ends == [(0, -5), (0, 5)]
    assert "1 open curve" in analysis.warning()


def test_closed_loops_and_separate_open_chain_are_classified_independently() -> None:
    s = Sketch()
    polygon(s, [(0, 0), (40, 0), (40, 20), (0, 20)])
    s.add_circle(10, 10, 5)
    first = s.add_line(7, 10, 10, 12)
    second = s.add_line(10, 12, 12, 10)
    analysis = analyze_profiles(s)
    assert len(analysis.faces) == 1
    assert area(analysis.faces[0]) == approx(800 - math.pi * 25)
    assert analysis.open_curves == frozenset({first, second})
    assert sorted(analysis.open_ends) == [(7, 10), (12, 10)]
    assert "2 open curves" in analysis.warning()


def test_open_line_crossing_a_closed_profile_is_not_silently_ignored() -> None:
    s = Sketch()
    s.add_circle(0, 0, 10)
    s.add_line(0, 0, 20, 0)
    with pytest.raises(ProfileError, match="crosses"):
        find_profiles(s)


def test_line_touching_a_circle_or_branching_a_closed_loop_is_not_ignored() -> None:
    s = Sketch()
    s.add_circle(0, 0, 10)
    s.add_line(0, 0, 10, 0)
    with pytest.raises(ProfileError, match="crosses"):
        find_profiles(s)

    s = Sketch()
    polygon(s, [(0, 0), (10, 0), (10, 10), (0, 10)])
    s.add_line(10, 10, 5, 5)
    with pytest.raises(ProfileError, match="More than two"):
        find_profiles(s)


def test_self_intersecting_profile_is_reported() -> None:
    s = Sketch()
    polygon(s, [(0, 0), (10, 10), (10, 0), (0, 10)])  # bow tie
    with pytest.raises(ProfileError, match="crosses itself") as err:
        find_profiles(s)
    assert err.value.points[0] == approx((5, 5))


def test_empty_sketch_has_no_profile() -> None:
    with pytest.raises(ProfileError, match="No profile"):
        find_profiles(Sketch())


@pytest.mark.parametrize(
    ("plane", "expected"),
    [("XY", (3, 4, 7)), ("XZ", (3, -7, 4)), ("YZ", (7, 3, 4))],
)
def test_sketch_planes(plane: str, expected: tuple[float, float, float]) -> None:
    """Sketch point (3, 4) on each base plane with a 7 mm offset."""
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCC.Core.gp import gp_Pnt
    from OCC.Core.TopoDS import topods

    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(3, 4, 0)).Vertex()
    p = BRep_Tool.Pnt(topods.Vertex(place_on_plane(vertex, BASE_PLANES[plane], 7)))
    assert (p.X(), p.Y(), p.Z()) == approx(expected)


def test_sketch_feature_wires_include_every_curve() -> None:
    from OCC.Core.TopAbs import TopAbs_EDGE
    from OCC.Core.TopExp import TopExp_Explorer

    feature = SketchFeature("f1", "Sketch1")
    polygon(feature.sketch, [(0, 0), (10, 0), (10, 10)])
    feature.sketch.add_circle(0, 0, 3, construction=True)
    explorer, count = TopExp_Explorer(feature.wires(), TopAbs_EDGE), 0
    while explorer.More():
        count += 1
        explorer.Next()
    assert count == 4
