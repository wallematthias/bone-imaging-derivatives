from pathlib import Path

from bone_imaging_derivatives.naming import (
    apply_naming_row_overrides,
    build_naming_rows,
    split_identity_metadata,
    suggested_filename,
    suggested_mids_relative_paths,
)


def test_naming_rows_flag_missing_identity_and_preserve_side_specific_sites(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "SUBJ001_RL_T1.AIM").touch()
    (data / "SUBJ001_RR_T1.AIM").touch()
    (data / "loose-mask.nii.gz").touch()

    rows = build_naming_rows(data)

    assert [row.site for row in rows if row.subject_id == "SUBJ001"] == ["radiusleft", "radiusright"]
    loose = next(row for row in rows if row.path.name == "loose-mask.nii.gz")
    assert loose.problem == "Missing session and site."
    assert loose.confidence == "low"


def test_apply_naming_row_overrides_recomputes_problem_and_site_category(tmp_path: Path) -> None:
    data = tmp_path / "data"
    path = data / "loose-mask.nii.gz"
    path.parent.mkdir()
    path.touch()
    row = build_naming_rows(data)[0]

    corrected = apply_naming_row_overrides(
        row,
        {
            "subject_id": "SUBJ001",
            "session_id": "Y04",
            "site": "RL",
            "role": "trab_mask",
            "stack_index": "2",
        },
    )

    assert corrected.subject_id == "SUBJ001"
    assert corrected.session_id == "04"
    assert corrected.site == "radiusleft"
    assert corrected.site_category == "radius"
    assert corrected.role == "trab"
    assert corrected.stack_index == 2
    assert corrected.confidence == "user"
    assert corrected.problem == ""


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

    assert suggested_filename(row) == "sub-SUBJ001_ses-T1_voi-radiusleft_stack-01_mask-trab.AIM"


def test_suggested_mids_paths_use_pseudonyms_voi_and_ipl_derivatives(tmp_path: Path) -> None:
    data = tmp_path / "data"
    for name in (
        "STRAMBO_0001_RL_Y00.AIM",
        "STRAMBO_0001_RL_Y00_TRAB_MASK.AIM",
    ):
        (data / name).parent.mkdir(parents=True, exist_ok=True)
        (data / name).touch()

    rows = build_naming_rows(data)
    suggestions = suggested_mids_relative_paths(rows)

    by_name = {row.path.name: suggestions[row.path] for row in rows}
    assert by_name["STRAMBO_0001_RL_Y00.AIM"] == Path(
        "sub-001/ses-001/xct/sub-001_ses-001_voi-radiusleft_xct.AIM"
    )
    assert by_name["STRAMBO_0001_RL_Y00_TRAB_MASK.AIM"] == Path(
        "derivatives/IPLContours/sub-001/ses-001/xct/sub-001_ses-001_voi-radiusleft_desc-trab_mask.AIM"
    )


def test_naming_rows_can_be_enriched_from_optional_metadata_reader(tmp_path: Path) -> None:
    data = tmp_path / "data"
    image = data / "SAMPLE433_T1.AIM"
    image.parent.mkdir()
    image.touch()

    def reader(path: Path):
        assert path.resolve() == image.resolve()
        return {"processing_log": "Index Patient 433\nIndex Measurement 2049\nSite 20\n"}

    row = build_naming_rows(data, metadata_reader=reader)[0]

    assert row.site == "radiusleft"
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

    assert by_name[image.name].site == "radiusleft"
    assert by_name[mask.name].site == "radiusleft"
    assert by_name[mask.name].problem == ""


def test_split_identity_metadata_keeps_shareable_fields_separate_from_private_header() -> None:
    public, private = split_identity_metadata(
        {
            "subject_id": "STRAMBO_0001",
            "session_id": "Y00",
            "site": "radiusleft",
            "role": "image",
            "processing_log": "Patient Name Jane Example\nIndex Patient 123\nSite 20\nMu_Scaling 8192\n",
            "scanner_model": "XtremeCT",
        }
    )

    assert public == {
        "subject_id": "STRAMBO_0001",
        "session_id": "Y00",
        "site": "radiusleft",
        "role": "image",
        "scanner_model": "XtremeCT",
    }
    assert "processing_log" not in public
    assert private["processing_log_identifiable_lines"] == [
        "Patient Name Jane Example",
        "Index Patient 123",
    ]
    assert "processing_log" in private
