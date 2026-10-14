"""Finite native console cadence and migration coverage."""
from hashlib import sha256
import sqlite3
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab,ApprovedLesson
from skeleton.ai.webcrawler.dragon_practice_cycles import DragonPracticeCycles
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision


def _offer(lab,owner="alice"):
    p=PromotionDecision("native-study",True,.99,"calibrated",None,(),
                        sha256(b"native-study").hexdigest())
    lab.offer(ApprovedLesson(owner,"Native design lesson",p,"a"*64,
        (Mechanic.MOVEMENT,Mechanic.EXPLORATION),True),
        authorized=True,now=1)

def test_native_cycles_create_native_source_not_browser_html():
    db=sqlite3.connect(":memory:")
    lab=DragonPracticeLab(db)
    _offer(lab)
    cycles=DragonPracticeCycles(db,lab)
    cycles.enable("alice",authorized=True,human_approved=True,now=2,
        expires_at=2000,interval_seconds=300,max_ticks=3,demos_per_tick=2,
        generation_mode="native",native_target="game_boy")
    assert cycles.status("alice",authorized=True).generation_mode=="native"
    one=cycles.pulse("alice",authorized=True,now=2)
    assert len(one)==2
    assert one[0].target_id=="game_boy"
    assert one[0].state=="source_generated"
    assert {x.variant for x in one}=={0,1}
    assert len({x.source_digest for x in one})==2
    assert {x.style for x in one}=={"arcade_score_attack"}
    assert lab.attempts("alice",authorized=True)==()
    assert len(cycles.pulse("alice",authorized=True,now=302))==2
    assert lab.progress("alice",authorized=True).xp==30
    assert not cycles.pulse("alice",authorized=True,now=303)

def test_old_html_cycle_schema_migrates_without_losing_consent_or_ticks():
    db=sqlite3.connect(":memory:")
    lab=DragonPracticeLab(db)
    db.execute("""CREATE TABLE dragon_practice_cycles(
        owner TEXT PRIMARY KEY,enabled INTEGER,expires_at REAL,next_due REAL,
        interval_seconds INTEGER,remaining_ticks INTEGER,demos_per_tick INTEGER)""")
    db.execute("INSERT INTO dragon_practice_cycles VALUES('alice',1,700,0,300,2,1)")
    db.commit()
    cycles=DragonPracticeCycles(db,lab)
    state=cycles.status("alice",authorized=True)
    assert state.enabled
    assert state.generation_mode=="html"
    assert state.remaining_ticks==2
    _offer(lab)
    assert len(cycles.pulse("alice",authorized=True,now=2))==1
