"""Undo/redo commands."""

import copy
from collections.abc import Callable
from typing import Any

from PySide6.QtGui import QUndoCommand


class SnapshotCommand(QUndoCommand):
    """Undo/redo by swapping whole-state snapshots. Simple and hard to get wrong.

    The change has already been applied when the command is pushed, so the
    first redo() (which QUndoStack.push calls) does nothing.
    """

    def __init__(self, text: str, before: Any, after: Any, restore: Callable[[Any], None]) -> None:
        super().__init__(text)
        self._before, self._after, self._restore = before, after, restore
        self._first = True

    def redo(self) -> None:
        if self._first:
            self._first = False
            return
        self._restore(copy.deepcopy(self._after))

    def undo(self) -> None:
        self._restore(copy.deepcopy(self._before))
