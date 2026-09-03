"""Shared profile and workflow asset registry for Bone Imaging tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class ProfileRecord:
    """One saved or registered reusable tool profile."""

    tool: str
    name: str
    kind: str
    path: Path
    source: str = "user"
    metadata: dict[str, Any] | None = None


def default_profile_root() -> Path:
    """Return the central user-writable profile registry root."""
    return Path.home() / ".slicerboneimagingtoolbox" / "profiles"


def tool_profile_dir(tool: str, *, root: Path | None = None) -> Path:
    """Return the profile directory for one tool, creating it if needed."""
    base = Path(root).expanduser() if root is not None else default_profile_root()
    path = base / _safe_token(tool)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json_profile(
    tool: str,
    name: str,
    payload: dict[str, Any],
    *,
    root: Path | None = None,
) -> ProfileRecord:
    """Save a JSON profile payload into the shared profile registry."""
    directory = tool_profile_dir(tool, root=root)
    path = directory / f"{_safe_token(name)}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    record = ProfileRecord(_safe_token(tool), str(name), "json", path, "user", {})
    _write_registry_record(record, root=root)
    return record


def register_profile_asset(
    tool: str,
    name: str,
    path: Path,
    *,
    kind: str,
    root: Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProfileRecord:
    """Index an existing profile asset such as a ``.parosol-workflow`` bundle."""
    asset_path = Path(path).expanduser()
    record = ProfileRecord(_safe_token(tool), str(name), str(kind), asset_path, "user", dict(metadata or {}))
    tool_profile_dir(tool, root=root)
    _write_registry_record(record, root=root)
    return record


def list_profiles(tool: str | None = None, *, root: Path | None = None) -> tuple[ProfileRecord, ...]:
    """List registered profiles, optionally limited to one tool."""
    registry_path = _registry_path(root)
    if not registry_path.exists():
        return ()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    requested_tool = _safe_token(tool) if tool else ""
    records = []
    for item in payload.get("profiles", []):
        if requested_tool and item.get("tool") != requested_tool:
            continue
        record = _record_from_json(item)
        if not record.path.exists():
            continue
        records.append(record)
    return tuple(sorted(records, key=lambda record: (record.tool, record.name.lower(), record.kind)))


def delete_profile(tool: str, name: str, kind: str = "json", *, root: Path | None = None) -> None:
    """Remove a saved profile record from the shared registry."""
    registry_path = _registry_path(root)
    if not registry_path.exists():
        return
    requested = (_safe_token(tool), str(name), str(kind))
    records = [
        record
        for record in list_profiles(root=root)
        if (record.tool, record.name, record.kind) != requested
    ]
    payload = {"schema": "bone-imaging-profile-registry-v1", "profiles": [_record_to_json(item) for item in records]}
    registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def load_profile_payload(profile: ProfileRecord | Path) -> dict[str, Any]:
    """Load the JSON payload for a JSON profile record or path."""
    path = profile.path if isinstance(profile, ProfileRecord) else Path(profile).expanduser()
    return json.loads(path.read_text(encoding="utf-8"))


def _write_registry_record(record: ProfileRecord, *, root: Path | None) -> None:
    registry_path = _registry_path(root)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing = list(list_profiles(root=root))
    key = (record.tool, record.name, record.kind)
    records = [item for item in existing if (item.tool, item.name, item.kind) != key]
    records.append(record)
    payload = {"schema": "bone-imaging-profile-registry-v1", "profiles": [_record_to_json(item) for item in records]}
    registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _registry_path(root: Path | None) -> Path:
    base = Path(root).expanduser() if root is not None else default_profile_root()
    return base / "profile_registry.json"


def _record_to_json(record: ProfileRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["path"] = str(record.path)
    payload["metadata"] = dict(record.metadata or {})
    return payload


def _record_from_json(payload: dict[str, Any]) -> ProfileRecord:
    return ProfileRecord(
        tool=str(payload["tool"]),
        name=str(payload["name"]),
        kind=str(payload["kind"]),
        path=Path(str(payload["path"])).expanduser(),
        source=str(payload.get("source", "user")),
        metadata=dict(payload.get("metadata") or {}),
    )


def _safe_token(value: str | None) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip()).strip("-").lower()
    return token or "profile"
