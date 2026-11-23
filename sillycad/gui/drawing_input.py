"""Small in-viewport fields for dimensions while drawing."""

import math

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget


class DrawingField(QLineEdit):
    """A dimension entry that leaves drawing completion to its controller."""

    next_field = Signal(bool)
    confirm = Signal()
    cancel = Signal()
    control_changed = Signal(bool)
    history = Signal(bool)
    finish_sketch = Signal()
    tool_requested = Signal(str)

    def event(self, event: QEvent) -> bool:
        if (
            isinstance(event, QKeyEvent)
            and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
            and event.key() == Qt.Key.Key_Control
        ):
            self.control_changed.emit(event.type() == QEvent.Type.KeyPress)
        if isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.finish_sketch.emit()
                    return True
                if event.key() == Qt.Key.Key_Z:
                    self.history.emit(bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                    return True
                if event.key() == Qt.Key.Key_Y:
                    self.history.emit(True)
                    return True
            if not event.modifiers() and event.key() in (
                Qt.Key.Key_L,
                Qt.Key.Key_C,
                Qt.Key.Key_A,
                Qt.Key.Key_P,
            ):
                self.tool_requested.emit(
                    {
                        Qt.Key.Key_L: "line",
                        Qt.Key.Key_C: "circle",
                        Qt.Key.Key_A: "arc",
                        Qt.Key.Key_P: "point",
                    }[event.key()]
                )
                return True
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self.next_field.emit(event.key() == Qt.Key.Key_Backtab)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.confirm.emit()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.cancel.emit()
                return True
        return super().event(event)


class DrawingInput(QObject):
    """Manage live measurement fields without making unedited values constraints."""

    changed = Signal()
    confirm = Signal()
    cancel = Signal()
    control_changed = Signal(bool)
    history = Signal(bool)
    finish_sketch = Signal()
    tool_requested = Signal(str)

    def __init__(self, viewer: QWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.fields: dict[str, DrawingField] = {}
        self.dirty: set[str] = set()

    def begin(self, names: tuple[str, ...]) -> None:
        """Show fields and let typing start immediately."""
        self.clear()
        for name in names:
            field = DrawingField(self.viewer)
            field.setObjectName("drawingDimension")
            field.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            field.setFixedWidth(92)
            field.setToolTip(f"{name.capitalize()} — type a value; Tab switches, Enter confirms")
            field.textEdited.connect(lambda _text, key=name: self._edited(key))
            field.next_field.connect(lambda backwards, key=name: self._next(key, backwards))
            field.confirm.connect(self.confirm)
            field.cancel.connect(self.cancel)
            field.control_changed.connect(self.control_changed)
            field.history.connect(self.history)
            field.finish_sketch.connect(self.finish_sketch)
            field.tool_requested.connect(self.tool_requested)
            self.fields[name] = field
            field.show()
        if names:
            self.fields[names[0]].setFocus()
            self.fields[names[0]].selectAll()

    def _edited(self, name: str) -> None:
        self.dirty.add(name)
        self.changed.emit()

    def _next(self, name: str, backwards: bool) -> None:
        names = list(self.fields)
        index = (names.index(name) + (-1 if backwards else 1)) % len(names)
        self.fields[names[index]].setFocus()
        self.fields[names[index]].selectAll()

    def update(self, measurements: dict[str, tuple[float, QPointF]]) -> None:
        """Update unedited measurements and move fields to projected anchors."""
        for name, (value, position) in measurements.items():
            field = self.fields.get(name)
            if field is None:
                continue
            if name not in self.dirty:
                field.setText(f"{value:.3f}".rstrip("0").rstrip(".") or "0")
                if field.hasFocus():
                    field.selectAll()
            x = max(0, min(self.viewer.width() - field.width(), round(position.x())))
            y = max(0, min(self.viewer.height() - field.height(), round(position.y())))
            field.move(x, y)
            field.raise_()

    def values(self, *, strict: bool = False) -> dict[str, float]:
        """Return edited valid numbers; invalid text prevents a strict commit."""
        values = {}
        for name in self.dirty:
            try:
                value = float(self.fields[name].text())
                if not math.isfinite(value):
                    raise ValueError
                if name in ("width", "height", "length", "radius") and value <= 0:
                    raise ValueError
                if name == "sweep" and not 0 < value < 360:
                    raise ValueError
            except ValueError:
                if strict:
                    raise ValueError(f"Enter a valid {name} value.") from None
                continue
            values[name] = value
        return values

    def clear(self) -> None:
        """Remove the fields without changing the sketch."""
        for field in self.fields.values():
            field.hide()
            field.deleteLater()
        self.fields.clear()
        self.dirty.clear()
