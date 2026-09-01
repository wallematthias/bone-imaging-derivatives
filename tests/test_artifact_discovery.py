from pathlib import Path

from bone_imaging_derivatives.artifacts import (
    ArtifactRecord,
    apply_overrides,
    discover_artifacts,
    normalize_session_id,
    normalize_site,
    site_category,
)


def test_discover_artifacts_combines_raw_images_and_derivative_masks(tmp_path: Path) -> None:
    """Batch tools need raw images plus masks already emitted by other tools."""
    root = tmp_path / "dataset"
    (root / "STRAMBO_0001_RL_Y00.AIM").parent.mkdir(parents=True)
    (root / "STRAMBO_0001_RL_Y00.AIM").touch()
    (root / "STRAMBO_0001_RL_Y04.AIM;1").touch()
    mask_root = root / "derivatives" / "Segmentation" / "sub-STRAMBO_0001" / "site-radius" / "ses-Y00" / "masks"
    mask_root.mkdir(parents=True)
    for role in ("seg", "full", "trab", "cort"):
        (mask_root / f"STRAMBO_0001_RL_Y00_mask-{role}.AIM").touch()
        (mask_root / f"STRAMBO_0001_RL_Y00_mask-{role}.json").write_text('{"algorithm_metadata": {"preset": "test"}}')

    index = discover_artifacts(root)

    images = index.find(kind="image", subject_id="STRAMBO_0001", site="radius_left")
    masks = index.find(kind="mask", subject_id="STRAMBO_0001", site="radius_left", session_id="00")

    assert [record.session_id for record in images] == ["00", "04"]
    assert {record.role for record in masks} == {"segmentation", "full", "trab", "cort"}
    assert all(record.site_source in {"filename", "path"} for record in images + masks)
    assert all(record.path.exists() for record in images + masks)


def test_discovery_accepts_non_aim_images_and_keeps_weak_evidence(tmp_path: Path) -> None:
    """Discovery should not be AIM-only; non-AIM files can still be useful with lower confidence."""
    root = tmp_path / "dataset"
    image = root / "sub-S01_ses-1_site-tibia_image.nii.gz"
    image.parent.mkdir(parents=True)
    image.touch()

    index = discover_artifacts(root)
    records = index.find(kind="image", subject_id="S01", site="tibia", session_id="1")

    assert len(records) == 1
    assert records[0].format == "nifti"
    assert records[0].identity_confidence == "high"


def test_site_and_session_aliases_are_side_safe() -> None:
    """Left/right site identity must not collapse when both sides exist."""
    assert normalize_site("RL") == "radius_left"
    assert normalize_site("RR") == "radius_right"
    assert normalize_site("DR") == "radius"
    assert normalize_site("TR") == "tibia_right"
    assert normalize_site("DT") == "tibia"
    assert normalize_site("KN") == "knee"
    assert normalize_site("radius_left") == "radius_left"
    assert site_category("radius_left") == "radius"
    assert site_category("RR") == "radius"
    assert normalize_session_id("ses-Y04") == "04"
    assert normalize_session_id("Y08") == "08"
    assert normalize_session_id("08") == "08"


def test_discover_artifacts_supports_calgary_blck_and_crtx_masks(tmp_path: Path) -> None:
    """Calgary-style BLCK/CRTX mask suffixes should map to full/cort roles."""
    root = tmp_path / "calgary" / "SAMPLE433"
    root.mkdir(parents=True)
    image = root / "SAMPLE433_T1.AIM"
    blck = root / "SAMPLE433_T1_BLCK_MASK.AIM"
    crtx = root / "SAMPLE433_T1_CRTX_MASK.AIM"
    for path in (image, blck, crtx):
        path.touch()

    index = discover_artifacts(tmp_path / "calgary")

    assert len(index.find(kind="image", subject_id="SAMPLE433", session_id="T1")) == 1
    assert index.find(kind="mask", subject_id="SAMPLE433", session_id="T1", role="full")[0].path == blck
    assert index.find(kind="mask", subject_id="SAMPLE433", session_id="T1", role="cort")[0].path == crtx


