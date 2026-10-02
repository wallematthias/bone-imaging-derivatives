# bone-imaging-derivatives

Small, standard-library-only models and helpers for interoperable bone-imaging derivative manifests.

Version 0.1.6 adds atomic manifest replacement and completion-gated U-Net
BoneContours discovery. U-Net full/trab/cort artifacts become discoverable only
after their complete masks, identifying sidecars and `_UNET.json` marker exist.
The public `completed_unet_masks(marker)` helper returns the three committed
paths, or an empty tuple for incomplete/invalid cases. Standard and imported
contour discovery is unchanged. This contract package remains MIT licensed.

Dataset naming uses the AIM patient header for native Scanco measurement names
such as `D0000308`, while explicit normalized/anonymized subject IDs remain
authoritative. Undo restores images and original sidecars after a complete
collision preflight, then archives the completed manifest as
`dataset_rename_manifest.undone-<unique-id>.json`. This permits another rename while
preserving the audit trail. Identity-bearing manifests should remain private.
