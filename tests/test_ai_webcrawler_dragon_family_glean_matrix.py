"""Mother Dragon glean matrix: independent claim grouping and safe shadow handoff."""
from __future__ import annotations
import sqlite3

import pytest

from skeleton.ai.webcrawler.dragon_family import (
    DragonFamily,IdleWindow,SourceSeed,SourceReceipt,
)
from skeleton.ai.webcrawler.dragon_family_almanakk import DragonAlmanakkLane,WikiEvidence
from skeleton.ai.webcrawler.dragon_family_glean_matrix import (
    DragonGleanMatrix,LensObservation,LENSES,
)

OWNER="dragon-owner"
OTHER="different-tenant"
NOW=1800000000.
REVIEW="a"*64
A="1"*64
B="2"*64
C="3"*64
REV="4"*64
PROP="b"*64
ANCHORS=("c"*64,"d"*64,"e"*64,"f"*64)
WIKI="9"*64


def source(sid: str,media="article"):
    return SourceSeed(sid,f"https://example.org/{sid}",media,("game_engine","physics"))


def proof(sid: str,digest: str=A,at:float=NOW+3):
    return SourceReceipt(sid,digest,REVIEW,at)


def setup():
    db=sqlite3.connect(":memory:")
    family=DragonFamily(db,owner_scope=OWNER,approval=lambda p:p.review_digest==REVIEW)
    family.enroll(OWNER,(source("alpha"),source("beta"),source("gamma","video")),
                  authorized=True,now=NOW)
    family.seal_inventory(OWNER,authorized=True,now=NOW+1)
    for idx,sid in enumerate(("alpha","beta","gamma")):
        family.consume(OWNER,proof(sid,at=NOW+2+idx),authorized=True)
    matrix=DragonGleanMatrix(family,
        finding_verify=lambda owner,obs:owner==OWNER and obs.anchor_digest in ANCHORS)
    return db,family,matrix


def finding(sid="alpha",*,media_digest=A,anchor=ANCHORS[0],
            group="publisher-alpha",stance="supports",
            lens="game_mechanics",at=NOW+100,proposition=PROP,score=.9):
    return LensObservation(sid,media_digest,proposition,anchor,lens,stance,
                           group,score,at,
                           "Reviewed actionable gameplay engineering inference")


def record_corroborated(matrix):
    assert matrix.record(OWNER,finding(),authorized=True)
    assert matrix.record(OWNER,finding("beta",group="publisher-beta",
                                    anchor=ANCHORS[1]),authorized=True)


def test_no_synthetic_hypotheses_and_lenses_advertised_without_claiming_proof():
    db,_,matrix=setup()
    view=matrix.projection(OWNER,authorized=True)
    assert view["schema"]=="skeleton.ai.dragon.glean.v1"
    assert view["insights"]==0 and view["lenses_used"]==0
    assert len(LENSES)>=20
    assert view["cells"]==[]
    assert view["read_only"] is True
    assert matrix.history(OWNER,authorized=True)==[]
    db.close()


def test_independent_sources_advance_wiki_candidate_but_not_model_weights():
    db,family,matrix=setup()
    assert matrix.record(OWNER,finding(),authorized=True)
    row=matrix.projection(OWNER,authorized=True)["cells"][0]
    assert row["status"]=="needs_independent_sources"
    assert row["support_groups"]==1
    assert row["priority"]=="seek_separate_source"
    assert not matrix.record(OWNER,finding(),authorized=True)
    # Same publisher identity even from two URLs is never independent.
    assert matrix.record(OWNER,finding("beta",anchor=ANCHORS[1],
                                    group="publisher-alpha"),authorized=True)
    row=matrix.projection(OWNER,authorized=True)["cells"][0]
    assert row["support_sources"]==2
    assert row["support_groups"]==1
    # A second distinct claim from beta with independent group demonstrates
    # the limits of relying on producer-supplied independence: an external
    # verifier must attest any group identity before admission.
    db.close()


def test_two_independent_publishers_corroborate_one_hypothesis():
    db,family,matrix=setup()
    record_corroborated(matrix)
    x=matrix.projection(OWNER,authorized=True)
    assert x["insights"]==1
    assert x["counts"]["wiki_candidate"]==1
    assert x["cells"][0]["support_sources"]==2
    assert x["cells"][0]["support_groups"]==2
    assert x["cells"][0]["status"]=="wiki_candidate"
    assert x["cells"][0]["modalities"]==["article"]
    assert family.snapshot(OWNER,authorized=True)["children"][0]["discoveries"]==0
    assert len(matrix.history(OWNER,authorized=True))==2
    db.close()


