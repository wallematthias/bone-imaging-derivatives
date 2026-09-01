"""Lightweight artifact discovery for loose files, sidecars, and derivatives.

This module deliberately avoids image-reading dependencies. It only inspects
paths and optional sidecar metadata so batch and Slicer scene tools can build a
consistent table before expensive image IO starts.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

_IMAGE_EXTENSIONS = (".aim", ".isq", ".scv", ".mha", ".mhd", ".nii", ".nii.gz", ".nrrd", ".nhdr")
_AIM_VERSION_RE = re.compile(r"\.aim(?:;\d+)?$", re.IGNORECASE)
_SESSION_PREFIX_RE = re.compile(r"^(?:ses[-_]?|session[-_]?|tp[-_]?)(.+)$", re.IGNORECASE)
_SUBJECT_TOKEN_RE = re.compile(r"(?:^|[_-])sub[-_]([A-Za-z0-9.]+)(?=[_-]|$)", re.IGNORECASE)
_SESSION_TOKEN_RE = re.compile(r"(?:^|[_-])ses[-_]?([A-Za-z0-9.]+)(?=[_-]|$)", re.IGNORECASE)
_SITE_TOKEN_RE = re.compile(r"(?:^|[_-])site[-_]?([A-Za-z0-9.]+)(?=[_-]|$)", re.IGNORECASE)
_MASK_ROLE_RE = re.compile(r"(?:^|[_-])(?:mask|roi|seg)[-_]?([A-Za-z0-9][A-Za-z0-9._-]*)(?=[_.-]|$)", re.IGNORECASE)
_TRANSFORM_RE = re.compile(
    r"from[-_]?ses[-_]?([A-Za-z0-9][A-Za-z0-9._-]*)[_-]to[-_]?ses[-_]?([A-Za-z0-9][A-Za-z0-9._-]*)",
    re.IGNORECASE,
)
_STACK_RE = re.compile(r"(?:^|[_-])STACK[_-]?0*([1-9]\d*)(?=[_-]|$)", re.IGNORECASE)

_SITE_ALIASES = {
    "20": "radius_left",
    "21": "radius_right",
    "38": "tibia_left",
    "29": "tibia_right",
    "rl": "radius_left",
    "radius_l": "radius_left",
    "radiusleft": "radius_left",
    "left_radius": "radius_left",
    "rr": "radius_right",
    "radius_r": "radius_right",
    "radiusright": "radius_right",
    "right_radius": "radius_right",
    "tl": "tibia_left",
    "tibia_l": "tibia_left",
    "tibialeft": "tibia_left",
    "left_tibia": "tibia_left",
    "tr": "tibia_right",
    "tibia_r": "tibia_right",
    "tibiaright": "tibia_right",
    "right_tibia": "tibia_right",
    "kl": "knee_left",
    "kr": "knee_right",
    "kn": "knee",
    "dr": "radius",
    "dt": "tibia",
    "radius": "radius",
    "tibia": "tibia",
    "knee": "knee",
    "patella": "knee",
}

_ROLE_ALIASES = {
    "image": "image",
    "img": "image",
    "seg": "segmentation",
    "bone": "segmentation",
    "bone_seg": "segmentation",
    "segmentation": "segmentation",
    "full": "full",
    "blck": "full",
    "block": "full",
    "blck_mask": "full",
    "block_mask": "full",
    "peri": "full",
    "periosteal": "full",
    "trab": "trab",
    "trabecular": "trab",
    "cort": "cort",
    "crtx": "cort",
    "crtx_mask": "cort",
    "cortical": "cort",
    "endo": "endo",
    "endosteal": "endo",
    "reg": "registration",
    "regmask": "registration",
    "registration": "registration",
}

_ROLE_SUFFIX_PATTERNS = (
    (re.compile(r"(?i)[_-]REGMASK$"), "registration"),
    (re.compile(r"(?i)[_-]REG[_-]MASK$"), "registration"),
    (re.compile(r"(?i)[_-]BLCK[_-]MASK$"), "full"),
    (re.compile(r"(?i)[_-]BLOCK[_-]MASK$"), "full"),
    (re.compile(r"(?i)[_-]CRTX[_-]MASK$"), "cort"),
    (re.compile(r"(?i)[_-]CORTX?[_-]MASK$"), "cort"),
    (re.compile(r"(?i)[_-]TRAB[_-]MASK$"), "trab"),
    (re.compile(r"(?i)[_-]CORT[_-]MASK$"), "cort"),
    (re.compile(r"(?i)[_-]FULL[_-]MASK$"), "full"),
    (re.compile(r"(?i)[_-]MASK[_-]TRAB$"), "trab"),
    (re.compile(r"(?i)[_-]MASK[_-]CORT$"), "cort"),
    (re.compile(r"(?i)[_-]MASK[_-]FULL$"), "full"),
    (re.compile(r"(?i)[_-]MASK[_-]SEG$"), "segmentation"),
    (re.compile(r"(?i)[_-]SEG$"), "segmentation"),
)
_ROI_SUFFIX_RE = re.compile(r"(?i)(?:^|[_-])ROI[_-]?([0-9A-Z][0-9A-Z_]*)$")
_MASK_NUMBER_SUFFIX_RE = re.compile(r"(?i)(?:^|[_-])MASK[_-]?([0-9]+)$")


@dataclass(frozen=True)
class ArtifactRecord:
    """One discovered input or derivative artifact with provenance."""

    path: Path
    kind: str
    role: str
    subject_id: str | None = None
    session_id: str | None = None
    stack_index: int | None = None
    site: str | None = None
    format: str | None = None
    subject_source: str | None = None
    session_source: str | None = None
    site_source: str | None = None
    role_source: str | None = None
    identity_confidence: str = "low"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ArtifactIndex:
    """Searchable collection of discovered artifacts."""

    records: tuple[ArtifactRecord, ...]
    dataset_root: Path

    def find(
        self,
        *,
        kind: str | None = None,
        role: str | None = None,
        subject_id: str | None = None,
        site: str | None = None,
        session_id: str | None = None,
    ) -> list[ArtifactRecord]:
        expected = {
            "kind": kind,
            "role": normalize_role(role) if role is not None else None,
            "subject_id": normalize_subject_id(subject_id) if subject_id is not None else None,
            "site": normalize_site(site) if site is not None else None,
            "session_id": normalize_session_id(session_id) if session_id is not None else None,
        }
        return [
            record
            for record in self.records
            if all(value is None or getattr(record, key) == value for key, value in expected.items())
        ]

    def missing_roles(
        self,
        *,
        subject_id: str,
        site: str,
        session_id: str,
        required_roles: Sequence[str],
    ) -> tuple[str, ...]:
        present = {
            record.role
            for record in self.find(
                kind="mask",
                subject_id=subject_id,
                site=site,
                session_id=session_id,
            )
        }
        return tuple(role for role in map(normalize_role, required_roles) if role not in present)


def normalize_subject_id(value: str | None) -> str | None:
    """Return a subject identifier without a leading ``sub-`` prefix."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower().startswith("sub-"):
        return text[4:]
    if text.lower().startswith("sub_"):
        return text[4:]
    return text or None


