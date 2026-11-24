"""Cosmetic thread strokes do not alter the modeled solid."""

import math
from dataclasses import replace

import pytest
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Edge, TopoDS_Shape, topods

from sillycad.core.document import Document, recompute
from sillycad.core.features import Feature, Hole, Pad, Pocket, SketchFeature
from sillycad.core.fileio import from_dict, to_dict
from sillycad.core.geometry import Placement, volume
from sillycad.core.sketch import Circle, Sketch
from sillycad.core.threads import THREAD_FAMILIES, ThreadSpec, thread_sizes
from sillycad.gui.thread_visual import _MAX_FEATURE_TURNS, _SEGMENTS_PER_TURN, thread_linework
from sillycad.sketch_math import add_rectangle


def threaded_block() -> Document:
    base = Sketch()
    add_rectangle(base, (0, 0), (40, 20))
    hole = Hole(
        "f3",
        "Hole",
        "",
        diameter=5,
        length=5,
        face=Placement((0, 0, 10), (0, 0, 1), (1, 0, 0)),
        center=(10, 10),
        thread=ThreadSpec("ISO metric", "M6 x 1"),
    )
    return Document([SketchFeature("f1", "Base", sketch=base), Pad("f2", "Block", "f1"), hole])


def edges_of(shape: TopoDS_Shape) -> list[TopoDS_Edge]:
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    edges = []
    while explorer.More():
        edges.append(topods.Edge(explorer.Current()))
        explorer.Next()
    return edges


def test_thread_strokes_follow_hole_and_do_not_change_volume() -> None:
    doc = threaded_block()
    model = recompute(doc)
    assert not model.errors
    before = volume(model.shape)
    strokes = thread_linework(doc, model)
    assert len(strokes) == 1
    edges = TopExp_Explorer(strokes[0], TopAbs_EDGE)
    assert edges.More()
    assert volume(model.shape) == pytest.approx(before)
    hole = doc.features[-1]
    doc.replace(replace(hole, thread=None))
    assert thread_linework(doc, recompute(doc)) == []
    assert volume(recompute(doc).shape) == pytest.approx(8000 - math.pi * 2.5**2 * 5)


def test_threaded_circular_cut_has_strokes_and_failed_hole_does_not() -> None:
    doc = threaded_block()
    doc.features.pop()
    circle = Sketch()
    circle.add_circle(10, 10, 2.5)
    doc.features.extend(
        [
            SketchFeature("f3", "Circle", "XY", 10, circle),
            Pocket("f4", "Cut", "f3", thread=ThreadSpec("ISO metric", "M6 x 1")),
        ]
    )
    assert len(thread_linework(doc, recompute(doc))) == 1
    bad = Hole(
        "f5",
        "Bad",
        "",
        reversed=True,
        diameter=5,
        length=5,
        face=Placement((0, 0, 10), (0, 0, 1), (1, 0, 0)),
        center=(30, 10),
        thread=ThreadSpec("ISO metric", "M6 x 1"),
    )
    doc.features.append(bad)
    model = recompute(doc)
    assert "f5" in model.errors
    assert len(thread_linework(doc, model)) == 1


def test_threaded_circle_cut_accepts_an_independent_open_guide() -> None:
    doc = threaded_block()
    doc.features.pop()
    sketch = Sketch()
    line = sketch.add_line(9, 10, 11, 10)
    circle = sketch.add_circle(10, 10, 2.5)
    curve = sketch.geo[circle]
    assert isinstance(curve, Circle)
    sketch.add_constraint("midpoint", [curve.center, line])
    doc.features.extend(
        [
            SketchFeature("f3", "Circle", "XY", 10, sketch),
            Pocket("f4", "Cut", "f3", thread=ThreadSpec("ISO metric", "M6 x 1")),
        ]
    )
    model = recompute(doc)
    assert not model.errors
    assert len(thread_linework(doc, model)) == 1


@pytest.mark.parametrize("pitch", [1.0, 0.001])
def test_long_thread_strokes_are_bounded_and_cover_both_surviving_ends(pitch: float) -> None:
    doc = threaded_block()
    doc.replace(replace(doc.features[1], length=500))
    hole = doc.features[2]
    doc.replace(
        replace(
            hole,
            length=1000,
            face=Placement((0, 0, 500), (0, 0, 1), (1, 0, 0)),
            thread=ThreadSpec("Custom", "Test", custom_major=5, custom_pitch=pitch),
        )
    )
    model = recompute(doc)
    assert not model.errors
    edges = edges_of(thread_linework(doc, model)[0])
    assert 0 < len(edges) <= _MAX_FEATURE_TURNS * _SEGMENTS_PER_TURN
    depths = []
    for edge in edges:
        curve = BRepAdaptor_Curve(edge)
        p1, p2 = curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())
        depths.extend((p1.Z(), p2.Z()))
        assert abs(p1.Z() - p2.Z()) <= pitch / 20
    assert min(depths) < 1 and max(depths) > 499


