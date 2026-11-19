"""Pad, Pocket, Revolve and recompute, checked by volume (headless)."""

import math

from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from pytest import approx

from sillycad.core.document import Document, recompute
from sillycad.core.features import Pad, Pocket, Revolve, SketchFeature
from sillycad.core.geometry import volume
from sillycad.core.sketch import Sketch


def rect(x0: float, y0: float, x1: float, y1: float) -> Sketch:
    s = Sketch()
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i, a in enumerate(corners):
        s.add_line(*a, *corners[(i + 1) % 4])
    return s


def add_sketch(doc: Document, sketch: Sketch, plane: str = "XY", offset: float = 0.0) -> str:
    fid = doc.new_id()
    doc.features.append(SketchFeature(fid, doc.new_name("Sketch"), plane, offset, sketch))
    return fid


def add(doc: Document, cls: type, sketch_id: str, **params: object) -> str:
    fid = doc.new_id()
    doc.features.append(cls(fid, doc.new_name(cls.__name__), sketch_id, **params))
    return fid


def bounds(shape) -> list[float]:  # noqa: ANN001
    box = Bnd_Box()
    brepbndlib.Add(shape, box)
    return [round(v, 6) for v in box.Get()]


def padded_block() -> Document:
    """40 x 20 x 10 block on XY."""
    doc = Document()
    add(doc, Pad, add_sketch(doc, rect(0, 0, 40, 20)), length=10)
    return doc


def test_pad_rectangle_volume() -> None:
    model = recompute(padded_block())
    assert not model.errors
    assert volume(model.shape) == approx(8000)


def test_pad_reversed_and_symmetric() -> None:
    doc = padded_block()
    doc.features[1].reversed = True
    assert bounds(recompute(doc).shape)[2::3] == approx([-10, 0])  # z min, z max
    doc.features[1].reversed = False
    doc.features[1].symmetric = True
    shape = recompute(doc).shape
    assert bounds(shape)[2::3] == approx([-5, 5])
    assert volume(shape) == approx(8000)


def test_pocket_removes_expected_volume() -> None:
    doc = padded_block()
    hole = Sketch()
    hole.add_circle(10, 10, 5)
    pocket = add(doc, Pocket, add_sketch(doc, hole, "XY", 10), length=4)
    model = recompute(doc)
    assert not model.errors
    assert volume(model.shape) == approx(8000 - math.pi * 25 * 4)
    doc.find(pocket).through_all = True
    assert volume(recompute(doc).shape) == approx(8000 - math.pi * 25 * 10)


def test_revolve_rectangle_gives_annulus_and_cylinder() -> None:
    doc = Document()  # XZ plane: sketch y = global Z, so the sketch Y axis is the Z axis
    add(doc, Revolve, add_sketch(doc, rect(10, 0, 20, 30), "XZ"), axis="y_axis")
    assert volume(recompute(doc).shape) == approx(math.pi * (20**2 - 10**2) * 30)

    doc = Document()
    add(doc, Revolve, add_sketch(doc, rect(0, 0, 10, 30), "XZ"), axis="y_axis", angle=180)
    assert volume(recompute(doc).shape) == approx(math.pi * 10**2 * 30 / 2)


def test_revolve_around_construction_line() -> None:
    s = rect(0, 0, 10, 10)
    axis = s.add_line(-5, 0, -5, 1, construction=True)  # x = -5, so radii 5..15
    doc = Document()
    add(doc, Revolve, add_sketch(doc, s), axis=axis)
    assert volume(recompute(doc).shape) == approx(math.pi * (15**2 - 5**2) * 10)


def test_revolve_axis_crossing_profile_is_rejected() -> None:
    doc = Document()
    rev = add(doc, Revolve, add_sketch(doc, rect(-5, 0, 5, 10)), axis="y_axis")
    model = recompute(doc)
    assert "axis crosses the profile" in model.errors[rev]
    assert model.shape is None


def test_first_solid_must_be_additive() -> None:
    doc = Document()
    pocket = add(doc, Pocket, add_sketch(doc, rect(0, 0, 5, 5)), length=3)
    model = recompute(doc)
    assert "first solid" in model.errors[pocket]
    assert model.shape is None


def test_failed_feature_keeps_last_good_shape() -> None:
    doc = padded_block()
    open_sketch = Sketch()
    open_sketch.add_line(0, 0, 10, 0)
    bad = add(doc, Pocket, add_sketch(doc, open_sketch, "XY", 10), length=2)
    model = recompute(doc)
    assert "Open profile" in model.errors[bad]
    assert volume(model.shape) == approx(8000)


def test_editing_an_earlier_feature_recomputes_the_rest() -> None:
    doc = padded_block()
    hole = Sketch()
    hole.add_circle(10, 10, 5)
    add(doc, Pocket, add_sketch(doc, hole, "XY", 10), through_all=True)
    doc.features[1].length = 20  # make the first pad taller...
    model = recompute(doc)
    assert not model.errors
    # ...the pocket is replayed on the new block: it cuts down from its plane at z = 10
    assert volume(model.shape) == approx(16000 - math.pi * 25 * 10)


def test_separate_pieces_are_rejected() -> None:
    doc = padded_block()
    far = add(doc, Pad, add_sketch(doc, rect(100, 100, 110, 110)), length=5)
    model = recompute(doc)
    assert "separate pieces" in model.errors[far]
    assert volume(model.shape) == approx(8000)


def test_delete_sketch_also_deletes_features_built_from_it() -> None:
    doc = padded_block()
    sketch_id = doc.features[0].id
    doc.delete(sketch_id)
    assert doc.features == []
    assert recompute(doc).shape is None
