"""Docked Hole controls laid out like Inventor's Hole property panel.

The hole Type (Simple, Clearance, Tapped, Taper Tapped) decides what is asked
for: a diameter, a fastener size and fit, or a thread whose tap drill sets the
bore. Only the section for the chosen type is shown.
"""

import copy
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
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
from sillycad.core.threads import (
    CLEARANCE_FITS,
    CLEARANCES,
    ThreadSize,
    ThreadSpec,
    clearance_diameter,
    resolve_thread,
    size_for_nominal,
)
from sillycad.gui.property_panel import _number_box
from sillycad.gui.thread_editor import ThreadEditor
from sillycad.gui.tooltips import tooltip

HOLE_TYPES = {
    "simple": ("Simple", "A plain drilled hole of the diameter you enter"),
    "clearance": ("Clearance", "A hole a fastener passes through, sized from the fastener"),
    "tapped": ("Tapped", "A threaded hole, drilled at the thread's tap drill"),
    "taper": ("Taper Tapped", "A tapered pipe thread, such as NPT or BSPT"),
}
SEATS = {
    "simple": ("None", "No seat"),
    "counterbore": ("Counterbore", "A flat-bottomed recess for a screw head"),
    "spotface": ("Spotface", "A shallow flat recess for a washer or nut"),
    "countersink": ("Countersink", "A conical recess for a flat-head screw"),
}


def hole_type(hole: Hole) -> str:
    """The Inventor hole type a stored hole corresponds to."""
    if hole.thread is not None:
        return "taper" if _tapered(hole.thread) else "tapped"
    return "clearance" if hole.clearance_size else "simple"


def _tapered(spec: ThreadSpec) -> bool:
    with suppress(ValueError):
        return resolve_thread(spec).taper > 0
    return spec.custom_taper > 0


def _parallel(size: ThreadSize) -> bool:
    return not size.taper


def _taper(size: ThreadSize) -> bool:
    return size.taper > 0


