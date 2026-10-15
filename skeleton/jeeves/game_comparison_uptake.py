"""Verified comparative training uptake and evidence integrity matrix.

Measures *coverage* and real local Q-policy update counts, never invents
intelligence, wisdom, game mastery, transformer parameters or held-out gains.
Verifies native step hash chains and observation checkpoint references without
running new ROMs. Designed for Dragon/Jeeves evidence review.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .game_comparison_schema import digest

SCHEMA="skeleton.game.comparison_uptake_audit.v1"


class ComparisonUptakeError(ValueError):
    """A native evidence chain, local policy or checkpoint cannot be trusted."""


def build_comparison_uptake_audit(report: Mapping[str,Any]) -> dict[str,Any]:
    if (not isinstance(report,dict)
        or report.get("schema_version")!="skeleton.game.comparative_study_result.v1"):
        raise ComparisonUptakeError("Comparative uptake requires actual canonical study evidence")
    games=report.get("games")
    if not isinstance(games,dict) or len(games)>30:
        raise ComparisonUptakeError("Study game evidence is outside the thirty-game contract")
    entries=[]
    total_steps=0
    q_updates=0
    for game_id, game in games.items():
        if not isinstance(game,dict):
            raise ComparisonUptakeError("Game evidence rows must be objects")
        if game.get("status")!="actual_native_observations_captured":
            entries.append({
                "game_id":game_id,
                "state":"native_execution_failed_or_not_observed",
                "native_step_receipts_verified":0,
                "locally_modified_q_parameters":0,
                "heldout_gain":None,
                "promotable":False,
            })
            continue
        receipts=game.get("native_session_event_receipts")
        if not isinstance(receipts,list) or not 1<=len(receipts)<=64:
            raise ComparisonUptakeError("Native game is missing its bounded step-receipt chain")
        source_identity=game.get("source_bundle_sha256", game.get("source_sha256"))
        previous=digest(["comparative-native-session",game_id,source_identity])
        for number,entry in enumerate(receipts,1):
            if not isinstance(entry,dict) or entry.get("step")!=number:
                raise ComparisonUptakeError("Native chain contains an unordered or malformed step")
            content={k:v for k,v in entry.items() if k!="receipt_chain_sha256"}
            previous=digest([previous,content])
            if entry.get("receipt_chain_sha256")!=previous:
                raise ComparisonUptakeError("Native action/frame/audio/transition receipt hash chain changed")
            for field in ("native_frame_sha256","native_pcm_sha256","transition_sha256"):
                value=entry.get(field)
                if type(value) is not str or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
                    raise ComparisonUptakeError("Native observation digest is not a bounded lowercase SHA-256")
        if game.get("native_session_log_digest")!=previous:
            raise ComparisonUptakeError("Game event-root receipt diverged from every actual native action")
        if game.get("native_session_log_steps")!=len(receipts):
            raise ComparisonUptakeError("Game native event count differs from complete chain")
        stages=game.get("phases")
        if not isinstance(stages,dict) or set(stages)!={"earlier","middle","after"}:
            raise ComparisonUptakeError("Game cannot claim observations without all three stage receipts")
        checkpoints={}
        for phase,stage in stages.items():
            number=stage.get("step")
            if type(number) is not int or not 1<=number<=len(receipts):
                raise ComparisonUptakeError("Stage points to an absent native input step")
            evidence=receipts[number-1]
            if (stage.get("controller_input_receipt_sha256")!=evidence["receipt_chain_sha256"]
                or stage.get("frame_sha256")!=evidence["native_frame_sha256"]
                or stage.get("audio_sha256")!=evidence["native_pcm_sha256"]
                or stage.get("transition_sha256")!=evidence["transition_sha256"]
                or stage.get("action_at_checkpoint")!=evidence["action"]):
                raise ComparisonUptakeError("A game stage no longer binds to its observed native session step")
            checkpoints[phase]=stage["evidence_sha256"]
        local=game.get("study_local_tabular_training")
        updates=0
        policy_sha=None
        if local is not None:
            if not isinstance(local,dict) or local.get("game_id")!=game_id:
                raise ComparisonUptakeError("Study-local Q policy identity differs from its native game")
            updates=local.get("updates_applied")
            if type(updates) is not int or not 0<=updates<=len(receipts):
                raise ComparisonUptakeError("Native study-local Q update count is outside the actual trace")
            policy_sha=local.get("trained_policy_sha256")
            if type(policy_sha) is not str or len(policy_sha)!=64:
                raise ComparisonUptakeError("Study-local policy lacks its actual post-update identity")
            if local.get("real_verified_trace_sha256")!=game.get("canonical_offline_trace_sha256"):
                raise ComparisonUptakeError("Trained policy does not bind to the observed native trace")
        total_steps+=len(receipts)
        q_updates+=updates
        entries.append({
            "game_id":game_id,
            "state":"native_receipts_locally_reverified",
            "native_step_receipts_verified":len(receipts),
            "checkpoint_evidence_sha256":checkpoints,
            "native_source_sha256":source_identity,
            "observed_audio_video":True,
            "controller_layout_sha256":game.get("controller_layout",{}).get("layout_sha256"),
            "actual_local_tabular_q_updates":updates,
            "trained_local_policy_sha256":policy_sha,
            "heldout_policy_evaluation_performed":False,
            "heldout_gain":None,
            "source_rights_independently_verified":False,
            "parameters_or_weights_promoted":False,
            "promotable":False,
        })
    dimension_notes=defaultdict(list)
    for note in report.get("observer_notes",[]):
        if not isinstance(note,dict):
            raise ComparisonUptakeError("Reviewer notes must retain typed provenance")
        if note.get("knowledge_status")=="reviewed_observation_candidate":
            dimension_notes[note["dimension"]].append({
                "note_id":note["note_id"],
                "author":note["author"],
                "kind":note["claim_type"],
                "evidence_refs":note["evidence"],
                "independent_verification":False,
            })
    summary={
        "native_receipt_chains_reverified":sum(item["state"]=="native_receipts_locally_reverified" for item in entries),
        "native_steps_reverified":total_steps,
        "locally_applied_q_table_updates":q_updates,
        "reviewed_source_linked_note_count":sum(len(x) for x in dimension_notes.values()),
        "independent_rights_clearances":0,
        "heldout_comparative_gameplay_improvements_verified":0,
        "production_llm_parameter_updates":0,
        "production_shadow_promotions":0,
    }
    result={
        "schema_version":SCHEMA,
        "source_study_id":report["study_id"],
        "source_study_manifest_sha256":report["study_manifest_sha256"],
        "game_receipts":entries,
        "dimension_evidence":[
            {
                "dimension":k,"note_count":len(v),"claims":v,
                "review_scope":"local_only_requires_external_adversarial_review",
            }
            for k,v in sorted(dimension_notes.items())
        ],
        "measured_summary":summary,
        "separation":"Observations are not wisdom; reviewed notes are not learned parameters; Q updates are not LLM weight updates; no source rights or held-out gain can be inferred from replay hashes.",
        "review_gate":{
            "requires_independent_rights_and_consent":True,
            "requires_heldout_gameplay_and_determinism":True,
            "requires_adversarial_review":True,
            "requires_human_approval_before_promotion":True,
            "ready_for_production_promotion":False,
        },
    }
    result["uptake_digest"]=digest(result)
    return result
