"""Cosmetic internal-thread specifications and selected standard sizes.

The catalog contains nominal dimensions, not tolerance limits or manufacturing
certification. Pipe-thread bores require an explicitly chosen entrance diameter.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ThreadSize:
    """A catalog designation, with millimetre dimensions and diametral taper per length."""

    family: str
    designation: str
    pitch: float
    major: float | None
    basic_minor: float | None
    taper: float = 0.0


@dataclass(frozen=True)
class ThreadSpec:
    """A cosmetic internal thread; ``depth=None`` means the complete hole depth."""

    family: str
    designation: str
    thread_class: str = ""
    left_hand: bool = False
    depth: float | None = None
    custom_major: float | None = None
    custom_pitch: float | None = None
    custom_taper: float = 0.0


# ISO 261 diameter -> coarse and fine pitches (mm).
_METRIC = {
    1.0: (0.25, 0.2),
    1.1: (0.25, 0.2),
    1.2: (0.25, 0.2),
    1.4: (0.3, 0.2),
    1.6: (0.35, 0.2),
    1.8: (0.35, 0.2),
    2.0: (0.4, 0.25),
    2.2: (0.45, 0.25),
    2.5: (0.45, 0.35),
    3.0: (0.5, 0.35),
    3.5: (0.6, 0.35),
    4.0: (0.7, 0.5),
    4.5: (0.75, 0.5),
    5.0: (0.8, 0.5),
    6.0: (1.0, 0.75),
    7.0: (1.0, 0.75),
    8.0: (1.25, 1.0, 0.75),
    10.0: (1.5, 1.25, 1.0, 0.75),
    12.0: (1.75, 1.5, 1.25, 1.0),
    14.0: (2.0, 1.5, 1.25, 1.0),
    16.0: (2.0, 1.5, 1.0),
    18.0: (2.5, 2.0, 1.5, 1.0),
    20.0: (2.5, 2.0, 1.5, 1.0),
    22.0: (2.5, 2.0, 1.5, 1.0),
    24.0: (3.0, 2.0, 1.5, 1.0),
    27.0: (3.0, 2.0, 1.5, 1.0),
    30.0: (3.5, 3.0, 2.0, 1.5, 1.0),
    33.0: (3.5, 3.0, 2.0, 1.5),
    36.0: (4.0, 3.0, 2.0, 1.5),
    39.0: (4.0, 3.0, 2.0, 1.5),
    42.0: (4.5, 4.0, 3.0, 2.0, 1.5),
    45.0: (4.5, 4.0, 3.0, 2.0, 1.5),
    48.0: (5.0, 4.0, 3.0, 2.0, 1.5),
    52.0: (5.0, 4.0, 3.0, 2.0, 1.5),
    56.0: (5.5, 4.0, 3.0, 2.0, 1.5),
    60.0: (5.5, 4.0, 3.0, 2.0, 1.5),
    64.0: (6.0, 4.0, 3.0, 2.0, 1.5),
}

# Inch size, major diameter (in), UNC, UNF and UNEF threads per inch.
_UNIFIED = (
    ("#0", 0.060, None, 80, None),
    ("#1", 0.073, 64, 72, None),
    ("#2", 0.086, 56, 64, None),
    ("#3", 0.099, 48, 56, None),
    ("#4", 0.112, 40, 48, None),
    ("#5", 0.125, 40, 44, None),
    ("#6", 0.138, 32, 40, None),
    ("#8", 0.164, 32, 36, None),
    ("#10", 0.190, 24, 32, None),
    ("#12", 0.216, 24, 28, 32),
    ("1/4", 0.250, 20, 28, 32),
    ("5/16", 0.3125, 18, 24, 32),
    ("3/8", 0.375, 16, 24, 32),
    ("7/16", 0.4375, 14, 20, 28),
    ("1/2", 0.500, 13, 20, 28),
    ("9/16", 0.5625, 12, 18, 24),
    ("5/8", 0.625, 11, 18, 24),
    ("3/4", 0.750, 10, 16, 20),
    ("7/8", 0.875, 9, 14, 20),
    ("1", 1.000, 8, 12, 20),
)

# Nominal pipe size and TPI. These are not bore diameters.
_NPT = (
    ("1/16", 27), ("1/8", 27), ("1/4", 18), ("3/8", 18), ("1/2", 14),
    ("3/4", 14), ("1", 11.5), ("1 1/4", 11.5), ("1 1/2", 11.5), ("2", 11.5),
)  # fmt: skip

# Pipe size, TPI, basic major and minor diameters at the reference plane (mm).
_BSP = (
    ("1/16", 28, 7.723, 6.561), ("1/8", 28, 9.728, 8.566),
    ("1/4", 19, 13.157, 11.445), ("3/8", 19, 16.662, 14.950),
    ("1/2", 14, 20.955, 18.631), ("3/4", 14, 26.441, 24.117),
    ("1", 11, 33.249, 30.291), ("1 1/4", 11, 41.910, 38.952),
    ("1 1/2", 11, 47.803, 44.845), ("2", 11, 59.614, 56.656),
    ("2 1/2", 11, 75.184, 72.226), ("3", 11, 87.884, 84.926),
    ("4", 11, 113.030, 110.072), ("6", 11, 163.830, 160.872),
)  # fmt: skip

_TRAPEZOIDAL = ((8, 1.5), (10, 2), (12, 3), (16, 3), (30, 3), (36, 6))
_ACME = (("3/8", 0.375, 12), ("1/2", 0.5, 10), ("5/8", 0.625, 8))

THREAD_FAMILIES = (
    "ISO metric",
    "UNC",
    "UNF",
    "UNEF",
    "NPT",
    "NPTF",
    "BSPP",
    "BSPT",
    "Tr",
    "ACME",
    "Custom",
)


def _catalog() -> tuple[ThreadSize, ...]:
    sizes: list[ThreadSize] = []
    for diameter, pitches in _METRIC.items():
        for pitch in pitches:
            sizes.append(
                ThreadSize(
                    "ISO metric",
                    f"M{diameter:g} x {pitch:g}",
                    pitch,
                    diameter,
                    diameter - 1.0825317547 * pitch,
                )
            )
    for label, inches, coarse, fine, extra_fine in _UNIFIED:
        for family, tpi in (("UNC", coarse), ("UNF", fine), ("UNEF", extra_fine)):
            if tpi:
                pitch, diameter = 25.4 / tpi, 25.4 * inches
                sizes.append(
                    ThreadSize(
                        family,
                        f"{label}-{tpi} {family}",
                        pitch,
                        diameter,
                        diameter - 1.0825317547 * pitch,
                    )
                )
    for label, tpi in _NPT:
        for family in ("NPT", "NPTF"):
            sizes.append(
                ThreadSize(family, f"{label}-{tpi:g} {family}", 25.4 / tpi, None, None, 1 / 16)
            )
    for label, tpi, major, minor in _BSP:
        sizes.append(ThreadSize("BSPP", f"G {label}", 25.4 / tpi, major, minor))
        sizes.append(ThreadSize("BSPT", f"Rc {label}", 25.4 / tpi, major, None, 1 / 16))
    for diameter, pitch in _TRAPEZOIDAL:
        sizes.append(
            ThreadSize("Tr", f"Tr {diameter:g} x {pitch:g}", pitch, diameter, diameter - pitch)
        )
    for label, inches, tpi in _ACME:
        pitch, diameter = 25.4 / tpi, 25.4 * inches
        sizes.append(ThreadSize("ACME", f"{label}-{tpi} ACME", pitch, diameter, diameter - pitch))
    return tuple(sizes)


THREAD_SIZES = _catalog()

# ISO 273 selected clearance diameters: fine, medium and coarse (mm).
CLEARANCES = {
    "M3": (3.2, 3.4, 3.6),
    "M4": (4.3, 4.5, 4.8),
    "M5": (5.3, 5.5, 5.8),
    "M6": (6.4, 6.6, 7.0),
    "M8": (8.4, 9.0, 10.0),
    "M10": (10.5, 11.0, 12.0),
    "M12": (13.0, 13.5, 14.5),
    "M14": (15.0, 15.5, 16.5),
    "M16": (17.0, 17.5, 18.5),
}
CLEARANCE_FITS = ("fine", "medium", "coarse")


def clearance_diameter(size: str, fit: str) -> float:
    """Resolve a selected ISO 273 clearance diameter."""
    if size not in CLEARANCES or fit not in CLEARANCE_FITS:
        raise ValueError(f"Unsupported clearance size or fit: {size}, {fit}.")
    return CLEARANCES[size][CLEARANCE_FITS.index(fit)]


def thread_sizes(family: str) -> tuple[ThreadSize, ...]:
    """Return the catalog sizes for a family; custom specifications have no catalog."""
    if family not in THREAD_FAMILIES:
        raise ValueError(f"Unknown thread family: {family}.")
    return tuple(size for size in THREAD_SIZES if size.family == family)


def resolve_thread(spec: ThreadSpec) -> ThreadSize:
    """Validate a cosmetic thread and resolve its nominal dimensions."""
    if spec.depth is not None and (not math.isfinite(spec.depth) or spec.depth <= 0):
        raise ValueError("Thread depth must be greater than zero.")
    if spec.family == "Custom":
        if not spec.designation.strip():
            raise ValueError("Enter a custom thread designation.")
        if (
            spec.custom_major is None
            or not math.isfinite(spec.custom_major)
            or spec.custom_major <= 0
        ):
            raise ValueError("Enter a positive custom major diameter.")
        if (
            spec.custom_pitch is None
            or not math.isfinite(spec.custom_pitch)
            or spec.custom_pitch <= 0
        ):
            raise ValueError("Enter a positive custom pitch.")
        if not math.isfinite(spec.custom_taper) or not 0 <= spec.custom_taper < 1:
            raise ValueError("Custom diametral taper must be at least zero and less than one.")
        return ThreadSize(
            "Custom",
            spec.designation,
            spec.custom_pitch,
            spec.custom_major,
            None,
            spec.custom_taper,
        )
    if spec.custom_major is not None or spec.custom_pitch is not None or spec.custom_taper != 0:
        raise ValueError("Custom dimensions can only be used with a custom thread.")
    match = next(
        (size for size in thread_sizes(spec.family) if size.designation == spec.designation), None
    )
    if match is None:
        raise ValueError(f"Unsupported {spec.family} thread size: {spec.designation}.")
    return match
