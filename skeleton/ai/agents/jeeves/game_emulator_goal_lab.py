"""Native memory-grounded, operator-defined game objective experiments.

No game victory state is invented. The operator provides bounded memory
addresses, concrete bit/threshold predicates and an explicit claim about
their meaning. The approved emulator reads actual bytes before/after each
exact-state intervention and neutral control. Repeated differences can be
measured, but semantic correctness and causal certainty are not asserted.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .game_learning import _digest, _json
from .game_learning_demonstrations import (
    current_observation, environment_snapshot_digest,
)
from .game_learning_parallel import GameEnvironmentRequest

SCHEMA = "skeleton.game.emulator_operator_goal_experiments.v1"


class EmulatorGoalError(ValueError):
    pass


def _bounded(value: Any, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise EmulatorGoalError(f"{name} exceeds its finite capacity")
    return value


@dataclass(frozen=True)
class MemoryGoal:
    """An operator's hypothesis, not a trusted game-success predicate."""

    label: str
    region: int
    offset: int
    bytes_per_value: int = 2
    direction: str = "increase"
    threshold: int = 1
    mask: int = 0
    signed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not 1 <= len(self.label) <= 64:
            raise EmulatorGoalError("a named operator-provided objective is required")
        _bounded(self.region, "native memory region", 0, 3)
        _bounded(self.offset, "memory offset", 0, 256 * 1024**2)
        if type(self.bytes_per_value) is not int or self.bytes_per_value not in (1, 2, 4):
            raise EmulatorGoalError("memory observation width must be 1, 2 or 4 bytes")
        if type(self.signed) is not bool:
            raise EmulatorGoalError("signedness must be explicit")
        if self.direction not in ("increase", "decrease", "at_least", "at_most", "bit_set", "bit_clear"):
            raise EmulatorGoalError("unsupported operator memory hypothesis direction")
        cap = 2 ** (8 * self.bytes_per_value)
        _bounded(self.threshold, "objective threshold", 0, cap - 1)
        if self.direction in ("increase", "decrease") and self.threshold == 0:
            raise EmulatorGoalError("real increase/decrease requires at least one changed unit")
        _bounded(self.mask, "operator-selected bitmask", 0, cap - 1)
        if self.direction.startswith("bit_") and (self.mask == 0 or self.signed):
            raise EmulatorGoalError("bit predicates require a nonzero unsigned memory mask")


@dataclass(frozen=True)
class GoalExperimentConfig:
    seed: int = 0
    anchors: int = 2
    repeats: int = 2
    horizon: int = 6
    max_actual_steps: int = 2048

    def __post_init__(self) -> None:
        for name, lo, hi in (
            ("seed", 0, 2**63 - 1),
            ("anchors", 1, 4),
            ("repeats", 2, 4),
            ("horizon", 1, 32),
            ("max_actual_steps", 8, 8192),
        ):
            _bounded(getattr(self, name), name, lo, hi)


def _guard(
    cancel: Callable[[], bool] | None, authorize: Callable[[], None] | None,
) -> None:
    if cancel is not None and cancel():
        raise EmulatorGoalError("native goal probe cancelled")
    if authorize is not None:
        authorize()


def _read_goal(env: Any, goal: MemoryGoal) -> dict[str, Any]:
    method = getattr(env, "read_memory", None)
    if not callable(method):
        raise EmulatorGoalError("approved native libretro memory read interface is unavailable")
    blob = method(goal.region, goal.offset, goal.bytes_per_value)
    if not isinstance(blob, bytes) or len(blob) != goal.bytes_per_value:
        raise EmulatorGoalError("game-provided native memory region was not readable")
    number = int.from_bytes(blob, "little", signed=goal.signed)
    return {
        "label": goal.label,
        "declared_address": {"region": goal.region, "offset": goal.offset, "width": goal.bytes_per_value},
        "native_memory_sha256": hashlib.sha256(blob).hexdigest(),
        "operator_measured_number": number,
        "operator_game_semantics_verified": False,
    }


def _goal_change(before: int, after: int, goal: MemoryGoal) -> dict[str, Any]:
    if goal.direction == "increase":
        matched = after - before >= goal.threshold
    elif goal.direction == "decrease":
        matched = before - after >= goal.threshold
    elif goal.direction == "at_least":
        matched = after >= goal.threshold
    elif goal.direction == "at_most":
        matched = after <= goal.threshold
    elif goal.direction == "bit_set":
        matched = (after & goal.mask) == goal.mask
    else:
        matched = (after & goal.mask) == 0
    return {
        "label": goal.label,
        "before": before,
        "after": after,
        "signed_delta": after - before,
        "operator_predicate_matched": bool(matched),
        "semantic_game_outcome_certified": False,
    }


