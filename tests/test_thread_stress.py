"""Exercise the full built-in thread catalog through geometry and viewport linework."""

import pytest

from sillycad.core.document import Document, recompute
from sillycad.core.features import Hole, Pad, SketchFeature
from sillycad.core.geometry import Placement, volume
from sillycad.core.sketch import Sketch
from sillycad.core.threads import THREAD_SIZES, ThreadSize, ThreadSpec
from sillycad.gui.thread_visual import thread_linework
from sillycad.sketch_math import add_rectangle


@pytest.mark.parametrize("size", THREAD_SIZES, ids=lambda size: f"{size.family}-{size.designation}")
def test_catalog_entry_builds_and_displays_a_threaded_hole(size: ThreadSize) -> None:
    diameter = size.major - size.pitch if size.major is not None else 8.0
    width = max(40.0, diameter * 3)
    sketch = Sketch()
    add_rectangle(sketch, (0, 0), (width, width))
    hole = Hole(
        "f3",
        "Hole",
        "",
        diameter=diameter,
        length=5,
        face=Placement((0, 0, 10), (0, 0, 1), (1, 0, 0)),
        center=(width / 2, width / 2),
        thread=ThreadSpec(size.family, size.designation, depth=4),
    )
    doc = Document([SketchFeature("f1", "Base", sketch=sketch), Pad("f2", "Block", "f1"), hole])
    model = recompute(doc)
    assert not model.errors
    assert 0 < volume(model.shape) < width * width * 10
    assert len(thread_linework(doc, model)) == 1
