"""Helpers for the standard derivatives directory layout."""

from pathlib import Path

from .families import validate_derivative_family


def derivative_family_root(dataset_root: Path, derivative_family: str) -> Path:
    validate_derivative_family(derivative_family)
    return Path(dataset_root) / "derivatives" / derivative_family


def manifest_path(dataset_root: Path, derivative_family: str) -> Path:
    return derivative_family_root(dataset_root, derivative_family) / "manifest.json"


def record_output_path(dataset_root: Path, derivative_family: str, subject_id: str, site: str,
                       *parts: str) -> Path:
    """Build a standard subject/site derivative artifact path."""
    if not subject_id or subject_id.startswith("sub-"):
        raise ValueError("subject_id must omit the 'sub-' prefix")
    if not site:
        raise ValueError("site must be non-empty")
    return derivative_family_root(dataset_root, derivative_family) / f"sub-{subject_id}" / f"site-{site}" / Path(*parts)
