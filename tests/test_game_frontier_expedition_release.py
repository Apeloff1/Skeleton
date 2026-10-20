"""Two independent game checks, source integrity and explicit content review."""
from copy import deepcopy
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_qa import run_expedition_qa
from skeleton.jeeves.game_frontier_expedition_godot import emit_expedition_godot_project
from skeleton.jeeves.game_frontier_expedition_release import (
    ExternalContentReview,evaluate_expedition_release,
)
from tests.test_game_frontier_expedition_native_runner import world,traveler


def inputs():
    w,p=world(),traveler()
    files=emit_expedition_godot_project(w,p)
    qa=run_expedition_qa(
        w.project_id,w.source_digest,seeds=(7,),islands=5)
    return w,p,files,qa


def test_release_executes_two_independent_gameplay_reviewers_not_just_metrics():
    w,p,files,qa=inputs()
    result=evaluate_expedition_release(w,p,files,qa)
    assert result["axis_count"]==8
    assert result["axes"]["gameplay_viability"]
    assert result["axes"]["independent_replay"]
    assert result["primary_gameplay_receipt"]==result["independent_gameplay_receipt"]
    assert "copyright_review" in result["blocked_axes"]
    assert "originality_review" in result["blocked_axes"]
    assert "native_validation" in result["blocked_axes"]
    assert result["status"]=="blocked"
    assert not result["production_release_approved"]
    assert not result["external_legal_clearance_verified"]


def test_content_review_roles_require_distinct_evidence_and_exact_source():
    w,p,files,qa=inputs()
    left=ExternalContentReview(
        "copyright","rights-a",w.source_digest,"approved",
        "host:rights:receipt","a"*64)
    right=ExternalContentReview(
        "originality","creative-b",w.source_digest,"approved",
        "host:creative:receipt","b"*64)
    result=evaluate_expedition_release(
        w,p,files,qa,copyright_review=left,originality_review=right)
    assert result["axes"]["copyright_review"]
    assert result["axes"]["originality_review"]
    assert not result["axes"]["native_validation"]
    assert not result["production_release_approved"]
    with pytest.raises(ExpeditionError,match="independent"):
        evaluate_expedition_release(
            w,p,files,qa,copyright_review=left,
            originality_review=ExternalContentReview(
                "originality","rights-a",w.source_digest,"approved",
                "host:creative:receipt","b"*64))


def test_qa_row_receipt_cannot_be_rewritten_even_if_root_checksum_recomputed():
    w,p,files,qa=inputs()
    changed=deepcopy(qa)
    changed["cases"][0]["routes_executed"]=77
    from skeleton.jeeves.game_frontier_expedition import _digest
    changed["receipt_digest"]=_digest({
        k:v for k,v in changed.items() if k!="receipt_digest"})
    with pytest.raises(ExpeditionError,match="case evidence"):
        evaluate_expedition_release(w,p,files,changed)


def test_foreign_game_source_and_engine_file_tampering_block_release():
    w,p,files,qa=inputs()
    changed=dict(files)
    changed["game/frontier/expedition.gd"]+="\n# unverified patch"
    with pytest.raises(ExpeditionError,match="differs"):
        evaluate_expedition_release(w,p,changed,qa)
    changed=deepcopy(qa)
    changed["project"]="foreign"
    from skeleton.jeeves.game_frontier_expedition import _digest
    changed["receipt_digest"]=_digest({
        k:v for k,v in changed.items() if k!="receipt_digest"})
    with pytest.raises(ExpeditionError,match="source or scenario"):
        evaluate_expedition_release(w,p,files,changed)


def test_review_signature_is_not_self_authorizing():
    w,p,files,qa=inputs()
    native={
        "schema":"skeleton.game.expedition_native_complete_replay.v1",
        "world_digest":w.digest,"source_digest":w.source_digest,
        "candidate_files_receipt":"invalid",
        "native_process_executed":True,
        "native_gameplay_consistent":True,"completed":True,
        "receipt_digest":"0"*64,
    }
    with pytest.raises(ExpeditionError,match="stale or contradictory"):
        evaluate_expedition_release(w,p,files,qa,native_report=native)


@pytest.mark.parametrize("role",("creative","",1))
def test_wrong_content_review_role_is_fail_closed(role):
    with pytest.raises(ExpeditionError,match="role"):
        ExternalContentReview(role,"reviewer","f"*64,"approved",
                              "host:scope","a"*64)
