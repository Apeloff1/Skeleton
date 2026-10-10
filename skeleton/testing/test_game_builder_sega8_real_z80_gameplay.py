"""Actual cartridge Z80 HUD observation and replay custody adversarial tests.

Synthetic VDP fixtures validate the observer only. They are not native game
verification or a claim that hardware cartridge gameplay has passed.
"""
from __future__ import annotations

import json

import pytest

from scripts.game_builder.emulate_sega8_sdcc_boot import Sega8Machine
from scripts.game_builder.sega8_real_z80_gameplay import (
    Sega8NativeGameplayError, _glyph, _read_project, observe_actual_gameplay,
    verify_original_z80_gameplay, advance_semantic_trace,
    ActualZ80GameSession, MAX_TOTAL_GAMEPLAY_FRAMES,
    MAX_TOTAL_GAMEPLAY_INSTRUCTIONS, MAX_INSTRUCTION_FRAMES,
)


def _demo_machine(target: str, *, score: int=1280, rank: int=7):
    machine = Sega8Machine(bytes(32768), target=target)
    machine.registers[2]=0xFF  # Correct mode-4 name table at $3800
    left, top, hud = ((0,2,0) if target=="sega_master_system" else (6,5,3))
    def paint(x,y,value,attr=0):
        pos=0x3800 + (y*32 + x)*2
        machine.vram[pos]=value
        machine.vram[pos+1]=attr
    def digits(columns,value):
        for c,ch in zip(reversed(columns),reversed(str(value).zfill(len(columns)))):
            paint(left+c,hud,6+int(ch))
    paint(left+3,top+5,5)
    digits((1,2),0)
    digits((5,6),4)
    digits((9,10),8)
    digits((12,),rank)
    digits((13,14,15,16),score)
    paint(left+18,hud,21)
    return machine,paint


@pytest.mark.parametrize("target",("sega_master_system","sega_game_gear"))
@pytest.mark.parametrize("score,rank",((0,0),(30,1),(790,6),(1280,7)))
def test_native_guest_screen_observer_decodes_real_vdp_original_hud(target,score,rank):
    machine,_=_demo_machine(target,score=score,rank=rank)
    out=observe_actual_gameplay(machine,width=17,height=15)
    assert out=={
        "level":7,"x":3,"y":5,"health":4,
        "score":score,"gems_remaining":0,"bond_rank":rank,
    }
    assert _glyph(machine, (0 if target=="sega_master_system" else 6)+3,
                  (2 if target=="sega_master_system" else 5)+5)==5


@pytest.mark.parametrize("target",("sega_master_system","sega_game_gear"))
def test_guest_screen_observer_never_accepts_multiple_players_or_hud_forgery(target):
    machine,paint=_demo_machine(target)
    left,top,hud=((0,2,0) if target=="sega_master_system" else (6,5,3))
    paint(left+2,top+3,16)
    with pytest.raises(Sega8NativeGameplayError,match="one hero"):
        observe_actual_gameplay(machine,width=17,height=15)
    paint(left+2,top+3,0)
    paint(left+18,hud,6)
    with pytest.raises(Sega8NativeGameplayError,match="companion"):
        observe_actual_gameplay(machine,width=17,height=15)
    paint(left+18,hud,17)
    paint(left+14,hud,22)
    with pytest.raises(Sega8NativeGameplayError,match="digit"):
        observe_actual_gameplay(machine,width=17,height=15)
    paint(left+14,hud,14)
    paint(left+12,hud,14)  # companion rank eight cannot be attained
    with pytest.raises(Sega8NativeGameplayError,match="rank"):
        observe_actual_gameplay(machine,width=17,height=15)
    paint(left+12,hud,13)
    paint(left+3,top+5,5,attr=1)
    with pytest.raises(Sega8NativeGameplayError,match="high bit"):
        observe_actual_gameplay(machine,width=17,height=15)


def test_actual_native_gameplay_rejects_unknown_target_without_loading_rom(tmp_path):
    with pytest.raises(Sega8NativeGameplayError,match="unknown"):
        verify_original_z80_gameplay(
            tmp_path/"not-found.sms",tmp_path/"not-found",
            tmp_path/"not-found.json",target="third_party_console",
        )


