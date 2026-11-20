"""Editable sketch state shared by the native viewport and sketch controls."""

import copy
import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

from sillycad.core.profiles import ProfileError, find_profiles
from sillycad.core.sketch import DIMENSIONS, RULES, XY, Sketch, label
from sillycad.core.solver import SolveResult, drag, solve
from sillycad.gui.commands import SnapshotCommand
from sillycad.sketch_math import infer_dimension

log = logging.getLogger(__name__)


class SketchSession(QObject):
    """Edit a sketch copy with its own solver feedback and undo stack."""

    changed = Signal()
    message = Signal(str)

    def __init__(
        self, sketch: Sketch, reference: list[list[XY]] | None = None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.sketch = copy.deepcopy(sketch)
        self.reference = reference or []
        self.selection: list[str] = []
        self.result = SolveResult(True, 0)
        self.bad_constraints: set[str] = set()
        self.bad_geometry: set[str] = set()
        self.problems: list[XY] = []
        self.profile_text = ""
        self.undo_stack = QUndoStack(self)
        self._analyse()

    def _analyse(self) -> None:
        self.result = solve(self.sketch)
        self.bad_constraints = set(self.result.conflicting) | set(self.result.redundant)
        self.bad_geometry = {
            ref for cid in self.bad_constraints for ref in self.sketch.constraints[cid].refs
        }
        try:
            count = len(find_profiles(self.sketch))
            self.profile_text = f"{count} closed profile{'s' if count != 1 else ''}"
            self.problems = []
        except ProfileError as exc:
            self.profile_text = str(exc)
            self.problems = exc.points
        except Exception as exc:  # OCCT failures must not hide the rest of the sketch
            log.exception("Profile check failed")
            self.profile_text = f"Profile check failed: {exc}"
            self.problems = []

    def highlighted(self) -> set[str]:
        """Return the selection plus geometry referred to by selected constraints."""
        selected = set(self.selection)
        for cid in self.selection:
            if cid in self.sketch.constraints:
                selected.update(self.sketch.constraints[cid].refs)
        return selected

    def set_selection(self, items: list[str]) -> None:
        """Select sketch geometry or constraints by stable ID."""
        self.selection = items
        self.changed.emit()

    def edit(self, text: str, change: Callable[[Sketch], None]) -> bool:
        """Apply one undoable edit, reporting invalid input without changing the sketch."""
        before = copy.deepcopy(self.sketch)
        try:
            change(self.sketch)
        except ValueError as exc:
            self.sketch = before
            self.message.emit(str(exc))
            return False
        self._analyse()
        self.undo_stack.push(
            SnapshotCommand(text, before, copy.deepcopy(self.sketch), self.restore)
        )
        self.selection = [
            item
            for item in self.selection
            if item in self.sketch.geo or item in self.sketch.constraints
        ]
        self.changed.emit()
        return True

    def restore(self, sketch: Sketch) -> None:
        """Restore a snapshot after a local undo or redo."""
        self.sketch = sketch
        self._analyse()
        self.selection = [
            item
            for item in self.selection
            if item in self.sketch.geo or item in self.sketch.constraints
        ]
        self.changed.emit()

    def constraint_trial(self, kind: str) -> tuple[str, list[str], float | None]:
        """Validate a selected constraint and return its initial measured value."""
        refs = [item for item in self.selection if item not in self.sketch.constraints]
        if kind == "smart":
            kind = infer_dimension(self.sketch, refs)
        if not refs:
            raise ValueError(f"{label(kind)}: select {RULES[kind][0]} first.")
        trial = copy.deepcopy(self.sketch)
        cid = trial.add_constraint(kind, refs)
        return kind, refs, trial.constraints[cid].value

    def add_constraint(self, kind: str, refs: list[str], value: float | None = None) -> bool:
        """Add an already validated constraint or dimension as one local edit."""
        added = self.edit(
            f"Add {label(kind)}", lambda sketch: sketch.add_constraint(kind, refs, value)
        )
        if added:
            self.set_selection([])
        return added

    def change_dimension(self, cid: str, value: float) -> bool:
        """Change an existing dimension as one local edit."""
        constraint = self.sketch.constraints.get(cid)
        if constraint is None or constraint.kind not in DIMENSIONS:
            self.message.emit("Select a dimension to edit.")
            return False
        return self.edit(
            f"Change {label(constraint.kind)}", lambda sketch: sketch.set_value(cid, value)
        )

    def delete_selection(self) -> None:
        """Delete selected geometry or constraints and their dependencies."""
        if not self.selection:
            self.message.emit("Select something to delete first.")
            return
        selected = list(self.selection)
        if self.edit("Delete", lambda sketch: sketch.delete(selected)):
            self.set_selection([])

    def toggle_construction(self) -> None:
        """Toggle construction status on selected curves."""
        selected = list(self.selection)
        self.edit("Toggle construction", lambda sketch: sketch.toggle_construction(selected))

    def start_drag(self) -> Sketch:
        """Snapshot the sketch before a continuous drag."""
        return copy.deepcopy(self.sketch)

    def drag_to(self, points: dict[str, XY], radii: dict[str, float] | None = None) -> None:
        """Move geometry with a live solve; do not create an undo step per frame."""
        if drag(self.sketch, points, radii):
            self.changed.emit()

    def finish_drag(self, before: Sketch) -> None:
        """Finish a continuous drag as one local undo step."""
        if self.sketch == before:
            return
        self._analyse()
        self.undo_stack.push(
            SnapshotCommand("Drag", before, copy.deepcopy(self.sketch), self.restore)
        )
        self.changed.emit()
