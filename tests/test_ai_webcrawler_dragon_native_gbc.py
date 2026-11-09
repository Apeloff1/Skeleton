"""Color-only RGBDS cartridge facts and palette initialization tests."""
from __future__ import annotations
from hashlib import sha256
import shutil
import pytest
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_native_compile import compile_local
from skeleton.ai.webcrawler.dragon_native_cli import emit_demo


def project(target="game_boy_color"):
    seed=sha256(("Dragon Tiny Adventure\0"+target+"\0arcade_score_attack").encode()).hexdigest()
    return render_native_project(
        title="Dragon Tiny Adventure",target_id=target,
        candidate_id=seed,style="arcade_score_attack",
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )


def test_game_boy_color_is_hardware_paletted_not_fake_extension():
    game=project()
    assert game.target_id=="game_boy_color" and game.output=="gbc"
    src=game.files["src/main.asm"]
    assert "$FF6A" in src and "$FF6B" in src
    assert "CGBObjectPalette:" in src
    assert "ldh [rOCPD], a" in src
    assert ".loadCGBPalette" in src
    assert "dragon.gbc" in game.files["Makefile"]
    assert "RGBFIX) -v -p 0 -C" in game.files["Makefile"]
    assert game.files["dragon-pixel-art.json"]
    assert src != project("game_boy").files["src/main.asm"]


def test_color_cartridge_compiles_when_rgbds_is_present(tmp_path):
    if not all(shutil.which(cmd) for cmd in ("rgbasm","rgblink","rgbfix")):
        pytest.skip("RGBDS not installed: compilation not verified")
    output=tmp_path/"cgb"
    emit_demo("game_boy_color",output)
    report=compile_local(project(),output,authorized=True)
    assert report.state=="compiled_native",report.message
    rom=(output/"build/dragon.gbc").read_bytes()
    assert rom[0x143]==0xC0
    assert rom[0x14D] == ((-sum(rom[0x134:0x14D])-25)&255)
    assert report.bytes_written==len(rom)
