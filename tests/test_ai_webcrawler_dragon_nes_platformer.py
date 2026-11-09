"""NES native 6502 side-scroller: original PPU, world mechanics, real ROM build."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json,subprocess,shutil
import pytest
from skeleton.ai.webcrawler.dragon_nes_platformer import (
    nes_platformer_source,_nametables,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

def project():
    return render_native_project(
        title="Dragon Original NES Scrolling Adventure",
        target_id="nes",style="side_scrolling_platformer",
        candidate_id=sha256(b"NES-NROM-original-side-scroll").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION,
                   Mechanic.PLATFORMING,Mechanic.PHYSICS),
        authorized=True)

def test_real_dedicated_gameplay_mode_and_hardware_compatibility():
    p=project()
    assert p.status=="source_generated"
    assert p.output=="nes"
    assert p==project()
    assert "src/main.s" in p.files
    assert "nes.cfg" in p.files
    assert "Makefile" in p.files
    assert "dragon-nes-scroller.json" in p.files
    assert "dragon-pixel-art.json" not in p.files
    assert "RODATA: load=PRG, type=ro;" in p.files["nes.cfg"]
    assert p.files["nes.cfg"].count("RODATA: load=PRG, type=ro;")==1
    info=json.loads(p.files["dragon-nes-scroller.json"])
    assert info["world_tile_columns"]==64
    assert info["levels"]==4
    assert info["mirroring"]=="vertical_for_horizontal_scroll"
    assert info["original_chr_tiles"]==8
    assert not info["compiled"] and not info["emulator_tested"]
    manifest=json.loads(p.files["dragon-native-manifest.json"])
    assert manifest["runtime_gameplay_mode"]=="nes_horizontal_scroll_platformer"
    assert manifest["campaign_stages"]==4
    assert "platforming" in manifest["supported_mechanics"]
    assert "physics" in manifest["supported_mechanics"]
    target=next(x for x in target_catalog() if x["id"]=="nes")
    assert target["supported_styles"]==(
        "arcade_score_attack","side_scrolling_platformer")
    assert "source" in p.files["README.md"].lower()

def test_true_ppu_scroll_vblank_controller_and_collision_code():
    code=nes_platformer_source(123)["src/main.s"]
    for fragment in (
        '.byte "NES",$1A,2,1,1,0',
        'sta $4014',          # real hardware OAM DMA
        'sta $2005',          # hardware PPU scroll
        'ora CamHi',          # select horizontal nametable
        'lda #<Background0', 'lda #<Background1',
        'lda (PtrLo),y',      # copy actual 2KB PPU map
        'NMI:', 'rti',
        'lda $4016',          # native controller shift register
        'sta BtnA', 'sta BtnL', 'sta BtnR',
        'lda OnFloor','sta Jump',
        'sbc #3','adc #2',    # gravity and jump impulse
        'lda #22','sta Jump', # enough jump height to clear ledge
        'cmp #200','lda #200',  # 8x8 sprite rests on tile row 26
        'UpdateEnemy:', 'inc Score', 'dec Lives',
        'lda #42','sta Damage',  # invulnerability timer
        'NextStage:', 'cmp #5', 'bcs FullScroll',
        '.segment "CHARS"', '.segment "RODATA"',
    ):
        assert fragment in code,fragment
    assert "SDL_" not in code and "WinMain" not in code
    # ca65 treats one-letter CPU register names as reserved tokens.
    assert "\nHeroY: .res 1\n" in code
    assert "\nY: .res 1\n" not in code
    assert "__CHR__" not in code and "__BG0__" not in code

def test_original_tilemaps_chrs_are_bounded_and_reproducible():
    a,b=_nametables()
    assert len(a)==len(b)==1024
    assert a!=b
    assert set(a).issubset({0,1})
    assert set(b).issubset({0,1})
    assert a[-64:]==b[-64:]==bytes(64)
    source=nes_platformer_source(10)["src/main.s"]
    other=nes_platformer_source(10)["src/main.s"]
    assert source==other
    source2=nes_platformer_source(11)["src/main.s"]
    assert source==source2, "the authored stage graphics are seed-independent"
    # Seed enters the manifests elsewhere; real tile format is stable.
    p1=nes_platformer_source(10)
    p2=nes_platformer_source(10)
    assert p1==p2
    data=json.loads(p1["dragon-nes-scroller.json"])
    assert len(data["bg0_digest"])==64
    assert len(data["bg1_digest"])==64
    assert len(data["chr_digest"])==64
    assert sha256(a).hexdigest()==data["bg0_digest"]

def test_other_nes_source_is_not_replaced_and_illegal_gameplay_rejected():
    original=render_native_project(
        title="Dragon Original Arcade NES",target_id="nes",
        style="arcade_score_attack",
        candidate_id="1"*64,mechanics=(Mechanic.MOVEMENT,),authorized=True)
    new=project()
    assert original.files["src/main.s"]!=new.files["src/main.s"]
    assert original.files["src/main.s"].startswith('.segment "HEADER"')
    with pytest.raises(ValueError,match="not implemented|not implemented the requested"):
        render_native_project(
            title="Dragon Original Arcade NES",target_id="nes",
            style="grand_strategy",candidate_id="2"*64,
            mechanics=(Mechanic.MOVEMENT,),authorized=True)
    for invalid in (True,-1,2**32,"hack",1.5):
        with pytest.raises(ValueError):
            nes_platformer_source(invalid)

def test_actual_nes_rom_ca65_ld65_build_and_ines_header(tmp_path):
    if not shutil.which("ca65") or not shutil.which("ld65"):
        pytest.skip("cc65's actual ca65/ld65 compiler suite is not installed")
    project_files=project().files
    for name,body in project_files.items():
        path=tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(body,encoding="utf-8")
    compiled=subprocess.run(["make","-C",str(tmp_path),"all"],
                            timeout=80,capture_output=True,text=True)
    assert compiled.returncode==0,(compiled.stdout,compiled.stderr)
    binary=(tmp_path/"build/dragon.nes").read_bytes()
    assert len(binary)==16+2*16384+8192
    assert binary.startswith(b"NES\x1a")
    assert binary[4]==2 and binary[5]==1 and binary[6]&1==1
    # Both nametable graphics and CHR are in actual iNES binary payload.
    assert binary[-8192:]!=bytes(8192)
