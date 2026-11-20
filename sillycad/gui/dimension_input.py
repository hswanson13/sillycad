"""Small opaque in-canvas editor for sketch dimension values."""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget

from sillycad.core.sketch import check_value


class DimensionInput(QLineEdit):
    """Edit a dimension without opening a modal dialog."""

    committed = Signal(float)
    invalid = Signal(str)

    def __init__(
        self, kind: str, value: float, position: QPoint, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setText(f"{value:g}")
        self.setToolTip("Enter a value and press Enter; Esc cancels.")
        self.setFixedWidth(110)
        self.move(position)
        self.returnPressed.connect(self._commit)

    def _commit(self) -> None:
        try:
            value = float(self.text())
            check_value(self.kind, value)
        except ValueError as exc:
            self.invalid.emit(str(exc))
            self.selectAll()
            return
        self.committed.emit(value)
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
