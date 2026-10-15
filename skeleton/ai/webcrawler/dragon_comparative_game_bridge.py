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


def export_dragon_counterfactual_review(report: Mapping[str, object]) -> dict[str, object]:
    """Propose measured controlled-input observations to Dragon's review queue.

    This is evidence-only, never an authoritative skill or trained weight.
    It intentionally excludes raw ROM bytes, native PCM, screenshots and
    gameplay recordings. A claimed result requires a complete, digest-intact
    native experiment with at least two fresh runs of each branch.
    """
    from skeleton.jeeves.game_comparison_counterfactual import verify_counterfactual_input_result

    verified=verify_counterfactual_input_result(report)
    games=report.get("games")
    if not isinstance(games,list) or not 2<=len(games)<=10:
        raise ValueError("Dragon counterfactual review requires two to ten actual game trials")
    cards=[]
    for game in games:
        if not isinstance(game,dict):
            raise ValueError("Actual source game row missing")
        baseline=game.get("baseline_fresh_native_runs")
        variant=game.get("perturbed_fresh_native_runs")
        if (not isinstance(baseline,list) or not isinstance(variant,list)
            or len(baseline)!=len(variant) or not 2<=len(baseline)<=3):
            raise ValueError("Controlled trials have too few actual fresh-worker repetitions")
        for arm in baseline+variant:
            if (not isinstance(arm,dict) or arm.get("real_native_run") is not True
                or not isinstance(arm.get("receipts"),list)
                or len(arm["receipts"])<1
                or any(r.get("source")!="actual_isolated_libretro" for r in arm["receipts"])):
                raise ValueError("Dragon must not promote fabricated trial observations")
        analysis=game.get("measured_analysis")
        if not isinstance(analysis,dict):
            raise ValueError("Measured native A/B analysis is absent")
        cards.append({
            "game_id":game["game_id"],
            "target_id":game["target_id"],
            "core_id":game["core_id"],
            "source_media_sha256":game["source_sha256"],
            "changed_input_step":game["perturbation_step"],
            "original_action":game["baseline_action"],
            "modified_action":game["alternative_action"],
            "repeat_count_per_arm":len(baseline),
            "baseline_final_receipt_sha256":[x["last_evidence_sha256"] for x in baseline],
            "variant_final_receipt_sha256":[x["last_evidence_sha256"] for x in variant],
            "actual_objective_deltas":analysis["measured_objective_changes"],
            "within_arm_repeat_consistency":analysis["repeat_consistent_in_both_arms"],
            "signal_divergences":analysis["signal_comparison"],
            "knowledge_candidate_kind":"controlled_input_response_hypothesis",
            "independently_verified_causal_game_mechanics":False,
            "requires_separate_human_review_and_rights_clearance":True,
            "eligible_for_production_model_training":False,
        })
    result={
        "schema_version":"skeleton.dragon.comparative_counterfactual_review.v1",
        "source_native_study_sha256":report["result_sha256"],
        "source_study_id":report["source_study_id"],
        "native_evidence_verification_sha256":verified["verification_sha256"],
        "native_input_steps_locally_verified":verified["native_action_observations_hash_checked"],
        "game_count":len(cards),
        "candidates":cards,
        "review_status":"pending_independent_human_and_dragon_adversarial_review",
        "source_rights_independently_verified":False,
        "game_mechanics_or_gameplay_quality_proven":False,
        "weights_or_longterm_memory_changed":False,
        "no_copyrighted_audio_video_or_rom_data_copied":True,
    }
    serialized=json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    if len(serialized)>MAX_PAYLOAD_BYTES:
        raise ValueError("Dragon controlled game experiment review envelope exceeds bounded payload")
    result["intake_sha256"]=hashlib.sha256(serialized).hexdigest()
    return result
