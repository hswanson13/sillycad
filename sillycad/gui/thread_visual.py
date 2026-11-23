"""Non-modeling viewport linework for cosmetic internal threads."""

import math

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.gp import gp_Pnt, gp_Trsf
from OCC.Core.TopAbs import TopAbs_IN, TopAbs_OUT
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Shape

from sillycad.core.document import Document, Model, _through_all_length
from sillycad.core.features import Hole, Pocket, SketchFeature
from sillycad.core.geometry import plane_trsf
from sillycad.core.sketch import Arc, Circle, Line
from sillycad.core.threads import resolve_thread


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
    classifier = BRepClass3d_SolidClassifier(model.shape)
    result: list[TopoDS_Shape] = []
    for feature in doc.features:
        if not isinstance(feature, Hole | Pocket) or feature.thread is None:
            continue
        if feature.id in model.errors:
            continue
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
            curves = [
                g
                for g in sketch.sketch.geo.values()
                if isinstance(g, Line | Arc | Circle) and not g.construction
            ]
            if len(curves) != 1 or not isinstance(curves[0], Circle):
                continue
            center = sketch.sketch.point(curves[0].center)
            diameter = curves[0].radius * 2
            recess = 0.0
        size = resolve_thread(feature.thread)
        cutter_length = (
            _through_all_length(model.shape, sketch) if feature.through_all else feature.length
        )
        length = min(feature.thread.depth or cutter_length - recess, cutter_length - recess)
        if length <= 0:
            continue
        steps = min(3000, max(24, math.ceil(length / size.pitch * 24)))
        transform = plane_trsf(sketch.placement(), sketch.offset)
        direction = 1 if feature.reversed else -1
        hand = direction * (-1 if feature.thread.left_hand else 1)
        epsilon = min(0.01, diameter * 0.001)
        compound, builder = TopoDS_Compound(), BRep_Builder()
        builder.MakeCompound(compound)
        previous: gp_Pnt | None = None
        edges = 0
        for i in range(steps + 1):
            depth = recess + length * i / steps
            angle = hand * math.tau * (depth - recess) / size.pitch
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