def _run(
    env: Any, snapshot: Mapping[str, Any], initial_observation: Mapping[str, float],
    controls: Sequence[str], goals: Sequence[MemoryGoal], *,
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
) -> dict[str, Any]:
    _guard(cancel, authorize)
    actual = current_observation(env, env.restore(snapshot))
    if dict(actual) != dict(initial_observation):
        raise EmulatorGoalError("native memory comparison started from a foreign emulator state")
    starts = [_read_goal(env, goal) for goal in goals]
    frames = []
    transitions = []
    for index, action in enumerate(controls):
        _guard(cancel, authorize)
        step = env.step(action)
        evidence = step.info.get("evidence", {})
        if not isinstance(evidence, Mapping) or not isinstance(evidence.get("frame_digest"), str):
            raise EmulatorGoalError("native physical ROM frame identity is missing")
        frame = evidence["frame_digest"]
        if len(frame) != 64 or any(ch not in "0123456789abcdef" for ch in frame):
            raise EmulatorGoalError("source game frame identity is invalid")
        transitions.append({
            "sequence": index + 1,
            "action": action,
            "real_reward": step.reward,
            "native_transition_digest": step.transition_digest,
            "source_frame_sha256": frame,
            "ended": step.terminated or step.truncated,
        })
        frames.append(frame)
        if step.terminated or step.truncated:
            break
    ends = [_read_goal(env, goal) for goal in goals]
    evidence = {
        "real_steps": len(transitions),
        "completed_horizon": len(transitions) == len(controls),
        "native_frame_sequence_sha256": _digest(frames),
        "final_native_state_sha256": environment_snapshot_digest(env),
        "actual_source_transitions": transitions,
        "source_memory_witnesses": [
            {
                "source_start": start,
                "source_end": end,
                "measured_test": _goal_change(
                    start["operator_measured_number"], end["operator_measured_number"], goal,
                ),
            }
            for goal, start, end in zip(goals, starts, ends, strict=True)
        ],
    }
    evidence["experiment_digest"] = _digest(evidence)
    return evidence


