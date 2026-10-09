"""Produce and authenticate a real original 8086 DOS .COM maze-game binary."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.dos_native_export import compile_native_dos, export_native_dos
from skeleton.ai.game_builder.dos_memory_replay import export_dos_replay
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def generate_source(output: Path) -> dict[str, object]:
    world = generate_playable_world(GameBuildIntent(
        project_id="original-8086-star-trek", title="Original DOS Star Trails",
        subtitle="Authentic BIOS and CGA/VGA text game", seed=808610,
        width=19, height=17, levels=3, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="arcade",
    ), authorized=True)
    original = HomebrewSource(
        project_id=world.intent.project_id, platform_id="dos_ega",
        rights_basis="project_owned", evidence_sha256=world.digest,
        creative_identity=("original star trails", "original obstacles", "new retro text aesthetics"),
    )
    project = compile_native_dos(world, original, authorized=True)
    folder = export_native_dos(project, output, authorized=True)
    export_dos_replay(world, folder / "original-dos-replay.json")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["world_digest"] != world.digest or manifest["executable_built"] is not False:
        raise RuntimeError("world identity or unverified native build assertion")
    return {"source_path": str(folder), "world_digest": world.digest,
            "native_source_digest": project.content_digest,
            "replay_digest": manifest["replay_digest"], "executable_compiled": False}


def verify_executable(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    # .COM is a raw DOS executable with no PE/MZ header and 100h load origin.
    if not 256 < len(data) <= 0xFF00:
        raise ValueError("8086 COM image out of DOS 64KiB segment budget")
    if not data.startswith(b"\x0E\x1F\xB8\x03\x00\xCD\x10"):
        raise ValueError("expected real 8086 CS->DS init and BIOS text-mode startup")
    if data.count(b"SKELDOSSTATE") != 1:
        raise ValueError("missing or duplicate real-mode state trace symbol table")
    for opcode, meaning in (
        (b"\xB8\x00\xB8\x8E\xC0", "IBM text-mode ES segment setup"),
        (b"\xCD\x16", "BIOS keyboard service"),
        (b"\xCD\x21", "DOS process exit"),
        (b"ORIGINAL HOMEBREW", "original game HUD"),
        (b"SKELDOS1", "original source signature"),
    ):
        if opcode not in data:
            raise ValueError(f"missing native DOS instruction or origin: {meaning}")
    return {
        "format": "8086_dos_com_raw",
        "target": "dos_vga",
        "load_origin": 0x100,
        "bytes": len(data),
        "sha256": sha256(data).hexdigest(),
        "real_8086_program_header_verified": True,
        "keyboard_bios_and_video_memory_verified_by_opcodes": True,
        "dos_emulator_playthrough_verified": False,
        "original_hardware_verified": False,
        "distribution_approved": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--emit", type=Path, metavar="NEW_DIRECTORY")
    group.add_argument("--verify-com", type=Path, metavar="COM_BINARY")
    args = ap.parse_args()
    result = generate_source(args.emit) if args.emit is not None else verify_executable(args.verify_com)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