class _Choice(QWidget):
    """Exclusive toggle buttons, two per row so they fit the docked panel."""

    changed = Signal()

    def __init__(self, options: dict[str, tuple[str, str]], current: str) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for index, (value, (title, description)) in enumerate(options.items()):
            button = QPushButton(title)
            button.setObjectName("operationButton")
            button.setCheckable(True)
            button.setToolTip(tooltip(title, description))
            button.setChecked(value == current)
            self.group.addButton(button)
            self.buttons[value] = button
            grid.addWidget(button, *divmod(index, 2))
        self._fallback = current  # an unknown stored value is kept until a button is clicked
        self.group.buttonClicked.connect(self.changed)

    def value(self) -> str:
        return next(
            (value for value, button in self.buttons.items() if button.isChecked()),
            self._fallback,
        )

    def select(self, value: str) -> None:
        self.buttons[value].setChecked(True)


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
        self._nominal: float | None = None  # the fastener size, kept across type changes
        # The taper thread whose entrance diameter was last suggested; a saved one is kept.
        self._entrance_for = feature.thread.designation if feature.thread else ""
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
        fields.addWidget(self._placement_group(feature, sketches))

        kind = hole_type(feature)
        self.types = _Choice(HOLE_TYPES, kind)
        self.seat = _Choice(SEATS, feature.style)
        group = QGroupBox("Type")
        form = QFormLayout(group)
        form.addRow(self.types)
        form.addRow("Seat", self.seat)
        fields.addWidget(group)

        self.behavior = QGroupBox("Behavior")
        form = QFormLayout(self.behavior)
        self.extent = QComboBox()
        self.extent.addItem("Distance", "distance")
        self.extent.addItem("Through All", "through_all")
        self.extent.setCurrentIndex(int(feature.through_all))
        self.length = _number_box(feature.length, 100000, " mm")
        self.direction = QComboBox()
        self.direction.addItem("Into the face", False)
        self.direction.addItem("Flipped", True)
        self.direction.setCurrentIndex(int(feature.reversed))
        form.addRow("Termination", self.extent)
        form.addRow("Depth", self.length)
        form.addRow("Direction", self.direction)
        fields.addWidget(self.behavior)

        self.seat_group = QGroupBox("Seat size")
        self.seat_form = QFormLayout(self.seat_group)
        self.head_diameter = _number_box(feature.head_diameter, 100000, " mm")
        self.head_depth = _number_box(feature.head_depth, 100000, " mm")
        self.angle = _number_box(feature.countersink_angle, 180, "°")
        self.seat_form.addRow("Seat diameter", self.head_diameter)
        self.seat_form.addRow("Seat depth", self.head_depth)
        self.seat_form.addRow("Countersink angle", self.angle)
        fields.addWidget(self.seat_group)

        self.size_group = QGroupBox("Size")
        self.size_form = QFormLayout(self.size_group)
        self.diameter = _number_box(feature.diameter, 100000, " mm")
        self.size_form.addRow("Diameter", self.diameter)
        fields.addWidget(self.size_group)

        self.fastener = QGroupBox("Fastener")
        form = QFormLayout(self.fastener)
        self.clearance = QComboBox()
        for size in CLEARANCES:
            self.clearance.addItem(size, size)
        if feature.clearance_size and feature.clearance_size not in CLEARANCES:
            self.clearance.addItem(f"Unsupported: {feature.clearance_size}", feature.clearance_size)
        self.clearance.setCurrentIndex(max(self.clearance.findData(feature.clearance_size), 0))
        self.fit = QComboBox()
        for fit in CLEARANCE_FITS:
            self.fit.addItem(fit.capitalize(), fit)
        if feature.clearance_fit not in CLEARANCE_FITS:
            self.fit.addItem(f"Unsupported: {feature.clearance_fit}", feature.clearance_fit)
        self.fit.setCurrentIndex(max(self.fit.findData(feature.clearance_fit), 0))
        self.clearance_size = QLabel()
        self.clearance_size.setObjectName("hintLabel")
        form.addRow("Standard", QLabel("ISO 273 metric"))
        form.addRow("Size", self.clearance)
        form.addRow("Fit", self.fit)
        form.addRow(self.clearance_size)
        fields.addWidget(self.fastener)

        self.thread_group = QGroupBox("Thread")
        thread_layout = QVBoxLayout(self.thread_group)
        self.thread = ThreadEditor(
            feature.thread,
            allowed=_taper if kind == "taper" else _parallel,
            suggest=self._suggest_thread,
            tapered=kind == "taper",
        )
        note = QLabel("Cosmetic: shown in the viewport and saved, but not modeled or exported.")
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        thread_layout.addWidget(self.thread)
        thread_layout.addWidget(note)
        fields.addWidget(self.thread_group)
        fields.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("errorLabel")
        layout.addWidget(self.message)
        layout.addLayout(self._buttons())

        self.sketch.currentIndexChanged.connect(self._sketch_changed)
        self.point.currentIndexChanged.connect(self._changed)
        self.x.valueChanged.connect(self._coordinates_changed)
        self.y.valueChanged.connect(self._coordinates_changed)
        self.x.lineEdit().textEdited.connect(self._coordinates_changed)
        self.y.lineEdit().textEdited.connect(self._coordinates_changed)
        self.types.changed.connect(self._type_changed)
        self.seat.changed.connect(self._changed)
        for combo in (self.clearance, self.fit, self.extent, self.direction):
            combo.currentIndexChanged.connect(self._changed)
        self.diameter.valueChanged.connect(self._diameter_edited)
        for number in (self.length, self.head_diameter, self.head_depth, self.angle):
            number.valueChanged.connect(self._changed)
        self.thread.changed.connect(self._changed)
        self._changed()

    # ── Layout ──────────────────────────────────────────────────────

    def _placement_group(self, feature: Hole, sketches: list[SketchFeature]) -> QGroupBox:
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
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        form.addRow(hint)
        form.addRow("Sketch", self.sketch)
        form.addRow("Center", self.point)
        form.addRow("Center X", self.x)
        form.addRow("Center Y", self.y)
        return placement

    def _buttons(self) -> QHBoxLayout:
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
        self.ok.clicked.connect(lambda: self.accepted.emit(self._current_feature()))
        self.apply.clicked.connect(lambda: self.applied.emit(self._current_feature()))
        self.cancel.clicked.connect(self.cancelled)
        shortcut = QShortcut(self)
        shortcut.setKeys([QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")])
        shortcut.activated.connect(self._accept_if_placed)
        return buttons

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

    # ── Placement ───────────────────────────────────────────────────

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

    # ── Type and size ───────────────────────────────────────────────

    def _nominal_size(self) -> float:
        """The fastener diameter the user is working with: last chosen, or as entered."""
        return self._nominal or self.diameter.value()

    def _suggest_thread(self, sizes: Sequence[ThreadSize]) -> ThreadSize | None:
        return size_for_nominal(sizes, self._nominal_size())

    def _diameter_edited(self) -> None:
        if self.types.value() == "simple":
            self._nominal = None
        self._changed()

    def _type_changed(self) -> None:
        kind = self.types.value()
        if kind == "clearance":
            nominal = self._nominal_size()
            closest = min(CLEARANCES, key=lambda size: abs(float(size[1:]) - nominal))
            self.clearance.blockSignals(True)
            self.clearance.setCurrentIndex(self.clearance.findData(closest))
            self.clearance.blockSignals(False)
        elif kind in ("tapped", "taper"):
            self.thread.blockSignals(True)
            if kind == "taper":
                self.thread.set_filter(_taper, tapered=True)
                self.seat.select("simple")  # tapered threads need a plain entrance
            else:
                self.thread.set_filter(_parallel)
            self.thread.suggest_size()  # follow the fastener size the user is working with
            self.thread.blockSignals(False)
        self._changed()

    def _diameter(self, kind: str) -> float | None:
        """The bore the type dictates, or None when the user enters it."""
        if kind == "clearance" and self.clearance.currentData() in CLEARANCES:
            if self.fit.currentData() in CLEARANCE_FITS:
                return clearance_diameter(self.clearance.currentData(), self.fit.currentData())
        if kind == "tapped" and (size := self.thread.selected()):
            return size.tap_drill
        if kind == "taper" and (size := self.thread.selected()):
            if size.designation != self._entrance_for and size.tap_drill:
                self._entrance_for = size.designation
                return size.tap_drill  # a suggestion: the field stays editable
        return None

    def _update_sections(self, kind: str, seat: str) -> None:
        self.fastener.setVisible(kind == "clearance")
        self.thread_group.setVisible(kind in ("tapped", "taper"))
        self.size_group.setVisible(kind in ("simple", "taper"))
        self.size_form.labelForField(self.diameter).setText(
            "Entrance diameter" if kind == "taper" else "Diameter"
        )
        for value, button in self.seat.buttons.items():
            button.setEnabled(kind != "taper" or value == "simple")
        self.seat_group.setVisible(seat != "simple")
        self.seat_form.setRowVisible(self.head_depth, seat in ("counterbore", "spotface"))
        self.seat_form.setRowVisible(self.angle, seat == "countersink")
        self.length.setEnabled(self.extent.currentData() == "distance")

    def _changed(self) -> None:
        kind, seat = self.types.value(), self.seat.value()
        driven = self._diameter(kind)
        if driven is not None:
            self.diameter.blockSignals(True)
            self.diameter.setValue(driven)
            self.diameter.blockSignals(False)
        thread = self.thread.value() if kind in ("tapped", "taper") else None
        if kind == "clearance" and self.clearance.currentData() in CLEARANCES:
            self._nominal = float(self.clearance.currentData()[1:])
            self.clearance_size.setText(f"Clearance hole Ø{self.diameter.value():g} mm")
        elif kind == "tapped" and (size := self.thread.selected()) and size.major:
            self._nominal = size.major
        self._update_sections(kind, seat)
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
            style=seat,
            clearance_size=self.clearance.currentData() if kind == "clearance" else "",
            clearance_fit=self.fit.currentData(),
            diameter=self.diameter.value(),
            length=self.length.value(),
            through_all=self.extent.currentData() == "through_all",
            reversed=self.direction.currentData(),
            head_diameter=self.head_diameter.value(),
            head_depth=self.head_depth.value(),
            countersink_angle=self.angle.value(),
            thread=thread,
        )
        if kind in ("tapped", "taper") and thread is None:
            error = "Choose a thread size."
        else:
            error = self._preview(copy.deepcopy(self.feature))
        self.message.setText(f"⚠ {error}" if error else "")
        placed = (not free or center is not None) and (
            bool(self.sketch.currentData()) or self._face is not None
        )
        self.ok.setEnabled(placed)
        self.apply.setEnabled(placed)

    # ── Commit ──────────────────────────────────────────────────────

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
