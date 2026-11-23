"""Mouse interaction for sketches drawn directly in the OCCT viewport."""

import math

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent

from sillycad.core.sketch import X_AXIS, XY, Arc, Circle, Line, Point, Sketch
from sillycad.gui.drawing_input import DrawingInput
from sillycad.gui.sketch_scene import SketchScene
from sillycad.sketch_math import (
    LineAlignment,
    SnapTarget,
    add_rectangle,
    arc_sweep,
    constrain_snap,
    infer_line_alignment,
    project_to_circle,
)

_CLICKS = {"point": 1, "line": 2, "circle": 2, "arc": 3}


class SketchInteraction(QObject):
    """Translate native viewport events into edits on a local sketch session."""

    coordinates = Signal(float, float)
    edit_dimension = Signal(str)
    marking_menu = Signal(QPoint)
    tool_changed = Signal(str)
    finish_requested = Signal()

    def __init__(self, scene: SketchScene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self.session = scene.session
        self.viewer = scene.viewer
        self.tool = "select"
        self.clicks: list[tuple[XY, SnapTarget | None]] = []
        self._press: tuple[QPointF, XY, str | None] | None = None
        self._before: Sketch | None = None
        self._rectangle: tuple[XY, SnapTarget | None] | None = None
        self._rectangle_press: QPointF | None = None
        self._rectangle_waiting = False
        self._arc_dimensions: dict[str, float] = {}
        self._right: QPointF | None = None
        self._right_dragged = False
        self._orbiting = False
        self._passing = False
        self._navigation: str | None = None
        self._cursor_pos: QPointF | None = None
        self._grid_timer = QTimer(self)
        self._grid_timer.setSingleShot(True)
        self._grid_timer.setInterval(80)
        self._grid_timer.timeout.connect(self.scene.update_grid)
        self.dimensions = DrawingInput(self.viewer, self)
        self.dimensions.changed.connect(self._dimension_changed)
        self.dimensions.confirm.connect(self._confirm_dimensions)
        self.dimensions.cancel.connect(self.escape)
        self.dimensions.control_changed.connect(self._control_changed)
        self.dimensions.history.connect(self._dimension_history)
        self.dimensions.finish_sketch.connect(self.finish_requested)
        self.dimensions.tool_requested.connect(self.set_tool)
        self.session.changed.connect(scene.redraw)
        self.session.undo_stack.indexChanged.connect(self._history_changed)
        self.viewer.installEventFilter(self)

    def set_tool(self, tool: str) -> None:
        """Switch drawing tools and discard any unfinished geometry."""
        self.tool = tool
        self.clicks = []
        self._rectangle = None
        self._rectangle_waiting = False
        self._arc_dimensions.clear()
        self.dimensions.clear()
        self._navigation = None
        self._cursor_pos = None
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
        self._rectangle_waiting = False
        self._arc_dimensions.clear()
        self.dimensions.clear()
        self.scene.set_preview([])

    def escape(self) -> None:
        """Cancel an unfinished shape, navigation, or the current selection."""
        if self.clicks or self._rectangle:
            self.clicks = []
            self._rectangle = None
            self._rectangle_waiting = False
            self._arc_dimensions.clear()
            self.dimensions.clear()
            self.scene.set_preview([])
        elif self._navigation or self.tool != "select":
            self.set_tool("select")
        else:
            self.session.set_selection([])

    def close(self) -> None:
        """Detach interaction and remove the native sketch presentations."""
        self.viewer.removeEventFilter(self)
        self._grid_timer.stop()
        self.dimensions.clear()
        self.session.changed.disconnect(self.scene.redraw)
        self.session.undo_stack.indexChanged.disconnect(self._history_changed)
        self.scene.clear()
        self.viewer.unsetCursor()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not self.viewer:
            return False
        if event.type() in (QEvent.Type.Wheel, QEvent.Type.Resize, QEvent.Type.Leave):
            self.scene.clear_snap()
        if event.type() in (QEvent.Type.Wheel, QEvent.Type.Resize):
            self._grid_timer.start()
            return False
        if (
            isinstance(event, QKeyEvent)
            and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
            and event.key() == Qt.Key.Key_Control
            and self.tool == "line"
            and self.clicks
            and self._cursor_pos is not None
        ):
            try:
                self._preview(
                    self._cursor_pos, suppress_alignment=event.type() == QEvent.Type.KeyPress
                )
            except ValueError as exc:
                self.session.message.emit(str(exc))
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if self._passing:
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._passing = False
                self._grid_timer.start()
                return False
            if event.type() != QEvent.Type.MouseMove or event.buttons() & Qt.MouseButton.LeftButton:
                return False
            self._passing = False
            self._grid_timer.start()
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
        self._cursor_pos = pos
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
            self._rectangle_press = pos
            if self._rectangle is None:
                self._rectangle = self._snap(pos)
                self._rectangle_waiting = False
                self.dimensions.begin(("width", "height"))
                self._preview(pos)
            return True
        if self.tool != "select":
            if self.clicks:
                self.dimensions.values(strict=True)
            point, target, alignment = self._drawing_point(
                pos, bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            )
            if self.tool == "arc" and len(self.clicks) == 1:
                self._arc_dimensions = self.dimensions.values(strict=True)
            self.clicks.append((point, target))
            if len(self.clicks) == _CLICKS[self.tool]:
                self._create_shape(pos, alignment)
            elif self.tool != "point":
                names = (
                    ("length", "angle")
                    if self.tool == "line"
                    else ("sweep",)
                    if self.tool == "arc" and len(self.clicks) == 2
                    else ("radius",)
                )
                self.dimensions.begin(names)
                self._preview(pos)
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
        self._cursor_pos = pos
        buttons = event.buttons()
        if self._right is not None and not buttons & Qt.MouseButton.RightButton:
            self._right = None
            self._right_dragged = False
        if self._orbiting and not buttons & Qt.MouseButton.MiddleButton:
            self._orbiting = False
        if self._press is not None and not buttons & Qt.MouseButton.LeftButton:
            if self._before is not None:
                self.session.finish_drag(self._before)
                self._before = None
            self._press = None
        if self._rectangle is not None and not buttons & Qt.MouseButton.LeftButton:
            if self._rectangle_press is not None:
                self._rectangle_waiting = True
                self._rectangle_press = None
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
            self._preview(pos, bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
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
            self._preview(pos, bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
            return True
        hover = self.scene.pick(pos)
        _, target = self.scene.snap(pos)
        if hover != self.scene.hover or target != self.scene._snap_target:
            self.scene.hover = hover
            self.scene.set_preview([], target)
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
            moved = (
                self._rectangle_press is not None
                and (event.position() - self._rectangle_press).manhattanLength() > 4
            )
            if self._rectangle_waiting or moved:
                self._finish_rectangle(event.position())
            else:
                self._rectangle_waiting = True
        if self._before is not None:
            self.session.finish_drag(self._before)
            self._before = None
        self._press = None
        return True

    def _snap(self, pos: QPointF) -> tuple[XY, SnapTarget | None]:
        point, target = self.scene.snap(pos)
        if target and self.tool == "arc" and len(self.clicks) == 2:
            center, start = self.clicks[0][0], self.clicks[1][0]
            projected = project_to_circle(center, point, math.dist(center, start))
            if math.dist(projected, point) > 1e-7:
                return self.scene.to_sketch(pos), None
        return point, target

    def _history_changed(self, _index: int) -> None:
        if self.clicks or self._rectangle:
            self.clicks = []
            self._rectangle = None
            self._rectangle_waiting = False
            self._arc_dimensions.clear()
            self.dimensions.clear()
            self.scene.set_preview([])

    def _drawing_point(
        self, pos: QPointF, suppress_alignment: bool
    ) -> tuple[XY, SnapTarget | None, LineAlignment | None]:
        point, target = self._snap(pos)
        values = self.dimensions.values()
        if self.tool == "line" and self.clicks and target is None and not suppress_alignment:
            if "angle" not in values:
                point, alignment = infer_line_alignment(self.clicks[0][0], point)
            else:
                alignment = None
        else:
            alignment = None
        start = (
            self._rectangle[0] if self._rectangle else self.clicks[0][0] if self.clicks else None
        )
        if start is not None and values:
            dx, dy = point[0] - start[0], point[1] - start[1]
            if self.tool == "rectangle":
                dx = math.copysign(values.get("width", abs(dx)), dx or 1)
                dy = math.copysign(values.get("height", abs(dy)), dy or 1)
                point = start[0] + dx, start[1] + dy
            elif self.tool == "line":
                length = values.get("length", math.hypot(dx, dy))
                angle = math.radians(values["angle"]) if "angle" in values else math.atan2(dy, dx)
                point = start[0] + length * math.cos(angle), start[1] + length * math.sin(angle)
            elif self.tool in ("circle", "arc") and "radius" in values:
                angle = math.atan2(dy, dx)
                point = (
                    start[0] + values["radius"] * math.cos(angle),
                    start[1] + values["radius"] * math.sin(angle),
                )
            elif self.tool == "arc" and len(self.clicks) == 2 and "sweep" in values:
                arc_start = self.clicks[1][0]
                angle = math.atan2(arc_start[1] - start[1], arc_start[0] - start[0])
                angle += math.radians(values["sweep"])
                radius = math.dist(start, arc_start)
                point = start[0] + radius * math.cos(angle), start[1] + radius * math.sin(angle)
            target = None
        return point, target, alignment

    def _preview(self, pos: QPointF, suppress_alignment: bool = False) -> None:
        point, target, alignment = self._drawing_point(pos, suppress_alignment)
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
        self.scene.set_preview(segments, target, aligned=alignment is not None)
        self._update_dimensions(point)

    def _update_dimensions(self, point: XY) -> None:
        start = (
            self._rectangle[0] if self._rectangle else self.clicks[0][0] if self.clicks else None
        )
        if start is None:
            return
        midpoint = ((start[0] + point[0]) / 2, (start[1] + point[1]) / 2)
        anchor = self.scene.screen(midpoint)
        measurements: dict[str, tuple[float, QPointF]] = {}
        if self.tool == "rectangle":
            measurements = {
                "width": (abs(point[0] - start[0]), anchor + QPointF(-98, -14)),
                "height": (abs(point[1] - start[1]), anchor + QPointF(6, -14)),
            }
        elif self.tool == "line":
            measurements = {
                "length": (math.dist(start, point), anchor + QPointF(-98, -14)),
                "angle": (
                    math.degrees(math.atan2(point[1] - start[1], point[0] - start[0])),
                    anchor + QPointF(6, -14),
                ),
            }
        elif self.tool in ("circle", "arc") and len(self.clicks) == 1:
            measurements = {"radius": (math.dist(start, point), anchor + QPointF(6, -14))}
        elif self.tool == "arc" and len(self.clicks) == 2:
            _, sweep = arc_sweep(start, self.clicks[1][0], point)
            measurements = {"sweep": (math.degrees(sweep), anchor + QPointF(6, -14))}
        self.dimensions.update(measurements)

    def _dimension_changed(self) -> None:
        if self._cursor_pos is not None:
            self._preview(self._cursor_pos)

    def _control_changed(self, pressed: bool) -> None:
        if self.tool == "line" and self.clicks and self._cursor_pos is not None:
            try:
                self._preview(self._cursor_pos, suppress_alignment=pressed)
            except ValueError as exc:
                self.session.message.emit(str(exc))

    def _dimension_history(self, redo: bool) -> None:
        if redo:
            self.session.undo_stack.redo()
        else:
            self.session.undo_stack.undo()

    def _confirm_dimensions(self) -> None:
        try:
            self.dimensions.values(strict=True)
            if self._cursor_pos is None:
                raise ValueError("Move the pointer to choose a drawing direction.")
            if self._rectangle is not None:
                self._finish_rectangle(self._cursor_pos)
            elif self.clicks:
                point, target, alignment = self._drawing_point(self._cursor_pos, False)
                if self.tool == "arc" and len(self.clicks) == 1:
                    self._arc_dimensions = self.dimensions.values(strict=True)
                self.clicks.append((point, target))
                if len(self.clicks) == _CLICKS[self.tool]:
                    self._create_shape(self._cursor_pos, alignment)
                else:
                    self.dimensions.begin(("sweep",))
                    self._preview(self._cursor_pos)
        except ValueError as exc:
            self.session.message.emit(str(exc))

    def _finish_rectangle(self, pos: QPointF) -> None:
        assert self._rectangle is not None
        values = self.dimensions.values(strict=True)
        start, start_snap = self._rectangle
        end, end_snap, _ = self._drawing_point(pos, False)

        def rectangle(sketch: Sketch) -> None:
            lines = add_rectangle(sketch, start, end)
            first, opposite = sketch.geo[lines[0]], sketch.geo[lines[2]]
            assert isinstance(first, Line) and isinstance(opposite, Line)
            constrain_snap(sketch, first.p1, start_snap)
            constrain_snap(sketch, opposite.p1, end_snap)
            if "width" in values:
                sketch.add_constraint("distance", [lines[0]], values["width"])
            if "height" in values:
                sketch.add_constraint("distance", [lines[1]], values["height"])

        if self.session.edit("Add rectangle", rectangle):
            self._rectangle = None
            self._rectangle_waiting = False
            self.dimensions.clear()
            self.scene.set_preview([])

    def _create_shape(self, pos: QPointF, alignment: LineAlignment | None = None) -> None:
        tool, clicks = self.tool, self.clicks
        positions, snaps = [point for point, _ in clicks], [snap for _, snap in clicks]
        values = {**self._arc_dimensions, **self.dimensions.values(strict=True)}
        threshold = 1e-9 if values else self.scene.tolerance(pos, 2)
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
                if alignment is not None:
                    sketch.add_constraint(alignment, [gid])
                if "length" in values:
                    sketch.add_constraint("distance", [gid], values["length"])
                if "angle" in values:
                    angle = (values["angle"] + 180) % 360 - 180
                    sketch.add_constraint("angle", [X_AXIS, gid], abs(angle))
            elif tool == "circle":
                radius = math.dist(*positions)
                if radius < threshold:
                    raise ValueError("That circle is too small.")
                gid = sketch.add_circle(*positions[0], radius)
                circle = sketch.geo[gid]
                assert isinstance(circle, Circle)
                ends = [circle.center, None]
                if "radius" in values:
                    sketch.add_constraint("radius", [gid], values["radius"])
            else:
                center, start, end = positions
                radius = math.dist(center, start)
                if radius < threshold:
                    raise ValueError("That arc is too small.")
                gid = sketch.add_arc(*center, *start, *project_to_circle(center, end, radius))
                arc = sketch.geo[gid]
                assert isinstance(arc, Arc)
                ends = [arc.center, arc.start, arc.end]
                if "radius" in values:
                    sketch.add_constraint("radius", [gid], values["radius"])
                if "sweep" in values:
                    sketch.add_constraint("arc_angle", [gid], values["sweep"])
            for point, snap in zip(ends, snaps, strict=True):
                if point:
                    constrain_snap(sketch, point, snap)
            if ends[-1]:
                new_end.append(ends[-1])

        ok = self.session.edit(f"Add {tool}", build)
        self.clicks = []
        self._arc_dimensions.clear()
        self.dimensions.clear()
        if ok and tool == "line" and (snaps[-1] is None or snaps[-1].kind == "reference"):
            end = self.session.sketch.point(new_end[0])
            self.clicks = [(end, SnapTarget(end, "point", new_end[0]))]
            self.dimensions.begin(("length", "angle"))
        self.scene.set_preview([])
