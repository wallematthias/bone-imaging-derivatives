# bone-imaging-derivatives

Small, standard-library-only models and helpers for interoperable bone-imaging derivative manifests.

Version 0.1.6 adds atomic manifest replacement and completion-gated U-Net
BoneContours discovery. U-Net full/trab/cort artifacts become discoverable only
after their complete masks, identifying sidecars and `_UNET.json` marker exist.
The public `completed_unet_masks(marker)` helper returns the three committed
paths, or an empty tuple for incomplete/invalid cases. Standard and imported
contour discovery is unchanged. This contract package remains MIT licensed.
