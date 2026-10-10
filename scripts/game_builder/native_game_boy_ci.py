"""CI fixture: compile a real world-derived DMG cartridge, not a generic demo."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.game_boy_native_export import (
    compile_native_game_boy, export_native_game_boy,
)
from skeleton.ai.game_builder.game_boy_memory_replay import export_game_boy_memory_replay
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource

NINTENDO_LOGO = bytes.fromhex(
    "CEED6666CC0D000B03730083000C000D"
    "0008111F8889000EDCCC6EE6DDDDD999"
    "BBBB67636E0EECCCDDDC999FBBB9333E"
)


def build_source(directory: Path) -> dict[str, object]:
    intent = GameBuildIntent(
        project_id="skeleton-gb-original-cart", title="Original Maze Stars",
        subtitle="Native hardware DMG homebrew", seed=910762,
        width=17, height=15, levels=3, collectibles_per_level=3,
        hazards_per_level=5, starting_health=4, theme="space",
    )
    world = generate_playable_world(intent, authorized=True)
    source = HomebrewSource(
        project_id=intent.project_id,
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",
        evidence_sha256=world.digest,
        creative_identity=("original star maze", "chipped tile palette", "collect-and-exit"),
    )
    project = compile_native_game_boy(world, source, authorized=True)
    folder = export_native_game_boy(project, directory, authorized=True)
    meta = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert meta["world_digest"] == world.digest
    assert meta["rom_compiled"] is False
    export_game_boy_memory_replay(world, folder / "verification-route.json")
    return {
        "source_path": str(folder),
        "source_digest": project.content_digest,
        "world_digest": world.digest,
        "safe_reference_moves": meta["safe_reference_moves"],
        "hardware_replay_route": str(folder / "verification-route.json"),
        "compile_claim": False,
    }


def verify_rom(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if len(data) < 0x8000 or len(data) % 0x4000 != 0:
        raise ValueError("Game Boy ROM has invalid bank-sized payload")
    if data[0x104:0x134] != NINTENDO_LOGO:
        raise ValueError("Game Boy cartridge header logo invalid")
    if data[0x100] != 0xC3:
        raise ValueError("Game Boy cartridge entry must be a JP instruction")
    if data[0x147] != 0:
        raise ValueError("only simple original ROM-only MBC-free cartridge supported")
    header_checksum = 0
    for byte in data[0x134:0x14D]:
        header_checksum = (header_checksum - byte - 1) & 255
    if data[0x14D] != header_checksum:
        raise ValueError("Game Boy header checksum invalid")
    return {
        "artifact": path.name,
        "target": "nintendo_game_boy",
        "bytes": len(data),
        "sha256": sha256(data).hexdigest(),
        "native_dmg_header_verified": True,
        "emulator_playthrough_verified": False,
        "physical_device_verified": False,
        "release_approved": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.add_mutually_exclusive_group(required=True)
    args.add_argument("--emit", type=Path, metavar="NEW_DIRECTORY")
    args.add_argument("--verify-rom", type=Path, metavar="COMPILED_GB_ROM")
    options = parser.parse_args()
    print(json.dumps(
        build_source(options.emit) if options.emit else verify_rom(options.verify_rom),
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
