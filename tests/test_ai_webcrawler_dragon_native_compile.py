"""Offline compiler adapter and claim-boundary checks for native ROMs."""
from __future__ import annotations
from hashlib import sha256
import shutil
import pytest
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_native_compile import (
    _verify, compile_local,
)
from skeleton.ai.webcrawler.dragon_native_cli import emit_demo
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

def project(target):
    return render_native_project(
        title="Dragon Tiny Adventure",target_id=target,style="arcade_score_attack",
        candidate_id=sha256(("Dragon Tiny Adventure\0"+target+"\0arcade_score_attack").encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)

def test_missing_toolchain_never_claims_rom_is_built(tmp_path,monkeypatch):
    destination=tmp_path/"native"
    emit_demo("game_boy",destination)
    monkeypatch.setattr(shutil,"which",lambda name:None)
    outcome=compile_local(project("game_boy"),destination,authorized=True)
    assert outcome.state=="toolchain_missing"
    assert outcome.binary_path=="" and outcome.binary_sha256==""
    assert outcome.bytes_written==0

def test_modified_code_or_unauthorized_compilation_rejected(tmp_path):
    destination=tmp_path/"native"
    emit_demo("game_boy",destination)
    p=project("game_boy")
    with pytest.raises(PermissionError):
        compile_local(p,destination,authorized=False)
    (destination/"src/main.asm").write_text("untrusted script")
    with pytest.raises(ValueError,match="changed"):
        compile_local(p,destination,authorized=True)

def test_invalid_roms_are_not_promoted():
    assert not _verify("nes",b"")
    assert not _verify("nes",b"MZ")
    assert not _verify("game_boy",b"\0"*32768)
    valid=bytearray(16+32768+8192)
    valid[:6]=b"NES\x1a\x02\x01"
    assert _verify("nes",bytes(valid))
    assert not _verify("nes",bytes(valid[:-1]))

def test_real_gb_rom_if_rgbds_toolchain_installed(tmp_path):
    if not all(shutil.which(x) for x in ("rgbasm","rgblink","rgbfix")):
        pytest.skip("RGBDS unavailable; this does not count as validated ROM execution")
    destination=tmp_path/"gb"
    emit_demo("game_boy",destination)
    result=compile_local(project("game_boy"),destination,authorized=True)
    assert result.state=="compiled_native",result.message
    assert result.binary_path.endswith(".gb")
    assert result.bytes_written>=32768
    assert result.binary_sha256==sha256((destination/"build/dragon.gb").read_bytes()).hexdigest()

def test_real_nes_rom_if_cc65_toolchain_installed(tmp_path):
    if not all(shutil.which(x) for x in ("ca65","ld65")):
        pytest.skip("cc65 unavailable; this does not count as validated NES ROM")
    destination=tmp_path/"nes"
    emit_demo("nes",destination)
    result=compile_local(project("nes"),destination,authorized=True)
    assert result.state=="compiled_native",result.message
    assert result.binary_path.endswith(".nes")
    assert _verify("nes",(destination/"build/dragon.nes").read_bytes())
