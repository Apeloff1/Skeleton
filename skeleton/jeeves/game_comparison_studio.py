"""Comparative native-game studio: at most 30 games, ten simultaneous workers.

Uses the existing approved Jeeves GameEmulatorRegistry and native host. Every
observation is from a real isolated libretro process; no game or visual samples
are fabricated and no commercial game bytes are copied into knowledge cards.
Viewer notes and Dragon notes are *supplied* claims, never web facts invented
by this process. A validated offline trace is not a trained model.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .game_comparison_schema import (
    ComparativeStudyError, PHASES, digest, plan_study, validate_study,
)

SCHEMA = "skeleton.game.comparative_study_result.v1"
MAX_PREVIEW_URI = 160000
MAX_PREVIEWS_TOTAL = 90
MAX_REPORT_BYTES = 24 * 1024 * 1024


def _stage_checkpoints(length: int) -> dict[str, int]:
    if not 3 <= length <= 64:
        raise ComparativeStudyError("Exactly three ordered stage observations require 3–64 native input actions")
    return {
        "earlier": max(1, length // 3),
        "middle": max(2, (2 * length) // 3),
        "after": length,
    }


def _source_file(game: Mapping[str, object]) -> tuple[bytes, str]:
    """Read a bounded, nonsymlink operator-owned local ROM with TOCTOU checks."""
    import stat
    from .game_emulator_catalog import MAX_CONTENT_BYTES

    path = Path(game["source_path"])
    if not path.is_absolute() or path.is_symlink():
        raise ComparativeStudyError("Operator source path must be an absolute nonsymlink regular file")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_CONTENT_BYTES:
            raise ComparativeStudyError("Operator ROM must be a bounded regular local file")
        with os.fdopen(os.dup(fd), "rb") as source:
            data = source.read(MAX_CONTENT_BYTES + 1)
        after = os.fstat(fd)
        if (len(data) != before.st_size or
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ComparativeStudyError("Operator ROM mutated during source admission")
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != game["source_sha256"]:
        raise ComparativeStudyError("Operator game source differs from the SHA-256 pinned in the study")
    return data, path.name


def _observe_one(
    game: dict[str, Any],
    *,
    expected_registry_digest: str,
    include_previews: bool,
    shadow_policy_training: bool,
    authorize_training: Callable[[], None] | None,
    cancelled: Callable[[], bool] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    from .game_emulator_host import create_emulator_environment

    if cancelled is not None and cancelled():
        raise ComparativeStudyError("Operator cancelled the comparative study")
    source, filename = _source_file(game)
    tape = game["actions"]
    checkpoints = _stage_checkpoints(len(tape))
    observed: dict[str, Any] = {}
    observation_count = 0
    summaries: dict[str, list[float]] = {name: [] for name in ("visual_change", "audio_rms", "screen_mean")}
    with create_emulator_environment(
        game["target_id"],
        core_id=game["core_id"],
        expected_registry_digest=expected_registry_digest,
        rom_source=source,
        filename=filename,
        max_steps=len(tape),
        frames_per_step=game["frames_per_step"],
        controller_devices=game["controller_devices"],
        timeout_seconds=timeout_seconds,
        cancelled=cancelled,
    ) as env:
        env.reset(game["seed"])
        for index, action in enumerate(tape, 1):
            if cancelled is not None and cancelled():
                raise ComparativeStudyError("Operator cancelled comparative native observation")
            step = env.step(action)
            observation_count += 1
            for name in summaries:
                summaries[name].append(float(step.observation[name]))
            for phase, chosen in checkpoints.items():
                if chosen != index:
                    continue
                frame = dict(env._frame)
                pixel_sha = frame["pixel_sha256"]
                stage = {
                    "phase": phase,
                    "step": index,
                    "source": "actual_isolated_libretro",
                    "evidence_ref": game["id"] + ":" + phase,
                    "evidence_sha256": digest([
                        env.spec.environment_digest, game["source_sha256"],
                        env.core.library_sha256, phase, index,
                        step.transition_digest, pixel_sha, frame["audio_sha256"],
                    ]),
                    "frame_sha256": pixel_sha,
                    "audio_sha256": frame["audio_sha256"],
                    "native_frames": frame["runs"],
                    "video_callbacks": frame["video_callbacks"],
                    "audio_frames": frame["audio_frames"],
                    "width": frame["width"], "height": frame["height"],
                    "rotation": frame["rotation"],
                    "observations": {
                        name: float(step.observation[name])
                        for name in ("screen_mean", "visual_change", "audio_rms", "step_fraction")
                    },
                    "reward_semantics": "visual difference, not victory",
                    "transition_sha256": step.transition_digest,
                    "image_data_uri": None,
                    "preview_limit": "not_requested",
                }
                if include_previews:
                    preview = env.preview()
                    uri = preview["data_uri"] if preview else None
                    if isinstance(uri, str) and uri.startswith("data:image/png;base64,") and len(uri) <= MAX_PREVIEW_URI:
                        stage["image_data_uri"] = uri
                        stage["preview_limit"] = "bounded_actual_native_frame"
                    else:
                        stage["preview_limit"] = "native_preview_unavailable_or_over_size_limit"
                observed[phase] = stage
        if set(observed) != set(PHASES):
            raise ComparativeStudyError("Native episode lacked one or more stage frames")
        # Second actual run emits full canonical hash-chained offline trace.
        # This has no hidden model weight side effect or success label.
        trace = env.capture_training_trace(
            tape, seed=game["seed"], rights_evidence_digest=game["rights_evidence_digest"]
        )
        actual_core_sha = env.core.library_sha256
        environment_sha = env.spec.environment_digest
        training = None
        if shadow_policy_training:
            if game["rights_evidence_digest"] is None or authorize_training is None:
                raise ComparativeStudyError("Training requires explicit operator source-rights receipt and per-step authorization")
            from .game_comparison_shadow_learning import train_study_local_policy

            training = train_study_local_policy(
                spec=env.spec,
                trace=trace,
                game_id=game["id"],
                rights_evidence_digest=game["rights_evidence_digest"],
                authorize=authorize_training,
                cancelled=cancelled,
            )
    metrics = {
        "observed_step_count": observation_count,
        "mean_visual_change": sum(summaries["visual_change"]) / observation_count,
        "mean_audio_rms": sum(summaries["audio_rms"]) / observation_count,
        "mean_screen_brightness": sum(summaries["screen_mean"]) / observation_count,
    }
    return {
        "id": game["id"], "title": game["title"],
        "series_id": game["series_id"], "release_order": game["release_order"],
        "release_year": game["release_year"], "series_phase": game["series_phase"],
        "target_id": game["target_id"], "core_id": game["core_id"],
        "source_sha256": game["source_sha256"],
        "core_sha256": actual_core_sha,
        "environment_sha256": environment_sha,
        "status": "actual_native_observations_captured",
        "phases": observed,
        "metrics": metrics,
        "canonical_offline_trace_sha256": trace["trace_digest"],
        "trace_step_count": trace["steps"],
        "study_local_tabular_training": training,
        "legal_rom_rights_independently_verified": False,
        "human_gameplay_quality_verified": False,
        "production_ai_model_weights_trained": False,
    }


def _pair_report(pair: Mapping[str, Any], results: Mapping[str, dict]) -> dict[str, Any]:
    a, b = results.get(pair["left_id"]), results.get(pair["right_id"])
    report: dict[str, Any] = {
        "left_id": pair["left_id"], "right_id": pair["right_id"],
        "questions": list(pair["questions"]),
        "status": "both_games_not_yet_observed",
        "phase_comparisons": [],
        "interpretation": "Numerical observations compare frames, not which game is better",
    }
    if not a or not b or a.get("status") != "actual_native_observations_captured" or b.get("status") != "actual_native_observations_captured":
        return report
    report["status"] = "paired_native_observations_available"
    for phase in PHASES:
        left, right = a["phases"][phase], b["phases"][phase]
        report["phase_comparisons"].append({
            "phase": phase,
            "left_evidence_ref": left["evidence_ref"],
            "right_evidence_ref": right["evidence_ref"],
            "left_evidence_sha256": left["evidence_sha256"],
            "right_evidence_sha256": right["evidence_sha256"],
            "same_exact_frame_sha256": left["frame_sha256"] == right["frame_sha256"],
            "same_exact_audio_sha256": left["audio_sha256"] == right["audio_sha256"],
            "screen_mean_absolute_difference": abs(left["observations"]["screen_mean"] - right["observations"]["screen_mean"]),
            "audio_rms_absolute_difference": abs(left["observations"]["audio_rms"] - right["observations"]["audio_rms"]),
            "resolution_equal": (left["width"], left["height"]) == (right["width"], right["height"]),
            "accuracy_winner": None,
        })
    return report


def _note_card(note: Mapping[str, Any], results: Mapping[str, dict]) -> dict[str, Any]:
    anchors = []
    missing = []
    for identity in note["game_ids"]:
        game = results.get(identity)
        if not game or game.get("status") != "actual_native_observations_captured":
            missing.append(identity)
            continue
        phases = PHASES if note["checkpoint"] == "series" else (note["checkpoint"],)
        anchors.extend({
            "game_id": identity,
            "checkpoint": phase,
            "evidence_ref": game["phases"][phase]["evidence_ref"],
            "evidence_sha256": game["phases"][phase]["evidence_sha256"],
        } for phase in phases)
    grounded = not missing and bool(anchors)
    status = (
        "rejected" if note["review_status"] == "rejected"
        else "reviewed_observation_candidate" if grounded and note["review_status"] == "reviewed"
        else "needs_observation_and_human_review"
    )
    return {
        **dict(note),
        "source": "externally_authored_viewer_or_dragon_note_not_generated_by_runtime",
        "evidence": anchors,
        "missing_game_ids": missing,
        "knowledge_status": status,
        "eligible_for_reference_almanac_review": grounded and note["review_status"] == "reviewed",
        "build_parameter_candidate": (
            {**note["build_parameter"], "promotion_authorized": False, "empirically_verified": False}
            if note["build_parameter"] is not None else None
        ),
        "model_weights_changed": False,
    }


def _series_report(model: Mapping[str, Any], results: Mapping[str, dict]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for game in model["games"]:
        groups.setdefault(game["series_id"], []).append(game)
    records = []
    for series_id, installments in sorted(groups.items()):
        ordered = sorted(installments, key=lambda x: x["release_order"])
        records.append({
            "series_id": series_id,
            "installment_count_in_this_study": len(ordered),
            "ordered_installments": [
                {
                    "game_id": g["id"], "release_order": g["release_order"],
                    "release_year": g["release_year"], "era": g["series_phase"],
                    "native_evidence_status": results.get(g["id"], {}).get("status", "not_yet_executed"),
                    "early_middle_after_observations": [
                        results[g["id"]]["phases"][name]["evidence_sha256"] for name in PHASES
                    ] if results.get(g["id"], {}).get("status") == "actual_native_observations_captured" else [],
                } for g in ordered
            ],
            "series_span_policy": "The same series_id and release_order can link multiple independently bounded 30-game studies; no assertion that all series installments have been acquired.",
            "continuity_or_narrative_quality_reviewed": False,
        })
    return records


def run_comparative_study(
    raw: Mapping[str, Any],
    *,
    selected_batch: int | None = None,
    include_previews: bool = True,
    shadow_policy_training: bool = False,
    authorize_training: Callable[[], None] | None = None,
    timeout_seconds: float = 5.0,
    cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute no more than 10 actual native core sessions concurrently.

    Select one batch to investigate <=10 games or omit for sequential 10-game
    batches across the entire <=30-game study. Errors remain visible per game.
    """
    from .game_emulator_catalog import GameEmulatorRegistry

    model = validate_study(dict(raw))
    plan = plan_study(model)
    registry = GameEmulatorRegistry.from_environment()
    selected = plan["batches"]
    if selected_batch is not None:
        if type(selected_batch) is not int or not 0 <= selected_batch < len(selected):
            raise ComparativeStudyError("Selected batch index is outside the fixed 30-game plan")
        selected = [selected[selected_batch]]
    game_by_id = {game["id"]: game for game in model["games"]}
    inspected = {}
    if type(include_previews) is not bool or type(shadow_policy_training) is not bool:
        raise ComparativeStudyError("Study visualization and training controls must be exact booleans")
    if shadow_policy_training and (selected_batch is None or include_previews):
        raise ComparativeStudyError("Study-local Q-learning is limited to a selected <=10-game batch without embedded screenshots")
    if shadow_policy_training and not callable(authorize_training):
        raise ComparativeStudyError("Training needs an explicit operator-owned rights/authorization callback")
    if shadow_policy_training and any(game["rights_evidence_digest"] is None for game in model["games"] if game["id"] in {
        identity for batch in selected for identity in batch["game_ids"]
    }):
        raise ComparativeStudyError("Training cannot begin without a declared rights receipt for every selected game")
    if type(timeout_seconds) not in (int, float) or not 0.1 <= timeout_seconds <= 30:
        raise ComparativeStudyError("Native command timeout is invalid")
    if on_progress is not None and not callable(on_progress):
        raise ComparativeStudyError("Study progress callback must be callable")

    for batch in selected:
        games = [game_by_id[g] for g in batch["game_ids"]]
        # Every core is verified before any work in the batch starts.
        for game in games:
            core = registry.resolve_core(game["core_id"])
            if game["target_id"] not in core.target_ids:
                raise ComparativeStudyError("Actual approved core does not allow its assigned game target")
        with ThreadPoolExecutor(max_workers=min(len(games), model["max_active"])) as executor:
            submitted = {
                executor.submit(
                    _observe_one, game,
                    expected_registry_digest=registry.registry_digest,
                    include_previews=include_previews,
                    shadow_policy_training=shadow_policy_training,
                    authorize_training=authorize_training,
                    cancelled=cancelled, timeout_seconds=timeout_seconds,
                ): game for game in games
            }
            for future in as_completed(submitted):
                game = submitted[future]
                try:
                    evidence = future.result()
                except Exception as exc:
                    # A native failure is not a simulated observation. Do not
                    # print source path, ROM bytes, firmware or privileged logs.
                    evidence = {
                        "id": game["id"], "title": game["title"],
                        "core_id": game["core_id"], "target_id": game["target_id"],
                        "status": "native_execution_failed",
                        "error_class": type(exc).__name__,
                        "error_code": getattr(exc, "code", "native_study_error"),
                        "phases": {},
                        "trained": False,
                    }
                inspected[game["id"]] = evidence
                if on_progress is not None:
                    on_progress({
                        "study_id": model["study_id"],
                        "batch_index": batch["batch_index"],
                        "game_id": game["id"],
                        "status": evidence["status"],
                        "completed_game_count": len(inspected),
                    })
    # Keep stable document ordering despite nondeterministic worker completion.
    ordered = {g["id"]: inspected[g["id"]] for g in model["games"] if g["id"] in inspected}
    pairing = [_pair_report(pair, ordered) for pair in model["pairs"]]
    notes = [_note_card(note, ordered) for note in model["notes"]]
    knowledge_candidates = [n for n in notes if n["eligible_for_reference_almanac_review"]]
    report = {
        "schema_version": SCHEMA,
        "study_id": model["study_id"], "title": model["title"],
        "study_manifest_sha256": digest(model),
        "approved_registry_sha256": registry.registry_digest,
        "planned_total_game_count": len(model["games"]),
        "selected_batch": selected_batch,
        "actual_game_sessions_attempted": len(ordered),
        "game_observations_completed": sum(g["status"] == "actual_native_observations_captured" for g in ordered.values()),
        "native_sessions_currently_running": 0,
        "maximum_parallel_native_game_sessions": model["max_active"],
        "study_local_tabular_training_requested": shadow_policy_training,
        "games_with_study_local_q_updates": sum(
            bool(g.get("study_local_tabular_training") and g["study_local_tabular_training"]["updates_applied"] > 0)
            for g in ordered.values()
        ),
        "completed_batches": [b["batch_index"] for b in selected],
        "games": ordered, "pairs": pairing,
        "series": _series_report(model, ordered),
        "observer_notes": notes,
        "dragon_and_jeeves_knowledge_candidates": knowledge_candidates,
        "evidence_and_training_boundary": {
            "actual_native_execution_required": True,
            "all_recorded_previews_if_present_are_actual_emulator_frames": True,
            "operator_rom_rights_independently_proven": False,
            "crawling_or_video_watching_performed": False,
            "semantic_gameplay_comprehension_automatically_verified": False,
            "study_local_tabular_q_learning_executed": shadow_policy_training,
            "large_language_model_parameter_training_executed": False,
            "weight_promotion_authorized": False,
        },
    }
    # One deterministic, separately reviewable synthesis layer; never train
    # model parameters from screen brightness or a submitted viewer hypothesis.
    from .game_comparison_synthesis import synthesize_comparative_report

    report["synthesis"] = synthesize_comparative_report(report)
    report["result_sha256"] = digest(report)
    if len(json.dumps(report, sort_keys=True, allow_nan=False).encode()) > MAX_REPORT_BYTES:
        raise ComparativeStudyError("Comparative evidence exceeds 24 MiB; rerun without previews or select a single batch")
    return report
