"""Contextual sketch controls and editing session in the main window."""

import copy
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sillycad.core.features import SketchFeature
from sillycad.core.sketch import DIMENSIONS, RULES, Arc, Circle, Line, label
from sillycad.gui import theme
from sillycad.gui.dimension_input import DimensionInput
from sillycad.gui.icons import icon
from sillycad.gui.marking_menu import MarkingMenu
from sillycad.gui.sketch_interaction import SketchInteraction
from sillycad.gui.sketch_scene import SketchScene
from sillycad.gui.sketch_session import SketchSession
from sillycad.gui.tooltips import tooltip
from sillycad.sketch_math import dimension_anchor

if TYPE_CHECKING:
    from sillycad.gui.main_window import MainWindow

_TOOLS = {
    "select": ("Select", "", "Select and drag sketch geometry"),
    "line": ("Line", "L", "Draw connected line segments"),
    "rectangle": ("Rectangle", "", "Drag between opposite corners"),
    "circle": ("Circle", "C", "Draw a circle by center and radius"),
    "arc": ("Arc", "A", "Draw an arc by center, start and end"),
    "point": ("Point", "P", "Place a sketch point"),
}
_CONSTRAINTS = {
    "coincident": "I",
    "horizontal": "H",
    "vertical": "V",
    "parallel": "Shift+P",
    "perpendicular": "N",
    "equal": "E",
    "point_on_line": "O",
    "tangent": "T",
    "midpoint": "M",
    "fix": "F",
}
_DIMENSIONS = {
    "distance": "",
    "distance_x": "Shift+H",
    "distance_y": "Shift+V",
    "angle": "Shift+A",
    "radius": "R",
    "diameter": "Shift+D",
}


