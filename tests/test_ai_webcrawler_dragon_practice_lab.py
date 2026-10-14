"""Dragon RPG progression and offline-game practice regression suite."""
import hashlib
import sqlite3

import pytest
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_practice_lab import (
    ApprovedLesson, DragonPracticeLab, PracticePolicy,
)


def decision(claim="physics", eligible=True):
    return PromotionDecision(
        claim_id=claim, eligible=eligible, belief_probability=0.99,
        probability_semantics="calibrated", calibration_artifact_fingerprint=None,
        reasons=() if eligible else ("insufficient corroboration",),
        evidence_digest=hashlib.sha256(claim.encode()).hexdigest(),
    )


def lesson(owner="alice", claim="physics", consent=True, eligible=True):
    return ApprovedLesson(
        owner=owner, title="Gravity and player motion",
        promotion=decision(claim, eligible),
        review_fingerprint="b" * 64,
        observed_mechanics=(Mechanic.MOVEMENT, Mechanic.PHYSICS,
                            Mechanic.PLATFORMING, Mechanic.EXPLORATION),
        practice_consent=consent,
    )


def test_reviewed_lessons_generate_real_offline_artifacts_and_level_up():
    db = sqlite3.connect(":memory:")
    lab = DragonPracticeLab(db)
    identity = lab.offer(lesson(), now=10, authorized=True)
    assert identity == lab.offer(lesson(), now=11, authorized=True)
    revised=ApprovedLesson("alice","New reviewed title",decision(),"c"*64,
        (Mechanic.PHYSICS,),True)
    assert identity==lab.offer(revised,now=12,authorized=True)  # no XP farming
    initial = lab.progress("alice", authorized=True)
    assert initial.verified_lessons == 1
    assert initial.level == 1 and initial.xp == 30
    built = lab.run_batch("alice", authorized=True, consent=True, now=100,
                          max_demos=4)
    assert len(built) == 4
    assert len({a.kind for a in built}) == 4
    assert all(a.state == "built" and len(a.artifact_digest) == 64 for a in built)
    for a in built:
        html = lab.artifact("alice", a.attempt_id, authorized=True)
        assert "<canvas" in html and "requestAnimationFrame" in html
        assert "connect-src 'none'" in html
        assert "<iframe" not in html and "fetch(" not in html
        assert hashlib.sha256(html.encode()).hexdigest() == a.artifact_digest
    after_build=lab.progress("alice", authorized=True)
    assert after_build.demos_built == 4 and after_build.demos_reviewed == 0
    assert after_build.xp == initial.xp  # builds are attempts, not mastery
    assert lab.review("alice", built[0].attempt_id, authorized=True,
                      playtested=True,accepted=True,playtest_digest="c"*64)
    assert not lab.review("alice", built[0].attempt_id, authorized=True,
                          playtested=True,accepted=True,playtest_digest="c"*64)
    claimed = lab.progress("alice", authorized=True)
    assert claimed.xp == 85 and claimed.level == 2
    assert claimed.demos_reviewed == 1
    assert "apprentice_forge" in claimed.unlocked
    assert len(lab.run_batch("alice", authorized=True, consent=True, now=101,
                              max_demos=4)) == 0


def test_unapproved_or_untraceable_knowledge_never_creates_games():
    lab=DragonPracticeLab(sqlite3.connect(":memory:"))
    with pytest.raises(PermissionError):
        lab.offer(lesson(consent=False), now=0, authorized=True)
    with pytest.raises(PermissionError):
        lab.offer(lesson(eligible=False), now=0, authorized=True)
    with pytest.raises(PermissionError):
        lab.offer(lesson(), now=0, authorized=False)
    invalid=ApprovedLesson("alice","Gravity",decision(),"bad",(Mechanic.MOVEMENT,),True)
    with pytest.raises(PermissionError):
        lab.offer(invalid,now=0,authorized=True)
    assert lab.progress("alice",authorized=True).xp == 0
    with pytest.raises(PermissionError):
        lab.run_batch("alice",authorized=True,consent=False,now=1)


def test_batch_quota_daily_ceiling_and_opt_in_revocation():
    lab=DragonPracticeLab(sqlite3.connect(":memory:"),
       PracticePolicy(max_demos_per_lesson=4,max_demos_per_day=3,max_demos_per_batch=3))
    lab.offer(lesson(),authorized=True,now=0)
    rows=lab.run_batch("alice",authorized=True,consent=True,now=100,max_demos=3)
    assert len(rows)==3
    assert lab.run_batch("alice",authorized=True,consent=True,now=101,max_demos=3)==()
    assert len(lab.run_batch("alice",authorized=True,consent=True,
                             now=86400,max_demos=3))==1
    lab.offer(lesson(claim="another"),authorized=True,now=86401)
    lab.revoke("alice",authorized=True)
    assert lab.run_batch("alice",authorized=True,consent=True,
                          now=172800,max_demos=3)==()
    assert lab.progress("alice",authorized=True).verified_lessons==2


def test_owner_isolation_and_auditable_failed_or_rejected_artifacts():
    lab=DragonPracticeLab(sqlite3.connect(":memory:"))
    lab.offer(lesson(),authorized=True,now=2)
    rows=lab.run_batch("alice",authorized=True,consent=True,now=3)
    assert lab.attempts("bob",authorized=True)==()
    with pytest.raises(LookupError):
        lab.artifact("bob",rows[0].attempt_id,authorized=True)
    assert lab.review("alice",rows[0].attempt_id,authorized=True,
                       playtested=False,accepted=False,playtest_digest="e"*64)
    assert lab.attempts("alice",authorized=True)[0].state in ("built","rejected")
    assert lab.progress("alice",authorized=True).demos_reviewed==0
    with pytest.raises(PermissionError):
        lab.attempts("alice",authorized=False)
    with pytest.raises(PermissionError):
        lab.artifact("alice",rows[0].attempt_id,authorized=False)
    with pytest.raises(ValueError):
        lab.review("alice",rows[0].attempt_id,authorized=True,
                   playtested=True,accepted=True,playtest_digest="nonsense")


def test_reopen_persists_artifacts_and_progression():
    db=sqlite3.connect(":memory:")
    first=DragonPracticeLab(db)
    first.offer(lesson(),authorized=True,now=2)
    attempts=first.run_batch("alice",authorized=True,consent=True,now=3)
    html=first.artifact("alice",attempts[0].attempt_id,authorized=True)
    second=DragonPracticeLab(db)
    assert second.artifact("alice",attempts[0].attempt_id,authorized=True)==html
    assert second.progress("alice",authorized=True).demos_built==2
    assert second.attempts("alice",authorized=True)[0].lesson_id==attempts[0].lesson_id


def test_rejects_overbudgets_bad_lesson_and_unknown_mechanics():
    with pytest.raises(ValueError):
        DragonPracticeLab(sqlite3.connect(":memory:"),
                          PracticePolicy(max_demos_per_day=0))
    lab=DragonPracticeLab(sqlite3.connect(":memory:"))
    bad=ApprovedLesson("alice","Lesson",decision(),"b"*64,
                       (Mechanic.MOVEMENT,Mechanic.MOVEMENT),True)
    with pytest.raises(ValueError):
        lab.offer(bad,authorized=True,now=1)
    with pytest.raises(ValueError):
        lab.run_batch("alice",authorized=True,consent=True,now=0,max_demos=999)
    with pytest.raises(ValueError):
        lab.run_batch("alice",authorized=True,consent=True,now=float("nan"))
    assert lab.progress("alice",authorized=True).next_level_xp==75
