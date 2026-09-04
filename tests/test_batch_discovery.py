import json
from pathlib import Path

from bone_imaging_derivatives import DerivativeManifest, DerivativeRecord, write_manifest
from bone_imaging_derivatives.batch_discovery import (
    BatchArtifact,
    CaseKey,
    ContourSelection,
    case_keys_match,
    discover_derivative_artifacts,
    discover_raw_xct_images,
    preferred_contours,
    prerequisite_status,
)
from bone_imaging_derivatives.families import DERIVATIVE_FAMILIES


def test_batch_contract_derivative_families_are_current_tool_names() -> None:
    """The shared batch vocabulary should match the public Slicer tool names."""
    assert "Timelapse" in DERIVATIVE_FAMILIES
    assert "MotionScoring" in DERIVATIVE_FAMILIES
    assert "Timelapsed" not in DERIVATIVE_FAMILIES


def test_normalized_strambo_dataset_discovers_imported_contours(tmp_path: Path) -> None:
    """A normalized STRAMBO case must use curated ImportedContours masks."""
    root = tmp_path / "dataset"
    raw = root / "sub-STRAMBO0001" / "ses-001" / "xct" / "sub-STRAMBO0001_ses-001_voi-radiusleft_xct.AIM"
    imported = root / "derivatives" / "ImportedContours" / "sub-STRAMBO0001" / "ses-001" / "xct"
    raw.parent.mkdir(parents=True)
    imported.mkdir(parents=True)
    raw.touch()
    for role in ("seg", "full", "trab", "cort"):
        (imported / f"sub-STRAMBO0001_ses-001_voi-radiusleft_desc-{role}_mask.AIM").touch()

    images = discover_raw_xct_images(root)
    contours = discover_derivative_artifacts(root, "ImportedContours")
    selected = preferred_contours(contours, images[0].key)

    assert images[0].key == CaseKey("STRAMBO0001", "001", "radiusleft", None)
    assert set(selected) == {"segmentation", "full", "trab", "cort"}
    assert all(artifact.derivative == "ImportedContours" for artifact in selected.values())


def test_normalized_dataset_discovers_ipl_contours_as_curated_masks(tmp_path: Path) -> None:
    """Imported scanner/IPL masks are first-class contour inputs for batch tools."""
    root = tmp_path / "dataset"
    raw = root / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-tibialeft_xct.AIM"
    ipl = root / "derivatives" / "IPLContours" / "sub-001" / "ses-001" / "xct"
    raw.parent.mkdir(parents=True)
    ipl.mkdir(parents=True)
    raw.touch()
    for role in ("full", "cort"):
        (ipl / f"sub-001_ses-001_voi-tibialeft_desc-{role}_mask.AIM").touch()

    images = discover_raw_xct_images(root)
    contours = discover_derivative_artifacts(root, "IPLContours")
    selected = preferred_contours(contours, images[0].key)

    assert set(selected) == {"full", "cort"}
    assert all(artifact.derivative == "IPLContours" for artifact in selected.values())


def test_normalized_discovery_keeps_radius_sides_as_distinct_keys(tmp_path: Path) -> None:
    """Collapsing sides would merge unrelated acquisition rows."""
    root = tmp_path / "dataset"
    for voi in ("radiusleft", "radiusright"):
        path = root / "sub-001" / "ses-001" / "xct" / f"sub-001_ses-001_voi-{voi}_xct.AIM"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    keys = {image.key for image in discover_raw_xct_images(root)}

    assert keys == {
        CaseKey("001", "001", "radiusleft", None),
        CaseKey("001", "001", "radiusright", None),
    }


def test_preferred_contours_choose_imported_masks_before_generated_masks(tmp_path: Path) -> None:
    """Curated contours must win when both families provide the same role."""
    root = tmp_path / "dataset"
    for family in ("ImportedContours", "BoneContours"):
        path = root / "derivatives" / family / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_desc-full_mask.AIM"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    artifacts = (
        *discover_derivative_artifacts(root, "BoneContours"),
        *discover_derivative_artifacts(root, "ImportedContours"),
    )
    selected = preferred_contours(artifacts, CaseKey("001", "001", "radiusleft"))

    assert selected["full"].derivative == "ImportedContours"


