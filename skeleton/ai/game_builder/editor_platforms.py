"""Editor-facing platform picker data for *candidate* homebrew source/targets.

The stable JSON-compatible payload distinguishes design reachability from
independently certified native exporters. This is an API model, not a GUI.
"""
from __future__ import annotations

from .platform_registry import PlatformProfile, PlatformRegistry, PlatformRegistryError, default_registry
from .port_planner import PortMode, HomebrewSource, compile_progressive_port_route

# Source producers are real and platform-specific. None self-certifies a build or release.
_NATIVE_SOURCE_ADAPTERS = {
    "windows_modern": "sdl2_c11_cmake",
    "linux_desktop": "sdl2_c11_cmake",
    "macos_modern": "sdl2_c11_cmake",
    "nintendo_game_boy": "rgbds_dmg_2bpp_rom_source",
    "nintendo_game_boy_color": "rgbds_cgb_rgb555_attribute_rom_source",
    "nintendo_famicom": "ca65_nrom256_2bpp_rom_source",
    "commodore_64": "cc65_6510_vic_ii_sid_prg_source",
    "dos_vga": "nasm_8086_pc_textmode_com_source",
    "atari_400_800": "cc65_6502_antic_gtia_pokey_xex_source",
    "apple_ii": "cc65_6502_apple2_applesingle_source",
    "sinclair_zx_spectrum": "z80asm_spectrum_ula_keyboard_rom_tap_source",
    "msx1": "z80asm_msx1_bios_vdp_16kb_rom_source",
    "colecovision": "z80asm_coleco_os7_32kb_tms9918_native_rom_source",
    "vectrex": "lwasm_6809_crt_beam_vector_game_source",
    "sega_master_system": "z80asm_sms_mode4_4bpp_32kb_cartridge_source",
    "sega_game_gear": "sdcc_devkitsms_gg_rgb444_handheld_source",
}
_NATIVE_SOURCE_TARGETS = frozenset(_NATIVE_SOURCE_ADAPTERS)

_PORTABLE_TILE_CODEC = {
    "nintendo_game_boy": "gb_2bpp",
    "nintendo_game_boy_color": "gb_2bpp",
    "nintendo_famicom": "nes_2bpp",
    "nintendo_snes": "snes_4bpp",
    "sega_master_system": "sms_4bpp",
    "sega_game_gear": "sms_4bpp",
    "sega_mega_drive": "genesis_4bpp",
}
_PORTABLE_PALETTE_CODEC = {
    "nintendo_game_boy_color": "rgb555",
    "nintendo_snes": "rgb555",
}
_PORTABLE_TONE_TIMER = {
    "nintendo_game_boy": "gameboy_pulse",
    "nintendo_game_boy_color": "gameboy_pulse",
    "nintendo_famicom": "nes_pulse",
    "sega_master_system": "sn76489",
    "sega_game_gear": "sn76489",
    "sega_mega_drive": "sn76489",
}


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
        "native_source_project_kind": _NATIVE_SOURCE_ADAPTERS.get(profile.id),
        "portable_tile_codec": _PORTABLE_TILE_CODEC.get(profile.id),
        "portable_palette_codec": _PORTABLE_PALETTE_CODEC.get(profile.id),
        "portable_tone_timer": _PORTABLE_TONE_TIMER.get(profile.id),
        "portable_asset_conversion_status": (
            "offline_source_data_only"
            if profile.id in _PORTABLE_TILE_CODEC
            else "platform_specific_codec_not_implemented"
        ),
        "portable_asset_release_verified": False,
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
            "native_source_project_kind": _NATIVE_SOURCE_ADAPTERS.get(target.id),
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



def editor_progressive_route_preview(
    source: HomebrewSource, destinations: tuple[str, ...], *,
    mode: PortMode = PortMode.ENHANCED,
    registry: PlatformRegistry | None = None,
) -> dict[str, object]:
    """Deliver a fully serializable, custody-bound cross-era editor preview.

    It never fabricates intermediate binaries, hardware test outcomes,
    independent IP review or licensed distribution rights.
    """
    plan = compile_progressive_port_route(
        source, destinations, mode=mode, registry=registry,
    )
    return {
        "schema": "skeleton.game_builder.progressive_route_preview.v1",
        "original_project_id": plan.original_project_id,
        "original_platform_id": plan.original_platform_id,
        "original_rights_basis": plan.original_rights_basis,
        "original_evidence_sha256": plan.original_evidence_sha256,
        "creative_identity": list(plan.creative_identity),
        "design_route_digest": plan.digest,
        "planning_status": plan.planning_status,
        "native_binary_built": False,
        "rights_independently_verified": False,
        "distribution_authorized": False,
        "hops": [
            {
                "ordinal": hop.step,
                "from": hop.from_platform_id,
                "to": hop.to_platform_id,
                "mode": hop.mode,
                "design_digest": hop.digest,
                "previous_design_digest": hop.prior_hop_digest,
                "original_rights_evidence_sha256": hop.original_rights_evidence_sha256,
                "target_constraints": list(hop.target_constraints),
                "actions": [
                    {"phase": action.phase,
                     "disposition": action.disposition, "work": action.work}
                    for action in hop.actions
                ],
                "pending_release_gates": list(hop.pending_release_gates),
                "native_binary_built": False,
                "rights_independently_verified": False,
                "distribution_authorized": False,
            }
            for hop in plan.hops
        ],
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
        "source_export_status": "three_desktop_three_rom_one_c64_one_dos_one_atari8_one_apple2_one_zx48_one_msx1_one_sms_one_gamegear_one_coleco_one_vectrex_native_sources",
        "native_source_project_destinations": sorted(_NATIVE_SOURCE_TARGETS & set(catalog.profiles)),
        "progressive_route_preview": {
            "supported": True,
            "max_destinations": 5,
            "modes": [PortMode.FAITHFUL.value, PortMode.ENHANCED.value,
                      PortMode.REVERSE_CONSTRAINED.value],
            "original_source_custody_preserved": True,
            "intermediate_binary_claims_permitted": False,
            "independent_hop_rights_reviews_required": True,
            "preview_is_release_authorization": False,
        },
        "atomic_all_native_original_portfolio_supported": True,
        "portfolio_target_count": len(_NATIVE_SOURCE_TARGETS & set(catalog.profiles)),
        "portfolio_partial_export_allowed": False,
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
        "disclaimer": "Platform selection is a blueprint unless a source adapter is shown; generated sources are not compiled binaries or release approvals.",
    }