@pytest.mark.parametrize("target",("sega_master_system","sega_game_gear"))
def test_native_source_manifest_type_bounds_and_release_gate_fail_closed(tmp_path,target):
    source=tmp_path/"source"
    source.mkdir()
    (source/"game.c").write_text("/* synthetic source, never a release */\n",encoding="utf-8")
    (source/"Makefile").write_text("all:\n\t@true\n",encoding="utf-8")
    metadata={
        "schema":"skeleton.game_builder.native_sega8_source.v1",
        "platform":target,
        "target_rom_suffix":"sms" if target=="sega_master_system" else "gg",
        "width":17,"height":15,"levels":3,
        "binary_compiled":False,"emulator_playthrough_verified":False,
        "physical_hardware_verified":False,"release_approved":False,
        "distribution_licensed":False,
        "third_party_game_or_firmware_redistributed":False,
    }
    manifest=source/"manifest.json"
    manifest.write_text(json.dumps(metadata),encoding="utf-8")
    accepted=_read_project(source,target)
    assert accepted["manifest"]==metadata
    assert len(accepted["source_digest"])==64
    for name,bad in (
        ("width","17"),("width",True),("height","15"),
        ("levels",8.0),("levels",True),("width",60),
        ("height",50),("levels",99),("release_approved",True),
        ("distribution_licensed",None),
        ("physical_hardware_verified","false"),
        ("binary_compiled",True),
        ("third_party_game_or_firmware_redistributed",True),
    ):
        forged=dict(metadata)
        forged[name]=bad
        manifest.write_text(json.dumps(forged),encoding="utf-8")
        with pytest.raises(Sega8NativeGameplayError):
            _read_project(source,target)
    manifest.write_text(json.dumps(metadata),encoding="utf-8")
    assert _read_project(source,target)["manifest"]==metadata
    old=manifest.read_bytes()
    manifest.unlink()
    outside=tmp_path/"external-manifest.json"
    outside.write_bytes(old)
    manifest.symlink_to(outside)
    with pytest.raises(Exception):
        _read_project(source,target)



def test_native_semantic_trace_is_deterministic_for_same_screen_and_actions_across_consoles():
    seed=bytes.fromhex("0f"*32)
    game_state={
        "level":0,"x":1,"y":2,"health":5,"score":0,
        "gems_remaining":4,"bond_rank":0,
    }
    first=advance_semantic_trace(seed,0,None,game_state)
    right=advance_semantic_trace(first,1,"right",{**game_state,"x":2})
    assert right==advance_semantic_trace(
        advance_semantic_trace(seed,0,None,game_state),
        1,"right",{**game_state,"x":2},
    )
    assert right!=advance_semantic_trace(first,1,"left",{**game_state,"x":2})
    assert right!=advance_semantic_trace(first,1,"right",{**game_state,"x":3})
    assert right!=advance_semantic_trace(first,2,"right",{**game_state,"x":2})
    assert right!=advance_semantic_trace(first,1,"right",{**game_state,"score":10,"x":2})
    assert len(right)==32


@pytest.mark.parametrize("index,button,state",[
    (0,"right",{"level":0,"x":1,"y":2,"health":5,"score":0,"gems_remaining":4,"bond_rank":0}),
    (1,None,{"level":0,"x":1,"y":2,"health":5,"score":0,"gems_remaining":4,"bond_rank":0}),
    (-1,"left",{"level":0,"x":1,"y":2,"health":5,"score":0,"gems_remaining":4,"bond_rank":0}),
    (1,"jump",{"level":0,"x":1,"y":2,"health":5,"score":0,"gems_remaining":4,"bond_rank":0}),
    (1,"right",{"level":0,"x":1,"y":2,"health":5,"score":0,"gems_remaining":4,"bond_rank":False}),
    (1,"right",{"level":0,"x":1,"y":2,"health":5,"score":0,"gems_remaining":4}),
    (1,"right",{"level":0,"x":1,"y":2,"health":5,"score":0,"gems_remaining":4,"bond_rank":0,"copied_game":"bad"}),
])
def test_native_semantic_transcript_rejects_forged_or_invalid_controller_screen_fields(
    index,button,state,
):
    with pytest.raises(Sega8NativeGameplayError):
        advance_semantic_trace(bytes(32),index,button,state)


@pytest.mark.parametrize("invalid",[bytes(31),bytes(33),None,"f"*64,b"",True])
def test_native_semantic_transcript_never_accepts_non_digest_parent(invalid):
    state={
        "level":0,"x":0,"y":0,"health":5,"score":0,
        "gems_remaining":3,"bond_rank":0,
    }
    with pytest.raises(Sega8NativeGameplayError):
        advance_semantic_trace(invalid,0,None,state)


def test_bounded_native_gameplay_denies_runaway_frame_before_running_cpu():
    session=object.__new__(ActualZ80GameSession)
    session.frames=MAX_TOTAL_GAMEPLAY_FRAMES
    with pytest.raises(Sega8NativeGameplayError,match="frame cap"):
        session.step_frame("up")


def test_bounded_native_gameplay_denies_runaway_instructions_before_running_cpu():
    session=object.__new__(ActualZ80GameSession)
    session.frames=0
    session.instructions=MAX_TOTAL_GAMEPLAY_INSTRUCTIONS-MAX_INSTRUCTION_FRAMES+1
    with pytest.raises(Sega8NativeGameplayError,match="instruction budget"):
        session.step_frame("left")
