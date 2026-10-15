"""Measured CPU-instruction divergences in source-authored Game Boy cartridges.

This diagnostic operates on the real experimental LR35902 interpreter, not
a simulated transition table. Independent source replay from an identical
machine snapshot is mandatory. The experiment compares passive and active
controller inputs, hashes full memory/raster/SRAM plus timer registers, and
returns bounded first-divergence receipts for adversarial AI debugging.

It never equates memory differences with game objective success, never
trains neural or Q weights, and never certifies native libretro or hardware.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .game_rom_generation import build_original_dmg_game
from .game_rom_runtime import FRAME_CYCLES, GameBoyMachine
from .game_learning import _digest, _json

SCHEMA = "skeleton.game.original_rom_instruction_divergence.v1"
ACTIONS = ("idle", "up", "down", "left", "right", "a", "b", "start", "select", "a_right")
HARD_MAX_SAMPLES = 1024


class InstructionDivergenceError(ValueError):
    pass


@dataclass(frozen=True)
class InstructionDivergenceConfig:
    seed: int = 42
    instruction_count: int = 2048
    sample_stride: int = 8
    max_cycles_per_branch: int = 131072
    boot_cycles: int = FRAME_CYCLES
    action_subset: tuple[str, ...] = ("idle", "a", "right", "a_right")
    temporal_sequences: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        for key, minimum, maximum in (
            ("seed", 0, 2**63 - 1),
            ("instruction_count", 64, 16384),
            ("sample_stride", 1, 512),
            ("max_cycles_per_branch", 512, 524288),
            ("boot_cycles", 4, FRAME_CYCLES * 2),
        ):
            value = getattr(self, key)
            if type(value) is not int or not minimum <= value <= maximum:
                raise InstructionDivergenceError(f"{key} outside admissible source CPU bounds")
        if (
            self.instruction_count // self.sample_stride + 2 > HARD_MAX_SAMPLES
            or self.max_cycles_per_branch < self.instruction_count * 4
            or not isinstance(self.action_subset, tuple)
            or not 2 <= len(self.action_subset) <= 8
            or self.action_subset[0] != "idle"
            or len(set(self.action_subset)) != len(self.action_subset)
            or any(action not in ACTIONS for action in self.action_subset)
            or not isinstance(self.temporal_sequences, tuple)
            or len(self.action_subset) + len(self.temporal_sequences) > 8
            or any(
                not isinstance(sequence, tuple)
                or not 2 <= len(sequence) <= 8
                or any(type(action) is not str or action not in ACTIONS for action in sequence)
                or any(left == right for left, right in zip(sequence, sequence[1:]))
                for sequence in self.temporal_sequences
            )
            or len(set(self.temporal_sequences)) != len(self.temporal_sequences)
        ):
            raise InstructionDivergenceError("bounded unique controls with idle baseline and finite sampling required")


def _capture(machine: GameBoyMachine, index: int, pc_before: int, opcode: int) -> dict[str, Any]:
    registers = {
        "a": machine.a, "f": machine.f, "b": machine.b, "c": machine.c,
        "d": machine.d, "e": machine.e, "h": machine.h, "l": machine.l,
        "sp": machine.sp, "pc": machine.pc,
        "ime": machine.ime, "halted": machine.halted,
        "stopped": machine.stopped, "halt_bug": machine.halt_bug,
    }
    timer = {
        "div": machine.read(0xFF04),
        "internal_divider_low": machine.divider & 255,
        "tima": machine.read(0xFF05),
        "tma": machine.read(0xFF06),
        "tac": machine.memory[0xFF07] & 7,
        "pending_overflow_cycles": machine.timer_reload_delay,
        "if": machine.read(0xFF0F), "ie": machine.read(0xFFFF),
    }
    sprite_dma = {
        "active": machine.dma_active,
        "programmed_source_page": machine.read(0xFF46),
        "source_address": machine.dma_source,
        "actual_copied_oam_bytes": machine.dma_index,
        "inflight_4t_byte_phase": machine.dma_tcycles,
        "startup_remaining_t_cycles": machine.dma_startup,
        "sprite_attribute_bytes_sha256": hashlib.sha256(
            machine.memory[0xFE00:0xFEA0]
        ).hexdigest(),
        "source_bus_conflicts_modeled": False,
    }
    cartridge = {
        "mapper": machine.metadata["mapper"],
        "rom_bank": machine.rom_bank,
        "ram_bank_selector": machine.bank_high,
        "ram_enabled": machine.ram_enabled,
        "mode": machine.bank_mode,
        "virtual_rtc": machine.metadata["virtual_rtc"],
    }
    if machine.metadata["virtual_rtc"]:
        cartridge["rtc_live"] = list(machine.rtc_regs)
        cartridge["rtc_latched"] = (
            None if machine.rtc_latched is None else list(machine.rtc_latched)
        )
        cartridge["rtc_fractional_cycles"] = machine.rtc_cycle_remainder
    parts = {
        "wram_full_sha256": hashlib.sha256(machine.memory[0xC000:0xE000]).hexdigest(),
        "vram_full_sha256": hashlib.sha256(machine.memory[0x8000:0xA000]).hexdigest(),
        "oam_full_sha256": hashlib.sha256(machine.memory[0xFE00:0xFEA0]).hexdigest(),
        "io_full_sha256": hashlib.sha256(machine.memory[0xFF00:0xFF80]).hexdigest(),
        "sram_full_sha256": hashlib.sha256(machine.external_ram).hexdigest(),
        "framebuffer_sha256": hashlib.sha256(machine.framebuffer).hexdigest(),
    }
    receipt = {
        "after_instruction_ordinal": index,
        "last_pc_before": pc_before,
        "last_observed_opcode_byte": opcode,
        "total_emulator_instruction_count": machine.instructions,
        "actual_cpu_schedule_cycles": machine.cycles,
        "actual_frame_count": machine.frames,
        "real_cpu_registers": registers,
        "real_div_timer_interrupts": timer,
        "real_mapper_control": cartridge,
        "real_sprite_dma_transfer": sprite_dma,
        "native_source_memory_sha256": parts,
        "authored_goal_memory": {
            "player_x": machine.read(0xC000),
            "player_y": machine.read(0xC001),
            "score": machine.read(0xC002),
            "completed": machine.read(0xC004),
        },
    }
    receipt["sample_digest"] = _digest(receipt)
    return receipt


def _run_from_exact_state(
    machine: GameBoyMachine, checkpoint: Mapping[str, Any],
    action: str | tuple[str, ...], config: InstructionDivergenceConfig,
) -> dict[str, Any]:
    machine.restore(checkpoint)
    phases = (action,) if isinstance(action, str) else action
    if not phases or any(phase not in ACTIONS for phase in phases):
        raise InstructionDivergenceError("finite source action schedule requires legal controller tokens")
    boundaries = [
        (phase_index * config.instruction_count) // len(phases)
        for phase_index in range(len(phases))
    ]
    if len(set(boundaries)) != len(phases):
        raise InstructionDivergenceError("source profile has more phases than instruction budget")
    schedule = [
        {"at_source_instruction": step, "action": phase}
        for step, phase in zip(boundaries, phases, strict=True)
    ]
    machine.set_buttons(
        tuple() if phases[0] == "idle" else tuple(phases[0].split("_"))
    )
    row = _capture(machine, 0, machine.pc, machine.read(machine.pc))
    points = [row]
    total_cycles = 0
    next_phase = 1
    for ordinal in range(1, config.instruction_count + 1):
        # An instruction boundary controls the input; it is a measured CPU
        # instruction count, NOT a wall time or a promise of frame timing.
        if next_phase < len(boundaries) and ordinal - 1 == boundaries[next_phase]:
            phase = phases[next_phase]
            machine.set_buttons(tuple() if phase == "idle" else tuple(phase.split("_")))
            next_phase += 1
        before_pc = machine.pc
        opcode = machine.read(before_pc)
        elapsed = machine.instruction()
        if type(elapsed) is not int or not 4 <= elapsed <= 24:
            raise InstructionDivergenceError("real source CPU instruction returned impossible cycles")
        total_cycles += elapsed
        if total_cycles > config.max_cycles_per_branch:
            raise InstructionDivergenceError("actual source branch exceeded CPU-cycle cap")
        if ordinal % config.sample_stride == 0 or ordinal == config.instruction_count:
            points.append(_capture(machine, ordinal, before_pc, opcode))
    if next_phase != len(phases):
        raise InstructionDivergenceError("bounded original ROM input schedule was not fully exercised")
    final_snapshot = machine.snapshot()
    return {
        "control": "->".join(phases),
        "source_input_schedule": schedule,
        "source_controller_changes": len(schedule),
        "real_source_cpu_instructions": config.instruction_count,
        "real_source_cycles": total_cycles,
        "real_source_sample_count": len(points),
        "source_state_before_inputs_sha256": _digest(checkpoint),
        "full_source_end_snapshot_sha256": _digest(final_snapshot),
        "time_and_video_evidence": points,
        "actual_source_output_digest": _digest(points),
    }

def _first_difference(
    passive: Mapping[str, Any], active: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = passive["time_and_video_evidence"]
    treatment = active["time_and_video_evidence"]
    if len(baseline) != len(treatment):
        raise InstructionDivergenceError("controlled instruction sampling dimension differs")
    domains = (
        "real_cpu_registers", "real_div_timer_interrupts", "real_mapper_control",
        "real_sprite_dma_transfer", "native_source_memory_sha256", "authored_goal_memory",
        "actual_cpu_schedule_cycles", "actual_frame_count",
    )
    for left, right in zip(baseline, treatment, strict=True):
        if left["after_instruction_ordinal"] != right["after_instruction_ordinal"]:
            raise InstructionDivergenceError("control CPU sample ordinal differs")
        changed = [key for key in domains if left[key] != right[key]]
        if changed:
            return {
                "first_sample_ordinal": left["after_instruction_ordinal"],
                "changed_measured_domains": changed,
                "passive_sample_sha256": left["sample_digest"],
                "active_sample_sha256": right["sample_digest"],
                "actual_source_control_difference_observed": True,
                "real_world_cause_proven": False,
                "game_objective_success_proven": False,
            }
    return {
        "first_sample_ordinal": None,
        "changed_measured_domains": [],
        "actual_source_control_difference_observed": False,
        "real_world_cause_proven": False,
        "game_objective_success_proven": False,
    }


def compare_original_rom_instruction_branches(
    config: InstructionDivergenceConfig = InstructionDivergenceConfig(),
) -> dict[str, Any]:
    if not isinstance(config, InstructionDivergenceConfig):
        raise InstructionDivergenceError("typed bounded physical source branch configuration required")
    generated = build_original_dmg_game(
        seed=config.seed, title="Original Instruction Evidence"
    )
    content = base64.b64decode(generated["rom_base64"], validate=True)
    if hashlib.sha256(content).hexdigest() != generated["rom_digest"]:
        raise InstructionDivergenceError("authored source cartridge hash does not match supplied ROM")
    core = GameBoyMachine(content)
    boot = core.run(config.boot_cycles)
    checkpoint = core.snapshot()
    if not 0 < boot["instructions"] or core.metadata["mapper"] != "rom_only":
        raise InstructionDivergenceError("expected source-executed original DMG boot is missing")
    results = []
    controlled = list(config.action_subset) + list(config.temporal_sequences)
    for action in controlled:
        first = _run_from_exact_state(core, checkpoint, action, config)
        replay = _run_from_exact_state(core, checkpoint, action, config)
        if first != replay:
            raise InstructionDivergenceError(
                f"original Game Boy CPU source controls {action} failed deterministic instruction replay"
            )
        results.append({
            "control": first["control"],
            "source_input_schedule": first["source_input_schedule"],
            "actual_repeated_physical_cpu_runs": 2,
            "source_replay_identical": True,
            "first_run": first,
            "second_run_source_output_digest": replay["actual_source_output_digest"],
            "second_run_final_snapshot_sha256": replay["full_source_end_snapshot_sha256"],
        })
    baseline = results[0]["first_run"]
    contrasts = []
    for candidate in results[1:]:
        contrasts.append({
            "control": candidate["control"],
            "comparison": _first_difference(baseline, candidate["first_run"]),
            "full_source_end_state_differs": (
                baseline["full_source_end_snapshot_sha256"]
                != candidate["first_run"]["full_source_end_snapshot_sha256"]
            ),
        })
    result = {
        "schema_version": SCHEMA,
        "source_original_game_rom_sha256": generated["rom_digest"],
        "source_rights": "locally_original_authored_ROM_no_third_party_media",
        "exact_boot_source_checkpoint_sha256": _digest(checkpoint),
        "source_boot_actual_cpu_instructions": boot["instructions"],
        "requested_instructions_per_branch": config.instruction_count,
        "sample_stride_in_source_instructions": config.sample_stride,
        "real_source_instruction_executions": (
            2 * len(controlled) * config.instruction_count
        ),
        "actual_passive_and_controller_interventions": results,
        "actually_executed_temporal_sequences": len(config.temporal_sequences),
        "controlled_source_input_assignment_events": sum(
            len(record["source_input_schedule"]) for record in results
        ),
        "paired_replay_verified_differences": contrasts,
        "all_source_replays_identical": True,
        "source_instruction_and_memory_trace": True,
        "no_game_objective_success_claimed": True,
        "no_arbitrary_rom_hardware_accuracy_claimed": True,
        "no_original_game_text_assets_reused": True,
        "neural_or_q_training_updates": 0,
        "production_jeeves_model_promotion": False,
        "disclosure": (
            "CPU instruction-ordinal alignment is not an equal-wall-time experiment; "
            "raw timer/frame/IO differences need independent source semantics."
        ),
    }
    result["report_digest"] = _digest(result)
    _json(result, limit=8 * 1024 * 1024)
    return result
