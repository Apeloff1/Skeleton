"""Durable signed post-ending story continuity, owner isolation and save conflicts."""
from __future__ import annotations
from dataclasses import replace
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_living_world import (
    create_world,initial_state,replay,
)
from skeleton.ai.webcrawler.dragon_living_world_store import (
    SCHEMA,store,restore,list_saves,
)
from skeleton.ai.webcrawler.dragon_living_world_checkpoint import (
    SECRET_SETTING,TTL_SECONDS,open_checkpoint,
)

OWNER="a"*64
OTHER="b"*64
SECRET="original-world-sqlite-store-hmac-validation-secret-2026-10-11"


@pytest.fixture(autouse=True)
def configure_key(monkeypatch):
    monkeypatch.setenv(SECRET_SETTING,SECRET)


def test_real_sqlite_world_save_survives_expired_session_token_and_reissues_valid_continuation():
    world=create_world(world_id=17,style="open_world_story")
    prior=replay(world,("help_settlers","help_settlers",
                        "ending_civic_union","observe","forage"))
    with sqlite3.connect(":memory:") as db:
        receipt=store(db,world,prior,OWNER,0,now=1_800_000_000)
        assert receipt["status"]=="durably_saved_original_game_state"
        assert receipt["version"]==1
        assert receipt["continues_after_ending"]
        restored=restore(db,world,OWNER,0,now=1_800_000_000+TTL_SECONDS*4)
        assert restored["state"]["endings_seen"]==["civic_union"]
        assert restored["state"]["era"]==1
        assert restored["history_digest"]==prior.history_digest
        resumed=open_checkpoint(world,restored["new_checkpoint"],OWNER,
                                now=1_800_000_000+TTL_SECONDS*4+1)
        assert resumed==prior
        assert list_saves(db,OWNER)==({
            "slot":0,"world_fingerprint":world.world_fingerprint,
            "version":1,"updated_at":1_800_000_000,
        },)


def test_save_overwrite_requires_explicit_authorization_and_expected_latest_history():
    world=create_world(world_id=10,style="survival_sandbox")
    original=replay(world,("forage","mine"))
    advanced=replay(world,("forage","mine","build"))
    with sqlite3.connect(":memory:") as db:
        first=store(db,world,original,OWNER,3,now=1_800_000_000)
        with pytest.raises(FileExistsError):
            store(db,world,advanced,OWNER,3,now=1_800_000_001)
        with pytest.raises(FileExistsError):
            store(db,world,advanced,OWNER,3,replace_existing=True,
                  expected_digest="0"*64,now=1_800_000_001)
        second=store(db,world,advanced,OWNER,3,replace_existing=True,
                     expected_digest=original.history_digest,now=1_800_000_002)
        assert second["version"]==first["version"]+1
        assert restore(db,world,OWNER,3,now=1_800_000_003)[
            "history_digest"]==advanced.history_digest


def test_tampered_db_state_is_detected_before_reissuing_a_new_session():
    world=create_world(world_id=9,style="open_world_story")
    current=replay(world,("help_settlers","help_settlers",
                          "ending_civic_union"))
    with sqlite3.connect(":memory:") as db:
        store(db,world,current,OWNER,2,now=1_800_000_000)
        db.execute(
            "UPDATE dragon_original_living_world_save_v1 SET "
            "document=? WHERE owner=? AND slot=?",
            (b'{"player":{"endings_seen":["civic_union"],"wood":999}}',OWNER,2),
        )
        db.commit()
        with pytest.raises(PermissionError):
            restore(db,world,OWNER,2,now=1_800_000_001)


def test_durable_world_saves_are_isolated_across_tenants_and_across_source_worlds():
    world=create_world(world_id=30,style="creative_sandbox")
    changed=create_world(world_id=31,style="creative_sandbox")
    with sqlite3.connect(":memory:") as db:
        store(db,world,initial_state(world),OWNER,1,now=1_800_000_000)
        assert list_saves(db,OTHER)==()
        with pytest.raises(FileNotFoundError):
            restore(db,world,OTHER,1,now=1_800_000_001)
        with pytest.raises(PermissionError):
            restore(db,changed,OWNER,1,now=1_800_000_001)


def test_ten_save_slots_are_bounded_and_cannot_overwrite_another_world_silently():
    a=create_world(world_id=101,style="mutable_labyrinth")
    b=create_world(world_id=102,style="mutable_labyrinth")
    with sqlite3.connect(":memory:") as db:
        for slot in range(10):
            store(db,a,initial_state(a),OWNER,slot,now=1_800_000_000)
        assert len(list_saves(db,OWNER))==10
        with pytest.raises(PermissionError):
            store(db,b,initial_state(b),OWNER,0,
                  replace_existing=True,
                  expected_digest=initial_state(a).history_digest,
                  now=1_800_000_001)
        with pytest.raises(ValueError):
            store(db,a,initial_state(a),OWNER,10,now=1_800_000_001)
        with pytest.raises(ValueError):
            restore(db,a,OWNER,-1,now=1_800_000_001)


def test_save_does_not_work_without_server_managed_signing_secret(monkeypatch):
    world=create_world(world_id=0)
    monkeypatch.delenv(SECRET_SETTING,raising=False)
    with sqlite3.connect(":memory:") as db:
        with pytest.raises(RuntimeError):
            store(db,world,initial_state(world),OWNER,0)


def test_source_history_writes_can_continue_after_world_already_completed():
    world=create_world(world_id=72,style="postgame_free_roam")
    opened=replay(world,("help_settlers","help_settlers",
                         "ending_civic_union"))
    later=replay(world,("forage","observe","rest"),starting_state=opened)
    with sqlite3.connect(":memory:") as db:
        previous=store(db,world,opened,OWNER,4,now=1_800_000_000)
        receipt=store(db,world,later,OWNER,4,replace_existing=True,
                      expected_digest=opened.history_digest,now=1_800_000_001)
        assert receipt["version"]==2
        restored=restore(db,world,OWNER,4,now=1_800_000_002)
        assert restored["state"]["era"]==1
        assert restored["state"]["endings_seen"]==["civic_union"]
        assert restored["state"]["actions_played"]==6
        assert restored["history_digest"]==later.history_digest
