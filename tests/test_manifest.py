from pathlib import Path
import shutil

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


def test_manifest_relative_records_follow_a_copied_dataset_root(tmp_path: Path) -> None:
    """An absolute serialized root would make copied datasets point at stale artifacts."""
    original = tmp_path / "original"
    original_record = original / "derivatives" / "Registration" / "sub-S01" / "transform.tfm"
    manifest_path = original / "derivatives" / "Registration" / "manifest.json"
    manifest = DerivativeManifest.create(
        "Registration", original, {"name": "timelapsed-hrpqct", "version": "2.0"},
        (DerivativeRecord("Registration", "transform_to_reference", "S01", "tibia", "1", None,
                          "native", original_record, "generated"),),
        "2026-08-29T00:00:00Z",
    )
    write_manifest(manifest, manifest_path)
    copied = tmp_path / "copied"
    shutil.copytree(original, copied)

    loaded = read_manifest(copied / "derivatives" / "Registration" / "manifest.json")

    assert loaded.dataset_root == copied.resolve()
    assert loaded.records[0].path == copied / "derivatives" / "Registration" / "sub-S01" / "transform.tfm"


def test_manifest_round_trip_supports_virtual_aim_stack_views(tmp_path: Path) -> None:
    """Virtual stack records let workflows reference AIM ranges without writing image copies."""
    dataset_root = tmp_path / "dataset"
    source = dataset_root / "raw" / "scan.AIM"
    manifest_path = dataset_root / "derivatives" / "Registration" / "manifest.json"
    record = DerivativeRecord(
        derivative="Registration",
        role="source_image_view",
        subject_id="S01",
        site="tibia",
        session_id="1",
        stack_index=2,
        space="native",
        path=source,
        source="virtual",
        inputs=(str(source),),
        metadata={
            "format": "AIM",
            "view_type": "stack_slices",
            "slice_axis": "z",
            "slice_start": 20,
            "slice_stop": 40,
            "scaling": "bmd",
        },
        content_type="image",
    )
    manifest = DerivativeManifest.create(
        "Registration",
        dataset_root,
        {"name": "timelapsed-hrpqct", "version": "2.1"},
        (record,),
        "2026-08-29T00:00:00Z",
    )

    write_manifest(manifest, manifest_path)
    loaded = read_manifest(manifest_path)

    assert loaded.records[0] == record
    assert '"source": "virtual"' in manifest_path.read_text()
    assert '"path": "raw/scan.AIM"' in manifest_path.read_text()
