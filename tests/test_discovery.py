from pathlib import Path

from bone_imaging_derivatives import (
    DerivativeManifest, DerivativeRecord, discover_manifests, find_records, write_manifest,
)


def _manifest(root: Path, family: str, record: DerivativeRecord) -> DerivativeManifest:
    return DerivativeManifest.create(
        derivative_family=family, dataset_root=root, software={"name": "test", "version": "1"},
        records=(record,), created_at="2026-08-29T00:00:00Z",
    )


def test_discovery_and_filtering_return_only_matching_records(tmp_path: Path) -> None:
    """Ignoring filter fields would feed a workflow records from another session."""
    root = tmp_path / "dataset"
    registration = DerivativeRecord("Registration", "transform_to_reference", "S01", "tibia", "1", 1, "native", root / "a.tfm", "generated")
    common = DerivativeRecord("CommonRegion", "scan_region_native_common", "S01", "tibia", "2", 1, "native", root / "b.nii.gz", "generated")
    write_manifest(_manifest(root, "Registration", registration), root / "derivatives" / "Registration" / "manifest.json")
    write_manifest(_manifest(root, "CommonRegion", common), root / "derivatives" / "CommonRegion" / "manifest.json")

    manifests = discover_manifests(root)
    found = find_records(manifests, derivative="CommonRegion", subject_id="S01", session_id="2", space="native")

    assert [record.path for record in found] == [root / "b.nii.gz"]
