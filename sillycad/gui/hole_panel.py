"""Docked controls for hole placement and cosmetic threads."""

import copy
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sillycad.core.features import Hole, SketchFeature
from sillycad.core.geometry import Placement
from sillycad.core.sketch import ORIGIN, XY, Point
from sillycad.core.threads import CLEARANCE_FITS, CLEARANCES, clearance_diameter
from sillycad.gui.property_panel import _number_box
from sillycad.gui.thread_editor import ThreadEditor
from sillycad.gui.tooltips import tooltip


class HolePanel(QWidget):
    """Edit a hole with live preview, without modifying the document."""

    accepted = Signal(object)
    applied = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        feature: Hole,
        sketches: list[SketchFeature],
        preview: Callable[[Hole], str | None],
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
        self._face = feature.face
        self._has_center = feature.center is not None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.title = QLabel(feature.name)
        self.title.setObjectName("propertyTitle")
        layout.addWidget(self.title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        fields = QVBoxLayout(content)
        fields.setContentsMargins(0, 0, 0, 0)
        placement = QGroupBox("Placement")
        form = QFormLayout(placement)
        self.sketch = QComboBox()
        self.sketch.addItem("Click a face in the viewport", "")
        for sketch in sketches:
            self.sketch.addItem(sketch.name, sketch.id)
        index = self.sketch.findData(feature.sketch_id)
        if index < 0:
            self.sketch.addItem(f"Missing sketch: {feature.sketch_id}", feature.sketch_id)
            index = self.sketch.count() - 1
        self.sketch.setCurrentIndex(index)
        self.point = QComboBox()
        self._fill_points(
            "" if feature.center is not None or not feature.sketch_id else feature.point_id
        )
        self.x = QDoubleSpinBox()
        self.y = QDoubleSpinBox()
        for box, value in zip((self.x, self.y), feature.center or (0.0, 0.0), strict=True):
            box.setDecimals(5)
            box.setRange(-100000, 100000)
            box.setSuffix(" mm")
            box.setValue(value)
        hint = QLabel("Click a face or a position on the selected sketch to move the hole.")
        hint.setWordWrap(True)
        form.addRow(hint)
        form.addRow("Sketch", self.sketch)
        form.addRow("Center", self.point)
        form.addRow("Center X", self.x)
        form.addRow("Center Y", self.y)
        fields.addWidget(placement)
        hole = QGroupBox("Hole")
        form = QFormLayout(hole)
        self.style = QComboBox()
        for title, value in (
            ("Simple", "simple"),
            ("Counterbore", "counterbore"),
            ("Spotface", "spotface"),
            ("Countersink", "countersink"),
        ):
            self.style.addItem(title, value)
        index = self.style.findData(feature.style)
        if index < 0:
            self.style.addItem(f"Unsupported style: {feature.style}", feature.style)
            index = self.style.count() - 1
        self.style.setCurrentIndex(index)
        self.clearance = QComboBox()
        self.clearance.addItem("Custom diameter", "")
        for size in CLEARANCES:
            self.clearance.addItem(f"ISO 273 {size}", size)
        index = self.clearance.findData(feature.clearance_size)
        if index < 0:
            self.clearance.addItem(
                f"Unsupported clearance: {feature.clearance_size}", feature.clearance_size
            )
            index = self.clearance.count() - 1
        self.clearance.setCurrentIndex(index)
        self.fit = QComboBox()
        for fit in CLEARANCE_FITS:
            self.fit.addItem(fit.capitalize(), fit)
        index = self.fit.findData(feature.clearance_fit)
        if index < 0:
            self.fit.addItem(f"Unsupported fit: {feature.clearance_fit}", feature.clearance_fit)
            index = self.fit.count() - 1
        self.fit.setCurrentIndex(index)
        self.diameter = _number_box(feature.diameter, 100000, " mm")
        self.extent = QComboBox()
        self.extent.addItem("Distance", "distance")
        self.extent.addItem("Through All", "through_all")
        self.extent.setCurrentIndex(int(feature.through_all))
        self.length = _number_box(feature.length, 100000, " mm")
        self.direction = QComboBox()
        self.direction.addItem("Into sketch plane", False)
        self.direction.addItem("Flipped", True)
        self.direction.setCurrentIndex(int(feature.reversed))
        self.head_diameter = _number_box(feature.head_diameter, 100000, " mm")
        self.head_depth = _number_box(feature.head_depth, 100000, " mm")
        self.angle = _number_box(feature.countersink_angle, 180, "°")
        for name, widget in (
            ("Style", self.style),
            ("Clearance", self.clearance),
            ("Fit", self.fit),
            ("Diameter", self.diameter),
            ("Extent", self.extent),
            ("Depth", self.length),
            ("Direction", self.direction),
            ("Head diameter", self.head_diameter),
            ("Head depth", self.head_depth),
            ("Countersink angle", self.angle),
        ):
            form.addRow(name, widget)
        fields.addWidget(hole)
        self.thread = ThreadEditor(feature.thread)
        fields.addWidget(self.thread)
        fields.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("errorLabel")
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        self.ok, self.cancel, self.apply = (
            QPushButton("OK"),
            QPushButton("Cancel"),
            QPushButton("Apply (+)"),
        )
        self.ok.setObjectName("primaryButton")
        self.ok.setToolTip(tooltip("OK", "Commit the feature and close the panel", "Ctrl+Enter"))
        self.cancel.setToolTip(tooltip("Cancel", "Discard this preview", "Esc"))
        self.apply.setToolTip(tooltip("Apply", "Commit and continue"))
        for button in (self.ok, self.cancel, self.apply):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.ok.clicked.connect(lambda: self.accepted.emit(self._current_feature()))
        self.apply.clicked.connect(lambda: self.applied.emit(self._current_feature()))
        self.cancel.clicked.connect(self.cancelled)
        shortcut = QShortcut(self)
        shortcut.setKeys([QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")])
        shortcut.activated.connect(self._accept_if_placed)
        self.sketch.currentIndexChanged.connect(self._sketch_changed)
        self.point.currentIndexChanged.connect(self._changed)
        self.x.valueChanged.connect(self._coordinates_changed)
        self.y.valueChanged.connect(self._coordinates_changed)
        self.x.lineEdit().textEdited.connect(self._coordinates_changed)
        self.y.lineEdit().textEdited.connect(self._coordinates_changed)
        for combo in (
            self.style,
            self.clearance,
            self.fit,
            self.extent,
            self.direction,
        ):
            combo.currentIndexChanged.connect(self._changed)
        for number in (self.diameter, self.length, self.head_diameter, self.head_depth, self.angle):
            number.valueChanged.connect(self._changed)
        self.thread.changed.connect(self._changed)
        self._changed()

    def _fill_points(self, current: str) -> None:
        self.point.blockSignals(True)
        self.point.clear()
        sketch = self._sketches.get(self.sketch.currentData())
        if sketch is not None:
            self.point.addItem("Click / enter coordinates", "")
            self.point.addItem("Sketch origin", ORIGIN)
            for point in sketch.sketch.geo.values():
                if isinstance(point, Point):
                    self.point.addItem(f"{point.id} ({point.x:g}, {point.y:g})", point.id)
        else:
            self.point.addItem("Click a face", "")
        index = self.point.findData(current)
        if index < 0:
            self.point.addItem(f"Missing point: {current}", current)
            index = self.point.count() - 1
        self.point.setCurrentIndex(index)
        self.point.blockSignals(False)

    def _sketch_changed(self) -> None:
        self._face = None
        self._has_center = False
        self._fill_points("")
        self._changed()

    def _coordinates_changed(self) -> None:
        self._has_center = True
        self._changed()

    def set_position(self, face: Placement | None, xy: XY, point_id: str | None = None) -> None:
        """Set a picked position, optionally linking it to a sketch point."""
        self._face = face
        self._has_center = True
        for box, value in zip((self.x, self.y), xy, strict=True):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        self.point.blockSignals(True)
        index = self.point.findData(point_id if point_id is not None else "")
        self.point.setCurrentIndex(max(index, 0))
        self.point.blockSignals(False)
        self._changed()

    def _changed(self) -> None:
        size = self.clearance.currentData()
        fit = self.fit.currentData()
        if size in CLEARANCES and fit in CLEARANCE_FITS:
            self.diameter.blockSignals(True)
            self.diameter.setValue(clearance_diameter(size, fit))
            self.diameter.blockSignals(False)
        self.diameter.setEnabled(not size)
        self.fit.setEnabled(bool(size))
        self.length.setEnabled(self.extent.currentData() == "distance")
        style = self.style.currentData()
        self.head_diameter.setEnabled(style != "simple")
        self.head_depth.setEnabled(style in ("counterbore", "spotface"))
        self.angle.setEnabled(style == "countersink")
        free = not self.point.currentData()
        self.point.setEnabled(bool(self.sketch.currentData()))
        self.x.setEnabled(free)
        self.y.setEnabled(free)
        center = (self.x.value(), self.y.value()) if free and self._has_center else None
        self.feature = replace(
            self.feature,
            sketch_id=self.sketch.currentData(),
            point_id=self.point.currentData(),
            face=self._face if not self.sketch.currentData() else None,
            center=center,
            style=style,
            clearance_size=size,
            clearance_fit=fit,
            diameter=self.diameter.value(),
            length=self.length.value(),
            through_all=self.extent.currentData() == "through_all",
            reversed=self.direction.currentData(),
            head_diameter=self.head_diameter.value(),
            head_depth=self.head_depth.value(),
            countersink_angle=self.angle.value(),
            thread=self.thread.value(),
        )
        error = self._preview(copy.deepcopy(self.feature))
        self.message.setText(f"⚠ {error}" if error else "")
        placed = (not free or center is not None) and (
            bool(self.sketch.currentData()) or self._face is not None
        )
        self.ok.setEnabled(placed)
        self.apply.setEnabled(placed)

    def _accept_if_placed(self) -> None:
        feature = self._current_feature()
        if self.ok.isEnabled():
            self.accepted.emit(feature)

    def _current_feature(self) -> Hole:
        for number in (
            self.x,
            self.y,
            self.diameter,
            self.length,
            self.head_diameter,
            self.head_depth,
            self.angle,
        ):
            number.interpretText()
        self._changed()
        return copy.deepcopy(self.feature)

    def next_feature(self, feature: Hole) -> None:
        """Retain settings while preparing a fresh feature after Apply."""
        self.feature = copy.deepcopy(feature)
        self.title.setText(feature.name)
        self._changed()
