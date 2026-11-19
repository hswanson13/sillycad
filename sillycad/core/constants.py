"""Units, tolerances and defaults in one place.

Model units are millimetres and degrees everywhere. Convert to radians only
right at the OCCT / solver boundary.
"""

# Sketch solver and profiles
SOLVER_TOLERANCE = 1e-6  # max constraint error (mm or rad) for a solve to count as good
POINT_TOLERANCE = 1e-6  # mm: end points closer than this count as joined in a profile

# STL export defaults
STL_LINEAR_DEFLECTION = 0.1  # mm: max distance between mesh and true surface
STL_ANGULAR_DEFLECTION = 15.0  # degrees: max angle between neighbouring facets
