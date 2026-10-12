"""Host-owned Dragon idle sessions: durable opt-in, revocation, quota and recovery."""
from __future__ import annotations

from hashlib import sha256
import sqlite3

import pytest

from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_family import IdleWindow, SourceReceipt
from skeleton.ai.webcrawler.dragon_family_custody_bridge import (
    DragonFamilyCustodyBridge, ApprovedSourceSnapshot,
)
from skeleton.ai.webcrawler.dragon_family_idle_host import (
    DragonIdleHostControl, DragonIdleHostPolicy, idle_consent_scope, SCHEMA,
)
from skeleton.ai.webcrawler.dragon_family_idle_integration import AcquiredArticle
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_ledger import DragonKnowledgeLedger
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab, ApprovedLesson
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import EvidencePass

OWNER="host-study"
T=1800000000.
SRC="doc-1"
URL="https://example.org/original-game-design"
TOPICS=("game_design",)
ADJACENT=("physics",)


def doc(text: str, when: float) -> CrawlDocument:
    digest=sha256(text.encode()).hexdigest()
    provenance={"schema":"skeleton.ai.crawl.provenance.v1",
                "canonical_url":URL,"fetched_url":URL,
                "content_hash":digest,"fetched_at":when,"status":200}
    return CrawlDocument(URL,URL,"Original game design",text,"text/html",
                         digest,when,.95,provenance,())


def reviewed(db: sqlite3.Connection, document: CrawlDocument) -> None:
    ledger=DragonKnowledgeLedger(db)
    for i in range(3):
        ledger.add(OWNER,EvidencePass(
            source_id=SRC,source_revision=document.content_hash,
            pass_id=f"source-read-{i}-{document.content_hash[:8]}",
            claim_id="claim-game",supports=True,confidence=.99,
            reliability=.99,independence_group="original-publisher",
            evidence_locator=f"sha256:{document.content_hash}@0:12",
            observation="locally reviewed original game design"),authorized=True)
    belief=ledger.belief(OWNER,"claim-game",authorized=True)
    decision=PromotionDecision("claim-game",True,.99,
          "empirically_calibrated_probability","b"*64,(),belief.evidence_digest)
    DragonPracticeLab(db).offer(ApprovedLesson(
        OWNER,"Source-reviewed design",decision,"a"*64,
        (Mechanic.MOVEMENT,),True),authorized=True,now=T)


def snap(at: float) -> ApprovedSourceSnapshot:
    return ApprovedSourceSnapshot(SRC,"article",URL,TOPICS,"claim-game",at,
                                  "reviewed new mechanic evidence")


def make(db: sqlite3.Connection | None = None, *,
         quota: int = 8, lifetime: float = 86400):
    db=db or sqlite3.connect(":memory:")
    bridge=DragonFamilyCustodyBridge(db,OWNER)
    initial=doc("Original independently reviewed game physics.",T+1)
    reviewed(db,initial)
    seed,proof=bridge.article(snap(T+10),initial)
    family=bridge.family()
    family.enroll(OWNER,(seed,),authorized=True,now=T+2)
    family.seal_inventory(OWNER,authorized=True,now=T+3)
    family.consume(OWNER,proof,authorized=True)
    scope=idle_consent_scope(OWNER,TOPICS,ADJACENT)
    ledger=DragonConsentLedger(db)
    grant=ledger.issue(OWNER,capture=True,analysis=True,issued_at=T+100,
                       expires_at=T+100+lifetime,policy_version="dragon-idle-host-v1",
                       scope_digest=scope,authorized=True)
    host=DragonIdleHostControl(bridge,host_policy=DragonIdleHostPolicy(
        max_daily_attempts=quota,max_daily_per_role=quota))
    return db,bridge,family,host,grant


def idle(now=T+720, *, foreground=False,consent=True,resources=True):
    return IdleWindow(now,T+100,0,foreground,consent,resources)


def current_capture(db:sqlite3.Connection):
    new=doc("New independently reviewed mechanical physics and events.",T+700)
    reviewed(db,new)
    return AcquiredArticle(snap(T+719),new)


def activate(host:DragonIdleHostControl, grant):
    return host.activate(consent_id=grant.consent_id,task_topics=TOPICS,
                         adjacent_topics=ADJACENT,at=T+500,authorized=True)


def test_requires_durable_scoped_consent_before_any_work():
    db,bridge,family,host,grant=make()
    offered=[]
    with pytest.raises(PermissionError,match="opted in"):
        host.tick(authorized=True,host_idle_state=idle,
                  article_capture=lambda task:offered.append(task))
    with pytest.raises(PermissionError,match="scope"):
        host.activate(consent_id=grant.consent_id,
            task_topics=("game_ai",),at=T+500,authorized=True)
    with pytest.raises(PermissionError,match="authenticated"):
        host.activate(consent_id=grant.consent_id,
            task_topics=TOPICS,adjacent_topics=ADJACENT,
            at=T+500,authorized=False)
    assert offered==[]
    assert activate(host,grant)["active"]
    assert host.status(at=T+520,authorized=True)["host_idle_now"] is None
    assert host.status(at=T+520,authorized=True)["schema"]==SCHEMA
    with pytest.raises(PermissionError):
        host.status(at=T+520,authorized=False)
    db.close()


