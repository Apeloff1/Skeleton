"""Native Game Boy platform scrolling and CGB colour-cartridge gates."""
from __future__ import annotations
from hashlib import sha256
import shutil
import pytest

from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_native_cli import emit_demo
from skeleton.ai.webcrawler.dragon_native_compile import compile_local
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog


def platform():
    return render_native_project(
        title="Dragon Jump Adventure",target_id="game_boy",
        style="side_scrolling_platformer",
        candidate_id=sha256(b"GB-gameplay-variant").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.PLATFORMING),
        authorized=True,
    )


def test_scrolling_platformer_has_real_ppu_camera_timing_collision_and_jump():
    p=platform()
    src=p.files["src/main.asm"]
    assert p.status=="source_generated" and p.output=="gb"
    assert "ldh [rSCX],a" in src
    assert "$9800+17*32" in src
    assert "$9800+12*32+5" in src
    assert "VelocityY:" in src
    assert "GravityAndJump:" in src
    assert "    ld a,$FA ; signed -6" in src
    assert "    inc [hl]" in src
    assert "    cp 144" in src
    assert "CollectStar:" in src
    assert "    ld [OAM+6],a" in src
    assert "PlayerWorldX: ds 1" in src
    assert "PlatformTilesEnd:" in src
    assert "CMakeLists.txt" not in p.files
    assert "dragon.gb" in p.files["Makefile"]
    assert p.files["dragon-native-manifest.json"].find(
        "game_boy_scrolling_platformer")!=-1


def test_catalog_exposes_only_real_gb_platformer_support():
    by_id={t["id"]:t for t in target_catalog()}
    assert "side_scrolling_platformer" in by_id["game_boy"]["supported_styles"]
    assert "side_scrolling_platformer" not in by_id["game_boy_color"]["supported_styles"]
    assert "side_scrolling_platformer" not in by_id["nes"]["supported_styles"]


def test_native_scrolling_cartridge_compile_when_rgbds_available(tmp_path):
    if not all(shutil.which(t) for t in ("rgbasm","rgblink","rgbfix")):
        pytest.skip("RGBDS unavailable, GB platformer compilation not certified")
    # The CLI uses its own deterministic candidate digest, which must be
    # used again during local compilation to validate source provenance.
    from skeleton.ai.webcrawler.dragon_native_cli import emit_demo
    title="Dragon Jump Adventure"
    style="side_scrolling_platformer"
    output=tmp_path/"gameboy"
    emit_demo("game_boy",output,title=title,style=style)
    candidate=sha256((title+"\0"+"game_boy"+"\0"+style).encode()).hexdigest()
    p=render_native_project(
        title=title,target_id="game_boy",style=style,candidate_id=candidate,
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    result=compile_local(p,output,authorized=True)
    assert result.state=="compiled_native",result.message
    assert result.bytes_written>=32768
    assert (output/"build/dragon.gb").is_file()
