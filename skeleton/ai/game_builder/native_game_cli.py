"""Produce a real, original game source project for a selected native machine.

Example:
  python -m skeleton.ai.game_builder.native_game_cli \
    --target nintendo_game_boy --basis bandai_wonderswan \
    --project-id my-puzzle --title 'Moon Trails' \
    --seed 1847 --width 17 --height 15 --levels 3 \
    --collectibles 3 --hazards 4 --health 4 \
    --rights-evidence ./my-owned-authorship-receipt.txt \
    --identity original-tiles --identity original-maze-rules \
    --output ./my-original-cartridge --authorize-original-homebrew

This CLI does not compile ROMs, install toolchains, fetch third-party material,
start emulators, or bypass permission gates. Output is a NEW directory only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .desktop_native_export import compile_native_desktop, export_native_desktop_source
from .game_boy_native_export import compile_native_game_boy, export_native_game_boy
from .game_boy_color_native_export import compile_native_game_boy_color, export_native_game_boy_color
from .nes_native_export import compile_native_nes, export_native_nes
from .c64_native_export import compile_native_c64, export_native_c64
from .dos_native_export import compile_native_dos, export_native_dos
from .atari8_native_export import compile_native_atari8, export_native_atari8
from .apple2_native_export import compile_native_apple2, export_native_apple2
from .spectrum_native_export import compile_native_spectrum, export_native_spectrum
from .sega_8bit_native_export import compile_native_sega_8bit, export_native_sega_8bit
from .msx1_native_export import compile_native_msx1, export_native_msx1
from .coleco_native_export import compile_native_coleco, export_native_coleco
from .vectrex_native_export import compile_native_vectrex, export_native_vectrex
from .sms_native_export import compile_native_sms, export_native_sms
from .platform_registry import default_registry
from .playable_simulation import demonstrate_solvable
from .playable_world import GameBuildIntent, generate_playable_world
from .port_planner import HomebrewSource
from .studio_asset_pipeline import ArtDirection, render_studio_art, export_studio_art
from .playable_compiler import compile_original_game
from .dual_runtime_export import render_dual_runtime_package, export_dual_runtime_package
from .rights_evidence import read_rights_evidence

_NATIVE = {
    "windows_modern": "sdl2_c11",
    "linux_desktop": "sdl2_c11",
    "macos_modern": "sdl2_c11",
    "nintendo_game_boy": "gb_rgbds",
    "nintendo_game_boy_color": "cgb_rgbds",
    "nintendo_famicom": "nes_ca65",
    "commodore_64": "c64_cc65",
    "dos_vga": "dos_nasm_8086",
    "atari_400_800": "atari8_cc65",
    "apple_ii": "apple2_cc65",
    "sinclair_zx_spectrum": "spectrum_z80asm",
    "sega_game_gear": "gg_sdcc_z80",
    "msx1": "msx1_z80asm",
    "colecovision": "coleco_z80asm",
    "vectrex": "vectrex_lwasm",
    "sega_master_system": "sms_z80asm",
}


def build_game(
    *, target: str, basis: str, project_id: str, title: str, seed: int,
    width: int, height: int, levels: int, collectibles: int,
    hazards: int, health: int, rights_evidence: str | Path,
    creative_identity: tuple[str, ...], output: str | Path, authorized: bool,
    studio_art: ArtDirection | None = None,
    theme: str = "forest",
) -> dict[str, object]:
    """Create native-source projects from a deterministic game, never HTML."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native game source requires explicit original-homebrew authority")
    if target not in _NATIVE:
        raise ValueError("no real native source adapter for requested platform")
    if basis not in default_registry().profiles:
        raise ValueError("unregistered historical design basis")
    evidence = read_rights_evidence(rights_evidence).document_sha256
    source = HomebrewSource(
        project_id=project_id, platform_id=basis, rights_basis="project_owned",
        evidence_sha256=evidence, creative_identity=creative_identity,
    )
    intent = GameBuildIntent(
        project_id=project_id, title=title, subtitle="Original portable native source",
        seed=seed, width=width, height=height, levels=levels,
        collectibles_per_level=collectibles, hazards_per_level=hazards,
        starting_health=health,
        theme=theme,
    )
    world = generate_playable_world(intent, authorized=True)
    proof = demonstrate_solvable(world, authorized=True)
    if proof.world_digest != world.digest or proof.final_state.status != "won":
        raise ValueError("world generator did not prove the original game playable")
    if studio_art is not None and not isinstance(studio_art, ArtDirection):
        raise TypeError("studio art direction must be typed")
    # Preflight and actually render assets BEFORE the source exporter creates
    # its destination. Invalid art cannot leave a half-created source project.
    art_pack = (
        render_studio_art(world, target=target, direction=studio_art, authorized=True)
        if studio_art is not None else None
    )
    tile_art = art_pack.runtime_tiles if art_pack is not None else None
    engine_package = None
    if art_pack is not None:
        # Existing canonical browser/Godot source owners, not a substitute
        # handcrafted JavaScript or a fabricated console emulator.
        playable = compile_original_game(intent, authorized=True)
        if playable.world.digest != world.digest or playable.proof.digest != proof.digest:
            raise ValueError("native and engine game worlds or playthrough proofs diverged")
        # Preserve canonical winning gameplay while rerendering the same world
        # with the precise original pixels used by console ROM source emitters.
        from dataclasses import replace
        from .playable_export import render_playable_world
        playable = replace(playable, playable=render_playable_world(
            world, studio_art=art_pack, authorized=True,
        ))
        engine_package = render_dual_runtime_package(
            playable, authorized=True, studio_art=art_pack,
        )
        if engine_package.manifest["world_digest"] != world.digest:
            raise ValueError("engine source manifests do not match native source")
    kind = _NATIVE[target]
    if kind == "gb_rgbds":
        project = compile_native_game_boy(world, source, authorized=True, tile_art=tile_art)
        folder = export_native_game_boy(project, output, authorized=True)
        artifact_type = "native_game_boy_rgbds_6502free_rom_source"
        digest = project.content_digest
    elif kind == "cgb_rgbds":
        project = compile_native_game_boy_color(world, source, authorized=True, tile_art=tile_art)
        folder = export_native_game_boy_color(project, output, authorized=True)
        artifact_type = "native_cgb_rgb555_rgbds_rom_source"
        digest = project.content_digest
    elif kind == "nes_ca65":
        project = compile_native_nes(world, source, authorized=True, tile_art=tile_art)
        folder = export_native_nes(project, output, authorized=True)
        artifact_type = "native_nes_6502_ca65_nrom_source"
        digest = project.content_digest
    elif kind == "c64_cc65":
        project = compile_native_c64(world, source, authorized=True)
        folder = export_native_c64(project, output, authorized=True)
        artifact_type = "native_c64_6510_vic_ii_sid_cc65_prg_source"
        digest = project.content_digest
    elif kind == "dos_nasm_8086":
        project = compile_native_dos(world, source, authorized=True)
        folder = export_native_dos(project, output, authorized=True)
        artifact_type = "native_dos_8086_pc_textmode_com_source"
        digest = project.content_digest
    elif kind == "atari8_cc65":
        project = compile_native_atari8(world, source, authorized=True)
        folder = export_native_atari8(project, output, authorized=True)
        artifact_type = "native_atari8_6502_antic_gtia_pokey_xex_source"
        digest = project.content_digest
    elif kind == "apple2_cc65":
        project = compile_native_apple2(world, source, authorized=True)
        folder = export_native_apple2(project, output, authorized=True)
        artifact_type = "native_apple2_cc65_applesingle_source"
        digest = project.content_digest
    elif kind == "spectrum_z80asm":
        project = compile_native_spectrum(world, source, authorized=True)
        folder = export_native_spectrum(project, output, authorized=True)
        artifact_type = "native_spectrum_48k_z80_tap_source"
        digest = project.content_digest
    elif kind in ("sms_sdcc_z80", "gg_sdcc_z80"):
        project = compile_native_sega_8bit(world, source, target, authorized=True, tile_art=tile_art)
        folder = export_native_sega_8bit(project, output, authorized=True)
        artifact_type = "native_sega_8bit_sdcc_vdp_original_game_source"
        digest = project.content_digest
    elif kind == "msx1_z80asm":
        project = compile_native_msx1(world, source, authorized=True)
        folder = export_native_msx1(project, output, authorized=True)
        artifact_type = "native_msx1_z80_16kb_bios_rom_source"
        digest = project.content_digest
    elif kind == "coleco_z80asm":
        project = compile_native_coleco(world, source, authorized=True)
        folder = export_native_coleco(project, output, authorized=True)
        artifact_type = "native_colecovision_32kb_z80_tms9918_source"
        digest = project.content_digest
    elif kind == "vectrex_lwasm":
        project = compile_native_vectrex(world, source, authorized=True)
        folder = export_native_vectrex(project, output, authorized=True)
        artifact_type = "native_vectrex_mc6809_vector_cartridge_source"
        digest = project.content_digest
    elif kind == "sms_z80asm":
        project = compile_native_sms(world, source, authorized=True, tile_art=tile_art)
        folder = export_native_sms(project, output, authorized=True)
        artifact_type = "native_sms_z80_mode4_32kb_cartridge_source"
        digest = project.content_digest
    else:
        project = compile_native_desktop(world, source, target, authorized=True)
        folder = export_native_desktop_source(project, output, authorized=True)
        artifact_type = "native_desktop_sdl2_c11_source"
        digest = project.content_digest
    engine_receipt = None
    if engine_package is not None:
        engine_path = export_dual_runtime_package(
            engine_package, folder / "engines", authorized=True,
        )
        engine_receipt = {
            "path": str(engine_path),
            "manifest_digest": engine_package.manifest["manifest_digest"],
            "world_digest": world.digest,
            "browser_source_rendered": "index.html" in engine_package.files,
            "godot4_source_rendered": "godot/scripts/main.gd" in engine_package.files,
            "interactive_tile_editor_source": "tile-editor.html" in engine_package.files,
            "actual_winning_python_replay": True,
            "godot_binary_executed": False,
            "hardware_qualified": False,
            "runtime_uses_custom_asset_tiles": True,
            "actual_browser_sprite_rasterizer_embedded": True,
            "godot_source_sprite_rasterizer_embedded": True,
            "godot_sprite_renderer_executed": False,
        }
    art_receipt = (
        export_studio_art(art_pack, folder, authorized=True)
        if art_pack is not None else None
    )
    return {
        "schema": "skeleton.game_builder.native_creation_receipt.v1",
        "project_id": source.project_id,
        "target": target,
        "source_basis": basis,
        "source_kind": artifact_type,
        "output_directory": str(folder),
        "world_digest": world.digest,
        "winning_replay_digest": proof.digest,
        "levels": len(world.levels),
        "source_content_digest": digest,
        "rights_evidence_sha256": evidence,
        "rights_independently_verified": False,
        "compiler_execution": False,
        "native_binary_built": False,
        "emulator_verified": False,
        "physical_hardware_verified": False,
        "distribution_licensed": False,
        "studio_assets": art_receipt,
        "engine_sources": engine_receipt,
        "native_art_embedded": bool(
            art_receipt and art_receipt["runtime_art_source_embedded"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(_NATIVE), required=True)
    parser.add_argument("--basis", required=True, help="catalogued historical basis")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--theme",
                        choices=("forest", "space", "desert", "ocean", "arcade"),
                        default="forest")
    parser.add_argument("--width", type=int, default=17)
    parser.add_argument("--height", type=int, default=15)
    parser.add_argument("--levels", type=int, default=3)
    parser.add_argument("--collectibles", type=int, default=3)
    parser.add_argument("--hazards", type=int, default=4)
    parser.add_argument("--health", type=int, default=3)
    parser.add_argument("--rights-evidence", required=True, type=Path)
    parser.add_argument("--identity", required=True, action="append")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorize-original-homebrew", action="store_true")
    parser.add_argument("--studio-assets", action="store_true",
                        help="Generate actual sprites, encoded native tiles and PNG previews")
    parser.add_argument("--studio-style",
                        choices=("etched", "luminous", "organic", "arcade"),
                        default="luminous")
    parser.add_argument("--studio-contrast", choices=("classic", "high"),
                        default="classic")
    parser.add_argument("--studio-animation-frames", type=int, default=3)
    parser.add_argument("--studio-no-outline", action="store_true")
    parser.add_argument("--studio-no-highlight", action="store_true")
    parser.add_argument("--studio-foliage", type=int, choices=range(5), default=2)
    parser.add_argument("--studio-shadow", type=int, choices=range(4), default=1)
    parser.add_argument("--studio-parallax-layers", type=int, choices=range(4), default=1)
    parser.add_argument("--studio-music-density", type=int, choices=range(5), default=2)
    parser.add_argument("--studio-animation-fps", type=int, choices=range(1, 25), default=4)
    args = parser.parse_args()
    result = build_game(
        target=args.target, basis=args.basis, project_id=args.project_id,
        title=args.title, seed=args.seed, width=args.width, height=args.height,
        levels=args.levels, collectibles=args.collectibles,
        hazards=args.hazards, health=args.health,
        rights_evidence=args.rights_evidence,
        creative_identity=tuple(args.identity), output=args.output,
        authorized=args.authorize_original_homebrew,
        theme=args.theme,
        studio_art=(
            ArtDirection(
                style=args.studio_style, contrast=args.studio_contrast,
                animation_frames=args.studio_animation_frames,
                seed=args.seed, outline=not args.studio_no_outline,
                highlight=not args.studio_no_highlight,
                foliage_density=args.studio_foliage,
                shadow_strength=args.studio_shadow,
                parallax_layers=args.studio_parallax_layers,
                music_density=args.studio_music_density,
                animation_fps=args.studio_animation_fps,
            ) if args.studio_assets else None
        ),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
