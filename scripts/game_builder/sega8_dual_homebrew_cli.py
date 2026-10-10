"""Create both *original source-only* Sega 8-bit ports from one owned world.

Unlike a superficial platform catalog, each exported directory contains
buildable original devkitSMS C, a native Makefile, and its independent source
manifest and complete safe gameplay route. This action NEVER builds, bundles,
or distributes a commercial ROM, BIOS, proprietary artwork, or game cartridge.

The final canonical portability receipt is written only after both targets
exist and agree on the original game world, solution, rights evidence, and
hardware-specific visual design; all external hardware/legal checks stay false.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.native_release_intake import _json, _read_bounded
from skeleton.ai.game_builder.playable_world import GameBuildIntent
from scripts.game_builder.native_sega_8bit_ci import emit

_TARGETS = ("sega_master_system", "sega_game_gear")
_SUPPORTED = ("standard", "full_campaign", "custom_original")
_ALLOWED_CONFIG = frozenset((
    "project_id", "title", "subtitle", "seed", "theme", "levels",
    "width", "height", "collectibles_per_level", "hazards_per_level",
    "starting_health",
))
_REQUIRED_CONFIG = frozenset(("project_id", "title", "seed", "theme", "levels"))


class Sega8DualPortError(ValueError):
    """Source-only portability custody, identity or file boundary failure."""


def _configuration(path: Path | None, profile: str) -> dict[str, Any] | None:
    if profile not in _SUPPORTED:
        raise Sega8DualPortError("unsupported original native hardware profile")
    if path is None:
        if profile == "custom_original":
            raise Sega8DualPortError("custom-original dual port requires author-configured game JSON")
        return None
    if profile != "custom_original":
        raise Sega8DualPortError("fixed campaign cannot accept unreviewed custom configuration")
    try:
        config = _json(
            _read_bounded(path, max_bytes=16384),
            "original Sega homebrew project configuration",
        )
    except (ValueError, OSError) as exc:
        raise Sega8DualPortError("original project configuration must be a bounded ordinary JSON file") from exc
    if (
        not isinstance(config, dict)
        or not _REQUIRED_CONFIG.issubset(config)
        or set(config) - _ALLOWED_CONFIG
    ):
        raise Sega8DualPortError("custom original game configuration has missing or unsafe fields")
    details = {
        "subtitle": "Independent original homebrew game",
        "width": 17, "height": 15,
        "collectibles_per_level": 3, "hazards_per_level": 4,
        "starting_health": 4,
    }
    details.update(config)
    try:
        intent = GameBuildIntent(**details)
    except (ValueError, TypeError) as exc:
        raise Sega8DualPortError("original game configuration violates world limits") from exc
    if intent.width > 19 or intent.height > 15:
        raise Sega8DualPortError("original game exceeds shared SMS/GG hardware viewport")
    return config


def _source_fingerprint(project_dir: Path) -> str:
    # Reopen generated artifacts through the shared no-follow bounded reader,
    # rather than trusting a mutable string supplied by the emitter.
    return sha256(b"\0".join(
        _read_bounded(project_dir / leaf, max_bytes=1024*1024)
        for leaf in ("game.c", "Makefile", "manifest.json")
    )).hexdigest()


def export_dual_original(
    output: Path, authorship: Path, *,
    profile: str = "standard",
    game_config_path: Path | None = None,
) -> dict[str, object]:
    config = _configuration(game_config_path, profile)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"destination must be a fresh original game project: {output}")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise Sega8DualPortError("use a pre-existing ordinary parent directory")
    # Authentication of the private authorship file is performed by emit().
    # We never place its bytes in either output package or manifest.
    if not isinstance(authorship, Path):
        raise Sega8DualPortError("original authorship evidence path required")
    # Fresh directory is atomically claimed. In case a downstream export
    # fails, no final portability receipt is ever written; partial products
    # are not silently promoted to an accepted release.
    output.mkdir(mode=0o700, exist_ok=False)
    per_target: dict[str, dict[str, Any]] = {}
    core_fields = (
        "project_id", "world_digest", "reference_safe_replay_digest",
        "original_demo_solution_sha256", "original_color_theme",
        "game_gear_original_stage_rgb444_accents",
        "master_system_original_stage_rgb222_accents",
        "source_rights_evidence_sha256", "levels", "width", "height", "title",
    )
    shared: dict[str, Any] | None = None
    for target in _TARGETS:
        path = output / target
        source = emit(
            target, path, authorship,
            profile=profile, original_config=config,
            reference_out=output / (target + "-original-reference.json"),
        )
        manifest = _json(
            _read_bounded(path / "manifest.json", max_bytes=1024*1024),
            "original Sega generated world",
        )
        if not isinstance(manifest, dict):
            raise Sega8DualPortError("native source manifest is not an object")
        observed = {key: manifest.get(key) for key in core_fields}
        if shared is None:
            shared = observed
        elif shared != observed:
            raise Sega8DualPortError("original world, rights, solution or palette diverged across consoles")
        if (
            manifest.get("platform") != target
            or manifest.get("source_platform") != target
            or source.get("native_source_authoring_platform") != target
            or source.get("third_party_console_origin_claimed") is not False
        ):
            raise Sega8DualPortError(
                "native original game must not claim a third-party console as its source"
            )
        digest = _source_fingerprint(path)
        if digest != source["source_content_digest"]:
            raise Sega8DualPortError("native project source changed during dual-port build")
        if (
            manifest.get("source_rights_evidence_sha256") != source.get("rights_evidence_sha256")
            or manifest.get("world_digest") != source.get("world_digest")
            or manifest.get("binary_compiled") is not False
            or manifest.get("distribution_licensed") is not False
            or manifest.get("release_approved") is not False
            or source.get("native_binary_built") is not False
        ):
            raise Sega8DualPortError("original rights/source statement was elevated or mismatched")
        per_target[target] = {
            "source_sha256": digest,
            "original_reference_sha256": sha256(_read_bounded(
                output / (target + "-original-reference.json"),
                max_bytes=4*1024*1024,
            )).hexdigest(),
            "native_source_created": True,
            "native_cartridge_compiled": False,
            "native_z80_gameplay_verified": False,
        }
    if per_target[_TARGETS[0]]["source_sha256"] == per_target[_TARGETS[1]]["source_sha256"]:
        raise Sega8DualPortError("separate native consoles unexpectedly got identical source bytes")
    assert shared is not None
    receipt: dict[str, object] = {
        "schema": "skeleton.game_builder.original_sega8_dual_port_source.v1",
        "profile": profile,
        "world_digest": shared["world_digest"],
        "project_id": shared["project_id"],
        "original_solution_sha256": shared["original_demo_solution_sha256"],
        "author_declaration_sha256": shared["source_rights_evidence_sha256"],
        "portability_identity_verified": True,
        "independently_generated_native_sources": per_target,
        "third_party_rom_or_firmware_included": False,
        "original_rights_independently_verified": False,
        "actual_native_rom_built": False,
        "full_hardware_emulator_verified": False,
        "physical_hardware_verified": False,
        "distribution_licensed": False,
        "release_approved": False,
    }
    receipt["receipt_sha256"] = sha256(json.dumps(
        receipt, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    with (output / "portability.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return receipt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--author-evidence", required=True, type=Path)
    ap.add_argument("--profile", choices=_SUPPORTED, default="standard")
    ap.add_argument("--original-config", type=Path)
    args = ap.parse_args()
    result = export_dual_original(
        args.output, args.author_evidence, profile=args.profile,
        game_config_path=args.original_config,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
