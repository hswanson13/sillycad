"""Mouse interaction for sketches drawn directly in the OCCT viewport."""

import math

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent

from sillycad.core.sketch import XY, Arc, Circle, Line, Point, Sketch
from sillycad.gui.sketch_scene import SketchScene
from sillycad.sketch_math import add_rectangle, arc_sweep, project_to_circle

_CLICKS = {"point": 1, "line": 2, "circle": 2, "arc": 3}


class SketchInteraction(QObject):
    """Translate native viewport events into edits on a local sketch session."""

    coordinates = Signal(float, float)
    edit_dimension = Signal(str)
    marking_menu = Signal(QPoint)
    tool_changed = Signal(str)

    def __init__(self, scene: SketchScene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self.session = scene.session
        self.viewer = scene.viewer
        self.tool = "select"
        self.clicks: list[tuple[XY, str | None]] = []
        self._press: tuple[QPointF, XY, str | None] | None = None
        self._before: Sketch | None = None
        self._rectangle: tuple[XY, str | None] | None = None
        self._right: QPointF | None = None
        self._right_dragged = False
        self._orbiting = False
        self._passing = False
        self._navigation: str | None = None
        self._grid_timer = QTimer(self)
        self._grid_timer.setSingleShot(True)
        self._grid_timer.setInterval(80)
        self._grid_timer.timeout.connect(self.scene.update_grid)
        self.session.changed.connect(scene.redraw)
        self.viewer.installEventFilter(self)

    def set_tool(self, tool: str) -> None:
        """Switch drawing tools and discard any unfinished geometry."""
        self.tool = tool
        self.clicks = []
        self._rectangle = None
        self._navigation = None
        self.scene.hover = None
        self.scene.set_preview([])
        self.viewer.setCursor(
            Qt.CursorShape.ArrowCursor if tool == "select" else Qt.CursorShape.CrossCursor
        )
        self.tool_changed.emit(tool)

    def set_navigation(self, mode: str) -> None:
        """Temporarily use the left mouse button to navigate the 3D view."""
        self._navigation = mode
        self.clicks = []
        self._rectangle = None
        self.scene.set_preview([])

    def escape(self) -> None:
        """Cancel an unfinished shape, navigation, or the current selection."""
        if self.clicks or self._rectangle:
            self.clicks = []
            self._rectangle = None
            self.scene.set_preview([])
        elif self._navigation or self.tool != "select":
            self.set_tool("select")
        else:
            self.session.set_selection([])

    def close(self) -> None:
        """Detach interaction and remove the native sketch presentations."""
        self.viewer.removeEventFilter(self)
        self._grid_timer.stop()
        self.session.changed.disconnect(self.scene.redraw)
        self.scene.clear()
        self.viewer.unsetCursor()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not self.viewer:
            return False
        if event.type() in (QEvent.Type.Wheel, QEvent.Type.Resize):
            self._grid_timer.start()
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if self._passing:
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._passing = False
                self._grid_timer.start()
            return False
        try:
            if event.type() == QEvent.Type.MouseButtonPress:
                return self._mouse_press(event)
            if event.type() == QEvent.Type.MouseMove:
                return self._mouse_move(event)
            if event.type() == QEvent.Type.MouseButtonRelease:
                return self._mouse_release(event)
            if event.type() == QEvent.Type.MouseButtonDblClick:
                picked = self.scene.pick(event.position())
                if picked in self.session.sketch.constraints:
                    self.edit_dimension.emit(picked)
                    return True
        except ValueError as exc:
            self.session.message.emit(str(exc))
            return True
        return False

    def _mouse_press(self, event: QMouseEvent) -> bool:
        self.viewer.stop_camera_animation()
        self.viewer.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = event.position()
        if event.button() == Qt.MouseButton.RightButton:
            self._right = pos
            self._right_dragged = False
            return True
        if event.button() == Qt.MouseButton.MiddleButton:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._orbiting = True
                self.viewer._display.StartRotation(round(pos.x()), round(pos.y()))
                return True
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        context = self.viewer._display.Context
        context.MoveTo(round(pos.x()), round(pos.y()), self.viewer._display.View, False)
        if context.HasDetected() and context.DetectedOwner().IsKind("AIS_ViewCubeOwner"):
            self._passing = True
            return False
        if self._navigation:
            self._press = (pos, (0, 0), None)
            self.viewer._display.StartRotation(round(pos.x()), round(pos.y()))
            return True
        xy = self.scene.to_sketch(pos)
        if self.tool == "rectangle":
            self._rectangle = self.scene.snap(pos)
            return True
        if self.tool != "select":
            self.clicks.append(self.scene.snap(pos))
            if len(self.clicks) == _CLICKS[self.tool]:
                self._create_shape(pos)
            return True
        picked = self.scene.pick(pos)
        selection = list(self.session.selection)
        additive = event.modifiers() & (
            Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
        )
        if picked is None:
            if not additive:
                selection = []
        elif additive and picked in selection:
            selection.remove(picked)
        elif additive:
            selection.append(picked)
        elif picked not in selection:
            selection = [picked]
        self.session.set_selection(selection)
        self._press = (pos, xy, picked)
        if picked is None:
            self.viewer._display.StartRotation(round(pos.x()), round(pos.y()))
        return True

    def _mouse_move(self, event: QMouseEvent) -> bool:
        pos = event.position()
        if self._orbiting:
            self.viewer._display.Rotation(round(pos.x()), round(pos.y()))
            self._grid_timer.start()
            return True
        if self._right is not None:
            if (pos - self._right).manhattanLength() > 4:
                self._right_dragged = True
                self.viewer._display.DynamicZoom(
                    round(self._right.x()), round(self._right.y()), round(pos.x()), round(pos.y())
                )
                self._right = pos
                self._grid_timer.start()
            return True
        if event.buttons() == Qt.MouseButton.MiddleButton:
            self._grid_timer.start()
            return False
        xy = self.scene.to_sketch(pos)
        self.coordinates.emit(*xy)
        if self._rectangle is not None:
            self._preview(pos)
            return True
        if self._press is not None:
            start_pos, start_xy, picked = self._press
            moved = (pos - start_pos).manhattanLength() > 4
            if self._navigation:
                self._navigate(start_pos, pos)
                self._grid_timer.start()
                self._press = (pos, start_xy, picked)
            elif picked is None and moved:
                self.viewer._display.Rotation(round(pos.x()), round(pos.y()))
                self._grid_timer.start()
            elif picked in self.session.sketch.geo:
                if self._before is None and moved:
                    self._before = self.session.start_drag()
                if self._before is not None:
                    geometry = self._before.geo[picked]
                    if isinstance(geometry, Point):
                        self.session.drag_to({picked: xy})
                    elif isinstance(geometry, Circle):
                        self.session.drag_to(
                            {}, {picked: math.dist(self._before.point(geometry.center), xy)}
                        )
                    else:
                        dx, dy = xy[0] - start_xy[0], xy[1] - start_xy[1]
                        self.session.drag_to(
                            {
                                point: (
                                    self._before.point(point)[0] + dx,
                                    self._before.point(point)[1] + dy,
                                )
                                for point in geometry.points
                            }
                        )
            return True
        if self.tool != "select":
            self._preview(pos)
            return True
        hover = self.scene.pick(pos)
        if hover != self.scene.hover:
            self.scene.hover = hover
            self.scene.redraw()
        return True

    def _navigate(self, start: QPointF, end: QPointF) -> None:
        if self._navigation == "orbit":
            self.viewer._display.Rotation(round(end.x()), round(end.y()))
        elif self._navigation == "pan":
            self.viewer._display.Pan(round(end.x() - start.x()), round(start.y() - end.y()))
        else:
            self.viewer._display.DynamicZoom(
                round(start.x()), round(start.y()), round(end.x()), round(end.y())
            )

    def _mouse_release(self, event: QMouseEvent) -> bool:
        if event.button() == Qt.MouseButton.MiddleButton and self._orbiting:
            self._orbiting = False
            return True
        if event.button() == Qt.MouseButton.RightButton and self._right is not None:
            start, self._right = self._right, None
            if not self._right_dragged and (event.position() - start).manhattanLength() <= 4:
                if self.clicks or self._rectangle:
                    self.escape()
                else:
                    self.marking_menu.emit(event.globalPosition().toPoint())
            return True
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._rectangle is not None:
            start, start_snap = self._rectangle
            end, end_snap = self.scene.snap(event.position())
            self._rectangle = None
            self.session.edit(
                "Add rectangle",
                lambda sketch: add_rectangle(sketch, start, end, start_snap, end_snap),
            )
            self.scene.set_preview([])
        if self._before is not None:
            self.session.finish_drag(self._before)
            self._before = None
        self._press = None
        return True

    def _preview(self, pos: QPointF) -> None:
        point, _ = self.scene.snap(pos)
        clicks = self.clicks
        segments: list[tuple[XY, XY]] = []
        if self._rectangle is not None:
            a = self._rectangle[0]
            corners = [a, (point[0], a[1]), point, (a[0], point[1])]
            segments = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        elif clicks and self.tool == "line":
            segments = [(clicks[0][0], point)]
        elif clicks and self.tool in ("circle", "arc"):
            center = clicks[0][0]
            radius = math.dist(center, clicks[1][0] if len(clicks) > 1 else point)
            if self.tool == "arc" and len(clicks) == 1:
                segments = [(center, point)]
            else:
                start, sweep = (
                    arc_sweep(center, clicks[1][0], point)
                    if self.tool == "arc"
                    else (0.0, math.tau)
                )
                points = [
                    (
                        center[0] + radius * math.cos(start + i * sweep / 64),
                        center[1] + radius * math.sin(start + i * sweep / 64),
                    )
                    for i in range(65)
                ]
                segments = list(zip(points, points[1:], strict=False))
        self.scene.set_preview(segments)

    def _create_shape(self, pos: QPointF) -> None:
        tool, clicks = self.tool, self.clicks
        positions, snaps = [point for point, _ in clicks], [snap for _, snap in clicks]
        threshold = self.scene.tolerance(pos, 2)
        new_end: list[str] = []

        def build(sketch: Sketch) -> None:
            if tool == "point":
                ends: list[str | None] = [sketch.add_point(*positions[0])]
            elif tool == "line":
                if math.dist(*positions) < threshold:
                    raise ValueError("That line is too short. Click two different spots.")
                gid = sketch.add_line(*positions[0], *positions[1])
                line = sketch.geo[gid]
                assert isinstance(line, Line)
                ends = list(line.points)
            elif tool == "circle":
                radius = math.dist(*positions)
                if radius < threshold:
                    raise ValueError("That circle is too small.")
                gid = sketch.add_circle(*positions[0], radius)
                circle = sketch.geo[gid]
                assert isinstance(circle, Circle)
                ends = [circle.center, None]
            else:
                center, start, end = positions
                radius = math.dist(center, start)
                if radius < threshold:
                    raise ValueError("That arc is too small.")
                gid = sketch.add_arc(*center, *start, *project_to_circle(center, end, radius))
                arc = sketch.geo[gid]
                assert isinstance(arc, Arc)
                ends = [arc.center, arc.start, arc.end]
            for point, snap in zip(ends, snaps, strict=True):
                if point and snap:
                    sketch.add_constraint("coincident", [point, snap])
            if ends[-1]:
                new_end.append(ends[-1])

        ok = self.session.edit(f"Add {tool}", build)
        self.clicks = []
        if ok and tool == "line" and snaps[-1] is None:
            self.clicks = [(positions[-1], new_end[0])]
        self.scene.set_preview([])
