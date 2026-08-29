"""Standard derivative-family vocabulary."""

REGISTRATION = "Registration"
COMMON_REGION = "CommonRegion"
SEGMENTATION = "Segmentation"
MICROARCHITECTURE = "Microarchitecture"
PLATE_ROD_MORPHOMETRY = "PlateRodMorphometry"
TIMELAPSED = "Timelapsed"
FEA = "FEA"
MECHANOREGULATION = "Mechanoregulation"
VOID_SPACE = "VoidSpace"
COMPATIBILITY = "Compatibility"

DERIVATIVE_FAMILIES = frozenset({
    REGISTRATION, COMMON_REGION, SEGMENTATION, MICROARCHITECTURE,
    PLATE_ROD_MORPHOMETRY, TIMELAPSED, FEA, MECHANOREGULATION, VOID_SPACE,
    COMPATIBILITY,
})


def validate_derivative_family(value: str) -> str:
    """Return a recognized derivative family or raise a useful error."""
    if value not in DERIVATIVE_FAMILIES:
        raise ValueError(f"Unknown derivative family: {value!r}")
    return value
