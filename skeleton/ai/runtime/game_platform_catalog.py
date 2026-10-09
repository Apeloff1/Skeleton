"""Cross-era game platform registry: planning, not fictional export support.

Every profile is a named *design/compatibility target*, not an emulator,
compiler, published SDK license, legal exemption or completed native port.
Only Skeleton's universal scene JSON exporter is currently implemented;
historical ROM/firmware formats and proprietary console binaries are not.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

SCHEMA = "skeleton.game.platform_catalog.v1"
ERA_GROUPS: tuple[tuple[str, str, str, str, str], ...] = (
    # Era, category, technical style, SDK gate, target list.
    ("1970s", "arcade", "fixed_screen", "community_toolchain",
     "arcade-discrete arcade-early-cpu atari-pong magnvox-odyssey atari-2600"),
    ("1970s", "home_console", "tile2d", "community_toolchain",
     "fairchild-channel-f rca-studio-ii intellivision"),
    ("1970s", "home_computer", "tile2d", "community_toolchain",
     "apple-ii trs80-model-i commodore-pet ti-99-4a"),
    ("1980s", "home_console", "tile2d", "community_toolchain",
     "atari-5200 atari-7800 colecovision vectrex nes-famicom famicom-disk-system "
     "sega-sg1000 sega-master-system sega-mark-iii atari-xegs"),
    ("1980s", "handheld", "tile2d", "community_toolchain",
     "nintendo-game-and-watch game-boy atari-lynx game-gear"),
    ("1980s", "home_computer", "tile2d", "community_toolchain",
     "commodore-vic20 commodore-64 commodore-128 zx-spectrum zx81 "
     "bbc-micro acorn-electron msx msx2 amstrad-cpc atari-8bit "
     "atari-st atari-ste amiga-ocs amiga-ecs pc8801 pc9801 x68000"),
    ("1980s", "pc", "tile2d", "open_toolchain",
     "ibm-pc-dos dos-cga dos-ega classic-macintosh apple-iigs"),
    ("1980s", "arcade", "sprite2d", "community_toolchain",
     "arcade-z80 arcade-m68000 sega-system16 capcom-cps1"),
    ("1980s", "home_console", "sprite2d", "community_toolchain",
     "pc-engine-turbografx pc-engine-cd sega-genesis-mega-drive neo-geo-mvs neo-geo-aes"),
    ("1990s", "home_console", "sprite2d", "community_toolchain",
     "super-nintendo-snes super-famicom sega-cd sega-32x pc-engine-supergrafx "
     "neo-geo-cd atari-jaguar cd32 3do philips-cdi"),
    ("1990s", "home_console", "polygon3d", "community_toolchain",
     "nintendo-64 playstation-1 sega-saturn sega-dreamcast pc-fx"),
    ("1990s", "handheld", "sprite2d", "community_toolchain",
     "game-boy-pocket game-boy-color virtual-boy neo-geo-pocket "
     "neo-geo-pocket-color wonderswan wonderswan-color"),
    ("1990s", "pc", "polygon3d", "open_toolchain",
     "dos-vga dos-mode-x windows-3x windows-95 windows-98 "
     "linux-x11 classic-mac-powerpc beos"),
    ("1990s", "arcade", "polygon3d", "community_toolchain",
     "sega-model1 sega-model2 sega-model3 sega-naomi capcom-cps2 capcom-cps3"),
    ("2000s", "home_console", "polygon3d", "community_toolchain",
     "playstation-2 gamecube original-xbox nintendo-wii xbox-360 playstation-3"),
    ("2000s", "handheld", "sprite2d", "community_toolchain",
     "game-boy-advance game-boy-advance-sp nintendo-ds nintendo-dsi "
     "playstation-portable gizmondo"),
    ("2000s", "pc", "polygon3d", "open_toolchain",
     "windows-xp windows-vista linux-opengl macos-x"),
    ("2000s", "mobile", "tile2d", "open_toolchain",
     "symbian-s60 j2me-midp palm-os blackberry-os early-iphone-os"),
    ("2010s", "home_console", "polygon3d", "licensed_sdk",
     "playstation-4 xbox-one nintendo-wii-u nintendo-switch"),
    ("2010s", "handheld", "polygon3d", "licensed_sdk",
     "nintendo-3ds new-nintendo-3ds playstation-vita"),
    ("2010s", "pc", "polygon3d", "open_toolchain",
     "windows-7 windows-8 windows-10 linux-vulkan macos-metal steam-os"),
    ("2010s", "mobile", "polygon3d", "platform_entitlement",
     "android-ios-era ios-metal ipad-os"),
    ("2020s", "home_console", "polygon3d", "licensed_sdk",
     "playstation-5 xbox-series-x xbox-series-s nintendo-switch-2"),
    ("2020s", "handheld", "polygon3d", "open_toolchain",
     "steam-deck rog-ally linux-handheld"),
    ("2020s", "pc", "polygon3d", "open_toolchain",
     "windows-11 linux-desktop macos-apple-silicon"),
    ("2020s", "mobile", "polygon3d", "platform_entitlement",
     "android-modern ios-modern"),
    ("2020s", "xr", "polygon3d", "platform_entitlement",
     "meta-quest visionos psvr2 steamvr openxr"),
    ("2020s", "fantasy", "tile2d", "separate_license_review",
     "pico8 tic80 wasm4 arduboy playdate"),
)
# Capability archetypes for *analysis* only; profiles do not assert that a
# build toolchain or emulator actually exists/works in this repository.
_STYLE_FEATURES: dict[str, frozenset[str]] = {
    "fixed_screen": frozenset({"tile2d", "input", "deterministic_gameplay"}),
    "tile2d": frozenset({"tile2d", "input", "deterministic_gameplay", "animation2d"}),
    "sprite2d": frozenset({
        "tile2d", "sprite2d", "animation2d", "input", "deterministic_gameplay",
        "local_audio",
    }),
    "polygon3d": frozenset({
        "tile2d", "sprite2d", "animation2d", "input", "deterministic_gameplay",
        "local_audio", "scene3d", "camera3d",
    }),
}
_FEATURES = frozenset({
    "tile2d", "sprite2d", "animation2d", "input", "deterministic_gameplay",
    "local_audio", "scene3d", "camera3d", "networked_play",
    "user_mods", "save_data", "physical_controller", "haptics",
})
_TARGET = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


class GamePlatformError(ValueError):
    """Unknown target or unsupported claim about platform readiness."""


@dataclass(frozen=True, slots=True)
class GamePlatform:
    id: str
    era: str
    category: str
    style: str
    toolchain_class: str

    @property
    def possible_design_features(self) -> frozenset[str]:
        return _STYLE_FEATURES[self.style]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "era": self.era,
            "category": self.category,
            "design_style": self.style,
            "toolchain_class": self.toolchain_class,
            "possible_design_features": sorted(self.possible_design_features),
            "native_export_implemented": False,
            "emulator_integrated": False,
            "real_hardware_validated": False,
            "sdk_access_verified": False,
            "published_binary_ready": False,
            "rights_clearance_certified": False,
            "unlocked_build_claimed": False,
        }


def _load() -> dict[str, GamePlatform]:
    out: dict[str, GamePlatform] = {}
    for era, category, style, sdk, identities in ERA_GROUPS:
        if style not in _STYLE_FEATURES or sdk not in (
            "open_toolchain", "community_toolchain", "licensed_sdk",
            "platform_entitlement", "separate_license_review",
        ):
            raise RuntimeError("invalid cross-era catalog grouping")
        for slug in identities.split():
            if not _TARGET.fullmatch(slug) or slug in out:
                raise RuntimeError("duplicate/invalid gaming platform ID: " + slug)
            out[slug] = GamePlatform(slug, era, category, style, sdk)
    return out


TARGETS: dict[str, GamePlatform] = _load()
CATALOG_SHA256 = hashlib.sha256(
    json.dumps(
        [profile.as_dict() for _, profile in sorted(TARGETS.items())],
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def catalog_summary() -> dict[str, Any]:
    by_era = {
        era: sum(target.era == era for target in TARGETS.values())
        for era in ("1970s", "1980s", "1990s", "2000s", "2010s", "2020s")
    }
    return {
        "schema_version": SCHEMA,
        "catalog_sha256": CATALOG_SHA256,
        "target_count": len(TARGETS),
        "eras": by_era,
        "native_console_exporter_count": 0,
        "ready_own_original_universal_scene_json": True,
        "catalog_equivalent_to_native_platform_support": False,
        "distribution_law_verified": False,
    }


def plan_game_targets(
    *,
    target_ids: list[str],
    required_features: list[str],
    sdk_authorizations: dict[str, str] | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(target_ids, list) or not 1 <= len(target_ids) <= 64
        or not all(isinstance(x, str) and x in TARGETS for x in target_ids)
        or len(set(target_ids)) != len(target_ids)
        or not isinstance(required_features, list)
        or any(not isinstance(x, str) or x not in _FEATURES for x in required_features)
        or len(set(required_features)) != len(required_features)
    ):
        raise GamePlatformError("invalid target or capability selection")
    sdk = sdk_authorizations if sdk_authorizations is not None else {}
    if not isinstance(sdk, dict) or any(
        target not in target_ids
        or not isinstance(ref, str)
        or not 4 <= len(ref) <= 256
        for target, ref in sdk.items()
    ):
        raise GamePlatformError("SDK proof identifiers must be tied to selected targets")
    rows = []
    for tid in target_ids:
        p = TARGETS[tid]
        uncovered = sorted(set(required_features) - p.possible_design_features)
        approval_required = p.toolchain_class in (
            "licensed_sdk", "platform_entitlement", "separate_license_review",
        )
        rows.append({
            **p.as_dict(),
            "requested_features": sorted(required_features),
            "unmodeled_design_features": uncovered,
            "design_feasibility_estimated": not uncovered,
            "sdk_reference_attested": tid in sdk,
            "sdk_independent_authorization_verified": False,
            "toolchain_authorization_review_required": approval_required,
            "unimplemented_native_export_is_blocker": True,
            "export_approved": False,
            "hardware_quality_measured": False,
        })
    return {
        "schema_version": "skeleton.game.platform_plan.v1",
        "catalog_sha256": CATALOG_SHA256,
        "targets": rows,
        "requested_targets": len(rows),
        "native_binaries_ready": 0,
        "design_only": True,
        "training_examples_created": 0,
        "rom_images_created": 0,
        "copyright_compliance_certified": False,
    }


__all__ = [
    "SCHEMA", "TARGETS", "ERA_GROUPS", "CATALOG_SHA256",
    "GamePlatformError", "GamePlatform", "catalog_summary",
    "plan_game_targets",
]
