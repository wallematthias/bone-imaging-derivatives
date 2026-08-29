from pathlib import Path

from bone_imaging_derivatives import DerivativeManifest, DerivativeRecord, read_manifest, write_manifest


def test_manifest_round_trip_stores_dataset_relative_paths(tmp_path: Path) -> None:
    """Changing the dataset root would break portable manifest records."""
    dataset_root = tmp_path / "dataset"
    output = dataset_root / "derivatives" / "CommonRegion" / "manifest.json"
    record_path = dataset_root / "derivatives" / "CommonRegion" / "sub-S01" / "mask.nii.gz"
    manifest = DerivativeManifest.create(
        derivative_family="CommonRegion",
        dataset_root=dataset_root,
        software={"name": "timelapsed-hrpqct", "version": "2.0"},
        records=(
            DerivativeRecord(
                derivative="CommonRegion", role="scan_region_native_common", subject_id="S01",
                site="tibia", session_id="1", stack_index=1, space="native", path=record_path,
                source="generated", inputs=("input-1",), metadata={"method": "overlap"},
            ),
        ),
        created_at="2026-08-29T00:00:00Z",
    )

    write_manifest(manifest, output)
    loaded = read_manifest(output)

    assert loaded == manifest
    assert '"path": "derivatives/CommonRegion/sub-S01/mask.nii.gz"' in output.read_text()


def test_manifest_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    """Accepting a future schema could silently misinterpret a record."""
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version": 2}')

    import pytest

    with pytest.raises(ValueError, match="schema_version"):
        read_manifest(path)
