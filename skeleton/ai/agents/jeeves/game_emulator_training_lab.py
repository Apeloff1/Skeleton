"""Evidence-first AI training on actual approved emulator or original DMG ROM steps.

This is NOT a new emulator, a game-success detector or a neural weight trainer.
Native libretro libraries run only in the already governed isolated host.
Each Q-policy update follows exact checkpoint -> action -> reverse replay
verification. Counterfactuals and boomerang revisits are NOT fabricated
episodes, rewards or extra policy updates. No game content is downloaded.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .game_learning import (
    TRACE_SCHEMA,
    GameLearningConfig,
    GameLearningError,
    GamePolicyLearner,
    _digest,
    _descriptor,
    _json,
)
from .game_learning_demonstrations import current_observation, environment_snapshot_digest
from .game_learning_parallel import GameEnvironmentRequest
from .game_emulator_curriculum import ANGLES, EvidenceCurriculum

SCHEMA = "skeleton.game.emulator_training_lab.v1"
TRAINING_PROJECTION_FIELDS = (
    "sequence", "observation", "action", "next_observation", "reward",
    "reward_components", "terminated", "truncated",
)


def verified_training_projection(row: Mapping[str, Any]) -> str:
    """Content digest for learning features from a fully audited source row.

    Trace metadata remains independently committed by the original trace SHA.
    This compact projection allows the later neural optimizer to demonstrate
    that *its numeric inputs* correspond to that exact source episode without
    trusting a separately rehashed candidate data export.
    """
    if not isinstance(row, Mapping) or not set(TRAINING_PROJECTION_FIELDS) <= set(row):
        raise EmulatorTrainingError("source transition missing verified training fields")
    return _digest({field: row[field] for field in TRAINING_PROJECTION_FIELDS})
class EmulatorTrainingError(GameLearningError):
    """Training provenance, replay or resource bound invalid."""


def _integer(value: int, lo: int, hi: int, label: str) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise EmulatorTrainingError(f"{label} must be an integer in {lo}..{hi}")
    return value


@dataclass(frozen=True)
class EmulatorLabConfig:
    max_runs: int = 48
    steps_per_run: int = 24
    stagnation_runs: int = 10
    checkpoint_stride: int = 6
    counterfactual_actions: int = 3
    boomerang_interval: int = 5
    boomerang_retained: int = 4
    heldout_episodes: int = 2
    seed: int = 0

    def __post_init__(self) -> None:
        for value, lo, hi, name in (
            (self.max_runs, 1, 256, "max runs"),
            (self.steps_per_run, 1, 128, "steps per run"),
            (self.stagnation_runs, 10, 32, "stagnation runs"),
            (self.checkpoint_stride, 1, 32, "checkpoint stride"),
            (self.counterfactual_actions, 0, 8, "counterfactual branches"),
            (self.boomerang_interval, 1, 64, "boomerang interval"),
            (self.boomerang_retained, 1, 8, "retained rewind runs"),
            (self.heldout_episodes, 1, 8, "heldout episode count"),
            (self.seed, 0, 2**63 - 1, "training seed"),
        ):
            _integer(value, lo, hi, name)
        if self.steps_per_run > 128 or self.max_runs * self.steps_per_run > 8192:
            raise EmulatorTrainingError("cumulative emulation work exceeds explicit bounds")


def _guard(cancel: Callable[[], bool] | None, authorize: Callable[[], None] | None) -> None:
    if cancel is not None and cancel():
        raise EmulatorTrainingError("emulator training was cancelled")
    if authorize is not None:
        authorize()


def _frame_digest(environment: Any, step: Any) -> str:
    # Native worker supplies real frame SHA, DMG supplies actual gray8 pixels.
    info = dict(step.info)
    evidence = info.get("evidence", {})
    if isinstance(evidence, Mapping) and isinstance(evidence.get("frame_digest"), str):
        return evidence["frame_digest"]
    preview = environment.preview()
    if not isinstance(preview, Mapping):
        raise EmulatorTrainingError("an actual emulator frame is required for visual audit")
    encoded = preview.get("pixels_base64")
    if isinstance(encoded, str):
        import base64

        pixels = base64.b64decode(encoded, validate=True)
        return hashlib.sha256(pixels).hexdigest()
    digest = preview.get("source_pixel_digest")
    if not isinstance(digest, str):
        raise EmulatorTrainingError("runtime has no auditable source frame digest")
    return digest


def _observation_signature(spec: Any, observation: Mapping[str, float], frame_digest: str) -> str:
    import bisect

    shape = [
        bisect.bisect_right(spec.observation_bins[key], observation[key])
        for key in spec.observation_bins
        if key != "step_fraction"
    ]
    return _digest({"bins": shape, "actual_frame": frame_digest})


def _choose_action(
    learner: GamePolicyLearner,
    observation: Mapping[str, float],
    angle: str,
    ordinal: int,
    step: int,
    rng: random.Random,
    underobserved_action: str | None = None,
) -> str:
    actions = tuple(learner.spec.actions)
    if step == 0 and angle in ("exploration", "boundary") and underobserved_action in actions:
        return underobserved_action
    if angle == "policy" or angle == "causal":
        return learner.predict(observation)["action"]
    if angle == "adversarial":
        q = learner.predict(observation)["q_values"]
        return min(actions, key=lambda name: (q[name], actions.index(name)))
    if angle == "temporal":
        return "idle" if "idle" in actions and step % 4 < 3 else actions[(step + ordinal) % len(actions)]
    if angle == "boundary":
        return actions[0 if step % 2 == 0 else -1]
    if angle == "reversal":
        opposites = ("left", "right", "up", "down")
        choices = [name for name in opposites if name in actions]
        return choices[(step + ordinal) % len(choices)] if choices else actions[(len(actions) - 1 - step) % len(actions)]
    if angle == "recovery":
        return "idle" if step % 3 == 0 and "idle" in actions else learner.predict(observation)["action"]
    if angle == "perturbation":
        return actions[rng.randrange(len(actions))]
    if angle == "boomerang":
        return actions[(step * 3 + ordinal) % len(actions)]
    return actions[(step + ordinal * 5) % len(actions)]


def _normalize_step(learner: GamePolicyLearner, before: Mapping[str, float], action: str,
                    step: Any, sequence: int, force_last: bool = False) -> dict[str, Any]:
    if step.terminated and force_last:
        force_last = False
    raw = {
        "sequence": sequence,
        "observation": dict(before),
        "action": action,
        "next_observation": dict(step.observation),
        "reward_components": dict(step.reward_components),
        "reward": math.fsum(step.reward_components.values()),
        "terminated": step.terminated,
        "truncated": step.truncated or force_last,
    }
    if step.info:
        raw["info"] = dict(step.info)
    if step.transition_digest:
        raw["transition_digest"] = step.transition_digest
    return learner._transition(raw, sequence)


def _replay_segment(
    environment: Any,
    learner: GamePolicyLearner,
    checkpoint: Mapping[str, Any],
    expected_observation: Mapping[str, float],
    rows: list[dict[str, Any]],
    *,
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
) -> dict[str, Any]:
    _guard(cancel, authorize)
    restored = current_observation(environment, environment.restore(checkpoint))
    if restored != expected_observation:
        raise EmulatorTrainingError("reverse restoration differs from recorded observation")
    observation = dict(restored)
    replayed = 0
    for row in rows:
        _guard(cancel, authorize)
        if row["observation"] != observation:
            raise EmulatorTrainingError("reverse replay observation ordering differs")
        actual = environment.step(row["action"])
        replay = _normalize_step(
            learner, observation, row["action"], actual, row["sequence"],
            force_last=row["truncated"] and not actual.truncated,
        )
        if replay != row:
            raise EmulatorTrainingError("reverse replay changed native action, reward, frame custody or outcome")
        observation = replay["next_observation"]
        replayed += 1
    return {"replayed_steps": replayed, "ending_snapshot_digest": environment_snapshot_digest(environment)}


def _counterfactuals(environment: Any, learner: GamePolicyLearner, checkpoint: Mapping[str, Any],
                     original_action: str, count: int,
                     *, cancel: Callable[[], bool] | None,
                     authorize: Callable[[], None] | None) -> list[dict[str, Any]]:
    if not count:
        return []
    actions = [name for name in learner.spec.actions if name != original_action][:count]
    samples = []
    for action in actions:
        _guard(cancel, authorize)
        before = current_observation(environment, environment.restore(checkpoint))
        step = environment.step(action)
        samples.append({
            "alternative_action": action,
            "real_reward": step.reward,
            "actual_frame_sha256": _frame_digest(environment, step),
            "from_state": environment_snapshot_digest_from_payload(checkpoint),
            "counterfactual_state": environment_snapshot_digest(environment),
            "observation_change": _digest([before, dict(step.observation)]),
            "used_as_policy_update": False,
        })
    return samples


def environment_snapshot_digest_from_payload(snapshot: Mapping[str, Any]) -> str:
    for field in ("snapshot_digest", "state_digest", "digest"):
        if field in snapshot:
            value = snapshot[field]
            if not isinstance(value, str) or len(value) != 64:
                raise EmulatorTrainingError("snapshot digest is invalid")
            return value
    return _digest(snapshot)



def _controller_probes(
    environment: Any, checkpoint: Mapping[str, Any], *,
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
) -> list[dict[str, Any]]:
    """Execute REAL multi-button/multi-port native controller probes.

    These are deliberately excluded from the finite policy action space:
    fabricated surrogate 'multi-controller Q updates' are prohibited.
    """
    if not callable(getattr(environment, "input_step", None)):
        return []
    from .game_emulator_host import _policy_controls

    mixed_ab = _policy_controls("a")
    mixed_ab["buttons"] |= _policy_controls("b")["buttons"]
    mixed_combo = _policy_controls("a_right")
    mixed_combo["buttons"] |= _policy_controls("start")["buttons"]
    probes = [
        [mixed_ab],
        [mixed_combo],
        [_policy_controls("a"), _policy_controls("b")],
        [_policy_controls("start"), _policy_controls("select"),
         _policy_controls("up"), _policy_controls("down")],
    ]
    observations = []
    for controls in probes:
        _guard(cancel, authorize)
        environment.restore(checkpoint)
        native_step = environment.input_step(controls)
        evidence = dict(native_step.info).get("evidence", {})
        if not isinstance(evidence, Mapping) or not evidence.get("controller_only"):
            raise EmulatorTrainingError("multi-controller probes must retain controller-only status")
        observations.append({
            "ports": len(controls),
            "controller_digest": evidence["controller_digest"],
            "actual_frame_sha256": _frame_digest(environment, native_step),
            "measured_reward": native_step.reward,
            "actual_native_runs": evidence.get("native_runs", 0),
            "learned_as_policy_action": False,
        })
    environment.restore(checkpoint)
    return observations


def _collect_audited(
    request: GameEnvironmentRequest, learner: GamePolicyLearner, config: EmulatorLabConfig,
    *, run_index: int, seed: int, angle: str,
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
    underobserved_action: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _guard(cancel, authorize)
    environment = request.build(cancel=cancel)
    try:
        if _descriptor(environment.spec) != learner.descriptor:
            raise EmulatorTrainingError("training factory resolved a different core, content or source")
        observation = learner._observation(environment.reset(seed))
        first_state = environment.snapshot()
        first_observation = dict(observation)
        checkpoints = [(0, first_state, first_observation)]
        transitions: list[dict[str, Any]] = []
        modality = []
        rng = random.Random(_digest([config.seed, run_index, angle]))
        counterfactual = []
        multi_controller = []
        for index in range(config.steps_per_run):
            _guard(cancel, authorize)
            if index and index % config.checkpoint_stride == 0:
                checkpoints.append((index, environment.snapshot(), dict(observation)))
            action = _choose_action(
                learner, observation, angle, run_index, index, rng,
                underobserved_action=underobserved_action,
            )
            # Counterfactuals are actual one-step native probes from one earlier
            # recorded state. Restore the real continuation before collecting.
            if index in (0, config.steps_per_run // 2) and config.counterfactual_actions:
                checkpoint = environment.snapshot()
                counterfactual.extend(
                    _counterfactuals(environment, learner, checkpoint, action,
                                     config.counterfactual_actions, cancel=cancel, authorize=authorize)
                )
                if index == 0 and request.kind == "libretro":
                    multi_controller = _controller_probes(
                        environment, checkpoint, cancel=cancel, authorize=authorize
                    )
                observation = learner._observation(current_observation(environment, environment.restore(checkpoint)))
            step = environment.step(action)
            row = _normalize_step(
                learner, observation, action, step, index + 1,
                force_last=index + 1 == config.steps_per_run,
            )
            transitions.append(row)
            frame = _frame_digest(environment, step)
            modality.append({
                "sequence": index + 1,
                "actual_frame_sha256": frame,
                "observed_audio_rms": float(step.observation.get("audio_rms", 0.0)),
                "measured_visual_change": float(step.observation.get("visual_change", 0.0)),
                "state_signature": _observation_signature(environment.spec, step.observation, frame),
            })
            observation = row["next_observation"]
            if row["terminated"] or row["truncated"]:
                break
        if not transitions:
            raise EmulatorTrainingError("empty measured episode cannot train")
        final_snapshot = environment_snapshot_digest(environment)
        audit = []
        # From the actual ending, jump backwards and independently replay each
        # recorded suffix; this is real emulator execution, NOT text matching.
        for index, checkpoint, prior_observation in reversed(checkpoints):
            result = _replay_segment(
                environment, learner, checkpoint, prior_observation,
                transitions[index:], cancel=cancel, authorize=authorize,
            )
            if result["ending_snapshot_digest"] != final_snapshot:
                raise EmulatorTrainingError("reverse checkpoint replay changed the final emulator state")
            audit.append({
                "checkpoint_step": index,
                "source_snapshot_digest": environment_snapshot_digest_from_payload(checkpoint),
                **result,
                "end_state_matches": True,
            })
        trace = {
            "schema_version": TRACE_SCHEMA,
            "environment": learner.descriptor,
            "episode_id": "emulator-lab:" + _digest([learner.policy_id, run_index, seed, angle]),
            "seed": seed,
            "source_lineage": learner.source_lineage,
            "transitions": transitions,
            "return": math.fsum(row["reward"] for row in transitions),
            "steps": len(transitions),
        }
        trace["trace_digest"] = _digest(trace)
        learner.validate_trace(trace)
        _json(trace, limit=learner.config.trace_byte_limit)
        audit_checks = {
            "core_and_content_spec_identity": _descriptor(environment.spec) == learner.descriptor,
            "rights_authority_declared": learner.source_lineage.get("rights_acknowledged") is True,
            "exact_initial_snapshot_recorded": bool(first_state),
            "trace_sha256_validated": bool(trace["trace_digest"]),
            "native_action_schema_verified": all(row["action"] in learner.spec.actions for row in transitions),
            "finite_measured_reward": all(math.isfinite(row["reward"]) for row in transitions),
            "frame_digests_grounded": all(len(item["actual_frame_sha256"]) == 64 for item in modality),
            "observed_steps_accounted": len(transitions) == len(modality),
            "reverse_checkpoint_replays_verified": all(item["end_state_matches"] for item in audit),
            "unmodified_final_native_state": bool(audit) and all(
                item["ending_snapshot_digest"] == final_snapshot for item in audit
            ),
        }
        if len(audit_checks) != 10 or not all(audit_checks.values()):
            raise EmulatorTrainingError("the ten independent training scrutiny controls are not satisfied")
        receipt = {
            "run_index": run_index,
            "angle": angle,
            "seed": seed,
            "environment_digest": learner.descriptor["environment_digest"],
            "initial_snapshot_digest": environment_snapshot_digest_from_payload(first_state),
            "final_snapshot_digest": final_snapshot,
            "actual_steps": len(transitions),
            "actual_replay_steps": sum(row["replayed_steps"] for row in audit),
            "reverse_checkpoints": audit,
            "counterfactual_probes": counterfactual,
            "multi_controller_probes": multi_controller,
            "scrutiny_checks": audit_checks,
            "modalities": modality,
            "observed_reward": trace["return"],
            "trace_digest": trace["trace_digest"],
            "verified_training_projection_sha256": [
                verified_training_projection(row) for row in trace["transitions"]
            ],
            "game_success_verified": False,
            "model_neural_weights_updated": 0,
        }
        receipt["receipt_digest"] = _digest(receipt)
        kept = {
            "start_snapshot": first_state,
            "initial_observation": first_observation,
            "transitions": transitions,
            "trace_digest": trace["trace_digest"],
            "ending_snapshot_digest": final_snapshot,
            "environment_digest": learner.descriptor["environment_digest"],
        }
        return trace, receipt, kept
    finally:
        environment.close() if callable(getattr(environment, "close", None)) else None


def _boomerang(
    request: GameEnvironmentRequest, learner: GamePolicyLearner, kept: Mapping[str, Any],
    *, cancel: Callable[[], bool] | None, authorize: Callable[[], None] | None,
) -> dict[str, Any]:
    _guard(cancel, authorize)
    environment = request.build(cancel=cancel)
    try:
        if environment.spec.environment_digest != kept["environment_digest"]:
            raise EmulatorTrainingError("boomerang source changed")
        # Activate the approved native runtime, then restore an *earlier actual*
        # savestate, not a seed-label pseudo-reset.
        environment.reset(0)
        replay = _replay_segment(
            environment, learner, kept["start_snapshot"], kept["initial_observation"],
            kept["transitions"], cancel=cancel, authorize=authorize,
        )
        if replay["ending_snapshot_digest"] != kept["ending_snapshot_digest"]:
            raise EmulatorTrainingError("boomerang reparse diverged from the previous native run")
        return {
            "original_trace_digest": kept["trace_digest"],
            "source_snapshot_digest": environment_snapshot_digest_from_payload(kept["start_snapshot"]),
            **replay,
            "reparse_verified": True,
            "policy_updates": 0,
        }
    finally:
        environment.close() if callable(getattr(environment, "close", None)) else None


def run_emulator_training_lab(
    request: GameEnvironmentRequest, *,
    source_lineage: Mapping[str, Any],
    config: EmulatorLabConfig = EmulatorLabConfig(),
    policy_id: str = "emulator-lab-q-candidate",
    cancel: Callable[[], bool] | None = None,
    authorize: Callable[[], None] | None = None,
    on_checkpoint: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run bounded native transitions, independent audits, THEN actual Q updates.

    Never mark a neural checkpoint updated: only the canonical tabular policy
    learner changes. Native availability, rights, serialization, trace and
    entropy constraints fail closed. Budget exhaustion != learning saturation.
    """
    if not isinstance(request, GameEnvironmentRequest) or request.kind not in ("libretro", "builtin"):
        raise EmulatorTrainingError("only declared emulator and native DMG ROM requests are admitted")
    if request.kind == "builtin" and (request.rom_source is None or request.target_id not in ("game_boy", "dragon_native:game_boy")):
        raise EmulatorTrainingError("reference game simulations cannot stand in for native ROM execution")
    if request.max_steps != config.steps_per_run:
        raise EmulatorTrainingError("training episode length must bind the actual environment request")
    if not isinstance(source_lineage, Mapping) or source_lineage.get("rights_acknowledged") is not True:
        raise EmulatorTrainingError("explicit rights-cleared operator authorization is required")
    _guard(cancel, authorize)
    environment = request.build(cancel=cancel)
    try:
        spec = environment.spec
        if not isinstance(spec.environment_digest, str):
            raise EmulatorTrainingError("native environment identity is unavailable")
    finally:
        environment.close() if callable(getattr(environment, "close", None)) else None
    learner = GamePolicyLearner(
        spec,
        GameLearningConfig(
            seed=config.seed, max_episodes=config.max_runs,
            max_updates=config.max_runs * config.steps_per_run,
            trace_byte_limit=8 * 1024 * 1024,
        ),
        policy_id=policy_id,
        source_lineage=dict(source_lineage),
    )
    curriculum = EvidenceCurriculum(learner.spec.actions, seed=config.seed)
    seen: set[str] = set()
    evidence: list[dict[str, Any]] = []
    neural_candidate_samples: list[dict[str, Any]] = []
    boomerangs: list[dict[str, Any]] = []
    ring: list[dict[str, Any]] = []
    next_boomerang = config.boomerang_interval
    measured_runs = 0
    stagnant = 0
    visual_stagnant = 0
    steps = 0
    updates = 0
    status = "budget_exhausted_before_saturation"
    for ordinal in range(config.max_runs):
        _guard(cancel, authorize)
        angle, scheduling_proof = curriculum.select()
        least_observed = curriculum.least_observed_action()
        run_seed = int(_digest(["train", config.seed, ordinal])[:15], 16)
        trace, receipt, retained = _collect_audited(
            request, learner, config, run_index=ordinal, seed=run_seed, angle=angle,
            cancel=cancel, authorize=authorize,
            underobserved_action=least_observed,
        )
        new_signatures = set(item["state_signature"] for item in receipt["modalities"]) - seen
        seen.update(item["state_signature"] for item in receipt["modalities"])
        prior_q = {
            tuple(row["state"]): row["values"]
            for row in learner.snapshot()["q_table"]
        }
        # Measured visual novelty is not game mastery. Every trace admitted to
        # the learner is first replayed from exact states with all rewards bound.
        result = learner.train_offline([trace], cancel=cancel, authorize=authorize)
        current_q = {
            tuple(row["state"]): row["values"]
            for row in result.snapshot["q_table"]
        }
        q_states_added = len(set(current_q) - set(prior_q))
        max_q_value_delta = max(
            (
                abs(new_value - old_value)
                for state, values in current_q.items()
                for new_value, old_value in zip(
                    values,
                    prior_q.get(state, [0.0] * len(values)),
                    strict=True,
                )
            ),
            default=0.0,
        )
        q_evidence_changed = q_states_added > 0 or max_q_value_delta > 1e-6
        updates += result.updates
        steps += trace["steps"]
        measured_runs += 1
        # Rights-admitted, exact replay-verified state/action examples become
        # candidate training DATA only, never a promoted neural checkpoint.
        # Held-out evaluator trajectories are deliberately excluded.
        for row in trace["transitions"]:
            neural_candidate_samples.append({
                "trace_digest": trace["trace_digest"],
                "environment_digest": learner.descriptor["environment_digest"],
                "seed": trace["seed"],
                "sequence": row["sequence"],
                "verified_training_projection_sha256": verified_training_projection(row),
                "observation": row["observation"],
                "action": row["action"],
                "next_observation": row["next_observation"],
                "measured_reward": row["reward"],
                "measured_reward_components": row["reward_components"],
                "terminated": row["terminated"],
                "truncated": row["truncated"],
                "source": "independently_replayed_emulator_transition",
            })
        curriculum_proof = curriculum.observe(
            angle=angle, run_index=ordinal, trace=trace,
            receipt=receipt, new_signatures=len(new_signatures),
        )
        receipt["curriculum_selection"] = scheduling_proof
        receipt["curriculum_result"] = curriculum_proof
        receipt["new_visual_state_signatures"] = len(new_signatures)
        receipt["new_learned_q_states"] = q_states_added
        receipt["max_absolute_q_value_change"] = max_q_value_delta
        receipt["q_values_moved_beyond_threshold"] = max_q_value_delta > 1e-6
        receipt["measured_learning_progress"] = bool(new_signatures) or q_evidence_changed
        receipt["actual_tabular_q_updates"] = result.updates
        receipt["policy_snapshot_digest_after"] = learner.snapshot_digest
        receipt["training_commit"] = True
        receipt["receipt_digest"] = _digest({k: v for k, v in receipt.items() if k != "receipt_digest"})
        evidence.append(receipt)
        visual_stagnant = 0 if new_signatures else visual_stagnant + 1
        stagnant = 0 if new_signatures or q_evidence_changed else stagnant + 1
        if len(ring) < config.boomerang_retained:
            ring.append(retained)
        else:
            # Deterministic reservoir replacement keeps some OLD samples
            # eligible for surprise reparse instead of only the last N runs.
            reservoir_index = int(_digest(["reservoir", config.seed, ordinal])[:8], 16) % (ordinal + 1)
            if reservoir_index < config.boomerang_retained:
                ring[reservoir_index] = retained
        if ordinal + 1 >= next_boomerang and ring:
            selection = int(_digest(["boomerang", config.seed, ordinal])[:8], 16) % len(ring)
            return_receipt = _boomerang(
                request, learner, ring[selection], cancel=cancel, authorize=authorize
            )
            return_receipt["after_run"] = ordinal + 1
            return_receipt["return_receipt_digest"] = _digest(return_receipt)
            boomerangs.append(return_receipt)
            # Interval randomized from a pinned seed; cannot silently run
            # unbounded additional native episodes between main runs.
            interval = 1 + int(
                _digest(["interval", config.seed, ordinal])[:8], 16
            ) % (2 * config.boomerang_interval)
            next_boomerang = ordinal + 1 + interval
        if on_checkpoint is not None:
            _guard(cancel, authorize)
            on_checkpoint(learner.snapshot(), {
                "committed_runs": measured_runs, "measured_steps": steps,
                "last_trace_digest": trace["trace_digest"],
                "last_run_receipt_digest": receipt["receipt_digest"],
                "stagnant_runs": stagnant,
                "visual_only_stagnant_runs": visual_stagnant,
                "last_q_max_absolute_value_change": max_q_value_delta,
            })
        if stagnant >= config.stagnation_runs:
            status = "observed_q_and_visual_learning_plateau"
            break
    heldout_seeds = [
        int(_digest(["heldout", config.seed, index])[:15], 16)
        for index in range(config.heldout_episodes)
    ]
    _guard(cancel, authorize)
    evaluated = learner.evaluate(
        request.build, heldout_seeds=heldout_seeds, cancel=cancel, authorize=authorize,
    ).as_dict()
    # Snapshot/trace identities, no fabricated claims of success or of neural
    # parameter changes. Independent eval is observational for native cores:
    # their seed label does not universally seed internal hardware RNG.
    report = {
        "schema_version": SCHEMA,
        "status": status,
        "environment": learner.descriptor,
        "request_digest": request.digest,
        "source_lineage": dict(source_lineage),
        "policy_id": policy_id,
        "policy_snapshot": learner.snapshot(),
        "run_count": measured_runs,
        "actual_training_steps": steps,
        "actual_q_table_updates": updates,
        "actual_neural_parameter_updates": 0,
        "unique_visual_state_signatures": len(seen),
        "consecutive_runs_without_new_visual_signature": visual_stagnant,
        "consecutive_runs_without_measured_q_or_visual_progress": stagnant,
        "q_value_progress_threshold": 1e-6,
        "stagnation_threshold": config.stagnation_runs,
        "audited_run_receipts": evidence,
        "boomerang_replay_receipts": boomerangs,
        "adaptive_evidence_curriculum": curriculum.report(),
        "neural_candidate_dataset": {
            "schema_version": "skeleton.game.emulator_neural_candidate_data.v1",
            "format": "finite_numeric_observation_action_reward_pairs",
            "source": "replayed_emulator_q_training_only",
            "training_sample_count": len(neural_candidate_samples),
            "train_only_no_heldout_examples": True,
            "candidate_samples": neural_candidate_samples,
            "dataset_digest": _digest(neural_candidate_samples),
            "training_executed": False,
            "weights_updated": 0,
            "production_promotion_authorized": False,
        },
        "heldout_evaluation": evaluated,
        "limits": {
            "seed_does_not_guarantee_native_rng_control": request.kind == "libretro",
            "visual_novelty_is_not_game_success": True,
            "hardware_compatibility_verified": False,
            "production_policy_promotion_authorized": False,
            "real_transformer_training_executed": False,
        },
    }
    report["report_digest"] = _digest(report)
    return report
