"""Public contract API for bone-imaging derivative datasets."""

from .compatibility import (
    discover_legacy_registered_microarchitecture_records, discover_legacy_timelapsed_records,
    write_compatibility_manifest,
)
from .discovery import discover_manifests, find_records
from .manifest import DerivativeManifest, read_manifest, write_manifest
from .naming import (
    NamingRow,
    RenamePlan,
    build_naming_rows,
    build_rename_plan,
    execute_rename_plan,
    read_rename_manifest,
    suggested_filename,
    undo_rename_manifest,
)
from .planning import WorkflowPlan, WorkflowRequirement, resolve_workflow_plan
from .progress import DerivativeProgressEvent, format_progress_event, parse_progress_event
from .records import DerivativeRecord
from .artifacts import (
    ArtifactIndex,
    ArtifactRecord,
    apply_overrides,
    discover_artifacts,
    normalize_role,
    normalize_session_id,
    normalize_site,
    normalize_subject_id,
    site_category,
)

__all__ = [
    "ArtifactIndex",
    "ArtifactRecord",
    "DerivativeManifest",
    "DerivativeProgressEvent",
    "DerivativeRecord",
    "NamingRow",
    "RenamePlan",
    "WorkflowPlan",
    "WorkflowRequirement",
    "build_naming_rows",
    "build_rename_plan",
    "discover_artifacts",
    "discover_legacy_registered_microarchitecture_records",
    "discover_legacy_timelapsed_records",
    "discover_manifests",
    "execute_rename_plan",
    "find_records",
    "format_progress_event",
    "normalize_role",
    "normalize_session_id",
    "normalize_site",
    "normalize_subject_id",
    "parse_progress_event",
    "read_manifest",
    "read_rename_manifest",
    "resolve_workflow_plan",
    "suggested_filename",
    "site_category",
    "undo_rename_manifest",
    "write_compatibility_manifest",
    "write_manifest",
]
