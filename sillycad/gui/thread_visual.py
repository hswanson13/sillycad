"""Non-modeling viewport linework for cosmetic internal threads."""

import logging
import math

from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.gp import gp_Pnt, gp_Trsf
from OCC.Core.TopAbs import TopAbs_IN, TopAbs_OUT
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Shape

from sillycad.core.document import Document, Model, _through_all_length
from sillycad.core.features import Hole, Pocket, SketchFeature
from sillycad.core.geometry import plane_trsf
from sillycad.core.profiles import sole_circular_profile
from sillycad.core.threads import resolve_thread

log = logging.getLogger(__name__)

_SEGMENTS_PER_TURN = 24
_MAX_FEATURE_SEGMENTS = 192
_MAX_TOTAL_SEGMENTS = 2400


def _bore_point(
    center: tuple[float, float],
    radius: float,
    cos_angle: float,
    sin_angle: float,
    z: float,
    transform: gp_Trsf,
) -> gp_Pnt:
    return gp_Pnt(center[0] + radius * cos_angle, center[1] + radius * sin_angle, z).Transformed(
        transform
    )


def thread_linework(doc: Document, model: Model) -> list[TopoDS_Shape]:
    """Make non-selectable thread strokes on surviving bore walls, not solid geometry."""
    if model.shape is None:
        return []
    features = [
        feature
        for feature in doc.features
        if isinstance(feature, Hole | Pocket)
        and feature.thread is not None
        and feature.id not in model.errors
    ]
    if not features:
        return []
    if len(features) > _MAX_TOTAL_SEGMENTS:
        log.warning(
            "Cosmetic thread display is limited to %d features; %d were omitted.",
            _MAX_TOTAL_SEGMENTS,
            len(features) - _MAX_TOTAL_SEGMENTS,
        )
        features = features[:_MAX_TOTAL_SEGMENTS]
    budget = min(_MAX_FEATURE_SEGMENTS, _MAX_TOTAL_SEGMENTS // len(features))
    bounds = Bnd_Box()
    brepbndlib.Add(model.shape, bounds)
    x0, y0, z0, x1, y1, z1 = bounds.Get()
    corners = [gp_Pnt(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    classifier = BRepClass3d_SolidClassifier(model.shape)
    result: list[TopoDS_Shape] = []
    for feature in features:
        assert feature.thread is not None
        sketch = doc.find(feature.sketch_id)
        if isinstance(feature, Hole) and not feature.sketch_id:
            if feature.face is None or feature.center is None:
                continue
            sketch = SketchFeature("", "", plane="Face", face=feature.face)
        if not isinstance(sketch, SketchFeature):
            continue
        if isinstance(feature, Hole):
            center = (
                feature.center
                if feature.center is not None
                else sketch.sketch.point(feature.point_id)
            )
            diameter = feature.diameter
            if feature.style in ("counterbore", "spotface"):
                recess = feature.head_depth
            elif feature.style == "countersink":
                recess = (feature.head_diameter - diameter) / (
                    2 * math.tan(math.radians(feature.countersink_angle / 2))
                )
            else:
                recess = 0.0
        else:
            circle = sole_circular_profile(sketch.sketch)
            if circle is None:
                continue
            center = sketch.sketch.point(circle.center)
            diameter = circle.radius * 2
            recess = 0.0
        size = resolve_thread(feature.thread)
        cutter_length = (
            _through_all_length(model.shape, sketch) if feature.through_all else feature.length
        )
        length = min(feature.thread.depth or cutter_length - recess, cutter_length - recess)
        if length <= 0:
            continue
        transform = plane_trsf(sketch.placement(), sketch.offset)
        direction = 1 if feature.reversed else -1
        inverse = transform.Inverted()
        depths = [direction * point.Transformed(inverse).Z() for point in corners]
        start = max(recess, min(depths))
        end = min(recess + length, max(depths))
        if end <= start:
            continue
        step = size.pitch / _SEGMENTS_PER_TURN
        if not step or step <= math.ulp(max(abs(start), abs(end))):
            log.warning("Thread pitch for %s is too small to display at this scale.", feature.name)
            continue
        epsilon = min(0.01, diameter * 0.001)
        inset = min(epsilon / 4, step / 10, (end - start) / 100)
        start, end = start + inset, end - inset
        if end - start <= step * budget:
            ranges = [(start, end, min(budget, max(1, math.ceil((end - start) / step))))]
        else:
            # Sparse patches preserve the pitch instead of aliasing turns into long chords.
            groups = min(4, budget)
            ranges = []
            for index in range(groups):
                count = budget // groups + int(index < budget % groups)
                width = count * step
                position = index / (groups - 1) if groups > 1 else 0
                begin = start + (end - start - width) * position
                ranges.append((begin, begin + width, count))
        hand = direction * (-1 if feature.thread.left_hand else 1)
        compound, builder = TopoDS_Compound(), BRep_Builder()
        builder.MakeCompound(compound)
        edges = 0
        for range_start, range_end, steps in ranges:
            previous: gp_Pnt | None = None
            for i in range(steps + 1):
                depth = range_start + (range_end - range_start) * i / steps
                angle = hand * math.tau * (((depth - recess) % size.pitch) / size.pitch)
                radius = diameter / 2 - size.taper * (depth - recess) / 2
                if radius <= epsilon:
                    previous = None
                    continue
                cos_angle, sin_angle = math.cos(angle), math.sin(angle)
                outside_point = _bore_point(
                    center, radius + epsilon, cos_angle, sin_angle, direction * depth, transform
                )
                inside_point = _bore_point(
                    center, radius - epsilon, cos_angle, sin_angle, direction * depth, transform
                )
                classifier.Perform(outside_point, epsilon / 10)
                outside = classifier.State() == TopAbs_IN
                classifier.Perform(inside_point, epsilon / 10)
                inside = classifier.State() == TopAbs_OUT
                point = inside_point if outside and inside else None
                if point is not None and previous is not None and point.Distance(previous) > 1e-8:
                    builder.Add(compound, BRepBuilderAPI_MakeEdge(previous, point).Edge())
                    edges += 1
                previous = point
        if edges:
            result.append(compound)
    return result
