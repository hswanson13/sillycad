"""Cosmetic internal-thread specifications and selected standard sizes.

The catalog contains nominal dimensions, not tolerance limits or manufacturing
certification. Tapered pipe threads suggest a common entrance drill that the
user can override.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

# Thread engagement limits for a tapped bore, as multiples of the pitch below the
# major diameter: about 100% of a 60° thread at the low end, 50% at the high end.
_DEEPEST, _SHALLOWEST = 1.3, 0.65


@dataclass(frozen=True)
class ThreadSize:
    """A catalog designation, with millimetre dimensions and diametral taper per length.

    ``nominal`` is the size label shared by every pitch of one diameter (``M6``,
    ``1/4``), ``fine`` marks a pitch finer than the coarse series (fine metric, UNF,
    UNEF), and ``drill`` is the suggested entrance diameter of a tapered thread.
    """

    family: str
    designation: str
    pitch: float
    major: float | None
    basic_minor: float | None
    taper: float = 0.0
    fine: bool = False
    nominal: str = ""
    drill: float | None = None

    @property
    def tap_drill(self) -> float | None:
        """The bore to drill: major minus pitch for parallel threads, else the suggestion."""
        if self.taper or self.major is None:
            return self.drill
        return round(self.major - self.pitch, 3)

    @property
    def bore_range(self) -> tuple[float, float] | None:
        """The smallest and largest bore a parallel thread can be tapped into."""
        if self.taper or self.major is None:
            return None
        return self.major - _DEEPEST * self.pitch, self.major - _SHALLOWEST * self.pitch

    def fits(self, bore: float) -> bool:
        """Whether this thread can be tapped into ``bore``; tapered threads are not checked."""
        limits = self.bore_range
        return limits is None or limits[0] - 1e-9 <= bore <= limits[1] + 1e-9


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

# Nominal pipe size, TPI and the common tap drill (in) without reaming.
_NPT = (
    ("1/16", 27, 0.246), ("1/8", 27, 0.339), ("1/4", 18, 0.4375), ("3/8", 18, 0.578),
    ("1/2", 14, 0.719), ("3/4", 14, 0.922), ("1", 11.5, 1.156), ("1 1/4", 11.5, 1.5),
    ("1 1/2", 11.5, 1.734), ("2", 11.5, 2.219),
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


def _catalog() -> Iterable[ThreadSize]:
    for diameter, pitches in _METRIC.items():
        for pitch in pitches:
            yield ThreadSize(
                "ISO metric",
                f"M{diameter:g} x {pitch:g}",
                pitch,
                diameter,
                diameter - 1.0825317547 * pitch,
                fine=pitch != pitches[0],
                nominal=f"M{diameter:g}",
            )
    for label, inches, *tpis in _UNIFIED:
        for family, tpi in zip(("UNC", "UNF", "UNEF"), tpis, strict=True):
            if tpi:
                pitch, diameter = 25.4 / tpi, 25.4 * inches
                minor = diameter - 1.0825317547 * pitch
                yield ThreadSize(
                    family,
                    f"{label}-{tpi} {family}",
                    pitch,
                    diameter,
                    minor,
                    fine=family != "UNC",
                    nominal=label,
                )
    for label, tpi, drill in _NPT:
        for family in ("NPT", "NPTF"):
            yield ThreadSize(
                family,
                f"{label}-{tpi:g} {family}",
                25.4 / tpi,
                None,
                None,
                1 / 16,
                nominal=label,
                drill=round(25.4 * drill, 2),
            )
    for label, tpi, major, minor in _BSP:
        pitch = 25.4 / tpi
        yield ThreadSize("BSPP", f"G {label}", pitch, major, minor, nominal=label)
        yield ThreadSize(
            "BSPT", f"Rc {label}", pitch, major, None, 1 / 16, nominal=label, drill=minor
        )
    for diameter, pitch in _TRAPEZOIDAL:
        yield ThreadSize(
            "Tr", f"Tr {diameter:g} x {pitch:g}", pitch, diameter, diameter - pitch,
            nominal=f"Tr {diameter:g}",
        )  # fmt: skip
    for label, inches, tpi in _ACME:
        pitch, diameter = 25.4 / tpi, 25.4 * inches
        yield ThreadSize(
            "ACME", f"{label}-{tpi} ACME", pitch, diameter, diameter - pitch, nominal=label
        )


THREAD_SIZES = tuple(_catalog())

# Thread types as Inventor groups them, mapped to the stored families.
THREAD_TYPES = {
    "ISO Metric": ("ISO metric",),
    "Unified Inch": ("UNC", "UNF", "UNEF"),
    "NPT Pipe": ("NPT", "NPTF"),
    "BSP Pipe": ("BSPP", "BSPT"),
    "Trapezoidal": ("Tr",),
    "ACME": ("ACME",),
}

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


def thread_type(family: str) -> str:
    """The Inventor-style thread type that contains a stored family."""
    return next((name for name, members in THREAD_TYPES.items() if family in members), family)


def size_for_nominal(sizes: Iterable[ThreadSize], diameter: float) -> ThreadSize | None:
    """The coarsest size whose nominal diameter is closest to ``diameter``.

    Sizes without a major diameter (NPT) fall back to the first one.
    """
    sizes = tuple(sizes)
    majors = {size: size.major for size in sizes if size.major is not None}
    if not majors:
        return next(iter(sizes), None)
    return min(majors, key=lambda size: abs(majors[size] - diameter))


def size_for_bore(sizes: Iterable[ThreadSize], bore: float) -> ThreadSize | None:
    """The size that fits an existing ``bore``, coarse pitch first, closest tap drill."""
    drills = {
        size: size.tap_drill
        for size in sizes
        if not size.taper and size.tap_drill is not None and size.fits(bore)
    }
    return min(drills, key=lambda size: (size.fine, abs(drills[size] - bore)), default=None)


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
