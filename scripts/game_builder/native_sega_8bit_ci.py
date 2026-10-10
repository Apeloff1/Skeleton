"""Build-stage orchestration and byte-level verification for original SMS/GG games.

The GitHub workflow invokes this after running a real SDCC/makesms toolchain.
No game ROM, proprietary SDK or distribution authorization is bundled here.
A valid cartridge header is not equivalent to a playable game.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.playable_simulation import demonstrate_solvable
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.sega_8bit_native_export import (
    compile_native_sega_8bit, export_native_sega_8bit,
)
from skeleton.ai.game_builder.sega_8bit_rom import validate_rom_file
from skeleton.ai.game_builder.native_release_intake import _open_directory, _read_bounded, _json


_TARGETS = {"sega_master_system": "sms", "sega_game_gear": "gg"}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_GIT_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def emit(target: str, output: Path, authorship_file: Path) -> dict[str, object]:
    if target not in _TARGETS:
        raise ValueError("unsupported real Z80 console target")
    try:
        declared_author_bytes = _read_bounded(Path(authorship_file), max_bytes=8*1024*1024)
    except (ValueError, OSError) as exc:
        raise ValueError("original author evidence must be an ordinary, private, bounded local file") from exc
    author_reference = sha256(declared_author_bytes).hexdigest()
    intent = GameBuildIntent(
        project_id="skeleton-original-sega-evolution",
        title="Original Stardust Exploration",
        subtitle="Self-authored console game, not commercial-content replication",
        seed=198701, width=17, height=15, levels=3,
        collectibles_per_level=3, hazards_per_level=4,
        starting_health=4, theme="space",
    )
    world = generate_playable_world(intent, authorized=True)
    rights = HomebrewSource(
        project_id=intent.project_id,
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",
        evidence_sha256=author_reference,
        creative_identity=(
            "independently created star puzzles",
            "original grid and constellation drawing",
            "fresh game rules and level arrangements",
        ),
    )
    # This explicit backend is in addition to the independently written Z80
    # assembly SMS adapter. The generic native CLI is free to choose either.
    project = compile_native_sega_8bit(world, rights, target, authorized=True)
    folder = export_native_sega_8bit(project, output, authorized=True)
    replay = demonstrate_solvable(world, authorized=True)
    proof = {
        "schema": "skeleton.game_builder.native_sega8_original_source_receipt.v1",
        "target": target, "output_directory": str(folder),
        "source_content_digest": project.content_digest,
        "world_digest": world.digest,
        "winning_replay_digest": replay.digest,
        "rights_evidence_sha256": author_reference,
        "native_binary_built": False,
        "emulator_verified": False,
        "physical_hardware_verified": False,
        "rights_independently_verified": False,
        "distribution_licensed": False,
    }
    if any(proof.get(flag) is not False for flag in (
        "native_binary_built", "emulator_verified", "physical_hardware_verified",
        "rights_independently_verified", "distribution_licensed",
    )):
        raise ValueError("generated source forged verification")
    return proof


def verify(
    target: str, directory: Path, rom: Path, *,
    toolchain_revision: str, expected_source_sha256: str | None = None,
    expected_authorship_sha256: str | None = None,
) -> dict[str, object]:
    """Verify *actual* bytes, not just strings in a source generation report."""
    if target not in _TARGETS:
        raise ValueError("unknown emulator/console hardware target")
    if not isinstance(toolchain_revision, str) or not _GIT_REVISION.fullmatch(toolchain_revision):
        raise ValueError("exact 40-hex SHA-1 or 64-hex SHA-256 Git revision is required")
    if expected_source_sha256 is not None and (
        not isinstance(expected_source_sha256, str)
        or not _SHA.fullmatch(expected_source_sha256)
    ):
        raise ValueError("independently supplied source digest must be SHA-256")
    if expected_authorship_sha256 is not None and (
        not isinstance(expected_authorship_sha256, str)
        or not _SHA.fullmatch(expected_authorship_sha256)
    ):
        raise ValueError("expected authorship evidence must be a SHA-256 digest")
    rootfd = _open_directory(directory)
    try:
        expected = {"game.c", "Makefile", "manifest.json"}
        present = set(os.listdir(rootfd))
        if not expected.issubset(present) or present - expected - {"build"}:
            raise ValueError("generated source project has missing or unreviewed extra files")
        if "build" in present:
            build_meta = os.stat("build", dir_fd=rootfd, follow_symlinks=False)
            if not stat.S_ISDIR(build_meta.st_mode):
                raise ValueError("compiler output directory cannot be linked or replaced")
        parts = [
            _read_bounded(Path(filename), max_bytes=1024*1024, root_fd=rootfd)
            for filename in ("game.c", "Makefile", "manifest.json")
        ]
    finally:
        os.close(rootfd)
    source_digest = sha256(b"\0".join(parts)).hexdigest()
    if expected_source_sha256 is not None and source_digest != expected_source_sha256:
        raise ValueError("generated source has changed since independently pinned evidence")
    manifest = _json(parts[2], "native Sega source")
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
    if (
        not isinstance(manifest.get("source_rights_evidence_sha256"), str)
        or not _SHA.fullmatch(manifest["source_rights_evidence_sha256"])
        or not isinstance(manifest.get("project_id"), str)
        or not manifest["project_id"]
        or manifest.get("toolchain_license_review_required") is not True
    ):
        raise ValueError("source rights and third-party toolchain legal evidence incomplete")
    if (
        expected_authorship_sha256 is not None
        and manifest["source_rights_evidence_sha256"] != expected_authorship_sha256
    ):
        raise ValueError("authorship evidence changed since source review")
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
        "source_digest_matches_expected": expected_source_sha256 is not None,
        "source_digest_independently_attested": False,  # Caller-provided hash is not trusted external authority.
        "source_rights_evidence_sha256": manifest["source_rights_evidence_sha256"],
        "source_authorship_hash_matches_expected": expected_authorship_sha256 is not None,
        "source_rights_independently_proven": False,
        "rom_sha256": measured["sha256"],
        "rom_size": measured["bytes"],
        "toolchain_revision": toolchain_revision,
        "toolchain_revision_hash_algorithm": "git-sha1" if len(toolchain_revision) == 40 else "git-sha256",
        "toolchain_source_authenticated": False,  # Exact Git ID is not a signed supply-chain attestation.
        "native_rom_compiled": False,  # Byte verification does not witness an SDCC execution.
        "real_rom_structure_verified": True,
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
    ap.add_argument("--expected-source-sha256")
    ap.add_argument("--expected-authorship-sha256")
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
            expected_source_sha256=args.expected_source_sha256,
            expected_authorship_sha256=args.expected_authorship_sha256,
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
