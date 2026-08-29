"""Manifest discovery and record filtering."""

from pathlib import Path
from typing import Sequence

from .manifest import DerivativeManifest, read_manifest
from .records import DerivativeRecord


def discover_manifests(dataset_root: Path, *, strict: bool = False) -> list[DerivativeManifest]:
    """Return readable manifests below ``derivatives`` in deterministic path order.

    By default, malformed or incomplete manifests are skipped so an interrupted
    write in one family does not hide completed derivatives in another. Set
    ``strict`` to surface the first read error to validation callers.
    """
    root = Path(dataset_root)
    derivatives = root / "derivatives"
    if not derivatives.exists():
        return []
    manifests: list[DerivativeManifest] = []
    for path in sorted(derivatives.rglob("manifest.json")):
        try:
            manifests.append(read_manifest(path))
        except (OSError, TypeError, ValueError):
            if strict:
                raise
    return manifests


def find_records(manifests: Sequence[DerivativeManifest], *, derivative: str | None = None,
                 role: str | None = None, subject_id: str | None = None, site: str | None = None,
                 session_id: str | None = None, stack_index: int | None = None,
                 space: str | None = None) -> list[DerivativeRecord]:
    """Filter records using only specified attributes."""
    expected = {key: value for key, value in {
        "derivative": derivative, "role": role, "subject_id": subject_id, "site": site,
        "session_id": session_id, "stack_index": stack_index, "space": space,
    }.items() if value is not None}
    return [record for manifest in manifests for record in manifest.records
            if all(getattr(record, key) == value for key, value in expected.items())]