def test_preferred_contours_choose_ipl_masks_before_generated_masks(tmp_path: Path) -> None:
    """IPL/scanner contours should be preferred over generated BoneContours."""
    root = tmp_path / "dataset"
    for family in ("IPLContours", "BoneContours"):
        path = root / "derivatives" / family / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_desc-full_mask.AIM"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    artifacts = (
        *discover_derivative_artifacts(root, "BoneContours"),
        *discover_derivative_artifacts(root, "IPLContours"),
    )
    selected = preferred_contours(artifacts, CaseKey("001", "001", "radiusleft"))

    assert selected["full"].derivative == "IPLContours"


def test_discover_derivative_artifacts_includes_file_only_material_labelmaps(tmp_path: Path) -> None:
    """Generated FEA material labels must be discoverable even when no manifest is present."""
    root = tmp_path / "dataset"
    label = (
        root
        / "derivatives"
        / "BoneContours"
        / "sub-001"
        / "ses-001"
        / "xct"
        / "sub-001_ses-001_voi-radiusleft_desc-fea-materials_label.AIM"
    )
    label.parent.mkdir(parents=True)
    label.touch()

    artifacts = discover_derivative_artifacts(root, "BoneContours")

    assert [(item.key, item.role, item.derivative) for item in artifacts] == [
        (CaseKey("001", "001", "radiusleft"), "material_labelmap", "BoneContours")
    ]


def test_imported_registration_is_a_first_class_derivative_family(tmp_path: Path) -> None:
    """Imported DAT/TFM registrations should be discoverable separately from generated registration."""
    root = tmp_path / "dataset"
    transform = (
        root
        / "derivatives"
        / "ImportedRegistration"
        / "sub-001"
        / "ses-002"
        / "xct"
        / "pairwise"
        / "sub-001_ses-002_voi-radiusleft_from-ses-002_to-ses-001_pairwise.tfm"
    )
    transform.parent.mkdir(parents=True)
    transform.touch()

    artifacts = discover_derivative_artifacts(root, "ImportedRegistration")

    assert [(item.key, item.role, item.derivative) for item in artifacts] == [
        (CaseKey("001", "002", "radiusleft"), "transform_pairwise", "ImportedRegistration")
    ]


def test_stack_aware_prerequisite_statuses_cover_ready_loadable_and_review(tmp_path: Path) -> None:
    """Stack-specific rows need distinct action states instead of one merged decision."""
    key = CaseKey("001", "001", "tibiaright", 2)
    image = BatchArtifact(tmp_path / "image.AIM", key, "image")
    selection = preferred_contours(
        (
            BatchArtifact(tmp_path / "seg.AIM", key, "segmentation", "ImportedContours"),
            BatchArtifact(tmp_path / "full.AIM", key, "full", "ImportedContours"),
        ),
        key,
    )

    assert prerequisite_status(image, selection, required_roles=("segmentation", "full")).status == "ready"
    assert prerequisite_status(
        image, selection, required_roles=("segmentation", "full"),
        existing_outputs=(BatchArtifact(tmp_path / "table.csv", key, "table", "Microarchitecture"),),
    ).status == "loadable"

    duplicate = preferred_contours(
        (
            BatchArtifact(tmp_path / "first.AIM", key, "full", "ImportedContours"),
            BatchArtifact(tmp_path / "second.nrrd", key, "full", "ImportedContours"),
        ),
        key,
    )
    assert prerequisite_status(image, duplicate, required_roles=("full",)).status == "review"
    assert prerequisite_status(
        image,
        duplicate,
        required_roles=("full",),
        existing_outputs=(BatchArtifact(tmp_path / "table.csv", key, "table", "BoneContours"),),
    ).status == "loadable"


