"""Trust-gated Lynx compiling, ROM structure and existing HMAC custody chain."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json,sqlite3,shutil
import pytest
from skeleton.ai.webcrawler.dragon_native_compile import _verify,compile_local
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_build_evidence import DragonBuildEvidence
from skeleton.ai.webcrawler.dragon_native_curriculum import MILESTONES
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab,ApprovedLesson
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

def sample_lnx():
    # Structurally correct only. This is not compiled game evidence.
    data=bytearray(131072)
    data[:4]=b"LYNX"
    data[4:6]=(512).to_bytes(2,"little")
    data[8:10]=(1).to_bytes(2,"little")
    return bytes(data)

def prepared_lab():
    db=sqlite3.connect(":memory:")
    parent=DragonPracticeLab(db)
    reviewed=PromotionDecision("original",True,.98,"calibrated",None,(),
                                sha256(b"lynx learning lesson").hexdigest())
    parent.offer(ApprovedLesson("alice","Original native Lynx 65C02 knowledge",
       reviewed,"a"*64,(Mechanic.MOVEMENT,Mechanic.EXPLORATION),True),
       now=1,authorized=True)
    lab=DragonNativePracticeLab(db,parent)
    attempt=lab.generate("alice",target_id="lynx",style="arcade_score_attack",
                         authorized=True,consent=True,now=2)
    return db,parent,lab,attempt

def test_only_lynx_standard_format_can_be_signed():
    cart=sample_lnx()
    assert _verify("lynx",cart)
    for offset,invalid in (
       (0,b"NEZX"),(4,b"\x00\x00"),(8,b"\x00\x00")
    ):
        copy=bytearray(cart)
        copy[offset:offset+len(invalid)]=invalid
        assert not _verify("lynx",bytes(copy))
    assert not _verify("lynx",cart[:400])
    assert not _verify("nes",cart)
    assert "lynx" in {x.target for x in MILESTONES}
    prerequisite=next(x for x in MILESTONES if x.target=="lynx")
    assert prerequisite.requires==("game_boy","nes")

def test_lynx_source_receipt_is_signed_owner_bound_and_non_farmable():
    db,parent,lab,attempt=prepared_lab()
    signer=DragonBuildEvidence(db,lab,private_signing_key=b"L"*32)
    cart=sample_lnx()
    with pytest.raises(PermissionError):
        signer.attest_rom("alice",attempt.attempt_id,cart,
            authorized=True,trusted_worker=False,toolchain="cc65",now=3)
    with pytest.raises(ValueError):
        signer.attest_rom("alice",attempt.attempt_id,cart,
            authorized=True,trusted_worker=True,toolchain="RGBDS",now=3)
    receipt=signer.attest_rom("alice",attempt.attempt_id,cart,
            authorized=True,trusted_worker=True,toolchain="cc65",now=4)
    assert receipt.target=="lynx" and receipt.toolchain=="cc65"
    assert receipt.source_digest==attempt.source_digest
    assert receipt.binary_sha256==sha256(cart).hexdigest()
    assert len(receipt.signature)==64
    assert signer.attest_rom("alice",attempt.attempt_id,cart,
        authorized=True,trusted_worker=True,toolchain="cc65",now=5)==receipt
    assert len(signer.history("alice",authorized=True))==1
    assert signer.history("bob",authorized=True)==()
    assert parent.progress("alice",authorized=True).xp==30
    row=db.execute("SELECT receipt_json FROM dragon_native_build_evidence").fetchone()
    data=json.loads(row[0]);data["binary_sha256"]="0"*64
    db.execute("UPDATE dragon_native_build_evidence SET receipt_json=?",
               (json.dumps(data),));db.commit()
    with pytest.raises(ValueError,match="signature"):
        signer.history("alice",authorized=True)

def test_native_local_compiler_adapter_produces_lynx_cartridge(tmp_path):
    if not shutil.which("cl65"):
        pytest.skip("cc65 Lynx toolchain not installed")
    project=render_native_project(
        title="Dragon Lynx Evidence",target_id="lynx",
        style="arcade_score_attack",candidate_id="c"*64,
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)
    for name,body in project.files.items():
        target=tmp_path/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(body)
    build=compile_local(project,tmp_path,authorized=True,timeout_seconds=105)
    assert build.state=="compiled_native",build.message
    assert build.steps==1
    data=Path(build.binary_path).read_bytes()
    assert data.startswith(b"LYNX")
    assert _verify("lynx",data)
    assert build.binary_sha256==sha256(data).hexdigest()
    assert not any(x.suffix==".vpk" for x in tmp_path.rglob("*"))
