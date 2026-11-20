"""Small dialogs for sketch planes and STL export."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QWidget,
)

from sillycad.gui.tooltips import tooltip


class SketchPlaneDialog(QDialog):
    """Choose the plane and offset for a sketch.

    ``has_face`` adds a "Picked face" choice: the plane of a face clicked in 3D.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        plane: str = "XY",
        offset: float = 0.0,
        has_face: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sketch plane")
        form = QFormLayout(self)
        self.plane = QComboBox()
        for key, text in (("XY", "XY (top)"), ("XZ", "XZ (front)"), ("YZ", "YZ (right)")):
            self.plane.addItem(text, key)
        if has_face:
            self.plane.addItem("Picked face", "Face")
        self.plane.setCurrentIndex(max(0, self.plane.findData(plane)))
        self.offset = _number_box(offset, -100000, 100000, " mm")
        self.plane.setToolTip(tooltip("Plane", "Choose the sketch plane"))
        self.offset.setToolTip(tooltip("Offset", "Set the offset from the selected plane"))
        form.addRow("Plane:", self.plane)
        form.addRow("Offset:", self.offset)
        hint = QLabel("Tip: click a flat face in the 3D view first to sketch on it.")
        hint.setObjectName("hintLabel")
        form.addRow(hint)
        form.addRow(_buttons(self))

    def values(self) -> tuple[str, float]:
        """(plane, offset in mm)."""
        return self.plane.currentData(), self.offset.value()


def _number_box(value: float, low: float, high: float, suffix: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(low, high)
    box.setDecimals(3)
    box.setSuffix(suffix)
    box.setValue(value)
    return box


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setToolTip(
        tooltip("OK", "Accept the settings", "Enter")
    )
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setToolTip(
        tooltip("Cancel", "Discard these settings", "Esc")
    )
    return buttons


class StlDialog(QDialog):
    """STL export quality. Smaller numbers give a smoother, bigger file."""

    def __init__(self, parent: QWidget | None, linear: float, angular: float) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export STL")
        form = QFormLayout(self)
        self.linear = _number_box(linear, 0.001, 10, " mm")
        self.linear.setToolTip(
            tooltip("Linear deflection", "Set how far triangles may stray from the surface")
        )
        self.angular = _number_box(angular, 1, 45, "°")
        self.angular.setToolTip(
            tooltip("Angular deflection", "Set how sharply neighbouring triangles may bend")
        )
        form.addRow("Linear deflection:", self.linear)
        form.addRow("Angular deflection:", self.angular)
        hint = QLabel("Smaller = smoother curves and a bigger file. The defaults suit 3D printing.")
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        form.addRow(hint)
        form.addRow(_buttons(self))

    def values(self) -> tuple[float, float]:
        """(linear deflection in mm, angular deflection in degrees)."""
        return self.linear.value(), self.angular.value()
