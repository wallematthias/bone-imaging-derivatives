from pathlib import Path

from bone_imaging_derivatives import DerivativeManifest, DerivativeRecord, WorkflowRequirement, resolve_workflow_plan


def test_planner_blocks_common_region_without_registration_when_generation_disabled(tmp_path: Path) -> None:
    """Missing required transforms must block a common-region run when generation is disabled."""
    manifest = DerivativeManifest.create("Registration", tmp_path, {"name": "test", "version": "1"}, (), "2026-08-29T00:00:00Z")

    plan = resolve_workflow_plan("CommonRegion", manifests=(manifest,), subject_id="S01", site="tibia", sessions=("1", "2"), generate_missing=False)

    assert plan.blocked is True
    assert plan.missing[0].derivative == "Registration"
    assert plan.missing[0].roles == ("transform_to_reference",)


def test_planner_allows_missing_prerequisite_generation(tmp_path: Path) -> None:
    """The generation option should turn a satisfiable prerequisite into an executable step."""
    plan = resolve_workflow_plan("Timelapse", manifests=(), subject_id="S01", site="tibia", sessions=("1", "2"), generate_missing=True)

    assert plan.blocked is False
    assert any("Generate Registration" in step for step in plan.steps)


def test_planner_requires_transform_for_every_non_reference_session(tmp_path: Path) -> None:
    """Treating one session's transform as all sessions' input would start incomplete work."""
    first_session_transform = DerivativeRecord(
        "Registration", "transform_to_reference", "S01", "tibia", "1", None,
        "native", tmp_path / "ses-1.tfm", "generated",
    )
    manifest = DerivativeManifest.create(
        "Registration", tmp_path, {"name": "test", "version": "1"},
        (first_session_transform,), "2026-08-29T00:00:00Z",
    )

    plan = resolve_workflow_plan("CommonRegion", manifests=(manifest,), subject_id="S01", site="tibia",
                                 sessions=("1", "2"), generate_missing=False)

    assert plan.blocked is True
    assert plan.missing == (WorkflowRequirement("Registration", ("transform_to_reference",)),)
    assert any("sessions: 2" in step for step in plan.steps)
