"""Build-stage orchestration and byte-level verification for original SMS/GG games.

The GitHub workflow invokes this after running a real SDCC/makesms toolchain.
No game ROM, proprietary SDK or distribution authorization is bundled here.
A valid cartridge header is not equivalent to a playable game.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from skeleton.ai.game_builder.native_game_cli import build_game
from skeleton.ai.game_builder.sega_8bit_rom import validate_rom_file


_TARGETS = {"sega_master_system": "sms", "sega_game_gear": "gg"}
_SHA = re.compile(r"^[0-9a-f]{64}$")


def emit(target: str, output: Path, authorship_file: Path) -> dict[str, object]:
    if target not in _TARGETS:
        raise ValueError("unsupported real Z80 console target")
    if not authorship_file.is_file() or authorship_file.is_symlink():
        raise ValueError("original author evidence must be an ordinary local file")
    proof = build_game(
        target=target,
        basis="bandai_wonderswan",
        project_id="skeleton-original-sega-evolution",
        title="Original Stardust Exploration",
        seed=198701,
        width=17,
        height=15,
        levels=3,
        collectibles=3,
        hazards=4,
        health=4,
        rights_evidence=authorship_file,
        creative_identity=(
            "independently created star puzzles",
            "original grid and constellation drawing",
            "fresh game rules and level arrangements",
        ),
        output=output,
        authorized=True,
    )
    if any(proof.get(flag) is not False for flag in (
        "native_binary_built", "emulator_verified", "physical_hardware_verified",
        "rights_independently_verified", "distribution_licensed",
    )):
        raise ValueError("generated source forged verification")
    return proof


def verify(
    target: str, directory: Path, rom: Path, *,
    toolchain_revision: str,
) -> dict[str, object]:
    """Verify *actual* bytes, not just strings in a source generation report."""
    if target not in _TARGETS:
        raise ValueError("unknown emulator/console hardware target")
    if not isinstance(toolchain_revision, str) or not _SHA.fullmatch(toolchain_revision):
        raise ValueError("exact toolchain revision is required")
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("expected ordinary generated source directory")
    expected = {"game.c", "Makefile", "manifest.json"}
    if not expected.issubset({path.name for path in directory.iterdir()}):
        raise ValueError("generated source project incomplete")
    parts = []
    for filename in ("game.c", "Makefile", "manifest.json"):
        path = directory / filename
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise ValueError("source input missing, symlinked or oversized")
        parts.append(path.read_bytes())
    source_digest = sha256(b"\0".join(parts)).hexdigest()
    manifest = json.loads(parts[2])
    if not isinstance(manifest, dict):
        raise ValueError("native source manifest must be a JSON object")
    if (
        manifest.get("schema") != "skeleton.game_builder.native_sega8_source.v1"
        or manifest.get("platform") != target
        or manifest.get("target_rom_suffix") != _TARGETS[target]
        or not isinstance(manifest.get("world_digest"), str)
        or not _SHA.fullmatch(manifest["world_digest"])
        or not isinstance(manifest.get("reference_safe_replay_digest"), str)
        or not _SHA.fullmatch(manifest["reference_safe_replay_digest"])
    ):
        raise ValueError("native console project identity or replay invalid")
    for field in (
        "binary_compiled", "emulator_playthrough_verified",
        "physical_hardware_verified", "release_approved",
        "distribution_licensed", "third_party_game_or_firmware_redistributed",
    ):
        if manifest.get(field) is not False:
            raise ValueError(f"pre-build manifest has forged claim: {field}")
    if rom.suffix != "." + _TARGETS[target]:
        raise ValueError("native ROM extension is inconsistent with requested console")
    measured = validate_rom_file(rom, target)
    return {
        "schema": "skeleton.game_builder.sega8_actual_compilation_evidence.v1",
        "target": target,
        "original_world_digest": manifest["world_digest"],
        "reference_safe_replay_digest": manifest["reference_safe_replay_digest"],
        "original_project_id": manifest.get("project_id"),
        "source_sha256": source_digest,
        "rom_sha256": measured["sha256"],
        "rom_size": measured["bytes"],
        "toolchain_revision": toolchain_revision,
        "native_rom_compiled": True,
        "rom_header_checksum_verified": measured["native_rom_checksum_verified"],
        "emulator_playthrough_verified": False,
        "physical_hardware_verified": False,
        "release_approved": False,
        "rights_independently_verified": False,
        "distribution_licensed": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit", type=Path)
    mode.add_argument("--verify-rom", type=Path)
    ap.add_argument("--target", choices=sorted(_TARGETS), required=True)
    ap.add_argument("--author-evidence", type=Path)
    ap.add_argument("--source-dir", type=Path)
    ap.add_argument("--toolchain-revision")
    ap.add_argument("--receipt-out", type=Path)
    args = ap.parse_args()
    if args.emit is not None:
        if args.author_evidence is None:
            ap.error("--author-evidence required with --emit")
        receipt = emit(args.target, args.emit, args.author_evidence)
    else:
        if args.source_dir is None or args.toolchain_revision is None:
            ap.error("--source-dir and --toolchain-revision required with --verify-rom")
        receipt = verify(
            args.target, args.source_dir, args.verify_rom,
            toolchain_revision=args.toolchain_revision,
        )
    if args.receipt_out is not None:
        if args.receipt_out.exists() or args.receipt_out.is_symlink():
            raise FileExistsError(str(args.receipt_out))
        with args.receipt_out.open("x", encoding="utf-8") as out:
            json.dump(receipt, out, indent=2, sort_keys=True)
            out.write("\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
