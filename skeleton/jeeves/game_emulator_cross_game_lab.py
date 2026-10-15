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
    _, digest_before = _snapshot(environment)
    if _digest(start) != digest_before:
        raise CrossGameComparisonError("same-core restore changed exact pre-intervention source state")
    previous_frame = _frame(environment)
    previous_observation = dict(before)
    transitions, visual_changes, initial_frame = [], 0, previous_frame
    for sequence, action in enumerate(program):
        step = environment.step(action)
        frame = _frame(environment)
        observed_change = frame != previous_frame
        visual_changes += observed_change
        previous_frame = frame
        if not isinstance(step.observation, Mapping) or not isinstance(step.reward_components, Mapping):
            raise CrossGameComparisonError("source step has no actual reward/observation contract")
        reward = {str(k): float(v) for k, v in step.reward_components.items()}
        if any(not math.isfinite(value) for value in reward.values()):
            raise CrossGameComparisonError("source game reward is not finite")
        _, actual_state_digest = _snapshot(environment)
        declared_digest = getattr(step, "transition_digest", "")
        if declared_digest:
            _sha(declared_digest)
        # Source Game Boy ROM steps do not declare transition_digest;
        # create an explicitly LOCAL projection hash of measured data,
        # never falsely label it as an engine-declared native receipt.
        next_observation = dict(step.observation)
        for measured in (previous_observation, next_observation, reward):
            if (
                not 1 <= len(measured) <= 64
                or any(
                    type(k) is not str or not 1 <= len(k) <= 128
                    or type(v) not in (int, float) or not math.isfinite(float(v))
                    for k, v in measured.items()
                )
            ):
                raise CrossGameComparisonError("native game numeric observation/reward is not finite or bounded")
        projected = {
            "ordinal": sequence,
            "action": action,
            "source_observation": previous_observation,
            "source_next_observation": next_observation,
            "source_reward_components": reward,
            "source_visual_change_observed": observed_change,
            "actual_frame_sha256": frame,
            "source_observation_sha256": _digest(next_observation),
            "source_reward_components_sha256": _digest(reward),
            "actual_machine_state_sha256": actual_state_digest,
            "declared_native_transition_sha256": declared_digest or None,
            "terminated": step.terminated,
            "truncated": step.truncated,
        }
        previous_observation = next_observation
        transitions.append({
            **projected,
            "measured_source_projection_sha256": _digest(projected),
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


def verify_cross_game_comparison_receipt(document: Mapping[str, Any]) -> dict[str, Any]:
    """Recheck finite source, per-step and pairwise lineage after publication.

    This detects post-publication corruption; it is NOT a substitute for
    trusted actual emulator execution or a digital signature from hardware.
    """
    if not isinstance(document, Mapping):
        raise CrossGameComparisonError("cross-emulator report must be an exact source record")
    report = dict(document)
    signed = report.pop("report_digest", None)
    if signed != _digest(report):
        raise CrossGameComparisonError("cross-game report no longer matches its source evidence digest")
    n, wave_size = report.get("selected_games"), report.get("games_per_sequential_wave")
    library = report.get("game_receipts")
    programs = report.get("controlled_programs")
    pairs = report.get("pairwise_measured_evidence")
    if (
        report.get("schema_version") != SCHEMA
        or report.get("status") != "measured_source_emulator_controller_comparison"
        or report.get("explicit_source_rights_acknowledged") is not True
        or type(n) is not int or not 2 <= n <= MAX_GAME_LIBRARY
        or type(wave_size) is not int or not 2 <= wave_size <= MAX_ACTIVE_WAVE
        or report.get("max_selected_game_capacity") != MAX_GAME_LIBRARY
        or report.get("actual_native_executions_concurrent") != 1
        or report.get("completed_sequential_waves") != (n + wave_size - 1) // wave_size
        or not isinstance(programs, list) or not 2 <= len(programs) <= MAX_PROGRAMS
        or programs[0] != ["idle"]
        or any(not isinstance(p, list) or not 1 <= len(p) <= MAX_PROGRAM_ACTIONS
               or any(type(a) is not str or a not in ALLOWED_ACTIONS for a in p)
               for p in programs)
        or len(set(tuple(p) for p in programs)) != len(programs)
        or sum(map(len, programs)) > MAX_TOTAL_ACTIONS
        or not isinstance(library, list) or len(library) != n
        or not isinstance(pairs, list) or len(pairs) != n * (n - 1) // 2
        or report.get("actual_replayed_game_programs") != n * len(programs) * 2
        or report.get("actual_source_action_steps") != n * sum(map(len, programs)) * 2
        or report.get("cross_game_feature_alignment_inferred") is not False
        or report.get("cross_game_rewards_equivalent") is not False
        or report.get("ai_training_gradient_updates") != 0
        or report.get("neural_model_promotion_authorized") is not False
        or report.get("trained_game_design_synthesis_proven") is not False
    ):
        raise CrossGameComparisonError("comparison source library, action budget or learning claims are unverified")
    seen = set()
    candidate_rows = []
    for i, row in enumerate(library):
        if (
            not isinstance(row, dict)
            or row.get("game_index") != i
            or row.get("wave") != i // wave_size
            or row.get("source_kind") not in ("builtin", "libretro")
            or row.get("request_digest") in seen
            or not isinstance(row.get("controller_programs"), list)
            or len(row["controller_programs"]) != len(programs)
        ):
            raise CrossGameComparisonError("unique source ROM/candidate and wave custody changed")
        seen.add(_sha(row["request_digest"]))
        _sha(row["environment_digest"])
        _sha(row["actual_start_snapshot_sha256"])
        for actions, phase in zip(programs, row["controller_programs"], strict=True):
            if (
                not isinstance(phase, dict)
                or phase.get("controller_program") != actions
                or phase.get("actual_replayed_source_passes") != 2
                or phase.get("exact_source_replay_verified") is not True
                or phase.get("real_steps_executed") != 2 * len(actions)
                or phase.get("source_before_sha256") != row["actual_start_snapshot_sha256"]
                or not isinstance(phase.get("controlled_source_step_receipts"), list)
                or len(phase["controlled_source_step_receipts"]) != len(actions)
            ):
                raise CrossGameComparisonError("source controller replay evidence is incomplete")
            prior = _sha(phase["initial_frame_sha256"])
            previous_observation = None
            changes = 0
            for j, (action, step) in enumerate(zip(
                actions, phase["controlled_source_step_receipts"], strict=True
            )):
                if (
                    not isinstance(step, dict)
                    or step.get("ordinal") != j or step.get("action") != action
                    or "measured_source_projection_sha256" not in step
                ):
                    raise CrossGameComparisonError("real source controller order changed")
                actual = _sha(step["measured_source_projection_sha256"])
                source_projection = {key: value for key, value in step.items()
                                     if key != "measured_source_projection_sha256"}
                if _digest(source_projection) != actual:
                    raise CrossGameComparisonError("source observation/action/frame projection is corrupted")
                _sha(step["actual_frame_sha256"])
                _sha(step["source_observation_sha256"])
                _sha(step["source_reward_components_sha256"])
                _sha(step["actual_machine_state_sha256"])
                before = step.get("source_observation")
                after = step.get("source_next_observation")
                reward = step.get("source_reward_components")
                if (
                    not all(isinstance(candidate, dict) and 1 <= len(candidate) <= 64
                            for candidate in (before, after, reward))
                    or any(
                        type(key) is not str or type(value) not in (int, float)
                        or not math.isfinite(float(value))
                        for candidate in (before, after, reward)
                        for key, value in candidate.items()
                    )
                    or previous_observation is not None and before != previous_observation
                    or _digest(after) != step["source_observation_sha256"]
                    or _digest(reward) != step["source_reward_components_sha256"]
                    or step.get("source_visual_change_observed") is not
                        (step["actual_frame_sha256"] != prior)
                ):
                    raise CrossGameComparisonError("real numeric source feature, reward or frame-change chronology differs")
                previous_observation = after
                candidate_rows.append({
                    "game_source_digest": row["request_digest"],
                    "environment_digest": row["environment_digest"],
                    "controller_program": actions,
                    "step": j,
                    "measured_source_projection_sha256": actual,
                })
                changes += step["actual_frame_sha256"] != prior
                prior = step["actual_frame_sha256"]
            program = {
                "source_start_snapshot_sha256": phase["source_before_sha256"],
                "source_end_snapshot_sha256": phase["source_after_sha256"],
                "initial_frame_sha256": phase["initial_frame_sha256"],
                "final_frame_sha256": phase["final_frame_sha256"],
                "actual_frame_change_events": phase["actual_frame_change_events"],
                "actual_executed_steps": len(actions),
                "source_step_receipts": phase["controlled_source_step_receipts"],
            }
            if (
                changes != phase.get("actual_frame_change_events")
                or prior != phase["final_frame_sha256"]
                or phase.get("source_program_digest") != _digest(program)
                or phase.get("observed_visual_change_rate") != changes / len(actions)
            ):
                raise CrossGameComparisonError("source frame chronology or exact CPU replay commitment differs")
    position = 0
    for i in range(n):
        for j in range(i + 1, n):
            pair = pairs[position]
            position += 1
            left, right = library[i], library[j]
            expected_rates = [
                round(a["observed_visual_change_rate"] - b["observed_visual_change_rate"], 6)
                for a, b in zip(left["controller_programs"], right["controller_programs"], strict=True)
            ]
            if (
                not isinstance(pair, dict)
                or pair.get("left_game_index") != i
                or pair.get("right_game_index") != j
                or pair.get("same_target_platform") != (left["target_id"] == right["target_id"])
                or pair.get("same_source_environment") != (left["environment_digest"] == right["environment_digest"])
                or pair.get("controlled_programs_matched") != len(programs)
                or pair.get("visual_event_rate_differences") != expected_rates
                or pair.get("pixel_content_directly_comparable") is not False
                or pair.get("gameplay_skill_or_causation_established") is not False
            ):
                raise CrossGameComparisonError("cross-console visual difference evidence was fabricated or altered")
    if (
        report.get("candidate_numeric_source_rows") != len(candidate_rows)
        or report.get("candidate_numeric_dataset_sha256") != _digest(candidate_rows)
    ):
        raise CrossGameComparisonError("measured numeric observation rows no longer match the candidate source dataset")
    return {
        "accepted": True,
        "source_game_count": n,
        "verified_numeric_candidate_rows": len(candidate_rows),
        "real_replayed_source_programs": n * len(programs) * 2,
        "controlled_pairwise_comparisons": position,
        "production_model_gradient_steps": 0,
    }


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
                    "initial_frame_sha256": first["initial_frame_sha256"],
                    "final_frame_sha256": first["final_frame_sha256"],
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
    candidate_rows = [
        {
            "game_source_digest": game["request_digest"],
            "environment_digest": game["environment_digest"],
            "controller_program": phase["controller_program"],
            "step": step["ordinal"],
            "measured_source_projection_sha256": step["measured_source_projection_sha256"],
        }
        for game in compared
        for phase in game["controller_programs"]
        for step in phase["controlled_source_step_receipts"]
    ]
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
        "candidate_numeric_source_rows": len(candidate_rows),
        "candidate_numeric_dataset_sha256": _digest(candidate_rows),
        "cross_game_feature_alignment_inferred": False,
        "game_receipts": compared,
        "pairwise_measured_evidence": comparisons,
        "cross_game_rewards_equivalent": False,
        "ai_training_gradient_updates": 0,
        "neural_model_promotion_authorized": False,
        "trained_game_design_synthesis_proven": False,
    }
    result["report_digest"] = _digest(result)
    verify_cross_game_comparison_receipt(result)
    return result
