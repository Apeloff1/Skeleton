"""Editor-facing platform picker data for *candidate* homebrew source/targets.

The stable JSON-compatible payload distinguishes design reachability from
independently certified native exporters. This is an API model, not a GUI.
"""
from __future__ import annotations

from .platform_registry import PlatformProfile, PlatformRegistry, PlatformRegistryError, default_registry
from .port_planner import PortMode

# These adapters generate genuine SDL2/C11 source only, NOT verified executable builds.
_NATIVE_SOURCE_TARGETS = frozenset({"windows_modern", "linux_desktop", "macos_modern"})


def _option(profile: PlatformProfile, *, as_source: bool) -> dict[str, object]:
    source_ready = profile.id in _NATIVE_SOURCE_TARGETS
    return {
        "id": profile.id,
        "label": profile.name,
        "kind": profile.kind,
        "family": profile.family,
        "lifecycle": profile.lifecycle,
        "first_year_candidate": profile.first_year_candidate,
        "archive_disposition": profile.archive_disposition,
        "screen_model": profile.render,
        "audio_model": profile.sound,
        "input_model": profile.input,
        "design_tier": profile.tier,
        "constraints": list(profile.constraints),
        "planned_native_format": profile.artifact,
        "capability_status": "native_source_project_only" if source_ready else "design_catalogue_only",
        "native_source_project_available": source_ready,
        "native_source_project_kind": "sdl2_c11_cmake" if source_ready else None,
        "native_binary_built": False,
        "native_gameplay_run_verified": False,
        "distribution_licensed": False,
        "verified_native_exporter": False,
        "may_select_for_original_homebrew": True,
        "commercial_game_import_allowed": False,
        "selection_role": "source_inspiration" if as_source else "port_destination",
    }


def editor_platform_options(
    *, search: str = "", kind: str | None = None,
    legacy: bool | None = None, as_source: bool = False,
    verified_native_only: bool = False, registry: PlatformRegistry | None = None,
) -> tuple[dict[str, object], ...]:
    """Return complete sorted searchable menu; never silently omit discontinued targets."""
    if not isinstance(search, str) or len(search) > 128:
        raise PlatformRegistryError("search must be <=128 characters")
    if kind is not None and kind not in {
        "console", "handheld", "computer", "arcade", "calculator", "mobile",
        "educational", "micro", "fantasy", "precursor", "electromechanical", "mechanical",
    }:
        raise PlatformRegistryError("unknown platform kind")
    if legacy is not None and type(legacy) is not bool:
        raise PlatformRegistryError("legacy filter must be boolean")
    if type(as_source) is not bool or type(verified_native_only) is not bool:
        raise PlatformRegistryError("option switches must be boolean")
    catalog = default_registry() if registry is None else registry
    if not isinstance(catalog, PlatformRegistry):
        raise PlatformRegistryError("registry must be validated")
    if verified_native_only:
        # No SDK or hardware attestation has been independently verified yet.
        return ()
    words = search.casefold().strip().split()
    return tuple(
        _option(p, as_source=as_source)
        for p in catalog.select(kind=kind, legacy=legacy)
        if all(word in " ".join((p.id, p.name, p.family, p.kind, p.render)).casefold() for word in words)
    )


def editor_portability_context(
    source_platform_id: str, *, registry: PlatformRegistry | None = None,
) -> dict[str, object]:
    """Describe all 300 possible planning directions from any source system."""
    catalog = default_registry() if registry is None else registry
    if not isinstance(catalog, PlatformRegistry):
        raise PlatformRegistryError("registry must be validated")
    source = catalog.get(source_platform_id)
    targets = []
    for target in catalog.profiles.values():
        delta = target.tier - source.tier
        operation = "enhance" if delta > 0 else ("constrain" if delta < 0 else "reinterpret")
        targets.append({
            "target_platform_id": target.id,
            "target_name": target.name,
            "target_kind": target.kind,
            "target_is_legacy": target.is_legacy,
            "transformation": operation,
            "design_reachable": True,
            "native_export_verified": False,
            "native_source_project_available": target.id in _NATIVE_SOURCE_TARGETS,
            "native_source_project_kind": "sdl2_c11_cmake" if target.id in _NATIVE_SOURCE_TARGETS else None,
            "source_style_retained_as_requirement": True,
        })
    return {
        "source_platform_id": source.id,
        "source_name": source.name,
        "source_constraints": list(source.constraints),
        "possible_destination_count": len(targets),
        "native_export_destination_count": 0,
        "native_source_project_destination_count": len(_NATIVE_SOURCE_TARGETS & set(catalog.profiles)),
        "rights_policy": "original_or_cleared_homebrew_only",
        "modes": [mode.value for mode in PortMode],
        "targets": targets,
    }


def editor_platform_form(*, registry: PlatformRegistry | None = None) -> dict[str, object]:
    """UI-neutral, versioned data contract for source/destination and port-mode menus."""
    catalog = default_registry() if registry is None else registry
    if not isinstance(catalog, PlatformRegistry):
        raise PlatformRegistryError("registry must be validated")
    return {
        "schema_version": 1,
        "source_options": list(editor_platform_options(as_source=True, registry=catalog)),
        "target_options": list(editor_platform_options(registry=catalog)),
        "port_modes": [
            {"value": PortMode.FAITHFUL.value, "label": "Faithful homebrew port"},
            {"value": PortMode.ENHANCED.value, "label": "Modernized style-preserving port"},
            {"value": PortMode.REVERSE_CONSTRAINED.value, "label": "Authentic older-hardware adaptation"},
            {"value": PortMode.CROSS_HYBRID.value, "label": "Original, independently cleared two-source hybrid"},
        ],
        "export_status": "no_native_target_verified",
        "source_export_status": "three_desktop_c11_source_exporters_unverified_binaries",
        "native_source_project_destinations": sorted(_NATIVE_SOURCE_TARGETS & set(catalog.profiles)),
        "native_source_export_requires": [
            "generated_original_playable_world",
            "matching_cleared_homebrew_source",
            "explicit_authorization",
            "independent_target_specific_compilation_and_gameplay_acceptance",
        ],
        "mandatory_inputs": [
            "owned_or_licensed_homebrew_project",
            "independently_reviewed_rights_evidence",
            "creative_identity_invariants",
            "target_platform_id",
        ],
        "disclaimer": "System selection produces a design blueprint, not a native ROM, disc, executable or firmware.",
    }