def test_unstacked_and_stack_one_keys_are_not_equivalent_for_matching(tmp_path: Path) -> None:
    """Explicit stack-01 artifacts must not satisfy an unstacked source row."""
    unstacked = CaseKey("001", "001", "radiusleft", None)
    stack_one = CaseKey("001", "001", "radiusleft", 1)
    stack_two = CaseKey("001", "001", "radiusleft", 2)
    image = BatchArtifact(tmp_path / "image.AIM", unstacked, "image")
    contours = preferred_contours(
        (BatchArtifact(tmp_path / "trab.AIM", stack_one, "trab", "BoneContours"),),
        unstacked,
    )

    assert not case_keys_match(unstacked, stack_one)
    assert not case_keys_match(stack_one, unstacked)
    assert not case_keys_match(unstacked, stack_two)
    assert "trab" not in contours
    assert prerequisite_status(
        image,
        contours,
        required_roles=("trab",),
        existing_outputs=(BatchArtifact(tmp_path / "table.csv", stack_one, "plate_rod_measurements_table", "PlateRodMorphometry"),),
    ).status == "missing"


def test_raw_discovery_accepts_density_nifti_images(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    raw = root / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_xct.nii.gz"
    raw.parent.mkdir(parents=True)
    raw.touch()

    images = discover_raw_xct_images(root)

    assert len(images) == 1
    assert images[0].path == raw
    assert images[0].key == CaseKey("001", "001", "radiusleft")


def test_raw_discovery_creates_virtual_stack_records_from_sidecar_slice_metadata(tmp_path: Path) -> None:
    """A multi-stack AIM stays one source file while each stack gets its own key."""
    root = tmp_path / "dataset"
    raw = root / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-tibiaright_xct.AIM"
    raw.parent.mkdir(parents=True)
    raw.touch()
    raw.with_name(f"{raw.name}.json").write_text(json.dumps({
        "virtual_stacks": [
            {"stack_index": 1, "slice_start": 0, "slice_stop": 168},
            {"stack_index": 2, "slice_start": 168, "slice_stop": 336},
        ],
    }))

    images = discover_raw_xct_images(root)

    assert [image.key.stack_index for image in images] == [1, 2]
    assert [image.metadata for image in images] == [
        {"view_type": "stack_slices", "slice_axis": "z", "slice_start": 0, "slice_stop": 168},
        {"view_type": "stack_slices", "slice_axis": "z", "slice_start": 168, "slice_stop": 336},
    ]


def test_invalid_virtual_stack_metadata_requires_review(tmp_path: Path) -> None:
    """Unusable stack bounds must not downgrade a multi-stack source to a runnable row."""
    root = tmp_path / "dataset"
    raw = root / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-tibiaright_xct.AIM"
    raw.parent.mkdir(parents=True)
    raw.touch()
    raw.with_name(f"{raw.name}.json").write_text(json.dumps({
        "virtual_stacks": [{"stack_index": 1, "slice_start": 168, "slice_stop": 0}],
    }))

    image = discover_raw_xct_images(root)[0]

    assert prerequisite_status(image, ContourSelection({}), required_roles=()).status == "review"


def test_prerequisite_status_is_missing_when_a_required_mask_is_absent(tmp_path: Path) -> None:
    """Rows without all required masks must not be presented as runnable."""
    root = tmp_path / "dataset"
    raw = root / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-tibialeft_xct.AIM"
    mask = root / "derivatives" / "ImportedContours" / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-tibialeft_desc-full_mask.AIM"
    raw.parent.mkdir(parents=True)
    mask.parent.mkdir(parents=True)
    raw.touch()
    mask.touch()

    image = discover_raw_xct_images(root)[0]
    contours = discover_derivative_artifacts(root, "ImportedContours")
    result = prerequisite_status(image, preferred_contours(contours, image.key), required_roles=("segmentation", "full", "trab"))

    assert result.status == "missing"
    assert result.missing_roles == ("segmentation", "trab")


def test_manifest_records_use_dataset_relative_paths(tmp_path: Path) -> None:
    """Moving a dataset root must not leave manifest records tied to one machine."""
    root = tmp_path / "dataset"
    artifact = root / "derivatives" / "ImportedContours" / "sub-001" / "ses-001" / "xct" / "mask.AIM"
    artifact.parent.mkdir(parents=True)
    artifact.touch()
    record = DerivativeRecord(
        "ImportedContours", "periosteal_mask", "001", "radiusleft", "001", None,
        "native", artifact, "provided",
    )
    manifest_path = root / "derivatives" / "ImportedContours" / "manifest.json"

    write_manifest(DerivativeManifest.create("ImportedContours", root, {"name": "test", "version": "1"}, (record,)), manifest_path)

    payload = json.loads(manifest_path.read_text())
    assert payload["dataset_root"] == "."
    assert payload["records"][0]["path"] == "derivatives/ImportedContours/sub-001/ses-001/xct/mask.AIM"


def test_derivative_manifest_rejects_records_outside_the_normalized_family_layout(tmp_path: Path) -> None:
    """A legacy path in a manifest must not become a valid batch input."""
    root = tmp_path / "dataset"
    legacy = root / "site-radius" / "native_space" / "mask.AIM"
    legacy.parent.mkdir(parents=True)
    legacy.touch()
    record = DerivativeRecord(
        "ImportedContours", "periosteal_mask", "001", "radiusleft", "001", None,
        "native", legacy, "provided",
    )
    manifest_path = root / "derivatives" / "ImportedContours" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    write_manifest(DerivativeManifest.create("ImportedContours", root, {"name": "test", "version": "1"}, (record,)), manifest_path)

    artifacts = discover_derivative_artifacts(root, "ImportedContours")

    assert artifacts == ()


def test_derivative_discovery_reads_normalized_manifest_records_before_filename_recovery(tmp_path: Path) -> None:
    """Manifest metadata must preserve a curated role when the filename is opaque."""
    root = tmp_path / "dataset"
    artifact = root / "derivatives" / "ImportedContours" / "sub-001" / "ses-001" / "xct" / "curated-mask.AIM"
    artifact.parent.mkdir(parents=True)
    artifact.touch()
    record = DerivativeRecord(
        "ImportedContours", "trabecular_mask", "001", "radiusright", "001", 2,
        "native", artifact, "provided",
    )
    manifest_path = root / "derivatives" / "ImportedContours" / "manifest.json"
    write_manifest(DerivativeManifest.create("ImportedContours", root, {"name": "test", "version": "1"}, (record,)), manifest_path)

    artifacts = discover_derivative_artifacts(root, "ImportedContours")

    assert [(item.key, item.role, item.source) for item in artifacts] == [
        (CaseKey("001", "001", "radiusright", 2), "trab", "provided"),
    ]


def test_derivative_discovery_keeps_non_contour_manifest_roles(tmp_path: Path) -> None:
    """The shared family reader must not discard downstream tables and maps."""
    root = tmp_path / "dataset"
    artifact = root / "derivatives" / "Microarchitecture" / "sub-001" / "ses-001" / "xct" / "measurements.csv"
    artifact.parent.mkdir(parents=True)
    artifact.touch()
    record = DerivativeRecord(
        "Microarchitecture", "measurements_table", "001", "radiusleft", "001", None,
        "table", artifact, "generated",
    )
    manifest_path = root / "derivatives" / "Microarchitecture" / "manifest.json"
    write_manifest(DerivativeManifest.create("Microarchitecture", root, {"name": "test", "version": "1"}, (record,)), manifest_path)

    artifacts = discover_derivative_artifacts(root, "Microarchitecture")

    assert [(item.role, item.derivative) for item in artifacts] == [("measurements_table", "Microarchitecture")]


def test_discover_derivative_artifacts_includes_profile_maps_and_tables_without_manifest(tmp_path: Path) -> None:
    """Canonical FEA outputs should be discoverable from files alone."""
    root = tmp_path / "dataset"
    out_dir = root / "derivatives" / "FEA" / "sub-001" / "ses-001" / "xct"
    map_path = out_dir / "maps" / "sub-001_ses-001_voi-radiusleft_desc-XtremeCTI_map-sed.nii.gz"
    table_path = out_dir / "measurements" / "sub-001_ses-001_voi-radiusleft_desc-XtremeCTI_fea.csv"
    map_path.parent.mkdir(parents=True)
    table_path.parent.mkdir(parents=True)
    map_path.write_bytes(b"map")
    table_path.write_text("Sample,Profile\n", encoding="utf-8")

    artifacts = discover_derivative_artifacts(root, "FEA")

    by_role = {artifact.role: artifact for artifact in artifacts}
    assert by_role["sed_map"].key == CaseKey("001", "001", "radiusleft", None)
    assert by_role["summary_table"].metadata["profile"] == "XtremeCTI"
