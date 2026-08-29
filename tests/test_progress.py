from pathlib import Path

from bone_imaging_derivatives import DerivativeProgressEvent, format_progress_event, parse_progress_event


def test_progress_events_round_trip_and_ignore_unrelated_output(tmp_path: Path) -> None:
    """A progress parser must recover job state without treating arbitrary logs as events."""
    event = DerivativeProgressEvent("CommonRegion", "S01", "tibia", "1", "write", "completed", "Saved mask", tmp_path / "mask.nii.gz")

    line = format_progress_event(event)

    assert parse_progress_event(line) == event
    assert parse_progress_event("ordinary application log") is None
