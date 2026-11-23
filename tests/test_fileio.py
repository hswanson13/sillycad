"""Saving and opening .sillycad files."""

import json
import math

import pytest
from pytest import approx

from sillycad.core.document import Document, recompute
from sillycad.core.features import Pad, Pocket, Revolve, SketchFeature
from sillycad.core.fileio import FORMAT_VERSION, load, save
from sillycad.core.geometry import Placement, volume
from sillycad.core.sketch import ORIGIN, Sketch
from sillycad.core.solver import solve


def sample_document() -> Document:
    """A constrained block with a pocket, a revolve and a face-plane sketch."""
    doc = Document()
    s = Sketch()
    corners = [(0, 0), (40, 0), (40, 20), (0, 20)]
    lines = [s.add_line(*corners[i], *corners[(i + 1) % 4]) for i in range(4)]
    for i in range(4):
        s.add_constraint("coincident", [s.geo[lines[i]].p2, s.geo[lines[(i + 1) % 4]].p1])
    s.add_constraint("coincident", [s.geo[lines[0]].p1, ORIGIN])
    for line, kind in zip(lines, ["horizontal", "vertical"] * 2, strict=True):
        s.add_constraint(kind, [line])
    s.add_constraint("distance", [lines[0]], 40)
    s.add_constraint("distance", [lines[1]], 20)
    assert solve(s).fully_constrained
    s.add_line(0, 10, 40, 10, construction=True)  # free, but it must survive saving too
    doc.features.append(SketchFeature(doc.new_id(), "Base sketch", "XY", 0, s))
    doc.features.append(Pad(doc.new_id(), "Block", "f1", 10, symmetric=True))

    hole = Sketch()
    hole.add_arc(20, 10, 25, 10, 15, 10)
    hole.add_line(15, 10, 25, 10)
    doc.features.append(SketchFeature(doc.new_id(), "Hole", "XY", 5, hole))
    doc.features.append(Pocket(doc.new_id(), "Half hole", "f3", through_all=True))

    post = Sketch()
    post.add_line(0, 5, 4, 5)
    post.add_line(4, 5, 4, 15)
    post.add_line(4, 15, 0, 15)
    post.add_line(0, 15, 0, 5)
    face = Placement((0.0, 0.0, 5.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
    doc.features.append(SketchFeature(doc.new_id(), "On top", "Face", 0, post, face))
    doc.features.append(Revolve(doc.new_id(), "Post", "f5", "y_axis", 270))
    return doc


def test_save_open_recompute_gives_the_same_volume(tmp_path) -> None:
    doc = sample_document()
    before = recompute(doc)
    assert not before.errors
    path = tmp_path / "part.sillycad"
    save(doc, path)
    opened = load(path)
    after = recompute(opened)
    assert not after.errors
    assert volume(after.shape) == approx(volume(before.shape))
    assert opened == doc  # every feature, sketch entity and constraint survives


def test_file_is_readable_json_with_a_version(tmp_path) -> None:
    path = tmp_path / "part.sillycad"
    save(sample_document(), path)
    data = json.loads(path.read_text())
    assert data["format_version"] == FORMAT_VERSION
    assert [f["type"] for f in data["features"]] == [
        "sketch", "pad", "sketch", "pocket", "sketch", "revolve",
    ]  # fmt: skip
    assert data["features"][0]["sketch"]["constraints"][-1]["value"] == 20  # mm, as typed
    assert data["features"][-1]["angle"] == 270  # degrees


def test_reopened_sketch_still_solves(tmp_path) -> None:
    path = tmp_path / "part.sillycad"
    save(sample_document(), path)
    sketch = load(path).features[0].sketch
    sketch.set_value(next(c for c in sketch.constraints.values() if c.value == 40).id, 50)
    result = solve(sketch)
    assert result.ok and result.dof == 4  # only the free construction line can move
    assert math.dist(*sketch.line_points("l3")) == approx(50)


def test_arc_sweep_dimension_round_trips(tmp_path) -> None:
    sketch = Sketch()
    arc = sketch.add_arc(0, 0, 10, 0, 0, 10)
    sketch.add_constraint("arc_angle", [arc], 90)
    doc = Document([SketchFeature("f1", "Arc", sketch=sketch)], 2)
    path = tmp_path / "arc.sillycad"
    save(doc, path)
    restored = load(path).sketches()[0].sketch
    assert solve(restored).ok
    assert restored.measure("arc_angle", [arc]) == approx(90)


def test_newer_or_broken_files_are_refused_politely(tmp_path) -> None:
    path = tmp_path / "x.sillycad"
    path.write_text(json.dumps({"format_version": FORMAT_VERSION + 1, "features": []}))
    with pytest.raises(ValueError, match="newer version"):
        load(path)
    path.write_text("not json")
    with pytest.raises(ValueError, match="isn't a SillyCAD file"):
        load(path)
    path.write_text(json.dumps({"format_version": 1, "next_id": 2, "features": [{"type": "pad"}]}))
    with pytest.raises(ValueError, match="damaged"):
        load(path)
