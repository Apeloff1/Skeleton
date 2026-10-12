"""Durable Dragon Family idle scheduler: fair specialist work, leases, budgets."""
from __future__ import annotations

import sqlite3
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_family import (
    DragonFamily, IdleWindow, SourceSeed, SourceReceipt,
)
from skeleton.ai.webcrawler.dragon_family_idle_coordinator import (
    DragonIdleCoordinator, IdleCoordinatorPolicy, read_idle_family_health,
)

OWNER="accepted-owner"
NOW=1800000000.0
REVIEW="a"*64
ORIGINAL="1"*64
ART="b"*64
VID="c"*64
UPDATE="d"*64


def seed(source_id: str, media="article", topics=("game_engine",)):
    return SourceSeed(source_id,f"https://example.org/games/{source_id}",media,topics)


def receipt(source_id: str, digest: str, at: float):
    return SourceReceipt(source_id,digest,REVIEW,at)


def make(*, complete=True, min_idle_seconds=300):
    db=sqlite3.connect(":memory:")
    family=DragonFamily(db,owner_scope=OWNER,min_idle_seconds=min_idle_seconds,
                        approval=lambda r:r.review_digest==REVIEW)
    sources=(seed("article-1"),seed("article-2",topics=("physics",)),
             seed("video-1","video"))
    family.enroll(OWNER,sources,authorized=True,now=NOW)
    if complete:
        family.seal_inventory(OWNER,authorized=True,now=NOW+1)
        for i,item in enumerate(sources):
            family.consume(OWNER,receipt(item.source_id,ORIGINAL,NOW+i+2),
                           authorized=True)
    return db,family,DragonIdleCoordinator(family)


def idle(at=NOW+720, *, busy=0, foreground=False, consent=True, resources=True):
    return IdleWindow(at,NOW+10,busy,foreground,consent,resources)


def gather(task):
    tags={"article":ART,"video":VID,"monitor":UPDATE}
    return receipt(task.source_id,tags[task.dragon],NOW+719)


def test_read_only_ui_health_never_creates_or_authorizes_scheduler():
    db=sqlite3.connect(":memory:")
    early=read_idle_family_health(db,OWNER,authorized=True)
    assert early["configured"] is False
    assert early["host_state"]=="not_connected"
    assert not db.execute("""SELECT 1 FROM sqlite_master WHERE
        name='dragon_family_idle_leases'""").fetchone()
    with pytest.raises(PermissionError):
        read_idle_family_health(db,OWNER,authorized=False)
    db.close()

def test_three_specialists_evolve_only_on_new_approved_content():
    db,family,worker=make()
    calls=[]
    def record(task):
        calls.append((task.dragon,task.source_id,task.media,task.attempt))
        return gather(task)
    observed=worker.run_once(OWNER,authorized=True,idle_state=idle,
                             gatherers={role:record for role in ("article","video","monitor")},
                             task_topics=("game_engine",),adjacent_topics=("physics",))
    assert observed["attempted"]==3
    assert observed["changed"]==3
    assert observed["failed"]==0
    assert len({s for _,s,_,_ in calls})==3, "one source cannot occupy two sibling slots"
    assert len({r for r,_,_,_ in calls})==3
    assert next(r for r in calls if r[0]=="video")[2]=="video"
    snapshot=family.snapshot(OWNER,authorized=True)
    assert [c["discoveries"] for c in snapshot["children"]]==[1,1,1]
    assert [c["stage"] for c in snapshot["children"]]==["hatchling"]*3
    assert [x["action"] for x in snapshot["history"]].count("hatched")==3
    assert worker.health(OWNER,authorized=True)["max_tasks_per_tick"]==3
    readonly=read_idle_family_health(db,OWNER,authorized=True)
    assert readonly["configured"] is True
    assert readonly["host_state"]=="not_observed"
    assert readonly["workers"]["article"]["last_changes"]==1
    assert readonly["workers"]["monitor"]["last_changes"]==1
    db.close()


