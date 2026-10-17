"""Dragon's evidence-linked corrective lessons from real Jeeves production gates.

A lesson is a bounded reviewable operational proposal, not an AI weight,
training example, third-party game asset or a verified knowledge promotion.
It references only current hashed source evidence and explicit gate failures.
Human-approved proposals persist in the same campaign as reviewed drafts;
repeated runtime changes invalidate earlier assumptions before reuse.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from .contracts import canonical_digest
from .studio_campaign import (
    CampaignOrder, _atomic_json, _load_json,
)
from .studio_campaign_assurance import (
    inspect_production_assurance, _inspect_production_assurance_unlocked,
)
from .studio_campaign_lock import campaign_lock

SCHEMA = "skeleton.game_builder.dragon_operational_lessons.v1"
REVIEW_SCHEMA = "skeleton.game_builder.dragon_lesson_review.v1"
_ALLOWED = frozenset({"approve_for_reviewed_knowledge", "reject", "needs_more_evidence"})
_LESSON_CODES = {
    "source_not_generated": (
        "source_missing", "Regenerate and checkpoint the exact original platform source",
        "Check source producer and campaign lock before rerunning target build",
    ),
    "approved_native_toolchain_missing": (
        "native_adapter_gap", "Implement a safe original source-to-ROM compiler adapter",
        "Supply a reviewed target-specific compiler and exact binary/replay validation",
    ),
    "independent_runtime_or_approval_evidence_required": (
        "independent_evidence_gap", "Run the corresponding real game runtime or review owner",
        "Collect exact source-bound target execution evidence without lowering the gate",
    ),
}
_GATE_PRIORITY = (
    "original_world_source", "replay_proof_source",
    "indexed_sprites_and_descriptors", "native_platform_source",
    "cross_engine_pixel_art_parity", "native_rom_compiled",
    "cartridge_structure_checked", "browser_javascript_playthrough_executed",
    "godot_headless_playthrough_executed", "generated_game_canvas_frames_recorded",
    "emulator_playthrough_executed", "controller_response_verified",
    "visual_and_audio_runtime_qualified", "rights_and_license_review_approved",
    "dragon_knowledge_review_approved", "extended_recovery_endurance_qualified",
    "release_signoff",
)
_HEX = re.compile(r"[a-f0-9]{64}\Z")


class DragonOperationalLessonError(ValueError):
    """Dragon attempted to admit unverified, stale or unapproved lesson evidence."""


def _candidate(
    report_digest: str, target: str, gate: str, blocker: str,
    source_digest: str | None,
) -> dict:
    category, title, improvement = _LESSON_CODES.get(
        blocker, _LESSON_CODES["independent_runtime_or_approval_evidence_required"]
    )
    body = {
        "schema": SCHEMA, "report_digest": report_digest,
        "target": target, "gate": gate,
        "blocker": blocker, "category": category,
        "title": title, "proposed_improvement": improvement,
        "source_receipt_digest": source_digest,
        "lesson_source": "actual_campaign_assurance_blocker",
        "training_example_promoted": False,
        "model_weights_modified": False,
        "knowledge_reviewed": False,
        "rights_clearance_inferred": False,
        "automatic_retry_authorized": False,
    }
    return {**body, "candidate_digest": canonical_digest(body)}


def _candidates(report: dict, maximum: int) -> list[dict]:
    evidence = []
    for target in report["targets"]:
        for gate in _GATE_PRIORITY:
            item = target["gates"].get(gate)
            if not isinstance(item, dict) or item.get("blocker") is None:
                continue
            evidence.append(_candidate(
                report["report_digest"], target["target"], gate,
                item["blocker"], target["source_receipt_digest"],
            ))
            if len(evidence) >= maximum:
                return evidence
    return evidence


def propose_dragon_operational_lessons(
    order: CampaignOrder, campaign: str | Path, *, authorized: bool,
    limit: int = 24,
) -> dict:
    if authorized is not True:
        raise PermissionError("Dragon's local production learning requires operator approval")
    if type(limit) is not int or not 1 <= limit <= 64:
        raise DragonOperationalLessonError("lesson generation bound must be 1..64")
    report = inspect_production_assurance(order, campaign)
    return _project_proposals(report, limit)


def _project_proposals(report: dict, limit: int) -> dict:
    choices = _candidates(report, limit)
    body = {
        "schema": SCHEMA, "campaign_identity": report["campaign_identity"],
        "assurance_report_digest": report["report_digest"],
        "candidate_count": len(choices), "candidates": choices,
        "review_required": True,
        "approved_for_model_training": False,
        "weights_changed": False,
        "almanac_knowledge_promoted": False,
    }
    return {**body, "proposal_digest": canonical_digest(body)}


def review_dragon_operational_lesson(
    order: CampaignOrder, campaign: str | Path, candidate_digest: str,
    decision: str, reviewer_note: str, *, authorized: bool,
    human_reviewed: bool,
) -> dict:
    if authorized is not True or human_reviewed is not True:
        raise PermissionError("human operator must review each Dragon operational lesson")
    if (type(candidate_digest) is not str or not _HEX.fullmatch(candidate_digest)
            or decision not in _ALLOWED
            or type(reviewer_note) is not str or not 10 <= len(reviewer_note) <= 600
            or any(ord(c) < 32 and c not in "\n\t" for c in reviewer_note)):
        raise DragonOperationalLessonError("typed candidate, decision and bounded review note required")
    root = Path(campaign)
    # The same OS lock protects the entire source/qualification/read transaction.
    # inspect_production_assurance acquires that lock itself, so derive its
    # report first and revalidate source status while holding the write lock.
    projection = propose_dragon_operational_lessons(
        order, root, authorized=True, limit=64,
    )
    candidate = next((item for item in projection["candidates"]
                      if item["candidate_digest"] == candidate_digest), None)
    if candidate is None:
        raise DragonOperationalLessonError("lesson candidate is stale or not evidence-backed")
    with campaign_lock(root):
        current = _inspect_production_assurance_unlocked(order, root)
        if (current["campaign_identity"] != projection["campaign_identity"]
                or current["report_digest"] != projection["assurance_report_digest"]):
            raise DragonOperationalLessonError("production evidence changed during human review")
        identity = current["campaign_identity"]
        # The currently locked exact-source and runtime report is the lesson
        # revision. A later source/playthrough change invalidates this review.
        body = {
            "schema": REVIEW_SCHEMA,
            "campaign_identity": identity,
            "assurance_report_digest": projection["assurance_report_digest"],
            "candidate_digest": candidate_digest, "target": candidate["target"],
            "gate": candidate["gate"], "blocker": candidate["blocker"],
            "decision": decision,
            "reviewer_note": reviewer_note,
            "human_reviewed": True,
            "model_weights_modified": False,
            "training_authorized": False,
            "knowledge_promoted": False,
        }
        entry = {**body, "review_digest": canonical_digest(body)}
        folder = root / "dragon_reviews"
        if folder.is_symlink():
            raise DragonOperationalLessonError("Dragon review folder cannot be a symlink")
        folder.mkdir(exist_ok=True)
        dest = folder / (candidate_digest + ".json")
        if dest.exists() or dest.is_symlink():
            existing = _load_json(dest)
            if existing != entry:
                raise DragonOperationalLessonError("existing human review cannot be silently overwritten")
            return existing
        _atomic_json(dest, entry)
        return entry


def inspect_dragon_reviewed_lessons(
    order: CampaignOrder, campaign: str | Path, *, authorized: bool,
) -> dict:
    if authorized is not True:
        raise PermissionError("reviewed operational lessons require operator approval")
    root = Path(campaign)
    with campaign_lock(root):
        proposed = _project_proposals(
            _inspect_production_assurance_unlocked(order, root), 64,
        )
        allowed = {x["candidate_digest"] for x in proposed["candidates"]}
        reviews = []
        folder = root / "dragon_reviews"
        if folder.is_symlink():
            raise DragonOperationalLessonError("Dragon operational review root is not an ordinary folder")
        if folder.exists():
            for entry in sorted(folder.iterdir()):
                if (entry.is_symlink() or not entry.is_file()
                        or not _HEX.fullmatch(entry.stem)
                        or entry.suffix != ".json"):
                    raise DragonOperationalLessonError("unrecognized Dragon lesson review")
                if len(reviews) >= 64:
                    raise DragonOperationalLessonError("bounded human-reviewed lesson inventory exceeded")
                review = _load_json(entry)
                if (review.get("schema") != REVIEW_SCHEMA
                        or review.get("candidate_digest") != entry.stem
                        or review.get("candidate_digest") not in allowed
                        or review.get("assurance_report_digest") != proposed["assurance_report_digest"]
                        or review.get("human_reviewed") is not True
                        or review.get("decision") not in _ALLOWED
                        or review.get("model_weights_modified") is not False
                        or review.get("knowledge_promoted") is not False
                        or canonical_digest({k: v for k, v in review.items()
                                             if k != "review_digest"}) != review.get("review_digest")):
                    raise DragonOperationalLessonError("stale or forged human-reviewed lesson")
                reviews.append(review)
        body = {
            "schema": SCHEMA, "campaign_identity": proposed["campaign_identity"],
            "assurance_report_digest": proposed["assurance_report_digest"],
            "human_reviewed_lessons": len(reviews),
            "reviewed_lessons": reviews,
            "approved_operational_drafts": sum(
                x["decision"] == "approve_for_reviewed_knowledge" for x in reviews
            ),
            "knowledge_promoted": False,
            "model_training_performed": False,
        }
        return {**body, "summary_digest": canonical_digest(body)}


__all__ = [
    "DragonOperationalLessonError", "propose_dragon_operational_lessons",
    "review_dragon_operational_lesson", "inspect_dragon_reviewed_lessons",
]