def test_shadow_queue_fails_closed_when_almanakk_is_not_installed():
    db,family,matrix=setup()
    record_corroborated(matrix)
    assert not db.execute("""SELECT 1 FROM sqlite_master
        WHERE name='dragon_almanakk_reviews'""").fetchone()
    verifier_calls=[]
    with pytest.raises(PermissionError,match="independent Wiki review"):
        matrix.queue_shadow_candidate(
            OWNER,"game_mechanics",PROP,authorized=True,
            at=NOW+200,
            wiki_claim_verify=lambda *args:verifier_calls.append(args) or True)
    assert verifier_calls==[]
    assert matrix.shadow_queue(OWNER,authorized=True)==[]
    assert not db.execute("""SELECT 1 FROM sqlite_master
        WHERE name='dragon_almanakk_reviews'""").fetchone()
    db.close()


def test_cross_media_contradiction_triggers_research_instead_of_promotion():
    db,_,matrix=setup()
    record_corroborated(matrix)
    assert matrix.record(OWNER,finding("gamma",anchor=ANCHORS[2],
          group="video-lab",stance="challenges"),authorized=True)
    view=matrix.projection(OWNER,authorized=True)
    row=view["cells"][0]
    assert row["status"]=="contested"
    assert row["priority"]=="investigate_disagreement"
    assert row["modalities"]==["article","video"]
    assert row["challenge_sources"]==1
    assert view["counts"]["contested"]==1
    with pytest.raises(PermissionError,match="uncontested"):
        matrix.queue_shadow_candidate(OWNER,"game_mechanics",PROP,
             authorized=True,at=NOW+150,wiki_claim_verify=lambda *a:True)
    db.close()


def test_logic_matrix_routes_disagreement_to_scrutiny_without_fetching():
    db,_,matrix=setup()
    record_corroborated(matrix)
    wiki=matrix.research_briefs(OWNER,authorized=True)
    assert wiki[0]["action"]=="request_independent_wiki"
    assert wiki[0]["required_specialists"]==[]
    assert wiki[0]["human_review_required"]
    assert not wiki[0]["permits_network"]
    assert "BUT" in wiki[0]["condition"]
    matrix.record(OWNER,finding("gamma",anchor=ANCHORS[2],
        group="video-lab",stance="challenges"),authorized=True)
    disputed=matrix.research_briefs(OWNER,authorized=True)
    assert disputed[0]["action"]=="revisit_conflicting_sources"
    assert disputed[0]["priority"]==0
    assert "monitor" in disputed[0]["required_specialists"]
    assert disputed[0]["source_count"]==3
    assert "BUT" in disputed[0]["condition"]
    assert not disputed[0]["permits_weight_promotion"]
    with pytest.raises(PermissionError):
        matrix.research_briefs(OWNER,authorized=False)
    db.close()


def test_sparse_glimpse_routes_to_separate_sources_not_model_promotion():
    db,_,matrix=setup()
    matrix.record(OWNER,finding(),authorized=True)
    item=matrix.research_briefs(OWNER,authorized=True)[0]
    assert item["action"]=="find_independent_corroboration"
    assert set(item["required_specialists"])=={"article","video"}
    assert item["source_ids"]==["alpha"]
    assert not item["permits_network"] and not item["permits_weight_promotion"]
    db.close()


def test_revoked_source_review_disappears_from_live_inferences():
    db,family,matrix=setup()
    record_corroborated(matrix)
    assert matrix.projection(OWNER,authorized=True)["counts"]["wiki_candidate"]==1
    # A new reviewed revision invalidates prior anchored observations.
    assert family.digest_idle(OWNER,"article",proof("beta",REV,NOW+720),
        authorized=True,window=IdleWindow(NOW+725,NOW+30,0,False,True),
        task_topics=("game_engine",))
    projection=matrix.projection(OWNER,authorized=True)
    assert projection["stale_observations"]==1
    assert projection["counts"]["wiki_candidate"]==0
    assert projection["counts"]["needs_independent_sources"]==1
    assert matrix.record(OWNER,finding("beta",media_digest=REV,
        at=NOW+750,group="publisher-beta",anchor=ANCHORS[1]),authorized=True)
    assert matrix.projection(OWNER,authorized=True)["counts"]["wiki_candidate"]==1
    db.close()


def test_denies_non_current_revision_without_verified_anchor_or_source():
    db,_,matrix=setup()
    with pytest.raises(PermissionError,match="reviewed source"):
        matrix.record(OWNER,finding(media_digest=REV),authorized=True)
    with pytest.raises(PermissionError,match="proposition"):
        matrix.record(OWNER,finding(anchor="7"*64),authorized=True)
    with pytest.raises(ValueError,match="lens"):
        matrix.record(OWNER,finding(lens="miracle"),authorized=True)
    with pytest.raises(ValueError,match="confidence"):
        matrix.record(OWNER,finding(score=float("nan")),authorized=True)
    with pytest.raises(ValueError,match="independent"):
        matrix.record(OWNER,finding(group="https://other.org"),authorized=True)
    with pytest.raises(PermissionError):
        matrix.record(OWNER,finding(),authorized=False)
    with pytest.raises(PermissionError,match="another owner"):
        matrix.record(OTHER,finding(),authorized=True)
    assert matrix.projection(OWNER,authorized=True)["insights"]==0
    db.close()


