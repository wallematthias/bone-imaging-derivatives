"""Small prerequisite planner shared by package batch workflows."""

from dataclasses import dataclass
from typing import Sequence

from .discovery import find_records
from .manifest import DerivativeManifest
from .records import DerivativeRecord


@dataclass(frozen=True)
class WorkflowRequirement:
    derivative: str
    roles: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class WorkflowPlan:
    workflow: str
    available: tuple[DerivativeRecord, ...]
    missing: tuple[WorkflowRequirement, ...]
    steps: tuple[str, ...]
    blocked: bool


_REQUIREMENTS = {
    "CommonRegion": (WorkflowRequirement("Registration", ("transform_to_reference",)),),
    "Microarchitecture": (WorkflowRequirement("CommonRegion", ("scan_region_native_common",), False),),
    "PlateRodMorphometry": (WorkflowRequirement("CommonRegion", ("scan_region_native_common",), False),),
    "Timelapsed": (
        WorkflowRequirement("Registration", ("transform_to_reference",)),
        WorkflowRequirement("CommonRegion", ("scan_region_native_common",), False),
    ),
    "FEA": (WorkflowRequirement("CommonRegion", ("scan_region_native_common",), False),),
    "Mechanoregulation": (
        WorkflowRequirement("Timelapsed", ("remodelling_pairwise_table",)),
        WorkflowRequirement("FEA", ("solver_output",)),
    ),
}


def resolve_workflow_plan(workflow: str, *, manifests: Sequence[DerivativeManifest], subject_id: str,
                          site: str, sessions: Sequence[str], generate_missing: bool) -> WorkflowPlan:
    """Resolve prerequisites for every selected session.

    The first selected session is the registration reference, so it does not
    require a ``transform_to_reference`` record. All other requirements are
    checked at each requested session.
    """
    if workflow not in _REQUIREMENTS:
        raise ValueError(f"Unknown workflow: {workflow!r}")
    available = tuple(find_records(manifests, subject_id=subject_id, site=site))
    missing: list[WorkflowRequirement] = []
    steps: list[str] = []
    for requirement in _REQUIREMENTS[workflow]:
        required_sessions = tuple(str(session) for session in sessions)
        if requirement.derivative == "Registration" and "transform_to_reference" in requirement.roles:
            required_sessions = required_sessions[1:]
        missing_sessions = tuple(
            session for session in required_sessions
            if not all(any(record.derivative == requirement.derivative and record.role == role
                           and record.session_id == session for record in available)
                       for role in requirement.roles)
        )
        has_all_roles = not missing_sessions
        session_note = f" for sessions: {', '.join(missing_sessions)}" if missing_sessions else ""
        if has_all_roles:
            steps.append(f"Reuse {requirement.derivative} {'/'.join(requirement.roles)}")
        else:
            missing.append(requirement)
            if generate_missing:
                steps.append(f"Generate {requirement.derivative} {'/'.join(requirement.roles)}{session_note}")
            elif requirement.required:
                steps.append(f"Missing {requirement.derivative} {'/'.join(requirement.roles)}{session_note}")
    blocked = any(requirement.required for requirement in missing) and not generate_missing
    return WorkflowPlan(workflow, available, tuple(missing), tuple(steps), blocked)