def normalize_session_id(value: str | None) -> str | None:
    """Normalize session aliases while keeping non-numeric labels meaningful."""
    if value is None:
        return None
    text = str(value).strip()
    match = _SESSION_PREFIX_RE.match(text)
    if match:
        text = match.group(1)
    if re.fullmatch(r"Y\d+", text, re.IGNORECASE):
        text = text[1:]
    if text.isdigit():
        return text
    return text or None


def normalize_site(value: str | None) -> str | None:
    """Normalize site labels without collapsing left and right."""
    if value is None:
        return None
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip()).strip("_").lower()
    return _SITE_ALIASES.get(text, text or None)


def site_category(value: str | None) -> str | None:
    """Return the anatomical site family used for presets."""
    site = normalize_site(value)
    if site is None:
        return None
    for family in ("radius", "tibia", "knee"):
        if site == family or site.startswith(f"{family}_"):
            return family
    return site


def normalize_role(value: str | None) -> str | None:
    """Normalize common segmentation and ROI labels."""
    if value is None:
        return None
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip()).strip("_").lower()
    return _ROLE_ALIASES.get(text, text or None)


def apply_overrides(record: ArtifactRecord, overrides: Mapping[str, str | None]) -> ArtifactRecord:
    """Return ``record`` with user-corrected identity fields and provenance."""
    updates: dict[str, Any] = {}
    metadata = dict(record.metadata)
    for public_key, attr, source_attr, normalizer in (
        ("subject_id", "subject_id", "subject_source", normalize_subject_id),
        ("session_id", "session_id", "session_source", normalize_session_id),
        ("site", "site", "site_source", normalize_site),
        ("role", "role", "role_source", normalize_role),
    ):
        if public_key not in overrides:
            continue
        old_value = getattr(record, attr)
        new_value = normalizer(overrides[public_key])
        if old_value != new_value:
            metadata[f"previous_{attr}"] = old_value
        updates[attr] = new_value
        updates[source_attr] = "user_override"
    if updates:
        updates["metadata"] = metadata
        updates["identity_confidence"] = "user"
    return replace(record, **updates)


