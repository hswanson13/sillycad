"""Inventor-style controls for cosmetic thread metadata."""

from collections.abc import Callable, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from sillycad.core.threads import (
    THREAD_TYPES,
    ThreadSize,
    ThreadSpec,
    thread_sizes,
    thread_type,
)

CUSTOM = "Custom"

# Common internal thread classes, the usual one first.
_CLASSES = {
    "ISO Metric": ("6H", "5H", "7H", "6G"),
    "Unified Inch": ("2B", "1B", "3B"),
    "Trapezoidal": ("7H", "8H"),
    "ACME": ("2G", "3G", "4G"),
}

Allowed = Callable[[ThreadSize], bool]
Suggest = Callable[[Sequence[ThreadSize]], ThreadSize | None]


def _first(sizes: Sequence[ThreadSize]) -> ThreadSize | None:
    return next(iter(sizes), None)


class ThreadEditor(QWidget):
    """Choose a thread by type, size and designation, as in Inventor.

    Only sizes accepted by ``allowed`` are offered (for example those that fit an
    existing bore, or only tapered pipe threads). ``suggest`` picks the default
    among a type's allowed sizes when the type changes or the current size stops
    being allowed.
    """

    changed = Signal()

    def __init__(
        self,
        spec: ThreadSpec | None = None,
        *,
        allowed: Allowed | None = None,
        suggest: Suggest | None = None,
        tapered: bool = False,
    ) -> None:
        super().__init__()
        self._allowed: Allowed = allowed or (lambda size: True)
        self._suggest: Suggest = suggest or _first
        self._tapered = tapered
        self.kind = QComboBox()
        self.size = QComboBox()
        self.designation = QComboBox()
        self.custom_designation = QLineEdit()
        self.custom_designation.setPlaceholderText("Name, e.g. M6 x 1 special")
        self.major = self._number(6, " mm", decimals=5)
        self.pitch = self._number(1, " mm", decimals=5)
        self.taper = self._number(1 / 16, "", minimum=0, maximum=0.999, decimals=5)
        self.thread_class = QComboBox()
        self.thread_class.setEditable(True)
        self.thread_class.lineEdit().setPlaceholderText("Optional")
        self.hand = QComboBox()
        self.hand.addItems(["Right hand", "Left hand"])
        self.full_depth = QCheckBox("Full depth")
        self.depth = self._number(5, " mm")
        self.info = QLabel()
        self.info.setObjectName("hintLabel")
        self.info.setWordWrap(True)
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        for label, widget in (
            ("Thread type", self.kind),
            ("Size", self.size),
            ("Designation", self.designation),
            ("Name", self.custom_designation),
            ("Major diameter", self.major),
            ("Pitch", self.pitch),
            ("Taper (on diameter)", self.taper),
            ("Class", self.thread_class),
            ("Direction", self.hand),
            ("", self.full_depth),
            ("Thread depth", self.depth),
        ):
            self.form.addRow(label, widget)
        self.form.addRow(self.info)
        self._load(spec)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.size.currentIndexChanged.connect(self._size_changed)
        self.designation.currentIndexChanged.connect(self._update)
        self.full_depth.toggled.connect(self._update)
        self.thread_class.currentTextChanged.connect(self.changed)
        self.custom_designation.textChanged.connect(self.changed)
        self.hand.currentIndexChanged.connect(self.changed)
        for box in (self.depth, self.major, self.pitch, self.taper):
            box.valueChanged.connect(self.changed)

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
        box.setKeyboardTracking(False)  # preview once the value is entered, not per keystroke
        return box

    # ── Catalog filtering ───────────────────────────────────────────

    def _sizes(self, kind: str) -> list[ThreadSize]:
        """The allowed sizes of a thread type, smallest first."""
        sizes = [
            size
            for family in THREAD_TYPES.get(kind, ())
            for size in thread_sizes(family)
            if self._allowed(size)
        ]
        return sorted(sizes, key=lambda size: size.major or 0)

    def _all_sizes(self) -> list[ThreadSize]:
        return [size for kind in THREAD_TYPES for size in self._sizes(kind)]

    def _kinds(self) -> list[str]:
        """Thread types with at least one allowed size, then Custom."""
        return [kind for kind in THREAD_TYPES if self._sizes(kind)] + [CUSTOM]

    def _current(self) -> ThreadSize | None:
        designation = self.designation.currentText()
        return next(
            (s for s in self._sizes(self.kind.currentText()) if s.designation == designation),
            None,
        )

    def _choose(self, designation: str) -> ThreadSize | None:
        """Select ``designation`` if allowed, else the suggestion for the current type."""
        before = self.kind.currentText()
        size = next((s for s in self._all_sizes() if s.designation == designation), None)
        if size is None:
            size = self._suggest(self._sizes(before) or self._sizes(self._kinds()[0]))
        _refill(self.kind, self._kinds(), thread_type(size.family) if size else CUSTOM)
        self._fill_size_lists(size)
        if self.kind.currentText() != before:
            self._fill_classes()
        return size

    def _fill_size_lists(self, size: ThreadSize | None) -> None:
        sizes = self._sizes(self.kind.currentText())
        nominals = list(dict.fromkeys(s.nominal for s in sizes))
        nominal = size.nominal if size else ""
        _refill(self.size, nominals, nominal)
        same = [s.designation for s in sizes if s.nominal == self.size.currentText()]
        _refill(self.designation, same, size.designation if size else "")

    def _load(self, spec: ThreadSpec | None) -> None:
        if spec is not None and spec.family == CUSTOM:
            _refill(self.kind, self._kinds(), CUSTOM)
            self.custom_designation.setText(spec.designation)
            self.major.setValue(spec.custom_major or 6)
            self.pitch.setValue(spec.custom_pitch or 1)
            self.taper.setValue(spec.custom_taper or 1 / 16)
        else:
            self._choose(spec.designation if spec else "")
        self._fill_classes(spec.thread_class if spec else None)
        self.hand.setCurrentIndex(int(bool(spec and spec.left_hand)))
        self.full_depth.setChecked(spec is None or spec.depth is None)
        if spec is not None and spec.depth is not None:
            self.depth.setValue(spec.depth)
        self.replaced = (  # a saved size that this hole no longer allows
            spec.designation
            if spec and spec.family != CUSTOM and spec.designation != self.designation.currentText()
            else ""
        )
        self._update_visible()

    def _fill_classes(self, current: str | None = None) -> None:
        """Offer the type's usual classes; ``None`` selects the most common one."""
        classes = _CLASSES.get(self.kind.currentText(), ())
        self.thread_class.blockSignals(True)
        self.thread_class.clear()
        self.thread_class.addItems(classes)
        self.thread_class.setCurrentText(
            classes[0] if current is None and classes else current or ""
        )
        self.thread_class.blockSignals(False)

    # ── Reactions ───────────────────────────────────────────────────

    def _kind_changed(self) -> None:
        self._fill_size_lists(self._suggest(self._sizes(self.kind.currentText())))
        self._fill_classes()
        self._update()

    def _size_changed(self) -> None:
        sizes = self._sizes(self.kind.currentText())
        same = [s.designation for s in sizes if s.nominal == self.size.currentText()]
        _refill(self.designation, same, "")
        self._update()

    def _update(self) -> None:
        self.replaced = ""
        self._update_visible()
        self.changed.emit()

    def _update_visible(self) -> None:
        custom = self.kind.currentText() == CUSTOM
        for widget in (self.size, self.designation):
            self.form.setRowVisible(widget, not custom)
        for widget in (self.custom_designation, self.major, self.pitch):
            self.form.setRowVisible(widget, custom)
        self.form.setRowVisible(self.taper, custom and self._tapered)
        self.form.setRowVisible(self.full_depth, not self._tapered)
        self.form.setRowVisible(self.depth, self._tapered or not self.full_depth.isChecked())
        self.thread_class.setEnabled(bool(_CLASSES.get(self.kind.currentText())) or custom)
        self.info.setText(self._describe())

    def _describe(self) -> str:
        if self.kind.currentText() == CUSTOM:
            if not self._all_sizes():
                return "No standard thread fits this hole, so define a custom one."
            return "Define the thread by its major diameter and pitch."
        size = self._current()
        if size is None:
            return ""
        if size.taper:
            drill = f"Suggested entrance Ø{size.tap_drill:g} mm. " if size.tap_drill else ""
            return f"{drill}Taper 1:16 on diameter, pitch {size.pitch:.4g} mm."
        note = f"{self.replaced} does not fit here. " if self.replaced else ""
        return f"{note}Tap drill Ø{size.tap_drill:g} mm, pitch {size.pitch:.4g} mm."

    # ── Public API ──────────────────────────────────────────────────

    def set_filter(self, allowed: Allowed, *, tapered: bool = False) -> None:
        """Offer only ``allowed`` sizes, keeping the current one when it still qualifies."""
        self._allowed, self._tapered = allowed, tapered
        if self.kind.currentText() != CUSTOM or not self._all_sizes():
            self._choose(self.designation.currentText())
        self._update_visible()

    def suggest_size(self) -> None:
        """Select the suggested size of the current type, replacing the current one."""
        self._choose("")
        self._update_visible()

    def selected(self) -> ThreadSize | None:
        """The chosen catalog size, or None for a custom thread."""
        return None if self.kind.currentText() == CUSTOM else self._current()

    def value(self) -> ThreadSpec | None:
        """The thread as metadata, or None when no allowed size is selected."""
        for box in (self.depth, self.major, self.pitch, self.taper):
            box.interpretText()
        common = {
            "thread_class": self.thread_class.currentText().strip(),
            "left_hand": self.hand.currentIndex() == 1,
            "depth": self.depth.value()
            if self._tapered or not self.full_depth.isChecked()
            else None,
        }
        if self.kind.currentText() == CUSTOM:
            return ThreadSpec(
                CUSTOM,
                self.custom_designation.text().strip(),
                custom_major=self.major.value(),
                custom_pitch=self.pitch.value(),
                custom_taper=self.taper.value() if self._tapered else 0,
                **common,
            )
        size = self._current()
        return ThreadSpec(size.family, size.designation, **common) if size else None


def _refill(combo: QComboBox, items: list[str], current: str) -> None:
    """Replace a combo's items without signals, selecting ``current`` or the first item."""
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(items)
    combo.setCurrentIndex(max(combo.findText(current), 0))
    combo.blockSignals(False)
