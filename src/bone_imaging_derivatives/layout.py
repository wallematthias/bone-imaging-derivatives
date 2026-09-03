"""Helpers for the standard derivatives directory layout."""

from pathlib import Path
import re

from .families import DERIVATIVE_FAMILIES, validate_derivative_family


def dataset_root_from_path(root: str | Path) -> Path:
    """Return the dataset root even when a derivatives or family folder is supplied."""
    root = Path(root)
    if root.name in DERIVATIVE_FAMILIES and root.parent.name == "derivatives":
        return root.parent.parent
    if root.name == "derivatives":
        return root.parent
    return root


def derivative_family_root(dataset_root: Path, derivative_family: str) -> Path:
    validate_derivative_family(derivative_family)
    return dataset_root_from_path(dataset_root) / "derivatives" / derivative_family


def manifest_path(dataset_root: Path, derivative_family: str) -> Path:
    return derivative_family_root(dataset_root, derivative_family) / "manifest.json"


def voi_token(site: str) -> str:
    """Return the compact VOI token used in artifact filenames."""
    return re.sub(r"[^A-Za-z0-9]+", "", str(site or "").strip()).lower() or "unknown"


def record_output_path(dataset_root: Path, derivative_family: str, subject_id: str, site: str,
                       *parts: str) -> Path:
    """Build a standard MIDS-like derivative artifact path.

    The site/VOI remains part of manifest records and filenames, not a directory
    level. Legacy caller tokens such as ``native_space`` and ``reference_space``
    are accepted but not emitted.
    """
    if not subject_id or subject_id.startswith("sub-"):
        raise ValueError("subject_id must omit the 'sub-' prefix")
    if not site:
        raise ValueError("site must be non-empty")
    cleaned_parts = [str(part) for part in parts if str(part)]
    cleaned_parts = [
        part for part in cleaned_parts
        if part not in {"native_space", "reference_space", "common_space"}
    ]
    session = None
    for index, part in enumerate(list(cleaned_parts)):
        if part.startswith("ses-"):
            session = part
            cleaned_parts.pop(index)
            break

    base = derivative_family_root(dataset_root, derivative_family) / f"sub-{subject_id}"
    if session:
        base = base / session / "xct"
    else:
        base = base / "xct"
    return base / Path(*cleaned_parts)