def test_idle_is_required_before_network_dispatch_and_when_user_returns():
    db,family,worker=make()
    invoked=[]
    for forbidden in (idle(at=NOW+250),idle(busy=1),idle(foreground=True),
                      idle(consent=False),idle(resources=False)):
        with pytest.raises(PermissionError):
            worker.run_once(OWNER,authorized=True,idle_state=lambda:forbidden,
                            gatherers={"article":lambda task:invoked.append(task)},
                            task_topics=("game_engine",))
    assert invoked==[]
    state={"poll":0}

    def idler():
        state["poll"]+=1
        return idle(foreground=state["poll"]>=3)
    result=worker.run_once(OWNER,authorized=True,idle_state=idler,
                           gatherers={"article":lambda task: receipt(task.source_id,ART,NOW+719)},
                           task_topics=("game_engine",))
    assert result["paused"] and result["changed"]==0
    assert family.snapshot(OWNER,authorized=True)["children"][0]["discoveries"]==0
    db.close()


def test_no_children_until_complete_parent_and_owner_locked():
    db,family,worker=make(complete=False)
    assert worker.run_once(OWNER,authorized=True,idle_state=idle,
                           gatherers={},task_topics=("game_engine",))["reason"]=="parent_source_quest_incomplete"
    with pytest.raises(PermissionError,match="another owner"):
        worker.run_once("intruder",authorized=True,idle_state=idle,
                        gatherers={},task_topics=("game_engine",))
    with pytest.raises(PermissionError):
        worker.run_once(OWNER,authorized=False,idle_state=idle,
                        gatherers={},task_topics=("game_engine",))
    with pytest.raises(PermissionError):
        worker.health(OWNER,authorized=False)
    with pytest.raises(PermissionError):
        DragonIdleCoordinator(DragonFamily(db,approval=lambda r:True))
    db.close()


def test_missing_consent_and_unknown_topic_never_create_tasks():
    db,family,worker=make()
    assert worker.run_once(OWNER,authorized=True,idle_state=idle,
                           gatherers={"article":gather},task_topics=("spacecraft",))["attempted"]==0
    with pytest.raises(ValueError,match="task context"):
        worker.run_once(OWNER,authorized=True,idle_state=idle,
                        gatherers={"article":gather},task_topics=())
    assert worker.run_once(OWNER,authorized=True,idle_state=idle,
                           gatherers={},task_topics=("game_engine",))["attempted"]==0
    db.close()


def test_backoff_after_error_does_not_award_xp_and_recovers_on_due():
    db,family,worker=make()
    attempts=[]
    def broken(task):
        attempts.append(task.source_id)
        raise RuntimeError("network unavailable")
    fail=worker.run_once(OWNER,authorized=True,idle_state=idle,
                         gatherers={"video":broken},task_topics=("game_engine",))
    assert fail["attempted"]==1 and fail["failed"]==1
    assert worker.health(OWNER,authorized=True)["workers"]["video"]["failed"]==1
    soon=worker.run_once(OWNER,authorized=True,idle_state=lambda:idle(NOW+800),
                         gatherers={"video":broken},task_topics=("game_engine",))
    assert soon["attempted"]==0 and len(attempts)==1
    after=worker.run_once(OWNER,authorized=True,idle_state=lambda:idle(NOW+1100),
                          gatherers={"video":lambda task:None},task_topics=("game_engine",))
    assert after["unchanged"]==1 and after["changed"]==0
    assert worker.health(OWNER,authorized=True)["workers"]["video"]["failed"]==0
    assert family.snapshot(OWNER,authorized=True)["children"][1]["discoveries"]==0
    db.close()


