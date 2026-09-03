"""Standard derivative-family vocabulary."""

REGISTRATION = "Registration"
COMMON_REGION = "CommonRegion"
IMPORTED_CONTOURS = "ImportedContours"
BONE_CONTOURS = "BoneContours"
SEGMENTATION = "Segmentation"
MICROARCHITECTURE = "Microarchitecture"
PLATE_ROD_MORPHOMETRY = "PlateRodMorphometry"
TIMELAPSE = "Timelapse"
FEA = "FEA"
MECHANOREGULATION = "Mechanoregulation"
MOTION_SCORING = "MotionScoring"
VOID_SPACE = "VoidSpace"
COMPATIBILITY = "Compatibility"

DERIVATIVE_FAMILIES = frozenset({
    REGISTRATION, COMMON_REGION, IMPORTED_CONTOURS, BONE_CONTOURS, SEGMENTATION, MICROARCHITECTURE,
    PLATE_ROD_MORPHOMETRY, TIMELAPSE, FEA, MECHANOREGULATION, MOTION_SCORING, VOID_SPACE,
    COMPATIBILITY,
})


def validate_derivative_family(value: str) -> str:
    """Return a recognized derivative family or raise a useful error."""
    if value not in DERIVATIVE_FAMILIES:
        raise ValueError(f"Unknown derivative family: {value!r}")
    return value
