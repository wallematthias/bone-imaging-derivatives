from pathlib import Path

from bone_imaging_derivatives import DerivativeManifest, DerivativeRecord, resolve_workflow_plan


def test_planner_blocks_common_region_without_registration_when_generation_disabled(tmp_path: Path) -> None:
    """Missing required transforms must block a common-region run when generation is disabled."""
    manifest = DerivativeManifest.create("Registration", tmp_path, {"name": "test", "version": "1"}, (), "2026-08-29T00:00:00Z")

    plan = resolve_workflow_plan("CommonRegion", manifests=(manifest,), subject_id="S01", site="tibia", sessions=("1", "2"), generate_missing=False)

    assert plan.blocked is True
    assert plan.missing[0].derivative == "Registration"
    assert plan.missing[0].roles == ("transform_to_reference",)


def test_planner_allows_missing_prerequisite_generation(tmp_path: Path) -> None:
    """The generation option should turn a satisfiable prerequisite into an executable step."""
    plan = resolve_workflow_plan("Timelapsed", manifests=(), subject_id="S01", site="tibia", sessions=("1", "2"), generate_missing=True)

    assert plan.blocked is False
    assert any("Generate Registration" in step for step in plan.steps)
