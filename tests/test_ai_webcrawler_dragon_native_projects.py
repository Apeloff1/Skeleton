"""The native hardware matrix and actual ROM/desktop project emitters."""
from __future__ import annotations

from hashlib import sha256
from zipfile import ZipFile
import io
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab,ApprovedLesson
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project, EMITTERS
from skeleton.ai.webcrawler.dragon_native_targets import TARGETS,CATALOG,STYLES,demand_target
from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
from skeleton.ai.webcrawler.dragon_native_cli import emit_demo

CANDIDATE="d"*64

def make(target:str,style:str="arcade_score_attack"):
    return render_native_project(title="Original Dragon",target_id=target,
        style=style,candidate_id=CANDIDATE,
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION,Mechanic.PHYSICS),
        authorized=True)

def test_platform_matrix_covers_actual_console_and_computer_history():
    assert len(CATALOG)>=45
    assert len(STYLES)>=25
    required=("atari_2600","nes","game_boy","game_boy_color","snes","genesis",
              "game_boy_advance","nintendo_64","nintendo_ds","gamecube",
              "wii","wii_u","nintendo_switch","ps1","ps2","ps3","ps4","ps5",
              "psp","ps_vita","xbox_original","xbox_360","xbox_one",
              "xbox_series","dos_8086","dos_vga","pc_linux","pc_windows",
              "pc_macos","steam_deck")
    assert all(target in CATALOG for target in required)
    assert all(t.status in ("native_source","toolchain_adapter","licensed_sdk","historical_reference")
               for t in TARGETS)
    assert CATALOG["xbox_series"].status=="licensed_sdk"
    assert CATALOG["ps5"].status=="licensed_sdk"
    assert CATALOG["game_boy"].status=="native_source"

@pytest.mark.parametrize("target",sorted(EMITTERS))
def test_native_emitters_make_platform_specific_source_not_html(target):
    p=make(target)
    assert p.status=="source_generated" and p.output in (
        "gb","gbc","nes","tap","prg","xex","dol","3dsx","sms","gg","sfc","z64","nds","pbp","exe","elf","app","bin","gba","xbe","hex","pdx")
    assert len(p.files)>=3 and p.target_id==target
    assert p.digest==sha(p.files)
    assert p==make(target)
    assert all(not name.endswith(".html") for name in p.files)
    assert "Makefile" in p.files or "CMakeLists.txt" in p.files
    assert "src/main.c" in p.files or "src/main.asm" in p.files or "src/main.s" in p.files
    assert "source_generated" in p.files["dragon-native-manifest.json"]
    assert "physics" in p.deferred_mechanics if target in ("game_boy","nes","dos_vga") else True

def sha(v):
    from skeleton.ai.webcrawler.dragon_native_projects import digest
    return digest(v)

def test_gb_is_sm83_code_and_rom_pipeline_not_a_browser_game():
    p=make("game_boy")
    asm=p.files["src/main.asm"]
    assert 'SECTION "Entry", ROM0[$100]' in asm
    assert 'ldh [rLCDC]' in asm
    assert 'ld [DRAGON_OAM+6]' in asm
    assert "ldh [rJOYP]" in asm
    assert "rgbasm" in p.files["Makefile"].lower()
    assert "rgblink" in p.files["Makefile"].lower()
    assert "rgbfix" in p.files["Makefile"].lower()
    assert "build/dragon.gb" in p.files["Makefile"]

def test_nes_is_6502_ines_nrom_and_chr_pipeline():
    p=make("nes")
    assert '.segment "HEADER"' in p.files["src/main.s"]
    assert "PollPad:" in p.files["src/main.s"]
    assert "ld65" in p.files["Makefile"].lower()
    assert "$2002" in p.files["src/main.s"]
    assert ".segment \"CHARS\"" in p.files["src/main.s"]
    assert "build/dragon.nes" in p.files["Makefile"]

def test_dos_is_real_vga_and_pc_is_sdl_not_browser():
    dos=make("dos_vga")
    assert "0xA0000" in dos.files["src/main.c"]
    assert "dosmemput" in dos.files["src/main.c"]
    assert "djgpp" in dos.files["Makefile"]
    linux=make("pc_linux","side_scrolling_platformer")
    assert "SDL_CreateWindow" in linux.files["src/main.c"]
    assert "CMakeLists.txt" in linux.files
    assert "SCANCODE_SPACE" in linux.files["src/main.c"]

def test_open_sdk_targets_emit_platform_specific_native_programs():
    sega=make("genesis")
    assert "JOY_readJoypad" in sega.files["src/main.c"]
    assert "SYS_doVBlankProcess" in sega.files["src/main.c"]
    assert "makefile.gen" in sega.files["Makefile"]
    gba=make("game_boy_advance")
    assert "0x06000000" in gba.files["src/main.c"]
    assert "0x04000130" in gba.files["src/main.c"]
    assert "gbafix" in gba.files["Makefile"]
    psx=make("ps1")
    assert "psn00bsdk_add_executable" in psx.files["CMakeLists.txt"]
    assert "ResetGraph" in psx.files["src/main.c"]
    xbox=make("xbox_original")
    assert "NXDK_SDL" in xbox.files["Makefile"]
    assert "SDL_GameControllerGetAxis" in xbox.files["src/main.c"]
    assert xbox.output=="xbe"


