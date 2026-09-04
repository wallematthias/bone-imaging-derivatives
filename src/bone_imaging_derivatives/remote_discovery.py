"""JSON discovery entry point for remote batch controllers.

This module intentionally depends only on ``bone-imaging-derivatives`` so a
Slicer desktop session can ask a remote Python environment what a dataset
contains without importing Qt, Slicer, or any analysis package.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Iterable

from .batch_discovery import BatchArtifact, discover_derivative_artifacts, discover_raw_xct_images


DEFAULT_DERIVATIVE_FAMILIES = (
    "IPLContours",
    "ImportedContours",
    "BoneContours",
    "ImportedRegistration",
    "Registration",
    "CommonRegion",
    "Timelapse",
    "Microarchitecture",
    "PlateRodMorphometry",
    "FEA",
    "Mechanoregulation",
)


def normalized_dataset_summary(dataset_root: str | Path) -> dict[str, object]:
    """Return a small status payload for a normalized dataset root."""
    root = _dataset_root(dataset_root)
    subject_dirs = sorted(path for path in root.glob("sub-*") if path.is_dir())
    raw_images = discover_raw_xct_images(root) if root.exists() else ()
    return {
        "ok": bool(root.exists() and subject_dirs and raw_images),
        "subject_count": len(subject_dirs),
        "image_count": len(raw_images),
        "message": _normalized_message(root, subject_dirs, raw_images),
    }


def remote_discovery_payload(
    dataset_root: str | Path,
    *,
    families: Iterable[str] = DEFAULT_DERIVATIVE_FAMILIES,
) -> dict[str, object]:
    """Build a JSON-serializable discovery payload for Slicer remote backends."""
    root = _dataset_root(dataset_root)
    raw_images = discover_raw_xct_images(root) if root.exists() else ()
    derivatives: list[dict[str, object]] = []
    for family in families:
        derivatives.extend(_artifact_payload(artifact, family=family) for artifact in discover_derivative_artifacts(root, family))
    return {
        "dataset_root": str(root.resolve()),
        "normalized": normalized_dataset_summary(root),
        "raw_images": [_artifact_payload(artifact) for artifact in raw_images],
        "derivatives": derivatives,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit normalized bone-imaging dataset discovery as JSON.")
    parser.add_argument("dataset_root")
    parser.add_argument(
        "--family",
        dest="families",
        action="append",
        help="Derivative family to include. May be repeated. Defaults to common toolbox families.",
    )
    parser.add_argument("--indent", type=int, default=None, help="Pretty-print JSON with the given indentation.")
    args = parser.parse_args(argv)

    payload = remote_discovery_payload(args.dataset_root, families=args.families or DEFAULT_DERIVATIVE_FAMILIES)
    print(json.dumps(payload, indent=args.indent, sort_keys=True))
    return 0


def _dataset_root(dataset_root: str | Path) -> Path:
    root = Path(dataset_root).expanduser()
    return root.parent if root.name == "derivatives" else root


def _normalized_message(root: Path, subject_dirs: list[Path], raw_images: tuple[BatchArtifact, ...]) -> str:
    if not root.exists():
        return "Dataset root does not exist."
    if not subject_dirs:
        return "Dataset is not normalized yet. Use Dataset Naming Helper first."
    if not raw_images:
        return "No modality images were found under sub-*/ses-*/xct."
    return f"Normalized dataset with {len(subject_dirs)} subject(s) and {len(raw_images)} modality image(s)."


def _artifact_payload(artifact: BatchArtifact, *, family: str | None = None) -> dict[str, object]:
    key = asdict(artifact.key)
    return {
        "path": str(artifact.path.resolve()),
        "family": family if family is not None else artifact.derivative,
        "role": artifact.role,
        "source": artifact.source,
        "key": key,
        "metadata": dict(artifact.metadata),
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
