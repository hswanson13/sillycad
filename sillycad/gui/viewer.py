"""3D viewport built on pythonocc's Qt viewer widget.

Mouse: left-drag orbits, middle-drag pans, right-drag or wheel zooms.
A left click (without dragging) picks a face; ``sig_topods_selected`` reports it.
"""

from OCC.Display.backend import load_backend
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QFontInfo, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

load_backend("pyside6")  # must run before importing qtDisplay

from OCC.Core.AIS import (  # noqa: E402
    AIS_AnimationCamera,
    AIS_TextLabel,
    AIS_Trihedron,
    AIS_ViewCube,
    AIS_ViewCubeOwner,
)
from OCC.Core.Aspect import Aspect_GFM_VER, Aspect_TOL_SOLID, Aspect_TOTP_RIGHT_UPPER  # noqa: E402
from OCC.Core.Bnd import Bnd_Box  # noqa: E402
from OCC.Core.BRepBndLib import brepbndlib  # noqa: E402
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeFace  # noqa: E402
from OCC.Core.Geom import Geom_Axis2Placement  # noqa: E402
from OCC.Core.gp import gp_Ax2, gp_Pln, gp_Pnt  # noqa: E402
from OCC.Core.Graphic3d import (  # noqa: E402
    Graphic3d_Camera,
    Graphic3d_NOM_PLASTER,
    Graphic3d_TMF_TriedronPers,
    Graphic3d_TransformPers,
    Graphic3d_Vec2i,
)
from OCC.Core.Prs3d import (  # noqa: E402
    Prs3d_LineAspect,
    Prs3d_TypeOfHighlight_Dynamic,
    Prs3d_TypeOfHighlight_LocalDynamic,
    Prs3d_TypeOfHighlight_LocalSelected,
    Prs3d_TypeOfHighlight_Selected,
)
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_sRGB  # noqa: E402
from OCC.Core.TopoDS import TopoDS_Shape  # noqa: E402
from OCC.Display.qtDisplay import qtViewer3d  # noqa: E402

from sillycad.core.geometry import BASE_PLANES, Placement, plane_axes, plane_trsf  # noqa: E402
from sillycad.gui import theme  # noqa: E402


def _color(rgb: tuple[float, float, float]) -> Quantity_Color:
    return Quantity_Color(*rgb, Quantity_TOC_sRGB)


SKETCH_COLOR = _color(theme.VIEW_SKETCH)


