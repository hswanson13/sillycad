"""Hole geometry, cosmetic thread validation and file compatibility."""

import math
from dataclasses import replace

import pytest

from sillycad.core.document import Document, recompute
from sillycad.core.features import Hole, Pad, Pocket, SketchFeature
from sillycad.core.fileio import from_dict, to_dict
from sillycad.core.geometry import Placement, volume
from sillycad.core.sketch import Sketch
from sillycad.core.threads import ThreadSpec, resolve_thread


def block() -> Document:
    sketch = Sketch()
    corners = ((0, 0), (40, 0), (40, 20), (0, 20))
    for i, a in enumerate(corners):
        sketch.add_line(*a, *corners[(i + 1) % 4])
    return Document([SketchFeature("f1", "Base", sketch=sketch), Pad("f2", "Block", "f1")], 3)


def hole_document(**kwargs: object) -> tuple[Document, Hole]:
    doc = block()
    sketch = Sketch()
    point = sketch.add_point(10, 10)
    doc.features.append(SketchFeature("f3", "Centers", "XY", 10, sketch))
    hole = Hole("f4", "Hole", "f3", point, **kwargs)
    doc.features.append(hole)
    doc.next_id = 5
    return doc, hole


@pytest.mark.parametrize(
    ("params", "removed"),
    [
        ({"diameter": 6, "length": 5}, math.pi * 9 * 5),
        ({"diameter": 6, "through_all": True}, math.pi * 9 * 10),
        ({"diameter": 6, "length": 5, "style": "counterbore"}, math.pi * (9 * 5 + (25 - 9) * 2)),
        ({"diameter": 6, "length": 5, "style": "spotface"}, math.pi * (9 * 5 + (25 - 9) * 2)),
        (
            {"diameter": 6, "length": 5, "style": "countersink"},
            math.pi * (9 * 5 + 2 * (25 + 15 + 9) / 3 - 9 * 2),
        ),
    ],
)
def test_hole_volume(params: dict[str, object], removed: float) -> None:
    doc, _ = hole_document(**params)
    result = recompute(doc)
    assert not result.errors
    assert volume(result.shape) == pytest.approx(8000 - removed)


def test_tapered_hole_is_really_tapered() -> None:
    spec = ThreadSpec("NPT", "1/8-27 NPT", depth=4)
    doc, _ = hole_document(diameter=8, length=5, thread=spec)
    result = recompute(doc)
    r0, r1 = 4, (8 - 4 / 16) / 2
    removed = math.pi * (4 * (r0 * r0 + r0 * r1 + r1 * r1) / 3 + r1 * r1)
    assert not result.errors
    assert volume(result.shape) == pytest.approx(8000 - removed)


def test_invalid_holes_keep_the_last_valid_body() -> None:
    doc, hole = hole_document()
    for changes, text in (
        ({"diameter": -1}, "diameter"),
        ({"point_id": "missing"}, "center"),
        ({"reversed": True}, "does not intersect"),
        ({"style": "counterbore", "head_depth": 6}, "Head depth"),
        ({"style": "countersink", "countersink_angle": 180}, "angle"),
        ({"thread": ThreadSpec("NPT", "1/8-27 NPT")}, "explicit thread depth"),
        ({"clearance_size": "M6", "thread": ThreadSpec("ISO metric", "M6 x 1")}, "clearance"),
    ):
        doc.replace(replace(hole, **changes))
        model = recompute(doc)
        assert text in model.errors[hole.id]
        assert volume(model.shape) == pytest.approx(8000)


def test_circle_pocket_threads_and_rejections() -> None:
    doc = block()
    sketch = Sketch()
    sketch.add_circle(10, 10, 2.5)
    doc.features.append(SketchFeature("f3", "Circle", "XY", 10, sketch))
    pocket = Pocket("f4", "Cut", "f3", length=5, thread=ThreadSpec("ISO metric", "M6 x 1"))
    doc.features.append(pocket)
    assert not recompute(doc).errors
    assert from_dict(to_dict(doc)) == doc
    doc.replace(replace(pocket, thread=ThreadSpec("NPT", "1/8-27 NPT", depth=3)))
    assert "tapered" in recompute(doc).errors["f4"]
    doc.replace(replace(pocket, thread=ThreadSpec("ISO metric", "M6 x 1", depth=6)))
    assert "depth" in recompute(doc).errors["f4"]
    sketch.add_circle(20, 10, 2.5)
    doc.replace(pocket)
    assert "one circular profile" in recompute(doc).errors["f4"]


@pytest.mark.parametrize("style", ["counterbore", "spotface", "countersink"])
def test_thread_depth_starts_after_recess(style: str) -> None:
    thread = ThreadSpec("ISO metric", "M6 x 1", depth=3)
    doc, hole = hole_document(diameter=5, length=5, style=style, head_diameter=9, thread=thread)
    assert not recompute(doc).errors
    doc.replace(replace(hole, thread=replace(thread, depth=3.1)))
    assert "Thread depth" in recompute(doc).errors[hole.id]


def test_thread_catalog_and_invalid_specifications() -> None:
    metric = resolve_thread(ThreadSpec("ISO metric", "M6 x 1", "6H"))
    assert metric.major == 6 and metric.pitch == 1
    assert metric.basic_minor == pytest.approx(4.9174682453)
    assert resolve_thread(ThreadSpec("UNC", "1/4-20 UNC")).pitch == pytest.approx(1.27)
    assert resolve_thread(ThreadSpec("BSPP", "G 1/2")).major == pytest.approx(20.955)
    assert resolve_thread(ThreadSpec("BSPT", "Rc 1/2")).taper == pytest.approx(1 / 16)
    assert resolve_thread(ThreadSpec("Tr", "Tr 12 x 3")).basic_minor == 9
    assert resolve_thread(ThreadSpec("ACME", "1/2-10 ACME")).basic_minor == pytest.approx(10.16)
    with pytest.raises(ValueError, match="Unsupported"):
        resolve_thread(ThreadSpec("ISO metric", "M6 x 3"))
    with pytest.raises(ValueError, match="positive custom"):
        resolve_thread(ThreadSpec("Custom", "Test"))
    custom = resolve_thread(
        ThreadSpec("Custom", "Special", custom_major=10, custom_pitch=2, custom_taper=0.01)
    )
    assert custom.taper == 0.01


