"""Stable semantic roles used by derivative records."""

DERIVATIVE_ROLES = frozenset({
    "transform_pairwise", "transform_to_reference", "transform_from_reference",
    "registration_mask", "registration_qc", "scan_region_native",
    "scan_region_reference", "scan_region_common_reference",
    "scan_region_native_common", "bone_segmentation", "periosteal_mask",
    "endosteal_mask", "trabecular_mask", "cortical_mask", "scan_region_mask",
    "void_mask", "measurements_table", "trabecular_thickness_map",
    "trabecular_spacing_map", "trabecular_number_map", "cortical_thickness_map",
    "cortical_porosity_map", "plate_rod_label_map", "plate_rod_measurements_table",
    "plate_local_thickness_map", "rod_local_thickness_map", "skeleton_map",
    "remodelling_pairwise_table", "remodelling_trajectory_table", "formation_mask",
    "resorption_mask", "stable_mask", "source_image_view", "transformed_image", "filled_image",
    "qc_report", "mesh", "material_map", "material_labelmap", "boundary_conditions", "solver_input",
    "solver_output", "strain_map", "stress_map", "load_transfer_table",
    "mechanoregulation_table", "mechanical_signal_map", "formation_mechanics_map",
    "resorption_mechanics_map", "adaptation_classification_map",
    "solver_config", "material_image", "sed_map", "displacement_map", "summary_table",
    "diagnostic_log", "stimulus_map", "formation_map", "resorption_map", "quiescence_map",
    "classification_map",
    "void_measurements_table", "void_distance_map", "void_connectivity_map",
})


def validate_role(value: str) -> str:
    """Return a recognized record role or raise a useful error."""
    if value not in DERIVATIVE_ROLES:
        raise ValueError(f"Unknown derivative role: {value!r}")
    return value
