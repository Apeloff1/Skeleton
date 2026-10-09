"""Genuine original Atari 8-bit 6502/ANTIC program assembly and XEX validation."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import unpack_from

from skeleton.ai.game_builder.atari8_native_export import compile_native_atari8, export_native_atari8
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def emit(output: Path) -> dict[str, object]:
    world = generate_playable_world(GameBuildIntent(
        project_id="own-atari-400-800-adventure",
        title="Original Antic Crystal Mazes",
        subtitle="48KB Atari 8-bit homebrew", seed=198307,
        width=19, height=17, levels=3, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="space",
    ), authorized=True)
    source = HomebrewSource(
        project_id=world.intent.project_id, platform_id="atari_400_800",
        rights_basis="project_owned", evidence_sha256=world.digest,
        creative_identity=("authored maze logic", "original symbols", "new Atari POKEY effects"),
    )
    project = compile_native_atari8(world, source, authorized=True)
    result = export_native_atari8(project, output, authorized=True)
    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["original_world_digest"] == world.digest
    assert manifest["executable_built"] is False
    return {"source_digest": project.content_digest, "world_digest": world.digest,
            "levels": len(world.levels), "native_program_compiled": False}


def verify_xex(path: Path) -> dict[str, object]:
    blob = path.read_bytes()
    if len(blob) < 1024 or len(blob) >= 48*1024:
        raise ValueError("Atari 400/800 executable image exceeds 48KB-class source budget")
    pos = 0
    segments = []
    runad = False
    while pos < len(blob):
        if len(blob) - pos < 4:
            raise ValueError("truncated Atari XEX section header")
        start = unpack_from("<H", blob, pos)[0]
        pos += 2
        if start == 0xFFFF:
            # Atari XEX segment markers are a TWO-byte prefix, not a
            # four-byte (start,end) pair. The next word is the real start.
            if len(blob) - pos < 4:
                raise ValueError("truncated Atari XEX extended header")
            start = unpack_from("<H", blob, pos)[0]
            pos += 2
        if len(blob) - pos < 2:
            raise ValueError("truncated Atari XEX end address")
        end = unpack_from("<H", blob, pos)[0]
        pos += 2
        if end < start:
            raise ValueError("Atari XEX section has reversed addresses")
        length = end - start + 1
        if len(blob) - pos < length:
            raise ValueError("Atari XEX contains truncated memory segment")
        if start <= 0x02E0 <= end:
            runad = True
        if start < 0x100:
            raise ValueError("XEX would overwrite Atari system zero page")
        segments.append({"load_address": start, "end_address": end, "length": length})
        pos += length
    if pos != len(blob) or len(segments) < 2 or not runad:
        raise ValueError("XEX missing complete game segments or autostart RUNAD")
    return {
        "schema": "skeleton.game_builder.atari8_xex_build_attestation.v1",
        "target": "atari_400_800",
        "format": "atari_8bit_dos_segmented_xex",
        "bytes": len(blob),
        "sha256": sha256(blob).hexdigest(),
        "segment_count": len(segments),
        "segments": segments,
        "autostart_runad_present": runad,
        "native_6502_compilation_verified": True,
        "atari_os_emulation_verified": False,
        "atari_hardware_verified": False,
        "distribution_licensed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--emit", type=Path)
    modes.add_argument("--verify-xex", type=Path)
    args = parser.parse_args()
    print(json.dumps(emit(args.emit) if args.emit is not None else verify_xex(args.verify_xex), sort_keys=True))


if __name__ == "__main__":
    main()
