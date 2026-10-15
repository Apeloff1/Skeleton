"""Source-executed counterfactual emulator experiment matrix for AI research.

Actual libretro/DMG state -> controlled action sequences -> exact repeats ->
action-duration/order/port comparisons -> bounded replay + sensor receipts.

Semantic game achievements, cutscenes, rewards and skills are NOT inferred
from pixel changes alone. These results are research evidence, not updates
to neural weights, human imitation receipts or production model authority.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .game_learning import _digest, _json
from .game_learning_demonstrations import (
    current_observation,
    environment_snapshot_digest,
)
from .game_learning_parallel import GameEnvironmentRequest

EXPERIMENT_SCHEMA = "skeleton.game.emulator_controlled_experiments.v1"
MAX_EXPERIMENT_REPORT = 16 * 1024 * 1024


class EmulatorExperimentError(ValueError):
    pass


def _bounded(value: Any, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise EmulatorExperimentError(f"{name} must be an integer between {lo} and {hi}")
    return value


def _guard(
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
) -> None:
    if cancel is not None and cancel():
        raise EmulatorExperimentError("emulator experiment was cancelled")
    if authorize is not None:
        authorize()


@dataclass(frozen=True)
class EmulatorExperimentConfig:
    seed: int = 0
    anchors: int = 3
    repeats: int = 2
    longest_duration: int = 4
    max_conditions: int = 32
    max_native_steps: int = 1536
    include_multiplayer: bool = True
    include_keyboard: bool = True
    include_memory_audit: bool = False

    def __post_init__(self) -> None:
        for value, low, high, name in (
            (self.seed, 0, 2**63 - 1, "experiment seed"),
            (self.anchors, 1, 8, "anchor count"),
            (self.repeats, 2, 5, "independent repeated trials"),
            (self.longest_duration, 2, 16, "max duration"),
            (self.max_conditions, 4, 128, "condition budget"),
            (self.max_native_steps, 32, 8192, "total emulation step budget"),
        ):
            _bounded(value, name, low, high)
        for name in ("include_multiplayer", "include_keyboard", "include_memory_audit"):
            if type(getattr(self, name)) is not bool:
                raise EmulatorExperimentError(f"{name} must be a boolean")
        if self.max_native_steps < self.repeats * self.longest_duration * 2:
            raise EmulatorExperimentError("experiment step budget cannot fit minimal controls")


@dataclass(frozen=True)
class MemoryWatch:
    """Explicit owner-chosen opaque libretro memory addresses, not game labels."""

    name: str
    region: int
    offset: int
    size: int = 16

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not 1 <= len(self.name) <= 48:
            raise EmulatorExperimentError("memory watch name invalid")
        _bounded(self.region, "libretro memory region", 0, 255)
        _bounded(self.offset, "memory offset", 0, 2**32 - 1)
        _bounded(self.size, "memory watch bytes", 1, 256)


def _observations(environment: Any, restored: Any) -> dict[str, float]:
    observation = current_observation(environment, restored)
    if not isinstance(observation, Mapping) or set(observation) != set(environment.spec.observation_bins):
        raise EmulatorExperimentError("restored observation schema does not match the bound emulator")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in observation.values()):
        raise EmulatorExperimentError("restored observation contains nonfinite channels")
    return {key: float(value) for key, value in observation.items()}


def _actual_frame(environment: Any, step: Any) -> str:
    from .game_emulator_training_lab import _frame_digest

    frame = _frame_digest(environment, step)
    if not isinstance(frame, str) or len(frame) != 64 or any(ch not in "0123456789abcdef" for ch in frame):
        raise EmulatorExperimentError("native source frame digest is invalid")
    return frame


def _memory(
    environment: Any,
    watches: Sequence[MemoryWatch],
) -> list[tuple[str, bytes]]:
    if not watches:
        return []
    read = getattr(environment, "read_memory", None)
    if not callable(read):
        raise EmulatorExperimentError("approved native memory interface is unavailable; no surrogate memory")
    result = []
    for item in watches:
        raw = read(item.region, item.offset, item.size)
        if type(raw) is not bytes or len(raw) != item.size:
            raise EmulatorExperimentError("native memory telemetry byte length differs")
        result.append((item.name, raw))
    return result


def _memory_changes(
    previous: list[tuple[str, bytes]], next_: list[tuple[str, bytes]],
) -> list[dict[str, Any]]:
    if len(previous) != len(next_):
        raise EmulatorExperimentError("native memory watch count changed")
    result = []
    for (name, before), (next_name, after) in zip(previous, next_, strict=True):
        if name != next_name or len(before) != len(after):
            raise EmulatorExperimentError("native memory watch identity differs")
        result.append({
            "watch": name,
            "pre_sha256": hashlib.sha256(before).hexdigest(),
            "post_sha256": hashlib.sha256(after).hexdigest(),
            "different_bytes": sum(a != b for a, b in zip(before, after, strict=True)),
            "bytes": len(before),
            "semantics": "opaque byte changes; operator must separately establish game meaning",
        })
    return result


def _build_sequences(
    actions: Sequence[str], config: EmulatorExperimentConfig, native: bool,
) -> list[dict[str, Any]]:
    """Finite orthogonal contrasts; no fictitious weapons/items/skills added."""
    idle = "idle" if "idle" in actions else actions[0]
    active = [name for name in ("a", "b", "left", "right", "up", "down", "start", "select")
              if name in actions and name != idle]
    if not active:
        active = [name for name in actions if name != idle]
    if not active:
        raise EmulatorExperimentError("an actual input action distinct from the idle control is required")
    a, b = active[0], (active[1] if len(active) > 1 else idle)
    length = config.longest_duration
    tests = [
        ("baseline_idle", [idle] * length, "passive"),
        ("short_pulse", [a] + [idle] * (length - 1), "pulse"),
        ("sustained_input", [a] * length, "duration"),
        ("delayed_input", [idle] * (length - 1) + [a], "latency"),
        ("second_input", [b] * length, "ability_vs_ability"),
        ("ordered_a_then_b", [a, b] + [idle] * (length - 2), "ordering"),
        ("ordered_b_then_a", [b, a] + [idle] * (length - 2), "ordering"),
        ("alternating", [a if index % 2 == 0 else b for index in range(length)], "combination"),
        ("recovery_after_input", [a] * max(1, length // 2) + [idle] * (length - max(1, length // 2)), "recovery"),
    ]
    for action in active[:6]:
        tests.append(("single_" + action, [action] + [idle] * (length - 1), "action_ablation"))
    if native:
        # Single-step combined-button sequences are emitted via approved
        # input_step, not synthetic actions in the finite Q policy.
        from .game_emulator_host import _policy_controls

        combo = _policy_controls("a_right")
        combo["buttons"] |= _policy_controls("start")["buttons"]
        dual = [_policy_controls("a"), _policy_controls("b")]
        four = [
            _policy_controls("up"), _policy_controls("down"),
            _policy_controls("left"), _policy_controls("right"),
        ]
        controls = [
            ("button_chord", [combo], "multi_button"),
            ("two_player", dual, "multi_player"),
            ("four_player", four, "multi_player"),
        ]
        if config.include_keyboard:
            keyboard = _policy_controls("key_enter")
            keyboard["keys"] = sorted(set(keyboard["keys"] + _policy_controls("key_space")["keys"]))
            controls.append(("keyboard_chord", [keyboard], "keyboard"))
        for name, ports, facet in controls:
            if len(ports) > 1 and not config.include_multiplayer:
                continue
            tests.append((name, [ports] * length, facet))
    conditions = []
    for name, steps, facet in tests:
        if len(conditions) >= config.max_conditions:
            break
        conditions.append({
            "condition_id": name,
            "facet": facet,
            "steps": steps,
            "real_native_controller_vectors": isinstance(steps[0], list),
        })
    # Never allow the baseline to disappear behind priority filters.
    if not conditions or conditions[0]["condition_id"] != "baseline_idle":
        raise EmulatorExperimentError("no neutral baseline condition")
    if len(conditions) < 4:
        raise EmulatorExperimentError("insufficient action counterfactual coverage")
    return conditions


def _run_condition(
    environment: Any, snapshot: Mapping[str, Any], initial: Mapping[str, float],
    condition: Mapping[str, Any], watches: Sequence[MemoryWatch],
    *,
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
) -> dict[str, Any]:
    _guard(cancel, authorize)
    observation = _observations(environment, environment.restore(snapshot))
    if observation != dict(initial):
        raise EmulatorExperimentError("experimental branch origin differs from real snapshot")
    before = _memory(environment, watches)
    rows = []
    frames: list[str] = []
    total_return = 0.0
    for index, controls in enumerate(condition["steps"]):
        _guard(cancel, authorize)
        if condition["real_native_controller_vectors"]:
            if not callable(getattr(environment, "input_step", None)):
                raise EmulatorExperimentError("real native controller interface is unavailable")
            step = environment.input_step(controls)
            evidence = dict(step.info).get("evidence", {})
            if not isinstance(evidence, Mapping) or evidence.get("controller_only") is not True:
                raise EmulatorExperimentError("chord/multiplayer input was not a controller-only native action")
        else:
            step = environment.step(controls)
        next_observation = _observations(environment, step.observation)
        reward = step.reward
        if not math.isfinite(reward) or abs(reward) > 1e9:
            raise EmulatorExperimentError("native trial produced unbounded reward")
        frame = _actual_frame(environment, step)
        frames.append(frame)
        rows.append({
            "step": index + 1,
            "control_digest": _digest(controls),
            "observation_before": observation,
            "observation_after": next_observation,
            "real_reward": reward,
            "native_transition_digest": getattr(step, "transition_digest", "") or None,
            "frame_sha256": frame,
            "actual_terminal": step.terminated,
            "actual_truncated": step.truncated,
        })
        total_return += reward
        observation = next_observation
        if step.terminated or step.truncated:
            break
    end_memory = _memory(environment, watches)
    result = {
        "condition_id": condition["condition_id"],
        "facet": condition["facet"],
        "controller_only": condition["real_native_controller_vectors"],
        "origin_digest": environment_snapshot_digest_from_payload(snapshot),
        "trial_steps": len(rows),
        "sum_real_visual_rewards": total_return,
        "end_observation": observation,
        "end_snapshot_digest": environment_snapshot_digest(environment),
        "frame_trace_digest": _digest(frames),
        "frame_change_events": sum(a != b for a, b in zip(frames, frames[1:])),
        "memory_watches": _memory_changes(before, end_memory),
        "step_receipts": rows,
    }
    result["trial_digest"] = _digest(result)
    return result


def environment_snapshot_digest_from_payload(snapshot: Mapping[str, Any]) -> str:
    from .game_emulator_training_lab import environment_snapshot_digest_from_payload as lookup

    return lookup(snapshot)


def _scalar_distance(
    first: Mapping[str, float],
    second: Mapping[str, float],
) -> float:
    if set(first) != set(second):
        raise EmulatorExperimentError("measured feature dimensions differ")
    if not first:
        raise EmulatorExperimentError("empty actual observation")
    return math.fsum(abs(first[key] - second[key]) for key in first) / len(first)


def _effect_summary(
    condition: Mapping[str, Any], baseline: Mapping[str, Any],
) -> dict[str, Any]:
    rows = condition["repeats"]
    controls = baseline["repeats"]
    if not rows or not controls:
        raise EmulatorExperimentError("cannot evaluate a contrast without actual repeats")
    delta = [
        row["sum_real_visual_rewards"] - pair["sum_real_visual_rewards"]
        for row, pair in zip(rows, controls, strict=True)
    ]
    differences = [
        _scalar_distance(row["end_observation"], pair["end_observation"])
        for row, pair in zip(rows, controls, strict=True)
    ]
    changes = [row["frame_trace_digest"] != pair["frame_trace_digest"]
               for row, pair in zip(rows, controls, strict=True)]
    stable = condition["replay_stable"] and baseline["replay_stable"]
    return {
        "baseline_condition": baseline["condition_id"],
        "measured_reward_delta_per_repetition": delta,
        "mean_measured_reward_delta": math.fsum(delta) / len(delta),
        "mean_observation_distance": math.fsum(differences) / len(differences),
        "frame_trace_differs_from_baseline_rate": sum(changes) / len(changes),
        "repeatable_counterfactual_observation": stable,
        "semantic_cause_identified": False,
        "game_objective_success_identified": False,
    }


def _interpret(
    conditions: Sequence[Mapping[str, Any]],
    contrasts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    selected = {entry["condition_id"]: entry for entry in conditions}
    order_a = selected.get("ordered_a_then_b")
    order_b = selected.get("ordered_b_then_a")
    order_result = None
    if order_a and order_b:
        order_result = {
            "order_dependent_ending_observation": (
                order_a["repeats"][0]["end_observation"] != order_b["repeats"][0]["end_observation"]
            ),
            "order_dependent_final_state": (
                order_a["repeats"][0]["end_snapshot_digest"] != order_b["repeats"][0]["end_snapshot_digest"]
            ),
            "order_dependence_repeated": order_a["replay_stable"] and order_b["replay_stable"],
            "semantics": "input order changes measured native state; does not establish a game combo",
        }
    baseline = selected.get("baseline_idle")
    passive_flow = None
    if baseline:
        observed_frames = sum(r["frame_change_events"] for r in baseline["repeats"])
        nonresponsive = [
            name for name, result in contrasts.items()
            if name != "baseline_idle" and result["repeatable_counterfactual_observation"]
            and result["mean_observation_distance"] == 0
            and result["frame_trace_differs_from_baseline_rate"] == 0
        ]
        passive_flow = {
            "observed_frame_change_events_during_idle": observed_frames,
            "input_conditions_indistinguishable_from_idle": nonresponsive,
            "cutscene_like_passive_visual_motion_candidate": bool(observed_frames and nonresponsive),
            "cutscene_semantics_verified": False,
            "possible_alternatives": ["menu", "loading", "animation", "unmapped_input", "video", "nondeterminism"],
        }
    return {
        "action_order": order_result,
        "passive_motion_input_responsiveness": passive_flow,
        "action_effects": dict(contrasts),
    }


def run_emulator_experiment_matrix(
    request: GameEnvironmentRequest,
    *,
    rights_acknowledged: bool,
    config: EmulatorExperimentConfig = EmulatorExperimentConfig(),
    watches: Sequence[MemoryWatch] = (),
    cancel: Callable[[], bool] | None = None,
    authorize: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Conduct actual replayed cause/control comparisons; never optimize weights."""
    if not isinstance(request, GameEnvironmentRequest) or request.kind not in ("libretro", "builtin"):
        raise EmulatorExperimentError("a real declared ROM interpreter or installed core is required")
    if request.kind == "builtin" and (
        request.rom_source is None or request.target_id not in ("game_boy", "dragon_native:game_boy")
    ):
        raise EmulatorExperimentError("reference simulations are not accepted as native ROM measurements")
    if rights_acknowledged is not True:
        raise EmulatorExperimentError("explicit rights clearance assertion is required")
    if not isinstance(config, EmulatorExperimentConfig):
        raise EmulatorExperimentError("typed experiment budget required")
    if type(watches) not in (tuple, list) or len(watches) > 8:
        raise EmulatorExperimentError("memory-watch count exceeds a finite bound")
    if any(not isinstance(watch, MemoryWatch) for watch in watches):
        raise EmulatorExperimentError("memory watch needs approved region/offset/length tuples")
    if len({watch.name for watch in watches}) != len(watches) or sum(w.size for w in watches) > 1024:
        raise EmulatorExperimentError("duplicate/oversized private memory watch set")
    if watches and (request.kind != "libretro" or not config.include_memory_audit):
        raise EmulatorExperimentError("memory telemetry requires explicit native mode and opt-in")
    if request.max_steps < config.longest_duration + config.anchors - 1:
        raise EmulatorExperimentError("experiment origin + branch duration exceeds the true episode length")
    _guard(cancel, authorize)
    environment = request.build(cancel=cancel)
    try:
        native = request.kind == "libretro"
        conditions = _build_sequences(environment.spec.actions, config, native)
        expected_total = (
            len(conditions) * config.repeats * config.longest_duration * config.anchors
            + config.anchors - 1
        )
        if expected_total > config.max_native_steps:
            raise EmulatorExperimentError("controlled experiment branch matrix exceeds native step budget")
        actions = tuple(environment.spec.actions)
        probe = [name for name in ("right", "left", "a", "idle") if name in actions]
        if not probe:
            raise EmulatorExperimentError("no actual environment anchor actions are available")
        # A real gameplay timeline supplies distinct state origins. Saving
        # those snapshots before branching prevents false seed-only variants.
        obs = _observations(environment, environment.reset(config.seed))
        anchors = []
        for index in range(config.anchors):
            _guard(cancel, authorize)
            anchor = environment.snapshot()
            anchors.append({
                "source_snapshot": anchor,
                "origin_observation": dict(obs),
                "source_snapshot_digest": environment_snapshot_digest_from_payload(anchor),
                "source_timeline_steps": index,
            })
            if index + 1 < config.anchors:
                step = environment.step(probe[index % len(probe)])
                if step.terminated or step.truncated:
                    raise EmulatorExperimentError("native state terminated before capturing all anchors")
                obs = _observations(environment, step.observation)
        all_results = []
        native_calls = config.anchors - 1
        for anchor_index, anchor in enumerate(anchors):
            evaluated = []
            for condition in conditions:
                attempts = []
                for repeat in range(config.repeats):
                    _guard(cancel, authorize)
                    trial = _run_condition(
                        environment, anchor["source_snapshot"], anchor["origin_observation"],
                        condition, watches, cancel=cancel, authorize=authorize,
                    )
                    native_calls += trial["trial_steps"]
                    if native_calls > config.max_native_steps:
                        raise EmulatorExperimentError("native experiment exceeded actual step limit")
                    attempts.append(trial)
                # A genuine exact-state control repeated N times must agree
                # on state/frame/reward/step counts; terminal nondeterminism is
                # reported instead of quietly promoting observations to truth.
                comparator = lambda sample: (
                    sample["end_snapshot_digest"], sample["frame_trace_digest"],
                    sample["sum_real_visual_rewards"], sample["trial_steps"],
                    tuple((row["observation_after"], row["frame_sha256"]) for row in sample["step_receipts"]),
                )
                stable = all(comparator(item) == comparator(attempts[0]) for item in attempts[1:])
                evaluated.append({
                    "condition_id": condition["condition_id"],
                    "facet": condition["facet"],
                    "actual_repeats": len(attempts),
                    "replay_stable": stable,
                    "repeats": attempts,
                })
            baseline = evaluated[0]
            if baseline["condition_id"] != "baseline_idle":
                raise EmulatorExperimentError("neutral control missing for source anchor")
            contrasts = {
                row["condition_id"]: _effect_summary(row, baseline)
                for row in evaluated[1:]
            }
            all_results.append({
                "anchor_index": anchor_index,
                "anchor_source_timeline_steps": anchor["source_timeline_steps"],
                "anchor_snapshot_digest": anchor["source_snapshot_digest"],
                "anchored_conditions": evaluated,
                "analyses": _interpret(evaluated, contrasts),
                "all_repeated_controls_stable": all(row["replay_stable"] for row in evaluated),
            })
        report = {
            "schema_version": EXPERIMENT_SCHEMA,
            "request_digest": request.digest,
            "environment_digest": environment.spec.environment_digest,
            "actual_native_library_host": native,
            "original_rom_interpreter": not native,
            "source_rights_asserted": True,
            "sampled_anchors": len(all_results),
            "distinct_conditions": len(conditions),
            "exact_repeats_per_condition": config.repeats,
            "actual_native_steps_including_probe_anchors": native_calls,
            "max_native_steps": config.max_native_steps,
            "all_trials_reproducible": all(item["all_repeated_controls_stable"] for item in all_results),
            "anchors": all_results,
            "declared_memory_watch_names": [item.name for item in watches],
            "limits": {
                "weight_updates": 0,
                "policy_promotion": False,
                "semantic_game_object_detection": False,
                "cutscene_certification": False,
                "content_rights_independently_verified": False,
                "native_hardware_accuracy_certified": False,
            },
        }
        report["report_digest"] = _digest(report)
        _json(report, limit=MAX_EXPERIMENT_REPORT)
        return report
    finally:
        if callable(getattr(environment, "close", None)):
            environment.close()
