"""Independently authored per-stage hardware palette adaptation and guest CRAM proof.

Original theme zero remains identical to source; future levels rotate visible
accent colors within the distinct physical SMS RGB222 / Game Gear RGB444 limits.
No commercial palette, extracted firmware or third-party graphics is used.
"""
from __future__ import annotations

import json

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.sega_8bit_native_export import (
    _authored_stage_accents, compile_native_sega_8bit,
)
from scripts.game_builder.emulate_sega8_sdcc_boot import Sega8Machine
from scripts.game_builder.sega8_real_z80_gameplay import (
    Sega8NativeGameplayError, verify_original_stage_palette,
)


@pytest.mark.parametrize("target,field,bits",(
    ("sega_master_system","master_system_original_stage_rgb222_accents",2),
    ("sega_game_gear","game_gear_original_stage_rgb444_accents",4),
))
@pytest.mark.parametrize("theme",("forest","space","desert","ocean","arcade"))
def test_each_original_stage_has_real_hardware_color_envelope(
    target,field,bits,theme,
):
    intent=GameBuildIntent(
        project_id="authored-stage-chroma",
        title="Original Stage Color Language",subtitle="Native homebrew artwork",
        seed=198801,width=17,height=15,levels=8,
        collectibles_per_level=3,hazards_per_level=4,
        theme=theme,starting_health=4,
    )
    world=generate_playable_world(intent,authorized=True)
    rights=HomebrewSource(
        project_id=intent.project_id,platform_id="bandai_wonderswan",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("original art","independent palette and level"),
    )
    project=compile_native_sega_8bit(world,rights,target,authorized=True)
    meta=json.loads(project.manifest_json)
    expected=meta[field]
    bound=(1 << (3*bits))-1
    assert len(expected)==8
    assert expected[0]==meta[
        "master_system_original_rgb222_palette"
        if bits==2 else "game_gear_original_rgb12_palette"
    ][1:3]
    assert all(isinstance(item,list) and len(item)==2 for item in expected)
    assert all(0<=v<=bound for colors in expected for v in colors)
    # The RGB222 ocean/forest case exposed visually identical accents after
    # rotation and saturation; enforce a minimum physical channel distance.
    minimum_delta=2 if bits==2 else 4
    mask=(1<<bits)-1
    for first,second in expected:
        distance=sum(
            abs(((first>>(bits*n))&mask)-((second>>(bits*n))&mask))
            for n in range(3)
        )
        assert distance>=minimum_delta
    assert len({tuple(color) for color in expected})>=3
    assert meta["native_per_stage_hardware_bg_palette_accents"] is True
    assert meta["native_stage_palettes_change_core_gameplay"] is False
    assert project.game_c.count("original_stage_accent_1")>=2
    assert project.game_c.count("original_stage_accent_2")>=2
    assert "__SMS_STAGE_ACCENT_" not in project.game_c
    assert "__GG_STAGE_ACCENT_" not in project.game_c
    machine=Sega8Machine(bytes(32768),target=target)
    for stage,colors in enumerate(expected):
        if bits==2:
            machine.cram[1:3]=bytes(colors)
        else:
            machine.cram[2:6]=bytes((
                colors[0]&255,colors[0]>>8,
                colors[1]&255,colors[1]>>8,
            ))
        verify_original_stage_palette(machine,meta,stage)
        machine.cram[2 if bits==2 else 3]^=1
        with pytest.raises(Sega8NativeGameplayError,match="CRAM diverges"):
            verify_original_stage_palette(machine,meta,stage)
        machine.cram[2 if bits==2 else 3]^=1
    with pytest.raises(Sega8NativeGameplayError,match="metadata"):
        verify_original_stage_palette(machine,meta,8)


@pytest.mark.parametrize("bits", (2,4))
def test_original_color_variants_do_not_mutate_author_owned_palettes(bits):
    limit=3 if bits==2 else 15
    base=(0,1,limit//2,limit*(1+(1<<bits)+(1<<(2*bits))))
    out=_authored_stage_accents(base,8,bits)
    assert out[0]==(base[1],base[2])
    assert len(out)==8
    assert all(type(value) is int for pair in out for value in pair)
    assert all(0<=value<(1<<(3*bits)) for pair in out for value in pair)
    assert base[0]==0
    assert out==_authored_stage_accents(base,8,bits)
    for bad in (0,-1,9,True):
        with pytest.raises(ValueError,match="envelope"):
            _authored_stage_accents(base,bad,bits)


def test_guest_palette_acceptance_rejects_wrong_console_quantization():
    sms=Sega8Machine(bytes(32768),target="sega_master_system")
    meta={"levels":1,"master_system_original_stage_rgb222_accents":[[16,32]]}
    sms.cram[1:3]=bytes((16,32))
    verify_original_stage_palette(sms,meta,0)
    for value in ("32",True,-1,64,None):
        meta["master_system_original_stage_rgb222_accents"]=[[16,value]]
        with pytest.raises(Sega8NativeGameplayError,match="CRAM limits"):
            verify_original_stage_palette(sms,meta,0)
