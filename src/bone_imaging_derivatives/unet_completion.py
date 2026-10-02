"""Dependency-free completion checks for transactionally published U-Net cases."""
import json
from pathlib import Path


def _read_object(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _is_unet(data):
    software = data.get("software", {})
    return (data.get("method") == "unet"
            or isinstance(software, dict) and software.get("name") == "hrpqct-segmentation")


def completed_unet_masks(marker):
    """Return full/trab/cort paths only after all members and sidecars commit.

    Accept the earlier standalone runtime's sidecars as well as the bundled
    bone-contouring backend. No image reader or model runtime is needed.
    """
    marker = Path(marker)
    if not marker.name.endswith("_UNET.json"):
        return ()
    prefix = marker.name[:-len("_UNET.json")]
    data = _read_object(marker)
    names = data.get("masks")
    expected = {role: f"{prefix}_desc-{role}_mask.AIM" for role in ("full", "trab", "cort")}
    if names != expected:
        return ()
    paths = tuple(marker.parent / expected[role] for role in expected)
    for role, path in zip(expected, paths):
        try:
            if not path.is_file() or path.stat().st_size == 0:
                return ()
        except OSError:
            return ()
        sidecar = _read_object(path.with_suffix(".AIM.json"))
        if not _is_unet(sidecar) or sidecar.get("short_role") != role:
            return ()
    return paths


def unet_artifact_ready(path, *, unet_hint=False):
    """Leave ordinary contours unchanged, but withhold incomplete U-Net masks."""
    path = Path(path)
    if not any(path.name.endswith(f"_desc-{role}_mask.AIM") for role in ("full", "trab", "cort")):
        return True
    marker = path.with_name(path.name.rsplit("_desc-", 1)[0] + "_UNET.json")
    sidecar = _read_object(path.with_suffix(".AIM.json"))
    if not (unet_hint or marker.exists() or _is_unet(sidecar)):
        return True
    return path in completed_unet_masks(marker)