def discover_artifacts(dataset_root: str | Path, *, include_derivatives: bool = True) -> ArtifactIndex:
    """Discover lightweight artifact records below a dataset root."""
    root = _normalize_dataset_root(Path(dataset_root))
    search_roots = [root]
    if include_derivatives and (root / "derivatives").exists():
        search_roots.append(root / "derivatives")
    seen: set[Path] = set()
    records: list[ArtifactRecord] = []
    for search_root in search_roots:
        for path in sorted(_iter_candidate_files(search_root)):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            record = _record_from_path(root, path)
            if record is not None:
                records.append(record)
    return ArtifactIndex(tuple(records), root)


def _normalize_dataset_root(root: Path) -> Path:
    root = root.resolve()
    if root.name == "derivatives":
        return root.parent
    return root


def _iter_candidate_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir() or _is_sidecar(path):
            continue
        if _file_format(path) is not None or path.suffix.lower() in {".tfm", ".h5", ".csv"}:
            candidates.append(path)
    return candidates


def _record_from_path(dataset_root: Path, path: Path) -> ArtifactRecord | None:
    fmt = _file_format(path)
    sidecar = _read_sidecar(path)
    kind = _kind_from_path(path, fmt)
    explicit_role = _explicit_sidecar_role(sidecar)
    if kind == "image" and explicit_role and normalize_role(explicit_role) not in {"image", "transform", "table"}:
        kind = "mask"
    if kind is None:
        return None
    role, role_source = _role_from_path(path, kind, sidecar)
    subject_id, subject_source = _subject_from_path(dataset_root, path, sidecar)
    session_id, session_source = _session_from_path(dataset_root, path, sidecar)
    stack_index = _stack_from_path(path, sidecar)
    site, site_source = _site_from_path(dataset_root, path, sidecar)
    confidence = _confidence(subject_id, session_id, site, subject_source, session_source, site_source)
    metadata = {"sidecar": sidecar} if sidecar else {}
    if kind == "transform":
        pair = _TRANSFORM_RE.search(path.name)
        if pair:
            metadata["from_session_id"] = normalize_session_id(pair.group(1))
            metadata["to_session_id"] = normalize_session_id(pair.group(2))
    return ArtifactRecord(
        path=path,
        kind=kind,
        role=role,
        subject_id=subject_id,
        session_id=session_id,
        stack_index=stack_index,
        site=site,
        format=fmt,
        subject_source=subject_source,
        session_source=session_source,
        site_source=site_source,
        role_source=role_source,
        identity_confidence=confidence,
        metadata=metadata,
    )


def _file_format(path: Path) -> str | None:
    name = path.name.lower()
    if _AIM_VERSION_RE.search(name):
        return "aim"
    if name.endswith(".nii.gz") or path.suffix.lower() == ".nii":
        return "nifti"
    if path.suffix.lower() in {".mha", ".mhd"}:
        return "metaimage"
    if path.suffix.lower() in {".nrrd", ".nhdr"}:
        return "nrrd"
    if path.suffix.lower() == ".isq":
        return "isq"
    if path.suffix.lower() == ".scv":
        return "scv"
    return None


def _is_sidecar(path: Path) -> bool:
    return path.suffix.lower() == ".json" and _file_format(_path_without_json_suffix(path)) is not None


