"""Cosmetic thread strokes do not alter the modeled solid."""

import math
from dataclasses import replace

import pytest
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopExp import TopExp_Explorer

from sillycad.core.document import Document, recompute
from sillycad.core.features import Hole, Pad, Pocket, SketchFeature
from sillycad.core.geometry import Placement, volume
from sillycad.core.sketch import Sketch
from sillycad.core.threads import ThreadSpec
from sillycad.gui.thread_visual import thread_linework
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
