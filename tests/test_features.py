"""Pad, Pocket, Revolve and recompute, checked by volume (headless)."""

import math

from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods
from pytest import approx

from sillycad.core.document import Document, recompute
from sillycad.core.features import Hole, Pad, Pocket, Revolve, SketchFeature, plane_from_face
from sillycad.core.geometry import BASE_PLANES, Placement, face_placement, outline_in_plane, volume
from sillycad.core.sketch import Circle, Line, Sketch
from sillycad.core.solver import solve


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


# ── Sketching on faces ──────────────────────────────────────────────


def face_facing(shape, normal: tuple[float, float, float]):  # noqa: ANN001, ANN201
    """The first flat face of ``shape`` whose outward normal is ``normal``."""
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = topods.Face(explorer.Current())
        try:
            if face_placement(face).normal == approx(normal, abs=1e-6):
                return face
        except ValueError:
            pass  # curved face
        explorer.Next()
    raise AssertionError(f"no face facing {normal}")


def test_top_face_becomes_xy_with_offset() -> None:
    top = face_facing(recompute(padded_block()).shape, (0, 0, 1))
    assert plane_from_face(top) == ("XY", 10.0, None)


def test_side_faces_match_base_planes_or_keep_their_own() -> None:
    shape = recompute(padded_block()).shape
    assert plane_from_face(face_facing(shape, (0, -1, 0))) == ("XZ", 0.0, None)  # front
    assert plane_from_face(face_facing(shape, (1, 0, 0))) == ("YZ", 40.0, None)  # right
    plane, _, face = plane_from_face(face_facing(shape, (0, 1, 0)))  # back faces the other way
    assert plane == "Face"
    assert face.x_dir == (-1, 0, 0)  # seen from behind, sketch x points to world -X, y is up


def test_pad_on_bottom_face_grows_outward() -> None:
    doc = padded_block()
    plane, offset, face = plane_from_face(face_facing(recompute(doc).shape, (0, 0, -1)))
    assert plane == "Face" and face.normal == (0, 0, -1)
    # On the bottom face, sketch y points to world -Y, so the block is at negative sketch y.
    sketch = SketchFeature(doc.new_id(), "Bottom", plane, offset, rect(0, -10, 10, 0), face)
    doc.features.append(sketch)
    add(doc, Pad, sketch.id, length=5)
    model = recompute(doc)
    assert not model.errors
    assert volume(model.shape) == approx(8000 + 500)
    assert bounds(model.shape)[2] == approx(-5)  # grew downward, out of the material


def test_large_face_circle_with_midpoint_guide_extrudes_without_losing_constraints() -> None:
    doc = padded_block()
    doc.features.append(
        Hole(
            doc.new_id(),
            "Hole",
            "",
            diameter=6,
            through_all=True,
            face=Placement((0, 0, 10), (0, 0, 1), (1, 0, 0)),
            center=(15, 15),
        )
    )
    before = volume(recompute(doc).shape)
    sketch = Sketch()
    line = sketch.add_line(20, 0, 20, 10)
    circle = sketch.add_circle(20, 5, 100)
    curve = sketch.geo[circle]
    assert isinstance(curve, Circle)
    midpoint = sketch.add_constraint("midpoint", [curve.center, line])
    radius = sketch.add_constraint("radius", [circle], 100)
    assert solve(sketch).ok
    sketch_id = add_sketch(doc, sketch, "XZ")
    add(doc, Pad, sketch_id, length=5)
    model = recompute(doc)
    assert not model.errors
    assert volume(model.shape) == approx(before + math.pi * 100**2 * 5)
    assert sketch.constraints[midpoint].refs == [curve.center, line]
    assert sketch.constraints[radius].value == 100
    assert isinstance(sketch.geo[line], Line) and not sketch.geo[line].construction
    sketch.set_value(radius, 120)
    assert solve(sketch).ok
    a, b = sketch.line_points(line)
    assert sketch.point(curve.center) == approx(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    changed = recompute(doc)
    assert not changed.errors
    assert volume(changed.shape) == approx(before + math.pi * 120**2 * 5)


def test_pad_on_slanted_face() -> None:
    doc = Document()
    triangle = Sketch()
    for a, b in [((0, 0), (20, 0)), ((20, 0), (0, 20)), ((0, 20), (0, 0))]:
        triangle.add_line(*a, *b)
    add(doc, Pad, add_sketch(doc, triangle), length=10)  # 2000 mm³ wedge
    slanted = face_facing(recompute(doc).shape, (math.sqrt(0.5), math.sqrt(0.5), 0))
    plane, offset, face = plane_from_face(slanted)
    assert plane == "Face"
    # Sketch origin is the world origin projected onto the face: world (10, 10, 0).
    # Sketch y is world up, so the face's middle (world z = 5) is at sketch (0, 5).
    sketch = SketchFeature(doc.new_id(), "OnSlope", plane, offset, rect(-5, 2, 5, 8), face)
    doc.features.append(sketch)
    add(doc, Pad, sketch.id, length=3)
    model = recompute(doc)
    assert not model.errors
    assert volume(model.shape) == approx(2000 + 60 * 3)


def test_outline_of_the_face_being_sketched_on() -> None:
    shape = recompute(padded_block()).shape
    lines = outline_in_plane(shape, BASE_PLANES["XY"], 10)  # the top face
    assert len(lines) == 4
    corners = {(round(x, 6), round(y, 6)) for line in lines for x, y in (line[0], line[-1])}
    assert corners == {(0, 0), (40, 0), (40, 20), (0, 20)}
    assert outline_in_plane(shape, BASE_PLANES["XY"], 5) == []  # nothing lies at mid-height