def test_version_one_loads_and_hole_thread_round_trips() -> None:
    old = to_dict(block())
    old["format_version"] = 1
    assert from_dict(old) == block()
    old_with_pocket = to_dict(block())
    old_with_pocket["features"].append(
        {
            "type": "pocket",
            "id": "f3",
            "name": "Cut",
            "sketch_id": "f1",
            "length": 5,
            "through_all": False,
            "reversed": False,
        }
    )
    old_with_pocket["format_version"] = 1
    assert from_dict(old_with_pocket).features[-1].thread is None
    doc, _ = hole_document(thread=ThreadSpec("ISO metric", "M6 x 1", "6H", True, 4))
    encoded = to_dict(doc)
    assert encoded["format_version"] == 4
    restored = from_dict(encoded)
    assert restored == doc
    assert not recompute(restored).errors
    encoded["features"][-1]["thread"]["extra"] = 1
    with pytest.raises(ValueError, match="unknown"):
        from_dict(encoded)


def test_clearance_diameter_is_parametric() -> None:
    doc, hole = hole_document(clearance_size="M6", clearance_fit="medium", diameter=1)
    result = recompute(doc)
    assert not result.errors
    assert volume(result.shape) == pytest.approx(8000 - math.pi * 3.3**2 * 5)
    doc.replace(replace(hole, clearance_fit="coarse"))
    assert volume(recompute(doc).shape) == pytest.approx(8000 - math.pi * 3.5**2 * 5)


def test_hole_on_bottom_face_uses_the_sketch_orientation() -> None:
    doc = block()
    sketch = Sketch()
    point = sketch.add_point(10, -10)
    face = Placement((0, 0, 0), (0, 0, -1), (1, 0, 0))
    doc.features.append(SketchFeature("f3", "Bottom", "Face", 0, sketch, face))
    doc.features.append(Hole("f4", "Hole", "f3", point, diameter=4, length=3))
    result = recompute(doc)
    assert not result.errors
    assert volume(result.shape) == pytest.approx(8000 - math.pi * 2**2 * 3)
    doc.delete("f3")
    assert doc.find("f4") is None


def test_direct_face_hole_and_sketch_coordinate_hole_round_trip() -> None:
    doc = block()
    face = Placement((0, 0, 10), (0, 0, 1), (1, 0, 0))
    hole = Hole("f3", "Hole", "", diameter=4, length=3, face=face, center=(10, 10))
    doc.features.append(hole)
    doc.next_id = 4
    result = recompute(doc)
    assert not result.errors
    assert volume(result.shape) == pytest.approx(8000 - math.pi * 2**2 * 3)
    restored = from_dict(to_dict(doc))
    assert restored == doc
    assert not recompute(restored).errors

    sketch = SketchFeature("f4", "Top", "XY", 10)
    doc.features.insert(2, sketch)
    doc.replace(replace(hole, sketch_id=sketch.id, face=None, center=(20, 10)))
    assert not recompute(doc).errors
    assert volume(recompute(doc).shape) == pytest.approx(8000 - math.pi * 2**2 * 3)
    assert from_dict(to_dict(doc)) == doc


def test_version_two_sketch_hole_still_loads() -> None:
    doc, hole = hole_document(thread=ThreadSpec("ISO metric", "M6 x 1"))
    data = to_dict(doc)
    data["format_version"] = 2
    data["features"][-1].pop("face")
    data["features"][-1].pop("center")
    assert from_dict(data) == doc
    assert from_dict(data).find(hole.id).point_id == hole.point_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("center", [1]),
        ("center", [1, 2, 3]),
        ("center", [1, "bad"]),
        ("center", [1, float("nan")]),
        ("face", {"origin": [0, 0, 10], "normal": [0, 0, 1]}),
        ("face", {"origin": [0, 0], "normal": [0, 0, 1], "x_dir": [1, 0, 0]}),
        ("face", {"origin": [0, 0, 10], "normal": [0, 0, 0], "x_dir": [1, 0, 0]}),
        ("face", {"origin": [0, 0, 10], "normal": [0, 0, 1], "x_dir": [0, 0, 1]}),
    ],
)
def test_malformed_direct_hole_placement_is_rejected(field: str, value: object) -> None:
    doc = block()
    face = Placement((0, 0, 10), (0, 0, 1), (1, 0, 0))
    doc.features.append(Hole("f3", "Hole", "", face=face, center=(10, 10)))
    data = to_dict(doc)
    data["features"][-1][field] = value
    with pytest.raises(ValueError, match="damaged"):
        from_dict(data)


@pytest.mark.parametrize(
    ("face", "center"),
    [(None, None), (None, (10, 10)), (Placement((0, 0, 10), (0, 0, 1), (1, 0, 0)), None)],
)
def test_incomplete_face_placement_reports_error(
    face: Placement | None, center: tuple[float, float] | None
) -> None:
    doc = block()
    doc.features.append(Hole("f3", "Hole", "", face=face, center=center))
    result = recompute(doc)
    assert "Click a planar face" in result.errors["f3"]
    assert volume(result.shape) == pytest.approx(8000)
