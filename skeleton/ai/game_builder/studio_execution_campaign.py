"""Synchronous full original-game qualification campaign for Jeeves Studio.

One operator-owned deterministic driver calls the actual existing producers
and validators; it never substitutes one platform's result for another.
Each stage writes its authoritative receipt in the canonical campaign;
the driver adds only a source-bound summary for an operator to inspect.
No autonomous background jobs, shell, model-weight promotion, unconsented
capture, third-party copyrighted assets or hardware release approvals.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .contracts import canonical_digest
from .studio_campaign import CampaignOrder, inspect_campaign, run_campaign
from .studio_campaign_assurance import (
    inspect_production_assurance, qualify_campaign_target,
    qualify_campaign_emulator, qualify_campaign_browser,
    qualify_campaign_godot, qualify_campaign_canvas,
)

SCHEMA = "skeleton.game_builder.studio_execution_campaign.v1"
STAGES = ("source", "rom", "emulator", "browser", "godot", "canvas")
_ROM_TARGETS = frozenset((
    "nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom",
))
_EMULATOR_TARGETS = frozenset((
    "nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom",
))


class StudioExecutionCampaignError(ValueError):
    """Invalid run authority, dependency, source identity or execution mode."""


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    stages: tuple[str, ...] = ("source", "rom", "emulator", "browser", "godot")
    timeout_seconds: int = 90
    max_emulator_frames: int = 260_000
    max_sources_per_run: int | None = None
    stop_after_blocker: bool = False
    capture_consent: bool = False

    def __post_init__(self) -> None:
        if (type(self.stages) is not tuple or not self.stages
                or any(type(step) is not str or step not in STAGES for step in self.stages)
                or len(self.stages) != len(set(self.stages))
                or tuple(sorted(self.stages, key=STAGES.index)) != self.stages):
            raise StudioExecutionCampaignError(
                "stages must be unique, ordered original studio execution stages"
            )
        if (type(self.timeout_seconds) is not int
                or not 5 <= self.timeout_seconds <= 120
                or type(self.max_emulator_frames) is not int
                or not 16 <= self.max_emulator_frames <= 260_000):
            raise StudioExecutionCampaignError("local execution budgets must be finite and typed")
        if (self.max_sources_per_run is not None
                and (type(self.max_sources_per_run) is not int
                     or self.max_sources_per_run < 1)):
            raise StudioExecutionCampaignError("source resume cap must be a positive integer")
        if type(self.stop_after_blocker) is not bool or type(self.capture_consent) is not bool:
            raise StudioExecutionCampaignError("run/consent flags must be explicit booleans")
        if "canvas" in self.stages and not self.capture_consent:
            raise StudioExecutionCampaignError(
                "actual browser image capture requires distinct explicit consent"
            )


def _stage_status(stage: str, outcome: dict) -> tuple[str, str | None]:
    if stage == "rom":
        if outcome.get("native_rom_compiled") is True:
            return "verified", None
        return "blocked", outcome.get("blocker", "rom_not_qualified")
    if stage == "emulator":
        if outcome.get("machine_code_victory") is True:
            return "verified", None
        return "blocked", outcome.get("blocker", "rom_emulator_not_qualified")
    if stage == "browser":
        if outcome.get("javascript_gameplay_executed") is True:
            return "verified", None
        return "blocked", outcome.get("failure", "javascript_playthrough_not_qualified")
    if stage == "godot":
        if outcome.get("godot_headless_gameplay_executed") is True:
            return "verified", None
        return "blocked", outcome.get("failure", "godot_playthrough_not_qualified")
    if stage == "canvas":
        if outcome.get("generated_game_canvas_recorded") is True:
            return "verified", None
        return "blocked", outcome.get("blocker", "generated_game_pixels_not_recorded")
    raise StudioExecutionCampaignError("unregistered studio execution stage")


def run_studio_execution_campaign(
    order: CampaignOrder, campaign: str | Path, *, policy: ExecutionPolicy,
    authorized: bool, execute: bool,
) -> dict:
    """Execute a real multi-stage qualification pass without relaxing gates.

    A requested, unavailable runtime remains blocked; unrequested stages are
    not counted as verified. Other independent targets and stages continue
    unless explicitly configured to stop after the first blocker.
    """
    if authorized is not True:
        raise PermissionError("studio E2E execution requires actual operator authorization")
    if execute is not True:
        raise StudioExecutionCampaignError("full production E2E run requires opt-in execution")
    if not isinstance(order, CampaignOrder) or not isinstance(policy, ExecutionPolicy):
        raise StudioExecutionCampaignError("typed original game and runtime policy required")
    root = Path(campaign)
    entries = []
    source_state = None
    halted = False
    if "source" in policy.stages:
        source_state = run_campaign(
            order, root, authorized=True,
            max_targets=policy.max_sources_per_run,
        )
        for target in order.targets:
            complete = target in source_state["completed_targets"]
            entries.append({
                "target": target, "stage": "source",
                "status": "verified" if complete else "blocked",
                "blocker": None if complete else source_state["failures"].get(
                    target, "source_not_yet_generated"
                ),
                # Exact source artifact digest is resolved from independently
                # checked assurance below, not substituted by campaign identity.
                "source_receipt_digest": None,
            })
        if policy.stop_after_blocker and any(x["status"] == "blocked" for x in entries):
            halted = True
    else:
        source_state = inspect_campaign(order, root)
    completed = set(source_state["completed_targets"])
    stage_operations: dict[str, Callable[[str], dict]] = {
        "rom": lambda target: qualify_campaign_target(
            order, root, target, authorized=True, execute=True,
            timeout_seconds=policy.timeout_seconds,
        ),
        "emulator": lambda target: qualify_campaign_emulator(
            order, root, target, authorized=True, execute=True,
            timeout_seconds=policy.timeout_seconds,
            max_frames=policy.max_emulator_frames,
        ),
        "browser": lambda target: qualify_campaign_browser(
            order, root, target, authorized=True, execute=True,
            timeout_seconds=policy.timeout_seconds,
        ),
        "godot": lambda target: qualify_campaign_godot(
            order, root, target, authorized=True, execute=True,
            timeout_seconds=policy.timeout_seconds,
        ),
        "canvas": lambda target: qualify_campaign_canvas(
            order, root, target, authorized=True,
            capture_consent=policy.capture_consent,
            execute=True, timeout_seconds=policy.timeout_seconds,
        ),
    }
    for stage in policy.stages:
        if stage == "source" or halted:
            continue
        for target in order.targets:
            outcome = None
            if target not in completed:
                status, blocker = "blocked", "original_source_missing"
                digest = None
            elif stage == "rom" and target not in _ROM_TARGETS:
                status, blocker, digest = "unsupported", "native_assembler_adapter_missing", None
            elif stage == "emulator" and target not in _EMULATOR_TARGETS:
                status, blocker, digest = "unsupported", "full_native_emulator_adapter_missing", None
            else:
                # Only canonical functions can qualify an execution. A raised
                # exception is a hard blocker, not an empty success receipt.
                try:
                    outcome = stage_operations[stage](target)
                    status, blocker = _stage_status(stage, outcome)
                    digest = outcome.get("evidence_digest") if status == "verified" else None
                except (OSError, ValueError, PermissionError, RuntimeError, ImportError) as exc:
                    status, blocker, digest = (
                        "blocked", "execution_exception:" + type(exc).__name__, None,
                    )
            entries.append({
                "target": target, "stage": stage, "status": status,
                "blocker": blocker, "evidence_digest": digest,
                "first_cpu_divergence": (
                    outcome.get("first_cpu_divergence")
                    if stage == "emulator" and outcome is not None else None
                ),
            })
            if policy.stop_after_blocker and status != "verified":
                halted = True
                break
        if halted:
            break
    # The assurance reader independently verifies and hashes the full actual
    # source+build+emulator+browser+Godot+canvas receipts before summarizing.
    report = inspect_production_assurance(order, root)
    from .studio_execution_history import validate_stage_evidence

    source_rows = {row["target"]: row for row in report["targets"]}
    for entry in entries:
        if entry["stage"] == "source" and entry["status"] == "verified":
            entry["source_receipt_digest"] = source_rows[entry["target"]][
                "source_receipt_digest"
            ]
    validate_stage_evidence(entries, report)
    body = {
        "schema": SCHEMA,
        "campaign_identity": report["campaign_identity"],
        "assurance_report_digest": report["report_digest"],
        "requested_stages": list(policy.stages),
        "total_source_targets": len(order.targets),
        "total_stage_attempts": len(entries),
        "verified_stage_attempts": sum(x["status"] == "verified" for x in entries),
        "blocked_stage_attempts": sum(x["status"] == "blocked" for x in entries),
        "unsupported_stage_attempts": sum(x["status"] == "unsupported" for x in entries),
        "interrupted_after_blocker": halted,
        "events": entries,
        "native_roms_verified": report["native_roms_structurally_verified"],
        "compiled_original_psg_tables_verified": (
            report["compiled_original_psg_tables_verified"]
        ),
        "compiled_cartridge_victories": report["native_rom_machine_code_playthroughs_verified"],
        "native_cpu_checkpoint_samples_verified": report["native_cpu_checkpoint_samples_verified"],
        "native_animation_audio_source_targets_checked": (
            report["original_console_media_sources_independently_checked"]
        ),
        "native_hero_animation_frames_in_source": (
            report["original_console_animation_frames_in_source"]
        ),
        "real_native_audio_capture_verified": False,
        "actual_browser_replays": report["browser_javascript_playthroughs_verified"],
        "actual_godot_replays": report["godot_headless_playthroughs_verified"],
        "actual_game_canvas_captures": report["generated_game_canvas_captures_verified"],
        "full_release_qualified": False,
        "physical_hardware_verified": False,
        "model_weights_updated": False,
        "automatically_promoted_dragon_knowledge": False,
    }
    return {**body, "run_digest": canonical_digest(body)}


__all__ = [
    "StudioExecutionCampaignError", "ExecutionPolicy",
    "run_studio_execution_campaign",
]