def _path_without_json_suffix(path: Path) -> Path:
    return path.with_name(path.name[:-5])


def _read_sidecar(path: Path) -> dict[str, Any]:
    candidates = [path.with_name(f"{path.name}.json")]
    if path.name.lower().endswith(".nii.gz"):
        candidates.append(path.with_name(f"{path.name[:-7]}.json"))
    else:
        candidates.append(path.with_suffix(".json"))
    for candidate in candidates:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text())
            except (OSError, json.JSONDecodeError):
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def _kind_from_path(path: Path, fmt: str | None) -> str | None:
    lower_parts = {part.lower() for part in path.parts}
    lower_name = path.name.lower()
    if path.suffix.lower() in {".tfm", ".h5"}:
        return "transform"
    if path.suffix.lower() == ".csv":
        return "table"
    if fmt is None:
        return None
    if (
        "masks" in lower_parts
        or "_mask-" in lower_name
        or "_mask" in lower_name
        or "_seg" in lower_name
        or any(pattern.search(_strip_known_image_suffix(path.name)) for pattern, _role in _ROLE_SUFFIX_PATTERNS)
        or _ROI_SUFFIX_RE.search(_strip_known_image_suffix(path.name))
        or _MASK_NUMBER_SUFFIX_RE.search(_strip_known_image_suffix(path.name))
    ):
        return "mask"
    return "image"


def _role_from_path(path: Path, kind: str, sidecar: Mapping[str, Any]) -> tuple[str, str]:
    explicit_role = _explicit_sidecar_role(sidecar)
    if explicit_role:
        return normalize_role(explicit_role) or explicit_role, "sidecar"
    lower_name = path.name.lower()
    if kind == "image":
        if "_map-" in lower_name or "maps" in {part.lower() for part in path.parts}:
            return "map", "filename"
        return "image", "kind"
    if kind == "transform":
        return "transform", "filename"
    if kind == "table":
        return "table", "filename"
    stem = _strip_known_image_suffix(path.name).lower()
    for pattern, role in _ROLE_SUFFIX_PATTERNS:
        if pattern.search(stem):
            return role, "filename"
    roi_match = _ROI_SUFFIX_RE.search(stem)
    if roi_match:
        suffix = str(roi_match.group(1)).lower()
        return f"roi{suffix}" if suffix[0].isdigit() else f"roi_{suffix}", "filename"
    mask_number_match = _MASK_NUMBER_SUFFIX_RE.search(stem)
    if mask_number_match:
        return f"mask{mask_number_match.group(1).lower()}", "filename"
    if "_mask-" in stem:
        return normalize_role(stem.rsplit("_mask-", 1)[1]) or stem.rsplit("_mask-", 1)[1], "filename"
    if "_mask_" in stem:
        return normalize_role(stem.rsplit("_mask_", 1)[1]) or stem.rsplit("_mask_", 1)[1], "filename"
    match = _MASK_ROLE_RE.search(lower_name)
    if match:
        return normalize_role(match.group(1)) or match.group(1), "filename"
    if "_seg" in lower_name:
        return "segmentation", "filename"
    return "mask", "unknown"


