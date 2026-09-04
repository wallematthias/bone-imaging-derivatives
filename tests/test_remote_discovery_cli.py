from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remote_discovery_cli_reports_normalized_dataset_json(tmp_path: Path) -> None:
    xct_dir = tmp_path / "sub-001" / "ses-001" / "xct"
    xct_dir.mkdir(parents=True)
    image = xct_dir / "sub-001_ses-001_voi-radiusleft_xct.AIM"
    image.write_bytes(b"aim")
    contour_dir = tmp_path / "derivatives" / "ImportedContours" / "sub-001" / "ses-001" / "xct"
    contour_dir.mkdir(parents=True)
    full = contour_dir / "sub-001_ses-001_voi-radiusleft_desc-full_mask.AIM"
    full.write_bytes(b"mask")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bone_imaging_derivatives.remote_discovery",
            str(tmp_path),
            "--family",
            "ImportedContours",
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["dataset_root"] == str(tmp_path.resolve())
    assert payload["normalized"]["ok"] is True
    assert payload["normalized"]["image_count"] == 1
    assert payload["raw_images"][0]["path"] == str(image.resolve())
    assert payload["raw_images"][0]["key"] == {
        "subject_id": "001",
        "session_id": "001",
        "voi": "radiusleft",
        "stack_index": None,
    }
    assert payload["derivatives"][0]["family"] == "ImportedContours"
    assert payload["derivatives"][0]["role"] == "full"
    assert payload["derivatives"][0]["path"] == str(full.resolve())
