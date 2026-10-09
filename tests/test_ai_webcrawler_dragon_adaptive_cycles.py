"""Finite adaptive native practice keeps real consent, budgets and no XP farming."""
from __future__ import annotations
from hashlib import sha256
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_practice_lab import ApprovedLesson,DragonPracticeLab
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_practice_cycles import DragonPracticeCycles


def _lesson(owner="alice"):
    receipt=PromotionDecision("claim",True,.98,"calibrated",None,(),
                              sha256(b"approved learning").hexdigest())
    return ApprovedLesson(owner,"Game Boy programming",receipt,"a"*64,
                          (Mechanic.MOVEMENT,Mechanic.EXPLORATION),True)

def test_opt_in_curriculum_scheduler_selects_truthful_bounded_native_games(
    tmp_path,monkeypatch,
):
    monkeypatch.delenv("SKL_DRAGON_BUILD_SIGNING_KEY_HEX",raising=False)
    db=sqlite3.connect(tmp_path/"native.sqlite")
    lab=DragonPracticeLab(db)
    lab.offer(_lesson(),authorized=True,now=1)
    cycles=DragonPracticeCycles(db,lab)
    with pytest.raises(PermissionError):
        cycles.enable("alice",authorized=True,human_approved=False,
                      now=10,expires_at=900,generation_mode="curriculum")
    schedule=cycles.enable(
        "alice",authorized=True,human_approved=True,now=10,expires_at=900,
        interval_seconds=300,max_ticks=2,demos_per_tick=2,
        generation_mode="curriculum")
    assert schedule.generation_mode=="curriculum"
    a=cycles.pulse("alice",authorized=True,now=10)
    assert len(a)==2
    assert all(x.target_id=="game_boy" for x in a)
    assert all(x.style=="arcade_score_attack" for x in a)
    assert {x.variant for x in a}=={0,1}
    assert cycles.pulse("alice",authorized=True,now=11)==()
    b=cycles.pulse("alice",authorized=True,now=310)
    assert len(b)==2
    assert {x.variant for x in b}=={2,3}
    assert cycles.status("alice",authorized=True).remaining_ticks==0
    assert cycles.pulse("alice",authorized=True,now=610)==()
    assert lab.progress("alice",authorized=True).xp==30
    assert len(DragonNativePracticeLab(db,lab).list("alice",authorized=True))==4

def test_adaptive_subscription_can_be_revoked_before_next_tick():
    db=sqlite3.connect(":memory:")
    parent=DragonPracticeLab(db)
    parent.offer(_lesson(),authorized=True,now=1)
    cycles=DragonPracticeCycles(db,parent)
    cycles.enable("alice",authorized=True,human_approved=True,now=10,
                  expires_at=350,interval_seconds=300,max_ticks=2,
                  generation_mode="curriculum")
    assert cycles.pulse("alice",authorized=True,now=10)
    cycles.disable("alice",authorized=True)
    assert cycles.pulse("alice",authorized=True,now=310)==()
    assert cycles.status("alice",authorized=True).enabled is False
