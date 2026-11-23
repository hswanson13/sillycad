"""The document: an ordered list of features, and recompute.

The 3D shape is never edited directly. ``recompute`` replays the feature list
from scratch every time, so editing an earlier feature updates everything
after it.
"""

import logging
import math
from dataclasses import dataclass, field

from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Core.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCC.Core.TopAbs import TopAbs_SOLID
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Shape

from sillycad.core.features import (
    Feature,
    FeatureError,
    Hole,
    Pad,
    Pocket,
    Revolve,
    SketchFeature,
    hole_shape,
    pad_shape,
    pocket_shape,
    revolve_shape,
    validate_thread,
)
from sillycad.core.geometry import plane_axes, volume
from sillycad.core.profiles import ProfileError
from sillycad.core.sketch import Arc, Circle, Line

log = logging.getLogger(__name__)


@dataclass
class Document:
    """An ordered feature history."""

    features: list[Feature] = field(default_factory=list)
    next_id: int = 1

    def new_id(self) -> str:
        """A fresh feature ID like ``f7``. IDs are never reused."""
        new = f"f{self.next_id}"
        self.next_id += 1
        return new

    def new_name(self, kind: str) -> str:
        """The next free name like ``Pad2``."""
        names = {f.name for f in self.features}
        n = 1
        while f"{kind}{n}" in names:
            n += 1
        return f"{kind}{n}"

    def find(self, fid: str) -> Feature | None:
        """The feature with this ID, or None."""
        return next((f for f in self.features if f.id == fid), None)

    def sketches(self, before: str | None = None) -> list[SketchFeature]:
        """Sketches that come before feature ``before`` (all sketches if None)."""
        found = []
        for f in self.features:
            if f.id == before:
                break
            if isinstance(f, SketchFeature):
                found.append(f)
        return found

    def users(self, sketch_id: str) -> list[Feature]:
        """Features built from a sketch."""
        return [f for f in self.features if getattr(f, "sketch_id", None) == sketch_id]

    def replace(self, feature: Feature) -> None:
        """Swap in an edited copy of a feature (matched by ID)."""
        index = next(i for i, f in enumerate(self.features) if f.id == feature.id)
        self.features[index] = feature

    def delete(self, fid: str) -> None:
        """Delete a feature, and anything built from it."""
        doomed = {fid} | {f.id for f in self.users(fid)}
        self.features = [f for f in self.features if f.id not in doomed]


@dataclass
class Model:
    """Result of a recompute."""

    shape: TopoDS_Shape | None  # the body: one solid, or None if there's nothing yet
    errors: dict[str, str]  # feature ID -> message, for features that failed


def recompute(doc: Document) -> Model:
    """Replay every feature from scratch.

    A feature that fails is recorded in ``errors`` and skipped: the body
    stays as it was before that feature.
    """
    shape: TopoDS_Shape | None = None
    errors: dict[str, str] = {}
    for f in doc.features:
        if isinstance(f, SketchFeature):
            continue
        try:
            shape = _apply(doc, f, shape)
        except (FeatureError, ProfileError) as exc:
            errors[f.id] = str(exc)
        except Exception as exc:  # OCCT failures: report, never crash
            log.exception("Feature %s failed", f.name)
            errors[f.id] = f"Geometry error: {exc}"
    return Model(shape, errors)


def _apply(
    doc: Document, f: Pad | Pocket | Revolve | Hole, body: TopoDS_Shape | None
) -> TopoDS_Shape:
    if isinstance(f, Hole) and not f.sketch_id:
        if f.face is None or f.center is None:
            raise FeatureError("Click a planar face to place the hole.")
        sk = SketchFeature("", "", plane="Face", face=f.face)
    else:
        sk = doc.find(f.sketch_id)
        if not isinstance(sk, SketchFeature) or sk.id not in {s.id for s in doc.sketches(f.id)}:
            raise FeatureError("Its sketch is missing. Double-click to pick another one.")
    if isinstance(f, Pocket | Hole):
        if body is None:
            raise FeatureError("Nothing to cut yet. The first solid must be a Pad or Revolve.")
        through_length = _through_all_length(body, sk)
        if isinstance(f, Hole):
            tool = hole_shape(f, sk, through_length)
        else:
            if f.thread is not None:
                curves = [
                    g
                    for g in sk.sketch.geo.values()
                    if isinstance(g, Line | Arc | Circle) and not g.construction
                ]
                if len(curves) != 1 or not isinstance(curves[0], Circle):
                    raise FeatureError("Threaded Pocket needs exactly one circular profile.")
                depth = through_length if f.through_all else f.length
                validate_thread(f.thread, 2 * curves[0].radius, depth, cylindrical=True)
            tool = pocket_shape(f, sk, through_length)
        result = _clean(BRepAlgoAPI_Cut(body, tool).Shape())
        if isinstance(f, Hole) and volume(body) - volume(result) < 1e-8:
            raise FeatureError("The hole does not intersect the body in this direction.")
        return result
    tool = pad_shape(f, sk) if isinstance(f, Pad) else revolve_shape(f, sk)
    return _clean(tool if body is None else BRepAlgoAPI_Fuse(body, tool).Shape())


def _clean(shape: TopoDS_Shape) -> TopoDS_Shape:
    """Merge coplanar faces, then insist on exactly one valid solid."""
    unify = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    unify.Build()
    shape = unify.Shape()
    explorer, solids = TopExp_Explorer(shape, TopAbs_SOLID), 0
    while explorer.More():
        solids += 1
        explorer.Next()
    if solids == 0:
        raise FeatureError("Nothing would be left of the body.")
    if solids > 1:
        raise FeatureError(
            f"That would make {solids} separate pieces. A body must stay one piece, "
            "so make it touch or overlap the rest."
        )
    if not BRepCheck_Analyzer(shape).IsValid():
        raise FeatureError("The result isn't a valid solid. Try slightly different sizes.")
    return shape


def _through_all_length(body: TopoDS_Shape, sk: SketchFeature) -> float:
    """A length that reaches past every part of the body from the sketch plane."""
    box = Bnd_Box()
    brepbndlib.Add(body, box)
    x0, y0, z0, x1, y1, z1 = box.Get()
    origin = plane_axes(sk.placement(), sk.offset).Location()
    corners = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return max(math.dist((origin.X(), origin.Y(), origin.Z()), c) for c in corners) + 1.0
