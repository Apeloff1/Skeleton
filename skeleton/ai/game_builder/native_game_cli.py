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
from hashlib import sha256
import json
from pathlib import Path

from .desktop_native_export import compile_native_desktop, export_native_desktop_source
from .game_boy_native_export import compile_native_game_boy, export_native_game_boy
from .nes_native_export import compile_native_nes, export_native_nes
from .c64_native_export import compile_native_c64, export_native_c64
from .platform_registry import default_registry
from .playable_simulation import demonstrate_solvable
from .playable_world import GameBuildIntent, generate_playable_world
from .port_planner import HomebrewSource

_NATIVE = {
    "windows_modern": "sdl2_c11",
    "linux_desktop": "sdl2_c11",
    "macos_modern": "sdl2_c11",
    "nintendo_game_boy": "gb_rgbds",
    "nintendo_famicom": "nes_ca65",
    "commodore_64": "c64_cc65",
}

_MAX_EVIDENCE_FILE = 8 * 1024 * 1024


def build_game(
    *, target: str, basis: str, project_id: str, title: str, seed: int,
    width: int, height: int, levels: int, collectibles: int,
    hazards: int, health: int, rights_evidence: str | Path,
    creative_identity: tuple[str, ...], output: str | Path, authorized: bool,
) -> dict[str, object]:
    """Create native-source projects from a deterministic game, never HTML."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native game source requires explicit original-homebrew authority")
    if target not in _NATIVE:
        raise ValueError("no real native source adapter for requested platform")
    if basis not in default_registry().profiles:
        raise ValueError("unregistered historical design basis")
    path = Path(rights_evidence)
    if path.is_symlink() or not path.is_file():
        raise ValueError("authorship/rights evidence must be an ordinary local file")
    if not 0 < path.stat().st_size <= _MAX_EVIDENCE_FILE:
        raise ValueError("authorship/rights file empty or exceeds input capacity")
    evidence_hash = sha256()
    with path.open("rb") as stream:
        while fragment := stream.read(256 * 1024):
            evidence_hash.update(fragment)
    evidence = evidence_hash.hexdigest()
    source = HomebrewSource(
        project_id=project_id, platform_id=basis, rights_basis="project_owned",
        evidence_sha256=evidence, creative_identity=creative_identity,
    )
    intent = GameBuildIntent(
        project_id=project_id, title=title, subtitle="Original portable native source",
        seed=seed, width=width, height=height, levels=levels,
        collectibles_per_level=collectibles, hazards_per_level=hazards,
        starting_health=health,
    )
    world = generate_playable_world(intent, authorized=True)
    proof = demonstrate_solvable(world, authorized=True)
    if proof.world_digest != world.digest or proof.final_state.status != "won":
        raise ValueError("world generator did not prove the original game playable")
    kind = _NATIVE[target]
    if kind == "gb_rgbds":
        project = compile_native_game_boy(world, source, authorized=True)
        folder = export_native_game_boy(project, output, authorized=True)
        artifact_type = "native_game_boy_rgbds_6502free_rom_source"
        digest = project.content_digest
    elif kind == "nes_ca65":
        project = compile_native_nes(world, source, authorized=True)
        folder = export_native_nes(project, output, authorized=True)
        artifact_type = "native_nes_6502_ca65_nrom_source"
        digest = project.content_digest
    elif kind == "c64_cc65":
        project = compile_native_c64(world, source, authorized=True)
        folder = export_native_c64(project, output, authorized=True)
        artifact_type = "native_c64_6510_vic_ii_sid_cc65_prg_source"
        digest = project.content_digest
    else:
        project = compile_native_desktop(world, source, target, authorized=True)
        folder = export_native_desktop_source(project, output, authorized=True)
        artifact_type = "native_desktop_sdl2_c11_source"
        digest = project.content_digest
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
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(_NATIVE), required=True)
    parser.add_argument("--basis", required=True, help="catalogued historical basis")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--seed", type=int, required=True)
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
    args = parser.parse_args()
    result = build_game(
        target=args.target, basis=args.basis, project_id=args.project_id,
        title=args.title, seed=args.seed, width=args.width, height=args.height,
        levels=args.levels, collectibles=args.collectibles,
        hazards=args.hazards, health=args.health,
        rights_evidence=args.rights_evidence,
        creative_identity=tuple(args.identity), output=args.output,
        authorized=args.authorize_original_homebrew,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
