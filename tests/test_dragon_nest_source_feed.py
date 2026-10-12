"""Canonical technical sources -> three idle-only Dragon gatherer integration."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import sqlite3

import pytest

from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url
from skeleton.ai.game_builder.dragon_technical_source_atlas import (
    CATALOG, DragonTechnicalSources,
)
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
)
from skeleton.ai.webcrawler.dragon_nest_source_feed import DragonNestSourceFeed
from skeleton.ai.webcrawler.dragon_nest_research_scheduler import ResearchLead
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample
from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json

OWNER = "studio"
T0 = "2026-10-12T12:00:00Z"
T1 = "2026-10-12T12:05:00Z"
T2 = "2026-10-12T12:15:00Z"


def sid(url):
    return "source-" + sha256(url.encode()).hexdigest()


def tick(value=T0):
    return int(datetime.fromisoformat(value.replace("Z","+00:00")).timestamp())


def hardware(age=0, pressure=.1):
    return HardwareSample(512*1024*1024,8,pressure,.75,True,False,1000-age)


@pytest.fixture
def studio(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"sources.sqlite") as lib:
        a=DragonAlmanacs(lib)
        atlas=DragonTechnicalSources(a)
        atlas.import_catalog(OWNER,authorized=True,recorded_at=tick())
        db=sqlite3.connect(":memory:")
        nest=DragonNestStore(db,signing_key=b"source-feed-trusted-test-signing-key-123456")
        nest.initialize(OWNER,("parent-source",),
            focus_tags=("gameboy",),adjacent_tags=("debugging",),
            at=T0,authorized=True)
        nest.record_parent(OWNER,"parent-source",content_sha256="a"*64,
            at=T0,authorized=True,reviewed=True,lawful=True)
        try:
            yield lib,a,atlas,nest,DragonNestSourceFeed(a,atlas,nest)
        finally:
            db.close()


def preview(broker,**changes):
    inputs={"sample":hardware(),"at":T2,"idle_since":T0,
        "now_seconds":1000,"authorized":True,"consented":True,
        "article_consent":True,"video_consent":True,
        "updates_consent":True}
    inputs.update(changes)
    return broker.preview(OWNER,**inputs)


def add_video(lib,a,url="https://www.youtube.com/watch?v=abc123"):
    url=canonical_source_url(url)
    source=sid(url)
    body={"source_id":source,"url":url,"host":"www.youtube.com",
        "kind":"video_candidate","discoveries":[],
        "availability":"not_checked","rights":"not_assessed",
        "independence":"not_assessed","training_authorized":False}
    lib.db.execute("INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
                   (OWNER,source,canonical_json(body),canonical_digest(body)))
    SequentialAlmanacWorker(a).seed(OWNER,authorized=True)
    return ResearchLead(source,url,("gameboy",),"video",T1)


def update_source(lib):
    url=next(x["url"] for x in CATALOG if x["slug"]=="pandocs")
    source=sid(url)
    def doc(text,at):
        return ReviewedDocument(OWNER,source,url,"Original hardware note",text,at,
            "rights-reference",("design_reference",),"independent-reviewer",True,
            (ReviewedNote("note-1","gameboy","Hardware timing requires careful review.",
                          0,7,"supports",940000,"publisher-a",("gameboy",)),))
    first=lib.import_document(doc("Gameboy initial hardware note.",T0),
        expected_parent_digest=None,authorized=True)
    latest=lib.import_document(doc("Gameboy revised hardware note.",T1),
        expected_parent_digest=first.revision_digest,authorized=True)
    return ResearchLead(source,url,("gameboy",),"updates",T2,
                        latest.source_text_digest,T1),latest


def test_new_article_atlas_is_connected_to_real_signed_idle_nest(studio):
    lib,a,atlas,nest,broker=studio
    before=lib.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs").fetchone()[0]
    signed_before=nest.read(OWNER,authorized=True)
    result=preview(broker)
    assert result.curated_article_leads>=2
    assert result.registered_video_leads==0
    assert result.reviewed_revision_leads==0
    assert any(x.lane=="article" for x in result.plan.assignments)
    assert all(not x.execution_authorized and
               not x.memory_promotion_authorized for x in result.plan.assignments)
    assert result.network_requests==0 and not result.queue_modified
    assert lib.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs").fetchone()[0]==before
    assert nest.read(OWNER,authorized=True)==signed_before
    assert preview(broker)==result


def test_video_is_registered_and_kept_separate_from_article(studio):
    lib,a,_,_,broker=studio
    video=add_video(lib,a)
    result=preview(broker,video_hints=(video,))
    assert result.registered_video_leads==1
    assert any(x.lane=="video" and x.source_id==video.source_id
               for x in result.plan.assignments)
    missing=ResearchLead(sid("https://www.youtube.com/watch?v=missing"),
        "https://www.youtube.com/watch?v=missing",("gameboy",),"video",T1)
    missing_plan=preview(broker,article_consent=False,video_hints=(missing,))
    assert missing_plan.registered_video_leads==0
    assert missing_plan.rejected_external_leads==1
    assert missing_plan.plan.assignments==()


def test_real_changed_reviewed_revision_can_be_proposed_as_update(studio):
    lib,a,_,_,broker=studio
    video=add_video(lib,a)
    updated,_=update_source(lib)
    result=preview(broker,video_hints=(video,),update_hints=(updated,))
    assert result.reviewed_revision_leads==1
    assert result.registered_video_leads==1
    assert result.curated_article_leads>=1
    assert result.duplicate_source_leads>=1
    assert [x.lane for x in result.plan.assignments].count("updates")==1
    assert [x.lane for x in result.plan.assignments].count("video")==1
    assert all(x.evidence_only and not x.execution_authorized
               for x in result.plan.assignments)
    assert result.plan.memory_promotion_authorized is False


def test_source_version_hint_must_match_current_reviewed_text(studio):
    lib,_,_,_,broker=studio
    updated,_=update_source(lib)
    old=ResearchLead(updated.source_id,updated.url,updated.tags,
        "updates",T2,"b"*64,T1)
    wrong=preview(broker,article_consent=False,update_hints=(old,))
    assert wrong.reviewed_revision_leads==0
    assert wrong.rejected_external_leads==1
    assert wrong.plan.assignments==()
    # A rediscovery is not a publication or a changed version.
    no_date=ResearchLead(updated.source_id,updated.url,updated.tags,
        "updates",T2,updated.revision_hint,None)
    assert preview(broker,article_consent=False,
                   update_hints=(no_date,)).reviewed_revision_leads==0


def test_forged_owner_url_or_wrong_media_never_enters_acquisition(studio):
    lib,a,_,_,broker=studio
    video=add_video(lib,a)
    with pytest.raises(ValueError,match="canonical acquisition"):
        preview(broker,video_hints=(ResearchLead(
            "source-"+("f"*64),video.url,("gameboy",),"video",T1),))
    assert preview(broker,article_consent=False,
        video_hints=(video,),video_consent=False).plan.assignments==()
    with pytest.raises(ValueError,match="initialized"):
        broker.preview("another-owner",sample=hardware(),at=T2,
            idle_since=T0,now_seconds=1000,authorized=True,consented=True,
            article_consent=True,video_consent=True,updates_consent=True)
    with pytest.raises(PermissionError):
        preview(broker,authorized=False)


def test_foreground_or_missing_consent_performs_no_source_scanning(studio):
    lib,_,_,_,broker=studio
    # Deliberately damage a source row to verify that preflight denies work
    # before inspecting either curated metadata or external discovery hints.
    source=sid(next(x["url"] for x in CATALOG if x["slug"]=="pandocs"))
    lib.db.execute("UPDATE dragon_almanac_sources SET body='{}' "
                   "WHERE owner=? AND source=?",(OWNER,source))
    assert preview(broker,consented=False).plan.reason=="authorization_or_consent_absent"
    assert preview(broker,idle_since=T2).plan.reason=="foreground_or_insufficient_idle_time"
    assert preview(broker,sample=hardware(pressure=.99)).plan.assignments==()
    with pytest.raises(ValueError,match="metadata integrity"):
        preview(broker)


def test_blocked_policy_jobs_are_suppressed(studio):
    lib,a,_,_,broker=studio
    video=add_video(lib,a)
    lib.db.execute("UPDATE dragon_almanac_jobs SET state='blocked' "
                   "WHERE owner=? AND source=?",(OWNER,video.source_id))
    r=preview(broker,article_consent=False,video_hints=(video,))
    assert r.registered_video_leads==0
    assert r.rejected_external_leads==1
    assert r.plan.assignments==()


def test_repeat_leads_are_counted_and_bounded(studio):
    lib,a,_,_,broker=studio
    video=add_video(lib,a)
    r=preview(broker,video_hints=(video,video))
    assert r.registered_video_leads==1
    assert r.duplicate_source_leads==1
    with pytest.raises(ValueError,match="bounded specialist"):
        preview(broker,video_hints=(video,)*129)
    with pytest.raises(ValueError,match="explicit per-specialist"):
        preview(broker,video_consent=1)
    with pytest.raises(ValueError,match="article candidate limit"):
        preview(broker,article_limit=0)
