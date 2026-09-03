from __future__ import annotations

from pathlib import Path


def test_profile_registry_saves_json_profiles_under_shared_tool_root(tmp_path: Path) -> None:
    """User profiles should live in one shared toolbox registry, grouped by tool."""
    from bone_imaging_derivatives import load_profile_payload, list_profiles, save_json_profile

    record = save_json_profile(
        "bone-contouring",
        "My Radius Recipe",
        {"schema": "bone-contour-recipe-v1", "value": 42},
        root=tmp_path,
    )

    assert record.tool == "bone-contouring"
    assert record.name == "My Radius Recipe"
    assert record.kind == "json"
    assert record.source == "user"
    assert record.path == tmp_path / "bone-contouring" / "my-radius-recipe.json"
    assert load_profile_payload(record) == {"schema": "bone-contour-recipe-v1", "value": 42}
    assert list_profiles("bone-contouring", root=tmp_path) == (record,)


def test_profile_registry_can_index_rich_external_profile_assets(tmp_path: Path) -> None:
    """ParOSol and motion-model profiles should be registry records, not forced into JSON payloads."""
    from bone_imaging_derivatives import list_profiles, register_profile_asset

    workflow = tmp_path / "workflows" / "distal-radius.parosol-workflow"
    workflow.parent.mkdir()
    workflow.write_text("workflow_template:\n  profile: distal-radius\n", encoding="utf-8")

    record = register_profile_asset(
        "parosol-fea",
        "Distal Radius",
        workflow,
        kind="parosol-workflow",
        root=tmp_path / "registry",
        metadata={"profile_group": "XCT"},
    )

    assert record.path == workflow
    assert record.metadata == {"profile_group": "XCT"}
    assert list_profiles("parosol-fea", root=tmp_path / "registry") == (record,)


def test_profile_registry_deletes_records_and_hides_missing_files(tmp_path: Path) -> None:
    """Deleted custom profiles should disappear from every toolbox profile dropdown."""
    from bone_imaging_derivatives import delete_profile, list_profiles, save_json_profile

    record = save_json_profile(
        "bone-contouring",
        "Temporary Profile",
        {"schema": "bone-contour-recipe-v1"},
        root=tmp_path,
    )
    assert list_profiles("bone-contouring", root=tmp_path) == (record,)

    record.path.unlink()
    assert list_profiles("bone-contouring", root=tmp_path) == ()

    save_json_profile(
        "bone-contouring",
        "Temporary Profile",
        {"schema": "bone-contour-recipe-v1"},
        root=tmp_path,
    )
    delete_profile("bone-contouring", "Temporary Profile", "json", root=tmp_path)
    assert list_profiles("bone-contouring", root=tmp_path) == ()
