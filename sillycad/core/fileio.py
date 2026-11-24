"""Native file format: the feature list as JSON (``.sillycad``).

Units in the file are millimetres and degrees, like everywhere else. Every
object has a ``type`` so the file reads well and loads without guessing.
The 3D shape is never saved; it's recomputed from the features on open.
"""

import json
import math
import os
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from sillycad.core.document import Document
from sillycad.core.features import Feature, Hole, Pad, Pocket, Revolve, SketchFeature
from sillycad.core.geometry import XYZ, Placement
from sillycad.core.sketch import XY, Arc, Circle, Constraint, Line, Point, Sketch
from sillycad.core.threads import ThreadSpec

FORMAT_VERSION = 4
SUFFIX = ".sillycad"

_FEATURES: dict[str, type] = {
    "sketch": SketchFeature,
    "pad": Pad,
    "pocket": Pocket,
    "revolve": Revolve,
    "hole": Hole,
}
_GEOMETRY: dict[str, type] = {"point": Point, "line": Line, "circle": Circle, "arc": Arc}


def save(doc: Document, path: str | Path) -> None:
    """Write ``doc`` to ``path``. Writes a temporary file first, so a crash can't corrupt it."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(to_dict(doc), indent=1), encoding="utf-8")
    os.replace(temporary, path)


def load(path: str | Path) -> Document:
    """Read a document. Raises ValueError with a user-facing message if it can't."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Couldn't read the file: {exc}") from None
    except json.JSONDecodeError:
        raise ValueError("That isn't a SillyCAD file (it's not valid JSON).") from None
    return from_dict(data)


def to_dict(doc: Document) -> dict[str, Any]:
    """The document as plain JSON-ready data."""
    return {
        "format_version": FORMAT_VERSION,
        "next_id": doc.next_id,
        "features": [_feature_to_dict(f) for f in doc.features],
    }


def from_dict(data: Any) -> Document:
    """Build a document from ``to_dict`` data. Raises ValueError if it's not valid."""
    if not isinstance(data, dict) or "format_version" not in data:
        raise ValueError("That isn't a SillyCAD file.")
    if data["format_version"] > FORMAT_VERSION:
        raise ValueError(
            "This file was made by a newer version of SillyCAD "
            f"(format {data['format_version']}; this version reads up to {FORMAT_VERSION})."
        )
    try:
        features = [_feature_from_dict(f) for f in data["features"]]
        return Document(features, data["next_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"The file is damaged and can't be opened ({exc!r}).") from None


def _feature_to_dict(f: Feature) -> dict[str, Any]:
    kind = next(k for k, cls in _FEATURES.items() if isinstance(f, cls))
    data = {"type": kind, **asdict(f)}
    if isinstance(f, SketchFeature):
        data["sketch"] = _sketch_to_dict(f.sketch)
    return data


def _feature_from_dict(data: dict[str, Any]) -> Feature:
    data = dict(data)
    cls = _FEATURES[data.pop("type")]
    if cls is SketchFeature:
        data["sketch"] = _sketch_from_dict(data["sketch"])
        if data.get("face") is not None:
            data["face"] = Placement(**{k: tuple(v) for k, v in data["face"].items()})
    if cls in (Pocket, Hole) and data.get("thread") is not None:
        data["thread"] = ThreadSpec(**_only_fields(ThreadSpec, data["thread"]))
    if cls is Hole:
        if data.get("face") is not None:
            face = data["face"]
            if not isinstance(face, dict) or set(face) != {"origin", "normal", "x_dir"}:
                raise ValueError("invalid hole face plane")
            origin = _xyz(face["origin"])
            normal = _xyz(face["normal"])
            x_dir = _xyz(face["x_dir"])
            normal_length = math.hypot(*normal)
            x_length = math.hypot(*x_dir)
            if normal_length < 1e-12 or x_length < 1e-12:
                raise ValueError("invalid hole face directions")
            n = tuple(v / normal_length for v in normal)
            x = tuple(v / x_length for v in x_dir)
            if (
                math.hypot(
                    n[1] * x[2] - n[2] * x[1],
                    n[2] * x[0] - n[0] * x[2],
                    n[0] * x[1] - n[1] * x[0],
                )
                < 1e-12
            ):
                raise ValueError("invalid hole face directions")
            data["face"] = Placement(origin, normal, x_dir)
        if data.get("center") is not None:
            data["center"] = _xy(data["center"])
    return cls(**_only_fields(cls, data))


def _vector(value: Any, length: int) -> tuple[float, ...]:
    if (
        not isinstance(value, list | tuple)
        or len(value) != length
        or any(isinstance(v, bool) or not isinstance(v, int | float) for v in value)
        or not all(math.isfinite(v) for v in value)
    ):
        raise ValueError("invalid hole placement coordinates")
    return tuple(value)


def _xy(value: Any) -> XY:
    vector = _vector(value, 2)
    return vector[0], vector[1]


def _xyz(value: Any) -> XYZ:
    vector = _vector(value, 3)
    return vector[0], vector[1], vector[2]


def _sketch_to_dict(s: Sketch) -> dict[str, Any]:
    geometry = []
    for g in s.geo.values():
        kind = next(k for k, cls in _GEOMETRY.items() if isinstance(g, cls))
        geometry.append({"type": kind, **asdict(g)})
    return {
        "next_id": s.next_id,
        "geometry": geometry,
        "constraints": [asdict(c) for c in s.constraints.values()],
    }


def _sketch_from_dict(data: dict[str, Any]) -> Sketch:
    sketch = Sketch(next_id=data["next_id"])
    for g in data["geometry"]:
        g = dict(g)
        cls = _GEOMETRY[g.pop("type")]
        item = cls(**_only_fields(cls, g))
        sketch.geo[item.id] = item
    for c in data["constraints"]:
        constraint = Constraint(**_only_fields(Constraint, c))
        sketch.constraints[constraint.id] = constraint
    return sketch


def _only_fields(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """Raise on unknown keys (a damaged file), rather than silently dropping data."""
    unknown = set(data) - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"unknown {cls.__name__} fields: {sorted(unknown)}")
    return data
