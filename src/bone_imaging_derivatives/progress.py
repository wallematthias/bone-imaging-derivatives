"""Line-oriented JSON progress protocol for background processes."""

from dataclasses import dataclass
import json
from pathlib import Path

_PREFIX = "BONE_DERIVATIVES_PROGRESS "


@dataclass(frozen=True)
class DerivativeProgressEvent:
    family: str
    subject_id: str | None
    site: str | None
    session_id: str | None
    step: str
    status: str
    message: str
    path: Path | None = None

    def __post_init__(self) -> None:
        if not self.family or not self.step or not self.status:
            raise ValueError("family, step, and status must be non-empty")
        if self.path is not None:
            object.__setattr__(self, "path", Path(self.path))


def format_progress_event(event: DerivativeProgressEvent) -> str:
    """Format one parseable progress line without printing it."""
    data = {"family": event.family, "subject_id": event.subject_id, "site": event.site,
            "session_id": event.session_id, "step": event.step, "status": event.status,
            "message": event.message, "path": str(event.path) if event.path is not None else None}
    return _PREFIX + json.dumps(data, sort_keys=True)


def parse_progress_event(line: str) -> DerivativeProgressEvent | None:
    """Parse a progress line, returning ``None`` for normal process output."""
    if not line.startswith(_PREFIX):
        return None
    try:
        data = json.loads(line[len(_PREFIX):])
        return DerivativeProgressEvent(data["family"], data.get("subject_id"), data.get("site"),
                                       data.get("session_id"), data["step"], data["status"],
                                       data.get("message", ""), Path(data["path"]) if data.get("path") else None)
    except (TypeError, KeyError, ValueError, json.JSONDecodeError):
        return None
