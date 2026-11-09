"""CI acceptance for real, world-specific NES NROM cartridge generation."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.native_release_intake import _read_bounded

from skeleton.ai.game_builder.nes_native_export import (
    compile_native_nes, export_native_nes,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def generate(destination: Path) -> dict[str, object]:
    intent = GameBuildIntent(
        project_id="skeleton-original-nes-practice",
        title="Original Tiny Constellation", subtitle="NROM 6502 playable game",
        seed=73018, width=19, height=17, levels=3,
        collectibles_per_level=3, hazards_per_level=3,
        starting_health=4, theme="space",
    )
    world = generate_playable_world(intent, authorized=True)
    source = HomebrewSource(
        project_id=intent.project_id, platform_id="bandai_wonderswan",
        rights_basis="project_owned", evidence_sha256=world.digest,
        creative_identity=("original maze navigation", "pixel constellations", "collect-and-exit"),
    )
    project = compile_native_nes(world, source, authorized=True)
    folder = export_native_nes(project, destination, authorized=True)
    meta = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert meta["world_digest"] == world.digest
    assert not meta["cartridge_built"]
    return {"source_directory": str(folder), "source_digest": project.content_digest,
            "world_digest": world.digest, "safe_moves": meta["reference_safe_moves"],
            "native_cartridge_compiled": False}


def inspect_rom(path: Path) -> dict[str, object]:
    # Read the actual ROM once through no-follow, bounded, regular-file
    # descriptors. A preliminary is_file()/read_bytes() enables path swapping.
    blob = _read_bounded(path, max_bytes=16+32768+8192)
    if len(blob) != 16 + 32768 + 8192:
        raise ValueError("NROM-256 ROM has wrong PRG/CHR length")
    if blob[:16] != bytes((0x4E, 0x45, 0x53, 0x1A, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)):
        raise ValueError("NROM-256 iNES mapper/header mismatch")
    reset_vector = int.from_bytes(blob[16 + 0x7FFC:16 + 0x7FFE], "little")
    if reset_vector < 0x8000:
        raise ValueError("invalid NES reset vector")
    # An iNES signature is not evidence of executable 6502 game code.
    # Reset and interrupt vectors must reference actual file-backed PRG.
    prg = blob[16:16+32768]
    nmi = int.from_bytes(prg[0x7FFA:0x7FFC], "little")
    irq = int.from_bytes(prg[0x7FFE:0x8000], "little")
    for vector in (reset_vector,nmi,irq):
        if not 0x8000 <= vector <= 0xFFFF:
            raise ValueError("NES reset/NMI/IRQ vector outside mapped executable PRG")
        if prg[vector-0x8000] in (0x00,0xFF):
            raise ValueError("NES vector enters empty or unsupported startup bytes")
    if not any(blob[16 + 32768:]):
        raise ValueError("CHR contains no original tiles")
    return {
        "target": "nintendo_famicom",
        "filename": path.name,
        "bytes": len(blob),
        "sha256": sha256(blob).hexdigest(),
        "ines_header_verified": True,
        "mapper_0_prg_chr_verified": True,
        "reset_vector": reset_vector,
        "nmi_vector": nmi,
        "irq_vector": irq,
        "real_machine_code_structurally_inspected": True,
        "compiler_execution_independently_attested": False,
        "emulator_playthrough_verified": False,
        "hardware_verified": False,
        "release_approved": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--emit", type=Path, metavar="NEW_SOURCE_DIRECTORY")
    options.add_argument("--verify-rom", type=Path, metavar="NES_CARTRIDGE")
    args = parser.parse_args()
    print(json.dumps(generate(args.emit) if args.emit is not None
                     else inspect_rom(args.verify_rom), sort_keys=True))


if __name__ == "__main__":
    main()
