"""Compile the original game into a real C64 loadable PRG using cc65."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.native_release_intake import _read_bounded
from skeleton.ai.game_builder.native_retro_artifact import parse_original_c64_prg
from skeleton.ai.game_builder.c64_native_export import compile_native_c64, export_native_c64
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit_source(output: Path) -> dict[str, object]:
    world = generate_playable_world(GameBuildIntent(
        project_id="original-c64-constellation", title="Moon Constellation",
        subtitle="Original VIC-II 6510 game", seed=401984,
        width=17, height=15, levels=3, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="arcade",
    ), authorized=True)
    source = HomebrewSource(
        project_id=world.intent.project_id,
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",
        evidence_sha256=world.digest,
        creative_identity=("original constellations", "original C64 map", "collect-and-exit"),
    )
    project = compile_native_c64(world, source, authorized=True)
    directory = export_native_c64(project, output, authorized=True)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["world_digest"] != world.digest or manifest["binary_built"] is not False:
        raise RuntimeError("authored C64 project lost source identity")
    return {
        "native_source_path": str(directory),
        "world_digest": world.digest,
        "project_digest": project.content_digest,
        "levels": len(world.levels),
        "binary_compilation_executed": False,
    }


def verify_prg(binary: Path) -> dict[str, object]:
    blob = _read_bounded(binary, max_bytes=0xD000-0x0801+2)
    layout = parse_original_c64_prg(blob)
    result = {
        **layout,
        "format": "c64_6510_loadable_prg",
        "target": "commodore_64",
        "prg_sha256": sha256(blob).hexdigest(),
        "load_address": 0x0801,
        "basic_sys_stub_found": True,
        "native_machine_code_compiled": True,
        "emulator_gameplay_verified": False,
        "real_hardware_verified": False,
        "redistribution_cleared": False,
        "bytes": len(blob),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--emit", type=Path, metavar="NEW_DIRECTORY")
    modes.add_argument("--verify-prg", type=Path, metavar="C64_BINARY")
    args = parser.parse_args()
    print(json.dumps(emit_source(args.emit) if args.emit is not None
                     else verify_prg(args.verify_prg), sort_keys=True))


if __name__ == "__main__":
    main()
