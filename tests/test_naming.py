from pathlib import Path

from bone_imaging_derivatives.naming import (
    build_naming_rows,
    suggested_filename,
)


def test_naming_rows_flag_missing_identity_and_preserve_side_specific_sites(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "SUBJ001_RL_T1.AIM").touch()
    (data / "SUBJ001_RR_T1.AIM").touch()
    (data / "loose-mask.nii.gz").touch()

    rows = build_naming_rows(data)

    assert [row.site for row in rows if row.subject_id == "SUBJ001"] == ["radius_left", "radius_right"]
    loose = next(row for row in rows if row.path.name == "loose-mask.nii.gz")
    assert loose.problem == "Missing session and site."
    assert loose.confidence == "low"


def test_naming_rows_recognize_calgary_masks_and_multistack_names(tmp_path: Path) -> None:
    data = tmp_path / "data"
    for name in (
        "SAMPLE433_T1.AIM",
        "SAMPLE433_T1_BLCK_MASK.AIM",
        "SAMPLE433_T1_CRTX_MASK.AIM",
        "BMLT_006_KN_STACK2_T0.AIM",
    ):
        (data / name).parent.mkdir(parents=True, exist_ok=True)
        (data / name).touch()

    rows = build_naming_rows(data)

    by_name = {row.path.name: row for row in rows}
    assert by_name["SAMPLE433_T1_BLCK_MASK.AIM"].role == "full"
    assert by_name["SAMPLE433_T1_CRTX_MASK.AIM"].role == "cort"
    assert by_name["BMLT_006_KN_STACK2_T0.AIM"].subject_id == "BMLT_006"
    assert by_name["BMLT_006_KN_STACK2_T0.AIM"].site == "knee"
    assert by_name["BMLT_006_KN_STACK2_T0.AIM"].stack_index == 2


def test_suggested_filename_uses_normalized_identity_and_role(tmp_path: Path) -> None:
    data = tmp_path / "data"
    path = data / "SUBJ001_RL_STACK01_T1_TRAB_MASK.AIM"
    path.parent.mkdir()
    path.touch()

    row = build_naming_rows(data)[0]

    assert suggested_filename(row) == "sub-SUBJ001_site-radius_left_ses-T1_stack-01_mask-trab.AIM"


def test_naming_rows_can_be_enriched_from_optional_metadata_reader(tmp_path: Path) -> None:
    data = tmp_path / "data"
    image = data / "SAMPLE433_T1.AIM"
    image.parent.mkdir()
    image.touch()

    def reader(path: Path):
        assert path.resolve() == image.resolve()
        return {"processing_log": "Index Patient 433\nIndex Measurement 2049\nSite 20\n"}

    row = build_naming_rows(data, metadata_reader=reader)[0]

    assert row.site == "radius_left"
    assert row.site_category == "radius"
    assert row.problem == ""


def test_naming_rows_inherit_missing_mask_site_from_matching_image(tmp_path: Path) -> None:
    data = tmp_path / "data"
    image = data / "SAMPLE433_T1.AIM"
    mask = data / "SAMPLE433_T1_BLCK_MASK.AIM"
    image.parent.mkdir()
    image.touch()
    mask.touch()

    def reader(path: Path):
        if path.name == image.name:
            return {"processing_log": "Site 20\n"}
        return {"processing_log": ""}

    rows = build_naming_rows(data, metadata_reader=reader)
    by_name = {row.path.name: row for row in rows}

    assert by_name[image.name].site == "radius_left"
    assert by_name[mask.name].site == "radius_left"
    assert by_name[mask.name].problem == ""
