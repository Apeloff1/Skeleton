"""Dragon mother glean matrix: exact quotations, skeptical cross-source handoff."""
from __future__ import annotations

from hashlib import sha256
import sqlite3

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_technical_source_atlas import CATALOG
from skeleton.ai.game_builder.dragon_technical_source_captures import DragonSourceCaptures
from skeleton.ai.game_builder.dragon_technical_source_analysis import DragonTechnicalGlean
from skeleton.ai.game_builder.dragon_technical_source_operations import DragonSourceOperations
from skeleton.ai.game_builder.dragon_source_policy_renewal import DragonSourcePolicyRenewal
from skeleton.ai.game_builder.dragon_source_refresh_planner import DragonSourceRefreshPlanner
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.core import FetchResponse, extract_document

OWNER="researcher-a"
T0=1791800000
BASE=(
    "Gameboy hardware memory registers use a frame timing scheduler. "
    "The system can verify a frame budget by testing memory timing. "
    "A game engine implementation may require hardware support."
)


@pytest.fixture
def lab(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"dragon-glean.sqlite") as library:
        atlas=DragonAlmanacs(library)
        worker=SequentialAlmanacWorker(atlas)
        captures=DragonSourceCaptures(atlas)
        glean=DragonTechnicalGlean(captures)
        yield library,atlas,worker,captures,glean


def install(lab,slug):
    library,atlas,worker,_,_=lab
    source=next(s for s in CATALOG if s["slug"]==slug)
    url=source["url"]
    sid="source-"+sha256(url.encode()).hexdigest()
    body={"source_id":sid,"url":url,"host":url.split("/")[2],
          "kind":"web_candidate","discoveries":[],
          "availability":"not_checked","rights":"not_assessed",
          "independence":"not_assessed","training_authorized":False,
          "provisional_discovery":True}
    library.db.execute("INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
        (OWNER,sid,canonical_json(body),canonical_digest(body)))
    assert worker.seed(OWNER,authorized=True)==1
    return sid,url


def permit(lab,sid,now=T0):
    _,_,worker,_,_=lab
    claim=worker.claim(OWNER,now=now,authorized=True,trusted_worker=True)
    assert claim and claim.stage=="policy" and claim.source_id==sid
    output="a"*64
    receipt={
        "url":claim.url,"input_digest":claim.input_digest,
        "output_digest":output,"robots_permitted":True,
        "terms_permitted":True,"reference_use_permitted":True,
        "ssrf_checked":True,"expires_at":now+500,
    }
    worker.finish(claim,now=now+1,output_digest=output,
                  evidence=receipt,authorized=True,trusted_worker=True)


def capture(lab,sid,url,*,text=BASE,at=T0+2,capture_id="primary"):
    _,_,_,captures,_=lab
    doc=extract_document(FetchResponse(
        url,200,{"content-type":"text/plain"},text.encode(),float(at)
    ),url)
    assert doc is not None
    result=captures.record(OWNER,sid,doc,observed_at=at,
       capture_id=capture_id,response_body_bytes=len(text.encode()),
       authorized=True,trusted_worker=True,reference_storage_permitted=True)
    return result


def extracted(lab,sid,url,at=T0):
    _,_,worker,captures,_=lab
    permit(lab,sid,now=at)
    created=capture(lab,sid,url,at=at+2,capture_id=f"captured-{at}")
    c=worker.claim(OWNER,now=at+3,authorized=True,trusted_worker=True)
    assert c.stage=="fetch" and c.source_id==sid
    captures.complete_fetch_stage(c,capture_digest=created["capture_digest"],
                                  now=at+4,authorized=True,trusted_worker=True)
    c=worker.claim(OWNER,now=at+5,authorized=True,trusted_worker=True)
    assert c.stage=="extract" and c.source_id==sid
    captures.complete_extract_stage(c,capture_digest=created["capture_digest"],
                                    now=at+6,authorized=True,trusted_worker=True)
    return created


