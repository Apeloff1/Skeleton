"""Opt-in recurring Dragon game practice with bounded work and revocation."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_practice_cycles import DragonPracticeCycles
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab
from hashlib import sha256
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_practice_lab import ApprovedLesson

def lesson():
    promotion=PromotionDecision("physics", True, 0.99, "calibrated", None, (),
                                sha256(b"physics").hexdigest())
    return ApprovedLesson("alice","Physics practice",promotion,"b"*64,
                          (Mechanic.MOVEMENT,Mechanic.PLATFORMING),True)


def test_authorized_practice_cycle_is_bounded_and_restart_safe():
    db=sqlite3.connect(":memory:")
    lab=DragonPracticeLab(db)
    lab.offer(lesson(),authorized=True,now=0)
    cycles=DragonPracticeCycles(db,lab)
    with pytest.raises(PermissionError):
        cycles.enable("alice",authorized=True,human_approved=False,now=0,expires_at=3000)
    with pytest.raises(ValueError):
        cycles.enable("alice",authorized=True,human_approved=True,now=0,
                      expires_at=8*86400)
    sub=cycles.enable("alice",authorized=True,human_approved=True,now=0,
                      expires_at=3600,interval_seconds=300,max_ticks=3,
                      demos_per_tick=2)
    assert sub.enabled and sub.remaining_ticks==3
    first=cycles.pulse("alice",authorized=True,now=0)
    assert len(first)==2
    assert cycles.pulse("alice",authorized=True,now=0)==()
    assert len(DragonPracticeCycles(db,lab).pulse(
        "alice",authorized=True,now=300))==2
    assert len(cycles.pulse("alice",authorized=True,now=600))==0
    assert not cycles.status("alice",authorized=True).enabled
    assert cycles.pulse("alice",authorized=True,now=900)==()
    assert lab.progress("alice",authorized=True).demo_attempts==4


def test_revocation_and_expiry_stop_generations():
    db=sqlite3.connect(":memory:")
    lab=DragonPracticeLab(db)
    lab.offer(lesson(),authorized=True,now=0)
    cycles=DragonPracticeCycles(db,lab)
    cycles.enable("alice",authorized=True,human_approved=True,now=0,
                  expires_at=900,max_ticks=15,demos_per_tick=1,interval_seconds=300)
    lab.revoke("alice",authorized=True)
    assert cycles.pulse("alice",authorized=True,now=0)==()
    cycles.disable("alice",authorized=True)
    assert cycles.pulse("alice",authorized=True,now=300)==()
    cycles.enable("alice",authorized=True,human_approved=True,now=0,
                  expires_at=900,max_ticks=15,demos_per_tick=1,interval_seconds=300)
    assert cycles.pulse("alice",authorized=True,now=900)==()
    assert not cycles.status("alice",authorized=True).enabled
    with pytest.raises(PermissionError):
        cycles.pulse("alice",authorized=False,now=901)
