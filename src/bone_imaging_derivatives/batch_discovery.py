"""Strict discovery primitives for normalized bone imaging batch datasets."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from .manifest import read_manifest

_IMAGE_SUFFIX = r"(?:\.aim(?:;\d+)?|\.isq|\.scv|\.mha|\.mhd|\.nii(?:\.gz)?|\.nrrd|\.nhdr)"
_RAW_NAME = re.compile(
    rf"^sub-(?P<subject>[A-Za-z0-9.]+)_ses-(?P<session>[A-Za-z0-9.]+)_voi-(?P<voi>[A-Za-z0-9]+)"
    rf"(?:_stack-(?P<stack>\d+))?_xct{_IMAGE_SUFFIX}$",
    re.IGNORECASE,
)
_DERIVATIVE_IMAGE_NAME = re.compile(
    rf"^sub-(?P<subject>[A-Za-z0-9.]+)_ses-(?P<session>[A-Za-z0-9.]+)_voi-(?P<voi>[A-Za-z0-9]+)"
    rf"(?:_stack-(?P<stack>\d+))?_desc-(?P<role>[A-Za-z0-9._-]+)_(?:mask|label|map){_IMAGE_SUFFIX}$",
    re.IGNORECASE,
)
_TRANSFORM_NAME = re.compile(
    r"^sub-(?P<subject>[A-Za-z0-9.]+)_ses-(?P<session>[A-Za-z0-9.]+)_voi-(?P<voi>[A-Za-z0-9]+)"
    r"(?:_stack-(?P<stack>\d+))?_from-ses-(?P<moving>[A-Za-z0-9.]+)_to-ses-(?P<fixed>[A-Za-z0-9.]+)"
    r"_(?P<kind>pairwise|baseline)\.(?:tfm|h5|dat)$",
    re.IGNORECASE,
)
_ROLE_ALIASES = {
    "seg": "segmentation",
    "segmentation": "segmentation",
    "bone_segmentation": "segmentation",
    "full": "full",
    "periosteal": "full",
    "periosteal_mask": "full",
    "trab": "trab",
    "trabecular": "trab",
    "trabecular_mask": "trab",
    "cort": "cort",
    "cortical": "cort",
    "cortical_mask": "cort",
    "fea_materials": "material_labelmap",
    "material": "material_labelmap",
    "material_label": "material_labelmap",
    "material_labelmap": "material_labelmap",
    "hom_ls": "material_labelmap",
    "model_label": "material_labelmap",
    "model_labelmap": "material_labelmap",
}
_CONTOUR_FAMILY_PRIORITY = {"IPLContours": 0, "ImportedContours": 0, "BoneContours": 1}


@dataclass(frozen=True, order=True)
class CaseKey:
    """One subject-session-VOI-stack acquisition key."""

    subject_id: str
    session_id: str
    voi: str
    stack_index: int | None = None

    def __post_init__(self) -> None:
        if not self.subject_id or not self.session_id or not self.voi:
            raise ValueError("CaseKey requires subject_id, session_id, and voi")
        if self.stack_index is not None and self.stack_index < 1:
            raise ValueError("stack_index must be positive when provided")


@dataclass(frozen=True)
class BatchArtifact:
    """A normalized raw or derivative artifact usable by batch tools."""

    path: Path
    key: CaseKey
    role: str
    derivative: str | None = None
    source: str = "file"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ContourSelection(Mapping[str, BatchArtifact]):
    """Preferred contour candidates plus any unresolved equal-priority ties."""

    selected: Mapping[str, BatchArtifact]
    review_roles: tuple[str, ...] = ()

    def __iter__(self) -> Iterator[str]:
        return iter(self.selected)

    def __len__(self) -> int:
        return len(self.selected)

    def __getitem__(self, role: str) -> BatchArtifact:
        return self.selected[role]


@dataclass(frozen=True)
class PrerequisiteResult:
    status: str
    missing_roles: tuple[str, ...] = ()
    review_roles: tuple[str, ...] = ()


def discover_raw_xct_images(dataset_root: str | Path) -> tuple[BatchArtifact, ...]:
    """Discover only raw images in the normalized ``sub-*/ses-*/xct`` layout."""
    root = Path(dataset_root).resolve()
    images: list[BatchArtifact] = []
    for path in sorted(root.glob("sub-*/ses-*/xct/*")):
        if not path.is_file():
            continue
        artifact = _artifact_from_filename(path, root, None, _RAW_NAME, "image")
        if artifact is not None:
            virtual_stacks = _virtual_stacks(path, artifact)
            if virtual_stacks is None:
                images.append(artifact)
            elif virtual_stacks:
                images.extend(virtual_stacks)
            else:
                images.append(BatchArtifact(path, artifact.key, artifact.role, artifact.derivative,
                                            artifact.source, {"review_reason": "invalid_virtual_stacks"}))
    return tuple(images)


def discover_derivative_artifacts(dataset_root: str | Path, derivative_family: str) -> tuple[BatchArtifact, ...]:
    """Discover normalized artifacts in one family, reading its manifest first."""
    root = Path(dataset_root).resolve()
    family_root = root / "derivatives" / derivative_family
    if not family_root.exists():
        return ()
    found: dict[Path, BatchArtifact] = {}
    manifest_path = family_root / "manifest.json"
    if manifest_path.exists():
        manifest = read_manifest(manifest_path)
        if manifest.derivative_family != derivative_family:
            raise ValueError(f"Manifest family does not match directory: {manifest_path}")
        for record in manifest.records:
            artifact = _artifact_from_manifest(record.path, record.subject_id, record.session_id, record.site,
                                               record.stack_index, record.role, derivative_family, record.source,
                                               family_root, metadata=record.metadata)
            if artifact is not None:
                found[artifact.path.resolve()] = artifact
    for path in sorted(family_root.glob("sub-*/ses-*/xct/*")):
        if not path.is_file():
            continue
        artifact = _artifact_from_filename(path, root, derivative_family, _DERIVATIVE_IMAGE_NAME, None)
        if artifact is not None:
            found.setdefault(artifact.path.resolve(), artifact)
    for path in sorted(family_root.glob("sub-*/ses-*/xct/*/*")):
        if not path.is_file():
            continue
        artifact = _artifact_from_transform_filename(path, root, derivative_family)
        if artifact is not None:
            found.setdefault(artifact.path.resolve(), artifact)
    return tuple(sorted(found.values(), key=lambda artifact: str(artifact.path)))


def preferred_contours(artifacts: Sequence[BatchArtifact], key: CaseKey) -> ContourSelection:
    """Choose contours by family preference without hiding equal-priority conflicts."""
    grouped: dict[str, list[BatchArtifact]] = {}
    for artifact in artifacts:
        if case_keys_match(artifact.key, key) and artifact.role in _ROLE_ALIASES.values():
            grouped.setdefault(artifact.role, []).append(artifact)
    selected: dict[str, BatchArtifact] = {}
    review_roles: list[str] = []
    for role, candidates in grouped.items():
        ordered = sorted(candidates, key=lambda artifact: (_family_priority(artifact.derivative), str(artifact.path)))
        selected[role] = ordered[0]
        if len(ordered) > 1 and _family_priority(ordered[0].derivative) == _family_priority(ordered[1].derivative):
            review_roles.append(role)
    return ContourSelection(selected, tuple(sorted(review_roles)))


def prerequisite_status(
    image: BatchArtifact,
    contours: ContourSelection,
    *,
    required_roles: Sequence[str],
    existing_outputs: Sequence[BatchArtifact] = (),
) -> PrerequisiteResult:
    """Classify a batch row as ready, loadable, missing, or needing review."""
    required = tuple(_normalize_role(role) for role in required_roles)
    missing = tuple(role for role in required if role not in contours)
    if any(case_keys_match(output.key, image.key) for output in existing_outputs):
        return PrerequisiteResult("loadable")
    if image.metadata.get("review_reason") or contours.review_roles:
        return PrerequisiteResult("review", missing, contours.review_roles)
    if missing:
        return PrerequisiteResult("missing", missing)
    return PrerequisiteResult("ready")


def case_keys_match(left: CaseKey, right: CaseKey) -> bool:
    """Return whether two case keys refer to the same acquisition.

    Stack identity is intentionally strict. A single-stack acquisition should
    be represented without a stack index; a split or virtual stack should carry
    an explicit positive stack index. Keeping those identities separate avoids
    accidental cross-matching when datasets mix native single-stack scans and
    materialized multistack views.
    """
    return (
        left.subject_id == right.subject_id
        and left.session_id == right.session_id
        and left.voi == right.voi
        and left.stack_index == right.stack_index
    )


def _artifact_from_filename(
    path: Path,
    root: Path,
    derivative: str | None,
    pattern: re.Pattern[str],
    default_role: str | None,
) -> BatchArtifact | None:
    match = pattern.match(path.name)
    if match is None:
        return None
    relative = path.relative_to(root)
    base_index = 2 if derivative is not None else 0
    expected = (f"sub-{match.group('subject')}", f"ses-{match.group('session')}", "xct")
    if tuple(relative.parts[base_index:base_index + 3]) != expected:
        return None
    key = CaseKey(match.group("subject"), match.group("session"), _normalize_voi(match.group("voi")), _stack(match.group("stack")))
    role = _normalize_role(match.groupdict().get("role") or default_role or "image")
    return BatchArtifact(path, key, role, derivative)


def _artifact_from_transform_filename(path: Path, root: Path, derivative: str) -> BatchArtifact | None:
    match = _TRANSFORM_NAME.match(path.name)
    if match is None:
        return None
    relative = path.relative_to(root)
    expected = (f"sub-{match.group('subject')}", f"ses-{match.group('session')}", "xct")
    if tuple(relative.parts[2:5]) != expected:
        return None
    kind = match.group("kind").lower()
    role = "transform_pairwise" if kind == "pairwise" else "transform_to_reference"
    metadata = {
        "from_session_id": match.group("moving"),
        "to_session_id": match.group("fixed"),
    }
    return BatchArtifact(
        path,
        CaseKey(match.group("subject"), match.group("session"), _normalize_voi(match.group("voi")), _stack(match.group("stack"))),
        role,
        derivative,
        "file",
        metadata,
    )


def _artifact_from_manifest(
    path: Path,
    subject_id: str,
    session_id: str | None,
    voi: str,
    stack_index: int | None,
    role: str,
    derivative: str,
    source: str,
    family_root: Path,
    metadata: Mapping[str, object] | None = None,
) -> BatchArtifact | None:
    if session_id is None:
        return None
    try:
        relative = path.resolve().relative_to(family_root.resolve())
    except ValueError:
        return None
    if len(relative.parts) < 4 or relative.parts[2] != "xct":
        return None
    if relative.parts[0] != f"sub-{subject_id}" or relative.parts[1] != f"ses-{session_id}":
        return None
    normalized_role = _normalize_role(role)
    return BatchArtifact(
        path,
        CaseKey(subject_id, session_id, _normalize_voi(voi), stack_index),
        normalized_role,
        derivative,
        source,
        metadata or {},
    )


def _normalize_voi(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).lower()


def _normalize_role(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return _ROLE_ALIASES.get(token, token)


def _stack(value: str | None) -> int | None:
    return int(value) if value is not None else None


def _family_priority(derivative: str | None) -> int:
    return _CONTOUR_FAMILY_PRIORITY.get(derivative or "", 2)


def _virtual_stacks(path: Path, artifact: BatchArtifact) -> tuple[BatchArtifact, ...] | None:
    """Build stack-slice views declared in an optional normalized image sidecar."""
    sidecar_path = path.with_name(f"{path.name}.json")
    if not sidecar_path.exists():
        return None
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    declarations = sidecar.get("virtual_stacks") if isinstance(sidecar, dict) else None
    if declarations is None:
        return None
    if not isinstance(declarations, list):
        return ()
    views: list[BatchArtifact] = []
    for declaration in declarations:
        if not isinstance(declaration, dict):
            return ()
        stack_index = declaration.get("stack_index")
        slice_start = declaration.get("slice_start")
        slice_stop = declaration.get("slice_stop")
        if (
            not isinstance(stack_index, int)
            or stack_index < 1
            or not isinstance(slice_start, int)
            or not isinstance(slice_stop, int)
            or slice_stop <= slice_start
        ):
            return ()
        metadata = {
            "view_type": "stack_slices",
            "slice_axis": "z",
            "slice_start": slice_start,
            "slice_stop": slice_stop,
        }
        views.append(BatchArtifact(path, CaseKey(artifact.key.subject_id, artifact.key.session_id,
                                                 artifact.key.voi, stack_index), artifact.role,
                                   artifact.derivative, "virtual", metadata))
    return tuple(sorted(views, key=lambda view: view.key.stack_index or 0))
