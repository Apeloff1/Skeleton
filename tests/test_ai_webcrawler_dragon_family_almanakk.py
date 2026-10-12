"""Dragon -> Almanakk -> Wiki -> sandbox -> authorized handoff regression suite."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.ai.webcrawler.dragon_family import (
    DragonFamily, IdleWindow, SourceSeed, SourceReceipt,
)
from skeleton.ai.webcrawler.dragon_family_almanakk import (
    DragonAlmanakkLane, WikiEvidence, SandboxEvidence,
)

AT=1800000000.0
OWNER="studio-A"
A="a"*64
B="b"*64
C="c"*64
D="d"*64
E="e"*64
F="f"*64


def proof(source, digest, at):
    return SourceReceipt(source,digest,A,at)


def setup():
    db=sqlite3.connect(":memory:")
    enabled={"approved":True}
    def verify(p):
        return enabled["approved"] and p.review_digest==A

    family=DragonFamily(db,approval=verify)
    assert family.enroll(OWNER,(
        SourceSeed("article-1","https://example.org/dragon/design","article",("game_design","physics")),
        SourceSeed("video-1","https://example.org/dragon/video","video",("game_design",)),
    ),authorized=True,now=AT)==2
    assert family.seal_inventory(OWNER,authorized=True,now=AT+1)
    assert family.consume(OWNER,proof("article-1",B,AT+2),authorized=True)
    assert family.consume(OWNER,proof("video-1",C,AT+3),authorized=True)
    idle=IdleWindow(AT+750, AT+100,0,False,True,True)
    assert family.digest_idle(OWNER,"article",proof("article-1",D,AT+749),
                              authorized=True,window=idle,
                              task_topics=("game_design",))
    lane=DragonAlmanakkLane(
        db,source_approval=verify,
        wiki_verify=lambda owner,digest,item: owner==OWNER and digest==D and item.fingerprint==E,
        sandbox_verify=lambda owner,digest,item: owner==OWNER and digest==D and item.fingerprint==F,
        handoff_verify=lambda owner,digest,signed: owner==OWNER and digest==D and signed==A,
    )
    return db,family,lane,enabled


def wiki(*, at=AT+760, groups=3, rights=True, explanation="independently corroborated"):
    return WikiEvidence(E,at,groups,rights,explanation)


def evaluation(*, at=AT+800, before=.5, after=.68, cases=50, regressions=0):
    return SandboxEvidence(F,at,before,after,cases,regressions,"holdout improved puzzle generation")


def test_read_only_projection_uses_parent_and_latest_child_source():
    db,family,lane,_=setup()
    report=lane.projection(OWNER,authorized=True)
    assert report["schema"]=="skeleton.ai.dragon.almanakk.v1"
    assert report["counts"]["collected"]==2
    assert [e["source_id"] for e in report["items"]]==["article-1","video-1"]
    assert [e["dragon"] for e in report["items"]]==["article","parent"]
    assert report["history"]==[]
    assert "Wiki" in report["architecture"] and "HOAG" in report["architecture"]
    assert not lane.projection("other",authorized=True)["items"]
    assert not lane.projection("other",authorized=True)["history"]
    with pytest.raises(PermissionError):
        lane.projection(OWNER,authorized=False)
    db.close()


def test_independent_wiki_then_holdout_then_separate_handoff_not_real_weights():
    db,_,lane,_=setup()
    with pytest.raises(PermissionError,match="stages"):
        lane.sandbox_review(OWNER,"article","article-1",D,evaluation(),authorized=True)
    assert lane.wiki_review(OWNER,"article","article-1",D,wiki(),authorized=True)
    assert not lane.wiki_review(OWNER,"article","article-1",D,wiki(),authorized=True)
    assert lane.sandbox_review(OWNER,"article","article-1",D,evaluation(),authorized=True)
    assert lane.authorize_weight_handoff(OWNER,"article","article-1",D,
                                         signed_receipt=A,approved_at=AT+900,authorized=True)
    report=lane.projection(OWNER,authorized=True)
    assert report["counts"]=={
        "collected":1,"wiki_verified":0,"shadow_validated":0,"weight_handoff":1,
    }
    item=report["items"][0]
    assert item["source_id"]=="article-1" and item["measured_gain"]==pytest.approx(.18)
    events=report["history"]
    assert [e["stage"] for e in events]==["weight_handoff","shadow_validated","wiki_verified"]
    assert "(improved: holdout improved puzzle generation)" in events[1]["change"]
    assert all(e["at"].endswith("Z") and len(e["event_hash"])==64 for e in events)
    # Not a real parameter mutation: no weights, tokens, adapter, or provider
    # are exposed or stored in this handoff ledger.
    assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='model_weights'").fetchone()
    db.close()


@pytest.mark.parametrize("change",[
    {"independence_groups":1}, {"meets_source_rights":False},
    {"fingerprint":"invalid"}, {"explanation":"x"},
])
def test_wiki_admission_fails_closed_before_any_status(change):
    from dataclasses import replace
    db,_,lane,_=setup()
    with pytest.raises((PermissionError,ValueError)):
        lane.wiki_review(OWNER,"article","article-1",D,
                         replace(wiki(),**change),authorized=True)
    assert lane.projection(OWNER,authorized=True)["counts"]["wiki_verified"]==0
    db.close()


@pytest.mark.parametrize("change",[
    {"candidate_score":.501},
    {"candidate_score":.49}, {"independent_cases":29},
    {"critical_regressions":1},{"baseline_score":float("nan")},
    {"candidate_score":1.1},
    {"fingerprint":"0"*64},
])
def test_shadow_gate_blocks_false_quality_and_regression(change):
    from dataclasses import replace
    db,_,lane,_=setup()
    lane.wiki_review(OWNER,"article","article-1",D,wiki(),authorized=True)
    with pytest.raises((PermissionError,ValueError)):
        lane.sandbox_review(OWNER,"article","article-1",D,
                            replace(evaluation(),**change),authorized=True)
    assert lane.projection(OWNER,authorized=True)["counts"]["wiki_verified"]==1
    db.close()


def test_signed_weight_handoff_is_idempotent_and_cannot_be_substituted():
    db,_,lane,_=setup()
    lane.wiki_review(OWNER,"article","article-1",D,wiki(),authorized=True)
    lane.sandbox_review(OWNER,"article","article-1",D,evaluation(),authorized=True)
    receipt=lane.authorize_weight_handoff(
        OWNER,"article","article-1",D,
        signed_receipt=A,approved_at=AT+900,authorized=True)
    assert receipt==lane.authorize_weight_handoff(
        OWNER,"article","article-1",D,
        signed_receipt=A,approved_at=AT+900,authorized=True)
    permissive=DragonAlmanakkLane(
        db,source_approval=lambda r:True,
        handoff_verify=lambda *_:True,
    )
    with pytest.raises(ValueError,match="persisted signed"):
        permissive.authorize_weight_handoff(
            OWNER,"article","article-1",D,
            signed_receipt=E,approved_at=AT+905,authorized=True)
    assert len(lane.history(OWNER,authorized=True))==3
    db.close()


def test_retraction_and_new_revision_invalidate_stale_predecessor():
    db,family,lane,enabled=setup()
    lane.wiki_review(OWNER,"article","article-1",D,wiki(),authorized=True)
    enabled["approved"]=False
    with pytest.raises(PermissionError,match="revoked"):
        lane.sandbox_review(OWNER,"article","article-1",D,evaluation(),authorized=True)
    enabled["approved"]=True
    fresh_window=IdleWindow(AT+1000,AT+100,0,False,True,True)
    assert family.digest_idle(OWNER,"monitor",proof("article-1",F,AT+999),
                              authorized=True,window=fresh_window,
                              task_topics=("game_design",))
    with pytest.raises(ValueError,match="superseded"):
        lane.sandbox_review(OWNER,"article","article-1",D,evaluation(at=AT+1001),
                            authorized=True)
    report=lane.projection(OWNER,authorized=True)
    assert report["counts"]["collected"]==2
    assert report["counts"]["wiki_verified"]==0
    assert report["items"][0]["dragon"]=="monitor"
    db.close()


def test_replay_failure_wrong_owner_invalid_signature_and_history_tamper():
    db,_,lane,_=setup()
    with pytest.raises(PermissionError):
        lane.wiki_review(OWNER,"article","article-1",D,wiki(),authorized=False)
    with pytest.raises(PermissionError,match="reviewer"):
        lane.wiki_review("other","article","article-1",D,wiki(),authorized=True)
    lane.wiki_review(OWNER,"article","article-1",D,wiki(),authorized=True)
    with pytest.raises(PermissionError,match="signed authorization"):
        lane.authorize_weight_handoff(OWNER,"article","article-1",D,
                                      signed_receipt=B,approved_at=AT+850,authorized=True)
    db.execute("""UPDATE dragon_almanakk_review_events SET details='forged'
        WHERE owner=? AND sequence=1""",(OWNER,))
    db.commit()
    with pytest.raises(ValueError,match="integrity"):
        lane.history(OWNER,authorized=True)
    with pytest.raises(ValueError,match="integrity"):
        lane.projection(OWNER,authorized=True)
    db.close()


def test_no_almanakk_write_permission_and_no_fabricated_source_history():
    db,_,_,_=setup()
    lane=DragonAlmanakkLane(db)
    with pytest.raises(PermissionError,match="source review"):
        lane.wiki_review(OWNER,"article","article-1",D,wiki(),authorized=True)
    with pytest.raises(ValueError,match="missing or superseded"):
        guarded=DragonAlmanakkLane(db,source_approval=lambda p:True,
                                   wiki_verify=lambda *args:True)
        guarded.wiki_review(OWNER,"article","fake-9",D,wiki(),authorized=True)
    assert guarded.projection(OWNER,authorized=True)["counts"]["collected"]==2
    db.close()