def test_locked_console_targets_fail_instead_of_pretending(tmp_path):
    with pytest.raises(PermissionError):
        make("ps5")
    with pytest.raises(PermissionError):
        make("xbox_series")
    with pytest.raises(ValueError):
        make("wii_u")
    with pytest.raises(PermissionError):
        render_native_project(title="Good Game",target_id="game_boy",
            style="racing",candidate_id=CANDIDATE,
            mechanics=(Mechanic.MOVEMENT,),authorized=False)
    with pytest.raises(ValueError):
        render_native_project(title="Good Game",target_id="../../tmp",
            style="racing",candidate_id=CANDIDATE,
            mechanics=(Mechanic.MOVEMENT,),authorized=True)
    with pytest.raises(ValueError):
        render_native_project(title="Original game",target_id="nes",
            style="bad",candidate_id=CANDIDATE,
            mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_original_source_cli_creates_real_project_files(tmp_path):
    path=tmp_path/"rom"
    hashes=emit_demo("game_boy",path)
    assert "src/main.asm" in hashes
    assert (path/"src/main.asm").is_file()
    assert (path/"Makefile").is_file()
    with pytest.raises(FileExistsError):
        emit_demo("game_boy",path)
    assert hashes==emit_demo("game_boy",path,overwrite=True)

def _approved(owner):
    promotion=PromotionDecision("claim",True,.99,"calibrated",None,(),
                                sha256(b"approved-claim").hexdigest())
    return ApprovedLesson(owner,"Dragon's Physics",promotion,"a"*64,
                          (Mechanic.MOVEMENT,Mechanic.EXPLORATION,Mechanic.PHYSICS),True)

def test_canonical_lessons_generate_durable_native_source_zip_and_isolate_owner():
    db=sqlite3.connect(":memory:")
    parent=DragonPracticeLab(db)
    native=DragonNativePracticeLab(db,parent)
    owner="alice"
    with pytest.raises(PermissionError):
        native.generate(owner,target_id="game_boy",style="arcade_score_attack",
                        now=50,authorized=True,consent=True)
    parent.offer(_approved(owner),now=10,authorized=True)
    one=native.generate(owner,target_id="game_boy",style="arcade_score_attack",
                        now=50,authorized=True,consent=True)
    assert one.state=="source_generated"
    assert parent.progress(owner,authorized=True).xp==30
    assert len(native.list(owner,authorized=True))==1
    assert native.list("bob",authorized=True)==()
    with pytest.raises(LookupError):
        native.archive("bob",one.attempt_id,authorized=True)
    zipped,zipped_hash=native.archive(owner,one.attempt_id,authorized=True)
    assert sha256(zipped).hexdigest()==zipped_hash
    with ZipFile(io.BytesIO(zipped)) as z:
        assert "src/main.asm" in z.namelist()
        assert b"SECTION" in z.read("src/main.asm")
        assert "Makefile" in z.namelist()
    assert native.archive(owner,one.attempt_id,authorized=True)==(zipped,zipped_hash)
    second=DragonNativePracticeLab(db,parent)
    assert second.project(owner,one.attempt_id,authorized=True)["target_id"]=="game_boy"
    variant=native.generate(owner,target_id="game_boy",style="arcade_score_attack",
                            now=55,authorized=True,consent=True)
    assert variant.variant==1 and variant.attempt_id!=one.attempt_id
    assert native.project(owner,variant.attempt_id,authorized=True)["digest"]!=one.source_digest
    nes=native.generate(owner,target_id="nes",style="arcade_score_attack",
                        now=55,authorized=True,consent=True)
    assert nes.target_id=="nes"
    assert parent.progress(owner,authorized=True).xp==30
    parent.revoke(owner,authorized=True)
    with pytest.raises(PermissionError):
        native.generate(owner,target_id="pc_linux",style="racing",
                        now=56,authorized=True,consent=True)

def test_native_and_legacy_attempts_share_daily_capacity():
    from skeleton.ai.webcrawler.dragon_practice_lab import PracticePolicy
    db=sqlite3.connect(":memory:")
    parent=DragonPracticeLab(db,PracticePolicy(max_demos_per_day=1,max_demos_per_batch=1))
    parent.offer(_approved("alice"),now=0,authorized=True)
    native=DragonNativePracticeLab(db,parent)
    a=native.generate("alice",target_id="game_boy",style="arcade_score_attack",
                      now=1,authorized=True,consent=True)
    assert a
    with pytest.raises(ValueError,match="budget"):
        native.generate("alice",target_id="nes",style="arcade_score_attack",
                        now=2,authorized=True,consent=True)
