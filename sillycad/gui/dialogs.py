"""Small dialogs."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QWidget,
)


class SketchPlaneDialog(QDialog):
    """Choose the base plane and offset for a new sketch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Sketch")
        form = QFormLayout(self)
        self.plane = QComboBox()
        for key, text in (("XY", "XY (top)"), ("XZ", "XZ (front)"), ("YZ", "YZ (right)")):
            self.plane.addItem(text, key)
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-100000, 100000)
        self.offset.setDecimals(3)
        self.offset.setSuffix(" mm")
        form.addRow("Plane:", self.plane)
        form.addRow("Offset:", self.offset)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[str, float]:
        """(plane, offset in mm)."""
        return self.plane.currentData(), self.offset.value()