def test_discover_artifacts_supports_documented_timelapsed_and_generic_roi_names(tmp_path: Path) -> None:
    root = tmp_path / "data"
    names = (
        "SUBJ001_DR_T1.AIM",
        "SUBJ001_DR_T1_TRAB_MASK.AIM",
        "SUBJ001_DR_T1_CORT_MASK.AIM",
        "SUBJ001_DR_T1_REGMASK.AIM",
        "SUBJ001_DR_T1_ROI1.AIM",
        "SUBJ001_DR_T1_MASK2.AIM",
        "SUBJ001_RL_T1.AIM",
        "SUBJ001_RR_T1.AIM",
    )
    root.mkdir()
    for name in names:
        (root / name).touch()

    index = discover_artifacts(root)

    assert len(index.find(kind="image", subject_id="SUBJ001", site="radius", session_id="T1")) == 1
    assert len(index.find(kind="image", subject_id="SUBJ001", site="radius_left", session_id="T1")) == 1
    assert len(index.find(kind="image", subject_id="SUBJ001", site="radius_right", session_id="T1")) == 1
    assert index.find(kind="mask", role="trab", site="radius")[0].path.name.endswith("_TRAB_MASK.AIM")
    assert index.find(kind="mask", role="cort", site="radius")[0].path.name.endswith("_CORT_MASK.AIM")
    assert index.find(kind="mask", role="registration", site="radius")[0].path.name.endswith("_REGMASK.AIM")
    assert index.find(kind="mask", role="roi1", site="radius")[0].path.name.endswith("_ROI1.AIM")
    assert index.find(kind="mask", role="mask2", site="radius")[0].path.name.endswith("_MASK2.AIM")


def test_discover_artifacts_preserves_split_multistack_index(tmp_path: Path) -> None:
    root = tmp_path / "nina"
    for name in (
        "BMLT_006_KN_STACK1_T0.AIM",
        "BMLT_006_KN_STACK2_T0.AIM",
        "BMLT_006_KN_STACK_03_T0.AIM",
        "BMLT_006_KN_STACK-04_T0.AIM",
    ):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).touch()

    index = discover_artifacts(root)

    records = sorted(
        index.find(kind="image", subject_id="BMLT_006", site="knee", session_id="T0"),
        key=lambda record: record.stack_index or 0,
    )
    assert [record.stack_index for record in records] == [1, 2, 3, 4]


def test_user_overrides_replace_inferred_identity_and_record_provenance(tmp_path: Path) -> None:
    """A manual correction in a batch table must be the value downstream tools consume."""
    record = ArtifactRecord(
        path=tmp_path / "STRAMBO_0001_RL_Y00.AIM",
        kind="image",
        role="image",
        subject_id="STRAMBO_0001",
        session_id="00",
        site="radius_left",
        format="aim",
        subject_source="filename",
        session_source="filename",
        site_source="filename",
        role_source="filename",
    )

    corrected = apply_overrides(record, {"site": "tibia_right", "session_id": "baseline"})

    assert corrected.site == "tibia_right"
    assert corrected.session_id == "baseline"
    assert corrected.site_source == "user_override"
    assert corrected.session_source == "user_override"
    assert corrected.metadata["previous_site"] == "radius_left"
    assert corrected.metadata["previous_session_id"] == "00"


def test_sidecar_mask_role_marks_unstructured_volume_as_mask(tmp_path: Path) -> None:
    """A sidecar role should be enough when a user-authored file has a loose name."""
    path = tmp_path / "outer-roi.nii.gz"
    path.write_bytes(b"mask")
    path.with_name("outer-roi.nii.gz.json").write_text(
        '{"subject_id": "S01", "session_id": "baseline", "site": "tibia_right", "role": "full"}'
    )

    index = discover_artifacts(tmp_path)

    assert len(index.records) == 1
    record = index.records[0]
    assert record.kind == "mask"
    assert record.role == "full"
    assert record.subject_id == "S01"


def test_derivative_maps_are_not_plain_input_images(tmp_path: Path) -> None:
    path = (
        tmp_path
        / "derivatives"
        / "Microarchitecture"
        / "sub-S01"
        / "site-tibia"
        / "ses-T1"
        / "maps"
        / "sub-S01_ses-T1_site-tibia_map-tb-th.nii.gz"
    )
    path.parent.mkdir(parents=True)
    path.touch()

    index = discover_artifacts(tmp_path)

    assert len(index.records) == 1
    assert index.records[0].kind == "image"
    assert index.records[0].role == "map"
    assert index.find(kind="image", role="image") == []


def test_index_reports_missing_roles_per_session(tmp_path: Path) -> None:
    """Slicer tables should display missing masks instead of marking rows ready."""
    root = tmp_path / "dataset"
    (root / "S01_DT_T1.AIM").parent.mkdir(parents=True)
    (root / "S01_DT_T1.AIM").touch()
    mask_root = root / "derivatives" / "Segmentation" / "sub-S01" / "site-tibia" / "ses-T1" / "masks"
    mask_root.mkdir(parents=True)
    (mask_root / "S01_DT_T1_mask-full.nii.gz").touch()

    index = discover_artifacts(root)
    missing = index.missing_roles(
        subject_id="S01",
        site="tibia",
        session_id="T1",
        required_roles=("segmentation", "full", "trab"),
    )

    assert missing == ("segmentation", "trab")
