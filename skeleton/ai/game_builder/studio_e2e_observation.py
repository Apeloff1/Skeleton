"""Read-only Dragon observation of the *existing* Jeeves studio goal journal.

This is a projection, not a second state store, model provider, task runner,
screen recorder, training engine or permission authority. The application
owner validates scope, permissions and the sealed goal journal BEFORE calling
this code. The projection exposes only allowlisted operational metadata.
Raw model prompts, responses, game sources, secrets and video never escape.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

SCHEMA = "skeleton.game.studio_e2e_observation.v1"
GOAL_SCHEMA = "skeleton.game.studio_goal.v2"
MAX_STEPS = 16
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_OPERATION = re.compile(r"[a-z][a-z0-9_.-]{0,95}\Z")
_STAGES = {
    "design": {"catalog", "knowledge.search", "lessons.search", "project.inspect", "world.inspect",
               "source.inspect", "console.inspect", "successor.inspect"},
    "authoring": {"console.edit", "world.edit", "successor.adopt",
                  "campaign.champion.adopt", "successor.synthesize"},
    "build": {"build", "build.inspect", "desktop.build", "desktop.inspect", "artifact.admit"},
    "playthrough": {"simulate", "play.start", "artifact.preview", "artifact.play"},
    "review": {"project.review", "successor.compare", "knowledge.practice"},
    "package": {"artifact.export", "project.export", "successor.export"},
    "training": {"train", "artifact.train", "artifact.campaign"},
    "recovery": {"job.resume", "job.cancel", "play.resume", "play.stop", "campaign.pause",
                 "campaign.cancel"},
}
# This is intentionally a small safe projection, not a copy of game or model output.
_ALLOWED_STATUS = frozenset({
    "ready", "running", "waiting", "paused", "cancelled", "completed", "planned",
    "expired", "failed", "blocked", "interrupted", "pending",
})


class StudioObservationError(ValueError):
    """Malformed, unverified or unbounded observational input."""


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise StudioObservationError(label + " must be an actual SHA-256 digest")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or value != value.strip():
        raise StudioObservationError("invalid " + label)
    return value


def _stage(operation: str) -> str:
    return next((name for name, ops in _STAGES.items() if operation in ops), "other")


def _events(steps: list, *, root: str) -> list[dict]:
    """Derive a chain from verified source receipts; never claim screen capture."""
    previous = _digest({"schema": SCHEMA, "root": root})
    observations = []
    for index, step in enumerate(steps):
        source = _sha(step["step_digest"], "step digest")
        operation = step.get("decision", {}).get("operation")
        if operation is None and step.get("decision", {}).get("done") is True:
            operation = "done"
        if not isinstance(operation, str) or _OPERATION.fullmatch(operation) is None:
            raise StudioObservationError("unknown or invalid model decision operation")
        executed = step.get("executed")
        if type(executed) is not bool:
            raise StudioObservationError("execution evidence must be boolean")
        stage = _stage(operation)
        # A model receipt records that a decision occurred, not that the model
        # was correct, that a tool succeeded or that learned weights changed.
        has_model_receipt = bool(step.get("model_receipt"))
        kinds = (["jeeves.decision"] if has_model_receipt else []) + [
            "builder.action_observed" if executed else "builder.non_execution_observed"
        ]
        for kind in kinds:
            record = {
                "sequence": len(observations) + 1,
                "step_index": index,
                "kind": kind,
                "operation": operation,
                "stage": stage,
                "source_step_digest": source,
                "executed": executed if kind.startswith("builder.") else False,
                "verification": "goal_journal_only",
                "video_recorded": False,
                "trained_model": False,
                "knowledge_promoted": False,
                "previous_event_digest": previous,
            }
            record["event_digest"] = _digest(record)
            previous = record["event_digest"]
            observations.append(record)
    return observations


def observe_goal(goal: Mapping, *, after: int = 0, limit: int = 8) -> dict:
    """Project a scope-checked, CURRENT, already-verified goal.

    The caller MUST first use game_studio_agent.inspect, which validates the
    canonical journal and source authority. This function rejects legacy
    unverified journals; it does not accept caller-supplied verification flags.
    Pagination is by production step, with a digest-bound event chain.
    """
    if not isinstance(goal, Mapping) or goal.get("schema_version") != GOAL_SCHEMA:
        raise StudioObservationError("verified current Jeeves goal required")
    if type(after) is not int or not 0 <= after <= MAX_STEPS:
        raise StudioObservationError("invalid observation cursor")
    if type(limit) is not int or not 1 <= limit <= MAX_STEPS:
        raise StudioObservationError("invalid observation page size")
    goal_id = _identifier(goal.get("goal_id"), "goal_id")
    project_id = _identifier(goal.get("project_id"), "project_id")
    status = goal.get("status")
    if not isinstance(status, str) or status not in _ALLOWED_STATUS:
        raise StudioObservationError("invalid goal status")
    history_head = _sha(goal.get("history_digest"), "history digest")
    steps = goal.get("steps")
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise StudioObservationError("bounded source history required")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise StudioObservationError("typed source history required")
        _sha(step.get("step_digest"), "step digest")
        prior = _sha(step.get("previous_step_digest"), "previous step digest")
        if index and prior != steps[index - 1]["step_digest"]:
            raise StudioObservationError("source history linkage is broken")
        if type(step.get("index")) is not int or step["index"] != index:
            raise StudioObservationError("source step index mismatch")
        if not isinstance(step.get("decision"), dict):
            raise StudioObservationError("source decision required")
    if steps and steps[-1]["step_digest"] != history_head:
        raise StudioObservationError("goal history head does not match latest receipt")

    # Project all bounded steps first to preserve page-independent event hashes.
    all_events = _events(steps, root=goal_id)
    visible = [row for row in all_events if after <= row["step_index"] < after + limit]
    observed_counts = {name: 0 for name in _STAGES}
    observed_counts["other"] = 0
    actions_executed = 0
    for row in steps:
        operation = row["decision"].get("operation") or "done"
        if row.get("executed") is True:
            observed_counts[_stage(operation)] += 1
            actions_executed += 1

    requested = goal.get("completion_requirements", [])
    if not isinstance(requested, list) or len(requested) > 7 or any(
        not isinstance(item, str) or len(item) > 32 for item in requested
    ):
        raise StudioObservationError("invalid verification requirements")
    completion = goal.get("completion") or {}
    if not isinstance(completion, dict):
        raise StudioObservationError("invalid completion receipt")
    verified = completion.get("verified") is True
    # The owner is the only source of completion proof; counting events never
    # raises qualification. Status 'completed' alone is insufficient.
    recovery = goal.get("recovery") or {}
    if not isinstance(recovery, dict):
        raise StudioObservationError("invalid recovery projection")
    next_action = recovery.get("next_action")
    if not isinstance(next_action, (str, type(None))) or next_action not in {"retry", "advance", "wait", "inspect_dependency",
                           "resume", "inspect", "authorize", "stop", None}:
        next_action = "inspect"

    return {
        "schema_version": SCHEMA,
        "source": "verified_scoped_jeeves_goal_journal",
        "goal_id": goal_id,
        "project_id": project_id,
        "status": status,
        "history_digest": history_head,
        "journal_integrity": "validated_by_canonical_goal_owner",
        "observations": visible,
        "total_observations": len(all_events),
        "after": after,
        "next_cursor": after + limit if after + limit < len(steps) else None,
        "observed_stages": observed_counts,
        "actions_executed": actions_executed,
        "steps_observed": len(steps),
        "completion_requirements": list(requested),
        "workflow_requirements_verified": verified,
        "game_qualified": False,
        "dragon_learning": {
            "mode": "observation_only",
            "candidate_count": 0,
            "observed_action_count": len([row for row in visible if row["kind"] == "builder.action_observed"]),
            "promotion": "not_authorized",
            "model_training": "not_authorized",
            "screen_video": "not_captured",
            "next_review": "explicit consent, source review and independent evidence required",
        },
        "recovery_next_action": next_action or "inspect",
        "page_digest": _digest(visible),
        "head_event_digest": all_events[-1]["event_digest"] if all_events else None,
    }


def observe_production_campaign(
    order: object, destination: object, *, authorized: bool,
    after: int = 0, limit: int = 16,
) -> dict:
    """Dragon's read-only view of a CURRENT verified source/ROM campaign.

    This is neither an app recording nor an admission to the Dragon's almanac.
    The source-checking owner is consulted on every call. Observations contain
    no raw prompts, game code, model logs, audio samples or document paths.
    """
    from .studio_campaign import CampaignOrder
    from .studio_campaign_assurance import inspect_production_assurance

    if authorized is not True:
        raise PermissionError("Dragon production observation requires operator authority")
    if not isinstance(order, CampaignOrder):
        raise StudioObservationError("typed original game production order required")
    if type(after) is not int or not 0 <= after <= 256:
        raise StudioObservationError("invalid production event cursor")
    if type(limit) is not int or not 1 <= limit <= 32:
        raise StudioObservationError("invalid production observation page size")
    report = inspect_production_assurance(order, destination)
    previous = _digest({
        "schema": SCHEMA, "type": "production_campaign",
        "campaign_identity": report["campaign_identity"],
    })
    records = []
    for target in report["targets"]:
        events = [
            ("studio.source_integrity_checked", target["source_receipt_digest"]),
            ("studio.cross_engine_pixel_parity", target["cross_engine_pixel_parity_digest"]),
            ("studio.rom_structure_checked", target["native_binary_evidence_digest"]),
            ("studio.native_cpu_dpad_playthrough", target["real_emulator_evidence_digest"]),
            ("studio.browser_javascript_replay", target["browser_javascript_evidence_digest"]),
            ("studio.godot_headless_replay", target["godot_headless_evidence_digest"]),
            ("studio.generated_game_canvas_frames", target["generated_canvas_evidence_digest"]),
        ]
        for kind, source_digest in events:
            if source_digest is None:
                continue
            source_digest = _sha(source_digest, "production evidence digest")
            record = {
                "sequence": len(records) + 1, "kind": kind,
                "target": target["target"],
                "source_evidence_digest": source_digest,
                "verification": "local_exact_source_and_artifact_integrity",
                "video_recorded": False,
                "human_controller_playthrough_verified": False,
                "model_training_performed": False,
                "knowledge_promoted": False,
                "previous_event_digest": previous,
            }
            record["event_digest"] = _digest(record)
            previous = record["event_digest"]
            records.append(record)
    page = records[after:after + limit]
    return {
        "schema_version": SCHEMA,
        "source": "verified_local_game_production_assurance",
        "campaign_identity": report["campaign_identity"],
        "assurance_report_digest": report["report_digest"],
        "observations": page,
        "total_observations": len(records),
        "next_cursor": after + limit if after + limit < len(records) else None,
        "head_event_digest": previous if records else None,
        "page_digest": _digest(page),
        "source_completed_target_count": report["targets_with_exact_source"],
        "cross_engine_pixel_parity_count": sum(
            row["cross_engine_pixel_parity_digest"] is not None
            for row in report["targets"]
        ),
        "rom_structurally_checked_count": report["native_roms_structurally_verified"],
        "compiled_original_psg_tables_checked": (
            report["compiled_original_psg_tables_verified"]
        ),
        "actual_native_rom_victory_replays": report["native_rom_machine_code_playthroughs_verified"],
        "actual_native_cpu_checkpoint_samples": report["native_cpu_checkpoint_samples_verified"],
        "original_native_animation_audio_sources_checked": (
            report["original_console_media_sources_independently_checked"]
        ),
        "original_native_animation_frames_in_source": (
            report["original_console_animation_frames_in_source"]
        ),
        "actual_native_psg_hardware_audio_verified": False,
        "actual_browser_javascript_replays": report["browser_javascript_playthroughs_verified"],
        "actual_godot_headless_replays": report["godot_headless_playthroughs_verified"],
        "generated_game_canvas_captures": report["generated_game_canvas_captures_verified"],
        "release_ready": False,
        "learned_new_weights": False,
        "dragon_knowledge_admitted": False,
        "screen_or_video_recorded": False,
        "next_action": "review production blockers and authorize explicit verification",
    }


def observe_tool_execution(outcome: object) -> dict:
    """Bridge the *actual* typed local tool outcome to a Dragon-safe summary."""
    from .studio_execution_plane import ExecutionOutcome

    if not isinstance(outcome, ExecutionOutcome):
        raise StudioObservationError("actual local execution outcome required")
    from .studio_execution_plane import EXECUTABLE_TOOLS

    _sha(outcome.intent_digest, "intent digest")
    _sha(outcome.plan_digest, "tool plan digest")
    if len(outcome.receipts) > 32:
        raise StudioObservationError("too many executed tool receipts")
    rows = []
    previous_receipt = None
    previous = _digest({"intent_digest": outcome.intent_digest, "plan_digest": outcome.plan_digest})
    for index, receipt in enumerate(outcome.receipts):
        if (receipt.index != index or receipt.predecessor_digest != previous_receipt
                or receipt.tool_id not in EXECUTABLE_TOOLS or receipt.status != "executed"):
            raise StudioObservationError("tool execution receipt linkage or capability invalid")
        _sha(receipt.output_digest, "tool output")
        _sha(receipt.evidence_digest, "tool evidence")
        previous_receipt = receipt.digest
        record = {
            "tool_id": receipt.tool_id,
            "receipt_digest": receipt.digest,
            "source_evidence_digest": receipt.evidence_digest,
            "output_digest": receipt.output_digest,
            "status": receipt.status,
            "previous_observation_digest": previous,
        }
        record["observation_digest"] = _digest(record)
        previous = record["observation_digest"]
        rows.append(record)
    return {
        "schema_version": SCHEMA,
        "source": "actual_typed_local_tool_execution",
        "intent_digest": outcome.intent_digest,
        "plan_digest": outcome.plan_digest,
        "outcome_digest": outcome.digest,
        "observations": rows,
        "head_observation_digest": previous,
        "screen_video": "not_captured",
        "training": "not_authorized",
        "model_or_hardware_certification": False,
        "e2e_evidence": {
            "world_constructed": outcome.world is not None,
            "winning_python_replay": bool(
                outcome.project is not None
                and outcome.project.proof.final_state.status == "won"
            ),
            "browser_source_compiled": outcome.project is not None,
            "godot_source_generated": outcome.package is not None,
            "adversarial_mirror_passed": bool(outcome.mirror and outcome.mirror.passed),
            "source_exported": outcome.exported_path is not None,
        },
    }
