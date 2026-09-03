"""Naming diagnostics built on shared artifact discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Callable, Mapping, Any, Sequence

from .artifacts import (
    ArtifactRecord,
    discover_artifacts,
    normalize_role,
    normalize_session_id,
    normalize_site,
    normalize_subject_id,
    site_category,
)


@dataclass(frozen=True)
class NamingRow:
    """One row in a dataset naming/preflight table."""

    path: Path
    kind: str
    role: str
    subject_id: str | None
    session_id: str | None
    site: str | None
    site_category: str | None
    stack_index: int | None
    confidence: str
    problem: str


@dataclass(frozen=True)
class RenamePlan:
    """Collision-checked file renames plus the manifest path to write."""

    dataset_root: Path
    manifest_path: Path
    renames: tuple[tuple[Path, Path], ...]


def build_naming_rows(
    dataset_root: str | Path,
    *,
    metadata_reader: Callable[[Path], Mapping[str, Any] | None] | None = None,
) -> list[NamingRow]:
    """Return naming diagnostics for all discovered artifacts below ``dataset_root``."""
    index = discover_artifacts(dataset_root, include_derivatives=True)
    records = [
        _enrich_record_from_metadata(record, metadata_reader)
        if metadata_reader is not None
        else record
        for record in index.records
    ]
    records = _inherit_missing_sites_from_images(records)
    rows = [_row_from_record(record) for record in records]
    return sorted(rows, key=lambda row: str(row.path).lower())


def suggested_filename(row: NamingRow | ArtifactRecord) -> str:
    """Return a strict normalized filename suggestion for a discovered artifact."""
    subject = row.subject_id or "UNKNOWN"
    session = row.session_id or "UNKNOWN"
    site = row.site or "unknown"
    stack = f"_stack-{int(row.stack_index):02d}" if row.stack_index is not None else ""
    extension = _image_extension(row.path)
    role = getattr(row, "role", "")
    kind = getattr(row, "kind", "")
    suffix = "image"
    if kind == "mask":
        suffix = f"mask-{role or 'unknown'}"
    elif kind == "transform":
        suffix = "transform"
    elif kind == "table":
        suffix = "table"
    elif role and role not in {"image"}:
        suffix = role
    return f"sub-{subject}_ses-{session}_voi-{_voi_label(site)}{stack}_{suffix}{extension}"


def suggested_mids_relative_path(
    row: NamingRow | ArtifactRecord,
    *,
    subject_label: str | None = None,
    session_label: str | None = None,
) -> Path:
    """Return the normalized Bone Imaging MIDS-style relative path for ``row``.

    Raw XCT images are placed in ``sub-*/ses-*/xct``. Imported scanner/IPL
    masks are treated as source-derived contours in ``derivatives/IPLContours``;
    imported scanner/IPL maps are placed in ``derivatives/IPLAnalysis``.
    """
    subject = _label_without_prefix(subject_label, "sub") or _safe_entity_label(row.subject_id or "unknown")
    session = _label_without_prefix(session_label, "ses") or _safe_entity_label(row.session_id or "unknown")
    voi = _voi_label(row.site)
    stack = f"_stack-{int(row.stack_index):02d}" if row.stack_index is not None else ""
    extension = _image_extension(row.path)
    prefix = f"sub-{subject}_ses-{session}_voi-{voi}{stack}"
    kind = getattr(row, "kind", "")
    role = normalize_role(getattr(row, "role", "")) or getattr(row, "role", "")
    if kind == "mask":
        desc = _safe_entity_label(role or "mask")
        return Path("derivatives") / "IPLContours" / f"sub-{subject}" / f"ses-{session}" / "xct" / f"{prefix}_desc-{desc}_mask{extension}"
    if kind == "image" and role == "map":
        desc = _safe_entity_label(_map_description_from_name(row.path))
        return Path("derivatives") / "IPLAnalysis" / f"sub-{subject}" / f"ses-{session}" / "xct" / f"{prefix}_desc-{desc}_map{extension}"
    return Path(f"sub-{subject}") / f"ses-{session}" / "xct" / f"{prefix}_xct{extension}"


def suggested_mids_relative_paths(rows: Sequence[NamingRow | ArtifactRecord]) -> dict[Path, Path]:
    """Return context-aware normalized relative paths keyed by source path."""
    row_list = list(rows)
    subject_labels = _subject_labels(row_list)
    session_labels = _session_labels(row_list, subject_labels)
    suggestions: dict[Path, Path] = {}
    for row in row_list:
        source = Path(row.path)
        subject_label = subject_labels.get(getattr(row, "subject_id", "") or "")
        session_label = session_labels.get((getattr(row, "subject_id", "") or "", getattr(row, "session_id", "") or ""))
        suggestions[source] = suggested_mids_relative_path(
            row,
            subject_label=subject_label,
            session_label=session_label,
        )
    return suggestions


def apply_naming_row_overrides(
    row: NamingRow,
    overrides: Mapping[str, str | None],
) -> NamingRow:
    """Return a naming-review row with user edits normalized and revalidated."""
    subject_id = row.subject_id
    session_id = row.session_id
    site = row.site
    role = row.role
    stack_index = row.stack_index

    if "subject_id" in overrides:
        subject_id = normalize_subject_id(overrides["subject_id"])
    if "session_id" in overrides:
        session_id = normalize_session_id(overrides["session_id"])
    if "site" in overrides:
        site = normalize_site(overrides["site"])
    if "role" in overrides:
        role = normalize_role(overrides["role"]) or ""
    if "stack_index" in overrides:
        stack_index = _normalize_stack_override(overrides["stack_index"])

    updated = NamingRow(
        path=row.path,
        kind=row.kind,
        role=role,
        subject_id=subject_id,
        session_id=session_id,
        site=site,
        site_category=site_category(site),
        stack_index=stack_index,
        confidence="user",
        problem="",
    )
    return _row_with_recomputed_problem(updated)


def build_rename_plan(
    dataset_root: str | Path,
    *,
    manifest_path: str | Path | None = None,
    metadata_reader: Callable[[Path], Mapping[str, Any] | None] | None = None,
) -> RenamePlan:
    """Build a reversible, collision-checked rename plan for normalized filenames."""
    root = Path(dataset_root).resolve()
    rows = build_naming_rows(root, metadata_reader=metadata_reader)
    eligible_rows = [
        row
        for row in rows
        if not row.problem and row.kind in {"image", "mask", "transform"} and not _is_generated_output(row.path, root)
    ]
    subject_labels = _subject_labels(eligible_rows)
    session_labels = _session_labels(eligible_rows, subject_labels)
    renames: list[tuple[Path, Path]] = []
    target_paths: set[Path] = set()
    for row in eligible_rows:
        subject_label = subject_labels.get(row.subject_id or "")
        session_label = session_labels.get((row.subject_id or "", row.session_id or ""))
        target = (root / suggested_mids_relative_path(row, subject_label=subject_label, session_label=session_label)).resolve()
        source = row.path.resolve()
        if source == target:
            continue
        if target.exists() and target != source:
            raise FileExistsError(f"Rename target already exists: {target}")
        if target in target_paths:
            raise FileExistsError(f"Multiple files would be renamed to: {target}")
        renames.append((source, target))
        target_paths.add(target)
        source_sidecar = _sidecar_path(source)
        target_sidecar = _sidecar_path(target)
        if source_sidecar.exists() and source_sidecar.resolve() != target_sidecar.resolve():
            if target_sidecar.exists():
                raise FileExistsError(f"Rename target already exists: {target_sidecar}")
            renames.append((source_sidecar.resolve(), target_sidecar.resolve()))
            target_paths.add(target_sidecar.resolve())
    if manifest_path is None:
        manifest_path = root / "dataset_rename_manifest.json"
    return RenamePlan(root, Path(manifest_path).resolve(), tuple(renames))


def execute_rename_plan(plan: RenamePlan) -> Path:
    """Rename files and write a manifest that can restore original paths."""
    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_root": str(plan.dataset_root),
        "renames": [
            {"original_path": str(source), "renamed_path": str(target)}
            for source, target in plan.renames
        ],
    }
    plan.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.manifest_path.exists():
        raise FileExistsError(f"Rename manifest already exists: {plan.manifest_path}")
    for source, target in plan.renames:
        if not source.exists():
            raise FileNotFoundError(f"Rename source is missing: {source}")
        if target.exists():
            raise FileExistsError(f"Rename target already exists: {target}")
    moved: list[tuple[Path, Path]] = []
    try:
        for source, target in plan.renames:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            moved.append((source, target))
    except Exception:
        for source, target in reversed(moved):
            if target.exists() and not source.exists():
                target.rename(source)
        raise
    plan.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return plan.manifest_path


def read_rename_manifest(path: str | Path) -> dict[str, Any]:
    """Read a rename manifest."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def undo_rename_manifest(path: str | Path) -> int:
    """Undo renames recorded in a manifest, returning the number of files restored."""
    manifest = read_rename_manifest(path)
    renames = manifest.get("renames", [])
    dataset_root = Path(manifest.get("dataset_root") or Path(path).parent).resolve()
    restored = 0
    cleanup_dirs: list[Path] = []
    for item in reversed(renames):
        source = Path(item["original_path"])
        target = Path(item["renamed_path"])
        cleanup_dirs.append(target.parent)
        if _is_sidecar_file(source) or _is_sidecar_file(target):
            if target.exists():
                target.unlink()
            if source.exists():
                source.unlink()
            continue
        if not target.exists():
            continue
        if source.exists():
            raise FileExistsError(f"Cannot restore {source}; path already exists")
        target.rename(source)
        restored += 1
    _prune_empty_dirs(cleanup_dirs, stop_at=dataset_root)
    return restored


