"""Small dialogs: sketch plane and feature parameters."""

import copy
from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QWidget,
)

from sillycad.core.features import Pad, Pocket, Revolve, SketchFeature, SolidFeature
from sillycad.core.sketch import Line


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
        form.addRow("Plane:", self.plane)
        form.addRow("Offset:", self.offset)
        hint = QLabel("Tip: click a flat face in the 3D view first to sketch on it.")
        hint.setStyleSheet("color: gray;")
        form.addRow(hint)
        form.addRow(_buttons(self))

    def values(self) -> tuple[str, float]:
        """(plane, offset in mm)."""
        return self.plane.currentData(), self.offset.value()


class FeatureDialog(QDialog):
    """Edit a Pad, Pocket or Revolve. Every change is previewed in the 3D view.

    ``preview(feature)`` shows the trial feature and returns its error message, if any.
    """

    def __init__(
        self,
        feature: SolidFeature,
        sketches: list[SketchFeature],
        preview: Callable[[SolidFeature], str | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.feature = copy.deepcopy(feature)
        self._preview = preview
        self._sketches = {s.id: s for s in sketches}
        self.setWindowTitle(feature.name)
        form = QFormLayout(self)

        self.sketch = QComboBox()
        for s in sketches:
            self.sketch.addItem(s.name, s.id)
        self.sketch.setCurrentIndex(max(0, self.sketch.findData(feature.sketch_id)))
        self.sketch.currentIndexChanged.connect(self._changed)
        form.addRow("Sketch:", self.sketch)

        f = self.feature
        if isinstance(f, Pad | Pocket):
            self.length = _number_box(f.length, 0.001, 100000, " mm")
            self.length.valueChanged.connect(self._changed)
            form.addRow("Length:", self.length)
        if isinstance(f, Pocket):
            self.through_all = self._check(form, "Through all", f.through_all)
        if isinstance(f, Pad):
            self.symmetric = self._check(form, "Symmetric to the sketch plane", f.symmetric)
        if isinstance(f, Pad | Pocket):
            self.reversed = self._check(form, "Reversed direction", f.reversed)
        if isinstance(f, Revolve):
            self.axis = QComboBox()
            self.axis.currentIndexChanged.connect(self._changed)
            self.angle = _number_box(f.angle, 0.001, 360, "°")
            self.angle.valueChanged.connect(self._changed)
            form.addRow("Axis:", self.axis)
            form.addRow("Angle:", self.angle)
            self._fill_axes()

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #d62828;")
        form.addRow(self.message)
        form.addRow(_buttons(self))
        self._changed()

    def _check(self, form: QFormLayout, text: str, value: bool) -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(value)
        box.toggled.connect(self._changed)
        form.addRow(box)
        return box

    def _fill_axes(self) -> None:
        """Axis choices: the sketch axes plus the sketch's construction lines."""
        current = self.axis.currentData() or self.feature.axis
        sketch = self._sketches.get(self.sketch.currentData())
        self.axis.blockSignals(True)
        self.axis.clear()
        self.axis.addItem("Sketch vertical axis (Y)", "y_axis")
        self.axis.addItem("Sketch horizontal axis (X)", "x_axis")
        if sketch:
            for g in sketch.sketch.geo.values():
                if isinstance(g, Line) and g.construction:
                    self.axis.addItem(f"Construction line {g.id}", g.id)
        self.axis.setCurrentIndex(max(0, self.axis.findData(current)))
        self.axis.blockSignals(False)

    def _changed(self) -> None:
        f = self.feature
        f.sketch_id = self.sketch.currentData()
        if isinstance(f, Pad | Pocket):
            f.length = self.length.value()
            f.reversed = self.reversed.isChecked()
        if isinstance(f, Pocket):
            f.through_all = self.through_all.isChecked()
            self.length.setEnabled(not f.through_all)
        if isinstance(f, Pad):
            f.symmetric = self.symmetric.isChecked()
            self.reversed.setEnabled(not f.symmetric)
        if isinstance(f, Revolve):
            self._fill_axes()
            f.axis = self.axis.currentData()
            f.angle = self.angle.value()
        error = self._preview(copy.deepcopy(f))
        self.message.setText(f"⚠ {error}" if error else "")


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
    return buttons