class SketchMode(QObject):
    """Own one local sketch editing session and its contextual UI."""

    finished = Signal(object, bool)

    def __init__(self, window: "MainWindow", feature: SketchFeature, new: bool) -> None:
        super().__init__(window)
        self.window, self.feature, self.new = window, feature, new
        self._previous_navigation = next(
            (key for key in ("orbit", "pan", "zoom") if window.actions[key].isChecked()), "orbit"
        )
        self.session = SketchSession(feature.sketch, window._outline(feature), self)
        self.actions: dict[str, QAction] = {}
        self._navigation_connections = []
        self._dimension_input: DimensionInput | None = None
        window.viewer.show_model(window.model.shape, [], planes=False)
        self.scene = SketchScene(window.viewer, self.session, feature.placement(), feature.offset)
        window.viewer.camera_changed.connect(self.scene.update_grid)
        self.interaction = SketchInteraction(self.scene, self)
        self._build_actions()
        self._build_status()
        self.session.changed.connect(self._refresh_status)
        self.session.message.connect(window.statusBar().showMessage)
        self.session.undo_stack.cleanChanged.connect(window._update_title)
        self.interaction.coordinates.connect(self._coordinates)
        self.interaction.edit_dimension.connect(self._edit_dimension)
        self.interaction.marking_menu.connect(self._marking_menu)
        self.interaction.tool_changed.connect(self._tool_changed)
        window.undo_group.addStack(self.session.undo_stack)
        window.undo_group.setActiveStack(self.session.undo_stack)
        for key in (
            "new",
            "open",
            "save",
            "save_as",
            "export",
            "new_sketch",
            "sketch_offset",
            "extrude",
            "pad",
            "pocket",
            "revolve",
            "sketches",
            "planes",
            "shaded",
            "wireframe",
        ):
            window.actions[key].setEnabled(False)
        window.actions["fit"].setShortcuts([QKeySequence("Home")])
        window.tree.setEnabled(False)
        window.ribbon.show_sketch(self.actions)
        window._cancel_shortcut.activated.connect(self.interaction.escape)
        for mode in ("orbit", "pan", "zoom"):
            action = window.actions[mode]

            def callback(_checked: bool = False, name: str = mode) -> None:
                self.interaction.set_navigation(name)

            action.triggered.connect(callback)
            self._navigation_connections.append((action, callback))
        self._refresh_status()
        self._tool_changed("select")
        window.statusBar().showMessage("Choose a sketch tool or select geometry.")
        self._camera_timer = QTimer(self)
        self._camera_timer.setSingleShot(True)
        self._camera_timer.timeout.connect(
            lambda: window.viewer.animate_look_at(
                feature.placement(),
                feature.offset,
                empty_sketch=window.model.shape is None and not self.session.sketch.geo,
            )
        )
        self._camera_timer.start(0)

    def _action(self, key: str, text: str, icon_name: str, shortcut: str, tip: str) -> QAction:
        action = QAction(icon(icon_name), text, self.window)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setToolTip(tooltip(text, tip, shortcut))
        self.window.addAction(action)
        self.actions[key] = action
        return action

    def _build_actions(self) -> None:
        group = QActionGroup(self)
        for name, (text, key, tip) in _TOOLS.items():
            action = self._action(name, text, name, key, tip)
            action.setCheckable(True)
            group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, tool=name: self.interaction.set_tool(tool)
            )
        self.actions["select"].setChecked(True)
        self._action(
            "finish", "Finish Sketch", "finish", "Ctrl+Return", "Save and leave the sketch"
        )
        self.actions["finish"].triggered.connect(
            lambda: self.finished.emit(self.session.sketch, True)
        )
        self._action("cancel", "Cancel Sketch", "delete", "", "Discard sketch changes")
        self.actions["cancel"].triggered.connect(self.cancel)
        self._action("delete", "Delete", "delete", "Del", "Delete selected geometry or constraints")
        self.actions["delete"].triggered.connect(self.session.delete_selection)
        self._action(
            "construction", "Construction", "construction", "G", "Toggle construction geometry"
        )
        self.actions["construction"].setCheckable(True)
        self.actions["construction"].triggered.connect(self._toggle_construction)
        self._action(
            "smart_dimension", "Dimension", "dimension", "D", "Dimension the selected geometry"
        )
        self.actions["smart_dimension"].triggered.connect(lambda: self._add_constraint("smart"))
        for kind, shortcut in _CONSTRAINTS.items():
            action = self._action(
                kind, label(kind), "constraint", shortcut, f"Select {RULES[kind][0]}"
            )
            action.triggered.connect(lambda _checked=False, name=kind: self._add_constraint(name))
        for kind, shortcut in _DIMENSIONS.items():
            action = self._action(
                kind, label(kind), "dimension", shortcut, f"Select {RULES[kind][0]}"
            )
            action.triggered.connect(lambda _checked=False, name=kind: self._add_constraint(name))
        action = self._action(
            "constraint_controls", "Constraints", "constraint", "", "Show constraint buttons"
        )
        action.setCheckable(True)
        action = self._action(
            "show_constraints", "Show Constraints", "constraint", "", "Show constraint glyphs"
        )
        action.setCheckable(True)
        action.setChecked(True)
        action.toggled.connect(self._show_constraints)
        for key, shortcut, visible in (("show_glyphs", "F8", True), ("hide_glyphs", "F9", False)):
            action = self._action(
                key,
                "Show Constraints" if visible else "Hide Constraints",
                "constraint",
                shortcut,
                "Change constraint glyph visibility",
            )
            action.triggered.connect(
                lambda _checked=False, show=visible: self.actions["show_constraints"].setChecked(
                    show
                )
            )

    def _build_status(self) -> None:
        self.dock = QDockWidget("Sketch status", self.window)
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.profile = QLabel()
        self.profile.setWordWrap(True)
        self.constraints = QListWidget()
        self.constraints.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.constraints.itemSelectionChanged.connect(self._select_constraints)
        self.constraints.itemDoubleClicked.connect(
            lambda item: self._edit_dimension(item.data(Qt.ItemDataRole.UserRole))
        )
        self.constraint_list_toggle = QToolButton()
        self.constraint_list_toggle.setText("Constraints")
        self.constraint_list_toggle.setToolTip(
            tooltip("Constraints", "Show or hide the list of sketch constraints")
        )
        self.constraint_list_toggle.setCheckable(True)
        self.constraint_list_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.constraint_list_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.constraint_list_toggle.toggled.connect(self.constraints.setVisible)
        self.constraint_list_toggle.toggled.connect(
            lambda visible: self.constraint_list_toggle.setArrowType(
                Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
            )
        )
        self.constraints.hide()
        layout.addWidget(self.info)
        layout.addWidget(self.profile)
        layout.addWidget(self.constraint_list_toggle)
        layout.addWidget(self.constraints)
        layout.addStretch()
        self.dock.setWidget(panel)
        self.window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.coordinates_label = QLabel("X: 0.000  Y: 0.000")
        self.window.statusBar().addPermanentWidget(self.coordinates_label)

    def _refresh_status(self) -> None:
        result = self.session.result
        self.info.setText(result.message)
        self.profile.setText(self.session.profile_text)
        if result.fully_constrained:
            self.window.volume_status.setText("Fully Constrained")
        elif result.conflicting or result.redundant:
            self.window.volume_status.setText("Over constrained")
        elif not result.solved:
            self.window.volume_status.setText("Solver problem")
        else:
            self.window.volume_status.setText(f"{result.dof} dimensions needed")
        self.constraints.blockSignals(True)
        self.constraints.clear()
        for constraint in self.session.sketch.constraints.values():
            text = label(constraint.kind)
            if constraint.value is not None:
                text += f" = {constraint.value:g}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, constraint.id)
            if constraint.id in self.session.bad_constraints:
                item.setForeground(QColor(theme.ERROR))
                item.setToolTip(self.session.result.message)
            self.constraints.addItem(item)
            item.setSelected(constraint.id in self.session.selection)
        self.constraints.blockSignals(False)
        curves = [
            geometry
            for gid in self.session.selection
            if isinstance((geometry := self.session.sketch.geo.get(gid)), Line | Circle | Arc)
        ]
        self.actions["construction"].setChecked(
            bool(curves) and all(curve.construction for curve in curves)
        )

    def _tool_changed(self, tool: str) -> None:
        self.actions[tool].setChecked(True)
        group = self.window._navigation_group
        group.setExclusive(False)
        for key in ("orbit", "pan", "zoom"):
            self.window.actions[key].setChecked(False)
        group.setExclusive(True)
        text, _, tip = _TOOLS[tool]
        self.window.statusBar().showMessage(f"{text}: {tip}.")

    def _toggle_construction(self) -> None:
        self.session.toggle_construction()
        self._refresh_status()

    def _coordinates(self, x: float, y: float) -> None:
        self.coordinates_label.setText(f"X: {x:.3f}  Y: {y:.3f}")

    def _select_constraints(self) -> None:
        self.session.set_selection(
            [item.data(Qt.ItemDataRole.UserRole) for item in self.constraints.selectedItems()]
        )

    def _show_constraints(self, visible: bool) -> None:
        self.scene.show_constraints = visible
        self.scene.redraw()

    def _add_constraint(self, kind: str) -> None:
        try:
            kind, refs, value = self.session.constraint_trial(kind)
        except ValueError as exc:
            self.window.statusBar().showMessage(str(exc), 8000)
            return
        if kind not in DIMENSIONS:
            self.session.add_constraint(kind, refs)
            return
        if value is None:
            self.window.statusBar().showMessage("The dimension has no measurable value.", 8000)
            return
        trial = copy.deepcopy(self.session.sketch)
        cid = trial.add_constraint(kind, refs)
        anchor = dimension_anchor(
            trial, trial.constraints[cid], self.window.viewer._display.View.Convert(24)
        )
        self._ask_dimension(
            kind, value, anchor, lambda number: self.session.add_constraint(kind, refs, number)
        )

    def _edit_dimension(self, cid: str) -> None:
        constraint = self.session.sketch.constraints.get(cid)
        if constraint is None or constraint.kind not in DIMENSIONS or constraint.value is None:
            return
        anchor = dimension_anchor(
            self.session.sketch, constraint, self.window.viewer._display.View.Convert(24)
        )
        self._ask_dimension(
            constraint.kind,
            constraint.value,
            anchor,
            lambda number: self.session.change_dimension(cid, number),
        )

    def _ask_dimension(
        self, kind: str, value: float, anchor: tuple[float, float], apply: Callable[[float], object]
    ) -> None:
        pos = self.window.viewer.mapToGlobal(self.scene.screen(anchor).toPoint())
        box = DimensionInput(kind, value, pos, self.window)
        box.committed.connect(apply)
        box.invalid.connect(lambda message: self.window.statusBar().showMessage(message, 8000))
        self._dimension_input = box

        def clear_input() -> None:
            if self._dimension_input is box:
                self._dimension_input = None

        box.destroyed.connect(clear_input)
        box.show()
        box.setFocus()
        box.selectAll()

    def _marking_menu(self, position: QPoint) -> None:
        actions = {**self.actions, "undo": self.window.actions["undo"]}
        MarkingMenu(actions, self.window, sketch=True).exec(position)

    def cancel(self) -> None:
        if self.session.undo_stack.isClean() or self.window.confirm_discard_sketch():
            self.finished.emit(self.session.sketch, False)

    def close(self) -> None:
        """Restore the part environment after finishing or cancelling."""
        if self._dimension_input is not None:
            self._dimension_input.close()
        self._camera_timer.stop()
        self.window.viewer.stop_camera_animation()
        self.window.viewer.camera_changed.disconnect(self.scene.update_grid)
        self.window._cancel_shortcut.activated.disconnect(self.interaction.escape)
        for action, callback in self._navigation_connections:
            action.triggered.disconnect(callback)
        self.window.actions[self._previous_navigation].trigger()
        self.interaction.close()
        self.window.undo_group.setActiveStack(self.window.undo_stack)
        self.window.undo_group.removeStack(self.session.undo_stack)
        self.window.ribbon.hide_sketch()
        for key in (
            "new",
            "open",
            "save",
            "save_as",
            "export",
            "new_sketch",
            "sketch_offset",
            "extrude",
            "pad",
            "pocket",
            "revolve",
            "sketches",
            "planes",
            "shaded",
            "wireframe",
        ):
            self.window.actions[key].setEnabled(True)
        self.window.actions["fit"].setShortcuts([QKeySequence("F"), QKeySequence("Home")])
        self.window.tree.setEnabled(True)
        for action in self.actions.values():
            self.window.removeAction(action)
            action.deleteLater()
        self.window.statusBar().removeWidget(self.coordinates_label)
        self.coordinates_label.deleteLater()
        self.window.removeDockWidget(self.dock)
        self.dock.deleteLater()
