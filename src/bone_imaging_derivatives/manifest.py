"""JSON serialization for derivative manifests."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from .families import validate_derivative_family
from .records import DerivativeRecord

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DerivativeManifest:
    schema_version: int
    derivative_family: str
    dataset_root: Path
    records: tuple[DerivativeRecord, ...]
    software: Mapping[str, str]
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema_version: {self.schema_version}")
        validate_derivative_family(self.derivative_family)
        if not self.software.get("name") or not self.software.get("version"):
            raise ValueError("software must include name and version")
        object.__setattr__(self, "dataset_root", Path(self.dataset_root))
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "software", dict(self.software))

    @classmethod
    def create(cls, derivative_family: str, dataset_root: Path, software: Mapping[str, str],
               records: tuple[DerivativeRecord, ...] = (), created_at: str | None = None) -> "DerivativeManifest":
        return cls(SCHEMA_VERSION, derivative_family, Path(dataset_root), tuple(records), dict(software),
                   created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))


def _portable_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _record_payload(record: DerivativeRecord, root: Path) -> dict[str, Any]:
    data: dict[str, Any] = {
        "derivative": record.derivative, "role": record.role, "subject_id": record.subject_id,
        "site": record.site, "session_id": record.session_id, "stack_index": record.stack_index,
        "space": record.space, "path": _portable_path(record.path, root), "source": record.source,
        "inputs": list(record.inputs), "metadata": dict(record.metadata), "record_id": record.record_id,
    }
    for key in ("content_type", "coordinate_reference", "settings_hash", "software"):
        value = getattr(record, key)
        if value is not None:
            data[key] = value
    return data


def write_manifest(manifest: DerivativeManifest, path: Path) -> None:
    """Write an indented, portable schema-v1 JSON manifest."""
    path = Path(path)
    root = manifest.dataset_root.resolve()
    manifest_location = path.resolve()
    dataset_root = "." if _manifest_is_within_dataset(manifest_location, root) else str(root)
    payload = {
        "schema_version": manifest.schema_version, "derivative_family": manifest.derivative_family,
        "software": dict(manifest.software), "dataset_root": dataset_root, "created_at": manifest.created_at,
        "records": [_record_payload(record, root) for record in manifest.records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest_is_within_dataset(path: Path, dataset_root: Path) -> bool:
    try:
        path.relative_to(dataset_root)
    except ValueError:
        return False
    return True


def _dataset_root_from_manifest(path: Path, raw_root: Path) -> Path:
    """Resolve a portable ``'.'`` root from the standard derivatives layout."""
    if raw_root != Path("."):
        return (path.parent / raw_root).resolve()
    for parent in path.parents:
        if parent.name == "derivatives":
            return parent.parent.resolve()
    return path.parent.resolve()


def _required(data: Mapping[str, Any], key: str) -> Any:
    if key not in data:
        raise ValueError(f"Manifest record is missing required field: {key}")
    return data[key]


def _read_record(data: Mapping[str, Any], root: Path) -> DerivativeRecord:
    raw_path = Path(_required(data, "path"))
    path = raw_path if raw_path.is_absolute() else root / raw_path
    return DerivativeRecord(
        derivative=_required(data, "derivative"), role=_required(data, "role"),
        subject_id=_required(data, "subject_id"), site=_required(data, "site"),
        session_id=_required(data, "session_id"), stack_index=_required(data, "stack_index"),
        space=_required(data, "space"), path=path, source=_required(data, "source"),
        inputs=tuple(_required(data, "inputs")), metadata=_required(data, "metadata"),
        record_id=data.get("record_id"), content_type=data.get("content_type"),
        coordinate_reference=data.get("coordinate_reference"), settings_hash=data.get("settings_hash"),
        software=data.get("software"),
    )


def read_manifest(path: Path) -> DerivativeManifest:
    """Read a schema-v1 manifest and resolve relative records from its dataset root."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid manifest JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Manifest must be a JSON object")
    version = _required(payload, "schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {version}")
    raw_root = Path(_required(payload, "dataset_root"))
    root = raw_root if raw_root.is_absolute() else _dataset_root_from_manifest(path, raw_root)
    records_data = _required(payload, "records")
    if not isinstance(records_data, list):
        raise ValueError("records must be a list")
    return DerivativeManifest(version, _required(payload, "derivative_family"), root,
                              tuple(_read_record(record, root) for record in records_data),
                              _required(payload, "software"), _required(payload, "created_at"))
