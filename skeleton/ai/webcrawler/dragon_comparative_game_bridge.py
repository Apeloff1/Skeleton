"""Evidence-only Dragon/Jeeves comparative knowledge export.

Does not write to Dragon Family custody or promote scientific memory. Returns a
bounded, human-reviewable intake envelope whose claims point to actual native
observation digests and a distinct source of authorship. Existing Dragon custody
requires its own authenticated, consented reviewer before knowledge adoption.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

SCHEMA = "skeleton.dragon.game_comparison_intake.v1"
MAX_CARDS = 1500
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024


def export_dragon_comparison_intake(report: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(report, dict) or report.get("schema_version") != "skeleton.game.comparative_study_result.v1":
        raise ValueError("Dragon intake only accepts the exact Jeeves native comparative result")
    candidates = report.get("dragon_and_jeeves_knowledge_candidates")
    if not isinstance(candidates, list) or len(candidates) > MAX_CARDS:
        raise ValueError("Dragon comparative intake exceeds reviewed knowledge-card capacity")
    cards = []
    for note in candidates:
        if not isinstance(note, dict):
            raise ValueError("Dragon intake note provenance differs")
        anchors = note.get("evidence", [])
        if (note.get("knowledge_status") != "reviewed_observation_candidate"
            or note.get("review_status") != "reviewed"
            or not isinstance(anchors, list) or not anchors):
            raise ValueError("Dragon intake rejects unreviewed or ungrounded comparison claims")
        for ref in anchors:
            if not isinstance(ref, dict) or len(ref.get("evidence_sha256", "")) != 64:
                raise ValueError("Dragon comparison evidence is missing its exact stage receipt")
        cards.append({
            "note_id": note["note_id"],
            "author": note["author"],
            "claim_type": note["claim_type"],
            "dimension": note["dimension"],
            "text": note["text"],
            "evidence": anchors,
            "build_parameter_candidate": note.get("build_parameter_candidate"),
            "review_state": "locally_reviewed_pending_independent_dragon_custody",
            "game_ids": note["game_ids"],
            "source_study_sha256": report["result_sha256"],
            "rights_clearance": "not independently established",
            "eligible_for_model_training": False,
            "promotable_as_fact": False,
        })
    data = {
        "schema_version": SCHEMA,
        "source_study_id": report["study_id"],
        "source_study_sha256": report["result_sha256"],
        "observer_card_count": len(cards),
        "cards": cards,
        "proposed_training_curricula": [
            {
                "cohort_index": cohort["cohort_index"],
                "game_ids": cohort["game_ids"],
                "native_trace_receipts": cohort["native_trace_receipts"],
                "training_ready": False,
                "weight_promotion_allowed": False,
            }
            for cohort in report.get("synthesis", {}).get("training_cohorts", [])
        ],
        "synthesis_sha256": report.get("synthesis", {}).get("synthesis_sha256"),
        "audited_native_evidence_uptake": {
            "digest": report.get("learning_uptake_audit", {}).get("uptake_digest"),
            "measured_summary": report.get("learning_uptake_audit", {}).get("measured_summary"),
            "review_gate": report.get("learning_uptake_audit", {}).get("review_gate"),
            "model_training_promotable": False,
        },
        "available_to_user_and_ai": True,
        "dragon_source_type": "native_emulator_comparison_user_supplied_observations",
        "actual_automated_dragon_crawling_or_video_watching": False,
        "external_claim_verification": False,
        "authenticated_dragon_review_and_consent_completed": False,
        "weights_trained_or_promoted": False,
        "reuse_policy": "Use abstract design principles or independently reviewed measurements only; do not transfer copied game art, protected text, ROMs, recorded audio or expressive character/story content.",
    }
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("Dragon comparative knowledge intake exceeds four MiB")
    data["intake_sha256"] = hashlib.sha256(encoded).hexdigest()
    return data
