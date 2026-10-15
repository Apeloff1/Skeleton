"""Manual, fail-closed executable acceptance suite for original-ROM AI training.

Intentionally NOT attached to normal PR/push workflow triggers. Executes the
repository's original DMG ROM, real instruction/rewind/Q/neural candidates
and original source-declared goal path; checks the *published bytes* as well
as process exit codes. Native libretro certification remains a separate
approved-core + lawful-ROM first-boot gate.

Invoke:
  python scripts/run_game_rom_acceptance_suite.py --output-directory /private/rom-acceptance-001

The parent directory must already exist; the output directory must not.
No network, external ROMs or BIOS. Never emit an acceptance claim before
all expected receipts have been checked and materialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SUITE_SCHEMA = "skeleton.game.original_rom_acceptance_suite.v1"
MAX_REPORT_BYTES = 32 * 1024 * 1024
MAX_STDOUT = 32768
TEST_MODULES = (
    "skeleton.testing.test_game_rom_mapper_expansion",
    "skeleton.testing.test_game_emulator_fleet_build",
    "skeleton.testing.test_game_emulator_training_lab",
    "skeleton.testing.test_game_emulator_advanced_experiments",
    "skeleton.testing.test_game_emulator_neural_world",
    "skeleton.testing.test_game_emulator_physical_planning",
    "skeleton.testing.test_game_emulator_operator_goals",
    "skeleton.testing.test_game_emulator_first_boot_audit",
    "skeleton.testing.test_game_emulator_disc_first_boot",
    "skeleton.testing.test_game_original_rom_ai_acceptance",
    "skeleton.testing.test_game_original_rom_goal_training",
    "skeleton.testing.test_game_rom_acceptance_suite",
    "skeleton.testing.test_game_original_mapper_bus_audit",
    "skeleton.testing.test_game_rom_virtual_rtc",
    "skeleton.testing.test_game_rom_cpu_timer",
    "skeleton.testing.test_game_rom_dma_timing",
    "skeleton.testing.test_game_original_cpu_bus_arbitration",
    "skeleton.testing.test_game_rom_serial_port",
    "skeleton.testing.test_game_original_serial_source_acceptance",
    "skeleton.testing.test_game_original_cpu_conformance",
    "skeleton.testing.test_game_original_cpu_interrupts",
    "skeleton.testing.test_game_rom_instruction_divergence",
)


class AcceptanceSuiteError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_file(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(path, Path) or path.is_symlink():
        raise AcceptanceSuiteError("evidence cannot be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_REPORT_BYTES:
            raise AcceptanceSuiteError("evidence file size or regular-file identity invalid")
        content = source.read(MAX_REPORT_BYTES + 1)
        after = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or len(content) != before.st_size:
            raise AcceptanceSuiteError("evidence changed during verification")
    document = json.loads(content)
    if not isinstance(document, dict):
        raise AcceptanceSuiteError("typed JSON evidence object required")
    return document, {"file": path.name, "bytes": len(content), "sha256": _sha(content)}


def _verify_digest(document: dict[str, Any], key: str) -> None:
    claimed = document.get(key)
    if (
        not isinstance(claimed, str) or len(claimed) != 64
        or _sha(_canonical({k: v for k, v in document.items() if k != key})) != claimed
    ):
        raise AcceptanceSuiteError(f"{key} is not bound to its emitted canonical report")


def _verify_original_pipeline(directory: Path) -> dict[str, Any]:
    acceptance, acceptance_ref = _json_file(directory / "acceptance.json")
    _verify_digest(acceptance, "acceptance_digest")
    if (
        acceptance.get("schema_version") != "skeleton.game.original_rom_ai_acceptance.v1"
        or acceptance.get("acceptance_gate_passed") is not True
        or acceptance.get("source_model_holdout_gain_measured") is not True
        or acceptance.get("native_libretro_core_executed") is not False
        or acceptance.get("production_jeeves_weights_changed") is not False
        or acceptance.get("production_model_promotion_authorized") is not False
        or type(acceptance.get("actual_q_updates")) is not int
        or acceptance["actual_q_updates"] < 32
        or type(acceptance.get("actual_candidate_neural_optimizer_steps")) is not int
        or acceptance["actual_candidate_neural_optimizer_steps"] < 1
    ):
        raise AcceptanceSuiteError("original ROM Q/neural operator acceptance did not pass")
    expected = {
        "original-training.gb", "rom-policy.json", "rom-source-evidence.json",
        "neural-world-candidate.json", "neural-world-measurements.json",
    }
    records = acceptance.get("private_output_sha256_receipts")
    if (
        not isinstance(records, list) or len(records) != len(expected)
        or {row.get("name") for row in records if isinstance(row, dict)} != expected
    ):
        raise AcceptanceSuiteError("original ROM acceptance did not declare all expected files")
    published = [acceptance_ref]
    for row in records:
        if not isinstance(row, dict) or row.get("private_create_only") is not True:
            raise AcceptanceSuiteError("report contains an untrusted output artifact entry")
        filename = row["name"]
        artifact = directory / filename
        if artifact.is_symlink() or not artifact.is_file():
            raise AcceptanceSuiteError("required original ROM pipeline artifact is missing")
        data = artifact.read_bytes()
        if len(data) != row["bytes"] or _sha(data) != row["sha256"]:
            raise AcceptanceSuiteError("published original ROM artifact checksum differs")
        published.append({"file": filename, "bytes": len(data), "sha256": _sha(data)})
    policy, _ = _json_file(directory / "rom-policy.json")
    source, _ = _json_file(directory / "rom-source-evidence.json")
    candidate, _ = _json_file(directory / "neural-world-candidate.json")
    metrics, _ = _json_file(directory / "neural-world-measurements.json")
    from skeleton.jeeves.game_emulator_neural_world import (
        validate_neural_world_checkpoint, verify_neural_training_sources,
    )
    from skeleton.jeeves.game_learning import _digest

    admitted, features, actions, original_digest = verify_neural_training_sources(source, policy)
    if (
        len(admitted) != acceptance["verified_neural_source_rows"]
        or original_digest != acceptance["source_q_report_digest"]
        or validate_neural_world_checkpoint(candidate) != acceptance["candidate_neural_model_sha256"]
        or metrics.get("report_digest") != acceptance["candidate_neural_measurement_sha256"]
        or metrics.get("candidate_status") != "candidate_predictive_gain_measured"
        or not isinstance(features, tuple) or not isinstance(actions, tuple)
        or _digest({k: v for k, v in metrics.items() if k != "report_digest"}) != metrics["report_digest"]
    ):
        raise AcceptanceSuiteError("published source, candidate and heldout neural reports disagree")
    return {
        "accepted": True,
        "rom_sha256": acceptance["original_game_rom_sha256"],
        "source_q_updates": acceptance["actual_q_updates"],
        "world_model_optimizer_steps": acceptance["actual_candidate_neural_optimizer_steps"],
        "world_model_heldout_improvement": acceptance["relative_holdout_mse_reduction"],
        "published_private_artifacts": published,
        "native_emulator_accuracy_proven": False,
        "production_jeeves_weights_updated": False,
    }


def _verify_mapper_bus(directory: Path) -> dict[str, Any]:
    report, reference = _json_file(directory / "original-mapper-bus.json")
    _verify_digest(report, "report_digest")
    names = (
        "rom_only", "mbc1_large", "mbc1_ram", "mbc2",
        "mbc3", "mbc3_timer_only", "mbc3_timer_ram", "mbc5",
    )
    categories = ("rom_only", "mbc1", "mbc2", "mbc3", "mbc5")
    if (
        report.get("schema_version") != "skeleton.game.original_mapper_bus_matrix.v1"
        or report.get("status") != "original_cartridge_mapper_bus_checks_passed"
        or report.get("mapped_cartridge_categories") != list(categories)
        or report.get("tested_actual_mapper_categories") != 5
        or report.get("tested_bank_geometry_profiles") != len(names)
        or report.get("source_original_cartridge_only") is not True
        or report.get("native_libretro_hardware_certified") is not False
        or report.get("production_model_weights_updated") != 0
    ):
        raise AcceptanceSuiteError("original synthetic mapper proof has missing categories or unsupported claims")
    cases = report.get("mapper_results")
    if not isinstance(cases, list) or len(cases) != len(names):
        raise AcceptanceSuiteError("mapper matrix must prove eight cartridge/RTC profiles across five mapper categories")
    total = 0
    for name, proof in zip(names, cases, strict=True):
        if not isinstance(proof, dict):
            raise AcceptanceSuiteError("typed source mapper receipt required")
        _verify_digest(proof, "receipt_digest")
        checks = proof.get("verified_register_and_memory_cases")
        if (
            proof.get("mapper") != name
            or proof.get("actual_mapper_type") != (
            "mbc1" if name.startswith("mbc1_")
            else "mbc3" if name.startswith("mbc3_")
            else name
        )
            or proof.get("actual_memory_cpu_savestate_roundtrip") is not True
            or not isinstance(checks, list)
            or len(checks) < 4 or len(set(checks)) != len(checks)
            or proof.get("real_source_bus_checks") != len(checks)
            or proof.get("hardware_cycle_accuracy_certified") is not False
            or proof.get("real_native_libretro_core_tested") is not False
        ):
            raise AcceptanceSuiteError(f"source mapper {name} has incomplete native bus evidence")
        total += len(checks)
    if report.get("verified_source_bus_checks") != total:
        raise AcceptanceSuiteError("source mapper executed bus-check totals differ")
    return {
        "accepted": True,
        "real_interpreter_mapper_types": list(categories),
        "verified_cartridge_geometry_profiles": len(names),
        "source_bus_checks": total,
        "mapper_receipt": reference,
        "native_libretro_core_certified": False,
        "hardware_timing_accuracy_certified": False,
    }


def _verify_serial_source(directory: Path) -> dict[str, Any]:
    report, ref = _json_file(directory / "original-serial-clock.json")
    _verify_digest(report, "report_digest")
    trials = report.get("real_source_trials")
    if (
        report.get("schema_version") != "skeleton.game.original_dmg_serial_source_proof.v1"
        or report.get("status") != "original_DMG_disconnected_serial_source_replayed"
        or report.get("original_owned_source_ROM_only") is not True
        or report.get("real_serial_cpu_modes") != 2
        or report.get("actual_cpu_oscillator_steps") != 2042
        or report.get("actual_original_cpu_instruction_calls") != 2050
        or report.get("hardware_serial_bit_cycles") != 512
        or report.get("unattached_external_link_peer_fabricated") is not False
        or report.get("interconsole_link_gameplay_verified") is not False
        or report.get("production_neural_model_updated") is not False
        or not isinstance(trials, list) or len(trials) != 2
    ):
        raise AcceptanceSuiteError("DMG serial source CPU clock or independent replay missing")
    for index, row in enumerate(trials):
        if (
            not isinstance(row, dict)
            or row.get("mode") != (
                "DMG_internal_disconnected" if index == 0 else "DMG_external_unclocked"
            )
            or row.get("CPU_started_actual_SB_SC_writes") != 4
            or row.get("actual_cpu_clock_advance_instructions") != 1021
            or row.get("source_program_cpu_instruction_calls") != 1025
            or row.get("serial_start_opcode_clocked_tcycles") != 12
            or row.get("hardware_clock_t_cycles_observed") != 4096
            or row.get("exact_source_cpu_replay") is not True
            or row.get("source_finished_snapshot_sha256") != row.get("source_replayed_snapshot_sha256")
            or not isinstance(row.get("source_ROM_SHA256"), str)
            or len(row["source_ROM_SHA256"]) != 64
            or row.get("serial_interrupt_set") is not (index == 0)
            or row.get("serial_SC_still_active") is not (index == 1)
            or row.get("serial_final_SB") != (255 if index == 0 else 0x6A)
        ):
            raise AcceptanceSuiteError("real DMG source CPU internal/external serial case inconsistent")
    return {
        "accepted": True,
        "source_serial_modes": 2,
        "actual_t_cycle_executions": 8192,
        "real_replay_snapshots_identical": True,
        "native_multiplayer_link_peers_verified": 0,
        "source_receipt": ref,
    }


def _verify_cpu_bus_arbitration(directory: Path) -> dict[str, Any]:
    document, ref = _json_file(directory / "original-cpu-bus.json")
    _verify_digest(document, "report_digest")
    from scripts.audit_original_gameboy_bus_arbitration import SCHEMA as BUS_SCHEMA
    findings = document.get("tested_source_bus_constraints")
    if (
        document.get("schema_version") != BUS_SCHEMA
        or document.get("status") != "original_DMG_source_bus_arbitration_passed"
        or document.get("source") != "real_GameBoyMachine_CPU_HRAM_video_and_DMA_source"
        or document.get("synthetic_original_cartridges_only") is not True
        or not isinstance(findings, list) or len(findings) != 21
        or len(set(findings)) != len(findings)
        or document.get("actual_CPU_memory_and_DMA_reference_checks") != len(findings)
        or document.get("cpu_dma_hram_only") is not True
        or document.get("cpu_video_ppu_mode_lockout") is not True
        or document.get("real_DMA_and_PPU_source_memories_unblocked") is not True
        or document.get("exact_inflight_DMA_savestate_replay") is not True
        or document.get("source_video_timing_dot_perfect") is not False
        or document.get("cpu_DMA_interrupt_bus_microcycles_certified") is not False
        or document.get("production_model_weights_updated") is not False
    ):
        raise AcceptanceSuiteError("real source Game Boy CPU bus arbitration evidence incomplete")
    if not isinstance(document.get("machine_rom_digest"), str) or len(document["machine_rom_digest"]) != 64:
        raise AcceptanceSuiteError("owned source CPU bus ROM identity unavailable")
    expected = {
        "active_DMA_CPU_external_WRAM_read_is_open_bus",
        "active_DMA_CPU_WRAM_write_ignored",
        "active_DMA_CPU_HRAM_read_allowed",
        "active_DMA_CPU_HRAM_write_allowed",
        "unmodeled_external_opcode_fetch_fails_closed",
        "PPU_VRAM_mode3_read_blocked",
        "PPU_OAM_mode2_read_blocked",
        "PPU_OAM_mode3_read_blocked",
        "LCDC_off_OAM_write_allowed",
        "inflight_OAM_DMA_full_replay_identical",
    }
    if not expected.issubset(set(findings)):
        raise AcceptanceSuiteError("critical DMA/PPU source bus cases absent from CPU proof")
    return {
        "accepted": True,
        "original_cpu_bus_checks": len(findings),
        "inflight_DMA_rewind_reproducible": True,
        "reference": ref,
        "full_electrical_hardware_accurate": False,
    }


def _verify_interrupt_matrix(directory: Path) -> dict[str, Any]:
    result, reference = _json_file(directory / "original-interrupt-control.json")
    _verify_digest(result, "report_digest")
    expected = [
        *(f"priority_vector_{number}" for number in range(5)),
        "ei_one_instruction_delay", "di_cancels_pending_ei",
        "halt_bug_duplicate_opcode_byte", "halt_wake_immediate_irq",
        "reti_stack_and_immediate_ime", "stop_frozen_until_joypad_edge",
    ]
    cases = result.get("source_scenarios")
    if (
        result.get("schema_version") != "skeleton.game.original_lr35902_interrupt_matrix.v1"
        or result.get("status") != "original_cpu_interrupt_control_replayed"
        or result.get("source") != "original_synthetic_ROM_real_GameBoyMachine"
        or result.get("priority_vectors_tested") != [0x40, 0x48, 0x50, 0x58, 0x60]
        or result.get("actual_independently_replayed_scenarios") != 11
        or result.get("physical_state_executions") != 22
        or result.get("cpu_interrupt_hardware_bus_phase_certified") is not False
        or result.get("production_neural_weights_updated") != 0
        or not isinstance(cases, list) or len(cases) != 11
    ):
        raise AcceptanceSuiteError("real source IRQ control and interrupt matrix is absent or incomplete")
    for label, case in zip(expected, cases, strict=True):
        if (
            not isinstance(case, dict) or case.get("probe") != label
            or case.get("real_interrupt_replay_passed") is not True
            or case.get("hardware_bus_cycle_certified") is not False
            or type(case.get("actual_execution_cycles")) is not int
            or case["actual_execution_cycles"] < 4
            or case.get("actual_source_after_sha256") != case.get("replayed_source_after_sha256")
            or not isinstance(case.get("actual_source_before_sha256"), str)
            or len(case["actual_source_before_sha256"]) != 64
        ):
            raise AcceptanceSuiteError(f"measured interrupt/replay scenario {label} failed source provenance")
    return {
        "accepted": True, "real_interrupt_scenarios": 11,
        "exact_interpreter_interrupt_replays": 22,
        "hardware_bus_accuracy_certified": False,
        "receipt_file": reference,
    }


def _verify_alu_reference(directory: Path) -> dict[str, Any]:
    document, reference = _json_file(directory / "original-alu-flags.json")
    _verify_digest(document, "report_digest")
    if (
        document.get("schema_version") != "skeleton.game.original_sm83_alu_reference.v1"
        or document.get("source") != "actual_GameBoyMachine_ALU_vs_independent_reference"
        or document.get("independent_hardware_flag_math_reference") is not True
        or document.get("actual_source_flag_comparisons") != 5184
        or document.get("actual_passed_alu_operations") != 8
        or document.get("full_game_accuracy_certified") is not False
        or document.get("production_model_updates") != 0
    ):
        raise AcceptanceSuiteError("original CPU ALU results fail the independent source flag reference")
    details = document.get("real_machine_results")
    if not isinstance(details, list) or len(details) != 8:
        raise AcceptanceSuiteError("each original CPU arithmetic operation needs a separate receipt")
    for index, row in enumerate(details):
        if (
            not isinstance(row, dict)
            or row.get("operation") != index
            or row.get("observed_real_machine_cases") != 648
            or row.get("source_arithmetic_flags_matched") is not True
            or not isinstance(row.get("bounded_reference_result_sha256"), str)
            or len(row["bounded_reference_result_sha256"]) != 64
        ):
            raise AcceptanceSuiteError("source ALU boundary sample counts, ordered flag math or digest differ")
    return {
        "accepted": True,
        "actual_independently_checked_ALU_flags": 5184,
        "operation_families": 8,
        "receipt_file": reference,
        "full_hardware_accuracy_certified": False,
    }


def _verify_cpu_opcode_matrix(directory: Path) -> dict[str, Any]:
    report, reference = _json_file(directory / "original-cpu-opcodes.json")
    _verify_digest(report, "report_digest")
    if (
        report.get("schema_version") != "skeleton.game.original_lr35902_opcode_matrix.v1"
        or report.get("status") != "all_documented_opcodes_executed_and_replayed"
        or report.get("actual_legal_base_opcodes") != 245
        or report.get("actual_base_opcode_single_step_executed") != 244
        or report.get("actual_cb_prefix_expansions_executed") != 256
        or report.get("expected_illegal_base_opcodes_rejected") != 11
        or report.get("actual_total_single_step_source_replays") != 1128
        or report.get("source_reference_opcodes_compared_to_actual_timing") != 564
        or report.get("conditional_real_executions") != 64
        or report.get("external_sm83_reference_commit")
        != "376f61c86fdac2048f7ce5fe838ae756b306017e"
        or report.get("native_libretro_corpus_tested") is not False
        or report.get("hardware_instruction_cycle_accuracy_independently_proven") is not False
        or report.get("production_jeeves_weights_modified") is not False
    ):
        raise AcceptanceSuiteError("original Game Boy CPU opcode coverage or replay provenance is incomplete")
    from scripts.audit_original_gameboy_cpu_opcodes import (
        INVALID_BASE, CONDITIONAL_BRANCHES, CONDITIONAL_FLAGS,
    )
    conditional = report.get("conditional_source_receipts")
    if (
        report.get("conditional_branch_flags_tested") != list(CONDITIONAL_FLAGS)
        or report.get("conditional_branch_opcodes_tested") != list(CONDITIONAL_BRANCHES)
        or not isinstance(conditional, list)
        or len(conditional) != len(CONDITIONAL_BRANCHES) * len(CONDITIONAL_FLAGS)
    ):
        raise AcceptanceSuiteError("real CPU conditional branch flag-state corpus is incomplete")
    for index, case in enumerate(conditional):
        opcode = CONDITIONAL_BRANCHES[index // len(CONDITIONAL_FLAGS)]
        flags = CONDITIONAL_FLAGS[index % len(CONDITIONAL_FLAGS)]
        outcome = case.get("conditional_control_result") if isinstance(case, dict) else None
        if (
            not isinstance(outcome, dict)
            or case.get("opcode") != opcode or case.get("cb") is not None
            or outcome.get("initial_z_c_flags") != flags
            or outcome.get("reference_conditional_branch_verified") is not True
            or outcome.get("expected_pc_after") != outcome.get("observed_pc_after")
            or outcome.get("expected_sp_after") != outcome.get("observed_sp_after")
            or case.get("emulated_t_cycles") != case.get("reference_documented_t_cycles")
            or case.get("real_independent_replay_executed") is not True
            or case.get("source_snapshot_after_sha256") != case.get("repeated_snapshot_sha256")
        ):
            raise AcceptanceSuiteError("actual conditional CPU control, flags, cycles or PC/SP replay disagrees")
    if sum(row["conditional_control_result"]["expected_branch_taken"] is True for row in conditional) != 32:
        raise AcceptanceSuiteError("conditional source opcode corpus is missing an actual branch outcome")

    base = report.get("base_instruction_receipts")
    cb = report.get("prefixed_instruction_receipts")
    if not isinstance(base, list) or len(base) != 255 or not isinstance(cb, list) or len(cb) != 256:
        raise AcceptanceSuiteError("all 256 CB variants and 255 non-CB base identities are required")
    for index, case in enumerate(base):
        opcode = index + (index >= 0xCB)
        if not isinstance(case, dict) or case.get("opcode") != opcode or case.get("cb") is not None:
            raise AcceptanceSuiteError("base LR35902 opcode identity or ordering changed")
        if opcode in INVALID_BASE:
            if case.get("expected_invalid_opcode_rejected") is not True or case.get("real_instruction_executed") is not False:
                raise AcceptanceSuiteError("illegal LR35902 opcode was treated as a successful execution")
        elif case.get("real_instruction_executed") is not True:
            raise AcceptanceSuiteError("documented legal LR35902 opcode was not executed")
    for index, case in enumerate(cb):
        if not isinstance(case, dict) or case.get("opcode") != 0xCB or case.get("cb") != index:
            raise AcceptanceSuiteError("CB-prefixed CPU opcode identity or ordering changed")
        if case.get("real_instruction_executed") is not True:
            raise AcceptanceSuiteError("documented CB subopcode did not execute")
    for case in base + cb + conditional:
        if case.get("real_instruction_executed") is True:
            before = case.get("source_snapshot_after_sha256")
            after = case.get("repeated_snapshot_sha256")
            if (
                case.get("real_independent_replay_executed") is not True
                or type(before) is not str or len(before) != 64 or before != after
                or type(case.get("emulated_t_cycles")) is not int
                or case["emulated_t_cycles"] not in (4, 8, 12, 16, 20, 24)
                or case.get("reference_documented_t_cycles") != case["emulated_t_cycles"]
                or case.get("source_reference_cycles_verified") is not True
                or type(case.get("reference_documented_instruction_bytes")) is not int
                or not 1 <= case["reference_documented_instruction_bytes"] <= 3
            ):
                raise AcceptanceSuiteError("legal opcode lacks exact real CPU/memory/raster replay proof")
    return {
        "accepted": True,
        "legal_base_opcode_variants": 245,
        "actual_cb_prefixed_opcode_variants": 256,
        "source_cpu_instruction_steps_replayed": 1128,
        "independent_cc0_opcode_cycle_reference_matches": 564,
        "conditional_branch_flag_state_trials": 64,
        "invalid_opcodes_denied": 11,
        "receipt_file": reference,
        "hardware_accuracy_certified": False,
    }


def _verify_instruction_microtrace(directory: Path) -> dict[str, Any]:
    """Read a real original CPU branching trace and validate every source row."""
    report, reference = _json_file(directory / "original-cpu-instruction-divergence.json")
    _verify_digest(report, "report_digest")
    runs = report.get("actual_passive_and_controller_interventions")
    contrasts = report.get("paired_replay_verified_differences")
    if (
        report.get("schema_version") != "skeleton.game.original_rom_instruction_divergence.v1"
        or report.get("all_source_replays_identical") is not True
        or report.get("source_instruction_and_memory_trace") is not True
        or report.get("production_jeeves_model_promotion") is not False
        or report.get("neural_or_q_training_updates") != 0
        or not isinstance(runs, list) or not 2 <= len(runs) <= 8
        or not isinstance(contrasts, list) or len(contrasts) != len(runs) - 1
        or runs[0].get("control") != "idle"
    ):
        raise AcceptanceSuiteError("controlled real ROM CPU instruction evidence is incomplete")
    from skeleton.jeeves.game_rom_instruction_divergence import ACTIONS

    executed = 0
    schedules_observed = 0
    temporal_sequences_observed = 0
    for case in runs:
        source = case.get("first_run", {})
        observations = source.get("time_and_video_evidence")
        schedule = source.get("source_input_schedule")
        count = report["requested_instructions_per_branch"]
        if (
            not isinstance(schedule, list) or not 1 <= len(schedule) <= 8
            or case.get("source_input_schedule") != schedule
            or source.get("source_controller_changes") != len(schedule)
            or any(
                not isinstance(entry, dict)
                or set(entry) != {"at_source_instruction", "action"}
                or type(entry["at_source_instruction"]) is not int
                or entry["at_source_instruction"] != index * count // len(schedule)
                or entry["action"] not in ACTIONS
                for index, entry in enumerate(schedule)
            )
            or case.get("control") != "->".join(entry["action"] for entry in schedule)
            or source.get("control") != case.get("control")
        ):
            raise AcceptanceSuiteError("real source input phase ledger is missing or not aligned to CPU instructions")
        schedules_observed += len(schedule)
        temporal_sequences_observed += len(schedule) > 1
        if (
            case.get("source_replay_identical") is not True
            or case.get("actual_repeated_physical_cpu_runs") != 2
            or source.get("source_state_before_inputs_sha256") != report.get("exact_boot_source_checkpoint_sha256")
            or source.get("actual_source_output_digest") != case.get("second_run_source_output_digest")
            or source.get("full_source_end_snapshot_sha256") != case.get("second_run_final_snapshot_sha256")
            or not isinstance(observations, list) or not 2 <= len(observations) <= 1024
            or source.get("real_source_sample_count") != len(observations)
            or source.get("real_source_cpu_instructions") != report.get("requested_instructions_per_branch")
        ):
            raise AcceptanceSuiteError("source-emulated CPU replay evidence differs from repeated run")
        for observation in observations:
            if not isinstance(observation, dict) or "sample_digest" not in observation:
                raise AcceptanceSuiteError("source microtrace sample digest is unavailable")
            _verify_digest(observation, "sample_digest")
        if _sha(_canonical(observations)) != source.get("actual_source_output_digest"):
            raise AcceptanceSuiteError("measured emulator CPU samples differ from their source trace")
        executed += source["real_source_cpu_instructions"] * 2
    if executed != report.get("real_source_instruction_executions"):
        raise AcceptanceSuiteError("source instruction replay claims more or fewer CPU instructions than audited")
    if (
        report.get("actually_executed_temporal_sequences") != temporal_sequences_observed
        or report.get("controlled_source_input_assignment_events") != schedules_observed
    ):
        raise AcceptanceSuiteError("source temporal interventions or actual controller event counts differ")
    for comparison in contrasts:
        finding = comparison.get("comparison")
        if (
            not isinstance(finding, dict)
            or type(finding.get("actual_source_control_difference_observed")) is not bool
            or finding.get("game_objective_success_proven") is not False
            or finding.get("real_world_cause_proven") is not False
        ):
            raise AcceptanceSuiteError("source CPU experiment invented game causation or objectives")
    return {
        "accepted": True,
        "source_instruction_executions": executed,
        "actual_replayed_branch_pairs": len(runs),
        "controlled_divergence_pairs": len(contrasts),
        "actual_multi_action_sequences": temporal_sequences_observed,
        "source_controller_assignment_events": schedules_observed,
        "receipt_file": reference,
        "hardware_timing_or_game_success_certified": False,
        "production_weights_updated": False,
    }


def _verify_game_goal(directory: Path) -> dict[str, Any]:
    goal, reference = _json_file(directory / "original-goal-q.json")
    _verify_digest(goal, "receipt_digest")
    snapshot = goal.get("q_policy_snapshot", {})
    if (
        goal.get("schema_version") != "skeleton.game.original_dmg_goal_q.v1"
        or goal.get("source_actual_goal_completion") is not True
        or goal.get("authored_game_specific_win_evidence") is not True
        or goal.get("observed_active_end", {}).get("completed") != 1
        or goal.get("observed_neutral_end", {}).get("completed") != 0
        or goal.get("observed_active_end", {}).get("score", 0) < 1
        or goal.get("native_libretro_execution") is not False
        or goal.get("production_policy_promotion") is not False
        or goal.get("neural_weights_updated") != 0
        or type(goal.get("real_goal_conditioned_q_updates")) is not int
        or goal["real_goal_conditioned_q_updates"] < 1
        or goal["real_goal_conditioned_q_updates"] != goal.get("executed_input_frames")
        or goal.get("independently_replayed_source_frames") != goal["executed_input_frames"]
        or not isinstance(snapshot, dict)
        or snapshot.get("committed_updates") != goal["real_goal_conditioned_q_updates"]
    ):
        raise AcceptanceSuiteError("original ROM game-mission score and Q training not physically established")
    from skeleton.jeeves.game_learning import _digest

    claimed_snapshot = snapshot.get("snapshot_digest")
    if not isinstance(claimed_snapshot, str) or _digest({
        k: v for k, v in snapshot.items() if k != "snapshot_digest"
    }) != claimed_snapshot:
        raise AcceptanceSuiteError("authored-game policy snapshot is not internally bound")
    return {
        "accepted": True,
        "original_rom_sha256": goal["rom_sha256"],
        "real_source_controller_frames": goal["executed_input_frames"],
        "real_goal_q_updates": goal["real_goal_conditioned_q_updates"],
        "authored_win_and_score_verified": True,
        "semantic_game_meaning_valid_only_for_authored_rom": True,
        "report_file": reference,
        "production_weights_updated": False,
    }


def _publish_phase(directory: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    """Write a create-only *failure or success* phase result, never acceptance."""
    label = receipt.get("label")
    if (
        type(label) is not str or not label
        or len(label) > 80
        or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in label)
    ):
        raise AcceptanceSuiteError("unbounded phase label rejected")
    result = dict(receipt)
    result["receipt_digest"] = _sha(_canonical(result))
    payload = _canonical(result) + b"\n"
    if len(payload) > 2 * MAX_STDOUT + 4096:
        raise AcceptanceSuiteError("phase diagnostic exceeds bounded output capacity")
    name = "phase_" + label + ".json"
    fd = os.open(
        directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0), 0o600,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return result


def _run(
    command: list[str], output_root: Path, label: str, *,
    seconds: int,
) -> dict[str, Any]:
    if (
        type(seconds) is not int or not 10 <= seconds <= 900
        or not isinstance(command, list) or not command
    ):
        raise AcceptanceSuiteError("bounded acceptance process command required")
    base = {
        "label": label,
        "command": command,
        "actual_process_invoked": True,
        "production_jeeves_weights_modified": False,
        "not_an_acceptance_receipt": True,
    }
    try:
        finished = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True,
            timeout=seconds, check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        decoded = lambda text: (
            text.decode("utf-8", errors="replace") if isinstance(text, bytes)
            else (text or "")
        )
        _publish_phase(output_root, {
            **base, "status": "bounded_child_timed_out",
            "exit_code": None,
            "timeout_seconds": seconds,
            "stdout_tail": decoded(exc.stdout)[-MAX_STDOUT:],
            "stderr_tail": decoded(exc.stderr)[-MAX_STDOUT:],
        })
        raise AcceptanceSuiteError(f"{label}: bounded real executable process timed out") from exc
    receipt = _publish_phase(output_root, {
        **base,
        "status": "child_passed" if finished.returncode == 0 else "child_failed",
        "exit_code": finished.returncode,
        "stdout_tail": finished.stdout[-MAX_STDOUT:],
        "stderr_tail": finished.stderr[-MAX_STDOUT:],
    })
    if finished.returncode != 0:
        raise AcceptanceSuiteError(
            f"{label} returned {finished.returncode}: {finished.stderr[-1400:]}"
        )
    return receipt

def run_acceptance_suite(
    output_directory: Path, *, seed: int = 42,
    tests: bool = True, process_timeout_seconds: int = 600,
) -> dict[str, Any]:
    if (
        not isinstance(output_directory, Path)
        or output_directory.exists() or output_directory.is_symlink()
        or not output_directory.parent.is_dir()
        or type(seed) is not int or not 0 <= seed <= 2**63 - 1
        or type(tests) is not bool
    ):
        raise AcceptanceSuiteError("acceptance output must be a new local directory with bounded seed")
    if type(process_timeout_seconds) is not int or not 30 <= process_timeout_seconds <= 900:
        raise AcceptanceSuiteError("acceptance worker timeout must be 30..900 seconds")
    output_directory.mkdir(mode=0o700)
    processes = []
    try:
        if tests:
            processes.append(_run(
                [sys.executable, "-m", "unittest", "-v", *TEST_MODULES],
                output_directory, "focused_synthetic_and_real_original_rom_regressions",
                seconds=process_timeout_seconds,
            ))
        serial_path = output_directory / "original-serial-clock.json"
        processes.append(_run(
            [sys.executable, "scripts/audit_original_gameboy_serial_port.py",
             "--evidence-file", str(serial_path)],
            output_directory, "original_dmg_serial_port_cpu_clock",
            seconds=process_timeout_seconds,
        ))
        serial_clock = _verify_serial_source(output_directory)
        bus_path = output_directory / "original-cpu-bus.json"
        processes.append(_run(
            [sys.executable, "scripts/audit_original_gameboy_bus_arbitration.py",
             "--evidence-file", str(bus_path)],
            output_directory, "original_dmg_cpu_dma_ppu_bus_arbitration",
            seconds=process_timeout_seconds,
        ))
        cpu_bus = _verify_cpu_bus_arbitration(output_directory)
        interrupt_path = output_directory / "original-interrupt-control.json"
        processes.append(_run(
            [
                sys.executable, "scripts/audit_original_gameboy_interrupts.py",
                "--evidence-file", str(interrupt_path),
            ],
            output_directory, "original_sm83_interrupt_control",
            seconds=process_timeout_seconds,
        ))
        interrupts = _verify_interrupt_matrix(output_directory)
        alu_path = output_directory / "original-alu-flags.json"
        processes.append(_run(
            [
                sys.executable, "scripts/audit_original_gameboy_alu_flags.py",
                "--evidence-file", str(alu_path),
            ],
            output_directory, "original_sm83_alu_reference",
            seconds=process_timeout_seconds,
        ))
        alu_reference = _verify_alu_reference(output_directory)
        opcode_path = output_directory / "original-cpu-opcodes.json"
        processes.append(_run(
            [
                sys.executable, "scripts/audit_original_gameboy_cpu_opcodes.py",
                "--evidence-file", str(opcode_path),
            ],
            output_directory, "original_lr35902_opcode_coverage",
            seconds=process_timeout_seconds,
        ))
        opcode_matrix = _verify_cpu_opcode_matrix(output_directory)
        instruction_path = output_directory / "original-cpu-instruction-divergence.json"
        processes.append(_run(
            [
                sys.executable, "scripts/audit_original_rom_instruction_divergence.py",
                "--evidence-file", str(instruction_path),
                "--seed", str(seed), "--instruction-count", "2048",
                "--sample-stride", "8", "--max-cycles-per-branch", "131072",
                "--actions", "idle", "a", "right", "a_right",
                "--sequence", "a,idle,right",
                "--sequence", "right,a",
                "--sequence", "a_right,idle",
            ],
            output_directory, "original_cpu_source_instruction_replays",
            seconds=process_timeout_seconds,
        ))
        instruction = _verify_instruction_microtrace(output_directory)
        mapper_path = output_directory / "original-mapper-bus.json"
        processes.append(_run(
            [
                sys.executable, "scripts/audit_original_gameboy_mapper_matrix.py",
                "--evidence-file", str(mapper_path),
            ],
            output_directory, "source_gameboy_mapper_bus_proof",
            seconds=process_timeout_seconds,
        ))
        mapper = _verify_mapper_bus(output_directory)
        original_path = output_directory / "original"
        processes.append(_run(
            [
                sys.executable, "scripts/accept_original_rom_ai_pipeline.py",
                "--output-directory", str(original_path),
                "--seed", str(seed), "--max-runs", "12",
                "--episode-steps", "12", "--neural-epochs", "4",
                "--neural-width", "8",
            ],
            output_directory, "original_rom_cpu_q_neural_acceptance",
            seconds=process_timeout_seconds,
        ))
        original = _verify_original_pipeline(original_path)
        goal_path = output_directory / "original-goal-q.json"
        processes.append(_run(
            [
                sys.executable, "-m", "skeleton.jeeves.game_original_rom_goal_training",
                "--seed", str(seed), "--max-steps", "2048",
                "--max-frames-per-tile", "16",
                "--evidence-file", str(goal_path),
            ],
            output_directory, "authored_rom_cpu_goal_q_acceptance",
            seconds=process_timeout_seconds,
        ))
        goal = _verify_game_goal(output_directory)
        report = {
            "schema_version": SUITE_SCHEMA,
            "status": "original_cpu_rom_emulator_ai_acceptance_pass",
            "tests_requested": tests,
            "focused_tests_executed": tests,
            "source_cpu_interpreter_executed": True,
            "original_cartridge_bus_matrix_verified": True,
            "source_instruction_replay_and_divergence_verified": True,
            "all_legal_source_opcodes_replay_verified": True,
            "independent_cpu_alu_flags_reference_verified": True,
            "real_interrupt_priority_and_IME_control_replay_verified": True,
            "cpu_DMA_and_PPU_bus_arbitration_verified": True,
            "source_internal_external_serial_replay_verified": True,
            "source_q_rewind_proven": True,
            "neural_candidate_optimized_and_scored": True,
            "source_goal_replay_and_neutral_control_verified": True,
            "original_training": original,
            "original_goal_training": goal,
            "real_cartridge_bus_matrix": mapper,
            "source_cpu_instruction_divergence": instruction,
            "original_cpu_opcode_coverage": opcode_matrix,
            "original_cpu_alu_reference": alu_reference,
            "original_cpu_interrupt_control": interrupts,
            "original_cpu_bus_arbitration": cpu_bus,
            "original_DMG_serial_clock": serial_clock,
            "bounded_worker_receipts": processes,
            "real_libretro_installed_core_tested": False,
            "independent_game_hardware_accuracy_certified": False,
            "production_jeeves_weights_modified": False,
            "production_model_promotion_authorized": False,
        }
        report["suite_digest"] = _sha(_canonical(report))
        payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
        if len(payload) > MAX_REPORT_BYTES:
            raise AcceptanceSuiteError("published acceptance suite evidence exceeds bounded capacity")
        fd = os.open(output_directory / "suite-acceptance.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        return report
    except BaseException:
        # Operator explicitly receives a nonzero command result and retains
        # partial real phase artifacts for debugging. Never publish a passing
        # acceptance receipt or auto-promote partial evidence.
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--without-tests", action="store_true")
    parser.add_argument("--process-timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        result = run_acceptance_suite(
            args.output_directory.resolve(strict=False), seed=args.seed,
            tests=not args.without_tests,
            process_timeout_seconds=args.process_timeout_seconds,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({
            "status": "original_rom_ai_acceptance_failed",
            "reason": str(exc)[:1200],
            "production_jeeves_weights_modified": False,
            "receipt_published": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": result["status"],
        "suite_sha256": result["suite_digest"],
        "original_emulator_accepted": True,
        "native_libretro_hardware_accepted": False,
        "result_file": str(args.output_directory / "suite-acceptance.json"),
        "production_jeeves_weights_modified": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
