"""Bounded native-confirmed counterfactual planning with a measured ROM world model.

A separately trained candidate neural model may PROPOSE action plans based on
speculative telemetry and predicted reward. Only physical emulator execution
can evaluate them. Plans are paired against exact-state neutral and policy
baselines; repeated independent source rollouts determine whether a difference
is reproducible. The model never invents game success or writes Q/LLM weights.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .game_learning import _digest, _json
from .game_learning_demonstrations import (
    current_observation, environment_snapshot_digest,
)
from .game_learning_parallel import GameEnvironmentRequest
from .game_emulator_neural_world import (
    SCHEMA as MODEL_SCHEMA,
    infer_neural_world_transition,
)

SCHEMA = "skeleton.game.emulator_planning_lab.v1"


class EmulatorPlanningError(ValueError):
    pass


@dataclass(frozen=True)
class EmulatorPlanningConfig:
    seed: int = 0
    anchors: int = 2
    horizon: int = 4
    beam_width: int = 8
    action_subset: int = 8
    proposal_count: int = 3
    repeats: int = 2
    max_actual_steps: int = 512
    objective: str = "measured_reward"

    def __post_init__(self) -> None:
        for key, lo, hi in (
            ("seed", 0, 2**63 - 1),
            ("anchors", 1, 4),
            ("horizon", 2, 8),
            ("beam_width", 1, 16),
            ("action_subset", 2, 16),
            ("proposal_count", 1, 6),
            ("repeats", 2, 4),
            ("max_actual_steps", 16, 4096),
        ):
            value = getattr(self, key)
            if type(value) is not int or not lo <= value <= hi:
                raise EmulatorPlanningError(f"{key} exceeds finite planning capacity")
        if self.objective not in (
            "measured_reward", "visual_activity", "audio_activity",
            "low_visual_activity",
        ):
            raise EmulatorPlanningError("planning objective is undeclared")
        if self.proposal_count > self.beam_width:
            raise EmulatorPlanningError("cannot request more proposals than beam capacity")


def _guard(
    cancel: Callable[[], bool] | None, authorize: Callable[[], None] | None,
) -> None:
    if cancel is not None and cancel():
        raise EmulatorPlanningError("physical planning execution was cancelled")
    if authorize is not None:
        authorize()


def _sample_distance(one: Mapping[str, float], two: Mapping[str, float]) -> float:
    if set(one) != set(two) or not one:
        raise EmulatorPlanningError("native and model state feature sets differ")
    return math.fsum(abs(one[name] - two[name]) for name in one) / len(one)


def _objective_score(
    objective: str, before: Mapping[str, float], next_: Mapping[str, float],
    reward: float,
) -> float:
    if objective == "measured_reward":
        return reward
    if objective == "visual_activity":
        return next_.get("motion_energy", next_.get("visual_change", 0.0))
    if objective == "audio_activity":
        return next_.get("audio_rms", 0.0)
    if objective == "low_visual_activity":
        return -next_.get("motion_energy", next_.get("visual_change", 0.0))
    raise EmulatorPlanningError("unsupported source-controlled planning objective")


def _beam_search(
    model: Mapping[str, Any], observation: Mapping[str, float],
    actions: tuple[str, ...], config: EmulatorPlanningConfig,
) -> tuple[list[dict[str, Any]], int]:
    """Predict only. All proposed gains remain explicitly speculative."""
    frontier = [(0.0, tuple(), dict(observation), [])]
    proposed = 0
    for depth in range(config.horizon):
        possibilities = []
        for score, sequence, predicted, per_step in frontier:
            for action in actions:
                raw = infer_neural_world_transition(model, predicted, action)
                next_ = raw["predicted_next_observation"]
                reward = raw["predicted_one_step_reward"]
                if (
                    not math.isfinite(reward)
                    or abs(reward) > 1e8
                    or any(not math.isfinite(value) or abs(value) > 1e8 for value in next_.values())
                ):
                    raise EmulatorPlanningError("neural proposal left finite training feature bounds")
                contribution = _objective_score(config.objective, predicted, next_, reward)
                if not math.isfinite(contribution):
                    raise EmulatorPlanningError("nonfinite candidate objective")
                # Discounted finite step score; this is not an inferred win.
                candidate_score = score + 0.97 ** depth * contribution
                proposal = (
                    candidate_score,
                    sequence + (action,),
                    next_,
                    per_step + [{
                        "predicted_reward": reward,
                        "proposed_objective_contribution": contribution,
                        "speculative_next_observation": next_,
                    }],
                )
                possibilities.append(proposal)
                proposed += 1
        if proposed > config.horizon * config.beam_width * config.action_subset:
            raise EmulatorPlanningError("predicted search exceeded finite planning envelope")
        # Ties follow the same seeded, source-independent order every time.
        frontier = sorted(
            possibilities,
            key=lambda row: (-row[0], _digest([config.seed, row[1]])),
        )[: config.beam_width]
    result = []
    for score, sequence, state, rows in frontier[: config.proposal_count]:
        result.append({
            "actions": list(sequence),
            "predicted_discounted_objective": score,
            "predicted_end_observation": state,
            "speculative_rollout": rows,
            "source_executed": False,
        })
    return result, proposed


def _observed(
    env: Any, origin: Mapping[str, Any],
    before: Mapping[str, float], actions: Sequence[str], objective: str,
    *,
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
) -> dict[str, Any]:
    _guard(cancel, authorize)
    observed = current_observation(env, env.restore(origin))
    if observed != dict(before):
        raise EmulatorPlanningError("physical rollout began from a different actual source state")
    value = 0.0
    measurements = []
    frames = []
    ended_before_horizon = False
    for index, action in enumerate(actions):
        _guard(cancel, authorize)
        step = env.step(action)
        after = dict(step.observation)
        if set(after) != set(before):
            raise EmulatorPlanningError("native source signal basis diverged from model features")
        if not math.isfinite(step.reward):
            raise EmulatorPlanningError("physical emulator return is nonfinite")
        info = dict(step.info)
        evidence = info.get("evidence", {})
        if isinstance(evidence, Mapping) and evidence.get("frame_digest"):
            frame = evidence["frame_digest"]
        else:
            from .game_emulator_training_lab import _frame_digest
            frame = _frame_digest(env, step)
        if type(frame) is not str or len(frame) != 64:
            raise EmulatorPlanningError("physical frame provenance not recorded")
        actual_contribution = _objective_score(objective, observed, after, step.reward)
        value += 0.97 ** index * actual_contribution
        measurements.append({
            "sequence": index + 1,
            "action": action,
            "native_frame_sha256": frame,
            "actual_observation": after,
            "actual_reward": step.reward,
            "actual_objective": actual_contribution,
            "native_transition_digest": step.transition_digest or None,
        })
        frames.append(frame)
        observed = after
        if step.terminated or step.truncated:
            ended_before_horizon = index + 1 < len(actions)
            break
    return {
        "ended_before_horizon": ended_before_horizon,
        "actions_requested": list(actions),
        "real_steps": len(measurements),
        "actual_discounted_objective": value,
        "source_frame_trace_digest": _digest(frames),
        "source_end_snapshot_digest": environment_snapshot_digest(env),
        "actual_end_observation": observed,
        "transition_receipts": measurements,
    }


def run_native_confirmed_planning(
    request: GameEnvironmentRequest, *,
    model: Mapping[str, Any], training_report: Mapping[str, Any],
    rights_acknowledged: bool,
    config: EmulatorPlanningConfig = EmulatorPlanningConfig(),
    cancel: Callable[[], bool] | None = None,
    authorize: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Rehearse model-suggested moves in a real ROM without assuming game skill."""
    if not isinstance(request, GameEnvironmentRequest) or request.kind not in ("libretro", "builtin"):
        raise EmulatorPlanningError("actual ROM or approved libretro source required")
    if (
        request.kind == "builtin"
        and (request.rom_source is None or request.target_id not in ("game_boy", "dragon_native:game_boy"))
    ):
        raise EmulatorPlanningError("reference mock games cannot certify neural gameplay predictions")
    if rights_acknowledged is not True or not isinstance(config, EmulatorPlanningConfig):
        raise EmulatorPlanningError("operator rights and typed planning budget are required")
    if not isinstance(model, Mapping) or model.get("schema_version") != MODEL_SCHEMA:
        raise EmulatorPlanningError("source-bound trained emulator neural candidate required")
    parent = dict(model)
    model_digest = parent.pop("model_digest", None)
    if _digest(parent) != model_digest:
        raise EmulatorPlanningError("candidate neural parameters are not checksum-bound")
    if (
        not isinstance(training_report, Mapping)
        or training_report.get("world_model_digest") != model_digest
        or training_report.get("report_digest") != _digest({
            key: val for key, val in training_report.items() if key != "report_digest"
        })
        or training_report.get("candidate_status") != "candidate_predictive_gain_measured"
        or model.get("measured_predictive_gate") != "candidate_predictive_gain_measured"
    ):
        raise EmulatorPlanningError("unqualified or mismatched neural candidate cannot direct source actions")
    if request.max_steps < config.anchors - 1 + config.horizon:
        raise EmulatorPlanningError("real episode cannot contain the anchor prefix and full proposed horizon")
    if config.objective == "audio_activity" and "audio_rms" not in model.get("observation_features", []):
        raise EmulatorPlanningError("audio objective requires real measured native audio channels")
    _guard(cancel, authorize)
    env = request.build(cancel=cancel)
    try:
        if env.spec.environment_digest != model.get("source_environment_digest"):
            raise EmulatorPlanningError("model source core, content or sensor basis changed")
        if list(env.spec.observation_bins) != model.get("observation_features"):
            raise EmulatorPlanningError("model trained on a different numeric sensor layout")
        allowed = tuple(name for name in model.get("actions", []) if name in env.spec.actions)
        if set(allowed) != set(env.spec.actions) or len(allowed) < 2:
            raise EmulatorPlanningError("neural model controller vocabulary differs")
        actions = allowed[: config.action_subset]
        if not actions:
            raise EmulatorPlanningError("no matching authorized controller actions")
        neutral = "idle" if "idle" in allowed else allowed[0]
        expected = config.anchors * config.repeats * config.horizon * (config.proposal_count + 1)
        expected += config.anchors - 1
        if expected > config.max_actual_steps:
            raise EmulatorPlanningError("actual native validation matrix exceeds requested budget")
        now = current_observation(env, env.reset(config.seed))
        anchors = []
        for index in range(config.anchors):
            _guard(cancel, authorize)
            anchors.append({
                "index": index,
                "start_snapshot": env.snapshot(),
                "observation": dict(now),
            })
            if index < config.anchors - 1:
                real = env.step(allowed[index % len(allowed)])
                if real.terminated or real.truncated:
                    raise EmulatorPlanningError("native source terminated before experiment anchor")
                now = dict(real.observation)
        proven = []
        total_steps = config.anchors - 1
        predicted_nodes = 0
        for anchor in anchors:
            candidates, count = _beam_search(model, anchor["observation"], actions, config)
            predicted_nodes += count
            baseline_actions = [neutral] * config.horizon
            base_trials = [
                _observed(
                    env, anchor["start_snapshot"], anchor["observation"],
                    baseline_actions, config.objective,
                    cancel=cancel, authorize=authorize,
                )
                for _ in range(config.repeats)
            ]
            total_steps += sum(row["real_steps"] for row in base_trials)
            baseline_stable = len({
                (item["source_frame_trace_digest"], item["source_end_snapshot_digest"],
                 item["actual_discounted_objective"])
                for item in base_trials
            }) == 1
            verified = []
            for candidate in candidates:
                trials = [
                    _observed(
                        env, anchor["start_snapshot"], anchor["observation"],
                        candidate["actions"], config.objective,
                        cancel=cancel, authorize=authorize,
                    )
                    for _ in range(config.repeats)
                ]
                total_steps += sum(row["real_steps"] for row in trials)
                if total_steps > config.max_actual_steps:
                    raise EmulatorPlanningError("source execution exceeded bounded actual step count")
                stable = len({
                    (item["source_frame_trace_digest"], item["source_end_snapshot_digest"],
                     item["actual_discounted_objective"])
                    for item in trials
                }) == 1
                full_length_observed = all(
                    not trial["ended_before_horizon"]
                    and trial["real_steps"] == config.horizon
                    for trial in trials + base_trials
                )
                paired_gain = [
                    trial["actual_discounted_objective"] - baseline["actual_discounted_objective"]
                    for trial, baseline in zip(trials, base_trials, strict=True)
                ]
                prediction_errors = [
                    _sample_distance(trial["actual_end_observation"],
                                     candidate["predicted_end_observation"])
                    for trial in trials
                ]
                verified.append({
                    "suggestion": candidate,
                    "real_trials": trials,
                    "source_replay_stable": stable,
                    "baseline_replay_stable": baseline_stable,
                    "full_proposed_horizon_executed": full_length_observed,
                    "measured_gain_over_neutral": paired_gain,
                    "mean_end_observation_prediction_error": math.fsum(prediction_errors) / len(prediction_errors),
                    "actual_measured_positive_gain": (
                        stable and baseline_stable and full_length_observed
                        and all(gain > 0 for gain in paired_gain)
                    ),
                    "semantic_game_success_certified": False,
                    "policy_or_neural_weights_promoted": False,
                })
            proven.append({
                "anchor_index": anchor["index"],
                "source_snapshot_digest": _digest(anchor["start_snapshot"]),
                "physical_neutral_trials": base_trials,
                "baseline_stable": baseline_stable,
                "model_proposals_physically_checked": verified,
            })
        report = {
            "schema_version": SCHEMA,
            "actual_rom_environment_digest": env.spec.environment_digest,
            "source_rom_request_digest": request.digest,
            "source_neural_candidate_digest": model_digest,
            "source_neural_training_report_digest": training_report["report_digest"],
            "objective": config.objective,
            "native_source_execution": True,
            "source_anchors": len(proven),
            "independent_trial_repetitions": config.repeats,
            "real_emulator_steps": total_steps,
            "speculative_search_nodes": predicted_nodes,
            "actual_positive_plans": sum(
                case["actual_measured_positive_gain"]
                for anchor in proven for case in anchor["model_proposals_physically_checked"]
            ),
            "tested_plan_count": config.anchors * config.proposal_count,
            "physical_evidence": proven,
            "limitations": {
                "no_game_objective_labels": True,
                "no_claim_of_general_skill": True,
                "visual_reward_can_be_gamed_by_flashing": True,
                "heldout_predictive_gain_is_not_gameplay_success": True,
                "neural_or_q_weight_updates": 0,
                "production_jeeves_promotion": False,
                "hardware_fidelity_certified": False,
                "rights_independently_verified": False,
            },
        }
        report["report_digest"] = _digest(report)
        _json(report, limit=8 * 1024 * 1024)
        return report
    finally:
        close = getattr(env, "close", None)
        if callable(close):
            close()
