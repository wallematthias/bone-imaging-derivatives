from pathlib import Path

import pytest

from bone_imaging_derivatives import DerivativeRecord
from bone_imaging_derivatives.families import validate_derivative_family
from bone_imaging_derivatives.layout import derivative_family_root, record_output_path
from bone_imaging_derivatives.roles import validate_role


def test_layout_helpers_build_the_standard_subject_site_layout(tmp_path: Path) -> None:
    """A changed layout would make independently produced derivatives undiscoverable."""
    root = tmp_path / "dataset"
    assert derivative_family_root(root, "CommonRegion") == root / "derivatives" / "CommonRegion"
    assert record_output_path(root, "CommonRegion", "S01", "tibia", "native_space", "ses-1", "masks", "mask.nii.gz") == (
        root / "derivatives" / "CommonRegion" / "sub-S01" / "site-tibia" / "native_space" / "ses-1" / "masks" / "mask.nii.gz"
    )


def test_family_role_and_record_validation_reject_unknown_contract_values(tmp_path: Path) -> None:
    """Unknown family or role strings would create non-interoperable records."""
    assert validate_derivative_family("CommonRegion") == "CommonRegion"
    assert validate_role("scan_region_native_common") == "scan_region_native_common"
    with pytest.raises(ValueError, match="Unknown derivative family"):
        validate_derivative_family("Unknown")
    with pytest.raises(ValueError, match="Unknown derivative role"):
        validate_role("not-a-role")
    with pytest.raises(ValueError, match="Unknown derivative role"):
        DerivativeRecord("CommonRegion", "not-a-role", "S01", "tibia", "1", None, "native", tmp_path / "x", "generated")


def test_virtual_image_view_requires_stack_slice_metadata(tmp_path: Path) -> None:
    """A virtual image without slice bounds cannot be safely loaded on demand."""
    valid = DerivativeRecord(
        "Registration",
        "source_image_view",
        "S01",
        "tibia",
        "1",
        1,
        "native",
        tmp_path / "scan.AIM",
        "virtual",
        metadata={"format": "AIM", "view_type": "stack_slices", "slice_axis": "z", "slice_start": 0, "slice_stop": 10},
        content_type="image",
    )
    assert valid.source == "virtual"
    with pytest.raises(ValueError, match="virtual source_image_view records require"):
        DerivativeRecord(
            "Registration",
            "source_image_view",
            "S01",
            "tibia",
            "1",
            1,
            "native",
            tmp_path / "scan.AIM",
            "virtual",
            metadata={"format": "AIM", "view_type": "stack_slices", "slice_start": 0},
            content_type="image",
        )
