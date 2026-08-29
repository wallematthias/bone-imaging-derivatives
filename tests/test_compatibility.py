from pathlib import Path

from bone_imaging_derivatives import (
    discover_legacy_registered_microarchitecture_records,
    discover_legacy_timelapsed_records,
    read_manifest,
    write_compatibility_manifest,
)


def test_legacy_discovery_and_compatibility_manifest_cover_existing_outputs(tmp_path: Path) -> None:
    """Legacy folders must remain available while packages migrate to manifests."""
    root = tmp_path / "dataset"
    (root / "derivatives" / "TimelapsedHRpQCT" / "sub-S01" / "site-tibia" / "ses-1").mkdir(parents=True)
    (root / "derivatives" / "TimelapsedHRpQCT" / "sub-S01" / "site-tibia" / "ses-1" / "formation_mask.nii.gz").touch()
    micro_path = root / "derivatives" / "Microarchitecture" / "sub-S01" / "site-tibia" / "registered" / "measurements.csv"
    micro_path.parent.mkdir(parents=True, exist_ok=True)
    micro_path.touch()

    timelapsed = discover_legacy_timelapsed_records(root)
    microarchitecture = discover_legacy_registered_microarchitecture_records(root)
    manifest_path = write_compatibility_manifest(root)

    assert timelapsed[0].role == "formation_mask"
    assert timelapsed[0].source == "legacy"
    assert microarchitecture[0].role == "measurements_table"
    assert len(read_manifest(manifest_path).records) == 2
