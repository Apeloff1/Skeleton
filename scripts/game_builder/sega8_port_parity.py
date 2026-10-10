"""Fail-closed cross-console port equivalence for original SMS/Game Gear games.

Consumes only independently produced build/gameplay receipts and manifests
from CI. It never substitutes one console's native binary for another,
imports commercial ROMs, grants publication rights or asserts full emulation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from skeleton.ai.game_builder.native_release_intake import _json, _read_bounded, NativeIntakeError

_TARGETS = {"sega_master_system": "sms", "sega_game_gear": "gg"}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_RECEIPT = 4 * 1024 * 1024


class Sega8PortParityError(ValueError):
    """Distinct native ports lost original world or review provenance."""


def _read(path: Path) -> dict[str, Any]:
    try:
        data = _json(_read_bounded(path, max_bytes=MAX_RECEIPT), "original Sega cross-port evidence")
    except (NativeIntakeError, OSError, UnicodeDecodeError, ValueError) as exc:
        raise Sega8PortParityError("receipt is linked, invalid, or beyond evidence budget") from exc
    if not isinstance(data, dict):
        raise Sega8PortParityError("receipt must be a canonical JSON object")
    return data


def _select(root: Path, target: str, leaf: str) -> dict[str, Any]:
    """Locate exactly one expected artifact, rejecting namespace ambiguity."""
    directory = root / ("original-sega8-source-and-hash-evidence-" + target)
    if directory.is_symlink() or not directory.is_dir():
        raise Sega8PortParityError("missing independently built target artifact directory")
    matches = tuple(p for p in directory.rglob(leaf) if p.is_file() or p.is_symlink())
    if len(matches) != 1:
        raise Sega8PortParityError(f"missing/ambiguous {target} {leaf}")
    selected = matches[0]
    if any(parent.is_symlink() for parent in selected.parents
           if parent != directory and directory in parent.parents):
        raise Sega8PortParityError("artifact ancestry may not contain linked folders")
    return _read(selected)


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise Sega8PortParityError(f"invalid {label} digest")
    return value



_REPRO_FALSE = (
    "two_compiler_executions_independently_verified",
    "source_rights_independently_verified",
    "gameplay_execution_verified",
    "real_console_hardware_verified",
    "developer_toolchain_authenticity_proven",
    "publication_licensed",
)


def _check_rebuilt_provenance(
    receipt: dict[str, Any], compilation: dict[str, Any],
    manifest: dict[str, Any], target: str,
) -> None:
    """Ensure the release candidate and twice-checked cartridge are identical."""
    if receipt.get("schema") != "skeleton.game_builder.sega_reproducibility.v1":
        raise Sega8PortParityError("required double-ROM comparison evidence absent")
    for field in _REPRO_FALSE:
        if receipt.get(field) is not False:
            raise Sega8PortParityError("ROM reproducibility cannot grant hardware/legal approval")
    for field in (
        "checked_two_distinct_artifact_paths", "exact_rom_bytes_match",
        "source_and_authorship_digests_match",
    ):
        if receipt.get(field) is not True:
            raise Sega8PortParityError("missing actual two-file native ROM comparison")
    expected = {
        "target": target,
        "source_sha256": compilation["source_sha256"],
        "author_declaration_sha256": manifest["source_rights_evidence_sha256"],
        "world_sha256": manifest["world_digest"],
        "reference_replay_sha256": manifest["reference_safe_replay_digest"],
        "toolchain_git_revision": compilation.get("toolchain_revision"),
        "cartridge_sha256": compilation["rom_sha256"],
        "cartridge_bytes": 32768,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise Sega8PortParityError(
                "reproducible ROM evidence not bound to the compiled game: " + key
            )
    _sha(receipt.get("comparison_sha256"), "reproducible ROM receipt")
    core = {key: value for key, value in receipt.items() if key != "comparison_sha256"}
    try:
        expected_digest = sha256(json.dumps(
            core, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise Sega8PortParityError("invalid reproducible ROM receipt values") from exc
    if receipt["comparison_sha256"] != expected_digest:
        raise Sega8PortParityError("reproducible ROM receipt digest does not match facts")
    fields = set(expected) | {
        "schema", "comparison_sha256",
        "checked_two_distinct_artifact_paths", "exact_rom_bytes_match",
        "source_and_authorship_digests_match", *_REPRO_FALSE,
    }
    if set(receipt) != fields:
        raise Sega8PortParityError("unreviewed additional field in ROM comparison evidence")


def verify_ports(root: Path) -> dict[str, object]:
    if root.is_symlink() or not root.is_dir():
        raise Sega8PortParityError("existing ordinary evidence root required")
    records: dict[str, dict[str, dict[str, Any]]] = {}
    for target, ext in _TARGETS.items():
        meta = _select(root, target, "manifest.json")
        compile_evidence = _select(root, target, target+"-compilation-evidence.json")
        host = _select(root, target, target+"-host-gameplay-receipt.json")
        boot = _select(root, target, target+"-real-z80-boot.json")
        reproducible = _select(root, target, target+"-reproducibility.json")
        if (meta.get("schema") != "skeleton.game_builder.native_sega8_source.v1"
            or meta.get("platform") != target or meta.get("target_rom_suffix") != ext):
            raise Sega8PortParityError("native platform manifest mismatch")
        if (
            compile_evidence.get("schema")
            != "skeleton.game_builder.sega8_actual_compilation_evidence.v1"
            or compile_evidence.get("target") != target
            or compile_evidence.get("real_rom_structure_verified") is not True
            or compile_evidence.get("rom_header_checksum_verified") is not True
        ):
            raise Sega8PortParityError("invalid independently measured native ROM")
        if (
            host.get("schema") != "skeleton.game_builder.sega8_c_gameplay_differential.v1"
            or host.get("target") != target
            or host.get("native_game_c_compiled_and_executed_on_host") is not True
            or host.get("all_level_completion_verified") is not True
            or host.get("original_score_and_screen_state_verified") is not True
            or host.get("original_companion_rank_progression_verified") is not True
        ):
            raise Sega8PortParityError("not all original C-gameplay steps accepted")
        if (
            boot.get("schema") != "skeleton.game_builder.sega8_real_z80_boot_smoke.v1"
            or boot.get("target") != target
            or boot.get("hardware_boot_smoke_verified") is not True
            or boot.get("game_hero_rendered") is not True
            or boot.get("original_companion_rendered") is not True
            or boot.get("zero_score_hud_verified") is not True
        ):
            raise Sega8PortParityError("actual compiled cartridge startup was not observed")
        # Each source has different typed false-claim envelopes. Missing,
        # non-boolean, or truthful-looking string fields are not acceptable:
        # a forged release gate must fail closed, not merely reject JSON true.
        unapproved = (
            (meta, ("binary_compiled", "emulator_playthrough_verified",
                    "physical_hardware_verified", "release_approved",
                    "distribution_licensed",
                    "third_party_game_or_firmware_redistributed")),
            (compile_evidence, ("native_rom_compiled", "emulator_playthrough_verified",
                                "physical_hardware_verified", "release_approved",
                                "distribution_licensed", "rights_independently_verified")),
            (host, ("native_z80_rom_executed", "full_console_emulator_playthrough_verified",
                    "physical_hardware_verified", "release_approved",
                    "rights_independently_verified")),
            (boot, ("entire_game_playthrough_verified",
                    "independent_cycle_exact_emulator_verified",
                    "physical_hardware_verified", "distribution_licensed",
                    "release_approved")),
        )
        for receipt, fields in unapproved:
            for key in fields:
                if receipt.get(key) is not False:
                    raise Sega8PortParityError(
                        f"native port evidence has an unreviewed or missing {key} claim"
                    )
        _check_rebuilt_provenance(reproducible, compile_evidence, meta, target)
        source = _sha(compile_evidence.get("source_sha256"), "source")
        rom = _sha(compile_evidence.get("rom_sha256"), "ROM")
        if (
            compile_evidence.get("original_world_digest") != meta.get("world_digest")
            or compile_evidence.get("reference_safe_replay_digest")
               != meta.get("reference_safe_replay_digest")
            or compile_evidence.get("source_rights_evidence_sha256")
               != meta.get("source_rights_evidence_sha256")
            or host.get("source_content_digest") != source
            or host.get("world_digest") != meta.get("world_digest")
            or boot.get("rom_sha256") != rom
        ):
            raise Sega8PortParityError("source, replay, rights or ROM hash chain mismatch")
        if (
            type(host.get("original_levels_verified")) is not int
            or type(host.get("original_controller_actions_verified")) is not int
            or host["original_levels_verified"] != meta.get("levels")
            or host["original_controller_actions_verified"] <= 0
        ):
            raise Sega8PortParityError("gameplay acceptance proof has invalid action counts")
        _sha(meta.get("world_digest"), "world")
        _sha(meta.get("reference_safe_replay_digest"), "safe replay")
        _sha(meta.get("source_rights_evidence_sha256"), "rights evidence")
        records[target] = {
            "manifest": meta, "compile": compile_evidence, "host": host, "boot": boot,
            "reproducibility": reproducible,
        }

    sms = records["sega_master_system"]
    gg = records["sega_game_gear"]
    identity = ("project_id", "world_digest", "reference_safe_replay_digest",
                "source_rights_evidence_sha256", "original_color_theme",
                "levels", "width", "height", "title")
    for key in identity:
        if sms["manifest"].get(key) != gg["manifest"].get(key):
            raise Sega8PortParityError(f"native ports diverged on original {key}")
    if sms["compile"].get("rom_sha256") == gg["compile"].get("rom_sha256"):
        raise Sega8PortParityError("different consoles unexpectedly share identical binary")
    for field in (
        "original_controller_actions_verified", "original_levels_verified",
    ):
        if sms["host"].get(field) != gg["host"].get(field):
            raise Sega8PortParityError("different hardware ports accepted different gameplay")
    if sms["manifest"].get("target_rom_suffix") == gg["manifest"].get("target_rom_suffix"):
        raise Sega8PortParityError("different native ports share incorrect ROM extension")
    result = {
        "schema": "skeleton.game_builder.original_sega8_crossport_parity.v1",
        "world_digest": sms["manifest"]["world_digest"],
        "source_reference_digest": sms["manifest"]["reference_safe_replay_digest"],
        "host_reference_sha256_by_platform": {
            target: _sha(records[target]["host"].get("authoritative_reference_sha256"),
                         target+" host reference")
            for target in sorted(_TARGETS)
        },
        "original_controller_actions_verified_per_platform":
            sms["host"]["original_controller_actions_verified"],
        "native_platforms_checked": sorted(_TARGETS),
        "gameplay_parity_verified": True,
        "independent_native_rom_formats_verified": True,
        "real_z80_startup_checked_per_platform": True,
        "native_cartridge_rebuild_byte_equality_checked_per_platform": True,
        "full_native_z80_gameplay_replay_verified": False,
        "physical_hardware_verified": False,
        "rights_independently_verified": False,
        "release_approved": False,
    }
    result["receipt_sha256"] = sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-root", type=Path, required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = verify_ports(args.evidence_root)
    if args.output is not None:
        if args.output.exists() or args.output.is_symlink():
            raise FileExistsError(str(args.output))
        with args.output.open("x", encoding="utf-8") as fp:
            json.dump(result, fp, indent=2, sort_keys=True)
            fp.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
