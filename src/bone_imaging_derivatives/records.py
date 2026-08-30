"""Immutable records describing one derivative artifact."""

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from .families import validate_derivative_family
from .roles import validate_role

_SPACES = frozenset({"native", "reference", "moving", "fixed", "model", "table"})
_SOURCES = frozenset({"generated", "provided", "derived", "legacy", "virtual"})


@dataclass(frozen=True)
class DerivativeRecord:
    derivative: str
    role: str
    subject_id: str
    site: str
    session_id: str | None
    stack_index: int | None
    space: str
    path: Path
    source: str
    inputs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    record_id: str | None = None
    content_type: str | None = None
    coordinate_reference: Mapping[str, Any] | None = None
    settings_hash: str | None = None
    software: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        validate_derivative_family(self.derivative)
        validate_role(self.role)
        if not self.subject_id or self.subject_id.startswith("sub-"):
            raise ValueError("subject_id must be non-empty and omit the 'sub-' prefix")
        if not self.site or "/" in self.site:
            raise ValueError("site must be a non-empty normalized identifier")
        if self.session_id is not None and not self.session_id:
            raise ValueError("session_id must be non-empty when provided")
        if self.stack_index is not None and not isinstance(self.stack_index, int):
            raise ValueError("stack_index must be an integer or None")
        if self.space not in _SPACES:
            raise ValueError(f"Unknown coordinate space: {self.space!r}")
        if self.source not in _SOURCES:
            raise ValueError(f"Unknown record source: {self.source!r}")
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.source == "virtual" and self.role == "source_image_view":
            self._validate_virtual_source_image_view()
        if self.coordinate_reference is not None:
            object.__setattr__(self, "coordinate_reference", dict(self.coordinate_reference))
        if self.software is not None:
            object.__setattr__(self, "software", dict(self.software))
        if self.record_id is None:
            object.__setattr__(self, "record_id", self._default_record_id())

    def _default_record_id(self) -> str:
        parts = (self.derivative, self.role, self.subject_id, self.site,
                 self.session_id or "", str(self.stack_index), self.space, str(self.path))
        return sha256("\x1f".join(parts).encode()).hexdigest()[:20]

    def _validate_virtual_source_image_view(self) -> None:
        required = ("format", "view_type", "slice_axis", "slice_start", "slice_stop")
        missing = [key for key in required if key not in self.metadata]
        if missing:
            keys = ", ".join(missing)
            raise ValueError(f"virtual source_image_view records require metadata: {keys}")
        if self.content_type not in (None, "image"):
            raise ValueError("virtual source_image_view records must have content_type='image'")
        if self.metadata.get("view_type") != "stack_slices":
            raise ValueError("virtual source_image_view records currently require view_type='stack_slices'")
        if self.metadata.get("slice_axis") != "z":
            raise ValueError("virtual source_image_view records currently require slice_axis='z'")
        start = self.metadata["slice_start"]
        stop = self.metadata["slice_stop"]
        if not isinstance(start, int) or not isinstance(stop, int) or stop <= start:
            raise ValueError("virtual source_image_view records require integer slice_start < slice_stop")
