"""Evidence-based cross-era target completion accounting.

Never infer real hardware support, distribution authorization or product
completion from a catalog row, emitted source file or unverified model
claim. Local CHIP-8 acceptance can produce a provenance-bound receipt,
but only an independently verified release may close a hardware target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any, Sequence

from skeleton.ai.runtime.game_platform_catalog import TARGETS, CATALOG_SHA256
from scripts.game.export_chip8 import (
    _original_capsule, compile_chip8_homebrew, verify_chip8_executable,
)


GATES = (
    "real_binary_or_source_emitter",
    "repeatable_deterministic_build",
    "in_repo_execution_verified",
    "official_hardware_or_authorized_emulator_verified",
    "asset_rights_independently_verified",
    "toolchain_license_compliance_reviewed",
    "release_ci_exact_head_success",
    "human_release_signoff",
)
SCHEMA = "skeleton.game.target_completion.v1"


def target_status(target: str, *, prove_local: bool = False) -> dict[str, Any]:
    if target not in TARGETS:
        raise ValueError("unknown or missing era target")
    row = TARGETS[target].as_dict()
    local_evidence: dict[str, Any] | None = None
    # Only this explicitly implemented homebrew adapter has an actual
    # target bytecode emitter and VM in the checked-in repository.
    if target == "chip8-vip" and prove_local:
        artifact = compile_chip8_homebrew(_original_capsule(42))
        accepted = verify_chip8_executable(artifact)
        if not accepted["win_state_reached"]:
            raise ValueError("CHIP-8 bytecode did not meet executable proof")
        local_evidence = {
            "rom_sha256": artifact["rom_sha256"],
            "rom_bytes": artifact["rom_bytes"],
            "machine_interpreter_win_verified": True,
            "independent_hardware_run": False,
            "training_examples_added": 0,
            "provenance_capsule_sha256": artifact["source_capsule_sha256"],
        }
    gate_values = {
        "real_binary_or_source_emitter": target == "chip8-vip",
        "repeatable_deterministic_build": local_evidence is not None,
        "in_repo_execution_verified": local_evidence is not None,
        # These values remain FALSE until signed independently verified
        # receipts exist. A local attacker can falsify plain JSON files.
        "official_hardware_or_authorized_emulator_verified": False,
        "asset_rights_independently_verified": False,
        "toolchain_license_compliance_reviewed": False,
        "release_ci_exact_head_success": False,
        "human_release_signoff": False,
    }
    passed = [key for key in GATES if gate_values[key]]
    missing = [key for key in GATES if not gate_values[key]]
    return {
        "schema_version": SCHEMA,
        "target": target, "era": row["era"],
        "platform_category": row["category"],
        "catalog_sha256": CATALOG_SHA256,
        "native_exporter_code_present": row["native_export_implemented"],
        "native_exporter_hardware_supported": row["real_hardware_validated"],
        "gates": gate_values,
        "passed_gates": passed, "missing_gates": missing,
        "gate_count": len(GATES),
        "local_proof": local_evidence,
        "operationally_usable_homebrew_rom": local_evidence is not None,
        "full_target_release_completed": all(gate_values.values()),
        "publish_or_license_approval": False,
        "training_examples_added": 0,
    }


def completion_overview(*, prove_chip8: bool = False) -> dict[str, Any]:
    summaries = {
        target: target_status(target, prove_local=prove_chip8 and target == "chip8-vip")
        for target in sorted(TARGETS)
    }
    counts = {
        "design_profiles": len(summaries),
        "source_or_bytecode_exporters_implemented": sum(
            item["native_exporter_code_present"] for item in summaries.values()
        ),
        "local_rom_execution_evidenced_in_this_run": sum(
            item["operationally_usable_homebrew_rom"] for item in summaries.values()
        ),
        "platforms_fully_release_verified": sum(
            item["full_target_release_completed"] for item in summaries.values()
        ),
        "platforms_needing_release_proofs": sum(
            not item["full_target_release_completed"]
            for item in summaries.values()
        ),
    }
    digest = hashlib.sha256(json.dumps(
        {key: value["gates"] for key, value in summaries.items()},
        sort_keys=True, separators=(",", ":"),
    ).encode("ascii")).hexdigest()
    return {
        "schema_version": "skeleton.game.completion_overview.v1",
        "catalog_sha256": CATALOG_SHA256,
        "target_gate_sha256": digest,
        "counts": counts,
        "completed_percent": round(
            100 * counts["platforms_fully_release_verified"]
            / counts["design_profiles"], 4
        ),
        "not_a_model_capability_metric": True,
        "machine_execution_may_be_unverified_until_--prove-chip8": not prove_chip8,
        "scope_is_target_releases_not_internal_coding_tasks": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report REAL evidence-based era-target completion, never guessed percentages.",
    )
    parser.add_argument("--target", choices=sorted(TARGETS))
    parser.add_argument("--prove-chip8", action="store_true")
    args = parser.parse_args(argv)
    result = (
        target_status(args.target, prove_local=args.prove_chip8)
        if args.target else completion_overview(prove_chip8=args.prove_chip8)
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