def test_wiki_and_source_level_approvals_required_before_shadow_queue():
    db,_,matrix=setup()
    record_corroborated(matrix)
    with pytest.raises(PermissionError,match="Almanakk|Wiki"):
        matrix.queue_shadow_candidate(OWNER,"game_mechanics",PROP,
            authorized=True,at=NOW+160,wiki_claim_verify=lambda *a:True)
    lane=DragonAlmanakkLane(db,source_approval=lambda r:r.review_digest==REVIEW,
                             owner_scope=OWNER,wiki_verify=lambda *args:True)
    wiki=WikiEvidence(WIKI,NOW+200,3,True,"Independent rights and citation review")
    lane.wiki_review(OWNER,"parent","alpha",A,wiki,authorized=True)
    lane.wiki_review(OWNER,"parent","beta",A,wiki,authorized=True)
    with pytest.raises(PermissionError,match="Wiki has not"):
        matrix.queue_shadow_candidate(OWNER,"game_mechanics",PROP,
            authorized=True,at=NOW+260,wiki_claim_verify=lambda *a:False)
    fingerprint=matrix.queue_shadow_candidate(OWNER,"game_mechanics",PROP,
            authorized=True,at=NOW+260,wiki_claim_verify=lambda *a:True)
    assert len(fingerprint)==64
    assert matrix.queue_shadow_candidate(OWNER,"game_mechanics",PROP,
        authorized=True,at=NOW+261,wiki_claim_verify=lambda *a:True)==fingerprint
    queue=matrix.shadow_queue(OWNER,authorized=True)
    assert len(queue)==1
    assert queue[0]["status"]=="awaiting_holdout"
    assert matrix.projection(OWNER,authorized=True)["counts"]["wiki_candidate"]==1
    # No actual weights or evaluated accuracy exist just because this queued.
    with pytest.raises(PermissionError):
        matrix.shadow_queue(OWNER,authorized=False)
    db.close()


def test_shadow_queue_stales_when_custody_revision_changes():
    db,family,matrix=setup()
    record_corroborated(matrix)
    lane=DragonAlmanakkLane(db,source_approval=lambda r:r.review_digest==REVIEW,
                wiki_verify=lambda *args:True,owner_scope=OWNER)
    decision=WikiEvidence(WIKI,NOW+200,3,True,"independently verified source rights")
    for sid in ("alpha","beta"):
        lane.wiki_review(OWNER,"parent",sid,A,decision,authorized=True)
    matrix.queue_shadow_candidate(OWNER,"game_mechanics",PROP,
        authorized=True,at=NOW+300,wiki_claim_verify=lambda *a:True)
    family.digest_idle(OWNER,"article",proof("alpha",REV,NOW+720),
        authorized=True,window=IdleWindow(NOW+725,NOW+30,0,False,True),
        task_topics=("game_engine",))
    assert matrix.shadow_queue(OWNER,authorized=True)[0]["status"]=="stale_requires_wiki_recheck"
    db.close()


def test_audit_history_detects_tampering_and_enforces_owner():
    db,_,matrix=setup()
    record_corroborated(matrix)
    events=matrix.history(OWNER,authorized=True)
    assert len(events)==2 and events[0]["at"].endswith("Z")
    assert events[0]["change"].startswith("(gleaned:")
    assert events[0]["sequence"]==2
    with pytest.raises(PermissionError):
        matrix.history(OWNER,authorized=False)
    with pytest.raises(PermissionError):
        matrix.projection(OTHER,authorized=True)
    db.execute("""UPDATE dragon_glean_events SET change='counterfeit insight'
        WHERE owner=? AND sequence=1""",(OWNER,))
    db.commit()
    with pytest.raises(ValueError,match="integrity"):
        matrix.history(OWNER,authorized=True)
    db.close()


def test_independent_source_validation_fails_closed_without_review_callback():
    db,family,_=setup()
    reader=DragonGleanMatrix(family)
    assert reader.projection(OWNER,authorized=True)["insights"]==0
    with pytest.raises(PermissionError,match="verifier not installed"):
        reader.record(OWNER,finding(),authorized=True)
    with pytest.raises(PermissionError):
        DragonGleanMatrix(DragonFamily(db,approval=lambda x:True),
                          finding_verify=lambda *args:True)
    db.close()