IDENTIFIABLE_METADATA_KEYS = {
    "patient",
    "patient_name",
    "patientname",
    "index_patient",
    "index patient",
    "name",
    "birth",
    "birthdate",
    "birth_date",
    "date_of_birth",
    "dob",
    "sex",
}
PUBLIC_METADATA_KEYS = {
    "subject_id",
    "session_id",
    "site",
    "role",
    "stack_index",
    "scanner",
    "scanner_model",
    "modality",
    "voi",
}


def split_identity_metadata(metadata: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split workflow sidecar metadata from private identity-bearing metadata.

    The public payload is intentionally small and contains only fields used for
    dataset discovery. Raw AIM headers and processing logs are retained in the
    private payload because they may include patient identifiers or dates.
    """
    public = {
        key: value
        for key, value in metadata.items()
        if value not in (None, "") and _metadata_key_is_public(key)
    }
    private = {
        key: value
        for key, value in metadata.items()
        if value not in (None, "") and not _metadata_key_is_public(key)
    }
    log = metadata.get("processing_log_raw", metadata.get("processing_log", ""))
    if isinstance(log, Mapping):
        log = "\n".join(f"{key} {value}" for key, value in log.items())
    if isinstance(log, str) and log.strip():
        identifiable_lines = _identifiable_processing_log_lines(log)
        if identifiable_lines:
            private["processing_log_identifiable_lines"] = identifiable_lines
    return public, private


def _row_from_record(record: ArtifactRecord) -> NamingRow:
    return _row_with_recomputed_problem(
        NamingRow(
            path=record.path,
            kind=record.kind,
            role=record.role,
            subject_id=record.subject_id,
            session_id=record.session_id,
            site=record.site,
            site_category=site_category(record.site),
            stack_index=record.stack_index,
            confidence=record.identity_confidence,
            problem="",
        )
    )


def _row_with_recomputed_problem(row: NamingRow) -> NamingRow:
    missing = []
    identity_required = row.kind in {"image", "mask", "transform"}
    if identity_required and not row.subject_id:
        missing.append("subject")
    if not row.session_id and row.kind in {"image", "mask"}:
        missing.append("session")
    if not row.site and row.kind in {"image", "mask"}:
        missing.append("site")
    problem = ""
    if missing:
        problem = f"Missing {_human_join(missing)}."
    elif identity_required and row.confidence == "low":
        problem = "Low-confidence identity; review recommended."
    return NamingRow(
        path=row.path,
        kind=row.kind,
        role=row.role,
        subject_id=row.subject_id,
        session_id=row.session_id,
        site=row.site,
        site_category=site_category(row.site),
        stack_index=row.stack_index,
        confidence=row.confidence,
        problem=problem,
    )


def _normalize_stack_override(value: str | None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\d+", text)
    if match is None:
        return None
    stack_index = int(match.group(0))
    return stack_index if stack_index > 0 else None


def _enrich_record_from_metadata(
    record: ArtifactRecord,
    metadata_reader: Callable[[Path], Mapping[str, Any] | None],
) -> ArtifactRecord:
    if record.subject_id and record.session_id and record.site:
        return record
    try:
        metadata = metadata_reader(record.path) or {}
    except Exception:
        return record
    processing_log = metadata.get("processing_log")
    if isinstance(processing_log, str):
        processing_log = _parse_processing_log(processing_log)
    if not isinstance(processing_log, Mapping):
        processing_log = metadata.get("processing_log_dict")
    if isinstance(processing_log, str):
        processing_log = _parse_processing_log(processing_log)
    if not isinstance(processing_log, Mapping):
        processing_log = metadata

    subject_id = record.subject_id or normalize_subject_id(_first_metadata_value(processing_log, "Index Patient", "Patient", "subject_id"))
    session_id = record.session_id or normalize_session_id(
        _first_metadata_value(processing_log, "Index Measurement", "Measurement", "session_id")
    )
    site = record.site or normalize_site(_first_metadata_value(processing_log, "Site", "site", "site_id"))
    if subject_id == record.subject_id and session_id == record.session_id and site == record.site:
        return record
    return ArtifactRecord(
        path=record.path,
        kind=record.kind,
        role=record.role,
        subject_id=subject_id,
        session_id=session_id,
        stack_index=record.stack_index,
        site=site,
        format=record.format,
        subject_source=record.subject_source if subject_id == record.subject_id else "metadata",
        session_source=record.session_source if session_id == record.session_id else "metadata",
        site_source=record.site_source if site == record.site else "metadata",
        role_source=record.role_source,
        identity_confidence="high" if subject_id and session_id and site else record.identity_confidence,
        metadata=record.metadata,
    )


def _inherit_missing_sites_from_images(records: list[ArtifactRecord]) -> list[ArtifactRecord]:
    image_sites: dict[tuple[str | None, str | None, int | None], set[str]] = {}
    for record in records:
        if record.kind != "image" or not record.site:
            continue
        key = (record.subject_id, record.session_id, record.stack_index)
        image_sites.setdefault(key, set()).add(record.site)

    updated: list[ArtifactRecord] = []
    for record in records:
        if record.site or record.kind not in {"mask", "transform"}:
            updated.append(record)
            continue
        candidates = image_sites.get((record.subject_id, record.session_id, record.stack_index), set())
        if len(candidates) != 1:
            updated.append(record)
            continue
        site = next(iter(candidates))
        updated.append(
            ArtifactRecord(
                path=record.path,
                kind=record.kind,
                role=record.role,
                subject_id=record.subject_id,
                session_id=record.session_id,
                stack_index=record.stack_index,
                site=site,
                format=record.format,
                subject_source=record.subject_source,
                session_source=record.session_source,
                site_source="group_context",
                role_source=record.role_source,
                identity_confidence="high" if record.subject_id and record.session_id and site else record.identity_confidence,
                metadata=record.metadata,
            )
        )
    return updated


def _first_metadata_value(metadata: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _metadata_key_is_public(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
    compact = normalized.replace("_", "")
    if normalized in PUBLIC_METADATA_KEYS or compact in PUBLIC_METADATA_KEYS:
        return True
    if normalized in IDENTIFIABLE_METADATA_KEYS or compact in IDENTIFIABLE_METADATA_KEYS:
        return False
    return False


def _identifiable_processing_log_lines(text: str) -> list[str]:
    sensitive_tokens = (
        "patient",
        "name",
        "birth",
        "dob",
        "sex",
        "date",
        "operator",
        "institution",
    )
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(token in lowered for token in sensitive_tokens):
            lines.append(stripped)
    return lines


def _parse_processing_log(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    known_keys = ("Index Patient", "Index Measurement", "Site")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            continue
        for key in known_keys:
            match = re.match(rf"(?i){re.escape(key)}\s+(.+)$", stripped)
            if match:
                parsed[key] = match.group(1).strip()
    return parsed


def _human_join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _subject_labels(rows: list[NamingRow]) -> dict[str, str]:
    subjects = sorted({row.subject_id for row in rows if row.subject_id}, key=_natural_key)
    return {subject: f"{index + 1:03d}" for index, subject in enumerate(subjects)}


def _session_labels(rows: list[NamingRow], subject_labels: Mapping[str, str]) -> dict[tuple[str, str], str]:
    labels: dict[tuple[str, str], str] = {}
    for subject in subject_labels:
        sessions = sorted(
            {row.session_id for row in rows if row.subject_id == subject and row.session_id},
            key=_natural_key,
        )
        for index, session in enumerate(sessions):
            labels[(subject, session)] = f"{index + 1:03d}"
    return labels


def _natural_key(value: str | None) -> tuple[Any, ...]:
    text = str(value or "")
    parts = re.split(r"(\d+)", text)
    return tuple(int(part) if part.isdigit() else part.lower() for part in parts)


def _label_without_prefix(value: str | None, prefix: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower().startswith(f"{prefix}-"):
        text = text[len(prefix) + 1 :]
    return _safe_entity_label(text)


def _safe_entity_label(value: str | None) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "", str(value or "").strip()).lower()
    return text or "unknown"


def _voi_label(site: str | None) -> str:
    return _safe_entity_label(normalize_site(site) or site or "unknown")


def _map_description_from_name(path: Path) -> str:
    stem = _strip_known_image_suffix(path.name)
    match = re.search(r"(?i)(?:^|[_-])desc[-_]?([A-Za-z0-9][A-Za-z0-9._-]*)[_-]map$", stem)
    if match:
        return match.group(1)
    match = re.search(r"(?i)(?:^|[_-])map[-_]?([A-Za-z0-9][A-Za-z0-9._-]*)$", stem)
    if match:
        return match.group(1)
    return "map"


def _strip_known_image_suffix(name: str) -> str:
    clean = re.sub(r"\.aim(?:;\d+)?$", "", name, flags=re.IGNORECASE)
    if clean.lower().endswith(".nii.gz"):
        clean = clean[:-7]
    else:
        clean = str(Path(clean).with_suffix(""))
    return clean


def _image_extension(path: Path) -> str:
    name = path.name
    lower = name.lower()
    if re.search(r"\.aim(?:;\d+)?$", lower):
        return ".AIM"
    if lower.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix


def _sidecar_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.json")


def _is_sidecar_file(path: Path) -> bool:
    return path.name.lower().endswith(".json")


def _prune_empty_dirs(paths: Sequence[Path], *, stop_at: Path) -> None:
    stop = stop_at.resolve()
    seen: set[Path] = set()
    for path in paths:
        current = Path(path).resolve()
        while current != stop and stop in current.parents and current not in seen:
            seen.add(current)
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


def _is_generated_output(path: Path, root: Path) -> bool:
    try:
        parts = path.resolve().relative_to(root).parts
    except ValueError:
        return False
    lower_parts = {part.lower() for part in parts}
    if "derivatives" in lower_parts:
        return True
    generated_dirs = {
        "analysis",
        "common_region",
        "measurements",
        "maps",
        "registration",
        "transforms",
        "visualize",
    }
    if lower_parts & generated_dirs:
        return True
    if any("timelapsedhrpqct" in part.lower() for part in parts):
        return True
    name = path.name.lower()
    generated_tokens = ("_remodelling", "_measurements", "_thickness", "_spacing", "_number", "_density")
    return any(token in name for token in generated_tokens)
