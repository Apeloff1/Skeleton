"""Original/native emulator comparative evidence from real controlled game steps.

Up to 30 approved real-ROM environments arranged in waves of ten. Each is
run separately (not 10 concurrent untrusted cores), exactly replaying the
same limited controller programs from its own saved state. Cross-platform
measurements are not assumed to be commensurable rewards, equivalent frame
pixels, gameplay mastery, neural training, or an inferred game design clone.

No external game fetching, provider AI inference or background execution.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .game_learning_parallel import GameEnvironmentRequest

SCHEMA = "skeleton.game.cross_emulator_controlled_observation.v1"
ALLOWED_ACTIONS = frozenset((
    "idle", "left", "right", "up", "down", "a", "b",
    "start", "select", "a_right", "a_left",
))
MAX_GAME_LIBRARY = 30
MAX_ACTIVE_WAVE = 10
MAX_PROGRAMS = 6
MAX_PROGRAM_ACTIONS = 8
MAX_TOTAL_ACTIONS = 32
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_PREVIEW_PIXEL_BYTES = 8 * 1024 * 1024


class CrossGameComparisonError(ValueError):
    """Invalid controlled comparison, unverifiable source or failed replay."""


@dataclass(frozen=True, slots=True)
class CrossGameConfig:
    seed: int = 42
    games_per_wave: int = 10

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed < 2**63:
            raise CrossGameComparisonError("comparison seed must be a finite 63-bit integer")
        if type(self.games_per_wave) is not int or not 2 <= self.games_per_wave <= MAX_ACTIVE_WAVE:
            raise CrossGameComparisonError("at most ten source ROM environments per wave")


def _encoded(value: object) -> bytes:
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ensure_ascii=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise CrossGameComparisonError("emulator evidence is not bounded deterministic JSON") from exc
    if len(payload) > MAX_REPORT_BYTES:
        raise CrossGameComparisonError("comparison source evidence exceeds bounded bytes")
    return payload


def _digest(value: object) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _sha(value: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise CrossGameComparisonError("source emulator digest is not an exact SHA256")
    return value


def _validate(
    requests: Sequence[GameEnvironmentRequest],
    programs: Sequence[Sequence[str]],
    config: CrossGameConfig,
    rights_acknowledged: bool,
) -> tuple[tuple[GameEnvironmentRequest, ...], tuple[tuple[str, ...], ...]]:
    if rights_acknowledged is not True or not isinstance(config, CrossGameConfig):
        raise CrossGameComparisonError("explicit lawful ROM use and finite comparison config required")
    if not isinstance(requests, (list, tuple)) or not 2 <= len(requests) <= MAX_GAME_LIBRARY:
        raise CrossGameComparisonError("cross-game library requires 2 to 30 actual ROM requests")
    admitted = tuple(requests)
    if any(
        not isinstance(row, GameEnvironmentRequest)
        or row.kind not in ("libretro", "builtin")
        or row.kind == "builtin" and (
            row.rom_source is None or row.target_id not in ("game_boy", "dragon_native:game_boy")
        )
        for row in admitted
    ):
        raise CrossGameComparisonError("original cartridge or approved native libretro requests only")
    identity = [row.digest for row in admitted]
    if len(set(identity)) != len(identity):
        raise CrossGameComparisonError("the same source ROM request cannot inflate comparison coverage")
    if not isinstance(programs, (list, tuple)) or not 2 <= len(programs) <= MAX_PROGRAMS:
        raise CrossGameComparisonError("finite 2..6 controller programs required")
    normalized = []
    for actions in programs:
        if (
            not isinstance(actions, (tuple, list))
            or not 1 <= len(actions) <= MAX_PROGRAM_ACTIONS
            or any(type(action) is not str or action not in ALLOWED_ACTIONS for action in actions)
        ):
            raise CrossGameComparisonError("controller program uses an unsupported action or exceeds eight steps")
        normalized.append(tuple(actions))
    if normalized[0] != ("idle",) or len(set(normalized)) != len(normalized):
        raise CrossGameComparisonError("first program must be passive idle and no program may repeat")
    if sum(map(len, normalized)) > MAX_TOTAL_ACTIONS:
        raise CrossGameComparisonError("cumulative controlled action budget exceeds 32")
    if any(req.max_steps < max(map(len, normalized)) for req in admitted):
        raise CrossGameComparisonError("source episode budget shorter than controlled program")
    return admitted, tuple(normalized)


def _frame(environment: Any) -> str:
    preview = environment.preview()
    if not isinstance(preview, Mapping):
        raise CrossGameComparisonError("actual source frame preview required")
    if isinstance(preview.get("pixels_base64"), str):
        try:
            pixels = base64.b64decode(preview["pixels_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise CrossGameComparisonError("actual frame pixel encoding invalid") from exc
        if not 1 <= len(pixels) <= MAX_PREVIEW_PIXEL_BYTES:
            raise CrossGameComparisonError("decoded source frame pixel budget invalid")
        return hashlib.sha256(pixels).hexdigest()
    return _sha(preview.get("source_pixel_digest"))


def _snapshot(environment: Any) -> tuple[Mapping[str, Any], str]:
    snapshot = environment.snapshot()
    if not isinstance(snapshot, Mapping):
        raise CrossGameComparisonError("real emulator lacks exact CPU/core savestate")
    # Never include content/savestate bytes in the resulting comparison
    # output. Hash only the private same-source state representation.
    return snapshot, _digest(snapshot)


def _run_program(environment: Any, start: Mapping[str, Any], program: tuple[str, ...]) -> dict[str, Any]:
    before = environment.restore(start)
    if not isinstance(before, Mapping):
        raise CrossGameComparisonError("emulator failed to restore exact observation")
    state_before, digest_before = _snapshot(environment)
    if _digest(start) != digest_before:
        raise CrossGameComparisonError("same-core restore changed exact pre-intervention source state")
    previous_frame = _frame(environment)
    transitions, visual_changes, initial_frame = [], 0, previous_frame
    for sequence, action in enumerate(program):
        step = environment.step(action)
        frame = _frame(environment)
        visual_changes += frame != previous_frame
        previous_frame = frame
        if not isinstance(step.observation, Mapping) or not isinstance(step.reward_components, Mapping):
            raise CrossGameComparisonError("source step has no actual reward/observation contract")
        reward = {str(k): float(v) for k, v in step.reward_components.items()}
        if any(not math.isfinite(value) for value in reward.values()):
            raise CrossGameComparisonError("source game reward is not finite")
        transitions.append({
            "ordinal": sequence,
            "action": action,
            "actual_frame_sha256": frame,
            "source_observation_sha256": _digest(dict(step.observation)),
            "source_reward_components_sha256": _digest(reward),
            "actual_transition_sha256": _sha(step.transition_digest),
            "terminated": step.terminated,
            "truncated": step.truncated,
        })
        if (step.terminated or step.truncated) and sequence + 1 != len(program):
            raise CrossGameComparisonError("controlled program crosses a true source episode termination")
    _, end_digest = _snapshot(environment)
    result = {
        "source_start_snapshot_sha256": digest_before,
        "source_end_snapshot_sha256": end_digest,
        "initial_frame_sha256": initial_frame,
        "final_frame_sha256": previous_frame,
        "actual_frame_change_events": visual_changes,
        "actual_executed_steps": len(program),
        "source_step_receipts": transitions,
    }
    result["source_program_digest"] = _digest(result)
    return result


def compare_real_emulator_games(
    requests: Sequence[GameEnvironmentRequest],
    programs: Sequence[Sequence[str]],
    *,
    rights_acknowledged: bool,
    config: CrossGameConfig = CrossGameConfig(),
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Run each approved source independently; compare measured phenomena only.

    All accepted results MUST replay exactly. Failures prevent a successful
    comparison report; neither one core's success nor a shared screenshot
    grants approval to another core/game/CPU environment.
    """
    admitted, programs = _validate(requests, programs, config, rights_acknowledged)
    compared = []
    for offset, request in enumerate(admitted):
        if cancel is not None and cancel():
            raise CrossGameComparisonError("real cross-emulator inspection cancelled")
        environment = request.build(cancel=cancel)
        try:
            spec = environment.spec
            if any(action not in spec.actions for program in programs for action in program):
                raise CrossGameComparisonError("controller program is not available in every actual source emulator")
            seed = config.seed  # same requested reset seed; never equate game-specific RAM states
            environment.reset(seed=seed)
            checkpoint, source_sha = _snapshot(environment)
            identities = []
            for program in programs:
                if cancel is not None and cancel():
                    raise CrossGameComparisonError("source controlled replay cancelled")
                first = _run_program(environment, checkpoint, program)
                replay = _run_program(environment, checkpoint, program)
                if first != replay:
                    raise CrossGameComparisonError("actual source game branch or frame digest changed after replay")
                identities.append({
                    "controller_program": list(program),
                    "actual_replayed_source_passes": 2,
                    "exact_source_replay_verified": True,
                    "real_steps_executed": 2 * len(program),
                    "actual_frame_change_events": first["actual_frame_change_events"],
                    "source_program_digest": first["source_program_digest"],
                    "source_before_sha256": source_sha,
                    "source_after_sha256": first["source_end_snapshot_sha256"],
                    "controlled_source_step_receipts": first["source_step_receipts"],
                    "observed_visual_change_rate": first["actual_frame_change_events"] / len(program),
                })
            compared.append({
                "game_index": offset,
                "wave": offset // config.games_per_wave,
                "request_digest": request.digest,
                "environment_digest": _sha(spec.environment_digest),
                "target_id": request.target_id,
                "core_id": request.core_id if request.kind == "libretro" else None,
                "source_kind": request.kind,
                "actual_start_snapshot_sha256": source_sha,
                "controller_programs": identities,
            })
        finally:
            close = getattr(environment, "close", None)
            if callable(close):
                close()
    comparisons = []
    for i in range(len(compared)):
        for j in range(i + 1, len(compared)):
            left, right = compared[i], compared[j]
            comparisons.append({
                "left_game_index": i,
                "right_game_index": j,
                "same_target_platform": left["target_id"] == right["target_id"],
                "same_source_environment": left["environment_digest"] == right["environment_digest"],
                "controlled_programs_matched": len(programs),
                "visual_event_rate_differences": [
                    round(
                        a["observed_visual_change_rate"] - b["observed_visual_change_rate"], 6
                    )
                    for a, b in zip(left["controller_programs"], right["controller_programs"], strict=True)
                ],
                "pixel_content_directly_comparable": False,
                "gameplay_skill_or_causation_established": False,
            })
    result = {
        "schema_version": SCHEMA,
        "status": "measured_source_emulator_controller_comparison",
        "explicit_source_rights_acknowledged": True,
        "selected_games": len(admitted),
        "max_selected_game_capacity": MAX_GAME_LIBRARY,
        "games_per_sequential_wave": config.games_per_wave,
        "actual_native_executions_concurrent": 1,
        "completed_sequential_waves": (len(admitted) + config.games_per_wave - 1) // config.games_per_wave,
        "controlled_programs": [list(p) for p in programs],
        "actual_replayed_game_programs": len(admitted) * len(programs) * 2,
        "actual_source_action_steps": len(admitted) * sum(map(len, programs)) * 2,
        "game_receipts": compared,
        "pairwise_measured_evidence": comparisons,
        "cross_game_rewards_equivalent": False,
        "ai_training_gradient_updates": 0,
        "neural_model_promotion_authorized": False,
        "trained_game_design_synthesis_proven": False,
    }
    result["report_digest"] = _digest(result)
    return result