def test_lenses_are_source_exact_and_never_approved_facts(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    library,_,worker,_,glean=lab
    preview=glean.preview(OWNER,sid,capture_digest=created["capture_digest"],
                          authorized=True)
    assert preview["readings"] and preview["lens_counts"]
    assert preview["fact_checked"] is False
    assert preview["independent_groups_verified"]==0
    assert not preview["training_authorized"]
    assert all(r["stance"]=="unreviewed" and
               r["confidence"]=="not_assessed" for r in preview["readings"])
    text=BASE
    for reading in preview["readings"]:
        assert text[reading["start"]:reading["end"]]==reading["exact_quote"]
        assert reading["independent_verification_required"]
        assert reading["lenses"]
    assert glean.preview(OWNER,sid,capture_digest=created["capture_digest"],
                          authorized=True)==preview
    assert library._rows(OWNER)==[]
    assert library.db.execute(
        "SELECT COUNT(*) FROM dragon_almanac_steps WHERE stage=3"
    ).fetchone()[0]==0


def test_canonical_analysis_atomic_receipt_and_readonly_wiki_handoff(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    library,_,worker,captures,glean=lab
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    assert claim.stage=="analyze"
    result=glean.complete_analyze(
        claim,capture_digest=created["capture_digest"],now=T0+8,
        authorized=True,trusted_worker=True)
    assert result["next_stage"]=="canonical_review"
    assert not result["knowledge_approved"]
    stored=library.db.execute(
        "SELECT stage,state,input_digest FROM dragon_almanac_jobs WHERE owner=? AND source=?",
        (OWNER,sid)).fetchone()
    assert stored==(4,"pending",result["analysis_digest"])
    hidden=glean.handoff(OWNER,sid,authorized=True)
    visible=glean.handoff(OWNER,sid,authorized=True,include_quotes=True)
    assert hidden["review_ready"]
    assert hidden["status"]=="awaiting_independent_wiki_hoag_review"
    assert hidden["reviewed_document_matches"]==0
    assert hidden["analysis_digest"]==result["analysis_digest"]
    assert all("exact_quote" not in reading for reading in hidden["readings"])
    assert any("exact_quote" in reading for reading in visible["readings"])
    assert library._rows(OWNER)==[]


def test_unchanged_reobservation_does_not_invalidate_valid_analysis(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    _,_,worker,_,glean=lab
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    glean.complete_analyze(claim,capture_digest=created["capture_digest"],
                           now=T0+8,authorized=True,trusted_worker=True)
    unchanged=capture(lab,sid,url,at=T0+9,capture_id="no-change")
    assert unchanged["change"]=="unchanged"
    assert glean.handoff(OWNER,sid,authorized=True)["review_ready"]


def test_new_text_revision_invalidates_prior_analysis_and_requires_reassessment(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    _,_,worker,_,glean=lab
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    glean.complete_analyze(claim,capture_digest=created["capture_digest"],
                           now=T0+8,authorized=True,trusted_worker=True)
    updated=capture(lab,sid,url,at=T0+9,capture_id="new-revision",text=
        "Gameboy hardware memory registers have changed timing requirements. "
        "The update should receive fresh, independent verification.")
    assert updated["change"]=="changed"
    with pytest.raises(ValueError,match="superseded"):
        glean.handoff(OWNER,sid,authorized=True)


def test_missing_extract_proof_stale_identity_or_replayed_analyze_rejected(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    _,_,worker,captures,glean=lab
    with pytest.raises(ValueError,match="capture digest"):
        glean.preview(OWNER,sid,capture_digest="wrong",authorized=True)
    with pytest.raises(PermissionError):
        glean.preview(OWNER,sid,capture_digest=created["capture_digest"],
                      authorized=False)
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    with pytest.raises(ValueError,match="stale"):
        glean.complete_analyze(claim,capture_digest="e"*64,now=T0+8,
                               authorized=True,trusted_worker=True)
    done=glean.complete_analyze(claim,capture_digest=created["capture_digest"],
                                now=T0+8,authorized=True,trusted_worker=True)
    with pytest.raises(ValueError,match="replayed|expired|mismatched"):
        glean.complete_analyze(claim,capture_digest=created["capture_digest"],
                               now=T0+9,authorized=True,trusted_worker=True)


def test_review_packet_digest_corruption_fails_closed(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    library,_,worker,_,glean=lab
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    glean.complete_analyze(claim,capture_digest=created["capture_digest"],
                           now=T0+8,authorized=True,trusted_worker=True)
    library.db.execute(
        "UPDATE dragon_almanac_steps SET body='{}' "
        "WHERE owner=? AND source=? AND stage=3",(OWNER,sid))
    with pytest.raises(ValueError,match="integrity|lineage|mismatch"):
        glean.handoff(OWNER,sid,authorized=True)


def test_peer_source_observations_are_not_independent_corroboration(lab):
    main_sid,url=install(lab,"pandocs")
    first=extracted(lab,main_sid,url)
    library,_,worker,_,glean=lab
    # Blocking one queue is the supported fail-closed release of the owner
    # sequential worker. No other research source can overtake its lease.
    current=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    assert current.stage=="analyze"
    assert worker.block(current,now=T0+8,authorized=True)
    peer_sid,peer_url=install(lab,"nesdev")
    permit(lab,peer_sid,now=T0+9)
    peer=capture(lab,peer_sid,peer_url,at=T0+11,capture_id="peer",
        text="NES hardware memory registers do not have universal frame timing. "
             "Hardware implementation requires measurements and testing.")
    preview=glean.preview(OWNER,main_sid,capture_digest=first["capture_digest"],
                          peers=(peer_sid,),authorized=True)
    assert preview["peer_signals"][0]["status"]=="observed"
    assert preview["peer_signals"][0]["shared_topics"]
    assert preview["peer_signals"][0]["independence"]=="not_proven"
    assert preview["independent_groups_verified"]==0
    assert preview["peer_signals"][0]["lexical_tension_hint"] is True
    assert preview["unanswered_questions"]
    with pytest.raises(ValueError,match="own independent"):
        glean.preview(OWNER,main_sid,capture_digest=first["capture_digest"],
                      peers=(main_sid,),authorized=True)


def test_bad_peer_owner_or_budget_refused(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    _,_,_,_,glean=lab
    with pytest.raises(ValueError,match="unique"):
        glean.preview(OWNER,sid,capture_digest=created["capture_digest"],
                      peers=("a","a"),authorized=True)
    with pytest.raises(ValueError,match="unique"):
        glean.preview(OWNER,sid,capture_digest=created["capture_digest"],
                      peers=tuple("source-"+("a"*63)+str(i) for i in range(9)),
                      authorized=True)
    with pytest.raises(ValueError,match="unregistered"):
        glean.preview(OWNER,sid,capture_digest=created["capture_digest"],
                      peers=("source-"+("f"*64),),authorized=True)


def test_unanalyzed_source_does_not_claim_approved_review(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    _,_,_,_,glean=lab
    handoff=glean.handoff(OWNER,sid,authorized=True)
    assert handoff["status"]=="awaiting_analysis_stage"
    assert handoff["review_ready"] is False
    with pytest.raises(ValueError,match="unregistered"):
        glean.handoff("other-owner",sid,authorized=True)



def reviewed_document(source_id,url,text,reviewer,group):
    from datetime import datetime, timezone
    from skeleton.ai.game_builder.reviewed_knowledge import ReviewedDocument,ReviewedNote
    offset=text.lower().index("hardware")
    return ReviewedDocument(
        OWNER,source_id,url,"Original technical evidence",text,
        datetime.fromtimestamp(T0+9,timezone.utc).isoformat().replace("+00:00","Z"),
        "rights-reference",("design_reference",),reviewer,True,
        (ReviewedNote("note-"+group,"hardware",
            "Hardware implementation requires source-verified constraints.",
            offset,offset+8,"supports",950000,group,("hardware",)),)
    )


def authoritative_wiki(lab,main_sid,main_url):
    from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
    from skeleton.ai.game_builder.dragon_wisdom_authority import DragonWisdomAuthority
    library,_,_,_,_=lab
    library.import_document(
        reviewed_document(main_sid,main_url,BASE,"reviewer-a","group-a"),
        expected_parent_digest=None,authorized=True)
    library.import_document(
        reviewed_document(
            "independent-source","https://independent.example.org/technical",
            "Independent hardware timing data supports verification of game registers.",
            "reviewer-b","group-b"),
        expected_parent_digest=None,authorized=True)
    brief=library.build_brief(OWNER,"hardware",authorized=True,
                             min_independent_groups=2,min_confidence_ppm=800000)
    authority=DragonWisdomAuthority(
        DragonWisdomPyramid(library),
        wiki_signing_key=b"k"*32,approval_signing_key=b"m"*32,
        issuer="verified-issuer")
    grant=authority.issue_grant(
        OWNER,"independent-wiki-expert","external-research",
        "wiki_reviewer",brief.to_payload()["brief_digest"],
        now=T0+10,expires_at=T0+300,
        identity_verified=True,authorized=True)
    wiki=authority.review(
        OWNER,brief,mechanic="hardware",disposition="accepted",
        review_evidence_digest="d"*64,grant=grant,
        now=T0+11,expires_at=T0+240,
        authorized=True,trusted_worker=True)
    return brief,authority,grant,wiki


def test_canonical_review_requires_existing_signed_independent_wiki_evidence(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    library,_,worker,_,glean=lab
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    result=glean.complete_analyze(
        claim,capture_digest=created["capture_digest"],
        now=T0+8,authorized=True,trusted_worker=True)
    brief,authority,grant,wiki=authoritative_wiki(lab,sid,url)
    final=worker.claim(OWNER,now=T0+12,authorized=True,trusted_worker=True)
    assert final.stage=="canonical_review"
    closed=glean.complete_canonical_review(
        final,capture_digest=created["capture_digest"],
        brief=brief,mechanic="hardware",
        wiki_review_digest=wiki["digest"],
        review_evidence_digest="d"*64,
        grant=grant,authority=authority,
        now=T0+13,authorized=True,trusted_worker=True)
    assert closed["next_stage"]=="reviewed"
    assert closed["knowledge_almanac_review_verified"]
    assert not closed["hoag_memory_promotion_completed"]
    assert not closed["model_training_authorized"]
    row=library.db.execute(
        "SELECT stage,state FROM dragon_almanac_jobs "
        "WHERE owner=? AND source=?",(OWNER,sid)).fetchone()
    assert row==(5,"reviewed")
    sealed=glean.handoff(OWNER,sid,authorized=True)
    assert sealed["status"]=="canonical_wiki_review_verified"
    assert sealed["training_authorized"] is False


def test_forged_wiki_evidence_cannot_close_canonical_review(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    _,_,worker,_,glean=lab
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    glean.complete_analyze(claim,capture_digest=created["capture_digest"],
                           now=T0+8,authorized=True,trusted_worker=True)
    brief,authority,grant,wiki=authoritative_wiki(lab,sid,url)
    final=worker.claim(OWNER,now=T0+12,authorized=True,trusted_worker=True)
    with pytest.raises(PermissionError,match="signed accepted Wiki"):
        glean.complete_canonical_review(
            final,capture_digest=created["capture_digest"],
            brief=brief,mechanic="hardware",
            wiki_review_digest=wiki["digest"],
            review_evidence_digest="e"*64,
            grant=grant,authority=authority,
            now=T0+13,authorized=True,trusted_worker=True)
    with pytest.raises(PermissionError,match="signed accepted Wiki"):
        glean.complete_canonical_review(
            final,capture_digest=created["capture_digest"],
            brief=brief,mechanic="hardware",
            wiki_review_digest=wiki["digest"],
            review_evidence_digest="d"*64,
            grant=grant,authority=authority,
            now=T0+250,authorized=True,trusted_worker=True)


def test_missing_independent_sources_do_not_close_review(lab):
    sid,url=install(lab,"pandocs")
    created=extracted(lab,sid,url)
    library,_,worker,_,glean=lab
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    glean.complete_analyze(claim,capture_digest=created["capture_digest"],
                           now=T0+8,authorized=True,trusted_worker=True)
    library.import_document(
        reviewed_document(sid,url,BASE,"reviewer-a","group-a"),
        expected_parent_digest=None,authorized=True)
    brief=library.build_brief(OWNER,"hardware",authorized=True,
                             min_independent_groups=1)
    from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
    from skeleton.ai.game_builder.dragon_wisdom_authority import DragonWisdomAuthority
    authority=DragonWisdomAuthority(
        DragonWisdomPyramid(library),
        wiki_signing_key=b"k"*32,approval_signing_key=b"m"*32,
        issuer="verified-issuer")
    grant=authority.issue_grant(
        OWNER,"independent-wiki-expert","external-research",
        "wiki_reviewer",brief.to_payload()["brief_digest"],
        now=T0+10,expires_at=T0+300,
        identity_verified=True,authorized=True)
    final=worker.claim(OWNER,now=T0+12,authorized=True,trusted_worker=True)
    with pytest.raises(ValueError,match="two-group"):
        glean.complete_canonical_review(
            final,capture_digest=created["capture_digest"],
            brief=brief,mechanic="hardware",wiki_review_digest="f"*64,
            review_evidence_digest="d"*64,
            grant=grant,authority=authority,
            now=T0+13,authorized=True,trusted_worker=True)



def test_reviewed_revisit_archives_full_chain_but_never_self_approves(lab):
    sid,url=install(lab,"pandocs")
    captured=extracted(lab,sid,url)
    library,_,worker,captures,glean=lab
    claim=worker.claim(OWNER,now=T0+7,authorized=True,trusted_worker=True)
    result=glean.complete_analyze(
        claim,capture_digest=captured["capture_digest"],
        now=T0+8,authorized=True,trusted_worker=True)
    brief,authority,grant,wiki=authoritative_wiki(lab,sid,url)
    final=worker.claim(OWNER,now=T0+12,authorized=True,trusted_worker=True)
    glean.complete_canonical_review(
        final,capture_digest=captured["capture_digest"],
        brief=brief,mechanic="hardware",
        wiki_review_digest=wiki["digest"],
        review_evidence_digest="d"*64,
        grant=grant,authority=authority,
        now=T0+13,authorized=True,trusted_worker=True)
    ops=DragonSourceOperations(captures)
    host=url.split("/")[2]
    # Arrange an existing completed durable observation; resource-lease
    # authorization is tested independently in worker integration cases.
    ops._append(OWNER,sid,host,"scheduled",now=T0+2,ready_at=T0+2)
    ops._append(OWNER,sid,host,"leased",now=T0+3,
                ready_at=T0+3,expires_at=T0+60,
                ticket_digest="a"*64)
    ops._append(OWNER,sid,host,"completed",now=T0+9,
                details={"capture_digest":captured["capture_digest"],
                         "review_status":"independent_review_pending"})
    planner=DragonSourceRefreshPlanner(ops)
    before=planner.assess(OWNER,sid,now=T0+5*86400,authorized=True)
    assert before["reason"]=="reviewed_source_cadence_not_due"
    due=T0+91*86400
    assessment=planner.assess(OWNER,sid,now=due,authorized=True)
    assert assessment["reason"]=="reviewed_source_revisit_due"
    assert not assessment["observed_remote_change"]
    renew=DragonSourcePolicyRenewal(ops)
    with pytest.raises(PermissionError,match="not yet"):
        renew.request(OWNER,sid,now=T0+5*86400,
            expected_operations_digest=ops.inspect(OWNER,sid,authorized=True)["head_digest"],
            reason="scheduled_revisit",authorized=True,trusted_supervisor=True)
    req=renew.request(OWNER,sid,now=due,
        expected_operations_digest=ops.inspect(OWNER,sid,authorized=True)["head_digest"],
        reason="scheduled_revisit",authorized=True,trusted_supervisor=True)
    assert req["status"]=="awaiting_new_independent_policy_review"
    assert library.db.execute(
        "SELECT COUNT(*) FROM dragon_almanac_archived_steps "
        "WHERE owner=? AND source=?",(OWNER,sid)).fetchone()[0]==5
    assert library.db.execute(
        "SELECT stage,state FROM dragon_almanac_jobs "
        "WHERE owner=? AND source=?",(OWNER,sid)).fetchone()==(0,"pending")
    assert len(library._rows(OWNER))==2
    assert ops.ready_candidates(OWNER,now=due,authorized=True)==()
    with pytest.raises(PermissionError,match="independent"):
        renew.rearm(OWNER,sid,now=due+1,
            expected_renewal_digest=req["renewal_digest"],
            authorized=True,trusted_supervisor=True)
