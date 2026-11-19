"""Sketch editor window: toolbars, constraint list, status and undo.

Every change goes through ``edit()``: snapshot, change, re-solve, push an
undo command. A solve that fails leaves the geometry at its last good state.
"""

import copy
import logging
from collections import Counter
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QShowEvent, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from sillycad.core.profiles import ProfileError, find_profiles
from sillycad.core.sketch import DIMENSIONS, RULES, XY, Constraint, Sketch, check_value, label
from sillycad.core.solver import SolveResult, drag, solve
from sillycad.gui.commands import SnapshotCommand
from sillycad.gui.sketch_view import BAD, DONE, SketchView

log = logging.getLogger(__name__)

TOOLS = {
    "select": ("Select", "", "Click to select (Shift/Ctrl adds more). Drag to move geometry."),
    "point": ("Point", "P", "Click to place a point."),
    "line": ("Line", "L", "Click the start, then the end. Keeps going; right-click or Esc stops."),
    "arc": ("Arc", "A", "Click the center, the start, then the end (counter-clockwise)."),
    "circle": ("Circle", "C", "Click the center, then a point on the rim."),
}
CONSTRAINT_KEYS = {
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
DIMENSION_KEYS = {
    "distance": "D",
    "distance_x": "Shift+H",
    "distance_y": "Shift+V",
    "angle": "Shift+A",
    "radius": "R",
    "diameter": "Shift+D",
}


class SketchEditor(QMainWindow):
    """Edits a copy of a sketch. Emits ``finished(sketch)`` when the user clicks Finish."""

    finished = Signal(object)

    def __init__(self, sketch: Sketch, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sketch: {title}")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.sketch = copy.deepcopy(sketch)
        self.selection: list[str] = []
        self.result = SolveResult(True, 0)
        self.bad_constraints: set[str] = set()
        self.bad_geometry: set[str] = set()
        self.problems: list[XY] = []  # profile trouble spots, drawn as red rings
        self.profile_text = ""
        self.undo_stack = QUndoStack(self)
        self._finishing = False
        self._fitted = False

        self.view = SketchView(self)
        self.setCentralWidget(self.view)
        self._build_side_panel()
        self.status = QLabel()
        self.statusBar().addPermanentWidget(self.status)
        self._build_toolbars()
        self._analyse()
        self.refresh()
        self.resize(1300, 850)
        self.flash("Pick a tool to draw. Select things, then click a constraint.")

    # ── Building the window ─────────────────────────────────────────

    def _build_side_panel(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.profile_info = QLabel()
        self.profile_info.setWordWrap(True)
        self.constraint_list = QListWidget()
        self.constraint_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.constraint_list.itemSelectionChanged.connect(self._list_selection_changed)
        self.constraint_list.itemDoubleClicked.connect(
            lambda item: self.edit_dimension(item.data(Qt.ItemDataRole.UserRole))
        )
        layout.addWidget(self.info)
        layout.addWidget(self.profile_info)
        layout.addWidget(QLabel("<b>Constraints</b> (double-click a dimension to change it)"))
        layout.addWidget(self.constraint_list)
        dock = QDockWidget("Sketch status", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setWidget(panel)
        dock.setMinimumWidth(280)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _action(
        self, bar: QToolBar | None, text: str, key: str, slot: Callable[[], object], tip: str
    ) -> QAction:
        action = QAction(text, self)
        if key:
            action.setShortcut(QKeySequence(key))
        action.setToolTip(f"{text} ({key}): {tip}" if key else f"{text}: {tip}")
        action.triggered.connect(lambda _checked=False: slot())
        (bar or self).addAction(action)
        return action

    def _build_toolbars(self) -> None:
        bar = self.addToolBar("Sketch")
        bar.setMovable(False)
        self._action(bar, "✔ Finish", "Ctrl+Return", self.finish, "save the sketch and close")
        self._action(bar, "Cancel", "", self.close, "close without saving")
        bar.addSeparator()
        group = QActionGroup(self)
        self.tool_actions: dict[str, QAction] = {}
        for name, (text, key, tip) in TOOLS.items():
            action = self._action(bar, text, key, lambda n=name: self.set_tool(n), tip)
            action.setCheckable(True)
            group.addAction(action)
            self.tool_actions[name] = action
        self.tool_actions["select"].setChecked(True)
        self._action(
            bar, "Construction", "G", self.toggle_construction,
            "toggle construction on the selected curves (they're ignored for profiles)",
        )  # fmt: skip
        bar.addSeparator()
        undo = self.undo_stack.createUndoAction(self, "Undo")
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        redo = self.undo_stack.createRedoAction(self, "Redo")
        redo.setShortcuts([QKeySequence(QKeySequence.StandardKey.Redo), QKeySequence("Ctrl+Y")])
        bar.addAction(undo)
        bar.addAction(redo)
        self._action(bar, "Delete", "Del", self.delete_selection, "delete the selection")
        self._action(bar, "Fit", "Home", self.view.fit, "zoom to fit the sketch")
        self._action(None, "Escape", "Esc", self.view.escape, "cancel / back to Select")

        self.addToolBarBreak()
        bar = self.addToolBar("Constraints")
        bar.setMovable(False)
        for kind, key in CONSTRAINT_KEYS.items():
            tip = f"select {RULES[kind][0]}"
            self._action(bar, label(kind), key, lambda k=kind: self.add_constraint(k), tip)
        bar.addSeparator()
        for kind, key in DIMENSION_KEYS.items():
            tip = f"select {RULES[kind][0]}"
            self._action(bar, label(kind), key, lambda k=kind: self.add_constraint(k), tip)

    # ── State ───────────────────────────────────────────────────────

    def flash(self, message: str) -> None:
        """Show a short message in the status bar."""
        self.statusBar().showMessage(message, 8000)

    def highlighted(self) -> set[str]:
        """Selected IDs, plus everything the selected constraints refer to."""
        ids = set(self.selection)
        for cid in self.selection:
            if cid in self.sketch.constraints:
                ids |= set(self.sketch.constraints[cid].refs)
        return ids

    def set_tool(self, name: str) -> None:
        self.view.tool = name
        self.view.clicks = []
        self.tool_actions[name].setChecked(True)
        drawing = name != "select"
        self.view.setCursor(Qt.CursorShape.CrossCursor if drawing else Qt.CursorShape.ArrowCursor)
        self.flash(f"{TOOLS[name][0]}: {TOOLS[name][2]}")
        self.view.redraw()

    def set_selection(self, ids: list[str]) -> None:
        self.selection = ids
        self._sync_list_selection()
        self.view.redraw()
        if ids:
            kinds = Counter(
                "constraint" if i in self.sketch.constraints else self.sketch.ref_type(i)
                for i in ids
            )
            names = {"round": "circle/arc"}
            parts = [f"{n} {names.get(k, k)}{'s' if n > 1 else ''}" for k, n in kinds.items()]
            self.flash("Selected: " + ", ".join(parts))

    def _analyse(self) -> None:
        """Solve, find bad constraints, and check profiles."""
        self.result = solve(self.sketch)
        self.bad_constraints = set(self.result.conflicting) | set(self.result.redundant)
        self.bad_geometry = {
            ref for cid in self.bad_constraints for ref in self.sketch.constraints[cid].refs
        }
        try:
            count = len(find_profiles(self.sketch))
            self.profile_text = f"✔ {count} closed profile{'s' if count != 1 else ''}"
            self.problems = []
        except ProfileError as exc:
            self.profile_text = str(exc)
            self.problems = exc.points
        except Exception as exc:  # OCCT trouble: report, don't crash
            log.exception("Profile check failed")
            self.profile_text = f"Profile check failed: {exc}"
            self.problems = []

    def refresh(self) -> None:
        """Redraw everything from the model."""
        self.selection = [
            i for i in self.selection if i in self.sketch.geo or i in self.sketch.constraints
        ]
        self.view.redraw()
        self._fill_list()
        r = self.result
        if r.fully_constrained:
            short, color = "✔ Fully constrained", DONE.name()
        elif not r.ok:
            short, color = "⚠ Constraint problem (see right)", BAD.name()
        else:
            short, color = f"Degrees of freedom: {r.dof}", "palette(text)"
        self.status.setText(short)
        self.status.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.info.setText(r.message)
        self.info.setStyleSheet(f"color: {color};")
        self.profile_info.setText(self.profile_text)

    def _fill_list(self) -> None:
        lst = self.constraint_list
        lst.blockSignals(True)
        lst.clear()
        for c in self.sketch.constraints.values():
            item = QListWidgetItem(f"{_describe(c)}   ({c.id})")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            if c.id in self.bad_constraints:
                item.setForeground(BAD)
            lst.addItem(item)
            item.setSelected(c.id in self.selection)
        lst.blockSignals(False)

    def _sync_list_selection(self) -> None:
        lst = self.constraint_list
        lst.blockSignals(True)
        for row in range(lst.count()):
            item = lst.item(row)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) in self.selection)
        lst.blockSignals(False)

    def _list_selection_changed(self) -> None:
        items = self.constraint_list.selectedItems()
        self.selection = [item.data(Qt.ItemDataRole.UserRole) for item in items]
        self.view.redraw()

    # ── Edits ───────────────────────────────────────────────────────

    def edit(self, text: str, change: Callable[[Sketch], None]) -> bool:
        """Apply ``change`` as one undoable step. Returns False if it was refused."""
        before = copy.deepcopy(self.sketch)
        try:
            change(self.sketch)
        except ValueError as exc:  # invalid selection or value: explain, change nothing
            self.sketch = before
            self.flash(str(exc))
            return False
        self._analyse()
        self.undo_stack.push(
            SnapshotCommand(text, before, copy.deepcopy(self.sketch), self.restore)
        )
        self.refresh()
        return True

    def restore(self, sketch: Sketch) -> None:
        """Undo/redo: put back a snapshot."""
        self.sketch = sketch
        self._analyse()
        self.refresh()

    def add_constraint(self, kind: str) -> None:
        refs = [i for i in self.selection if i not in self.sketch.constraints]
        if not refs:
            self.flash(f"{label(kind)}: select {RULES[kind][0]} first.")
            return
        trial = copy.deepcopy(self.sketch)
        try:
            cid = trial.add_constraint(kind, refs)
        except ValueError as exc:
            self.flash(str(exc))
            return
        value = None
        if kind in DIMENSIONS:  # ask right away, starting from the current measurement
            value = self._ask_value(kind, trial.constraints[cid].value)
            if value is None:
                return
        if self.edit(f"Add {label(kind)}", lambda s: s.add_constraint(kind, refs, value)):
            self.set_selection([])

    def edit_dimension(self, cid: str | None) -> None:
        c = self.sketch.constraints.get(cid or "")
        if c is None or c.kind not in DIMENSIONS:
            return
        value = self._ask_value(c.kind, c.value)
        if value is not None:
            self.edit(f"Change {label(c.kind)}", lambda s: s.set_value(c.id, value))

    def _ask_value(self, kind: str, current: float) -> float | None:
        unit = "°" if kind == "angle" else "mm"
        value, ok = QInputDialog.getDouble(
            self, label(kind), f"{label(kind)} ({unit}):", current, -1e6, 1e6, 3
        )
        if not ok:
            return None
        try:
            check_value(kind, value)
        except ValueError as exc:
            self.flash(str(exc))
            return None
        return value

    def delete_selection(self) -> None:
        if not self.selection:
            self.flash("Select something to delete first.")
            return
        ids = list(self.selection)
        if self.edit("Delete", lambda s: s.delete(ids)):
            self.set_selection([])

    def toggle_construction(self) -> None:
        ids = list(self.selection)
        self.edit("Toggle construction", lambda s: s.toggle_construction(ids))

    # ── Dragging (called by the view) ───────────────────────────────

    def start_drag(self) -> Sketch:
        return copy.deepcopy(self.sketch)

    def drag_to(self, points: dict[str, XY], radii: dict[str, float] | None = None) -> None:
        if drag(self.sketch, points, radii):
            self.view.redraw()

    def finish_drag(self, before: Sketch) -> None:
        if self.sketch == before:
            return
        self._analyse()
        self.undo_stack.push(
            SnapshotCommand("Drag", before, copy.deepcopy(self.sketch), self.restore)
        )
        self.refresh()

    # ── Window ──────────────────────────────────────────────────────

    def finish(self) -> None:
        self._finishing = True
        self.finished.emit(copy.deepcopy(self.sketch))
        self.close()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            self.view.fit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._finishing and not self.undo_stack.isClean():
            answer = QMessageBox.question(
                self, "Discard sketch changes?", "Close the sketch without saving your changes?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()


def _describe(c: Constraint) -> str:
    if c.kind not in DIMENSIONS:
        return label(c.kind)
    unit = "°" if c.kind == "angle" else " mm"
    return f"{label(c.kind)} = {round(c.value, 3):g}{unit}"