class Viewer(qtViewer3d):
    """The 3D view. Call ``init()`` once, after the window is shown."""

    marking_menu_requested = Signal(QPoint)
    plane_pick_cancelled = Signal()
    camera_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._press_at: QPointF | None = None
        self._display_mode = "shaded"
        self._navigation_mode = "orbit"
        self._picking_plane = False
        self._plane_shapes: dict[str, TopoDS_Shape] = {}
        self._camera_animation: AIS_AnimationCamera | None = None
        self._camera_end: Graphic3d_Camera | None = None
        self._camera_timer = QTimer(self)
        self._camera_timer.timeout.connect(self._animate_camera)

    def init(self) -> None:
        """Create the OCCT viewer. Needs a real native window, so call after show()."""
        self.InitDriver()
        display = self._display
        display.View.SetBgGradientColors(
            _color(theme.VIEW_BACKGROUND_TOP),
            _color(theme.VIEW_BACKGROUND_BOTTOM),
            Aspect_GFM_VER,
            False,
        )
        for kind in (Prs3d_TypeOfHighlight_Dynamic, Prs3d_TypeOfHighlight_LocalDynamic):
            display.Context.HighlightStyle(kind).SetColor(_color(theme.VIEW_HOVER))
        for kind in (Prs3d_TypeOfHighlight_Selected, Prs3d_TypeOfHighlight_LocalSelected):
            display.Context.HighlightStyle(kind).SetColor(_color(theme.VIEW_SELECTED))

        self._font = QFontInfo(QApplication.font()).family()
        styles = QFontDatabase.styles(self._font)
        if (
            styles
            and all("italic" in style.lower() or "oblique" in style.lower() for style in styles)
            and "FreeSans" in QFontDatabase.families()
        ):
            self._font = "FreeSans"
        self._cube = AIS_ViewCube()
        self._cube.SetTransformPersistence(
            Graphic3d_TransformPers(
                Graphic3d_TMF_TriedronPers, Aspect_TOTP_RIGHT_UPPER, Graphic3d_Vec2i(75, 75)
            )
        )
        self._cube.SetBoxColor(_color(theme.VIEW_CUBE))
        self._cube.SetTextColor(_color(theme.VIEW_EDGE))
        self._cube.SetFont(self._font)
        self._cube.SetDrawAxes(False)
        self._cube_animation = AIS_AnimationCamera("ViewCube", display.View)
        self._cube.SetViewAnimation(self._cube_animation)
        self._cube.SetFixedAnimationLoop(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.stop_camera_animation()
        self._press_at = event.position()
        super().mousePressEvent(event)

    def finish_placement_click(self) -> None:
        """Complete a consumed placement click without selecting viewport geometry."""
        self._press_at = None
        self._on_left_release()
        self.cursor = "arrow"

    @property
    def cursor(self) -> str:
        return self._current_cursor

    @cursor.setter
    def cursor(self, value: str) -> None:
        if self._current_cursor != value:
            self._current_cursor = value
            cursor = self._available_cursors.get(value)
            if cursor is None:
                self.unsetCursor()
            else:
                self.setCursor(cursor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.pixelDelta().y() or event.angleDelta().y()
        if not delta:
            event.ignore()
            return
        self.stop_camera_animation()
        self._display.ZoomFactor(2.0 ** (max(-480, min(480, delta)) / 120))
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            event.buttons() == Qt.MouseButton.LeftButton
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            and self._navigation_mode in ("pan", "zoom")
        ):
            x, y = event.position().toPoint().x(), event.position().toPoint().y()
            if self._navigation_mode == "pan":
                self.cursor = "pan"
                self._display.Pan(x - self.dragStartPosX, self.dragStartPosY - y)
            else:
                self.cursor = "zoom"
                self._display.DynamicZoom(self.dragStartPosX, self.dragStartPosY, x, y)
            self.dragStartPosX, self.dragStartPosY = x, y
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        dragged = (
            self._press_at is not None and (event.position() - self._press_at).manhattanLength() > 4
        )
        self._press_at = None
        if event.button() == Qt.MouseButton.RightButton and not dragged:
            if self._picking_plane:
                self.plane_pick_cancelled.emit()
            else:
                self.marking_menu_requested.emit(event.globalPosition().toPoint())
            self.cursor = "arrow"
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if dragged:
                self._on_left_release()
                self.cursor = "arrow"
                return
            pos = event.position().toPoint()
            context = self._display.Context
            context.MoveTo(pos.x(), pos.y(), self._display.View, False)
            if context.HasDetected():
                detected = context.DetectedOwner()
                if detected.IsKind("AIS_ViewCubeOwner"):
                    owner = AIS_ViewCubeOwner.DownCast(detected)
                    self._cube.HandleClick(owner)
                    self._display.Repaint()
                    self.cursor = "arrow"
                    return
            if self._navigation_mode != "orbit":
                self._on_left_release()
                self.cursor = "arrow"
                return
        super().mouseReleaseEvent(event)

    def show_model(
        self,
        solid: TopoDS_Shape | None,
        sketches: list[TopoDS_Shape],
        planes: bool = True,
        fit: bool = False,
        threads: list[TopoDS_Shape] | None = None,
    ) -> None:
        """Replace what's on screen: the body, sketch wires, base planes and origin axes."""
        display = self._display
        display.Context.RemoveAll(False)
        self._plane_shapes.clear()
        size = _model_size(solid)
        if planes:
            self._show_planes(size)
            trihedron = AIS_Trihedron(Geom_Axis2Placement(gp_Ax2()))
            trihedron.SetSize(size * 0.6)
            trihedron.SetXAxisColor(_color(theme.VIEW_AXIS_X))
            trihedron.SetYAxisColor(_color(theme.VIEW_AXIS_Y))
            trihedron.SetAxisColor(_color(theme.VIEW_AXIS_Z))
            trihedron.SetTextColor(_color(theme.VIEW_EDGE))
            display.Context.Display(trihedron, False)
        if solid is not None:
            body = display.DisplayShape(
                solid, material=Graphic3d_NOM_PLASTER, color=_color(theme.VIEW_BODY), update=False
            )[0]
            body.Attributes().SetFaceBoundaryDraw(True)
            body.Attributes().SetFaceBoundaryAspect(
                Prs3d_LineAspect(_color(theme.VIEW_EDGE), Aspect_TOL_SOLID, 1.0)
            )
            display.Context.Redisplay(body, False)
        for wires in sketches:
            display.DisplayShape(wires, color=SKETCH_COLOR, update=False)
        for strokes in threads or []:
            item = display.DisplayShape(strokes, color=_color(theme.VIEW_THREAD), update=False)[0]
            display.Context.Deactivate(item)
        if fit:
            display.FitAll()
        display.SetSelectionModeFace()  # clicks pick faces (to sketch on)
        self.set_mode(self._display_mode)
        display.Context.Display(self._cube, False)
        display.Context.Deactivate(self._cube)
        display.Context.Activate(self._cube, 0, False)
        display.Repaint()

    def _show_planes(self, size: float) -> None:
        for name, color in theme.VIEW_PLANES.items():
            face = BRepBuilderAPI_MakeFace(
                gp_Pln(plane_axes(BASE_PLANES[name])), 0, size, 0, size
            ).Face()
            self._plane_shapes[name] = face
            plane = self._display.DisplayShape(
                face, color=_color(color), transparency=0.85, update=False
            )[0]
            plane.Attributes().SetFaceBoundaryDraw(True)
            plane.Attributes().SetFaceBoundaryAspect(
                Prs3d_LineAspect(_color(color), Aspect_TOL_SOLID, 1.0)
            )
            self._display.Context.Redisplay(plane, False)
            label = AIS_TextLabel()
            label.SetText(name)
            label.SetPosition(gp_Pnt(size, size, 0).Transformed(plane_trsf(BASE_PLANES[name])))
            label.SetColor(_color(color))
            label.SetFont(self._font)
            label.SetHeight(16)
            self._display.Context.Display(label, False)

    def plane_name(self, shape: TopoDS_Shape) -> str | None:
        """Return the base-plane name for a selected work-plane face."""
        return next((name for name, face in self._plane_shapes.items() if face.IsSame(shape)), None)

    def set_plane_pick(self, active: bool) -> None:
        """Control whether a right click cancels plane selection instead of opening a menu."""
        self._picking_plane = active

    def set_navigation_mode(self, mode: str) -> None:
        """Choose the action of a left drag; middle pan and right zoom remain available."""
        if mode not in ("orbit", "pan", "zoom"):
            raise ValueError(f"Unknown navigation mode: {mode}")
        self._navigation_mode = mode

    def look_at(self, placement: Placement, offset: float = 0.0) -> None:
        """Look directly at a sketch plane with its vertical axis pointing up."""
        self.stop_camera_animation()
        axes = plane_axes(placement, offset)
        normal, up = axes.Direction(), axes.YDirection()
        self._display.View.SetProj(normal.X(), normal.Y(), normal.Z())
        self._display.View.SetUp(up.X(), up.Y(), up.Z())
        self._display.FitAll()

    def animate_look_at(
        self, placement: Placement, offset: float = 0.0, *, empty_sketch: bool = False
    ) -> None:
        """Animate the camera from the current view to a sketch plane."""
        view = self._display.View
        start = Graphic3d_Camera()
        start.Copy(view.Camera())
        self.look_at(placement, offset)
        if empty_sketch:
            bounds = Bnd_Box()
            transform = plane_trsf(placement, offset)
            for x, y in ((-50, -50), (-50, 50), (50, -50), (50, 50)):
                bounds.Add(gp_Pnt(x, y, 0).Transformed(transform))
            view.FitAll(bounds, 0.1, True)
        else:
            view.FitAll(0.1, True)
        end = Graphic3d_Camera()
        end.Copy(view.Camera())
        view.SetCamera(start)
        animation = AIS_AnimationCamera("SketchView", view)
        animation.SetCameraStart(start)
        animation.SetCameraEnd(end)
        animation.SetOwnDuration(0.3)
        animation.StartTimer(0.0, 1.0, True)
        self._camera_animation = animation
        self._camera_end = end
        self._camera_timer.start(16)

    def _animate_camera(self) -> None:
        animation = self._camera_animation
        if animation is None:
            self._camera_timer.stop()
            return
        elapsed = animation.UpdateTimer()
        self._display.View.Redraw()
        if animation.IsStopped() or elapsed >= animation.Duration():
            self.stop_camera_animation()

    def stop_camera_animation(self) -> None:
        """Finish a running camera animation before accepting another command."""
        self._camera_timer.stop()
        if self._camera_animation is not None:
            self._camera_animation.Stop()
            if self._camera_end is not None:
                self._display.View.SetCamera(self._camera_end)
                self._display.View.MustBeResized()
                self._display.View.Redraw()
            self.camera_changed.emit()
        self._camera_animation = None
        self._camera_end = None

    def set_view(self, name: str) -> None:
        """Standard view: "front", "top", "right", "iso" or "fit"."""
        self.stop_camera_animation()
        display = self._display
        {
            "front": display.View_Front,
            "top": display.View_Top,
            "right": display.View_Right,
            "iso": display.View_Iso,
            "fit": lambda: None,
        }[name]()
        display.FitAll()
        self.camera_changed.emit()

    def set_mode(self, mode: str) -> None:
        """Set the model's shaded or wireframe display mode."""
        self._display_mode = mode
        {"shaded": self._display.SetModeShaded, "wireframe": self._display.SetModeWireFrame}[mode]()


def _model_size(solid: TopoDS_Shape | None) -> float:
    """A size for the planes and axes that suits the model (at least 30 mm)."""
    if solid is None:
        return 30.0
    box = Bnd_Box()
    brepbndlib.Add(solid, box)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return max(30.0, 0.7 * max(x1, y1, z1, -x0, -y0, -z0))
