from pathlib import Path

import pytest

from bone_imaging_derivatives.naming import (
    build_rename_plan,
    execute_rename_plan,
    read_rename_manifest,
    undo_rename_manifest,
)


def test_rename_plan_writes_manifest_and_renames_files(tmp_path: Path) -> None:
    source = tmp_path / "SUBJ001_RL_T1_TRAB_MASK.AIM"
    source.touch()
    manifest = tmp_path / "rename_manifest.json"

    plan = build_rename_plan(tmp_path, manifest_path=manifest)
    written_manifest = execute_rename_plan(plan)

    target = tmp_path / "derivatives" / "IPLContours" / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_desc-trab_mask.AIM"
    assert written_manifest == manifest
    assert target.exists()
    assert not source.exists()

    loaded = read_rename_manifest(manifest)
    assert loaded["renames"][0]["original_path"] == str(source)
    assert loaded["renames"][0]["renamed_path"] == str(target)


def test_rename_plan_places_scanco_dat_transforms_in_imported_registration(tmp_path: Path) -> None:
    source = tmp_path / "sub-SAMPLE341" / "site-tibia" / "ses-T1" / "SAMPLE341_T2-to-T1.DAT"
    source.parent.mkdir(parents=True)
    source.write_text("SCANCO TRANSFORMATION DATA VERSION:   10R4_MAT: 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1")

    manifest = execute_rename_plan(build_rename_plan(tmp_path))

    target = (
        tmp_path
        / "derivatives"
        / "ImportedRegistration"
        / "sub-001"
        / "ses-002"
        / "xct"
        / "pairwise"
        / "sub-001_ses-002_voi-tibia_from-ses-002_to-ses-001_pairwise.DAT"
    )
    assert target.exists()
    assert not source.exists()

    undo_rename_manifest(manifest)

    assert source.exists()
    assert not target.exists()


def test_undo_rename_manifest_restores_original_names(tmp_path: Path) -> None:
    source = tmp_path / "SUBJ001_RL_T1_TRAB_MASK.AIM"
    source.touch()
    manifest = execute_rename_plan(build_rename_plan(tmp_path))
    target = tmp_path / "derivatives" / "IPLContours" / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_desc-trab_mask.AIM"

    restored = undo_rename_manifest(manifest)

    assert restored == 1
    assert source.exists()
    assert not target.exists()
    assert not (tmp_path / "derivatives").exists()


def test_rename_plan_rejects_collisions_before_moving_files(tmp_path: Path) -> None:
    source = tmp_path / "SUBJ001_RL_T1_TRAB_MASK.AIM"
    target = tmp_path / "derivatives" / "IPLContours" / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_desc-trab_mask.AIM"
    source.touch()
    target.parent.mkdir(parents=True)
    target.touch()

    with pytest.raises(FileExistsError, match="Rename target already exists"):
        build_rename_plan(tmp_path)

    assert source.exists()
    assert target.exists()


def test_execute_rename_plan_rejects_existing_manifest(tmp_path: Path) -> None:
    source = tmp_path / "SUBJ001_RL_T1_TRAB_MASK.AIM"
    source.touch()
    manifest = tmp_path / "dataset_rename_manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Rename manifest already exists"):
        execute_rename_plan(build_rename_plan(tmp_path, manifest_path=manifest))

    assert source.exists()


def test_rename_plan_includes_sidecars_when_present(tmp_path: Path) -> None:
    source = tmp_path / "SUBJ001_RL_T1.AIM"
    sidecar = tmp_path / "SUBJ001_RL_T1.AIM.json"
    source.touch()
    sidecar.write_text('{"site": "radius_left"}', encoding="utf-8")

    manifest = execute_rename_plan(build_rename_plan(tmp_path))

    target = tmp_path / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_xct.AIM"
    target_sidecar = tmp_path / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_xct.AIM.json"
    assert target.exists()
    assert target_sidecar.exists()

    undo_rename_manifest(manifest)

    assert source.exists()
    assert not sidecar.exists()
    assert not target_sidecar.exists()
    assert not (tmp_path / "sub-001").exists()


def test_rename_plan_drops_scanco_aim_version_suffix_from_targets(tmp_path: Path) -> None:
    source = tmp_path / "SUBJ001_RL_T1.AIM;1"
    sidecar = tmp_path / "SUBJ001_RL_T1.AIM;1.json"
    source.touch()
    sidecar.write_text('{"site": "radius_left"}', encoding="utf-8")

    manifest = execute_rename_plan(build_rename_plan(tmp_path))

    target = tmp_path / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_xct.AIM"
    target_sidecar = tmp_path / "sub-001" / "ses-001" / "xct" / "sub-001_ses-001_voi-radiusleft_xct.AIM.json"
    assert target.exists()
    assert target_sidecar.exists()
    assert not source.exists()
    assert not sidecar.exists()

    loaded = read_rename_manifest(manifest)
    assert loaded["renames"][0]["original_path"] == str(source)
    assert loaded["renames"][0]["renamed_path"] == str(target)

    undo_rename_manifest(manifest)

    assert source.exists()
    assert not sidecar.exists()
    assert not target_sidecar.exists()
    assert not (tmp_path / "sub-001").exists()


def test_rename_plan_skips_derivative_outputs(tmp_path: Path) -> None:
    derivative = tmp_path / "derivatives" / "BoneContours" / "SUBJ001_RL_T1_TRAB_MASK.AIM"
    derivative.parent.mkdir(parents=True)
    derivative.touch()

    plan = build_rename_plan(tmp_path)

    assert plan.renames == ()


def test_rename_plan_skips_legacy_generated_outputs(tmp_path: Path) -> None:
    generated = (
        tmp_path
        / "TimelapsedHRpQCT-old"
        / "sub-SUBJ001"
        / "site-radius_left"
        / "analysis"
        / "visualize"
        / "sub-SUBJ001_site-radius_left_comp-full_t0-00_t1-04_thr-225p0_cluster-12_remodelling.nii.gz"
    )
    generated.parent.mkdir(parents=True)
    generated.touch()

    plan = build_rename_plan(tmp_path)

    assert plan.renames == ()
