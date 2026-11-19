"""STL export and basic geometry checks."""

import pytest

from sillycad.core.export import export_stl
from sillycad.core.geometry import make_box, volume


def test_box_volume() -> None:
    assert volume(make_box(40, 20, 10)) == pytest.approx(8000)


def test_stl_export_box(tmp_path) -> None:
    path = tmp_path / "box.stl"
    count = export_stl(make_box(40, 20, 10), path)
    assert 12 <= count < 1000  # a box needs at least 2 triangles per face
    assert path.stat().st_size == 84 + 50 * count  # binary STL: header + 50 bytes/triangle
