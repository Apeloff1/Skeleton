"""Truthful target inventory for the coded Jeeves game runtimes.

Console labels are design targets, not evidence that a cartridge or hardware
instruction set is emulated.  The eleven existing engines are deterministic
reference simulations.  The separately owned DMG core is explicitly limited.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from importlib.util import find_spec

from .game_engine_lab import EngineEra, GameEngineLabError, engine_era_profile
from .game_engine_runtime import EngineFamily, engine_family

CATALOG_SCHEMA = "skeleton.game_console_catalog.v1"

GENERATION_ERAS = {
    "8bit": EngineEra.EIGHT_BIT,
    "16bit": EngineEra.SIXTEEN_BIT,
    "early3d": EngineEra.FIXED_3D,
    "64bit": EngineEra.SHADER,
    "earlyhd": EngineEra.HD,
    "modern": EngineEra.MODERN,
    "nextgen": EngineEra.NEXT,
}


@dataclass(frozen=True, slots=True)
class ConsoleTarget:
    target_id: str
    label: str
    era: EngineEra
    generation_id: str | None = None
    runtime_kind: str = "reference_game_simulation"
    requires_rom: bool = False
    native_target_id: str | None = None

    @property
    def family(self) -> EngineFamily:
        return engine_family(self.era)

    @property
    def reference_supported(self) -> bool:
        return not self.requires_rom and self.native_target_id is None

    def as_dict(self) -> dict[str, object]:
        if self.native_target_id is not None:
            native = next((row for row in _native_inventory() if row["id"] == self.native_target_id), None)
            if native is None:
                raise GameEngineLabError("canonical Dragon target declaration is unavailable")
            source_available = bool(native.get("supported_styles")) and native["status"] == "native_source"
            local_gameplay = self.native_target_id == "thumby"
            return {
                "schema_version": CATALOG_SCHEMA,
                "target_id": self.target_id,
                "label": self.label,
                "engine_era": self.era.value,
                "family": self.family.value,
                "generation_id": self.generation_id,
                "native_target_id": self.native_target_id,
                "runtime_kind": "native_gameplay_python" if local_gameplay else "native_source_project",
                "execution_mode": (
                    "canonical_numeric_gameplay" if local_gameplay else "source_only_toolchain_required"
                ),
                "native_metadata": dict(native),
                "source_status": native["status"],
                "reference_target_id": self.era.value,
                "reference_association_only": True,
                "reference_supported": False,
                "requires_rom": False,
                "rom_execution": False,
                "full_hardware_emulation": False,
                "commercial_rom_compatibility_verified": False,
                "readiness": {
                    "status": (
                        "source_implemented_unverified"
                        if local_gameplay
                        else "native_source_available_uncompiled" if source_available else native["status"]
                    ),
                    "execution_checked": False,
                    "reason": "Canonical native CPU/SDK source is available only where supported_styles is nonempty; native execution requires an admitted independent local build",
                },
                "capabilities": {
                    "native_source_generation": source_available,
                    "native_binary_execution": False,
                    "native_gameplay_execution": local_gameplay,
                    "device_graphics_verified": False,
                    "native_console_binary_export": False,
                    "generated_grid_simulation": True,
                    "reset": local_gameplay,
                    "step": local_gameplay,
                    "snapshot": local_gameplay,
                    "restore": local_gameplay,
                    "hosted_provider_required": False,
                },
                "limitations": [
                    "The associated EngineEra is a design reference, not hardware emulation",
                    "Source generation does not establish successful compilation or gameplay",
                    "Licensed SDK access and external toolchain installation are not supplied",
                ],
            }
        profile = engine_era_profile(self.era)
        rom_core = find_spec("skeleton.jeeves.game_rom_runtime") is not None
        return {
            "schema_version": CATALOG_SCHEMA,
            "target_id": self.target_id,
            "label": self.label,
            "engine_era": self.era.value,
            "generation_id": self.generation_id,
            "family": self.family.value,
            "runtime_kind": self.runtime_kind,
            "reference_supported": self.reference_supported,
            "rom_execution": self.requires_rom and rom_core,
            "requires_rom": self.requires_rom,
            "full_hardware_emulation": False,
            "commercial_rom_compatibility_verified": False,
            "readiness": {
                "status": (
                    "requires_compatible_rom"
                    if self.requires_rom and rom_core
                    else (
                        "implementation_unavailable" if self.requires_rom else "source_implemented_unverified"
                    )
                ),
                "execution_checked": False,
                "reason": (
                    "Experimental DMG instruction/mapper limits are validated at ROM admission"
                    if self.requires_rom
                    else "Real coded reference simulation; platform label does not grant binary compatibility"
                ),
            },
            "capabilities": {
                "reset": True,
                "step": True,
                "snapshot": True,
                "restore": True,
                "deterministic_replay": True,
                "tabular_policy_learning": True,
                "native_console_binary_export": False,
                "reference_render_commands": not self.requires_rom,
                "rom_framebuffer": self.requires_rom and rom_core,
                "hosted_provider_required": False,
            },
            "tick_hz": profile.tick_hz if not self.requires_rom else None,
            "reference_profile": {
                "render_path": profile.render_path,
                "numeric_mode": profile.numeric_mode.value,
                "entity_budget": profile.entity_budget,
                "draw_budget": profile.draw_budget,
                "capabilities": list(profile.capabilities),
                "constraints": list(profile.constraints),
            },
            "limitations": [
                "No target label proves commercial console compatibility",
                "GB-20 is the repository's biomechanical spine module; ROM there means range of motion",
                *(
                    ["Experimental DMG core; unsupported instructions and mappers fail explicitly"]
                    if self.requires_rom
                    else ["No CPU, cartridge mapper or console operating system emulation"]
                ),
            ],
        }


_TARGETS = (
    tuple(ConsoleTarget(era.value, era.value.replace("_", " "), era) for era in EngineEra)
    + tuple(
        ConsoleTarget(generation, generation, era, generation) for generation, era in GENERATION_ERAS.items()
    )
    + (
        ConsoleTarget("nes", "NES", EngineEra.EIGHT_BIT, "8bit"),
        ConsoleTarget("sms", "Sega Master System", EngineEra.EIGHT_BIT, "8bit"),
        ConsoleTarget("snes", "SNES", EngineEra.SIXTEEN_BIT, "16bit"),
        ConsoleTarget("genesis", "Genesis", EngineEra.SIXTEEN_BIT, "16bit"),
        ConsoleTarget("ps1", "PlayStation", EngineEra.FIXED_3D, "early3d"),
        ConsoleTarget("n64", "Nintendo 64", EngineEra.FIXED_3D, "early3d"),
        ConsoleTarget("saturn", "Saturn", EngineEra.FIXED_3D, "early3d"),
        ConsoleTarget("ps2", "PlayStation 2", EngineEra.SHADER, "64bit"),
        ConsoleTarget("xbox", "Xbox", EngineEra.SHADER, "64bit"),
        ConsoleTarget("gamecube", "GameCube", EngineEra.SHADER, "64bit"),
        ConsoleTarget("ps3", "PlayStation 3", EngineEra.HD, "earlyhd"),
        ConsoleTarget("xbox360", "Xbox 360", EngineEra.HD, "earlyhd"),
        ConsoleTarget("ps5", "PlayStation 5", EngineEra.MODERN, "modern"),
        ConsoleTarget("xbox_series", "Xbox Series", EngineEra.MODERN, "modern"),
        ConsoleTarget("pc", "PC reference simulation", EngineEra.MODERN, "modern"),
        ConsoleTarget("dos_pc", "Software 3D PC", EngineEra.EARLY_3D),
        ConsoleTarget("ps6_concept", "PS6 design concept", EngineEra.NEXT, "nextgen"),
        ConsoleTarget("next_xbox_concept", "Next Xbox design concept", EngineEra.NEXT, "nextgen"),
        ConsoleTarget(
            "game_boy",
            "Game Boy DMG experimental ROM",
            EngineEra.EIGHT_BIT,
            "8bit",
            "experimental_dmg_rom",
            True,
        ),
    )
)
_BY_ID = {target.target_id: target for target in _TARGETS}
_ALIASES = {
    "famicom": "nes",
    "master_system": "sms",
    "mega_drive": "genesis",
    "megadrive": "genesis",
    "xbox_360": "xbox360",
    "series_x": "xbox_series",
    "seriesx": "xbox_series",
    "gameboy": "game_boy",
    "dmg": "game_boy",
    "gb": "game_boy",
}


def _native_inventory() -> tuple[dict[str, object], ...]:
    """Reuse the canonical complete registry, including supplemental identities."""
    try:
        module = importlib.import_module("skeleton.ai.webcrawler.dragon_native_targets")
    except ModuleNotFoundError as exc:
        if exc.name in {"skeleton.ai.webcrawler", "skeleton.ai.webcrawler.dragon_native_targets"}:
            return ()
        raise GameEngineLabError("canonical Dragon target dependency is unavailable") from exc
    rows = module.target_catalog()
    if not isinstance(rows, tuple) or len(rows) > 512:
        raise GameEngineLabError("canonical Dragon target inventory exceeds capacity")
    seen = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not 1 <= len(row["id"]) <= 128
            or row["id"] in seen
            or row.get("status")
            not in {"native_source", "toolchain_adapter", "licensed_sdk", "historical_reference"}
        ):
            raise GameEngineLabError("canonical Dragon target identity or status is invalid")
        seen.add(row["id"])
    return rows


def _native_reference_era(row: dict[str, object]) -> EngineEra:
    identity, year = row["id"], row["year"]
    if identity in {
        "game_boy",
        "game_boy_pocket",
        "game_boy_light",
        "game_boy_color",
        "game_gear",
        "arduboy",
        "thumby",
        "playdate",
    }:
        return EngineEra.EIGHT_BIT
    if identity in {"dos_vga", "dos_8086", "windows_95", "windows_31", "windows_98"}:
        return EngineEra.EARLY_3D
    if type(year) is not int:
        raise GameEngineLabError("canonical Dragon target year is invalid")
    if year < 1987:
        return EngineEra.EIGHT_BIT
    if year < 1993:
        return EngineEra.SIXTEEN_BIT
    if year < 1999:
        return EngineEra.FIXED_3D
    if year < 2005:
        return EngineEra.SHADER
    if year < 2013:
        return EngineEra.HD
    if year < 2020:
        return EngineEra.OPEN_WORLD
    return EngineEra.MODERN


def native_console_catalog() -> list[dict[str, object]]:
    return [_native_target(row).as_dict() for row in _native_inventory()]


def _native_target(row: dict[str, object]) -> ConsoleTarget:
    return ConsoleTarget(
        "dragon_native:" + row["id"],
        row["family"] + " · " + row["id"],
        _native_reference_era(row),
        runtime_kind="native_source_project",
        native_target_id=row["id"],
    )


def resolve_console(target_id: str | EngineEra) -> ConsoleTarget:
    """Resolve only declared targets; an unknown label never selects a fallback."""
    if isinstance(target_id, EngineEra):
        return _BY_ID[target_id.value]
    if not isinstance(target_id, str) or not 1 <= len(target_id) <= 128:
        raise GameEngineLabError("console target must be a bounded registered identifier")
    key = target_id.strip().lower().replace(" ", "_").replace("-", "_")
    if key.startswith("dragon_native:"):
        native_id = key.removeprefix("dragon_native:")
        for row in _native_inventory():
            if row["id"] == native_id:
                return _native_target(row)
        raise GameEngineLabError("native target is absent from the canonical Dragon registry")
    key = _ALIASES.get(key, key)
    try:
        return _BY_ID[key]
    except KeyError as exc:
        raise GameEngineLabError(f"unsupported console target: {target_id!r}") from exc


def console_catalog() -> list[dict[str, object]]:
    return [target.as_dict() for target in _TARGETS] + native_console_catalog()


def execution_inventory() -> dict[str, object]:
    """Include related real owners without disguising them as console emulators."""
    return {
        "schema_version": CATALOG_SCHEMA,
        "targets": console_catalog(),
        "related_owners": [
            {
                "owner": "skeleton.ai.webcrawler.dragon_native_targets",
                "kind": "complete_native_hardware_and_source_registry",
                "hardware_emulation": False,
            },
            {
                "owner": "skeleton.ai.webcrawler.dragon_native_projects",
                "kind": "original_native_cpu_and_sdk_source_emitters",
                "native_execution": "requires_independent_toolchain_build",
            },
            {
                "owner": "skeleton.ai.webcrawler.dragon_native_arcade_runtime",
                "kind": "actual_c99_sdl2_2d_engine_source",
                "native_execution": "source_not_compiled",
            },
            {
                "owner": "skeleton.ai.webcrawler.dragon_native_raycaster",
                "kind": "actual_c99_sdl2_dda_3d_engine_source",
                "native_execution": "source_not_compiled",
            },
            {
                "owner": "skeleton.ai.webcrawler.dragon_native_compile",
                "kind": "opt_in_fixed_toolchain_local_compiler",
                "native_execution": "separate_local_cli_authority",
            },
            {
                "owner": "skeleton.forge.hardware",
                "kind": "seven_generation_asset_envelopes",
                "hardware_emulation": False,
            },
            {
                "owner": "skeleton.forge.eras",
                "kind": "twenty_four_gameplay_dialects",
                "hardware_emulation": False,
            },
            {
                "owner": "skeleton.forge.sim",
                "kind": "deterministic_encounter_and_session_simulation",
                "hardware_emulation": False,
            },
            {
                "owner": "skeleton.forge.playtest",
                "kind": "optional_local_godot_process",
                "readiness": "requires_installed_toolchain",
                "hardware_emulation": False,
            },
            {
                "owner": "skeleton.simulation.game",
                "kind": "gameplay_composition_and_replay",
                "hardware_emulation": False,
            },
            {
                "owner": "skeleton.simulation.ecs",
                "kind": "world_state_and_checkpoint_runtime",
                "hardware_emulation": False,
            },
            {
                "owner": "skeleton.spine.engine",
                "kind": "gb20_biomechanical_range_of_motion",
                "hardware_emulation": False,
            },
        ],
    }
