"""Controls for cosmetic thread metadata."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
)

from sillycad.core.threads import THREAD_FAMILIES, ThreadSpec, thread_sizes


class ThreadEditor(QGroupBox):
    """Edit a cosmetic internal thread without generating a helical solid."""

    changed = Signal()

    def __init__(self, spec: ThreadSpec | None = None) -> None:
        super().__init__("Cosmetic thread")
        self.setCheckable(True)
        self.setChecked(spec is not None)
        form = QFormLayout(self)
        self.family = QComboBox()
        self.family.addItems(THREAD_FAMILIES)
        if spec and spec.family not in THREAD_FAMILIES:
            self.family.addItem(spec.family)
        self.family.setCurrentText(spec.family if spec else "ISO metric")
        self.designation = QComboBox()
        self.custom_designation = QLineEdit(
            spec.designation if spec and spec.family == "Custom" else ""
        )
        self.thread_class = QLineEdit(spec.thread_class if spec else "")
        self.thread_class.setPlaceholderText("Optional, e.g. 6H or 2B")
        self.left_hand = QCheckBox("Left hand")
        self.left_hand.setChecked(spec.left_hand if spec else False)
        self.full_depth = QCheckBox("Full hole depth")
        self.full_depth.setChecked(spec is None or spec.depth is None)
        self.depth = self._number(spec.depth if spec and spec.depth is not None else 5, " mm")
        self.major = self._number(
            spec.custom_major if spec and spec.custom_major else 6, " mm", decimals=5
        )
        self.pitch = self._number(
            spec.custom_pitch if spec and spec.custom_pitch else 1, " mm", decimals=5
        )
        self.taper = self._number(
            spec.custom_taper if spec else 0, "", minimum=0, maximum=0.999, decimals=5
        )
        note = QLabel(
            "Metadata only; no helical geometry. Class and pipe-bore dimensions are not certified."
        )
        note.setWordWrap(True)
        form.addRow(note)
        form.addRow("Family", self.family)
        form.addRow("Size", self.designation)
        form.addRow("Custom name", self.custom_designation)
        form.addRow("Class", self.thread_class)
        form.addRow("Hand", self.left_hand)
        form.addRow("Depth", self.full_depth)
        form.addRow("Thread depth", self.depth)
        form.addRow("Custom major", self.major)
        form.addRow("Custom pitch", self.pitch)
        form.addRow("Custom taper (diameter/length)", self.taper)
        self._fill_sizes(spec.designation if spec else "M6 x 1")
        self.family.currentIndexChanged.connect(self._family_changed)
        self.designation.currentIndexChanged.connect(self.changed)
        self.custom_designation.textChanged.connect(self.changed)
        self.thread_class.textChanged.connect(self.changed)
        self.left_hand.toggled.connect(self.changed)
        self.full_depth.toggled.connect(self._depth_changed)
        for box in (self.depth, self.major, self.pitch, self.taper):
            box.valueChanged.connect(self.changed)
        self.toggled.connect(self.changed)
        self._update_enabled()

    @staticmethod
    def _number(
        value: float,
        suffix: str,
        *,
        minimum: float = 0.001,
        maximum: float = 100000,
        decimals: int = 3,
    ) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(decimals)
        box.setRange(minimum, maximum)
        box.setSuffix(suffix)
        box.setValue(value)
        return box

    def _fill_sizes(self, current: str = "") -> None:
        self.designation.blockSignals(True)
        self.designation.clear()
        family = self.family.currentText()
        for size in thread_sizes(family) if family in THREAD_FAMILIES else ():
            self.designation.addItem(size.designation)
        index = self.designation.findText(current)
        if current and index < 0 and self.family.currentText() != "Custom":
            self.designation.addItem(current)
            index = self.designation.count() - 1
        self.designation.setCurrentIndex(max(index, 0))
        self.designation.blockSignals(False)

    def _family_changed(self) -> None:
        self._fill_sizes()
        self._update_enabled()
        self.changed.emit()

    def _depth_changed(self) -> None:
        self._update_enabled()
        self.changed.emit()

    def _update_enabled(self) -> None:
        custom = self.family.currentText() == "Custom"
        self.designation.setEnabled(not custom)
        for widget in (self.custom_designation, self.major, self.pitch, self.taper):
            widget.setEnabled(custom)
        self.depth.setEnabled(not self.full_depth.isChecked())

    def value(self) -> ThreadSpec | None:
        """Return the controls as metadata, preserving custom input and depth."""
        for box in (self.depth, self.major, self.pitch, self.taper):
            box.interpretText()
        if not self.isChecked():
            return None
        custom = self.family.currentText() == "Custom"
        return ThreadSpec(
            family=self.family.currentText(),
            designation=self.custom_designation.text()
            if custom
            else self.designation.currentText(),
            thread_class=self.thread_class.text(),
            left_hand=self.left_hand.isChecked(),
            depth=None if self.full_depth.isChecked() else self.depth.value(),
            custom_major=self.major.value() if custom else None,
            custom_pitch=self.pitch.value() if custom else None,
            custom_taper=self.taper.value() if custom else 0,
        )
