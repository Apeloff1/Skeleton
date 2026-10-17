"""Evidence-bound three-vertex training review for Jeeves and Dragon.

The vertices are (1) companion telemetry/viewing queue, (2) real AI gameplay
and native simulation, and (3) adversarial scrutiny. Repeated lenses and
replays point back to unique transitions, NEVER duplicate examples or claim
independent observations. Frame hashes are not semantic video viewing and
rule checks are not a separately executed adversarial LLM.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from .game_learning import _digest
from .game_emulator_curriculum import ANGLES
from .game_emulator_training_lab import SCHEMA as LAB_SCHEMA

SCHEMA = "skeleton.jeeves.game_training_triangle.v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_EPISODES = 1024
MAX_STEPS = 65_536
LENSES = (
    "visual_state", "audio_ambience", "controller_action",
    "reward_and_consequence", "temporal_reversal", "causal_counterfactual",
    "policy_progress", "adversarial_boundary",
)


class TrainingTriangleError(ValueError):
    """Source custody or a claimed review vertex is not established."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise TrainingTriangleError(reason)


def _sha(value: Any) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _source(report: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _require(type(report) is dict and report.get("schema_version") == LAB_SCHEMA,
             "training triangle requires the exact native lab report")
    claimed = report.get("report_digest")
    _require(_sha(claimed) and claimed == _digest({
        key: value for key, value in report.items() if key != "report_digest"
    }), "parent lab report checksum differs")
    _require(type(report.get("source_lineage")) is dict and report["source_lineage"].get("rights_acknowledged") is True,
             "triangle source rights have not been approved")
    _require(report.get("status") in (
        "observed_q_and_visual_learning_plateau", "budget_exhausted_before_saturation"
    ) and report.get("actual_neural_parameter_updates") == 0,
             "triangle requires unpromoted real gameplay evidence")
    episodes = report.get("audited_run_receipts")
    _require(type(episodes) is list and 1 <= len(episodes) <= MAX_EPISODES
             and type(report.get("run_count")) is int
             and report["run_count"] == len(episodes),
             "triangle episode count is unverified or exceeds capacity")
    policy = report.get("policy_snapshot")
    _require(type(policy) is dict and _sha(policy.get("snapshot_digest"))
             and policy["snapshot_digest"] == _digest({
                 k: v for k, v in policy.items() if k != "snapshot_digest"
             }), "triangle source policy checksum differs")
    _require(type(report.get("environment")) is dict and _sha(report["environment"].get("environment_digest")) and report["environment"] == policy.get("environment"),
             "triangle source environment and committed policy differ")
    data = report.get("neural_candidate_dataset")
    _require(type(data) is dict and data.get("train_only_no_heldout_examples") is True
             and data.get("training_executed") is False
             and data.get("weights_updated") == 0
             and data.get("production_promotion_authorized") is False,
             "triangle must keep heldout trajectories and model promotions excluded")
    samples = data.get("candidate_samples")
    _require(type(samples) is list and len(samples) <= MAX_STEPS
             and data.get("training_sample_count") == len(samples)
             and data.get("dataset_digest") == _digest(samples),
             "triangle training examples must retain their native dataset digest")
    return episodes, data


def build_training_triangle(report: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct three training perspectives from real, custody-bound evidence.

    Produces compact lens *references*, not synthetic samples or model updates.
    Adversarial audits run now; independent AI critic and semantic frame viewing
    remain explicit unfulfilled queues until actual separate witnesses exist.
    """
    episodes, data = _source(report)
    views: list[dict[str, Any]] = []
    proofs: dict[str, dict[str, Any]] = {}
    coverage = {angle: 0 for angle in ANGLES}
    seen_traces: set[str] = set()
    seen_frames: set[str] = set()
    total_steps = total_q = total_replay = total_counter = 0
    for ordinal, row in enumerate(episodes):
        _require(type(row) is dict and row.get("run_index") == ordinal
                 and _sha(row.get("receipt_digest"))
                 and row["receipt_digest"] == _digest({
                     k: v for k, v in row.items() if k != "receipt_digest"
                 }), "gameplay episode receipt digest/order differs")
        trace = row.get("trace_digest")
        _require(_sha(trace) and trace not in seen_traces
                 and type(row.get("angle")) is str and row["angle"] in coverage,
                 "gameplay trace or curriculum lens repeated without independent play")
        seen_traces.add(trace)
        coverage[row["angle"]] += 1
        steps, updates = row.get("actual_steps"), row.get("actual_tabular_q_updates")
        _require(type(steps) is int and 1 <= steps <= 128
                 and type(updates) is int and 0 <= updates <= steps
                 and row.get("training_commit") is True
                 and row.get("game_success_verified") is False
                 and row.get("model_neural_weights_updated") == 0,
                 "triangle claims an unmeasured game result or training update")
        checks = row.get("scrutiny_checks")
        _require(type(checks) is dict and len(checks) == 10
                 and all(value is True for value in checks.values()),
                 "gameplay must satisfy all ten native replay scrutiny checks")
        checkpoints = row.get("reverse_checkpoints")
        _require(type(checkpoints) is list and bool(checkpoints)
                 and all(type(c) is dict and c.get("end_state_matches") is True
                         and type(c.get("replayed_steps")) is int and c["replayed_steps"] >= 1
                         and c.get("ending_snapshot_digest") == row.get("final_snapshot_digest")
                         for c in checkpoints),
                 "reverse native replay changed the game state")
        replays = row.get("actual_replay_steps")
        _require(type(replays) is int and replays >= steps
                 and replays == sum(c.get("replayed_steps", -1) for c in checkpoints),
                 "native repeated playback accounting differs")
        projection = row.get("verified_training_projection_sha256")
        _require(type(projection) is list and len(projection) == steps
                 and all(_sha(digest) for digest in projection),
                 "actual gameplay learning projections are not bound to source")
        modalities = row.get("modalities")
        _require(type(modalities) is list and len(modalities) == steps,
                 "companion observation length differs from native actions")
        frames: list[str] = []
        audio: list[float] = []
        visual: list[float] = []
        optics: list[str] = []
        optical_sources = 0
        for sequence, sensor in enumerate(modalities, 1):
            _require(type(sensor) is dict and sensor.get("sequence") == sequence
                     and _sha(sensor.get("actual_frame_sha256"))
                     and _sha(sensor.get("state_signature"))
                     and _number(sensor.get("observed_audio_rms"))
                     and sensor["observed_audio_rms"] >= 0
                     and _number(sensor.get("measured_visual_change")),
                     "companion frame/audio telemetry is missing or fabricated")
            optical = sensor.get("dragon_optical")
            if optical is not None:
                from .game_emulator_dragon_observer import verify_native_observation
                verify_native_observation(
                    optical, frame_sha256=sensor["actual_frame_sha256"],
                )
                optics.append(optical["observation_digest"])
                optical_sources += 1
            frames.append(sensor["actual_frame_sha256"])
            audio.append(sensor["observed_audio_rms"])
            visual.append(sensor["measured_visual_change"])
        _require(optical_sources in (0, steps),
                 "a native Dragon optical capture cannot be silently partial")
        seen_frames.update(frames)
        counter = row.get("counterfactual_probes")
        controllers = row.get("multi_controller_probes")
        _require(type(counter) is list and len(counter) <= 16
                 and all(type(x) is dict and _sha(x.get("actual_frame_sha256"))
                         and x.get("used_as_policy_update") is False for x in counter)
                 and type(controllers) is list
                 and all(type(x) is dict and _sha(x.get("actual_frame_sha256"))
                         and x.get("learned_as_policy_action") is False for x in controllers),
                 "simulation probes cannot masquerade as independent Q training")
        total_steps += steps
        total_q += updates
        total_replay += replays
        total_counter += len(counter)
        proofs[trace] = {"steps": steps, "seed": row.get("seed"),
                         "projections": projection}
        views.append({
            "run_index": ordinal,
            "source_trace_sha256": trace,
            "source_receipt_sha256": row["receipt_digest"],
            "curriculum_angle": row["angle"],
            "lenses": list(LENSES),
            "unique_source_transitions": steps,
            "repetition": {
                "replayed_native_steps": replays,
                "reverse_checkpoint_count": len(checkpoints),
                "new_training_examples_from_replay": 0,
            },
            "companion_viewing": {
                "frame_sequence_sha256": _digest(frames),
                "audio_sequence_sha256": _digest(audio),
                "visual_change_sequence_sha256": _digest(visual),
                "frames_observed_as_digests": len(frames),
                "native_rgb24_frames_optically_inspected": optical_sources,
                "native_rgb24_optical_sequence_sha256": (
                    _digest(optics) if optics else None
                ),
                "semantic_video_witness_verified": False,
                "status": ("native_pixel_optics_measured_semantic_review_pending"
                           if optical_sources else "telemetry_indexed_media_viewer_required"),
            },
            "ai_playing": {
                "actual_native_steps": steps,
                "actual_q_table_updates": updates,
                "counterfactual_native_probes": len(counter),
                "controller_only_probes": len(controllers),
            },
            "adversarial_review": {
                "ten_replay_checks_passed": True,
                "counterfactuals_excluded_from_policy_updates": True,
                "heldout_excluded_from_training": True,
                "independent_model_critic_executed": False,
            },
        })
    _require(total_steps <= MAX_STEPS
             and report.get("actual_training_steps") == total_steps
             and report.get("actual_q_table_updates") == total_q,
             "triangle native gameplay totals differ from the report")
    samples = data["candidate_samples"]
    _require(len(samples) == total_steps, "triangle cannot amplify missing or duplicate samples")
    seen_samples: set[tuple[str, int]] = set()
    for sample in samples:
        _require(type(sample) is dict and sample.get("source") ==
                 "independently_replayed_emulator_transition",
                 "triangle dataset contains an unverified/simulated training sample")
        trace, sequence = sample.get("trace_digest"), sample.get("sequence")
        _require(_sha(trace) and trace in proofs and type(sequence) is int
                 and 1 <= sequence <= proofs[trace]["steps"]
                 and sample.get("seed") == proofs[trace]["seed"]
                 and sample.get("environment_digest") ==
                 report["environment"].get("environment_digest")
                 and sample.get("verified_training_projection_sha256") ==
                 proofs[trace]["projections"][sequence - 1]
                 and (trace, sequence) not in seen_samples,
                 "triangle duplicate, altered or cross-source episode sample")
        _require(set(sample) == {
            "trace_digest", "environment_digest", "seed", "sequence",
            "verified_training_projection_sha256", "observation", "action",
            "next_observation", "measured_reward", "measured_reward_components",
            "terminated", "truncated", "source",
        } and _digest({
            "sequence": sequence, "observation": sample["observation"],
            "action": sample["action"], "next_observation": sample["next_observation"],
            "reward": sample["measured_reward"],
            "reward_components": sample["measured_reward_components"],
            "terminated": sample["terminated"], "truncated": sample["truncated"],
        }) == sample["verified_training_projection_sha256"],
                 "triangle source numeric features do not match native replay projection")
        seen_samples.add((trace, sequence))
    samples_by_trace: dict[str, list[dict[str, Any]]] = {trace: [] for trace in proofs}
    for sample in samples:
        samples_by_trace[sample["trace_digest"]].append(sample)
    # These are genuinely different deterministic readings of the SAME data.
    # Keeping feature and trace hashes together prevents a lens from silently
    # inflating the sample count or leaking heldout gameplay to the candidate set.
    for view in views:
        trace = view["source_trace_sha256"]
        episode = episodes[view["run_index"]]
        ordered = sorted(samples_by_trace[trace], key=lambda item: item["sequence"])
        _require(len(ordered) == view["unique_source_transitions"],
                 "each lens requires every source action exactly once")
        view["grounded_lens_evidence"] = {
            "visual_state": {
                "source_frame_sequence_sha256": view["companion_viewing"]["frame_sequence_sha256"],
                "measured_pixel_optics_sha256": view["companion_viewing"]["native_rgb24_optical_sequence_sha256"],
            },
            "audio_ambience": {
                "source_audio_sequence_sha256": view["companion_viewing"]["audio_sequence_sha256"],
            },
            "controller_action": {
                "action_sequence_sha256": _digest([item["action"] for item in ordered]),
            },
            "reward_and_consequence": {
                "measured_reward_sequence_sha256": _digest([
                    [item["measured_reward"], item["measured_reward_components"]]
                    for item in ordered
                ]),
            },
            "temporal_reversal": {
                "reverse_checkpoint_sha256": _digest(episode["reverse_checkpoints"]),
            },
            "causal_counterfactual": {
                "real_native_probe_sha256": _digest(episode["counterfactual_probes"]),
                "simulation_is_new_training_data": False,
            },
            "policy_progress": {
                "actual_episode_q_updates": episode["actual_tabular_q_updates"],
                "committed_policy_snapshot_sha256": episode.get("policy_snapshot_digest_after"),
            },
            "adversarial_boundary": {
                "native_scrutiny_sha256": _digest(episode["scrutiny_checks"]),
                "independent_critic_attested": False,
            },
        }
    boomerangs = report.get("boomerang_replay_receipts")
    _require(type(boomerangs) is list and all(
        type(b) is dict and b.get("reparse_verified") is True
        and b.get("policy_updates") == 0
        and _sha(b.get("original_trace_digest")) and b["original_trace_digest"] in proofs
        and type(b.get("replayed_steps")) is int and b["replayed_steps"] >= 1
        and b.get("return_receipt_digest") == _digest({
            k: v for k, v in b.items() if k != "return_receipt_digest"
        }) for b in boomerangs), "boomerang revisits cannot create synthetic independent data")
    _require(report.get("heldout_evaluation") is not None,
             "separate heldout evaluation must remain present")
    challenges = []
    for angle in ANGLES:
        if not coverage[angle]:
            challenges.append({"kind": "unobserved_curriculum_angle", "angle": angle})
    for view in views:
        if view["ai_playing"]["counterfactual_native_probes"] == 0:
            challenges.append({"kind": "no_counterfactual_native_probe",
                               "source_trace_sha256": view["source_trace_sha256"]})
        challenges.append({
            "kind": "dragon_semantic_view_pending",
            "source_trace_sha256": view["source_trace_sha256"],
            "frame_sequence_sha256": view["companion_viewing"]["frame_sequence_sha256"],
        })
        challenges.append({
            "kind": "independent_model_red_team_pending",
            "source_trace_sha256": view["source_trace_sha256"],
            "source_receipt_sha256": view["source_receipt_sha256"],
        })
    triangle = {
        "schema_version": SCHEMA,
        "parent_emulator_evidence_sha256": report["report_digest"],
        "vertices": {
            "dragon_companion_viewing": (
                "native_pixel_optics_measured_semantic_review_pending"
                if all(view["companion_viewing"]["native_rgb24_frames_optically_inspected"]
                       == view["unique_source_transitions"] for view in views)
                else "telemetry_indexed_awaiting_semantic_media_review"
            ),
            "jeeves_ai_playing_and_simulation": "verified_actual_native_gameplay",
            "adversarial_reviewer": "deterministic_scrutiny_passed_independent_model_review_pending",
        },
        "lens_catalog": list(LENSES),
        "episode_lens_references": views,
        "repeat_and_simulation_accounting": {
            "verified_reverse_replay_steps": total_replay,
            "verified_boomerang_replays": len(boomerangs),
            "real_counterfactual_probe_count": total_counter,
            "additional_independent_training_samples_from_repetition": 0,
        },
        "source_diversity": {
            "unique_native_episodes": len(views),
            "unique_measured_training_transitions": total_steps,
            "unique_observed_frame_hashes": len(seen_frames),
            "actual_native_rgb24_optical_frames": sum(
                v["companion_viewing"]["native_rgb24_frames_optically_inspected"] for v in views
            ),
            "curriculum_lenses_exercised": sum(bool(v) for v in coverage.values()),
            "curriculum_lenses_available": len(coverage),
            "by_angle": coverage,
        },
        "adversarial_challenge_queue": challenges,
        "training": {
            "existing_tabular_q_updates": total_q,
            "additional_q_updates_from_triangle": 0,
            "additional_neural_optimizer_steps_from_triangle": 0,
            "production_jeeves_weight_updates": 0,
            "dataset_rows_after_lens_amplification": total_steps,
            "promotion_approved": False,
            "semantic_video_review_done": False,
            "independent_ai_critic_review_done": False,
        },
    }
    triangle["triangle_digest"] = _digest(triangle)
    return triangle


def verify_training_triangle(report: dict[str, Any], triangle: dict[str, Any]) -> None:
    """Compare a stored triangle with freshly reconstructed source custody."""
    _require(type(triangle) is dict and _sha(triangle.get("triangle_digest"))
             and triangle["triangle_digest"] == _digest({
                 k: v for k, v in triangle.items() if k != "triangle_digest"
             }), "training triangle receipt digest differs")
    expected = build_training_triangle(report)
    _require(triangle == expected,
             "training triangle no longer matches the exact native source evidence")