def test_trusted_idle_tick_acquires_exact_reviewed_article_once_with_budget():
    db,bridge,family,host,grant=make()
    activate(host,grant)
    item=current_capture(db)
    called=[]
    result=host.tick(authorized=True,host_idle_state=idle,
        article_capture=lambda task:(called.append(task.source_id) or item))
    assert result["attempted"]==1
    assert result["changed"]==1
    assert called==[SRC]
    assert family.snapshot(OWNER,authorized=True)["children"][0]["discoveries"]==1
    status=host.status(at=T+721,authorized=True)
    assert status["daily_attempts"]==1
    assert status["daily_by_specialist"]=={"article":1}
    assert status["next_tick_at"] is not None
    with pytest.raises(PermissionError,match="tick rate"):
        host.tick(authorized=True,host_idle_state=idle,
                  article_capture=lambda task:pytest.fail("unexpected second fetch"))
    db.close()


def test_stopping_while_capture_is_inflight_discards_reviewed_result():
    db,bridge,family,host,grant=make()
    activate(host,grant)
    item=current_capture(db)
    def consent_cancelled(task):
        host.stop(at=T+720,authorized=True)
        return item
    report=host.tick(authorized=True,host_idle_state=idle,
        article_capture=consent_cancelled)
    assert report["paused"] is True
    assert report["changed"]==0
    assert family.snapshot(OWNER,authorized=True)["children"][0]["discoveries"]==0
    assert host.status(at=T+721,authorized=True)["active"] is False
    with pytest.raises(PermissionError,match="opted in"):
        host.tick(authorized=True,host_idle_state=idle,
                  article_capture=lambda task:pytest.fail("unexpected dispatch"))
    db.close()


def test_revoked_consent_blocks_delivery_after_fetch_even_while_idle():
    db,bridge,family,host,grant=make()
    activate(host,grant)
    item=current_capture(db)
    def revoke_during_fetch(task):
        host.consent.revoke(OWNER,grant.consent_id,now=T+718,authorized=True)
        return item
    result=host.tick(authorized=True,host_idle_state=idle,
        article_capture=revoke_during_fetch)
    assert result["changed"]==0
    assert result["paused"] is True
    assert host.status(at=T+721,authorized=True)["active"] is False
    assert family.snapshot(OWNER,authorized=True)["children"][0]["discoveries"]==0
    db.close()


def test_foreground_event_interrupts_acquisition_without_growth():
    db,bridge,family,host,grant=make()
    activate(host,grant)
    item=current_capture(db)
    call=[0]
    def state():
        call[0]+=1
        return idle(foreground=call[0]>=3)
    report=host.tick(authorized=True,host_idle_state=state,
                     article_capture=lambda task:item)
    assert report["paused"] is True and report["changed"]==0
    assert family.snapshot(OWNER,authorized=True)["children"][0]["discoveries"]==0
    db.close()


def test_quota_is_charged_with_atomic_lease_and_stops_second_specialist():
    db,bridge,family,host,grant=make(quota=1)
    activate(host,grant)
    token=host.acquisition.coordinator._reserve(OWNER,"article",SRC,T+720)
    assert isinstance(token,str) and token
    assert host.status(at=T+720,authorized=True)["daily_attempts"]==1
    with pytest.raises(PermissionError,match="daily idle acquisition quota"):
        host.acquisition.coordinator._reserve(OWNER,"monitor",SRC,T+721)
    row=db.execute("""SELECT started FROM dragon_family_idle_daily_usage
        WHERE owner=?""",(OWNER,)).fetchall()
    assert row==[(1,)]
    assert not db.execute("""SELECT 1 FROM dragon_family_idle_leases
        WHERE owner=? AND role='monitor'""",(OWNER,)).fetchone()
    db.close()


def test_restarted_host_preserves_opt_in_and_durable_budget(tmp_path):
    path=tmp_path/"dragon-idle.sqlite3"
    db=sqlite3.connect(path)
    db,bridge,family,host,grant=make(db)
    activate(host,grant)
    host.acquisition.coordinator._reserve(OWNER,"article",SRC,T+720)
    db.close()
    db2=sqlite3.connect(path)
    restored=DragonIdleHostControl(DragonFamilyCustodyBridge(db2,OWNER))
    state=restored.status(at=T+721,authorized=True)
    assert state["active"] is True
    assert state["daily_attempts"]==1
    stopped=restored.stop(at=T+725,authorized=True)
    assert stopped["active"] is False
    db2.close()


def test_policy_fences_and_lifetime_are_bounded():
    for options in ({"max_daily_attempts":1001},
                    {"max_daily_attempts":2,"max_daily_per_role":3},
                    {"min_seconds_between_ticks":2},
                    {"max_consent_lifetime_seconds":10}):
        with pytest.raises(ValueError):
            DragonIdleHostPolicy(**options).validate()
    assert idle_consent_scope(OWNER,TOPICS,ADJACENT)==idle_consent_scope(
        OWNER,tuple(reversed(TOPICS)),ADJACENT)
    with pytest.raises(ValueError):
        idle_consent_scope(OWNER,(),())
    with pytest.raises(ValueError):
        idle_consent_scope(OWNER,TOPICS,TOPICS)
    db,bridge,family,host,grant=make(lifetime=35*86400)
    with pytest.raises(PermissionError,match="lifetime"):
        activate(host,grant)
    db.close()
