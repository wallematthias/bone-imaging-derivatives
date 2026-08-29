"""Best-effort readers for pre-manifest derivative layouts."""

from pathlib import Path

from .layout import manifest_path
from .manifest import DerivativeManifest, write_manifest
from .records import DerivativeRecord


def _context(path: Path) -> tuple[str, str, str | None]:
    subject = next((part[4:] for part in path.parts if part.startswith("sub-")), "legacy")
    site = next((part[5:] for part in path.parts if part.startswith("site-")), "unknown")
    session = next((part[4:] for part in path.parts if part.startswith("ses-")), None)
    return subject, site, session


def _space(path: Path) -> str:
    name = str(path).lower()
    return "reference" if "reference" in name or "registered" in name else "native"


def discover_legacy_timelapsed_records(dataset_root: Path) -> list[DerivativeRecord]:
    """Discover recognizable artifacts below the historical TimelapsedHRpQCT tree."""
    root = Path(dataset_root)
    legacy = root / "derivatives" / "TimelapsedHRpQCT"
    if not legacy.exists():
        return []
    role_patterns = {
        "formation": "formation_mask", "resorption": "resorption_mask", "stable": "stable_mask",
        "transform": "transform_to_reference", "common": "scan_region_native_common",
        "region": "scan_region_native_common", "remodelling": "remodelling_pairwise_table",
    }
    records: list[DerivativeRecord] = []
    for path in sorted(item for item in legacy.rglob("*") if item.is_file()):
        name = path.name.lower()
        role = next((value for key, value in role_patterns.items() if key in name), None)
        if role is None:
            continue
        subject, site, session = _context(path)
        records.append(DerivativeRecord("Timelapsed", role, subject, site, session, None,
                                        _space(path), path, "legacy"))
    return records


def discover_legacy_registered_microarchitecture_records(dataset_root: Path) -> list[DerivativeRecord]:
    """Discover registered microarchitecture CSV tables not yet recorded in a manifest."""
    root = Path(dataset_root)
    base = root / "derivatives" / "Microarchitecture"
    if not base.exists():
        return []
    records: list[DerivativeRecord] = []
    for path in sorted(base.rglob("*.csv")):
        if "registered" not in str(path).lower():
            continue
        subject, site, session = _context(path)
        records.append(DerivativeRecord("Microarchitecture", "measurements_table", subject, site,
                                        session, None, "table", path, "legacy", content_type="table"))
    return records


def write_compatibility_manifest(dataset_root: Path) -> Path:
    """Write a manifest that explicitly exposes all currently recognized legacy files."""
    root = Path(dataset_root)
    records = tuple(discover_legacy_timelapsed_records(root) + discover_legacy_registered_microarchitecture_records(root))
    output = manifest_path(root, "Compatibility")
    manifest = DerivativeManifest.create("Compatibility", root, {"name": "bone-imaging-derivatives", "version": "0.1.0"}, records)
    write_manifest(manifest, output)
    return output
