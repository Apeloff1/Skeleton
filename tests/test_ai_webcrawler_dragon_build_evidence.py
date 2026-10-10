"""Actual ROM byte-bound build evidence and cryptographic chain regression."""
from __future__ import annotations
from hashlib import sha256
import json,sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_build_evidence import DragonBuildEvidence
from skeleton.ai.webcrawler.dragon_practice_lab import ApprovedLesson,DragonPracticeLab
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

def fixture():
    db=sqlite3.connect(":memory:")
    parent=DragonPracticeLab(db)
    proof=PromotionDecision("claim",True,.98,"calibrated",None,(),
                            sha256(b"original lesson").hexdigest())
    parent.offer(ApprovedLesson("alice","Native sound and graphics",proof,
        "a"*64,(Mechanic.MOVEMENT,Mechanic.EXPLORATION),True),
        now=1,authorized=True)
    lab=DragonNativePracticeLab(db,parent)
    a=lab.generate("alice",target_id="nes",style="arcade_score_attack",
                   authorized=True,consent=True,now=2)
    return db,parent,lab,a

def valid_nrom():
    # This synthetic byte fixture is structurally an iNES image, NOT a
    # successfully compiled game. Production attestation requires the
    # isolated trusted worker that owns the signing key and compiler logs.
    raw=bytearray(16+32768+8192)
    raw[:6]=b"NES\x1a\x02\x01"
    return bytes(raw)

def test_native_binary_evidence_signed_owner_bound_and_replay_verified():
    db,parent,lab,attempt=fixture()
    signer=DragonBuildEvidence(db,lab,private_signing_key=b"k"*32)
    with pytest.raises(PermissionError):
        signer.attest_rom("alice",attempt.attempt_id,valid_nrom(),
            authorized=True,trusted_worker=False,toolchain="cc65",now=3)
    one=signer.attest_rom("alice",attempt.attempt_id,valid_nrom(),
         authorized=True,trusted_worker=True,toolchain="cc65",now=3)
    assert one.target=="nes"
    assert one.bytes_written==40976
    assert one.binary_sha256==sha256(valid_nrom()).hexdigest()
    assert one.source_digest==attempt.source_digest
    assert one.claim=="rom_header_and_content_verified_not_gameplay_verified"
    assert len(one.signature)==64
    assert len(signer.history("alice",authorized=True))==1
    assert signer.history("bob",authorized=True)==()
    again=signer.attest_rom("alice",attempt.attempt_id,valid_nrom(),
         authorized=True,trusted_worker=True,toolchain="cc65",now=4)
    assert again==one
    assert len(signer.history("alice",authorized=True))==1
    assert parent.progress("alice",authorized=True).xp==30
    with pytest.raises(LookupError):
        signer.attest_rom("bob",attempt.attempt_id,valid_nrom(),
            authorized=True,trusted_worker=True,toolchain="cc65",now=3)

def test_forged_toolchain_corrupt_binary_and_signing_key_rejected():
    db,parent,lab,attempt=fixture()
    signer=DragonBuildEvidence(db,lab,private_signing_key=b"k"*32)
    with pytest.raises(ValueError):
        DragonBuildEvidence(db,lab,private_signing_key=b"123")
    with pytest.raises(ValueError,match="compiler"):
        signer.attest_rom("alice",attempt.attempt_id,valid_nrom(),
            authorized=True,trusted_worker=True,toolchain="RGBDS",now=5)
    invalid=valid_nrom()[:-3]
    with pytest.raises(ValueError):
        signer.attest_rom("alice",attempt.attempt_id,invalid,
            authorized=True,trusted_worker=True,toolchain="cc65",now=5)
    receipt=signer.attest_rom("alice",attempt.attempt_id,valid_nrom(),
        authorized=True,trusted_worker=True,toolchain="cc65",now=6)
    row=db.execute("""SELECT receipt_json FROM dragon_native_build_evidence
        WHERE owner=?""",("alice",)).fetchone()
    tampered=json.loads(row[0])
    tampered["bytes_written"]=123
    db.execute("""UPDATE dragon_native_build_evidence SET receipt_json=?
        WHERE owner=?""",(json.dumps(tampered),"alice"))
    db.commit()
    with pytest.raises(ValueError,match="signature"):
        signer.history("alice",authorized=True)
    assert receipt.binary_sha256==sha256(valid_nrom()).hexdigest()


def test_c64_real_compile_receipt_and_curriculum_round_trip(tmp_path):
    import shutil
    from skeleton.ai.webcrawler.dragon_native_projects import NativeProject
    from skeleton.ai.webcrawler.dragon_native_compile import compile_local
    from skeleton.ai.webcrawler.dragon_native_curriculum import DragonNativeCurriculum
    if not shutil.which("cl65"):
        pytest.skip("cc65 required for actual C64 build evidence")
    db, parent, lab, _ = fixture()
    attempt = lab.generate("alice", target_id="commodore_64", style="arcade_score_attack",
                           authorized=True, consent=True, now=3)
    source = NativeProject(**lab.project("alice", attempt.attempt_id, authorized=True))
    for name, text in source.files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    result = compile_local(source, tmp_path, authorized=True)
    assert result.state == "compiled_native", result.message
    signer = DragonBuildEvidence(db, lab, private_signing_key=b"k" * 32)
    with pytest.raises(ValueError, match="compiler"):
        signer.attest_from_local_file("alice", attempt.attempt_id, result.binary_path,
            authorized=True, trusted_worker=True, toolchain="RGBDS", now=4)
    receipt = signer.attest_from_local_file("alice", attempt.attempt_id, result.binary_path,
        authorized=True, trusted_worker=True, toolchain="cc65", now=4)
    assert receipt.binary_sha256 == result.binary_sha256
    assert receipt.source_digest == source.digest
    assert receipt.claim == "native_program_header_and_content_verified_not_gameplay_verified"
    assert signer.history("alice", authorized=True) == (receipt,)
    assert signer.history("bob", authorized=True) == ()
    snapshot = DragonNativeCurriculum(lab, signer).evaluate("alice", authorized=True)
    assert snapshot.structural_build_targets == ("commodore_64",)
    assert snapshot.curriculum_level == 1  # A C64 receipt does not prove GB/NES mastery.
    duplicate = signer.attest_from_local_file("alice", attempt.attempt_id, result.binary_path,
        authorized=True, trusted_worker=True, toolchain="cc65", now=5)
    assert duplicate == receipt
    assert parent.progress("alice", authorized=True).xp == 30
