"""Video and updates hatchlings: offline evidence staging, never self-review."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime,timezone
from hashlib import sha256
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from skeleton.ai.game_builder.contracts import canonical_digest,canonical_json
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_technical_source_atlas import (
    CATALOG,DragonTechnicalSources,
)
from skeleton.ai.game_builder.dragon_technical_source_captures import DragonSourceCaptures
from skeleton.ai.game_builder.dragon_video_transcript_ledger import (
    DragonVideoTranscriptLedger,TimedTranscriptCue,TranscriptRightsReceipt,
)
from skeleton.ai.game_builder.dragon_source_delta_ledger import DragonSourceDeltaLedger
from skeleton.ai.game_builder.dragon_mother_evidence_synergy import DragonMotherEvidenceSynergy
from skeleton.ai.game_builder.dragon_article_hatchling import DragonArticleHatchling
from skeleton.ai.game_builder.dragon_three_hatchling_coordinator import DragonThreeHatchlingCoordinator
from skeleton.ai.game_builder.dragon_research_source_picker import DragonResearchSourcePicker
from skeleton.ai.game_builder.dragon_research_workboard import DragonResearchWorkboard
from skeleton.ai.game_builder.dragon_task_research_planner import DragonTaskResearchPlanner
from skeleton.ai.game_builder.dragon_family_research_history import DragonFamilyResearchHistory
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedKnowledgeStore,ReviewedDocument,ReviewedNote,
)
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore
from skeleton.ai.webcrawler.dragon_nest_source_feed import DragonNestSourceFeed
from skeleton.ai.webcrawler.dragon_nest_worker_admission import DragonNestWorkerAdmission
from skeleton.ai.webcrawler.dragon_nest_research_scheduler import ResearchLead
from skeleton.ai.webcrawler.dragon_resource_session import DragonResourceSession,HardwareSample
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourceScheduler,GlobalResourcePolicy,PlanePolicy,ResourceVector,
)
from skeleton.ai.webcrawler.core import FetchResponse,extract_document

OWNER="specialist-lab"
T0="2026-10-12T12:00:00Z"
T1="2026-10-12T12:05:00Z"
T2="2026-10-12T12:15:00Z"


def epoch(value=T2):
    return int(datetime.fromisoformat(value.replace("Z","+00:00")).timestamp())


def sample():
    return HardwareSample(512*1024**2,8,.1,.75,True,False,1000.)


def resource_scheduler():
    return GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=2000,memory_mb=128,io_tokens=100),
        (PlanePolicy("interactive",2,ResourceVector(),1.0),
         PlanePolicy("background",1,ResourceVector(),1.0)),
    ))


@pytest.fixture
def context(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"specialists.sqlite") as lib:
        a=DragonAlmanacs(lib)
        atlas=DragonTechnicalSources(a)
        atlas.import_catalog(OWNER,authorized=True,recorded_at=epoch(T0))
        nestdb=sqlite3.connect(":memory:")
        nest=DragonNestStore(nestdb,signing_key=b"specialist-bridge-test-nest-key-32bytes")
        nest.initialize(
            OWNER,("reviewed-parent",),
            focus_tags=("gameboy",),adjacent_tags=("debugging",),
            at=T0,authorized=True)
        nest.record_parent(OWNER,"reviewed-parent",
            content_sha256="a"*64,at=T0,
            authorized=True,reviewed=True,lawful=True)
        feed=DragonNestSourceFeed(a,atlas,nest)
        resources=resource_scheduler()
        admission=DragonNestWorkerAdmission(
            feed,DragonResourceSession(global_resources=resources,tenant=OWNER))
        try:
            yield lib,a,feed,admission,resources
        finally:
            for ticket,_,_ in list(admission.active.values()):
                admission.stopped(ticket,authorized=True,trusted_worker=True,
                                  worker_stopped=True)
            nestdb.close()


def add_video(context):
    lib,a,_,_,_=context
    url=canonical_source_url("https://www.youtube.com/watch?v=abc123")
    sid="source-"+sha256(url.encode()).hexdigest()
    body={"source_id":sid,"url":url,"host":"www.youtube.com",
          "kind":"video_candidate","discoveries":[],
          "availability":"not_checked","rights":"not_assessed",
          "independence":"not_assessed","training_authorized":False}
    lib.db.execute("INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
                   (OWNER,sid,canonical_json(body),canonical_digest(body)))
    SequentialAlmanacWorker(a).seed(OWNER,authorized=True)
    return ResearchLead(sid,url,("gameboy",),"video",T1)


def video_worker(context,lead):
    _,_,_,admission,_=context
    result=admission.begin(
        OWNER,sample=sample(),at=T2,idle_since=T0,
        now_seconds=1000,authorized=True,trusted_worker=True,
        consented=True,article_consent=False,video_consent=True,
        updates_consent=False,video_hints=(lead,))
    assert result.admitted and result.ticket is not None
    assert result.ticket.lane=="video"
    return result.ticket


def transcript_ledger(context):
    _,_,feed,_,_=context
    key=Ed25519PrivateKey.from_private_bytes(b"\x42"*32)
    ledger=DragonVideoTranscriptLedger(
        feed,review_public_key=key.public_key().public_bytes_raw(),
        issuer="independent-video-rights",key_id="transcript-review-1")
    return ledger,key


def transcript_cues():
    return (
        TimedTranscriptCue(0,1250,"Gameboy hardware memory registers."),
        TimedTranscriptCue(1250,2800,"Frame timing requires independent tests."),
    )


def transcript_receipt(key,lead,cues,*,expires_at=None):
    _,sha=DragonVideoTranscriptLedger._track(cues)
    now=epoch(T2)
    receipt=TranscriptRightsReceipt(
        OWNER,lead.source_id,lead.url,sha,"c"*64,
        "verified-external-reviewer","independent-video-rights",
        "transcript-review-1",now-5,
        expires_at or now+60,signature_hex="")
    return replace(receipt,signature_hex=key.sign(
        canonical_json(receipt.body()).encode()).hex())


def stage_video(context,ledger,ticket,cues,receipt,attempt="video-1",**kw):
    return ledger.stage(
        context[3],ticket,cues=cues,rights=receipt,attempt_id=attempt,
        at=T2,idle_since=kw.get("idle_since",T0),
        now_seconds=1000,sample=sample(),
        authorized=True,trusted_worker=True,
        consented=kw.get("consented",True),
        video_consent=kw.get("video_consent",True))


def test_video_worker_stages_timecoded_source_exact_review_without_xp(context):
    lead=add_video(context)
    ledger,key=transcript_ledger(context)
    cues=transcript_cues()
    ticket=video_worker(context,lead)
    result=stage_video(context,ledger,ticket,cues,
        transcript_receipt(key,lead,cues))
    assert result["change"]=="new" and result["cues"]==2
    assert not result["knowledge_approved"] and not result["training_authorized"]
    assert context[4].active_grants()==()
    assert not context[3].active
    public=ledger.review_packet(OWNER,lead.source_id,authorized=True)
    private=ledger.review_packet(
        OWNER,lead.source_id,authorized=True,include_quotes=True)
    assert public["timecoded_cues"][0]=={"start_ms":0,"end_ms":1250}
    assert private["timecoded_cues"][0]["text"]==cues[0].text
    assert public["xp_awarded"]==0
    assert context[0]._rows(OWNER)==[]


def test_video_invalid_external_signature_and_foreground_block(context):
    lead=add_video(context)
    ledger,key=transcript_ledger(context)
    cues=transcript_cues()
    invalid=replace(transcript_receipt(key,lead,cues),signature_hex="0"*128)
    ticket=video_worker(context,lead)
    with pytest.raises(PermissionError,match="signature"):
        stage_video(context,ledger,ticket,cues,invalid)
    assert context[4].active_grants()==()
    assert ledger.review_packet(OWNER,lead.source_id,authorized=True) is None
    ticket=video_worker(context,lead)
    with pytest.raises(PermissionError,match="not current"):
        stage_video(context,ledger,ticket,cues,
            transcript_receipt(key,lead,cues),idle_since=T2)
    assert context[4].active_grants()==()


def test_video_retention_is_idempotent_and_journal_tamper_fails_closed(context):
    lead=add_video(context)
    ledger,key=transcript_ledger(context)
    cues=transcript_cues()
    rights=transcript_receipt(key,lead,cues)
    ticket=video_worker(context,lead)
    first=stage_video(context,ledger,ticket,cues,rights)
    ticket=video_worker(context,lead)
    again=stage_video(context,ledger,ticket,cues,rights)
    assert again["replayed"] and again["capture_digest"]==first["capture_digest"]
    different=(
        TimedTranscriptCue(0,1200,"A different game engine fact."),
    )
    ticket=video_worker(context,lead)
    with pytest.raises(ValueError,match="conflicting"):
        stage_video(context,ledger,ticket,different,
            transcript_receipt(key,lead,different),attempt="video-1")
    assert context[4].active_grants()==()
    context[0].db.execute(
        "UPDATE dragon_video_cues_v1 SET body='{}' "
        "WHERE owner=? AND source=?",(OWNER,lead.source_id))
    with pytest.raises(Exception):
        ledger.review_packet(OWNER,lead.source_id,authorized=True)


def test_video_bad_timecodes_and_wrong_rights_track_never_enter_ledger(context):
    lead=add_video(context)
    ledger,key=transcript_ledger(context)
    cue=transcript_cues()
    with pytest.raises(ValueError,match="bounded"):
        TimedTranscriptCue(0,100,"")
    ticket=video_worker(context,lead)
    with pytest.raises(PermissionError,match="permission"):
        stage_video(context,ledger,ticket,cue,
            transcript_receipt(key,lead,(TimedTranscriptCue(0,300,"Other"),)))
    assert context[4].active_grants()==()


def article_source(context):
    lib,a,_,_,_=context
    url=next(row["url"] for row in CATALOG if row["slug"]=="pandocs")
    sid="source-"+sha256(url.encode()).hexdigest()
    lib.db.execute(
        "UPDATE dragon_almanac_jobs SET state='blocked' "
        "WHERE owner=? AND source<>?",(OWNER,sid))
    worker=SequentialAlmanacWorker(a)
    claim=worker.claim(OWNER,now=epoch(T0),authorized=True,trusted_worker=True)
    assert claim.source_id==sid and claim.stage=="policy"
    worker.finish(claim,now=epoch(T0)+1,
        output_digest="a"*64,
        evidence={
            "url":claim.url,"input_digest":claim.input_digest,
            "output_digest":"a"*64,"robots_permitted":True,
            "terms_permitted":True,"reference_use_permitted":True,
            "ssrf_checked":True,"expires_at":epoch(T0)+3600},
        authorized=True,trusted_worker=True)
    return sid,url


def add_capture(captures,sid,url,text,at,name):
    document=extract_document(FetchResponse(
        url,200,{"content-type":"text/plain"},text.encode(),float(at)),url)
    assert document is not None
    return captures.record(
        OWNER,sid,document,capture_id=name,observed_at=at,
        authorized=True,trusted_worker=True,reference_storage_permitted=True,
        response_body_bytes=len(text.encode()))


def prepare_article_revisions(context):
    sid,url=article_source(context)
    captures=DragonSourceCaptures(context[1])
    initial="Gameboy hardware memory access is stable on old devices. " \
            "API timing needs a regression check."
    revised="Gameboy hardware memory access is deprecated on newer devices. " \
            "Breaking API timing requires independent regression validation."
    a=add_capture(captures,sid,url,initial,epoch(T0)+2,"old-capture")
    b=add_capture(captures,sid,url,revised,epoch(T0)+3,"new-capture")
    return captures,sid,url,initial,revised,a,b


def test_update_specialist_detects_exact_changed_spans_not_automatic_truth(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    ledger=DragonSourceDeltaLedger(captures)
    report=ledger.preview(OWNER,sid,authorized=True)
    assert report["change"]=="changed"
    assert report["total_changed_segments"]>=1
    assert not report["training_authorized"] and not report["knowledge_approved"]
    assert report["shown_changes"]
    for item in report["shown_changes"]:
        for text,field in ((old,"before"),(new,"after")):
            evidence=item[field]
            if evidence:
                assert text[evidence["start"]:evidence["end"]]==evidence["exact_quote"]
    assert ledger.preview(OWNER,sid,authorized=True)==report
    assert ledger.review_packet(OWNER,sid,authorized=True) is None


def test_unchanged_recrawl_does_not_claim_updated_knowledge(context):
    captures,sid,url,old,new,a,b=prepare_article_revisions(context)
    add_capture(captures,sid,url,new,epoch(T0)+4,"unchanged-capture")
    ledger=DragonSourceDeltaLedger(captures)
    report=ledger.preview(OWNER,sid,authorized=True)
    assert report["status"]=="unchanged_reobservation"
    assert not report["changed"]
    assert not report["model_training_authorized"]


def test_delta_rejects_cross_tenant_or_corrupt_real_capture(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    ledger=DragonSourceDeltaLedger(captures)
    with pytest.raises(ValueError,match="unregistered"):
        ledger.preview("unrelated",sid,authorized=True)
    context[0].db.execute(
        "UPDATE dragon_technical_captures_v1 SET body='{}' "
        "WHERE owner=? AND source=? AND sequence=2",(OWNER,sid))
    with pytest.raises(Exception):
        ledger.preview(OWNER,sid,authorized=True)



def test_update_hatchling_stages_actual_changed_capture_with_idle_grant(context):
    captures,sid,url,old,new,_,new_capture=prepare_article_revisions(context)
    lib,a,feed,admission,resources=context
    # Publish exactly the same changed source bytes as independently reviewed
    # reference material; this does NOT auto-approve delta findings.
    def reviewed(content,at):
        return ReviewedDocument(
            OWNER,sid,url,"Gameboy hardware research",content,at,
            "rights-reference",("design_reference",),
            "verified-independent-reviewer",True,
            (ReviewedNote(
                "note-gameboy","gameboy",
                "Gameboy device compatibility needs independent tests.",
                0,7,"supports",930000,"publisher-a",("gameboy",)),)
        )
    initial=lib.import_document(
        reviewed(old,T0),expected_parent_digest=None,authorized=True)
    latest=lib.import_document(
        reviewed(new,T1),expected_parent_digest=initial.revision_digest,
        authorized=True)
    update=ResearchLead(
        sid,url,("gameboy",),"updates",T2,
        revision_hint=latest.source_text_digest,published_at=T1)
    result=admission.begin(
        OWNER,sample=sample(),at=T2,idle_since=T0,
        now_seconds=1000,authorized=True,trusted_worker=True,
        consented=True,article_consent=False,video_consent=False,
        updates_consent=True,update_hints=(update,))
    assert result.admitted and result.ticket.lane=="updates"
    ledger=DragonSourceDeltaLedger(captures)
    outcome=ledger.stage_idle(
        admission,result.ticket,
        sample=sample(),at=T2,idle_since=T0,
        now_seconds=1000,authorized=True,trusted_worker=True,
        consented=True,updates_consent=True)
    assert outcome["status"]=="awaiting_independent_update_review"
    assert outcome["changes"]>=1
    assert not outcome["model_training_authorized"]
    assert resources.active_grants()==()
    assert not admission.active
    packet=ledger.review_packet(OWNER,sid,authorized=True)
    assert packet["independent_claim_review_required"]
    assert packet["candidate_changes"]
    assert not packet["model_training_authorized"]
    assert len(lib.history(OWNER,sid,authorized=True))==2
    # Harmless re-observation cannot make the already-staged evidence stale.
    add_capture(captures,sid,url,new,epoch(T0)+4,"unchanged-again")
    still=ledger.review_packet(OWNER,sid,authorized=True)
    assert still["delta_receipt"]==packet["delta_receipt"]
    # A genuinely different subsequent revision must invalidate the packet.
    add_capture(captures,sid,url,
        "Gameboy hardware latency now has different constraints.",
        epoch(T0)+5,"later-change")
    with pytest.raises(ValueError,match="supersedes"):
        ledger.review_packet(OWNER,sid,authorized=True)


def test_update_lane_rejects_repeated_growth_from_same_revision(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    ledger=DragonSourceDeltaLedger(captures)
    original=ledger.preview(OWNER,sid,authorized=True)
    assert original["delta_digest"]
    add_capture(captures,sid,url,new,epoch(T0)+4,"repeated")
    report=ledger.preview(OWNER,sid,authorized=True)
    assert report["status"]=="unchanged_reobservation"
    assert not report["model_training_authorized"]



def test_mother_dragon_synergy_links_only_exact_video_and_delta_evidence(context):
    captures,sid,url,old,new,_,new_capture=prepare_article_revisions(context)
    lib,a,feed,admission,resources=context
    def reviewed(content,at):
        return ReviewedDocument(
            OWNER,sid,url,"Gameboy reference research",content,at,
            "rights-reference",("design_reference",),
            "reviewer",True,
            (ReviewedNote(
                "note-1","gameboy",
                "Gameboy timing needs review",0,7,
                "supports",930000,"publisher-a",("gameboy",)),)
        )
    prior=lib.import_document(
        reviewed(old,T0),expected_parent_digest=None,authorized=True)
    latest=lib.import_document(
        reviewed(new,T1),expected_parent_digest=prior.revision_digest,
        authorized=True)
    hint=ResearchLead(
        sid,url,("gameboy",),"updates",T2,
        revision_hint=latest.source_text_digest,published_at=T1)
    update_ticket=admission.begin(
        OWNER,sample=sample(),at=T2,idle_since=T0,
        now_seconds=1000,authorized=True,trusted_worker=True,
        consented=True,article_consent=False,video_consent=False,
        updates_consent=True,update_hints=(hint,)).ticket
    assert update_ticket and update_ticket.lane=="updates"
    updates=DragonSourceDeltaLedger(captures)
    staged=updates.stage_idle(
        admission,update_ticket,sample=sample(),at=T2,idle_since=T0,
        now_seconds=1000,authorized=True,trusted_worker=True,
        consented=True,updates_consent=True)
    assert staged["status"]=="awaiting_independent_update_review"
    lead=add_video(context)
    videos,key=transcript_ledger(context)
    cues=transcript_cues()
    vt=video_worker(context,lead)
    staged_video=stage_video(
        context,videos,vt,cues,transcript_receipt(key,lead,cues))
    mother=DragonMotherEvidenceSynergy(videos,updates)
    packet=mother.preview(OWNER,lead.source_id,sid,authorized=True)
    assert packet["status"]=="possible_cross_media_relevance"
    assert packet["video_capture_digest"]==staged_video["capture_digest"]
    assert packet["bridges"]
    assert "gameboy" in packet["task_terms"]
    assert not packet["source_independence_verified"]
    assert not packet["knowledge_approved"]
    assert not packet["training_authorized"]
    with pytest.raises(ValueError,match="unregistered"):
        mother.preview("other-tenant",lead.source_id,sid,authorized=True)

    # The mother must incorporate ALL THREE independent hatchling roles:
    # article exact citations + video timecodes + changed-source scrutiny.
    triad=DragonThreeHatchlingCoordinator(
        DragonArticleHatchling(captures),videos,updates,feed.nest)
    statuses=triad.status(
        OWNER,article_source_id=sid,video_source_id=lead.source_id,
        update_source_id=sid,authorized=True)
    assert [h["lane"] for h in statuses["hatchlings"]]==[
        "article","video","updates"]
    assert statuses["lane_count"]==3
    assert statuses["review_ready_count"]==3
    assert statuses["distinct_source_count"]==2
    assert statuses["mother_stage"]=="adult"
    assert statuses["mother_level"]>=1
    assert all(h["growth"]["level"]==0 for h in statuses["hatchlings"])
    assert all(h["growth"]["accepted_evidence_count"]==0
               for h in statuses["hatchlings"])
    triad_packet=triad.mother_review(
        OWNER,article_source_id=sid,video_source_id=lead.source_id,
        update_source_id=sid,authorized=True)
    assert triad_packet["status"]=="three_lane_research_questions"
    assert triad_packet["hypotheses"]
    first=triad_packet["hypotheses"][0]
    assert set(first["source_ids"])=={"article","video","updates"}
    assert {"hardware","gameboy"} & set(first["shared_terms"])
    assert first["video"]["exact_quote"] in {x.text for x in cues}
    assert first["article"]["exact_quote"] in new
    assert first["updates"]["exact_quote"] in new
    assert not triad_packet["source_independence_verified"]
    assert not triad_packet["agreement_verified"]
    assert not triad_packet["training_authorized"]
    assert not triad_packet["shadow_weights_authorized"]
    assert first["risk_lenses"]["agreement_verified"] is False
    assert first["risk_lenses"]["independent_source_review_required"] is True
    assert len(first["risk_lenses"]["lens_digest"])==64
    assert triad_packet["xp_awarded"]==0
    assert triad.mother_review(
        OWNER,article_source_id=sid,video_source_id=lead.source_id,
        update_source_id=sid,authorized=True)==triad_packet
    assert resources.active_grants()==()


def test_mother_synergy_rejects_mismatched_authority(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    videos,key=transcript_ledger(context)
    from skeleton.ai.game_builder.dragon_mother_evidence_synergy import (
        DragonMotherEvidenceSynergy,
    )
    with pytest.raises(TypeError,match="canonical"):
        DragonMotherEvidenceSynergy(videos,None)
    with pytest.raises(ValueError,match="independent"):
        DragonMotherEvidenceSynergy(
            videos,DragonSourceDeltaLedger(captures)
        ).preview(OWNER,sid,sid,authorized=True)



def test_article_hatchling_preserves_material_evidence_after_unchanged_observation(context):
    captures,sid,url,old,new,prior,latest=prepare_article_revisions(context)
    articles=DragonArticleHatchling(captures)
    first=articles.review_packet(
        OWNER,sid,authorized=True,include_quotes=True)
    assert first["lane"]=="article"
    assert first["candidate_capture_digest"]==latest["capture_digest"]
    assert first["observation_count"]==2
    assert first["passages"]
    for span in first["passages"]:
        assert new[span["start"]:span["end"]]==span["exact_quote"]
    assert first["xp_awarded"]==0 and not first["knowledge_approved"]
    masked=articles.review_packet(OWNER,sid,authorized=True)
    assert all(span["exact_quote"] is None for span in masked["passages"])
    assert all(len(span["quote_sha256"])==64 for span in masked["passages"])
    add_capture(captures,sid,url,new,epoch(T0)+4,"unchanged-recrawl")
    retained=articles.review_packet(
        OWNER,sid,authorized=True,include_quotes=True)
    assert retained["candidate_capture_digest"]==latest["capture_digest"]
    assert retained["observation_count"]==3
    assert retained["unchanged_rechecks_after_candidate"]==1
    assert retained["latest_observation_change"]=="unchanged"
    assert retained["latest_observation_digest"]!=latest["capture_digest"]
    assert retained["passages"]==first["passages"]
    assert "unchanged rechecks" in retained["improvements"][0]
    census=articles.census(OWNER,authorized=True)
    assert census["count_this_page"]==1
    assert census["items"][0]["candidate_capture_digest"]==latest["capture_digest"]
    assert not census["training_authorized"]
    assert context[4].active_grants()==()


def test_article_hatchling_refuses_unregistered_owner_and_tampered_citations(context):
    captures,sid,url,old,new,prior,latest=prepare_article_revisions(context)
    articles=DragonArticleHatchling(captures)
    with pytest.raises(PermissionError):
        articles.review_packet(OWNER,sid,authorized=False)
    with pytest.raises(ValueError,match="unregistered"):
        articles.review_packet("other-tenant",sid,authorized=True)
    with pytest.raises(ValueError,match="canonical"):
        articles.census(OWNER,authorized=True,after_source="../../foreign")
    context[0].db.execute(
        "UPDATE dragon_technical_captures_v1 SET body='{}' "
        "WHERE owner=? AND source=? AND sequence=2",(OWNER,sid))
    with pytest.raises(Exception):
        articles.review_packet(OWNER,sid,authorized=True)


def test_three_hatchling_coordinator_incomplete_lanes_do_not_promote(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    videos,key=transcript_ledger(context)
    lead=add_video(context)
    triad=DragonThreeHatchlingCoordinator(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures),context[2].nest)
    status=triad.status(
        OWNER,article_source_id=sid,video_source_id=lead.source_id,
        update_source_id=sid,authorized=True)
    assert status["lane_count"]==3
    assert status["review_ready_count"]==1
    assert [h["status"] for h in status["hatchlings"]]==[
        "review_ready","awaiting_licensed_transcript","awaiting_material_revision"]
    review=triad.mother_review(
        OWNER,article_source_id=sid,video_source_id=lead.source_id,
        update_source_id=sid,authorized=True)
    assert review["status"]=="awaiting_three_reviewable_lanes"
    assert review["hypotheses"]==[]
    assert review["xp_awarded"]==0
    assert not review["training_authorized"]
    with pytest.raises(ValueError,match="differ"):
        triad.status(
            OWNER,article_source_id=sid,video_source_id=sid,
            update_source_id=sid,authorized=True)
    with pytest.raises(PermissionError):
        triad.status(
            OWNER,article_source_id=sid,video_source_id=lead.source_id,
            update_source_id=sid,authorized=False)


def test_article_hatchling_has_no_spurious_findings_without_captures(context):
    article=DragonArticleHatchling(
        DragonSourceCaptures(context[1]))
    url=next(item["url"] for item in CATALOG if item["slug"]=="pandocs")
    sid="source-"+sha256(url.encode()).hexdigest()
    packet=article.review_packet(OWNER,sid,authorized=True)
    assert packet["status"]=="not_yet_captured"
    assert packet["passages"]==[]
    assert packet["xp_awarded"]==0
    assert not packet["training_authorized"]



def test_research_source_picker_lists_all_three_lane_choices_without_network(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    lead=add_video(context)
    videos,_=transcript_ledger(context)
    picker=DragonResearchSourcePicker(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures))
    cursor=None
    collected=[]
    for _ in range(25):
        page=picker.page(OWNER,authorized=True,limit=20,after_source=cursor)
        assert page["read_only"] and page["network_requests"]==0
        assert not page["training_authorized"] and page["xp_awarded"]==0
        assert all(not item["is_rights_approval"] for item in page["entries"])
        collected+=page["entries"]
        if not page["has_more"]:
            break
        cursor=page["next_after_source"]
        assert cursor
    assert {entry["source_id"] for entry in collected}=={sid,lead.source_id}
    article=next(e for e in collected if e["kind"]=="article")
    video=next(e for e in collected if e["kind"]=="video")
    assert article["research_status"]=="review_candidate"
    assert article["capture_digest"]
    assert video["research_status"]=="awaiting_licensed_transcript"
    assert video["capture_digest"] is None
    assert not context[4].active_grants()


def test_research_catalog_owner_isolation_bad_cursors_and_corrupt_source(context):
    captures,sid,_,_,_,_,_=prepare_article_revisions(context)
    lead=add_video(context)
    videos,_=transcript_ledger(context)
    picker=DragonResearchSourcePicker(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures))
    assert picker.page("foreign-owner",authorized=True)["entries"]==[]
    with pytest.raises(PermissionError):
        picker.page(OWNER,authorized=False)
    with pytest.raises(ValueError,match="cursor"):
        picker.page(OWNER,authorized=True,after_source="../../foreign")
    with pytest.raises(ValueError):
        picker.page(OWNER,authorized=True,limit=1000)
    context[0].db.execute(
        "UPDATE dragon_almanac_sources SET digest=? "
        "WHERE owner=? AND source=?",("0"*64,OWNER,lead.source_id))
    with pytest.raises(ValueError,match="identity|integrity"):
        cursor=None
        while True:
            page=picker.page(OWNER,authorized=True,limit=60,after_source=cursor)
            if not page["has_more"]:
                break
            cursor=page["next_after_source"]



def test_three_hatchlings_new_owner_without_signed_nest_reports_real_zero_progress(context):
    from contextlib import closing
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    lead=add_video(context)
    videos,_=transcript_ledger(context)
    # Use a REAL empty signed-nest SQLite database. This catches failures
    # that mocking read() would conceal, including accidental XP creation.
    with closing(sqlite3.connect(":memory:")) as empty_db:
        nest=DragonNestStore(
            empty_db,signing_key=b"fresh-dragon-nest-test-signing-key-minimum-32-bytes")
        assert nest.read(OWNER,authorized=True) is None
        triad=DragonThreeHatchlingCoordinator(
            DragonArticleHatchling(captures),videos,
            DragonSourceDeltaLedger(captures),nest)
        status=triad.status(
            OWNER,article_source_id=sid,video_source_id=lead.source_id,
            update_source_id=sid,authorized=True)
        assert nest.read(OWNER,authorized=True) is None
        assert empty_db.execute(
            "SELECT COUNT(*) FROM dragon_nest_history"
        ).fetchone()[0]==0
    assert status["mother_stage"]=="not_initialized"
    assert status["mother_level"] is None
    assert status["lane_count"]==3
    assert [child["growth"]["stage"] for child in status["hatchlings"]]==[
        "locked","locked","locked"]
    assert all(child["growth"]["level"]==0 for child in status["hatchlings"])
    assert all(child["growth"]["accepted_evidence_count"]==0
               for child in status["hatchlings"])
    assert status["xp_awarded"]==0
    assert status["model_training_authorized"] is False


def test_existing_signed_nest_with_tampered_head_is_not_mistaken_for_new_egg(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    lead=add_video(context)
    videos,_=transcript_ledger(context)
    nest=context[2].nest
    triad=DragonThreeHatchlingCoordinator(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures),nest)
    assert nest.read(OWNER,authorized=True) is not None
    nest.db.execute(
        "UPDATE dragon_nest_state SET head=? WHERE owner=?",
        ("f"*64,OWNER))
    with pytest.raises(ValueError,match="signature|history|head|invalid"):
        triad.status(
            OWNER,article_source_id=sid,video_source_id=lead.source_id,
            update_source_id=sid,authorized=True)



def test_three_hatchling_research_workboard_reports_actual_pending_actions(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    lead=add_video(context)
    videos,_=transcript_ledger(context)
    board=DragonResearchWorkboard(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures))
    tasks=[]
    cursor=None
    for _ in range(30):
        page=board.page(OWNER,authorized=True,limit=20,after_source=cursor)
        assert page["schema"]=="skeleton.dragon.research_workboard.v1"
        assert page["read_only"] and page["workers_started"]==0
        assert not page["training_authorized"]
        assert page["permissions_granted"]==0 and page["xp_awarded"]==0
        tasks+=page["missions"]
        if not page["has_more"]:
            break
        cursor=page["next_after_source"]
    by_lane={lane:[x for x in tasks if x["lane"]==lane]
             for lane in ("article","video","updates")}
    assert len(by_lane["article"])==1
    assert len(by_lane["video"])==1
    assert len(by_lane["updates"])==1
    assert by_lane["article"][0]["action"]=="article_candidate"
    assert by_lane["article"][0]["requires_independent_wiki_review"]
    assert by_lane["video"][0]["action"]=="video_needs_transcript"
    assert by_lane["video"][0]["requires_operator_authorization"]
    assert by_lane["updates"][0]["action"]=="update_needs_idle_analysis"
    assert by_lane["updates"][0]["requires_idle"]
    assert all(not task["automatically_executable"] for task in tasks)
    assert all(not task["model_training_authorized"] for task in tasks)
    assert not context[4].active_grants()


def test_workboard_no_rights_or_training_and_tenant_guard(context):
    captures,sid,_,_,_,_,_=prepare_article_revisions(context)
    videos,_=transcript_ledger(context)
    board=DragonResearchWorkboard(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures))
    assert board.page("different-tenant",authorized=True)["missions"]==[]
    with pytest.raises(PermissionError):
        board.page(OWNER,authorized=False)
    with pytest.raises(ValueError,match="cursor"):
        board.page(OWNER,authorized=True,after_source="../../other")
    with pytest.raises(ValueError):
        board.page(OWNER,authorized=True,limit=999)
    with pytest.raises(TypeError,match="canonical"):
        DragonResearchWorkboard(None,videos,DragonSourceDeltaLedger(captures))


def test_workboard_duplicate_reobservation_does_not_claim_change(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    videos,_=transcript_ledger(context)
    board=DragonResearchWorkboard(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures))
    add_capture(captures,sid,url,new,epoch(T0)+4,"same-source-recheck")
    # The catalog has 248 entries, while a workboard response is capped
    # to 60 source IDs. Page through canonical cursors before asserting a
    # particular source's state.
    changes=[]
    cursor=None
    for _ in range(10):
        page=board.page(OWNER,authorized=True,limit=60,after_source=cursor)
        changes.extend(
            m for m in page["missions"]
            if m["lane"]=="updates" and m["source_id"]==sid)
        if not page["has_more"]:
            break
        cursor=page["next_after_source"]
        assert cursor
    assert len(changes)==1
    assert changes[0]["action"]=="update_unchanged"
    assert changes[0]["requires_idle"] is False
    assert changes[0]["xp_awarded"]==0
    assert changes[0]["model_training_authorized"] is False



def test_three_hatchling_history_preserves_timestamped_article_and_video_custody(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    lead=add_video(context)
    videos,key=transcript_ledger(context)
    cues=transcript_cues()
    ticket=video_worker(context,lead)
    result=stage_video(
        context,videos,ticket,cues,transcript_receipt(key,lead,cues))
    deltas=DragonSourceDeltaLedger(captures)
    history=DragonFamilyResearchHistory(
        DragonArticleHatchling(captures),videos,deltas)
    packet=history.timeline(
        OWNER,article_source_id=sid,
        video_source_id=lead.source_id,update_source_id=sid,
        authorized=True,limit=10)
    assert packet["schema"]=="skeleton.dragon.three_hatchling_history.v1"
    assert packet["event_counts"]=={"article":2,"video":1,"updates":0}
    assert packet["total_events"]==3
    assert packet["entries"][0]["lane"]=="video"
    assert packet["entries"][0]["event_digest"]==result["capture_digest"]
    assert all(event["change_note"].startswith("(") for event in packet["entries"])
    assert all("exact_quote" not in event and "text" not in event
               for event in packet["entries"])
    assert all(event["observation_at"]>0 for event in packet["entries"])
    assert packet["network_requests"]==0 and packet["workers_started"]==0
    assert packet["xp_awarded"]==0 and not packet["knowledge_approved"]
    assert not packet["training_authorized"]
    one=history.timeline(
        OWNER,article_source_id=sid,
        video_source_id=lead.source_id,update_source_id=sid,
        authorized=True,limit=1)
    assert one["truncated"] and len(one["entries"])==1
    assert one["total_events"]==3
    assert context[4].active_grants()==()


def test_family_history_owner_tampering_and_invalid_source_refused(context):
    captures,sid,url,old,new,_,_=prepare_article_revisions(context)
    lead=add_video(context)
    videos,key=transcript_ledger(context)
    ledger=DragonFamilyResearchHistory(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures))
    with pytest.raises(PermissionError):
        ledger.timeline(
            OWNER,article_source_id=sid,video_source_id=lead.source_id,
            update_source_id=sid,authorized=False)
    with pytest.raises(ValueError,match="unregistered"):
        ledger.timeline(
            "foreign-owner",article_source_id=sid,
            video_source_id=lead.source_id,update_source_id=sid,
            authorized=True)
    with pytest.raises(ValueError,match="differ"):
        ledger.timeline(
            OWNER,article_source_id=sid,
            video_source_id=sid,update_source_id=sid,
            authorized=True)
    with pytest.raises(ValueError):
        ledger.timeline(
            OWNER,article_source_id=sid,
            video_source_id=lead.source_id,update_source_id=sid,
            authorized=True,limit=0)
    context[0].db.execute(
        "UPDATE dragon_technical_captures_v1 SET digest=? "
        "WHERE owner=? AND source=? AND sequence=2",
        ("0"*64,OWNER,sid))
    with pytest.raises(ValueError,match="integrity"):
        ledger.timeline(
            OWNER,article_source_id=sid,video_source_id=lead.source_id,
            update_source_id=sid,authorized=True)



def test_mother_task_plan_balances_three_real_hatchlings_without_execution(context):
    captures,sid,_,_,_,_,_=prepare_article_revisions(context)
    lead=add_video(context)
    videos,_=transcript_ledger(context)
    board=DragonResearchWorkboard(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures))
    planner=DragonTaskResearchPlanner(board)
    terms=("gameboy","physics")
    first=planner.plan(OWNER,authorized=True,task_terms=terms,
                       max_sources=300,limit=12)
    second=planner.plan(OWNER,authorized=True,task_terms=terms,
                        max_sources=300,limit=12)
    assert first==second
    assert first["schema"]=="skeleton.dragon.task_research_plan.v1"
    assert first["search_scope_exhausted"]
    assert first["scanned_registered_sources"]==249
    assert set(first["represented_hatchlings"])=={"article","video","updates"}
    assert first["distinct_source_ids"]<=first["suggestion_count"]
    assert first["distinct_source_hosts"]<=first["suggestion_count"]
    # Eligibility and review policy may exclude an otherwise curated
    # topic. The planner must report that gap honestly rather than invent
    # a match from an unapproved publisher or missing video transcript.
    matched=set(first["matched_task_terms"])
    missing=set(first["unmatched_task_terms"])
    assert matched | missing == set(terms)
    assert matched.isdisjoint(missing)
    assert "gameboy" in matched
    assert len(first["plan_digest"])==64
    assert all(not task["source_independence_verified"]
               and not task["automatically_executable"]
               and not task["knowledge_approved"]
               and not task["training_authorized"]
               and task["xp_awarded"]==0
               for task in first["suggestions"])
    article=next(t for t in first["suggestions"] if t["lane"]=="article")
    assert article["lexical_priority_signal"]>0
    assert first["read_only"] and first["network_requests"]==0
    # Two-letter industry axes must be accepted, not silently filtered.
    short=planner.plan(OWNER,authorized=True,task_terms=("ai","qa"),
                       max_sources=60,limit=3)
    assert short["task_terms"]==["ai","qa"]
    assert short["source_scan_budget"]==60
    assert first["workers_started"]==0 and first["permissions_granted"]==0
    assert first["xp_awarded"]==0 and not first["training_authorized"]
    assert not context[4].active_grants()


def test_mother_task_plan_partial_scan_does_not_claim_catalog_complete(context):
    captures,_,_,_,_,_,_=prepare_article_revisions(context)
    videos,_=transcript_ledger(context)
    planner=DragonTaskResearchPlanner(DragonResearchWorkboard(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures)))
    small=planner.plan(OWNER,authorized=True,task_terms=("gameboy",),
                       max_sources=1,limit=2)
    assert small["scanned_registered_sources"]==1
    assert not small["search_scope_exhausted"]
    assert small["source_scan_budget"]==1
    assert len(small["suggestions"])<=2
    assert small["host_diversity_not_independent_corroboration"]
    assert small["lexical_priority_not_quality_or_fact_confidence"]


def test_mother_task_plan_refuses_forged_tasks_and_cross_tenant_custody(context):
    captures,_,_,_,_,_,_=prepare_article_revisions(context)
    videos,_=transcript_ledger(context)
    planner=DragonTaskResearchPlanner(DragonResearchWorkboard(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures)))
    assert planner.plan("other-tenant",authorized=True,
                        task_terms=("gameboy",))["suggestions"]==[]
    with pytest.raises(PermissionError):
        planner.plan(OWNER,authorized=False,task_terms=("gameboy",))
    for terms in ((),("physics","physics"),("../../../",),("Gameboy",),
                  ("x",),("gameboy",42),["gameboy"],tuple("abcdefghij")):
        with pytest.raises(ValueError,match="task terms"):
            planner.plan(OWNER,authorized=True,task_terms=terms)
    for invalid in (False,0,301):
        with pytest.raises(ValueError,match="scan budget"):
            planner.plan(OWNER,authorized=True,task_terms=("gameboy",),
                         max_sources=invalid)
    for invalid in (False,0,19):
        with pytest.raises(ValueError,match="recommendations"):
            planner.plan(OWNER,authorized=True,task_terms=("gameboy",),
                         limit=invalid)


def test_mother_task_plan_refuses_tampered_source_registry(context):
    captures,sid,_,_,_,_,_=prepare_article_revisions(context)
    videos,_=transcript_ledger(context)
    planner=DragonTaskResearchPlanner(DragonResearchWorkboard(
        DragonArticleHatchling(captures),videos,
        DragonSourceDeltaLedger(captures)))
    context[0].db.execute(
        "UPDATE dragon_almanac_sources SET digest=? "
        "WHERE owner=? AND source=?",("0"*64,OWNER,sid))
    with pytest.raises(ValueError,match="integrity"):
        planner.plan(OWNER,authorized=True,task_terms=("gameboy",),
                     max_sources=300,limit=12)