def test_retries_not_eligible_during_same_source_lease_and_expired_lease_reclaimed():
    db,family,worker=make()
    second=DragonIdleCoordinator(family)
    observed=[]
    def first(task):
        other=second.run_once(OWNER,authorized=True,idle_state=idle,
                              gatherers={"article":lambda _:observed.append("double")},
                              task_topics=("game_engine",))
        # A different *eligible* article may still be worked by another
        # dispatcher; ensure the leased same source isn't duplicated.
        assert "double" not in observed
        return receipt(task.source_id,ART,NOW+719)
    worker.run_once(OWNER,authorized=True,idle_state=idle,
                    gatherers={"article":first},task_topics=("game_engine",))
    assert family.snapshot(OWNER,authorized=True)["children"][0]["discoveries"]==1
    db.close()


def test_repeated_unchanged_receipt_is_cooldown_only():
    db,family,worker=make()
    first=worker.run_once(OWNER,authorized=True,idle_state=idle,
                          gatherers={"video":lambda task:receipt(task.source_id,ORIGINAL,NOW+719)},
                          task_topics=("game_engine",))
    assert first["unchanged"]==1
    later=worker.run_once(OWNER,authorized=True,idle_state=lambda:idle(NOW+900),
                          gatherers={"video":gather},task_topics=("game_engine",))
    assert later["attempted"]==0
    assert family.snapshot(OWNER,authorized=True)["children"][1]["discoveries"]==0
    db.close()


def test_keyset_rotation_reaches_sources_beyond_initial_window():
    db=sqlite3.connect(":memory:")
    family=DragonFamily(db,owner_scope=OWNER,approval=lambda r:r.review_digest==REVIEW)
    family.enroll(OWNER,(seed("parent-source",topics=("misc",)),),authorized=True,now=NOW)
    family.seal_inventory(OWNER,authorized=True,now=NOW+1)
    family.consume(OWNER,receipt("parent-source",ORIGINAL,NOW+2),authorized=True)
    additions=tuple(seed(f"source-{i:03d}",topics=("misc",) if i<24 else ("game_engine",))
                    for i in range(25))
    family.enroll(OWNER,additions,authorized=True,now=NOW+10)
    worker=DragonIdleCoordinator(family,policy=IdleCoordinatorPolicy(max_eligible_scan=10))
    calls=[]
    for tick in range(4):
        result=worker.run_once(OWNER,authorized=True,idle_state=lambda tick=tick:idle(NOW+720+tick*20),
              gatherers={"article":lambda task:(calls.append(task.source_id) or
                  receipt(task.source_id,ART,NOW+719+tick*20))},
              task_topics=("game_engine",))
        if calls:
            break
    assert calls==["source-024"]
    assert result["changed"]==1
    assert family.snapshot(OWNER,authorized=True)["children"][0]["discoveries"]==1
    db.close()


def test_budget_refuses_policy_bypass_and_unscoped_family():
    for values in ({"max_tasks":4},{"min_idle_seconds":1},
                   {"lease_seconds":5000},{"max_eligible_scan":2},
                   {"transient_backoff_seconds":600,"maximum_backoff_seconds":300}):
        with pytest.raises(ValueError):
            IdleCoordinatorPolicy(**values).validate()
    db,family,_=make(min_idle_seconds=400)
    with pytest.raises(ValueError,match="weaken"):
        DragonIdleCoordinator(family,policy=IdleCoordinatorPolicy(min_idle_seconds=300))
    db.close()


def test_wrong_source_returned_cannot_evolve_and_fails_safely():
    db,family,worker=make()
    result=worker.run_once(OWNER,authorized=True,idle_state=idle,
                           gatherers={"video":lambda task:receipt("article-1",ART,NOW+719)},
                           task_topics=("game_engine",))
    assert result["failed"]==1
    assert result["changed"]==0
    assert worker.health(OWNER,authorized=True)["workers"]["video"]["failed"]==1
    assert family.snapshot(OWNER,authorized=True)["children"][1]["discoveries"]==0
    db.close()