def test_many_long_threads_have_a_shared_linework_budget() -> None:
    base = Sketch()
    add_rectangle(base, (0, 0), (240, 40))
    features: list[Feature] = [
        SketchFeature("f1", "Base", sketch=base),
        Pad("f2", "Block", "f1", length=500),
    ]
    for index in range(12):
        features.append(
            Hole(
                f"h{index}",
                "Hole",
                "",
                diameter=5,
                length=500,
                face=Placement((0, 0, 500), (0, 0, 1), (1, 0, 0)),
                center=(10 + 17 * index, 20),
                thread=ThreadSpec("ISO metric", "M6 x 1"),
            )
        )
    doc = Document(features)
    model = recompute(doc)
    assert not model.errors
    strokes = thread_linework(doc, model)
    assert len(strokes) == 12
    assert sum(len(edges_of(shape)) for shape in strokes) <= 2400


def test_excess_thread_displays_are_bounded_and_reported(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    doc = threaded_block()
    hole = doc.features[-1]
    assert isinstance(hole, Hole)
    doc.features.extend(
        [
            replace(hole, id="f4", center=(20, 10)),
            replace(hole, id="f5", center=(30, 10)),
        ]
    )
    model = recompute(doc)
    assert not model.errors
    monkeypatch.setattr("sillycad.gui.thread_visual._MAX_TOTAL_SEGMENTS", 2 * _SEGMENTS_PER_TURN)
    strokes = thread_linework(doc, model)
    assert len(strokes) == 2
    assert all(len(edges_of(shape)) == _SEGMENTS_PER_TURN for shape in strokes)
    assert "1 were omitted" in caplog.text


def test_strokes_remain_on_a_bore_after_both_ends_are_cut_away() -> None:
    doc = threaded_block()
    doc.replace(replace(doc.features[1], length=500))
    top = Placement((0, 0, 500), (0, 0, 1), (1, 0, 0))
    bottom = Placement((0, 0, 0), (0, 0, -1), (1, 0, 0))
    doc.replace(replace(doc.features[2], face=top, length=500))
    doc.features.extend(
        [
            Hole("f4", "Top cut", "", diameter=10, length=25, face=top, center=(10, 10)),
            Hole("f5", "Bottom cut", "", diameter=10, length=25, face=bottom, center=(10, -10)),
        ]
    )
    model = recompute(doc)
    assert not model.errors
    strokes = thread_linework(doc, model)
    assert len(strokes) == 1
    depths = []
    for edge in edges_of(strokes[0]):
        curve = BRepAdaptor_Curve(edge)
        depths.extend(
            (curve.Value(curve.FirstParameter()).Z(), curve.Value(curve.LastParameter()).Z())
        )
    assert depths and min(depths) >= 25 and max(depths) <= 475


@pytest.mark.parametrize("family", [family for family in THREAD_FAMILIES if family != "Custom"])
def test_every_catalog_family_can_render_a_valid_thread(family: str) -> None:
    size = thread_sizes(family)[0]
    diameter = size.major - size.pitch if size.major is not None else 8
    doc = threaded_block()
    hole = doc.features[2]
    doc.replace(
        replace(
            hole,
            diameter=diameter,
            length=5,
            thread=ThreadSpec(family, size.designation, depth=4),
        )
    )
    model = recompute(doc)
    assert not model.errors
    assert len(thread_linework(doc, model)) == 1


@pytest.mark.parametrize("left_hand", [False, True])
def test_stroke_handedness_follows_thread_metadata(left_hand: bool) -> None:
    doc = threaded_block()
    hole = doc.features[2]
    assert isinstance(hole, Hole) and hole.thread is not None
    doc.replace(replace(hole, thread=replace(hole.thread, left_hand=left_hand)))
    edge = edges_of(thread_linework(doc, recompute(doc))[0])[0]
    curve = BRepAdaptor_Curve(edge)
    start, end = curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())
    angle = math.atan2(end.Y() - 10, end.X() - 10) - math.atan2(start.Y() - 10, start.X() - 10)
    angle = math.atan2(math.sin(angle), math.cos(angle))
    assert (angle * (end.Z() - start.Z()) > 0) != left_hand


@pytest.mark.parametrize("style", ["simple", "counterbore", "spotface", "countersink"])
@pytest.mark.parametrize("through_all", [False, True])
@pytest.mark.parametrize("reversed", [False, True])
@pytest.mark.parametrize("left_hand", [False, True])
def test_threaded_hole_styles_extents_directions_and_round_trips(
    style: str, through_all: bool, reversed: bool, left_hand: bool
) -> None:
    doc = threaded_block()
    hole = doc.features[-1]
    assert isinstance(hole, Hole)
    doc.replace(
        replace(
            hole,
            style=style,
            head_diameter=9,
            head_depth=2,
            length=8,
            through_all=through_all,
            reversed=reversed,
            face=Placement((0, 0, 0 if reversed else 10), (0, 0, 1), (1, 0, 0)),
            thread=ThreadSpec("ISO metric", "M6 x 1", left_hand=left_hand, depth=4),
        )
    )
    restored = from_dict(to_dict(doc))
    assert restored == doc
    model = recompute(restored)
    assert not model.errors
    assert 0 < volume(model.shape) < 8000
    strokes = thread_linework(restored, model)
    assert len(strokes) == 1
    assert 0 < len(edges_of(strokes[0])) <= 4 * _SEGMENTS_PER_TURN  # 4 mm of M6 x 1
