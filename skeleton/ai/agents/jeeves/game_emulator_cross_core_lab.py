"""Measured cross-core, same-content disagreement lab for approved libretro cores.

Real gameplay is run on each approved native emulator independently with
identical controls. Cross-emulator agreement is a probe, NEVER proof that
one core is accurate, licensed, equivalent, or a legitimate target for
neural-weight promotion.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .game_learning import _digest, _json
from .game_learning_demonstrations import environment_snapshot_digest
from .game_learning_parallel import GameEnvironmentRequest
from .game_emulator_training_lab import _frame_digest

SCHEMA = "skeleton.game.cross_core_comparison.v1"


class EmulatorCrossCoreError(ValueError):
    pass


@dataclass(frozen=True)
class CrossCoreConfig:
    seed: int = 0
    steps: int = 16
    repetitions: int = 2
    max_native_steps: int = 256

    def __post_init__(self) -> None:
        for item, label, low, high in (
            (self.seed, "comparison seed", 0, 2**63 - 1),
            (self.steps, "actual input steps", 1, 64),
            (self.repetitions, "repeat count", 2, 4),
            (self.max_native_steps, "native step budget", 4, 1024),
        ):
            if type(item) is not int or not low <= item <= high:
                raise EmulatorCrossCoreError(f"{label} outside supported bounds")


def _content_key(request: GameEnvironmentRequest) -> str:
    if request.rom_source is not None:
        return hashlib.sha256(request.rom_source).hexdigest()
    if not isinstance(request.content, Mapping):
        raise EmulatorCrossCoreError("same private content requires an admitted content descriptor")
    # A materialization directory is not content identity; the signed bundle
    # digest is the authority and carries all disc/track relationships.
    digest = request.content.get("content_digest")
    if type(digest) is not str or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise EmulatorCrossCoreError("the content descriptor has no exact identity")
    return digest


def _guard(
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
) -> None:
    if cancel is not None and cancel():
        raise EmulatorCrossCoreError("cross-core comparison cancelled")
    if authorize is not None:
        authorize()


def _actual_trial(
    request: GameEnvironmentRequest,
    actions: Sequence[str],
    *,
    seed: int,
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
) -> dict[str, Any]:
    _guard(cancel, authorize)
    env = request.build(cancel=cancel)
    try:
        if env.spec.max_episode_steps < len(actions):
            raise EmulatorCrossCoreError("core environment cannot run the requested action sequence")
        if any(action not in env.spec.actions for action in actions):
            raise EmulatorCrossCoreError("selected action is unsupported by this approved core")
        previous = env.reset(seed)
        initial = environment_snapshot_digest(env)
        samples = []
        frames = []
        for index, action in enumerate(actions):
            _guard(cancel, authorize)
            step = env.step(action)
            frame = _frame_digest(env, step)
            if (
                not isinstance(frame, str) or len(frame) != 64
                or not math.isfinite(step.reward)
            ):
                raise EmulatorCrossCoreError("native comparison frame/reward integrity differs")
            observation = dict(step.observation)
            if set(observation) != set(env.spec.observation_bins):
                raise EmulatorCrossCoreError("source observation schema differs")
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in observation.values()):
                raise EmulatorCrossCoreError("source supplied nonfinite measured signals")
            evidence = dict(step.info).get("evidence", {})
            if not isinstance(evidence, Mapping) or evidence.get("frame_digest") != frame:
                raise EmulatorCrossCoreError("libretro native worker did not bind exact pixels to the action")
            samples.append({
                "step": index + 1,
                "action": action,
                "frame_sha256": frame,
                "observation": observation,
                "native_transition_sha256": step.transition_digest,
                "real_reward": step.reward,
                "actual_native_runs": evidence.get("native_runs"),
                "audio_frames": evidence.get("audio_frames"),
            })
            frames.append(frame)
            previous = observation
            if step.terminated or step.truncated:
                if index + 1 != len(actions):
                    raise EmulatorCrossCoreError("native trial terminated before its matched control sequence")
                break
        return {
            "core_id": env.core.core_id,
            "library_sha256": env.core.library_sha256,
            "environment_digest": env.spec.environment_digest,
            "initial_snapshot_digest": initial,
            "last_snapshot_digest": environment_snapshot_digest(env),
            "frame_trace_sha256": _digest(frames),
            "actual_steps": len(samples),
            "total_measured_visual_reward": math.fsum(row["real_reward"] for row in samples),
            "observations": samples,
        }
    finally:
        if callable(getattr(env, "close", None)):
            env.close()


def _pairwise(
    left: Mapping[str, Any], right: Mapping[str, Any],
) -> dict[str, Any]:
    if left["actual_steps"] != right["actual_steps"]:
        raise EmulatorCrossCoreError("cross-core trial execution lengths differ")
    frames = []
    differences: dict[str, list[float]] = {}
    for a, b in zip(left["observations"], right["observations"], strict=True):
        if a["action"] != b["action"] or a["step"] != b["step"]:
            raise EmulatorCrossCoreError("paired controls are not aligned")
        a_obs, b_obs = a["observation"], b["observation"]
        if set(a_obs) != set(b_obs):
            raise EmulatorCrossCoreError("shared telemetry dimensions differ")
        frames.append(a["frame_sha256"] == b["frame_sha256"])
        for name in a_obs:
            differences.setdefault(name, []).append(abs(a_obs[name] - b_obs[name]))
    return {
        "left_core": left["core_id"],
        "right_core": right["core_id"],
        "same_frame_sha256_fraction": sum(frames) / len(frames),
        "normalized_sensor_absolute_difference": {
            name: math.fsum(vals) / len(vals) for name, vals in differences.items()
        },
        "measured_total_reward_delta": left["total_measured_visual_reward"] - right["total_measured_visual_reward"],
        "hardware_correctness_inferred": False,
        "different_cores_cannot_share_native_savestates": True,
    }


def compare_real_emulator_cores(
    requests: Sequence[GameEnvironmentRequest],
    *,
    rights_acknowledged: bool,
    config: CrossCoreConfig = CrossCoreConfig(),
    actions: Sequence[str] | None = None,
    cancel: Callable[[], bool] | None = None,
    authorize: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if not isinstance(requests, (tuple, list)) or not 2 <= len(requests) <= 4:
        raise EmulatorCrossCoreError("two to four approved native emulator requests required")
    if any(not isinstance(item, GameEnvironmentRequest) or item.kind != "libretro" for item in requests):
        raise EmulatorCrossCoreError("cross-core comparison accepts actual isolated native libretro runtimes only")
    if rights_acknowledged is not True or not isinstance(config, CrossCoreConfig):
        raise EmulatorCrossCoreError("source rights and explicit typed finite budgets are required")
    if len({item.core_id for item in requests}) != len(requests):
        raise EmulatorCrossCoreError("distinct independently approved emulator cores are required")
    if len({item.target_id for item in requests}) != 1:
        raise EmulatorCrossCoreError("all cores must claim the same console target identity")
    if len({_content_key(item) for item in requests}) != 1:
        raise EmulatorCrossCoreError("cross-core comparison cannot mix different ROMs/media bundles")
    if len({item.max_steps for item in requests}) != 1 or any(
        item.max_steps < config.steps for item in requests
    ):
        raise EmulatorCrossCoreError("core requests must use equal sufficient episode step budgets")
    if config.steps * config.repetitions * len(requests) > config.max_native_steps:
        raise EmulatorCrossCoreError("cross-core trial matrix exceeds the total native step budget")
    if actions is None:
        pattern = ("idle", "a", "right", "a_right", "left", "b", "down", "start", "up", "select")
        actions = tuple(pattern[index % len(pattern)] for index in range(config.steps))
    if (
        not isinstance(actions, (tuple, list)) or len(actions) != config.steps
        or any(type(item) is not str or not 1 <= len(item) <= 64 for item in actions)
    ):
        raise EmulatorCrossCoreError("exact finite action matrix is required")
    _guard(cancel, authorize)
    trials = []
    for req in requests:
        repeated = []
        for iteration in range(config.repetitions):
            _guard(cancel, authorize)
            # Native reset seeds are labels, not universal hardware RNG seeds.
            # Use independent actual runs and compare their measured identities.
            item = _actual_trial(
                req, actions, seed=config.seed, cancel=cancel, authorize=authorize
            )
            repeated.append(item)
        identical = all(
            trial["frame_trace_sha256"] == repeated[0]["frame_trace_sha256"]
            and trial["last_snapshot_digest"] == repeated[0]["last_snapshot_digest"]
            and trial["total_measured_visual_reward"] == repeated[0]["total_measured_visual_reward"]
            for trial in repeated[1:]
        )
        trials.append({
            "core_id": req.core_id,
            "repeat_stable": identical,
            "repetitions": repeated,
        })
    pairs = []
    for left_index in range(len(trials)):
        for right_index in range(left_index + 1, len(trials)):
            pairs.append(
                _pairwise(trials[left_index]["repetitions"][0], trials[right_index]["repetitions"][0])
            )
    report = {
        "schema_version": SCHEMA,
        "target_id": requests[0].target_id,
        "source_media_sha256": _content_key(requests[0]),
        "rights_acknowledged": True,
        "exact_controller_sequence": list(actions),
        "comparison_seed_label": config.seed,
        "compared_approved_native_cores": len(trials),
        "repetitions_per_core": config.repetitions,
        "actual_native_steps": config.steps * config.repetitions * len(trials),
        "all_repeats_stable": all(item["repeat_stable"] for item in trials),
        "core_trials": trials,
        "cross_core_differences": pairs,
        "limits": {
            "universal_native_rng_seeding": False,
            "pixel_match_proves_hardware_compatibility": False,
            "native_savestate_transfer_between_cores": False,
            "game_objective_semantics_verified": False,
            "neural_weights_updated": 0,
            "production_promotion_authorized": False,
        },
    }
    report["report_digest"] = _digest(report)
    _json(report, limit=8 * 1024 * 1024)
    return report