def _explicit_sidecar_role(sidecar: Mapping[str, Any]) -> str | None:
    for key in ("role", "mask_role", "artifact_role"):
        value = sidecar.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _subject_from_path(dataset_root: Path, path: Path, sidecar: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for key in ("subject_id", "subject", "patient_id", "patient_index"):
        if sidecar.get(key) is not None:
            return normalize_subject_id(str(sidecar[key])), "sidecar"
    for part in path.relative_to(dataset_root).parts[:-1]:
        if part.lower().startswith(("sub-", "sub_")):
            return normalize_subject_id(part), "path"
    for part in (*path.relative_to(dataset_root).parts[:-1], path.stem):
        match = _SUBJECT_TOKEN_RE.search(part)
        if match:
            return normalize_subject_id(match.group(1)), "path"
    tokens = _tokens(path.name)
    if len(tokens) >= 2 and tokens[0].lower().startswith("strambo"):
        return f"{tokens[0]}_{tokens[1]}", "filename"
    if len(tokens) >= 2 and tokens[0].lower() == "bmlt":
        return f"{tokens[0]}_{tokens[1]}", "filename"
    subject_tokens: list[str] = []
    for token in tokens:
        if _is_site_token(token) or _is_stack_token(token) or _is_session_token(token) or _is_role_token(token):
            break
        subject_tokens.append(token)
    if subject_tokens:
        return normalize_subject_id("_".join(subject_tokens)), "filename"
    return None, None


def _session_from_path(dataset_root: Path, path: Path, sidecar: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for key in ("session_id", "session", "timepoint", "index_measurement"):
        if sidecar.get(key) is not None:
            return normalize_session_id(str(sidecar[key])), "sidecar"
    for part in (*path.relative_to(dataset_root).parts[:-1], path.stem):
        match = _SESSION_TOKEN_RE.search(part)
        if match:
            return normalize_session_id(match.group(1)), "path"
    for token in _tokens(path.name):
        if re.fullmatch(r"Y\d+", token, re.IGNORECASE):
            return normalize_session_id(token), "filename"
        if re.fullmatch(r"T\d+", token, re.IGNORECASE):
            return normalize_session_id(token), "filename"
    return None, None


def _stack_from_path(path: Path, sidecar: Mapping[str, Any]) -> int | None:
    for key in ("stack_index", "stack", "source_stack_index"):
        if sidecar.get(key) is None:
            continue
        try:
            return int(sidecar[key])
        except (TypeError, ValueError):
            return None
    match = _STACK_RE.search(_strip_known_image_suffix(path.name))
    if match:
        return int(match.group(1))
    return None


def _site_from_path(dataset_root: Path, path: Path, sidecar: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for key in ("site", "site_id", "scan_site"):
        if sidecar.get(key) is not None:
            return normalize_site(str(sidecar[key])), "sidecar"
    filename_site: str | None = None
    for token in _tokens(path.name):
        site = normalize_site(token)
        if site in {"radius_left", "radius_right", "tibia_left", "tibia_right", "knee_left", "knee_right", "radius", "tibia", "knee"}:
            filename_site = site
            break
    for part in path.relative_to(dataset_root).parts[:-1]:
        match = _SITE_TOKEN_RE.search(part)
        if match:
            path_site = normalize_site(match.group(1))
            if filename_site and _sites_are_compatible(filename_site, path_site):
                return filename_site, "filename"
            return path_site, "path"
    if filename_site:
        return filename_site, "filename"
    return None, None


def _sites_are_compatible(specific: str | None, generic: str | None) -> bool:
    if not specific or not generic:
        return False
    return specific == generic or specific.startswith(f"{generic}_")


def _tokens(name: str) -> list[str]:
    clean = _strip_known_image_suffix(name)
    return [token for token in re.split(r"[_\-.]+", clean) if token]


def _is_site_token(token: str) -> bool:
    site = normalize_site(token)
    return site in {
        "radius_left",
        "radius_right",
        "tibia_left",
        "tibia_right",
        "knee_left",
        "knee_right",
        "radius",
        "tibia",
        "knee",
    }


def _is_stack_token(token: str) -> bool:
    return re.fullmatch(r"(?i)STACK\d*", token) is not None


def _is_session_token(token: str) -> bool:
    return re.fullmatch(r"(?i)[TY]\d+", token) is not None


def _is_role_token(token: str) -> bool:
    return normalize_role(token) in {"segmentation", "full", "trab", "cort", "endo", "registration"} or re.fullmatch(
        r"(?i)(ROI\d+|MASK\d+|MASK|SEG|EVENTS)", token
    ) is not None


def _strip_known_image_suffix(name: str) -> str:
    clean = _AIM_VERSION_RE.sub("", name)
    for suffix in (".nii.gz",):
        if clean.lower().endswith(suffix):
            clean = clean[: -len(suffix)]
    return Path(clean).stem


def _confidence(
    subject_id: str | None,
    session_id: str | None,
    site: str | None,
    subject_source: str | None,
    session_source: str | None,
    site_source: str | None,
) -> str:
    if subject_id and session_id and site:
        if "sidecar" in {subject_source, session_source, site_source}:
            return "high"
        if {subject_source, session_source, site_source} <= {"filename", "path"}:
            return "high"
    if subject_id and (session_id or site):
        return "medium"
    return "low"
