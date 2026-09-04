from __future__ import annotations

from pathlib import Path

from bone_imaging_derivatives.remote_discovery import remote_discovery_payload


def test_remote_discovery_payload_reports_normalized_images_and_derivatives(tmp_path: Path) -> None:
    image_dir = tmp_path / "sub-001" / "ses-001" / "xct"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "sub-001_ses-001_voi-radiusleft_xct.AIM"
    image_path.write_bytes(b"aim")

    contour_dir = tmp_path / "derivatives" / "BoneContours" / "sub-001" / "ses-001" / "xct"
    contour_dir.mkdir(parents=True)
    contour_path = contour_dir / "sub-001_ses-001_voi-radiusleft_desc-full_mask.AIM"
    contour_path.write_bytes(b"mask")

    payload = remote_discovery_payload(tmp_path, families=("BoneContours",))

    assert payload["normalized"]["ok"] is True
    assert payload["normalized"]["image_count"] == 1
    assert len(payload["raw_images"]) == 1
    assert len(payload["derivatives"]) == 1
    assert payload["derivatives"][0]["family"] == "BoneContours"
