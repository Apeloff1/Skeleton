"""Durable native exercise progression: actual different source, no XP farming."""
from __future__ import annotations
from hashlib import sha256
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_practice_lab import ApprovedLesson, DragonPracticeLab
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic


def approved(owner="alice"):
    proof=PromotionDecision("claim-arcade",True,.99,"calibrated",None,(),
                            sha256(b"genuine review digest").hexdigest())
    return ApprovedLesson(owner,"Original Native Dragon Adventure",proof,
                          "a"*64,(Mechanic.MOVEMENT,Mechanic.EXPLORATION),True)


def test_eight_real_distinct_variants_no_xp_inflation(tmp_path):
    db=sqlite3.connect(tmp_path/"practice.sqlite")
    parent=DragonPracticeLab(db)
    parent.offer(approved(),authorized=True,now=1)
    native=DragonNativePracticeLab(db,parent)
    rows=[]
    for i in range(8):
        item=native.generate("alice",target_id="game_boy",
                             style="arcade_score_attack",now=i+3,
                             authorized=True,consent=True)
        rows.append(item)
    assert [a.variant for a in rows]==list(range(8))
    assert len({a.source_digest for a in rows})==8
    assert len({native.project("alice",a.attempt_id,authorized=True)["project_id"]
                for a in rows})==8
    assert len(native.list("alice",authorized=True))==8
    assert parent.progress("alice",authorized=True).xp==30
    with pytest.raises(ValueError,match="variants exhausted"):
        native.generate("alice",target_id="game_boy",style="arcade_score_attack",
                        now=13,authorized=True,consent=True)
    db.close()
    db=sqlite3.connect(tmp_path/"practice.sqlite")
    parent=DragonPracticeLab(db)
    native=DragonNativePracticeLab(db,parent)
    assert len(native.list("alice",authorized=True))==8
    assert native.archive("alice",rows[0].attempt_id,authorized=True)[0]==(
        native.archive("alice",rows[0].attempt_id,authorized=True)[0])
    assert parent.progress("alice",authorized=True).xp==30


def test_migrates_first_generation_native_table_preserves_original_artifacts(tmp_path):
    db=sqlite3.connect(tmp_path/"old.sqlite")
    parent=DragonPracticeLab(db)
    parent.offer(approved(),authorized=True,now=1)
    db.execute("""CREATE TABLE dragon_native_game_attempts(
        owner TEXT NOT NULL,attempt_id TEXT NOT NULL,lesson_id TEXT NOT NULL,
        target_id TEXT NOT NULL,style TEXT NOT NULL,state TEXT NOT NULL,
        source_digest TEXT NOT NULL,project_json TEXT NOT NULL,
        created_at REAL NOT NULL,review_digest TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(owner,attempt_id),
        UNIQUE(owner,lesson_id,target_id,style))""")
    db.commit()
    native=DragonNativePracticeLab(db,parent)
    assert "variant" in {r[1] for r in db.execute(
        "PRAGMA table_info(dragon_native_game_attempts)")}
    item=native.generate("alice",target_id="nes",style="arcade_score_attack",
                         now=10,authorized=True,consent=True)
    assert item.variant==0
    assert native.project("alice",item.attempt_id,authorized=True)["files"]


def test_opt_out_and_owner_isolation_hold_under_variants():
    db=sqlite3.connect(":memory:")
    parent=DragonPracticeLab(db)
    parent.offer(approved(),authorized=True,now=1)
    native=DragonNativePracticeLab(db,parent)
    first=native.generate("alice",target_id="game_boy",
                          style="arcade_score_attack",now=10,
                          authorized=True,consent=True)
    assert native.list("bob",authorized=True)==()
    with pytest.raises(LookupError):
        native.project("bob",first.attempt_id,authorized=True)
    parent.revoke("alice",authorized=True)
    with pytest.raises(PermissionError):
        native.generate("alice",target_id="game_boy",
                        style="arcade_score_attack",now=11,
                        authorized=True,consent=True)
    # Revoking new generation does not destroy audit/archive of past sources.
    assert native.project("alice",first.attempt_id,authorized=True)["target_id"]=="game_boy"
