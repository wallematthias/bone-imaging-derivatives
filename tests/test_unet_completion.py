import json

from bone_imaging_derivatives.batch_discovery import discover_derivative_artifacts


def make_case(root):
    output = root / 'derivatives/BoneContours/sub-001/ses-1/xct'
    output.mkdir(parents=True)
    prefix = 'sub-001_ses-1_voi-radiusleft'
    masks = {role: f'{prefix}_desc-{role}_mask.AIM' for role in ('full', 'trab', 'cort')}
    for role, name in masks.items():
        (output / name).write_bytes(b'complete mask fixture')
        (output / (name + '.json')).write_text(json.dumps({
            'method': 'unet', 'short_role': role,
            'software': {'name': 'bone-contouring', 'version': '0.3.0'}}))
    marker = output / (prefix + '_UNET.json')
    return masks, marker


def test_unet_masks_are_invisible_until_complete_marker(tmp_path):
    masks, marker = make_case(tmp_path)
    assert discover_derivative_artifacts(tmp_path, 'BoneContours') == ()
    marker.write_text(json.dumps({'masks': masks, 'model': 'radius_tibia_final'}))
    assert len(discover_derivative_artifacts(tmp_path, 'BoneContours')) == 3
    (marker.parent / masks['cort']).unlink()
    assert discover_derivative_artifacts(tmp_path, 'BoneContours') == ()


def test_invalid_unet_marker_never_exposes_masks(tmp_path):
    masks, marker = make_case(tmp_path)
    for payload in ('{', '[]', json.dumps({'masks': dict(masks, cort='../outside.AIM')})):
        marker.write_text(payload)
        assert discover_derivative_artifacts(tmp_path, 'BoneContours') == ()


def test_unet_marker_without_sidecars_is_not_complete(tmp_path):
    masks, marker = make_case(tmp_path)
    marker.write_text(json.dumps({'masks': masks}))
    (marker.parent / (masks['trab'] + '.json')).unlink()
    assert discover_derivative_artifacts(tmp_path, 'BoneContours') == ()
