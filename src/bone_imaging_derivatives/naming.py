"""Naming diagnostics built on shared artifact discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Callable, Mapping, Any

from .artifacts import ArtifactRecord, discover_artifacts, normalize_session_id, normalize_site, normalize_subject_id, site_category


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
    return f"sub-{subject}_site-{site}_ses-{session}{stack}_{suffix}{extension}"


def build_rename_plan(
    dataset_root: str | Path,
    *,
    manifest_path: str | Path | None = None,
    metadata_reader: Callable[[Path], Mapping[str, Any] | None] | None = None,
) -> RenamePlan:
    """Build a reversible, collision-checked rename plan for normalized filenames."""
    root = Path(dataset_root).resolve()
    rows = build_naming_rows(root, metadata_reader=metadata_reader)
    renames: list[tuple[Path, Path]] = []
    target_paths: set[Path] = set()
    for row in rows:
        if row.problem or row.kind not in {"image", "mask", "transform"}:
            continue
        if _is_generated_output(row.path, root):
            continue
        target = row.path.with_name(suggested_filename(row)).resolve()
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
    restored = 0
    for item in reversed(renames):
        source = Path(item["original_path"])
        target = Path(item["renamed_path"])
        if not target.exists():
            continue
        if source.exists():
            raise FileExistsError(f"Cannot restore {source}; path already exists")
        target.rename(source)
        restored += 1
    return restored


def _row_from_record(record: ArtifactRecord) -> NamingRow:
    missing = []
    identity_required = record.kind in {"image", "mask", "transform"}
    if identity_required and not record.subject_id:
        missing.append("subject")
    if not record.session_id and record.kind in {"image", "mask"}:
        missing.append("session")
    if not record.site and record.kind in {"image", "mask"}:
        missing.append("site")
    problem = ""
    if missing:
        problem = f"Missing {_human_join(missing)}."
    elif identity_required and record.identity_confidence == "low":
        problem = "Low-confidence identity; review recommended."
    return NamingRow(
        path=record.path,
        kind=record.kind,
        role=record.role,
        subject_id=record.subject_id,
        session_id=record.session_id,
        site=record.site,
        site_category=site_category(record.site),
        stack_index=record.stack_index,
        confidence=record.identity_confidence,
        problem=problem,
    )


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


def _image_extension(path: Path) -> str:
    name = path.name
    lower = name.lower()
    if lower.endswith(".aim;1"):
        return ".AIM;1"
    if lower.endswith(".aim"):
        return ".AIM"
    if lower.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix


def _sidecar_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.json")


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
