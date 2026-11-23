"""Viewport placement for the Hole property panel."""

import math
from collections.abc import Callable

from OCC.Core.AIS import AIS_Point
from OCC.Core.Aspect import Aspect_TOM_BALL
from OCC.Core.Geom import Geom_CartesianPoint
from OCC.Core.gp import gp_Dir, gp_Lin, gp_Pnt
from OCC.Core.Graphic3d import Graphic3d_ZLayerId_TopOSD
from OCC.Core.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCC.Core.Prs3d import Prs3d_PointAspect
from OCC.Core.TopoDS import TopoDS_Shape
from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from sillycad.core.features import SketchFeature
from sillycad.core.geometry import Placement, face_placement, outline_in_plane
from sillycad.core.sketch import XY, Sketch
from sillycad.gui import theme
from sillycad.gui.hole_panel import HolePanel
from sillycad.gui.sketch_scene import PICK_PIXELS, _color
from sillycad.gui.viewer import Viewer
from sillycad.sketch_math import ray_to_sketch, sketch_to_world, snap_targets


class HolePlacement(QObject):
    """Pick a position on the original body or the selected sketch plane."""

    def __init__(
        self,
        viewer: Viewer,
        panel: HolePanel,
        body: TopoDS_Shape | None,
        sketches: list[SketchFeature],
        message: Callable[[str], None],
    ) -> None:
        super().__init__(panel)
        self.viewer = viewer
        self.panel = panel
        self.body = body
        self.sketches = {sketch.id: sketch for sketch in sketches}
        self.message = message
        self._pressed: QPointF | None = None
        self._marker: AIS_Point | None = None
        self._outline_cache: dict[tuple[tuple[float, ...], ...], list[list[XY]]] = {}
        self._sketch_targets = {sketch.id: snap_targets(sketch.sketch, []) for sketch in sketches}
        self.viewer.installEventFilter(self)

    def set_body(self, body: TopoDS_Shape | None) -> None:
        """Use the latest committed body after applying a new hole."""
        self.body = body
        self._outline_cache.clear()
        self._clear_marker()

    def close(self) -> None:
        """Stop picking and remove the marker."""
        self.viewer.removeEventFilter(self)
        self._clear_marker()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not self.viewer:
            return False
        if event.type() in (QEvent.Type.Leave, QEvent.Type.Wheel, QEvent.Type.Resize):
            self._clear_marker()
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._pressed = event.position()
            return False
        if event.type() == QEvent.Type.MouseMove and not event.buttons():
            try:
                candidate = self._candidate(event.position())
                self._show_marker(candidate[1], candidate[0]) if candidate and candidate[
                    3
                ] else self._clear_marker()
            except ValueError as exc:
                self._clear_marker()
                self.message(str(exc))
            return False
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            start, self._pressed = self._pressed, None
            if start is None or (event.position() - start).manhattanLength() > 4:
                return False
            context = self.viewer._display.Context
            context.MoveTo(
                round(event.position().x()),
                round(event.position().y()),
                self.viewer._display.View,
                False,
            )
            if context.HasDetected() and context.DetectedOwner().IsKind("AIS_ViewCubeOwner"):
                return False
            try:
                candidate = self._candidate(event.position())
                if candidate is None:
                    self.message("Click a planar face on the body to place the hole.")
                else:
                    plane, xy, point_id, _ = candidate
                    self._clear_marker()
                    self.panel.set_position(
                        plane if not self.panel.sketch.currentData() else None, xy, point_id
                    )
            except ValueError as exc:
                self.message(str(exc))
            self.viewer.finish_placement_click()
            return True
        return False

    def _candidate(self, pos: QPointF) -> tuple[Placement, XY, str | None, bool] | None:
        view = self.viewer._display.View
        x, y, z, vx, vy, vz = view.ConvertWithProj(round(pos.x()), round(pos.y()))
        origin, direction = (x, y, z), (vx, vy, vz)
        sketch = self.sketches.get(self.panel.sketch.currentData())
        if sketch is None:
            if self.body is None:
                return None
            camera = view.Camera().Direction()
            if vx * camera.X() + vy * camera.Y() + vz * camera.Z() < 0:
                direction = (-vx, -vy, -vz)
            intersector = IntCurvesFace_ShapeIntersector()
            intersector.Load(self.body, 1e-7)
            intersector.Perform(gp_Lin(gp_Pnt(*origin), gp_Dir(*direction)), -1e9, 1e9)
            if not intersector.NbPnt():
                return None
            index = min(range(1, intersector.NbPnt() + 1), key=intersector.WParameter)
            placement = face_placement(intersector.Face(index))
        else:
            base = sketch.placement()
            placement = Placement(
                tuple(a + sketch.offset * b for a, b in zip(base.origin, base.normal, strict=True)),
                base.normal,
                base.x_dir,
            )
        xy = ray_to_sketch(origin, direction, placement)
        outline = self._outline(placement)
        candidates: list[tuple[XY, str | None]] = []
        sources = sorted(self.sketches.values(), key=lambda source: source is not sketch)
        for source in sources:
            source_plane = source.placement()
            world_origin = sketch_to_world((0, 0), source_plane, source.offset)
            distance = sum(
                (a - b) * n
                for a, b, n in zip(world_origin, placement.origin, placement.normal, strict=True)
            )
            dot = sum(a * b for a, b in zip(source_plane.normal, placement.normal, strict=True))
            if abs(distance) > 1e-6 or abs(abs(dot) - 1) > 1e-6:
                continue
            for target in self._sketch_targets[source.id]:
                world = sketch_to_world(target.point, source_plane, source.offset)
                point = ray_to_sketch(world, placement.normal, placement)
                ref = target.ref if source is sketch and target.kind == "point" else None
                candidates.append((point, ref))
        candidates.extend((target.point, None) for target in snap_targets(Sketch(), outline))
        best, distance = None, PICK_PIXELS
        for point, ref in candidates:
            sx, sy = view.Convert(*sketch_to_world(point, placement))
            gap = math.hypot(pos.x() - sx, pos.y() - sy)
            if gap < distance:
                best, distance = (point, ref), gap
        return (placement, best[0], best[1], True) if best else (placement, xy, None, False)

    def _outline(self, placement: Placement) -> list[list[XY]]:
        if self.body is None:
            return []
        key = (placement.origin, placement.normal, placement.x_dir)
        if key not in self._outline_cache:
            self._outline_cache[key] = outline_in_plane(self.body, placement)
        return self._outline_cache[key]

    def _show_marker(self, xy: XY, placement: Placement) -> None:
        context = self.viewer._display.Context
        geometry = Geom_CartesianPoint(gp_Pnt(*sketch_to_world(xy, placement)))
        if self._marker is None:
            self._marker = AIS_Point(geometry)
            self._marker.SetZLayer(Graphic3d_ZLayerId_TopOSD)
            color = _color(theme.SKETCH_SNAP)
            self._marker.SetColor(color)
            self._marker.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TOM_BALL, color, 3.0))
        else:
            self._marker.SetComponent(geometry)
        if not context.IsDisplayed(self._marker):
            context.Display(self._marker, False)
            context.Deactivate(self._marker)
        context.Redisplay(self._marker, False)
        self.viewer._display.Repaint()

    def _clear_marker(self) -> None:
        if self._marker is not None:
            self.viewer._display.Context.Remove(self._marker, True)
            self._marker = None
