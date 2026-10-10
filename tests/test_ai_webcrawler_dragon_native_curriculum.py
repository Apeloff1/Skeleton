"""Bounded curriculum: distinguish compiler evidence from generated source."""
from __future__ import annotations
from hashlib import sha256
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_native_curriculum import DragonNativeCurriculum,MILESTONES
from skeleton.ai.webcrawler.dragon_build_evidence import DragonBuildEvidence
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab,ApprovedLesson
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision


def fixture(owner="alice"):
    db=sqlite3.connect(":memory:")
    parent=DragonPracticeLab(db)
    promotion=PromotionDecision("candidate",True,.98,"calibrated",None,(),
                                 sha256(b"curriculum").hexdigest())
    parent.offer(ApprovedLesson(owner,"Original handheld engineering",promotion,
       "a"*64,(Mechanic.MOVEMENT,Mechanic.EXPLORATION),True),
       now=1,authorized=True)
    native=DragonNativePracticeLab(db,parent)
    evidence=DragonBuildEvidence(db,native,private_signing_key=b"s"*32)
    return db,parent,native,evidence

def structural_gb_fixture():
    # Structurally valid header only, not a compiled or gameplay-verified ROM.
    rom=bytearray(32768)
    checksum=0
    for b in rom[0x134:0x14D]:
        checksum=(checksum-b-1)&0xff
    rom[0x14D]=checksum
    return bytes(rom)

def test_new_dragon_earns_no_console_mastery_from_source_count_alone():
    db,parent,native,evidence=fixture()
    course=DragonNativeCurriculum(native,evidence)
    baseline=course.evaluate("alice",authorized=True)
    assert baseline.curriculum_level==1
    assert baseline.structural_build_targets==()
    assert baseline.next_recommendation.target=="game_boy"
    assert baseline.next_recommendation.genre=="arcade_score_attack"
    assert "nes" in {r["target"] for r in baseline.blocked}
    assert len(MILESTONES)>=16
    one=course.generate_next("alice",authorized=True,consent=True,now=10)
    assert one[1].target_id=="game_boy"
    assert one[0].curriculum_level==1
    assert one[0].native_source_attempts==1
    assert parent.progress("alice",authorized=True).xp==30
    assert course.evaluate("bob",authorized=True).native_source_attempts==0
    with pytest.raises(PermissionError):
        course.generate_next("alice",authorized=True,consent=False,now=11)
    with pytest.raises(PermissionError):
        course.evaluate("alice",authorized=False)

def test_only_signed_rom_bytes_unlock_next_hardware_platform():
    db,parent,native,evidence=fixture()
    course=DragonNativeCurriculum(native,evidence)
    _,attempt=course.generate_next("alice",authorized=True,consent=True,now=10)
    before=course.evaluate("alice",authorized=True)
    assert before.next_recommendation.target=="game_boy"
    evidence.attest_rom(
        "alice",attempt.attempt_id,structural_gb_fixture(),authorized=True,
        trusted_worker=True,toolchain="RGBDS",now=12,
    )
    after=course.evaluate("alice",authorized=True)
    assert after.curriculum_level==2
    assert after.structural_build_targets==("game_boy",)
    assert after.next_recommendation.target=="nes"
    assert ("game_boy", "side_scrolling_platformer") in {(x.target, x.genre) for x in after.unlocked}
    assert "nes" in {r.target for r in after.unlocked}
    assert "game_boy_color" in {r.target for r in after.unlocked}
    assert parent.progress("alice",authorized=True).xp==30
    # The same receipt does not increase evidence level or mint an upgrade.
    assert course.evaluate("alice",authorized=True)==after

def test_explicit_signer_required_for_evidence_unlock():
    db,parent,native,evidence=fixture()
    course=DragonNativeCurriculum(native)
    before=course.evaluate("alice",authorized=True)
    assert before.curriculum_level==1
    a=native.generate("alice",target_id="game_boy",style="arcade_score_attack",
                      now=3,authorized=True,consent=True)
    evidence.attest_rom(
        "alice",a.attempt_id,structural_gb_fixture(),authorized=True,
        trusted_worker=True,toolchain="RGBDS",now=4)
    # If the signing key isn't configured for the curriculum, fail closed.
    assert course.evaluate("alice",authorized=True).curriculum_level==1