def evaluate_operator_native_goals(
    request: GameEnvironmentRequest, *,
    goals: Sequence[MemoryGoal],
    interventions: Mapping[str, Sequence[str]],
    rights_acknowledged: bool,
    source_authority: str,
    config: GoalExperimentConfig = GoalExperimentConfig(),
    cancel: Callable[[], bool] | None = None,
    authorize: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Source-measured objective comparisons; human semantic claims remain unverified."""
    if (
        not isinstance(request, GameEnvironmentRequest) or request.kind != "libretro"
        or rights_acknowledged is not True
        or not isinstance(config, GoalExperimentConfig)
        or not isinstance(source_authority, str) or not 1 <= len(source_authority) <= 256
    ):
        raise EmulatorGoalError("approved native ROM, explicit source rights and operator objective authority required")
    if (
        type(goals) not in (tuple, list) or not 1 <= len(goals) <= 8
        or any(not isinstance(goal, MemoryGoal) for goal in goals)
        or len({goal.label for goal in goals}) != len(goals)
    ):
        raise EmulatorGoalError("goal probes must be bounded unique operator hypotheses")
    if (
        not isinstance(interventions, Mapping) or not 1 <= len(interventions) <= 12
        or any(
            not isinstance(label, str) or not 1 <= len(label) <= 64
            or not isinstance(sequence, (tuple, list)) or not 1 <= len(sequence) <= config.horizon
            or any(not isinstance(action, str) or not action for action in sequence)
            for label, sequence in interventions.items()
        )
    ):
        raise EmulatorGoalError("finite action-sequence intervention map required")
    if request.max_steps < config.anchors - 1 + config.horizon:
        raise EmulatorGoalError("native episode cannot contain all state anchors and full trial horizons")
    num_steps = config.anchors - 1 + config.anchors * config.repeats * (
        config.horizon * (1 + len(interventions))
    )
    if num_steps > config.max_actual_steps:
        raise EmulatorGoalError("native goal experiment exceeds declared source-step budget")
    _guard(cancel, authorize)
    env = request.build(cancel=cancel)
    try:
        action_basis = tuple(env.spec.actions)
        if "idle" not in action_basis or any(
            action not in action_basis for seq in interventions.values() for action in seq
        ):
            raise EmulatorGoalError("all comparison controls must be present in the approved native action basis")
        observation = dict(env.reset(config.seed))
        anchors = []
        for ordinal in range(config.anchors):
            _guard(cancel, authorize)
            anchor = env.snapshot()
            anchors.append((anchor, dict(observation)))
            if ordinal < config.anchors - 1:
                next_ = env.step("idle")
                if next_.terminated or next_.truncated:
                    raise EmulatorGoalError("source terminated while recording goal observation anchors")
                observation = dict(next_.observation)
        results = []
        measured_steps = config.anchors - 1
        for ordinal, (anchor, initial) in enumerate(anchors):
            neutral_controls = ["idle"] * config.horizon
            neutral = [
                _run(env, anchor, initial, neutral_controls, goals, cancel=cancel, authorize=authorize)
                for _ in range(config.repeats)
            ]
            measured_steps += sum(item["real_steps"] for item in neutral)
            outcomes = []
            for label, controls in interventions.items():
                active_controls = list(controls) + ["idle"] * (config.horizon - len(controls))
                matched = [
                    _run(env, anchor, initial, active_controls, goals, cancel=cancel, authorize=authorize)
                    for _ in range(config.repeats)
                ]
                measured_steps += sum(item["real_steps"] for item in matched)
                if measured_steps > config.max_actual_steps:
                    raise EmulatorGoalError("native objective probes exceeded actual emulator step budget")
                proofs = []
                for goal_index, goal in enumerate(goals):
                    active = [
                        item["source_memory_witnesses"][goal_index]["measured_test"]["operator_predicate_matched"]
                        for item in matched
                    ]
                    passive = [
                        item["source_memory_witnesses"][goal_index]["measured_test"]["operator_predicate_matched"]
                        for item in neutral
                    ]
                    active_stable = len({
                        (item["final_native_state_sha256"], item["native_frame_sequence_sha256"],
                         item["source_memory_witnesses"][goal_index]["source_end"]["native_memory_sha256"])
                        for item in matched
                    }) == 1
                    neutral_stable = len({
                        (item["final_native_state_sha256"], item["native_frame_sequence_sha256"],
                         item["source_memory_witnesses"][goal_index]["source_end"]["native_memory_sha256"])
                        for item in neutral
                    }) == 1
                    proofs.append({
                        "label": goal.label,
                        "all_active_repetitions_match_operator_predicate": all(active),
                        "any_passive_repetition_matches_operator_predicate": any(passive),
                        "active_exact_replay_stable": active_stable,
                        "passive_exact_replay_stable": neutral_stable,
                        "active_horizon_fully_executed": all(item["completed_horizon"] for item in matched),
                        "neutral_horizon_fully_executed": all(item["completed_horizon"] for item in neutral),
                        "measured_active_only_goal_difference": (
                            all(active) and not any(passive) and active_stable and neutral_stable
                            and all(item["completed_horizon"] for item in matched + neutral)
                        ),
                        "game_goal_semantics_independently_proven": False,
                        "causation_independently_proven": False,
                    })
                outcomes.append({
                    "operator_intervention": label,
                    "requested_actions": list(controls),
                    "executed_horizon_actions": active_controls,
                    "source_active_repetitions": matched,
                    "operator_goal_contrasts": proofs,
                })
            results.append({
                "anchor_index": ordinal,
                "anchor_source_snapshot_sha256": _digest(anchor),
                "source_neutral_repetitions": neutral,
                "interventions": outcomes,
            })
        report = {
            "schema_version": SCHEMA,
            "rom_environment_digest": env.spec.environment_digest,
            "request_digest": request.digest,
            "operator_source_authority": source_authority,
            "source_rights_asserted": True,
            "operator_goals": [
                {
                    "label": goal.label, "region": goal.region, "offset": goal.offset,
                    "value_width": goal.bytes_per_value,
                    "direction": goal.direction,
                    "threshold": goal.threshold,
                    "mask": goal.mask,
                    "signed": goal.signed,
                }
                for goal in goals
            ],
            "actual_source_steps": measured_steps,
            "source_anchors": results,
            "measured_active_only_goal_contrasts": sum(
                probe["measured_active_only_goal_difference"]
                for anchor in results for trial in anchor["interventions"]
                for probe in trial["operator_goal_contrasts"]
            ),
            "semantics": {
                "memory_values_from_actual_approved_core": True,
                "goals_user_defined_not_automatically_discovered": True,
                "game_meanings_independently_certified": False,
                "production_reward_safety_certified": False,
                "neural_or_transformer_training_updates": 0,
                "policy_or_model_promotion": False,
            },
        }
        report["report_digest"] = _digest(report)
        _json(report, limit=8 * 1024 * 1024)
        return report
    finally:
        close = getattr(env, "close", None)
        if callable(close):
            close()
