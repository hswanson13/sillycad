"""Dockable controls for creating and editing solid features."""

import copy
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sillycad.core.features import Pad, Pocket, Revolve, SketchFeature, SolidFeature
from sillycad.core.sketch import Line
from sillycad.gui.tooltips import tooltip


class FeaturePanel(QWidget):
    """Edit a solid feature, updating its preview without changing the document."""

    accepted = Signal(object)
    applied = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        feature: SolidFeature,
        sketches: list[SketchFeature],
        preview: Callable[[SolidFeature], str | None],
        *,
        editing: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("propertyPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.feature = copy.deepcopy(feature)
        self.editing = editing
        self._preview = preview
        self._sketches = {sketch.id: sketch for sketch in sketches}
        self._last_reversed = getattr(feature, "reversed", False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self.title = QLabel(feature.name)
        self.title.setObjectName("propertyTitle")
        layout.addWidget(self.title)

        profile = QGroupBox("Profile")
        form = QFormLayout(profile)
        self.sketch = QComboBox()
        for sketch in sketches:
            self.sketch.addItem(sketch.name, sketch.id)
        index = self.sketch.findData(feature.sketch_id)
        if index < 0:
            self.sketch.addItem(f"Missing sketch: {feature.sketch_id}", feature.sketch_id)
            index = self.sketch.count() - 1
        self.sketch.setCurrentIndex(index)
        self.sketch.setToolTip(
            tooltip("Profile", "Select the sketch whose closed profiles make the feature")
        )
        form.addRow("Sketch", self.sketch)
        layout.addWidget(profile)

        if isinstance(feature, Pad | Pocket):
            operation = QGroupBox("Operation")
            buttons = QHBoxLayout(operation)
            self.operations = QButtonGroup(self)
            self.join = QPushButton("Join")
            self.cut = QPushButton("Cut")
            for button, description in (
                (self.join, "Add the extrusion to the body"),
                (self.cut, "Subtract the extrusion from the body"),
            ):
                button.setObjectName("operationButton")
                button.setCheckable(True)
                button.setToolTip(tooltip(button.text(), description))
                self.operations.addButton(button)
                buttons.addWidget(button)
            self.join.setChecked(isinstance(feature, Pad))
            self.cut.setChecked(isinstance(feature, Pocket))
            if editing:
                self.join.setEnabled(isinstance(feature, Pad))
                self.cut.setEnabled(isinstance(feature, Pocket))
            layout.addWidget(operation)

            extent = QGroupBox("Extent")
            form = QFormLayout(extent)
            self.extent = QComboBox()
            self.length = _number_box(feature.length, 100000, " mm")
            self.length.setToolTip(tooltip("Distance", "Set the extrusion depth in millimetres"))
            form.addRow("Type", self.extent)
            form.addRow("Distance", self.length)
            layout.addWidget(extent)

            direction = QGroupBox("Direction")
            form = QFormLayout(direction)
            self.direction = QComboBox()
            self.direction.setToolTip(tooltip("Direction", "Choose the direction of the extrusion"))
            form.addRow("Direction", self.direction)
            layout.addWidget(direction)
            direction_value = (
                "symmetric"
                if isinstance(feature, Pad) and feature.symmetric
                else "flipped"
                if feature.reversed
                else "default"
            )
            extent_value = (
                "through_all" if isinstance(feature, Pocket) and feature.through_all else "distance"
            )
            self._extrude_choices(direction_value, extent_value)
        else:
            axis_group = QGroupBox("Axis")
            form = QFormLayout(axis_group)
            self.axis = QComboBox()
            self.axis.setToolTip(tooltip("Axis", "Choose a sketch axis or construction line"))
            form.addRow("Axis", self.axis)
            layout.addWidget(axis_group)

            extent = QGroupBox("Extent")
            form = QFormLayout(extent)
            self.extent = QComboBox()
            self.extent.addItem("Full", "full")
            self.extent.addItem("Angle", "angle")
            self.extent.setCurrentIndex(0 if feature.angle == 360 else 1)
            self.angle = _number_box(feature.angle, 360, "°")
            self.angle.setToolTip(tooltip("Angle", "Set the rotation in degrees"))
            form.addRow("Type", self.extent)
            form.addRow("Angle", self.angle)
            layout.addWidget(extent)
            self._fill_axes(feature.axis)

        self.extent.setToolTip(tooltip("Extent", "Choose how far the feature extends"))
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("errorLabel")
        layout.addWidget(self.message)
        layout.addStretch()

        buttons = QHBoxLayout()
        self.ok = QPushButton("OK")
        self.ok.setObjectName("primaryButton")
        self.ok.setToolTip(tooltip("OK", "Commit the feature and close the panel", "Ctrl+Enter"))
        self.cancel = QPushButton("Cancel")
        self.cancel.setToolTip(tooltip("Cancel", "Discard this preview", "Esc"))
        self.apply = QPushButton("Apply (+)")
        description = (
            "Apply changes and continue editing" if editing else "Create and start another feature"
        )
        self.apply.setToolTip(tooltip("Apply", description))
        for button in (self.ok, self.cancel, self.apply):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.ok.clicked.connect(self._accept)
        self.cancel.clicked.connect(self.cancelled)
        self.apply.clicked.connect(self._apply)
        shortcut = QShortcut(self)
        shortcut.setKeys([QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")])
        shortcut.activated.connect(self._accept)

        self.sketch.currentIndexChanged.connect(self._changed)
        self.extent.currentIndexChanged.connect(self._changed)
        if isinstance(feature, Pad | Pocket):
            self.operations.buttonClicked.connect(self._operation_changed)
            self.direction.currentIndexChanged.connect(self._changed)
            self.length.valueChanged.connect(self._changed)
        else:
            self.axis.currentIndexChanged.connect(self._changed)
            self.angle.valueChanged.connect(self._changed)
        self._changed()

    def _extrude_choices(self, direction: str, extent: str) -> None:
        self.direction.blockSignals(True)
        self.direction.clear()
        self.direction.addItem("Default", "default")
        self.direction.addItem("Flipped", "flipped")
        if self.join.isChecked():
            self.direction.addItem("Symmetric", "symmetric")
        self.direction.setCurrentIndex(max(0, self.direction.findData(direction)))
        self.direction.blockSignals(False)
        self.extent.blockSignals(True)
        self.extent.clear()
        self.extent.addItem("Distance", "distance")
        if self.cut.isChecked():
            self.extent.addItem("Through All", "through_all")
        self.extent.setCurrentIndex(max(0, self.extent.findData(extent)))
        self.extent.blockSignals(False)

    def _operation_changed(self) -> None:
        self._extrude_choices(self.direction.currentData(), self.extent.currentData())
        self._changed()

    def _fill_axes(self, current: str) -> None:
        self.axis.blockSignals(True)
        self.axis.clear()
        self.axis.addItem("Sketch vertical axis (Y)", "y_axis")
        self.axis.addItem("Sketch horizontal axis (X)", "x_axis")
        sketch = self._sketches.get(self.sketch.currentData())
        if sketch is not None:
            for geometry in sketch.sketch.geo.values():
                if isinstance(geometry, Line) and geometry.construction:
                    self.axis.addItem(f"Construction line {geometry.id}", geometry.id)
        index = self.axis.findData(current)
        if index < 0:
            self.axis.addItem(f"Missing construction line: {current}", current)
            index = self.axis.count() - 1
        self.axis.setCurrentIndex(index)
        self.axis.blockSignals(False)

    def _changed(self) -> None:
        feature = self.feature
        sketch_id = self.sketch.currentData()
        if isinstance(feature, Pad | Pocket):
            direction = self.direction.currentData()
            if direction != "symmetric":
                self._last_reversed = direction == "flipped"
            self.length.setEnabled(self.extent.currentData() == "distance")
            if self.join.isChecked():
                self.feature = Pad(
                    feature.id,
                    feature.name,
                    sketch_id,
                    length=self.length.value(),
                    reversed=self._last_reversed,
                    symmetric=direction == "symmetric",
                )
            else:
                self.feature = Pocket(
                    feature.id,
                    feature.name,
                    sketch_id,
                    length=self.length.value(),
                    through_all=self.extent.currentData() == "through_all",
                    reversed=self._last_reversed,
                )
        else:
            self._fill_axes(self.axis.currentData() or feature.axis)
            self.angle.setEnabled(self.extent.currentData() == "angle")
            self.feature = Revolve(
                feature.id,
                feature.name,
                sketch_id,
                axis=self.axis.currentData(),
                angle=self.angle.value() if self.angle.isEnabled() else 360,
            )
        error = self._preview(copy.deepcopy(self.feature))
        self.message.setText(f"⚠ {error}" if error else "")

    def _current_feature(self) -> SolidFeature:
        if isinstance(self.feature, Pad | Pocket):
            self.length.interpretText()
        else:
            self.angle.interpretText()
        self._changed()
        return copy.deepcopy(self.feature)

    def _accept(self) -> None:
        self.accepted.emit(self._current_feature())

    def _apply(self) -> None:
        self.applied.emit(self._current_feature())

    def next_feature(self, feature: SolidFeature) -> None:
        """Retain the settings while preparing a fresh feature after Apply."""
        self.feature = copy.deepcopy(feature)
        self.title.setText(feature.name)
        self._changed()


def _number_box(value: float, maximum: float, suffix: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(0.001, maximum)
    box.setDecimals(3)
    box.setSuffix(suffix)
    box.setValue(value)
    return box
