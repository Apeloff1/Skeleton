"""No-network research timing from independently approved Dragon revisions."""
from __future__ import annotations

import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_family import (
    DragonFamily,SourceSeed,SourceReceipt,IdleWindow,
)
from skeleton.ai.webcrawler.dragon_family_idle_coordinator import DragonIdleCoordinator
from skeleton.ai.webcrawler.dragon_family_recrawl_planner import (
    DragonFamilyRecrawlPlanner,DragonRecrawlPolicy,
)

OWNER="recrawl-studio"
NOW=1800000000.
APPROVED="a"*64
BASE="1"*64
NEW="2"*64


def fixture():
    db=sqlite3.connect(":memory:")
    trust={"active":True}
    def approval(p):
        return trust["active"] and p.review_digest==APPROVED
    family=DragonFamily(db,owner_scope=OWNER,approval=approval)
    family.enroll(OWNER,(
        SourceSeed("alpha","https://example.org/a","article",("game_engine",)),
        SourceSeed("beta","https://example.net/b","article",("game_engine",)),
        SourceSeed("off-topic","https://example.com/x","video",("cooking",)),
    ),authorized=True,now=NOW)
    family.seal_inventory(OWNER,authorized=True,now=NOW+1)
    for i,sid in enumerate(("alpha","beta","off-topic")):
        family.consume(OWNER,SourceReceipt(sid,BASE,APPROVED,NOW+2+i),
                       authorized=True)
    DragonIdleCoordinator(family)
    return db,family,trust


def test_read_only_recrawl_plan_uses_only_reviewed_task_relevant_source_data():
    db,family,trust=fixture()
    planner=DragonFamilyRecrawlPlanner(family)
    prior=db.total_changes
    early=planner.plan(OWNER,authorized=True,at=NOW+720,
        task_topics=("game_engine",))
    assert early["schema"]=="skeleton.ai.dragon.recrawl_plan.v1"
    assert early["reviewed_sources"]==2
    assert early["due_sources"]==0
    assert early["no_network_authority"] and early["uncalibrated_volatility"]
    assert [s["source_id"] for s in early["items"]]==["alpha","beta"]
    assert db.total_changes==prior, "planning cannot mutate source or consent ledgers"
    later=planner.plan(OWNER,authorized=True,at=NOW+86400,
        task_topics=("game_engine",))
    assert later["due_sources"]==2
    assert all(p["due"] for p in later["items"])
    db.close()


def test_verified_revision_influences_volatility_but_not_model_probability():
    db,family,trust=fixture()
    family.digest_idle(OWNER,"article",SourceReceipt(
        "alpha",NEW,APPROVED,NOW+719,"new validated input mechanic"),
        authorized=True,window=IdleWindow(NOW+720,NOW+100,0,False,True),
        task_topics=("game_engine",))
    planner=DragonFamilyRecrawlPlanner(family)
    report=planner.plan(OWNER,authorized=True,at=NOW+2*86400,
        task_topics=("game_engine",))
    by_id={x["source_id"]:x for x in report["items"]}
    assert by_id["alpha"]["reviewed_revisions"]==2
    assert by_id["beta"]["reviewed_revisions"]==1
    assert by_id["alpha"]["volatility_index"]>by_id["beta"]["volatility_index"]
    assert report["uncalibrated_volatility"] is True
    trust["active"]=False
    revoked=planner.plan(OWNER,authorized=True,at=NOW+2*86400,
        task_topics=("game_engine",))
    assert revoked["reviewed_sources"]==0
    db.close()


def test_policy_blocked_source_is_omitted_and_no_cross_owner_read():
    db,family,trust=fixture()
    coordinator=DragonIdleCoordinator(family)
    token=coordinator._reserve(OWNER,"article","alpha",NOW+720)
    assert token is not None
    coordinator._finish(OWNER,"article","alpha",token,NOW+721,
                        "policy_blocked")
    plan=DragonFamilyRecrawlPlanner(family).plan(
        OWNER,authorized=True,at=NOW+2*86400,task_topics=("game_engine",))
    assert [x["source_id"] for x in plan["items"]]==["beta"]
    with pytest.raises(PermissionError):
        DragonFamilyRecrawlPlanner(family).plan(
            "wrong-owner",authorized=True,at=NOW+720,task_topics=("game_engine",))
    with pytest.raises(PermissionError):
        DragonFamilyRecrawlPlanner(family).plan(
            OWNER,authorized=False,at=NOW+720,task_topics=("game_engine",))
    db.close()


def test_bounded_host_planner_refuses_forged_weights_and_input():
    for p in (DragonRecrawlPolicy(minimum_interval_seconds=10),
              DragonRecrawlPolicy(max_source_scan=100000),
              DragonRecrawlPolicy(minimum_interval_seconds=10000,
                                  maximum_interval_seconds=3600)):
        with pytest.raises(ValueError):
            p.validate()
    db,family,trust=fixture()
    with pytest.raises(ValueError):
        DragonFamilyRecrawlPlanner(family).plan(
            OWNER,authorized=True,at=NOW+720,task_topics=())
    with pytest.raises(PermissionError):
        DragonFamilyRecrawlPlanner(DragonFamily(db,approval=lambda r:True))
    db.close()
